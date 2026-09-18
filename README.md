# AEGIS

**A credit and dispute layer for the AI agent economy.**

Built for DSU DevHack 3.0 — Blockchain & Fintech.

Today, when one AI agent hires another, it prepays 100% of the job value. Every transaction
is a stranger meeting a stranger. AEGIS gives agents a portable credit score built from
their on-chain job history, so a trustworthy agent can transact on **partial collateral**
instead of locking up its entire balance — and if a job goes wrong, the dispute resolves
automatically and both agents' scores move.

We are not building a payment rail or a marketplace. We are building the trust layer that
decides who gets to transact on credit.

**[SPEC.md](SPEC.md) is the single source of truth for all shared types.** Read it first.

---

## How it works

1. **Score.** Each agent has a score from 0 to 1000, derived from its job history:
   jobs completed, dispute rate, defaults, payment timeliness, account age, counterparty
   diversity. New agents start at 500.

2. **Credit.** The score sets how much collateral a hirer must post upfront, as a step
   function (see [SPEC.md §3](SPEC.md#3-collateral-curve)):

   | Score      | Upfront collateral |
   | ---------- | ------------------ |
   | `>= 800`   | 20%                |
   | `>= 600`   | 40%                |
   | `>= 400`   | 70%                |
   | below / unknown | 100%          |

3. **Dispute.** If the worker under-delivers, the job is disputed, settlement moves the
   money, and the outcome is recorded against both agents. The off-chain oracle rescores
   them. No human arbitrator.

---

## Repository layout

```
aegis/
  SPEC.md          Frozen type definitions. Source of truth.
  contracts/       Foundry project — AegisRegistry (implemented), IAegisEscrow (interface only)
  score/           Python — synthetic data, logistic regression, FastAPI scoring service
  agents/          Demo agents, seeding script, stand-in hirer driver
  dashboard/       (not built yet)
```

---

## Contracts

Foundry, Solidity `^0.8.20`, targeting Base Sepolia.

`AegisRegistry` holds every agent's profile and answers the one question the escrow needs:
*how much collateral does this address have to post?*

```bash
cd contracts
make build
make test
```

To deploy:

```bash
cp .env.example .env    # then fill it in — .env is gitignored, never commit it
make deploy-sepolia
```

`AegisEscrow` is **interface only**. No escrow logic is implemented yet.

### Access control

- `updateScore` — only the `scoreOracle` address. The score is written exclusively by the
  off-chain model.
- `recordOutcome` — only the `escrow` address. Updates counters and value handled, never
  the score.
- Both addresses are set by the `owner`.

---

## Score service

Python, FastAPI, scikit-learn. No database, no mock data — every response comes from the
real fitted model.

```bash
cd score
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt

python generate_data.py         # writes data/agents.csv
python train.py                 # fits the model, prints AUC, writes models/
pytest tests/ -v
uvicorn app:app --reload        # http://127.0.0.1:8000/docs
```

### Endpoints

| Method | Path                 | Purpose                                                |
| ------ | -------------------- | ------------------------------------------------------ |
| `GET`  | `/health`            | Liveness plus whether the model is loaded.              |
| `POST` | `/score`             | Score an agent from the seven features.                 |
| `POST` | `/score/from-events` | Derive features from raw job events, then score.        |
| `GET`  | `/agents/state`      | Everything the dashboard renders. Sample: [docs/api_stub.json](docs/api_stub.json). |
| `PUT`  | `/internal/agents/state` | Oracle-only: pushes its in-memory state. Not for the dashboard. |

`/agents/state` is served from the snapshot the oracle pushes after every rescore and on a 3s
heartbeat. It makes no chain reads and needs no database; the dashboard must never touch web3.
Band, collateral percentage and deltas are all computed server-side. A test keeps the live
response identical in shape to `docs/api_stub.json`.

`/score` returns the score, the band, the required collateral in basis points, the raw
default probability, and `top_factors` — the three features that moved the score most,
each with a signed point impact and a plain-English explanation.

`/score/from-events` takes a list of `{delivered, disputed, value_usd, timestamp}` job
events and derives the features itself, so live chain events can be fed straight in.

---

## Oracle (local)

Polls the Registry for `OutcomeRecorded`, rebuilds the agent's history, calls
`/score/from-events`, and writes `updateScore(agent, score, reason)` from Anvil account 0.
History is in memory and replayed from block 0 on every start, so Anvil restarts are safe.

```bash
anvil                                          # terminal 1
cd contracts && python script/deploy_local.py  # writes deployments/local.json
cd score && uvicorn app:app                    # terminal 2
cd oracle && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
copy oracle\.env.example oracle\.env
oracle\.venv\Scripts\python oracle\watcher.py   # terminal 3
```

Until `AegisEscrow` exists, the local deploy wires in `StubEscrow`, a clearly labelled
stand-in (no tokens move, disputes always go against the worker).

### Seeding the demo agents

```bash
agents\.venv\Scripts\python agents\seed_demo.py
```

Gives HonestAgent (account 1) and SloppyAgent (account 2) a prior track record so the demo
does not start from a cold file: ~864 / excellent and ~613 / good. The driver's hirer
(account 3) is seeded too (~875), so it hires on 20% collateral instead of 100%. Idempotent; after a live
run, restart anvil and redeploy to seed again.

### Running the agents

```bash
agents\.venv\Scripts\python agents\honest_agent.py          # terminal 4
agents\.venv\Scripts\python agents\sloppy_agent.py          # terminal 5
agents\.venv\Scripts\python agents\demo_driver.py --worker SloppyAgent   # one job, end to end
```

`demo_driver.py` is a stand-in hirer: it posts a job, disputes any delivery that comes back
in under 2s (SloppyAgent) and accepts the rest (HonestAgent), settles, and prints the rescore.
Agents talk to the escrow only through the `IAegisEscrow` ABI; see `agents/escrow.py` for
where the real escrow plugs in.

---

## The one invariant that matters

The collateral step table is duplicated in two places:

- `contracts/src/AegisRegistry.sol` — `requiredCollateralBps`
- `score/app.py` — `required_collateral_bps`

If those two ever disagree, the demo is broken: the score service quotes a collateral
requirement the chain refuses to honour. Both copies carry a comment pointing at
[SPEC.md §3](SPEC.md#3-collateral-curve). Change both together, or neither. The Python
test suite asserts the mapping matches the contract's table exactly.

---

## Not built yet

- Escrow logic (interface only)
- Real escrow (local deploy uses `StubEscrow` as a stand-in)
- Dashboard
- x402 integration
