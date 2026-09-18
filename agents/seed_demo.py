"""Seed both demo agents with prior job history before a live run.

A credit model is at its worst on an agent with no history -- one bad job on a two-job file
genuinely is disqualifying. So the demo agents do not start cold: this script gives them a
track record first, by calling recordOutcome from the stand-in escrow account.

    HonestAgent  20 clean jobs over two years               -> lands ~864, excellent, 2000 bps
    SloppyAgent  14 clean + 1 disputed-but-delivered job,
                 over the last 380 days                     -> lands ~613, good,      4000 bps

Job values vary between $230 and $880, averaging ~$500, so the live $500 demo job is an
ordinary job for both agents rather than a spike the model rightly reads as risk. With that
history every clean $500 job is worth about +7, and SloppyAgent's live lost dispute drops it
to ~383: two tiers, 4000 -> 10000 bps.

The demo's hirer (demo_driver.py) is seeded too. Collateral is quoted on the HIRER's score
(SPEC.md section 3), so a hirer with no history posts 100% and the demo's headline number --
20% upfront instead of 100% -- never appears. Its clean record puts it in "excellent".

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
USDC = 10**6  # recordOutcome values are 6-decimal USDC, SPEC.md section 5

ORACLE_WAIT_SECONDS = 90

# Collateral bps -> band name, SPEC.md sections 3 and 4. Read-only labelling; the bps itself
# comes from the chain.
BAND_BY_BPS = {2000: "excellent", 4000: "good", 7000: "fair", 10000: "poor"}


# Job values in USD, deliberately uneven. Mean $525, range $230-$880.
JOB_VALUES_USD = [420, 650, 310, 880, 540, 230, 720, 470, 590, 360,
                  810, 500, 280, 640, 450, 760, 390, 560, 250, 690]


@dataclass(frozen=True)
class SeedOutcome:
    delivered: bool
    disputed: bool
    value_usd: int


@dataclass(frozen=True)
class SeedPlan:
    role: str
    outcomes: list[SeedOutcome]  # oldest first
    span_days: int  # first job this many days before the end of seeding

    @property
    def counts(self) -> tuple[int, int, int]:
        """(jobsCompleted, jobsDisputed, defaults) the Registry will hold once seeded."""
        return (
            sum(1 for outcome in self.outcomes if outcome.delivered),
            sum(1 for outcome in self.outcomes if outcome.disputed),
            sum(1 for outcome in self.outcomes if not outcome.delivered),
        )


def clean(count: int) -> list[SeedOutcome]:
    return [SeedOutcome(True, False, JOB_VALUES_USD[i % len(JOB_VALUES_USD)]) for i in range(count)]


def with_disputed_but_delivered(outcomes: list[SeedOutcome]) -> list[SeedOutcome]:
    """Insert one job the hirer disputed but the worker won, mid-history."""
    middle = len(outcomes) // 2
    return outcomes[:middle] + [SeedOutcome(True, True, 450)] + outcomes[middle:]


# Tuned against the live model. SloppyAgent is the demo's pivot: it must sit clearly inside
# "good" and one lost $500 dispute must take it clearly under 400. These numbers leave 14
# points of margin above 600 and 17 below 400.
PLANS = [
    SeedPlan("HonestAgent", clean(20), span_days=730),
    SeedPlan("SloppyAgent", with_disputed_but_delivered(clean(14)), span_days=380),
    # The hirer's own track record, so it hires on 20% collateral rather than 100%.
    SeedPlan("Hirer", clean(22), span_days=730),
]


def schedule(start: int) -> list[tuple[int, SeedPlan, SeedOutcome]]:
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

    for timestamp, plan, outcome in events:
        # The oracle mines its own blocks in between, so never ask for a time in the past.
        timestamp = max(timestamp, w3.eth.get_block("latest").timestamp + 1)
        w3.provider.make_request("evm_setNextBlockTimestamp", [timestamp])
        send(w3, seeder, registry.functions.recordOutcome(
            deployment["accounts"][plan.role]["address"],
            outcome.delivered, outcome.disputed, outcome.value_usd * USDC,
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

    # A run that died mid-seed may have left the escrow slot borrowed. Hand it back.
    seeder_address = account(deployment, "Seeder").address
    if registry.functions.escrow().call() == seeder_address and deployment.get("AegisEscrow"):
        escrow = registry.functions.escrow().call()
        send(w3, owner_account(deployment),
             registry.functions.setEscrow(w3.to_checksum_address(deployment["AegisEscrow"])))
        print(f"Escrow was left pointing at the seeder ({escrow}); restored to {deployment['AegisEscrow']}")

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
        # the seeder and always hand it back, even if seeding fails halfway. The hand-back
        # waits for the oracle first: both sign as account 0 and would race for the nonce.
        borrowed = original_escrow != seeder.address
        if borrowed:
            print(f"Pointing escrow at the seeder ({seeder.address}) for the duration")
            send(w3, owner, registry.functions.setEscrow(seeder.address))
        try:
            print("Recording seed history", end="", flush=True)
            record_history(w3, registry, deployment)
            caught_up = wait_for_oracle(registry, deployment)
        finally:
            if borrowed:
                send(w3, owner, registry.functions.setEscrow(original_escrow))
                print(f"Escrow restored to {original_escrow}")
        return report(registry, deployment, caught_up)

    return report(registry, deployment, wait_for_oracle(registry, deployment))


def report(registry, deployment, caught_up: bool) -> int:
    if not caught_up:
        print(f"The oracle has not rescored within {ORACLE_WAIT_SECONDS}s. Is it running?")
        print("Start it and it will catch up on its own: oracle/.venv/Scripts/python oracle/watcher.py")
        print_scores(registry, deployment)
        return 1

    print_scores(registry, deployment)
    return 0


if __name__ == "__main__":
    sys.exit(main())
