"""Deploy to a running `anvil` and record the addresses in deployments/local.json.

Foundry refuses to write outside contracts/, so the Solidity script only deploys. This wrapper
reads the addresses back out of Foundry's own broadcast record rather than parsing console
output, then writes the file every off-chain component reads. Re-run after every anvil restart.

Usage (from contracts/):
    python script/deploy_local.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

RPC_URL = "http://127.0.0.1:8545"
CHAIN_ID = 31337

CONTRACTS_DIR = Path(__file__).resolve().parent.parent
BROADCAST = CONTRACTS_DIR / "broadcast" / "DeployLocal.s.sol" / str(CHAIN_ID) / "run-latest.json"
OUTPUT = CONTRACTS_DIR.parent / "deployments" / "local.json"


def main() -> int:
    # foundryup's default install dir is often on the shell's PATH but not the OS one.
    forge = shutil.which("forge") or shutil.which("forge", path=str(Path.home() / ".foundry" / "bin"))
    if forge is None:
        print("forge not found on PATH. Install Foundry: https://getfoundry.sh", file=sys.stderr)
        return 1

    result = subprocess.run(
        [forge, "script", "script/DeployLocal.s.sol:DeployLocal", "--rpc-url", RPC_URL, "--broadcast"],
        cwd=CONTRACTS_DIR,
    )
    if result.returncode != 0:
        print("forge script failed. Is anvil running on " + RPC_URL + "?", file=sys.stderr)
        return result.returncode

    transactions = json.loads(BROADCAST.read_text())["transactions"]

    registry = next(
        tx["contractAddress"]
        for tx in transactions
        if tx["transactionType"] == "CREATE" and tx["contractName"] == "AegisRegistry"
    )
    calls = {tx["function"]: tx["arguments"][0] for tx in transactions if tx["transactionType"] == "CALL"}
    owner = transactions[0]["transaction"]["from"]

    deployment = {
        "chainId": CHAIN_ID,
        "rpcUrl": RPC_URL,
        "AegisRegistry": registry,
        "owner": owner,
        "scoreOracle": calls["setScoreOracle(address)"],
        "escrow": calls["setEscrow(address)"],
    }

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(json.dumps(deployment, indent=2) + "\n")
    print(f"\nWrote {OUTPUT}")
    print(json.dumps(deployment, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
