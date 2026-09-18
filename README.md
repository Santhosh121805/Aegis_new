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
   jobs completed, dispute rate, defaults, clean-settlement rate (a proxy: no timing data
   exists), account age, counterparty diversity (estimated from job count). New agents start at 500.

2. **Credit.** The score sets how much collateral a hirer must post upfront, as a step
   function (see [SPEC.md §3](SPEC.md#3-collateral-curve)):

   | Score      | Upfront collateral |
   | ---------- | ------------------ |
   | `>= 800`   | 20%                |
   | `>= 600`   | 40%                |
   | `>= 400`   | 70%                |
   | below / unknown | 100%          |

3. **Dispute.** If the hirer disputes a delivery, settlement refunds the hirer's collateral,
   the worker is not paid, and the outcome is recorded against the worker only. The
   off-chain oracle rescores it. No human arbitrator. Known limitation: the hirer can
   dispute any delivery at no cost to its own score (SPEC.md, intro).

---

## Repository layout

```
aegis/
  SPEC.md          Frozen type definitions. Source of truth.
  contracts/       Foundry project — AegisRegistry, AegisEscrow, MockUSDC; StubEscrow fallback
  score/           Python — synthetic data, logistic regression, FastAPI scoring service
  agents/          Demo agents, seeding script, stand-in hirer driver
  web/             Product site: landing, /dashboard (live), /how-it-works. Vite + React.
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
make deploy-sepolia     # or: python script/deploy_sepolia.py
```

Contracts deployed on Base Sepolia (chain 84532), recorded in
[deployments/base-sepolia.json](deployments/base-sepolia.json). Demo runs locally on Anvil for
deterministic state and controllable time.

| Contract | Address |
| --- | --- |
| AegisRegistry | [`0x449d781155EFe14B6607209a5F9a81c14C69490c`](https://sepolia.basescan.org/address/0x449d781155efe14b6607209a5f9a81c14c69490c) |
| AegisEscrow | [`0x66266ec8FCE6190D507114C9EE91262eC887a9C4`](https://sepolia.basescan.org/address/0x66266ec8fce6190d507114c9ee91262ec887a9c4) |
| MockUSDC | [`0x2fcb4eDe5a608166A1d13b78ae18e435C63e68cC`](https://sepolia.basescan.org/address/0x2fcb4ede5a608166a1d13b78ae18e435c63e68cc) |

**MockUSDC is a test token with public mint, not Circle's USDC.** It stands in because there
is no testnet USDC to hand. The deployer (`0x4234…76C1`) is both owner and score oracle.
Contracts are not verified on BaseScan.

`AegisEscrow` holds real (mock) USDC: it takes the hirer's collateral at `createJob` and the
remainder at `settle`, and refunds the collateral on a lost dispute. See SPEC.md §6.

### Access control

- `updateScore` — only the `scoreOracle` address. The score is written exclusively by the
  off-chain model.
- `recordOutcome` — only the `escrow` address. Updates counters and value handled, never
  the score.
- Both addresses are set by the `owner`.

---

## Score service

Python, FastAPI, scikit-learn. No database. Every response comes from the fitted model,
which is trained entirely on synthetic data (`generate_data.py`): no real agent-economy data
exists yet.

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

Set `AEGIS_STATE_CHAIN=base-sepolia` to serve `/agents/state` from that chain instead: one
`getProfile` per agent in `deployments/base-sepolia.json`, scored by the service itself and
cached for 5s. No event replay, so it shows no score deltas or activity (`source: "chain"`).
Unset (the default), the local oracle path is used unchanged.

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
# the rest run from the repo root
python -m venv oracle\.venv && oracle\.venv\Scripts\pip install -r oracle\requirements.txt
python -m venv agents\.venv && agents\.venv\Scripts\pip install -r agents\requirements.txt
copy oracle\.env.example oracle\.env
oracle\.venv\Scripts\python oracle\watcher.py   # terminal 3
```

The local deploy wires in the real `AegisEscrow` with `MockUSDC` (6 decimals, $1M minted to
accounts 1-3), so jobs move real test tokens. `StubEscrow` stays as a fallback (no tokens,
disputes always against the worker). Switch with:

```bash
agents\.venv\Scripts\python agents\select_escrow.py          # which one is active, and is the Registry wired to it
agents\.venv\Scripts\python agents\select_escrow.py --stub   # fall back to StubEscrow
agents\.venv\Scripts\python agents\select_escrow.py --real   # back to AegisEscrow
```

Restart the oracle and both agents after switching.

### Seeding the demo agents

```bash
agents\.venv\Scripts\python agents\seed_demo.py
```

Gives HonestAgent (account 1) and SloppyAgent (account 2) a prior track record so the demo
does not start from a cold file: ~864 / excellent and ~613 / good. The driver's hirer
(account 3) is seeded too (~877), so it hires on 20% collateral instead of 100%. Idempotent; after a live
run, restart anvil and redeploy to seed again.

### Running the agents

```bash
agents\.venv\Scripts\python agents\honest_agent.py          # terminal 4
agents\.venv\Scripts\python agents\sloppy_agent.py          # terminal 5
agents\.venv\Scripts\python agents\demo_driver.py --worker SloppyAgent   # one job, end to end
```

`demo_driver.py` is a stand-in hirer: it posts a job, disputes any delivery that comes back
in under 2s (SloppyAgent) and accepts the rest (HonestAgent), settles, and prints the rescore.
With the real escrow it approves the full job value (collateral is taken at `createJob`, the
rest at `settle`), prints the hirer's mUSDC balance at each step, and exits non-zero if the
hirer is ever recorded as a default -- the escrow's silent failure when under-approved.
Agents talk to the escrow only through the `IAegisEscrow` ABI; see `agents/escrow.py` for
where the real escrow plugs in.

---

## Website

```bash
cd web
npm install
npm run build && npm run preview   # http://localhost:5173  (/, /dashboard, /how-it-works)
```

`/dashboard` polls `GET /agents/state` on the score service every 1.5s and renders it as-is.
`/dashboard?stub=1` renders `docs/api_stub.json` instead, for offline previews; `?api=` points
it at another score service. The whole demo, website included, starts with
`powershell -ExecutionPolicy Bypass -File scripts\demo.ps1`.

---

## The one invariant that matters

The collateral step table is duplicated in two places:

- `contracts/src/AegisRegistry.sol` — `requiredCollateralBps`
- `score/app.py` — `required_collateral_bps`

If those two ever disagree, the demo is broken: the score service quotes a collateral
requirement the chain refuses to honour. Both copies carry a comment pointing at
[SPEC.md §3](SPEC.md#3-collateral-curve). Change both together, or neither. The Python
test suite checks the Python table against a hand-written copy of the contract's table. It
does not read the Solidity, so a change made only in the contract would not be caught.

---

## Not built yet

- x402 integration
