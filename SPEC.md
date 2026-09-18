# AEGIS — SPEC

**This file is the single source of truth for all shared types.**

Every other file in this repository — Solidity contracts, Python services, tests, scripts —
must match the definitions below exactly. Do not add fields. Do not rename fields. If a type
needs to change, change it here first, then propagate.

AEGIS is a credit and dispute layer for the AI agent economy:

1. Agents carry a portable credit score built from their on-chain job history.
2. A high-score agent hiring another agent posts only **partial** collateral instead of
   prepaying 100%. Low or unknown score means 100% upfront.
3. If the worker under-delivers, a dispute resolves automatically, money moves, and both
   agents' scores update. No human arbitrator.

---

## 1. JobState

```
enum JobState {
    Created,
    Funded,
    Delivered,
    Accepted,
    Disputed,
    Settled
}
```

### Valid transitions

```
Created -> Funded -> Delivered -> Accepted -> Settled
Delivered -> Disputed -> Settled
```

No other transition is legal. Any attempt to move between two states not connected above
must revert.

---

## 2. AgentProfile

```solidity
struct AgentProfile {
    address addr;
    uint16  score;              // 0-1000, new agents start at 500
    uint32  jobsCompleted;
    uint32  jobsDisputed;
    uint32  defaults;
    uint256 totalValueHandled;
    bool    exists;
}
```

| Field               | Type      | Meaning                                                      |
| ------------------- | --------- | ------------------------------------------------------------ |
| `addr`              | `address` | The agent's wallet address.                                   |
| `score`             | `uint16`  | Credit score, clamped to `0-1000`. New agents start at `500`. |
| `jobsCompleted`     | `uint32`  | Jobs where the worker delivered.                              |
| `jobsDisputed`      | `uint32`  | Jobs that entered the `Disputed` state.                       |
| `defaults`          | `uint32`  | Jobs where the worker failed to deliver.                      |
| `totalValueHandled` | `uint256` | Cumulative value of all jobs recorded against this agent.     |
| `exists`            | `bool`    | `true` once registered. Distinguishes a new agent from a zeroed slot. |

**Score authority:** the score is written **only** by the off-chain oracle via
`updateScore`. On-chain outcome recording (`recordOutcome`) updates counters and
`totalValueHandled` but never touches `score`.

---

## 3. Collateral curve

A step function over the agent's score, expressed in basis points, where `10000 = 100%`
of the job value posted upfront.

| Condition        | Required collateral (bps) | Meaning        |
| ---------------- | ------------------------- | -------------- |
| `score >= 800`   | `2000`                    | 20% upfront    |
| `score >= 600`   | `4000`                    | 40% upfront    |
| `score >= 400`   | `7000`                    | 70% upfront    |
| otherwise        | `10000`                   | 100% upfront   |
| unknown agent    | `10000`                   | 100% upfront   |

An **unknown agent** is any address with `exists == false`. It is treated as maximum risk
and must prepay in full.

> **This table is duplicated on-chain and off-chain.** It appears in
> `contracts/src/AegisRegistry.sol` and in `score/app.py`. If those two ever disagree, the
> product is broken: the score service would quote a collateral requirement the chain
> refuses to honour. Both copies carry a comment pointing back to this section. Change
> both together, or neither.

---

## 4. Score bands

Used by the score service for human-readable output. The band boundaries are the same
breakpoints as the collateral curve.

| Band        | Condition       | Required collateral (bps) |
| ----------- | --------------- | ------------------------- |
| `excellent` | `score >= 800`  | `2000`                    |
| `good`      | `score >= 600`  | `4000`                    |
| `fair`      | `score >= 400`  | `7000`                    |
| `poor`      | `score < 400`   | `10000`                   |

---

## 5. Registry interface

```solidity
interface IAegisRegistry {
    event AgentRegistered(address indexed agent);
    event ScoreUpdated(address indexed agent, uint16 oldScore, uint16 newScore, string reason);
    event OutcomeRecorded(address indexed agent, bool delivered, bool disputed, uint256 value);

    function register(address agent) external;
    function getProfile(address agent) external view returns (AgentProfile memory);
    function requiredCollateralBps(address agent) external view returns (uint16);
    function updateScore(address agent, uint16 newScore, string calldata reason) external;
    function recordOutcome(address agent, bool delivered, bool disputed, uint256 value) external;
}
```

**Access control**

| Function         | Caller                                      |
| ---------------- | ------------------------------------------- |
| `register`       | anyone (idempotent)                          |
| `getProfile`     | anyone (view)                                |
| `requiredCollateralBps` | anyone (view)                         |
| `updateScore`    | `scoreOracle` only (address set by `owner`)  |
| `recordOutcome`  | `escrow` only (address set by `owner`)       |

`register` is idempotent: calling it on an already-registered agent is a no-op and must not
reset an existing profile.

### Value units

**Every job value is 6-decimal USDC base units.** `500000000` is a $500 job. This applies to
`recordOutcome`'s `value`, `OutcomeRecorded.value`, `AgentProfile.totalValueHandled`, and
every `value`, `collateralTaken` and `amountToWorker` in the escrow interface (section 6).
Not 18 decimals. The oracle divides by `10**6` before scoring; a value in 18 decimals would
reach the model as a $500,000,000,000,000 job.

---

## 6. Escrow interface

Interface only. **No escrow logic is implemented yet.**

```solidity
interface IAegisEscrow {
    event JobCreated(uint256 indexed jobId, address indexed hirer, address indexed worker,
                     uint256 value, uint256 collateralTaken);
    event JobDelivered(uint256 indexed jobId);
    event JobDisputed(uint256 indexed jobId, address raisedBy);
    event JobSettled(uint256 indexed jobId, bool workerPaid, uint256 amountToWorker);

    function createJob(address worker, uint256 value) external returns (uint256 jobId);
    function markDelivered(uint256 jobId) external;
    function accept(uint256 jobId) external;
    function dispute(uint256 jobId) external;
    function settle(uint256 jobId) external;
}
```

### Stand-in escrow (local development)

Until the real escrow deploys, `contracts/script/deploy_local.py` deploys
`contracts/src/StubEscrow.sol` and points `escrow` at it. It implements this interface and
the section 1 state machine, but moves no tokens and settles every dispute against the
worker. `agents/seed_demo.py` temporarily points `escrow` at Anvil account 9 to record seed
history, then hands it back. The agents use only the `IAegisEscrow` ABI, so swapping in the
real escrow is an address change in `deployments/local.json`.

**When the real escrow deploys, `setEscrow` MUST point at it.** Otherwise `recordOutcome`
reverts with `NotEscrow`: the escrow's `settle` either reverts with it, or, if the escrow
wraps the call, silently records nothing. Either way no `OutcomeRecorded` is emitted, the
oracle never wakes, and it looks like an oracle bug when it is a wiring bug.

---

## 7. Score service contract

The off-chain scoring model consumes seven features per agent.

| Feature                  | Type    | Range / shape                            |
| ------------------------ | ------- | ---------------------------------------- |
| `jobs_completed`         | `int`   | `>= 0`, heavy-tailed                     |
| `dispute_rate`           | `float` | `0.0 - 1.0`, most agents near 0          |
| `avg_job_value_usd`      | `float` | `> 0`, lognormal                         |
| `account_age_days`       | `int`   | `>= 0`                                   |
| `on_time_payment_rate`   | `float` | `0.0 - 1.0`, skewed high                 |
| `prior_defaults`         | `int`   | `>= 0`, mostly 0                         |
| `counterparty_diversity` | `int`   | `>= 0`, distinct agents transacted with  |

The model predicts `default_probability`. **Low risk means a high score.**

**`counterparty_diversity` is stubbed at `1` in the oracle path.** `OutcomeRecorded` carries
no counterparty, and `msg.sender` is always the escrow, so the score service's
`derive_features` assumes a single counterparty. Being constant it shifts every live agent by
the same amount and does not reorder them. It has a second effect worth knowing: in the
training data diversity rises with job count, so the model credits experience mostly through
diversity (coefficient `-0.94`) rather than `jobs_completed` (`-0.17`). With diversity pinned,
one more clean job is worth about +1 point.

The raw probability is deliberately *not* used as the score. At a ~15% base default rate it
pushes 79% of agents above 800, so nearly everyone qualifies for the cheapest collateral
tier and the curve in section 3 stops discriminating. Per-feature point impacts also
saturate to near zero at the extremes, which breaks the explanation the service exists to
give.

Instead the score is **linear in log-odds**, the standard credit-scoring calibration:

```
logit = ln(default_probability / (1 - default_probability))
score = clamp(round(ANCHOR - FACTOR * (logit - MEDIAN_LOGIT)), 0, 1000)
```

| Constant       | Value                   | Meaning                                                      |
| -------------- | ----------------------- | ------------------------------------------------------------ |
| `ANCHOR`       | `500`                   | The median agent scores 500, matching the on-chain starting score. |
| `FACTOR`       | `100 / ln(2)` ≈ `144.3` | 100 points per doubling of the odds of default.               |
| `MEDIAN_LOGIT` | fitted                  | Median logit over the training split. Written to `models/calibration.json` by `train.py`. |

**Chosen values: `ANCHOR = 500`, `FACTOR = 144.3`.** These are final for the build, not
placeholders pending tuning. The measured spread below was accepted as is.

**`ANCHOR = 500` is load-bearing.** It must equal the on-chain starting score of a newly
registered agent in section 2. The two numbers encode the same claim — that an agent with no
history is exactly average until proven otherwise — so a new agent's first score must not
jump the moment the oracle first writes to it. Changing one requires changing the other.

Because the mapping is linear in log-odds, a feature's effect in points is exactly
`-FACTOR * (coefficient * standardized_value)`. Point impacts therefore stay stable across
the whole range instead of collapsing at the extremes, which is what makes
"this agent lost 40 points from one disputed job" a true statement rather than a slogan.

### Measured population spread

Verified by `score/check_distribution.py` over all 5000 synthetic agents:

| Band        | Collateral | Share     |
| ----------- | ---------- | --------- |
| `excellent` | `2000` bps | **4.6%**  |
| `good`      | `4000` bps | **18.5%** |
| `fair`      | `7000` bps | **47.3%** |
| `poor`      | `10000` bps| **29.6%** |

Median score 499. Only 4.1% of agents sit at a rail (0 or 1000). Model test ROC AUC is
0.82, inside the 0.80-0.88 band, so the data is not over-separable. Agents at the rails are
deliberately extreme histories; ordinary agents built around the population medians score
between 370 and 831 and none clamp.

The requirement is that no band swallows the population and all four collateral tiers stay
reachable. That holds.

A flatter 15/35/35/15 spread was considered and **rejected**. `ANCHOR` pins the median agent's
score, so exactly 50% of agents score at or above `ANCHOR` by construction. Putting 50% of
agents at or above 600 therefore forces `ANCHOR = 600` — no value of `FACTOR` can achieve it
alone. That would break the load-bearing tie to the starting score above. The alternative,
raising `FACTOR` to ~295 while holding `ANCHOR = 500`, roughly doubles the points swing per
job and makes per-job score changes read as arbitrary rather than calibrated. Neither cost is
worth paying for a distribution that is never rendered: the demo shows two agents, not the
population.

---

## 8. Target chain

Base Sepolia. Solidity `^0.8.20`. OpenZeppelin for `Ownable` and `IERC20`.

---

## 9. Out of scope tonight

Escrow logic, agent scripts, dashboard, and x402 integration are deliberately not built.
The escrow interface exists so the registry can be wired against it later.

---

## 10. Roadmap

**Cold-start handling for thin-file agents.** Rates computed from a handful of jobs are
extreme: one lost dispute on a two-job history is a 50% dispute rate and takes the score from
509 to 0. The standard credit-scoring fix is to shrink each rate toward the population mean
in proportion to how little history backs it (empirical-Bayes smoothing, e.g.
`(disputes + k * population_rate) / (jobs + k)`), so a thin file reads as "insufficient
history" rather than as a confident extreme. Not built: the demo seeds its agents with prior
history instead (`agents/seed_demo.py`). Doing it properly means re-running
`check_distribution.py` and re-tuning the seed.
