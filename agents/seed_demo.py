"""Seed both demo agents with prior job history before a live run.

A credit model is at its worst on an agent with no history -- one bad job on a two-job file
genuinely is disqualifying. So the demo agents do not start cold: this script gives them a
track record first, by calling recordOutcome from the stand-in escrow account.

    HonestAgent  20 clean $60 jobs over two years           -> lands ~814, excellent, 2000 bps
    SloppyAgent  14 clean + 1 disputed-but-delivered job,
                 $60 each, over the last 460 days           -> lands ~618, good,      4000 bps

SloppyAgent's live lost dispute then drops it to ~383: two tiers, 4000 -> 10000 bps.

History is spread over time with Anvil's clock (evm_setNextBlockTimestamp), because account
age is one of the seven features. The chain clock therefore ends about two years ahead of
the wall clock. Local Anvil only.

Idempotent: agents already holding exactly the seed history are left alone. Anything else
(for example history from a previous live run) is refused -- restart anvil and redeploy.

Usage (from the repo root; anvil, a local deploy, the score service and the oracle running):
    agents/.venv/Scripts/python agents/seed_demo.py      # Windows
    agents/.venv/bin/python agents/seed_demo.py          # macOS / Linux
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

from chain import account, connect, contract, load_deployment, owner_account, send

DAY = 86_400
USDC = 10**6  # recordOutcome values are 6-decimal USDC, SPEC.md section 6

ORACLE_WAIT_SECONDS = 90

# Collateral bps -> band name, SPEC.md sections 3 and 4. Read-only labelling; the bps itself
# comes from the chain.
BAND_BY_BPS = {2000: "excellent", 4000: "good", 7000: "fair", 10000: "poor"}


@dataclass(frozen=True)
class SeedPlan:
    role: str
    outcomes: list[tuple[bool, bool]]  # (delivered, disputed), oldest first
    value_usd: int
    span_days: int  # first job this many days before the end of seeding

    @property
    def counts(self) -> tuple[int, int, int]:
        """(jobsCompleted, jobsDisputed, defaults) the Registry will hold once seeded."""
        return (
            sum(1 for delivered, _ in self.outcomes if delivered),
            sum(1 for _, disputed in self.outcomes if disputed),
            sum(1 for delivered, _ in self.outcomes if not delivered),
        )


CLEAN = (True, False)
DISPUTED_BUT_DELIVERED = (True, True)

# Tuned against the live model. SloppyAgent is the demo's pivot: it must sit clearly inside
# "good" and one lost $500 dispute must take it clearly under 400. These numbers leave about
# 18 points of margin on each side.
PLANS = [
    SeedPlan("HonestAgent", [CLEAN] * 20, value_usd=60, span_days=730),
    SeedPlan(
        "SloppyAgent",
        [CLEAN] * 7 + [DISPUTED_BUT_DELIVERED] + [CLEAN] * 7,
        value_usd=60,
        span_days=460,
    ),
]


def schedule(start: int) -> list[tuple[int, SeedPlan, tuple[bool, bool]]]:
    """Every seed outcome with its block timestamp, all plans ending at the same moment."""
    end = start + max(plan.span_days for plan in PLANS) * DAY
    events = []
    for plan in PLANS:
        first = end - plan.span_days * DAY
        step = plan.span_days * DAY // max(len(plan.outcomes) - 1, 1)
        for i, outcome in enumerate(plan.outcomes):
            events.append((first + i * step, plan, outcome))
    return sorted(events, key=lambda event: event[0])


def seed_state(registry, deployment) -> str:
    """'empty', 'seeded', or a description of why neither."""
    states = []
    for plan in PLANS:
        profile = registry.functions.getProfile(deployment["accounts"][plan.role]["address"]).call()
        counts = (profile[2], profile[3], profile[4])
        if counts == (0, 0, 0):
            states.append("empty")
        elif counts == plan.counts:
            states.append("seeded")
        else:
            states.append(f"{plan.role} has {counts[0]} completed / {counts[1]} disputed / "
                          f"{counts[2]} defaults, which is not the seed history")
    if all(state == "empty" for state in states):
        return "empty"
    if all(state == "seeded" for state in states):
        return "seeded"
    return "; ".join(state for state in states if state not in ("empty", "seeded")) or \
        "only some agents are seeded"


def record_history(w3, registry, deployment) -> None:
    seeder = account(deployment, "Seeder")
    events = schedule(start=w3.eth.get_block("latest").timestamp + DAY)

    for timestamp, plan, (delivered, disputed) in events:
        # The oracle mines its own blocks in between, so never ask for a time in the past.
        timestamp = max(timestamp, w3.eth.get_block("latest").timestamp + 1)
        w3.provider.make_request("evm_setNextBlockTimestamp", [timestamp])
        send(w3, seeder, registry.functions.recordOutcome(
            deployment["accounts"][plan.role]["address"], delivered, disputed, plan.value_usd * USDC
        ))
        print(".", end="", flush=True)
    print(f" {len(events)} outcomes recorded")


def oracle_caught_up(registry, deployment) -> bool:
    for plan in PLANS:
        agent = deployment["accounts"][plan.role]["address"]
        outcomes = registry.events.OutcomeRecorded().get_logs(
            from_block=0, argument_filters={"agent": agent})
        scores = registry.events.ScoreUpdated().get_logs(
            from_block=0, argument_filters={"agent": agent})
        if not scores:
            return False
        last_outcome = (outcomes[-1].blockNumber, outcomes[-1].logIndex)
        last_score = (scores[-1].blockNumber, scores[-1].logIndex)
        if last_score < last_outcome:
            return False
    return True


def wait_for_oracle(registry, deployment) -> bool:
    """While the oracle works through a backlog, a rescore of an *earlier* outcome can land
    after the last outcome and look like catch-up. So also require a quiet period with no
    new ScoreUpdated at all."""
    deadline = time.time() + ORACLE_WAIT_SECONDS
    print("Waiting for the oracle to rescore", end="", flush=True)
    previous = -1
    while time.time() < deadline:
        updates = len(registry.events.ScoreUpdated().get_logs(from_block=0))
        if updates == previous and oracle_caught_up(registry, deployment):
            print(" done")
            return True
        previous = updates
        print(".", end="", flush=True)
        time.sleep(3)
    print()
    return False


def print_scores(registry, deployment) -> None:
    print()
    print(f"{'agent':<13}{'score':>6}  {'band':<10}{'collateral':>11}  jobs  disputed  defaults")
    for plan in PLANS:
        agent = deployment["accounts"][plan.role]["address"]
        profile = registry.functions.getProfile(agent).call()
        bps = registry.functions.requiredCollateralBps(agent).call()
        print(f"{plan.role:<13}{profile[1]:>6}  {BAND_BY_BPS[bps]:<10}{bps:>7} bps"
              f"  {profile[2]:>4}  {profile[3]:>8}  {profile[4]:>8}")


def main() -> int:
    deployment = load_deployment()
    w3 = connect(deployment)
    registry = contract(w3, deployment, "AegisRegistry")

    state = seed_state(registry, deployment)
    if state == "seeded":
        print("Demo agents already hold the seed history. Nothing to record.")
    elif state != "empty":
        print(f"Refusing to seed: {state}.")
        print("Seeding only starts from a clean chain. Restart anvil, then:")
        print("    cd contracts && python script/deploy_local.py")
        return 1
    else:
        seeder = account(deployment, "Seeder")
        owner = owner_account(deployment)
        original_escrow = registry.functions.escrow().call()

        # recordOutcome is escrow-only. If a contract escrow is wired in, borrow the slot for
        # the seeder and always hand it back, even if seeding fails halfway.
        borrowed = original_escrow != seeder.address
        if borrowed:
            print(f"Pointing escrow at the seeder ({seeder.address}) for the duration")
            send(w3, owner, registry.functions.setEscrow(seeder.address))
        try:
            print("Recording seed history", end="", flush=True)
            record_history(w3, registry, deployment)
        finally:
            if borrowed:
                send(w3, owner, registry.functions.setEscrow(original_escrow))
                print(f"Escrow restored to {original_escrow}")

    if not wait_for_oracle(registry, deployment):
        print(f"The oracle has not rescored within {ORACLE_WAIT_SECONDS}s. Is it running?")
        print("Start it and it will catch up on its own: oracle/.venv/Scripts/python oracle/watcher.py")
        print_scores(registry, deployment)
        return 1

    print_scores(registry, deployment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
