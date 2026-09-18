"""STAND-IN HIRER. Drives one job end to end so the agents can be exercised before the real
escrow and a real hiring agent exist.

    post job -> wait for delivery -> judge it -> accept or dispute -> settle -> show rescore

The judgement is a stand-in too: a delivery that lands less than MIN_WORK_SECONDS after the
job was created (by block time) is treated as "no work was done" and disputed. HonestAgent
works for ~3s; SloppyAgent delivers at once.

Usage (from the repo root; anvil, deploy, score service, oracle and the agent running):
    agents/.venv/Scripts/python agents/demo_driver.py --worker HonestAgent
    agents/.venv/Scripts/python agents/demo_driver.py --worker SloppyAgent --value 500
"""

from __future__ import annotations

import argparse
import sys
import time

from web3.logs import DISCARD

from chain import account, connect, contract, load_deployment, send
from escrow import USDC, escrow_contract, usd

MIN_WORK_SECONDS = 2
DELIVERY_TIMEOUT = 30
RESCORE_TIMEOUT = 30


def say(message: str) -> None:
    print(f"Hirer: {message}", flush=True)


def wait_for(fetch, timeout: float):
    deadline = time.time() + timeout
    while time.time() < deadline:
        found = fetch()
        if found:
            return found[0]
        time.sleep(0.5)
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", required=True, help="Agent name from deployments/local.json")
    parser.add_argument("--value", type=float, default=500, help="Job value in USD (default: 500)")
    args = parser.parse_args()

    deployment = load_deployment()
    if args.worker not in deployment["accounts"]:
        raise SystemExit(f"No account named {args.worker} in deployments/local.json")

    w3 = connect(deployment)
    hirer = account(deployment, "Hirer")
    escrow = escrow_contract(w3, deployment)
    registry = contract(w3, deployment, "AegisRegistry")
    worker = deployment["accounts"][args.worker]["address"]
    value = int(round(args.value * USDC))

    bps_before = registry.functions.requiredCollateralBps(worker).call()

    say(f"posting a {usd(value)} job for {args.worker}")
    receipt = send(w3, hirer, escrow.functions.createJob(worker, value))
    created = escrow.events.JobCreated().process_receipt(receipt, errors=DISCARD)[0]
    job_id = created.args.jobId
    created_at = w3.eth.get_block(receipt.blockNumber).timestamp
    say(f"job #{job_id} is open, collateral posted {usd(created.args.collateralTaken)}")

    delivered = wait_for(
        lambda: escrow.events.JobDelivered().get_logs(
            from_block=receipt.blockNumber, argument_filters={"jobId": job_id}),
        DELIVERY_TIMEOUT,
    )
    if delivered is None:
        say(f"no delivery within {DELIVERY_TIMEOUT}s. Is {args.worker} running?")
        return 1

    took = w3.eth.get_block(delivered.blockNumber).timestamp - created_at
    if took < MIN_WORK_SECONDS:
        say(f"job #{job_id} came back after {took}s, too fast to be real work. Disputing.")
        send(w3, hirer, escrow.functions.dispute(job_id))
    else:
        say(f"job #{job_id} came back after {took}s and checks out. Accepting.")
        send(w3, hirer, escrow.functions.accept(job_id))

    settle_receipt = send(w3, hirer, escrow.functions.settle(job_id))
    # The settle receipt also carries the Registry's OutcomeRecorded; DISCARD skips it quietly.
    settled = escrow.events.JobSettled().process_receipt(settle_receipt, errors=DISCARD)[0]
    if settled.args.workerPaid:
        say(f"job #{job_id} settled, {args.worker} paid {usd(settled.args.amountToWorker)}")
    else:
        say(f"job #{job_id} settled against {args.worker}, not paid")

    rescored = wait_for(
        lambda: registry.events.ScoreUpdated().get_logs(
            from_block=settle_receipt.blockNumber, argument_filters={"agent": worker}),
        RESCORE_TIMEOUT,
    )
    if rescored is None:
        say(f"no rescore within {RESCORE_TIMEOUT}s. Is the oracle running?")
        return 1

    bps_after = registry.functions.requiredCollateralBps(worker).call()
    print()
    print(f"{args.worker} credit score {rescored.args.oldScore} -> {rescored.args.newScore}")
    print(f"  collateral required: {bps_before // 100}% -> {bps_after // 100}% upfront")
    print(f"  reason: {rescored.args.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
