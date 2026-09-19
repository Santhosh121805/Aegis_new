<div align="center">

<img src="web/public/aegis-mark.png" alt="AEGIS" width="84" />

# AEGIS

### A credit score for AI agents

**Trustworthy agents hire each other on 20% collateral instead of 100% prepaid.**

[![Base Sepolia](https://img.shields.io/badge/deployed-Base%20Sepolia-0052FF)](#deployed-on-base-sepolia)
[![Solidity](https://img.shields.io/badge/Solidity-0.8.20-363636)](contracts/)
[![Contract tests](https://img.shields.io/badge/contract%20tests-71%20passing-27f293)](contracts/test/)
[![Service tests](https://img.shields.io/badge/service%20tests-66%20passing-27f293)](score/tests/)

Built for **DSU DevHack 3.0 · Blockchain & Fintech**

</div>

---

## The problem

When one AI agent hires another today, it **prepays 100%** of the job. Every deal is a stranger
meeting a stranger: there is no memory of who delivered and who cheated, so nobody can be
trusted with credit and capital sits locked up.

## The idea

AEGIS is the **trust layer** between agents. Not a marketplace and not a payment rail.

| | What it does |
| --- | --- |
| **Score** | Every agent gets a 0–1000 credit score from its on-chain job history, with the three reasons that moved it most. It belongs to the agent's address, so it follows the agent anywhere the registry is read. |
| **Credit** | A hirer's score sets how much it must post upfront: **20%** for an excellent score, **100%** for an unknown or poor one. |
| **Recourse** | If the hirer disputes a delivery, the escrow settles it by a fixed rule, with no human arbitrator. The worker's score moves, and so does what it pays upfront next time. |

## How it works

<p align="center">
  <img src="docs/architecture.svg" alt="AEGIS architecture: agents, on-chain escrow and registry, off-chain oracle, score service and dashboard" width="100%" />
</p>

1. **Open.** A hirer opens a $500 job in the **AegisEscrow** contract.
2. **Quote.** The escrow asks **AegisRegistry** for the hirer's collateral tier and takes only that much USDC upfront.
3. **Deliver.** The worker agent marks the job delivered.
4. **Settle.** The hirer accepts (the worker is paid in full) or disputes (the hirer is refunded).
5. **Record.** The escrow writes the outcome to the registry.
6. **Rescore.** The **oracle** sees the new outcome…
7. …sends the agent's job history to the **score service**, which returns a new score and its reasons…
8. …and writes the score back to the registry on-chain.
9. **Watch.** The **dashboard** shows every score, collateral level and reason, live.

## See it in 60 seconds

Three agents on a live local chain. One command starts everything:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
```

When the **CONTROL** window says **READY**, type:

| Command | What happens | What you see |
| --- | --- | --- |
| `honest` | A hirer with score 877 posts a $500 job for **HonestAgent**. It does the work and gets paid. | Hirer posts **$100, not $500**. HonestAgent **864 → 871 (+7)**. |
| `sloppy` | **SloppyAgent** fakes the work. The hirer disputes, and the escrow refunds the hirer by rule. | SloppyAgent **613 → 382 (−231)**. Its collateral jumps **40% → 100%**. |
| `multi` | One hirer opens **5 jobs at once** with HonestAgent. | Five jobs run concurrently, all settle, five rescores: **871 → 906**. |
| `swarm` | **5 different, never-scored hirers** hire HonestAgent at the same time. | Unknown hirers each post **100%**; every job settles. |
| `reset` | A fresh chain and fresh seed history (about 40s). | Back to 864 / 613 / 877. |

The dashboard at <http://localhost:5173/dashboard> updates within about 2 seconds of each step.

> Run `honest` and `sloppy` first, `multi` and `swarm` after. Use `reset` before each full run-through.

## What is real

- **Smart contracts** for the registry and the escrow, written in Solidity and covered by **71 Foundry tests**, including every illegal state transition.
- **Real token movement.** Collateral is taken at job creation, the remainder at settlement, and refunds happen on a dispute, all through the escrow contract in test USDC.
- **A trained model.** A logistic regression over seven features, with an ROC AUC of 0.82. The score is calibrated so a new agent starts at exactly 500.
- **An explanation with every score.** For example: *"lost dispute on $500 job (−231); top factor: more prior defaults than peers"*. That text is written on-chain with the score.
- **Advisory risk flags** for manipulation patterns: a burst of disputes against one worker, a hirer that disputes far more than average, and a closed ring of agents trading only with each other. They are shown beside the score and never change it.
- **Deployed on Base Sepolia**, with public addresses below. **66 Python tests** cover the score service.

## Deployed on Base Sepolia

| Contract | Address |
| --- | --- |
| AegisRegistry | [`0x449d781155EFe14B6607209a5F9a81c14C69490c`](https://sepolia.basescan.org/address/0x449d781155efe14b6607209a5f9a81c14c69490c) |
| AegisEscrow | [`0x66266ec8FCE6190D507114C9EE91262eC887a9C4`](https://sepolia.basescan.org/address/0x66266ec8fce6190d507114c9ee91262ec887a9c4) |
| MockUSDC | [`0x2fcb4eDe5a608166A1d13b78ae18e435C63e68cC`](https://sepolia.basescan.org/address/0x2fcb4ede5a608166a1d13b78ae18e435c63e68cc) |

The three demo agents are seeded there too, reading **864 / 613 / 877** on-chain. The live demo
runs on a local Anvil chain for deterministic state. **MockUSDC is a test token, not Circle's
USDC.** The contracts are not verified on BaseScan.

## Known limitations

We would rather you hear these from us:

- **The model is trained on synthetic data.** No real agent-economy data exists yet.
- **The oracle is a single key.** It is trusted to write scores; anyone can re-check a score by replaying the chain's outcomes through the public model.
- **Disputes are one-sided.** A hirer can dispute any delivery at no cost to its own score. The serial-disputer flag surfaces this; it does not prevent it.
- **Counterparty diversity is estimated** from job count, because outcomes don't yet record who the counterparty was.
- **The demo agents are scripts.** HonestAgent's "work" is a 3-second wait, and the hirer's quality check is a timing rule. The contracts, oracle and scoring they drive are real.
- **x402 is not integrated.** x402 settles 100% upfront; AEGIS is designed as the credit layer in front of it.

## Tech stack

| Layer | Technology |
| --- | --- |
| Contracts | Solidity 0.8.20, Foundry, OpenZeppelin |
| Chain | Base Sepolia (public), Anvil (demo) |
| Oracle | Python, web3.py |
| Scoring | Python, FastAPI, scikit-learn |
| Agents | Python, web3.py |
| Website | React, Vite |

## Repository layout

```
aegis/
├── contracts/   Solidity: AegisRegistry, AegisEscrow, MockUSDC (+ StubEscrow fallback), Foundry tests
├── score/       Score service: synthetic data, model training, FastAPI, tests
├── oracle/      Watches the chain, rescores agents, writes scores on-chain
├── agents/      HonestAgent, SloppyAgent, the hirer drivers, seeding scripts
├── web/         Website: landing page, live dashboard, how it works, docs
├── scripts/     One-command demo launcher (Windows PowerShell)
├── deployments/ Deployed addresses (Base Sepolia)
├── docs/        Architecture diagram, sample dashboard data
└── SPEC.md      The single source of truth for every shared type and rule
```

**[SPEC.md](SPEC.md)** defines every shared type, the state machine, the collateral curve and the
scoring calibration. Read it for the full design.

---

## Developer guide

<details>
<summary><b>Prerequisites and first-time setup</b></summary>

Windows with PowerShell, [Foundry](https://getfoundry.sh), Python 3.10+, Node.js 20+.

```bash
# score service: data, model, tests
cd score
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python generate_data.py      # writes data/agents.csv
.venv\Scripts\python train.py              # fits the model, prints AUC, writes models/
.venv\Scripts\python -m pytest tests/ -q
cd ..

# oracle and agents (from the repo root)
python -m venv oracle\.venv && oracle\.venv\Scripts\pip install -r oracle\requirements.txt
python -m venv agents\.venv && agents\.venv\Scripts\pip install -r agents\requirements.txt
copy oracle\.env.example oracle\.env

# contracts
cd contracts && forge build && forge test && cd ..

# website
cd web && npm install && cd ..
```

Then start everything with `powershell -ExecutionPolicy Bypass -File scripts\demo.ps1`.

</details>

<details>
<summary><b>Running each piece by hand</b></summary>

```bash
anvil                                            # terminal 1
cd contracts && python script/deploy_local.py    # writes deployments/local.json
cd score && .venv\Scripts\python -m uvicorn app:app --port 8000     # terminal 2
oracle\.venv\Scripts\python oracle\watcher.py    # terminal 3
agents\.venv\Scripts\python agents\seed_demo.py  # seed history: 864 / 613 / 877
agents\.venv\Scripts\python agents\honest_agent.py                  # terminal 4
agents\.venv\Scripts\python agents\sloppy_agent.py                  # terminal 5
agents\.venv\Scripts\python agents\demo_driver.py --worker HonestAgent
agents\.venv\Scripts\python agents\multi_driver.py parallel         # or: swarm
cd web && npm run build && npm run preview       # http://localhost:5173
```

- **Seeding** gives the demo agents a prior track record so they don't start cold. Account age comes from a stored `registeredAt`, not from moving the chain clock. After a live run, restart Anvil and redeploy to seed again. Run the live demo within a day of seeding for the exact numbers above.
- **`demo_driver.py`** is the stand-in hirer. It disputes any delivery that comes back in under 2 seconds, and exits loudly if the hirer is ever recorded as a default.
- **`select_escrow.py --stub | --real`** switches between the real escrow and a token-free fallback.

</details>

<details>
<summary><b>Score service API</b></summary>

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness, and whether the model is loaded |
| `POST` | `/score` | Score an agent from its seven features |
| `POST` | `/score/from-events` | Derive the features from raw job events, then score |
| `GET` | `/agents/state` | Everything the dashboard renders. Sample: [docs/api_stub.json](docs/api_stub.json) |
| `PUT` | `/internal/agents/state` | Oracle only: pushes its state and escrow job facts |

- Band, collateral, deltas and risk flags are all computed server-side.
- Set `AEGIS_STATE_CHAIN=base-sepolia` to serve `/agents/state` straight from the Base Sepolia registry (one `getProfile` per agent, cached for 5s) instead of the local oracle.
- `/dashboard?stub=1` renders the sample data offline, and `?api=` points the dashboard at another score service.

</details>

<details>
<summary><b>Deploying to Base Sepolia</b></summary>

```bash
cd contracts
cp .env.example .env            # BASE_SEPOLIA_RPC_URL and PRIVATE_KEY; .env is gitignored
python script/deploy_sepolia.py # deploys and wires everything, writes deployments/base-sepolia.json
cd ..
agents\.venv\Scripts\python agents\seed_sepolia.py   # optional: seed the demo agents there
```

The deployer becomes both the owner and the score oracle.

</details>

<details>
<summary><b>The one invariant that matters</b></summary>

The collateral table is duplicated in `contracts/src/AegisRegistry.sol` (`requiredCollateralBps`)
and `score/app.py` (`required_collateral_bps`). If they disagree, the service quotes a
collateral level the chain refuses to honour. Change both together, or neither. The Python
tests check against a hand-written copy of the contract's table; they do not read the Solidity.

</details>
