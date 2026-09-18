"""AEGIS score service.

Turns an agent's job history into a credit score, a risk band, and the collateral the
chain will demand from it. Every number in every response comes from the fitted logistic
regression in models/ -- nothing here is mocked.

Usage:
    python generate_data.py
    python train.py
    uvicorn app:app --reload
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

MODELS_DIR = Path(__file__).parent / "models"

MIN_SCORE, MAX_SCORE = 0, 1000

# ESTIMATE, not an observation. OutcomeRecorded carries no counterparty, so when events arrive
# without counterparty labels, diversity is estimated as this fraction of completed jobs. 0.6
# sits near the training data's own ratio (generate_data.py draws it from Beta(4, 3), mean
# 0.57). Pinning it at 1 instead froze the model's strongest experience signal and made a clean
# job worth ~+1 point, or less than zero on a larger job. Replace with real counts once
# OutcomeRecorded carries a counterparty (SPEC.md section 10).
DIVERSITY_PER_JOB_ESTIMATE = 0.6


# ---------------------------------------------------------------------------
# Collateral curve
# ---------------------------------------------------------------------------


def required_collateral_bps(score: int) -> int:
    """Collateral the agent must post upfront, in basis points of job value.

    Step function from SPEC.md section 3. 10000 bps = 100% prepaid.

        score >= 800  ->  2000
        score >= 600  ->  4000
        score >= 400  ->  7000
        otherwise     -> 10000

    WARNING: this table is duplicated on-chain in `contracts/src/AegisRegistry.sol`
    (`requiredCollateralBps`). If the two ever disagree, this service quotes a collateral
    requirement the chain will refuse to honour and the product is broken. Change both
    together, or neither. See SPEC.md section 3.
    """
    if score >= 800:
        return 2000
    if score >= 600:
        return 4000
    if score >= 400:
        return 7000
    return 10000


def score_band(score: int) -> str:
    """Human-readable band. Same breakpoints as the collateral curve, SPEC.md section 4."""
    if score >= 800:
        return "excellent"
    if score >= 600:
        return "good"
    if score >= 400:
        return "fair"
    return "poor"


# ---------------------------------------------------------------------------
# Model artifacts
# ---------------------------------------------------------------------------


class ScoringModel:
    """The fitted model plus everything needed to explain a prediction."""

    def __init__(self, model, scaler, feature_names: list[str], metrics: dict, calibration: dict):
        self.model = model
        self.scaler = scaler
        self.feature_names = feature_names
        self.metrics = metrics
        self.calibration = calibration
        self.coefficients = model.coef_[0]

    @classmethod
    def load(cls) -> "ScoringModel":
        model = joblib.load(MODELS_DIR / "model.joblib")
        scaler = joblib.load(MODELS_DIR / "scaler.joblib")
        feature_names = json.loads((MODELS_DIR / "feature_names.json").read_text())
        metrics = json.loads((MODELS_DIR / "metrics.json").read_text())
        calibration = json.loads((MODELS_DIR / "calibration.json").read_text())
        return cls(model, scaler, feature_names, metrics, calibration)


def _load_model() -> ScoringModel | None:
    try:
        return ScoringModel.load()
    except FileNotFoundError:
        return None


SCORING_MODEL = _load_model()


def _require_model() -> ScoringModel:
    if SCORING_MODEL is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Model artifacts not found in models/. "
                "Run `python generate_data.py` then `python train.py`."
            ),
        )
    return SCORING_MODEL


# ---------------------------------------------------------------------------
# Explanations
# ---------------------------------------------------------------------------

EXPLANATIONS: dict[str, dict[str, str]] = {
    "jobs_completed": {
        "much_high": "Very long track record of completed jobs",
        "high": "More completed jobs than most peers",
        "mid": "Typical number of completed jobs",
        "low": "Fewer completed jobs than most peers",
        "much_low": "Thin track record, very few completed jobs",
    },
    "dispute_rate": {
        "much_high": "Dispute rate far above peers",
        "high": "High dispute rate relative to peers",
        "mid": "Dispute rate close to the peer average",
        "low": "Dispute rate below peers",
        "much_low": "Almost no disputes across its history",
    },
    "avg_job_value_usd": {
        "much_high": "Handles jobs far larger than peers",
        "high": "Handles larger jobs than most peers",
        "mid": "Typical job size",
        "low": "Handles smaller jobs than most peers",
        "much_low": "Handles very small jobs",
    },
    "account_age_days": {
        "much_high": "Long-established account",
        "high": "Account older than most peers",
        "mid": "Typical account age",
        "low": "Account younger than most peers",
        "much_low": "Very new account with little history",
    },
    "on_time_payment_rate": {
        "much_high": "Pays on time almost without exception",
        "high": "Pays on time more reliably than peers",
        "mid": "Payment timeliness close to the peer average",
        "low": "Misses payment deadlines more often than peers",
        "much_low": "Frequently misses payment deadlines",
    },
    "prior_defaults": {
        "much_high": "Many prior defaults on record",
        "high": "More prior defaults than peers",
        "mid": "Prior defaults close to the peer average",
        "low": "Fewer prior defaults than peers",
        "much_low": "Clean of prior defaults",
    },
    "counterparty_diversity": {
        "much_high": "Trusted by a wide range of counterparties",
        "high": "Works with more counterparties than peers",
        "mid": "Typical counterparty spread",
        "low": "Concentrated in a few counterparties",
        "much_low": "Almost all work with a single counterparty",
    },
}


def _tier(z: float) -> str:
    """Where this agent sits versus the training population, in standard deviations."""
    if z >= 1.0:
        return "much_high"
    if z >= 0.35:
        return "high"
    if z <= -1.0:
        return "much_low"
    if z <= -0.35:
        return "low"
    return "mid"


def _explain(feature: str, value: float, z: float) -> str:
    # Zero reads better than "below peers" for the two count-like risk features.
    if feature == "dispute_rate" and value == 0:
        return "No disputes on record"
    if feature == "prior_defaults" and value == 0:
        return "No prior defaults on record"
    return EXPLANATIONS[feature][_tier(z)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AgentFeatures(BaseModel):
    """The seven features the model consumes. Frozen in SPEC.md section 7."""

    jobs_completed: int = Field(..., ge=0, description="Jobs this agent has delivered.")
    dispute_rate: float = Field(..., ge=0.0, le=1.0, description="Fraction of jobs disputed.")
    avg_job_value_usd: float = Field(..., gt=0, description="Mean job value in USD.")
    account_age_days: int = Field(..., ge=0, description="Days since first activity.")
    on_time_payment_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Fraction of obligations met on time."
    )
    prior_defaults: int = Field(..., ge=0, description="Jobs this agent failed to deliver.")
    counterparty_diversity: int = Field(
        ..., ge=0, description="Distinct agents transacted with."
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "jobs_completed": 34,
                "dispute_rate": 0.06,
                "avg_job_value_usd": 120.0,
                "account_age_days": 260,
                "on_time_payment_rate": 0.94,
                "prior_defaults": 0,
                "counterparty_diversity": 19,
            }
        }
    }


class Factor(BaseModel):
    feature: str
    value: float
    impact: int = Field(..., description="Signed points this feature moved the score.")
    explanation: str


class ScoreResponse(BaseModel):
    score: int = Field(..., ge=MIN_SCORE, le=MAX_SCORE)
    band: str
    required_collateral_bps: int
    default_probability: float
    top_factors: list[Factor]


class JobEvent(BaseModel):
    """One settled job, as the chain would report it."""

    delivered: bool
    disputed: bool = False
    value_usd: float = Field(..., gt=0)
    timestamp: datetime
    counterparty: str | None = Field(
        default=None,
        description="Optional. Supplied, it makes counterparty_diversity real rather than assumed.",
    )


class EventsRequest(BaseModel):
    events: list[JobEvent] = Field(..., min_length=1)
    as_of: datetime | None = Field(
        default=None, description="Defaults to now. Used to compute account age."
    )


class EventsScoreResponse(ScoreResponse):
    derived_features: AgentFeatures


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    test_roc_auc: float | None = None
    features: list[str] | None = None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def _logit_to_points(logit: float, calibration: dict) -> float:
    """Map log-odds of default to the score scale, before clamping. SPEC.md section 7.

    Linear in log-odds so a feature's effect in points stays constant instead of saturating
    at the extremes. The raw probability is deliberately not used: at a ~15% base default
    rate it pushes most agents into the top band and the collateral tiers stop discriminating.
    """
    return calibration["anchor_score"] - calibration["factor"] * (
        logit - calibration["median_logit"]
    )


def _clamp_score(points: float) -> int:
    return max(MIN_SCORE, min(MAX_SCORE, int(round(points))))


def score_agent(features: AgentFeatures, scoring_model: ScoringModel) -> ScoreResponse:
    names = scoring_model.feature_names
    values = [float(getattr(features, name)) for name in names]
    # A DataFrame rather than a bare array so the scaler sees the feature names it was fit on.
    raw = pd.DataFrame([values], columns=names)

    standardized = scoring_model.scaler.transform(raw)[0]

    # For binary logistic regression this is exactly intercept + coefficients . standardized,
    # so the per-feature contributions below sum back to it.
    logit = float(scoring_model.model.decision_function(standardized.reshape(1, -1))[0])

    probability = float(_sigmoid(logit))
    points = _logit_to_points(logit, scoring_model.calibration)
    score = _clamp_score(points)

    contributions = scoring_model.coefficients * standardized

    # Rank by contribution size in logit space, then report each effect in score points as a
    # counterfactual: what this agent would have scored with that one feature at the peer
    # average. Because the mapping is linear in log-odds, this is stable at both extremes.
    ranked = np.argsort(-np.abs(contributions))[:3]

    top_factors: list[Factor] = []
    for index in ranked:
        counterfactual = _logit_to_points(logit - contributions[index], scoring_model.calibration)
        top_factors.append(
            Factor(
                feature=names[index],
                value=values[index],
                impact=int(round(points - counterfactual)),
                explanation=_explain(names[index], values[index], float(standardized[index])),
            )
        )

    return ScoreResponse(
        score=score,
        band=score_band(score),
        required_collateral_bps=required_collateral_bps(score),
        default_probability=round(probability, 4),
        top_factors=top_factors,
    )


def estimate_counterparty_diversity(jobs_completed: int) -> int:
    """ESTIMATE used only when no event carries a counterparty. See DIVERSITY_PER_JOB_ESTIMATE."""
    return max(1, round(jobs_completed * DIVERSITY_PER_JOB_ESTIMATE))


def derive_features(request: EventsRequest) -> AgentFeatures:
    """Collapse a job history into the seven model features.

    An agent with no events is unknown by definition, and the chain already charges such an
    address 100% collateral, so at least one event is required rather than invented.
    """
    events = request.events
    total = len(events)

    as_of = request.as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)

    timestamps = [
        event.timestamp if event.timestamp.tzinfo else event.timestamp.replace(tzinfo=timezone.utc)
        for event in events
    ]

    delivered_count = sum(1 for event in events if event.delivered)
    disputed_count = sum(1 for event in events if event.disputed)

    # Proxy: the chain reports delivery and disputes, not payment timing. A job that was
    # delivered and never disputed is the closest on-chain evidence of a clean settlement.
    clean_count = sum(1 for event in events if event.delivered and not event.disputed)

    counterparties = {event.counterparty for event in events if event.counterparty}

    return AgentFeatures(
        jobs_completed=delivered_count,
        dispute_rate=disputed_count / total,
        avg_job_value_usd=sum(event.value_usd for event in events) / total,
        account_age_days=max(0, (as_of - min(timestamps)).days),
        on_time_payment_rate=clean_count / total,
        prior_defaults=total - delivered_count,
        counterparty_diversity=(
            len(counterparties)
            if counterparties
            else estimate_counterparty_diversity(delivered_count)
        ),
    )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AEGIS score service",
    description=(
        "Credit scoring for the AI agent economy. Converts an agent's job history into a "
        "score, a band, and the collateral the chain will require from it."
    ),
    version="0.1.0",
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    if SCORING_MODEL is None:
        return HealthResponse(status="degraded", model_loaded=False)
    return HealthResponse(
        status="ok",
        model_loaded=True,
        test_roc_auc=SCORING_MODEL.metrics.get("test_roc_auc"),
        features=SCORING_MODEL.feature_names,
    )


@app.post("/score", response_model=ScoreResponse)
def score(features: AgentFeatures) -> ScoreResponse:
    """Score an agent from its seven features."""
    return score_agent(features, _require_model())


@app.post("/score/from-events", response_model=EventsScoreResponse)
def score_from_events(request: EventsRequest) -> EventsScoreResponse:
    """Derive the features from raw job events, then score.

    Lets live chain events be fed straight in without the caller computing features itself.
    """
    scoring_model = _require_model()
    features = derive_features(request)
    result = score_agent(features, scoring_model)
    return EventsScoreResponse(**result.model_dump(), derived_features=features)
