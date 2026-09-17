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

The model predicts `default_probability`. Score is the inverse, mapped to `0-1000`:

```
score = round((1 - default_probability) * 1000)
```

clamped to `[0, 1000]`, so **low risk means a high score**.

---

## 8. Target chain

Base Sepolia. Solidity `^0.8.20`. OpenZeppelin for `Ownable` and `IERC20`.

---

## 9. Out of scope tonight

Escrow logic, agent scripts, dashboard, and x402 integration are deliberately not built.
The escrow interface exists so the registry can be wired against it later.
