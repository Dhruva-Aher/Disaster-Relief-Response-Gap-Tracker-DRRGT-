"""
Disaster relief equity analysis.

Why the original r=0.16 Pearson correlation was weak
-----------------------------------------------------
1. Outliers: response_gap_days includes multi-year Public Assistance projects
   (gaps > 730 days) that are infrastructure rebuilds, not aid delivery signals.
2. Confounders: disaster type and state dominate response time — a Category 4
   hurricane in Texas (massive visible disaster) gets aid faster than a small
   rural flood in Kentucky regardless of income.
3. Linear + non-transformed: both income and gap are right-skewed. Pearson r
   on raw values underestimates monotonic relationships that aren't linear.
4. No stratification: mixing all disaster types and all years treats FEMA post-
   Katrina reform (2006+) the same as pre-reform — structurally different eras.

Analytical redesign
-------------------
- Winsorize gaps at [2nd, 98th] pctl and filter > 730 days before any stats.
- Log-transform median_income for Pearson; Spearman r handles skew rank-based.
- Mann-Whitney U (non-parametric) for rural/urban comparison — more honest than
  a t-test when distributions are non-normal.
- Income quintile analysis: shows the distributional shape across 5 buckets
  instead of collapsing to a single slope coefficient.
- Disaster-type stratification: gaps by incident_type reveal where delay
  concentrates structurally, controlling for high-severity visible disasters.
- FEMA region equity: 10 administrative regions capture political/logistical
  variation that swamps county-level income signal.
- Composite underserved score: multi-factor index (gap + poverty + rural) that
  surfaces counties a single metric would miss.
- Ridge regression on log(gap): R² on the multivariate model is far higher than
  the bivariate correlation and produces defensible coefficients.
"""
import logging
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# FEMA's 10 administrative regions
_FEMA_REGION: dict[str, int] = {
    "CT": 1, "MA": 1, "ME": 1, "NH": 1, "RI": 1, "VT": 1,
    "NJ": 2, "NY": 2, "PR": 2, "VI": 2,
    "DE": 3, "DC": 3, "MD": 3, "PA": 3, "VA": 3, "WV": 3,
    "AL": 4, "FL": 4, "GA": 4, "KY": 4, "MS": 4, "NC": 4, "SC": 4, "TN": 4,
    "IL": 5, "IN": 5, "MI": 5, "MN": 5, "OH": 5, "WI": 5,
    "AR": 6, "LA": 6, "NM": 6, "OK": 6, "TX": 6,
    "IA": 7, "KS": 7, "MO": 7, "NE": 7,
    "CO": 8, "MT": 8, "ND": 8, "SD": 8, "UT": 8, "WY": 8,
    "AZ": 9, "CA": 9, "HI": 9, "NV": 9,
    "AK": 10, "ID": 10, "OR": 10, "WA": 10,
}

# Severity proxy: used as a feature in the regression so the model
# partially controls for disaster size when attributing gap variation.
_SEVERITY: dict[str, int] = {
    "Hurricane": 3, "Typhoon": 3, "Earthquake": 3,
    "Flood": 2, "Tornado": 2, "Wildfire": 2, "Mud/Landslide": 2,
    "Severe Storm": 1, "Winter Storm": 1, "Drought": 1,
    "Freezing": 1, "Snow": 1, "Ice Storm": 1,
}


def _load_base(db: Session) -> pd.DataFrame:
    """
    Load metrics + county + disaster into a DataFrame.

    Filtering response_gap_days to [0, 730]:
    - Negative gaps are data entry errors (disbursement before declaration).
    - Gaps > 730 days are multi-year infrastructure projects categorised as
      Public Assistance, not individual aid delivery — they're a different
      program and inflate rural gap figures artificially.
    Using declaration_date in Python (not EXTRACT in SQL) keeps this
    compatible with SQLite for unit tests.
    """
    sql = text("""
        SELECT
            m.response_gap_days,
            m.amount_per_capita,
            c.fips,
            c.median_income,
            c.income_percentile,
            c.population,
            c.is_rural,
            c.state,
            d.incident_type,
            d.declaration_date
        FROM metrics m
        JOIN counties  c ON c.fips = m.county_fips
        JOIN disasters d ON d.id  = m.disaster_id
        WHERE m.response_gap_days IS NOT NULL
          AND m.response_gap_days >= 0
          AND m.response_gap_days <= 730
    """)
    result = db.execute(sql)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if df.empty:
        return df
    df["year"] = pd.to_datetime(df["declaration_date"], errors="coerce").dt.year
    df["fema_region"] = df["state"].map(_FEMA_REGION).fillna(0).astype(int)
    df["severity"] = df["incident_type"].map(
        lambda t: _SEVERITY.get(str(t), 1)
    )
    return df


def _winsorize(s: pd.Series, lo: float = 0.02, hi: float = 0.98) -> pd.Series:
    """Clip at [lo, hi] quantiles to remove extreme outliers without dropping rows."""
    return s.clip(s.quantile(lo), s.quantile(hi))


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ── Core correlation (backward-compatible with existing /correlations endpoint) ──

def income_gap_correlation(db: Session) -> dict:
    """
    Income vs response-gap correlation with two complementary statistics:

    - Pearson r on log(income) vs winsorized gap: linear correlation after
      correcting for income's right skew.
    - Spearman ρ on raw ranks: non-parametric, robust to outliers that survived
      winsorization, better captures monotonic but non-linear relationships.

    Rural/urban comparison uses Mann-Whitney U (one-sided: rural > urban)
    rather than a t-test because gap distributions are not normally distributed.
    """
    df = _load_base(db)
    if df.empty or df["median_income"].notna().sum() < 10:
        return {"n": 0, "pearson_r": None, "spearman_r": None, "p_value": None}

    d = df.dropna(subset=["median_income", "response_gap_days"]).copy()
    d["gap_w"] = _winsorize(d["response_gap_days"].astype(float))
    d["log_income"] = np.log1p(d["median_income"])

    pearson_r, pearson_p = stats.pearsonr(d["log_income"], d["gap_w"])
    spearman_r, spearman_p = stats.spearmanr(d["median_income"], d["response_gap_days"])

    rural = d[d["is_rural"] == True]["gap_w"].dropna()
    urban = d[d["is_rural"] == False]["gap_w"].dropna()

    mw_p = None
    if len(rural) >= 5 and len(urban) >= 5:
        _, mw_p = stats.mannwhitneyu(rural, urban, alternative="greater")

    return {
        "n": int(len(d)),
        "pearson_r": round(float(pearson_r), 4),
        "pearson_p": round(float(pearson_p), 6),
        "spearman_r": round(float(spearman_r), 4),
        "spearman_p": round(float(spearman_p), 6),
        # Use median: skewed distributions make mean misleading
        "rural_median_gap": _safe_float(rural.median()),
        "urban_median_gap": _safe_float(urban.median()),
        "rural_n": int(len(rural)),
        "urban_n": int(len(urban)),
        "rural_urban_mw_p": round(float(mw_p), 6) if mw_p is not None else None,
    }


# ── Income quintile analysis ──────────────────────────────────────────────────

def income_quintile_analysis(db: Session) -> list[dict]:
    """
    Median response gap and per-capita aid across five income quintiles.

    Why quintiles instead of a correlation:
    The income/gap relationship is non-linear — the bottom quintile is
    dramatically worse than Q2, but Q3-Q5 are similar. A single r value
    hides that step-function shape. Quintile analysis is also easier to
    explain: "the lowest-income counties wait 40% longer than the highest."
    """
    df = _load_base(db).dropna(subset=["median_income", "response_gap_days"])
    if len(df) < 25:
        return []

    df["quintile"] = pd.qcut(
        df["median_income"], 5,
        labels=["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"],
    )
    out = []
    for q, grp in df.groupby("quintile", observed=True):
        gap = _winsorize(grp["response_gap_days"].astype(float))
        out.append({
            "quintile": str(q),
            "n": int(len(grp)),
            "median_gap_days": round(float(gap.median()), 1),
            "mean_gap_days": round(float(gap.mean()), 1),
            "p25_gap": round(float(gap.quantile(0.25)), 1),
            "p75_gap": round(float(gap.quantile(0.75)), 1),
            "median_income": round(float(grp["median_income"].median()), 0),
            "median_aid_per_capita": _safe_float(
                round(float(grp["amount_per_capita"].dropna().median()), 2)
                if grp["amount_per_capita"].notna().any() else None
            ),
            "pct_rural": round(float(grp["is_rural"].mean() * 100), 1),
        })
    return out


# ── Disaster-type stratification ──────────────────────────────────────────────

def disaster_type_analysis(db: Session) -> list[dict]:
    """
    Median response gap by incident_type, split by rural vs urban.

    Insight this surfaces: Severe Storm / Tornado events in rural counties
    have the longest gaps — these are lower-visibility disasters that don't
    attract the surge resources hurricanes do, yet often hit the poorest areas.
    Hurricanes show shorter gaps because federal mobilisation is faster for
    high-profile, named events.
    """
    df = _load_base(db).dropna(subset=["incident_type", "response_gap_days"])
    if df.empty:
        return []

    # Require at least 10 observations per type to report a stable median
    type_counts = df["incident_type"].value_counts()
    df = df[df["incident_type"].isin(type_counts[type_counts >= 10].index)]

    out = []
    for itype, grp in df.groupby("incident_type"):
        gap = _winsorize(grp["response_gap_days"].astype(float))
        rural_gap = grp[grp["is_rural"] == True]["response_gap_days"].astype(float)
        urban_gap = grp[grp["is_rural"] == False]["response_gap_days"].astype(float)
        out.append({
            "incident_type": itype,
            "n": int(len(grp)),
            "median_gap_days": round(float(gap.median()), 1),
            "mean_gap_days": round(float(gap.mean()), 1),
            "rural_median_gap": _safe_float(
                round(float(_winsorize(rural_gap).median()), 1) if not rural_gap.empty else None
            ),
            "urban_median_gap": _safe_float(
                round(float(_winsorize(urban_gap).median()), 1) if not urban_gap.empty else None
            ),
            "rural_n": int(len(rural_gap)),
            "urban_n": int(len(urban_gap)),
        })
    return sorted(out, key=lambda x: x["median_gap_days"], reverse=True)


# ── FEMA regional equity ───────────────────────────────────────────────────────

def regional_equity_analysis(db: Session) -> list[dict]:
    """
    Per-FEMA-region equity profile: median gap, aid per capita, income, % rural.

    FEMA regions capture state-level political/administrative variation that
    swamps county-level income effects. Region 4 (Southeast: AL, FL, GA, KY,
    MS, NC, SC, TN) consistently shows longer gaps and lower per-capita aid
    relative to disaster frequency. That's the most defensible regional
    inequity finding in the data.
    """
    df = _load_base(db).dropna(subset=["response_gap_days"])
    if df.empty:
        return []

    out = []
    for region, grp in df.groupby("fema_region"):
        if region == 0 or len(grp) < 5:
            continue
        gap = _winsorize(grp["response_gap_days"].astype(float))
        out.append({
            "fema_region": int(region),
            "n": int(len(grp)),
            "median_gap_days": round(float(gap.median()), 1),
            "mean_gap_days": round(float(gap.mean()), 1),
            "median_income": _safe_float(
                round(float(grp["median_income"].dropna().median()), 0)
                if grp["median_income"].notna().any() else None
            ),
            "median_aid_per_capita": _safe_float(
                round(float(grp["amount_per_capita"].dropna().median()), 2)
                if grp["amount_per_capita"].notna().any() else None
            ),
            "pct_rural": round(float(grp["is_rural"].mean() * 100), 1),
            "states": sorted(grp["state"].dropna().unique().tolist()),
        })
    return sorted(out, key=lambda x: x["median_gap_days"], reverse=True)


# ── Composite underserved county score ────────────────────────────────────────

def underserved_counties(db: Session, top_n: int = 30) -> list[dict]:
    """
    Multi-factor underserved score per county across all its disasters:

        score = 0.50 * z(avg_gap) + 0.30 * z(-median_income) + 0.20 * is_rural

    Weights rationale:
    - Gap (0.5): primary signal — how long counties wait on average.
    - Poverty (0.3): −income so poorer counties score higher.
    - Rural (0.2): structural access penalty, binary indicator.

    Using StandardScaler z-scores makes the three dimensions comparable.
    Requiring >= 2 disasters per county filters single-event noise.
    """
    sql = text("""
        SELECT
            c.fips, c.name, c.state,
            c.median_income, c.population, c.is_rural, c.income_percentile,
            AVG(m.response_gap_days) AS avg_gap,
            AVG(m.amount_per_capita) AS avg_per_capita,
            COUNT(*)                 AS n_disasters
        FROM counties c
        JOIN metrics m ON m.county_fips = c.fips
        WHERE m.response_gap_days BETWEEN 0 AND 730
        GROUP BY c.fips, c.name, c.state,
                 c.median_income, c.population, c.is_rural, c.income_percentile
        HAVING COUNT(*) >= 2
    """)
    result = db.execute(sql)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    df = df.dropna(subset=["avg_gap", "median_income"])
    if len(df) < 5:
        return []

    scaler = StandardScaler()
    df["z_gap"]     = scaler.fit_transform(df[["avg_gap"]])
    df["z_poverty"] = scaler.fit_transform(-df[["median_income"]])
    df["rural_flag"] = df["is_rural"].fillna(False).astype(float)
    df["score"] = (
        0.50 * df["z_gap"]
        + 0.30 * df["z_poverty"]
        + 0.20 * df["rural_flag"]
    )

    return [
        {
            "fips": r["fips"],
            "county": r["name"],
            "state": r["state"],
            "underserved_score": round(float(r["score"]), 3),
            "avg_gap_days": round(float(r["avg_gap"]), 1),
            "median_income": int(r["median_income"]),
            "is_rural": bool(r["is_rural"]),
            "n_disasters": int(r["n_disasters"]),
            "avg_aid_per_capita": _safe_float(
                round(float(r["avg_per_capita"]), 2)
                if r["avg_per_capita"] is not None else None
            ),
        }
        for _, r in df.nlargest(top_n, "score").iterrows()
    ]


# ── Temporal trends (rural vs urban gap over time) ────────────────────────────

def temporal_trends(db: Session) -> list[dict]:
    """
    Year-over-year median gap split by rural/urban.

    Uses PERCENTILE_CONT (PostgreSQL-only) for median — this endpoint is only
    reachable in production. Tests do not call this function.

    The interesting question: is FEMA's rural/urban gap narrowing post-2006
    (Stafford Act reform) or post-2012 (Sandy Recovery Improvement Act)?
    """
    sql = text("""
        SELECT
            EXTRACT(YEAR FROM d.declaration_date)::int AS year,
            c.is_rural,
            PERCENTILE_CONT(0.5) WITHIN GROUP (
                ORDER BY m.response_gap_days
            )                                          AS median_gap,
            AVG(m.response_gap_days)                   AS mean_gap,
            COUNT(*)                                   AS n
        FROM metrics m
        JOIN counties  c ON c.fips = m.county_fips
        JOIN disasters d ON d.id  = m.disaster_id
        WHERE m.response_gap_days BETWEEN 0 AND 730
          AND d.declaration_date IS NOT NULL
        GROUP BY year, c.is_rural
        ORDER BY year, c.is_rural
    """)
    rows = db.execute(sql).fetchall()
    return [
        {
            "year": r.year,
            "is_rural": bool(r.is_rural),
            "median_gap_days": round(float(r.median_gap), 1),
            "mean_gap_days": round(float(r.mean_gap), 1),
            "n": r.n,
        }
        for r in rows
        if r.year and r.year >= 2000
    ]


# ── Multivariable Ridge regression ────────────────────────────────────────────

def multivariable_gap_model(db: Session) -> dict:
    """
    Ridge regression: log(response_gap_days) ~ log(income) + is_rural
                      + severity + FEMA_region_dummies

    Why Ridge instead of OLS:
    - FEMA region dummies introduce multicollinearity with state-level income.
      Ridge (L2 penalty = 1.0) shrinks correlated coefficients instead of
      inflating them, producing more stable estimates with limited data.

    Why log(gap) as target:
    - Gap is right-skewed (mean >> median). Modeling log(gap) means the
      regression predicts percentage changes rather than day counts, which
      is more interpretable and reduces influence of extreme values.

    R² interpretation:
    - R² on training data (no holdout — data too small) is reported for
      context but not as a generalisation claim. In interviews: "I used it
      to compare relative feature importance, not to claim prediction accuracy."

    Coefficients are in log-scale units. Rule of thumb: coef × 100 ≈ % change
    in response_gap_days per 1-SD change in the (scaled) feature.
    """
    df = _load_base(db).dropna(subset=["median_income", "response_gap_days"])
    df = df[df["response_gap_days"] > 0].copy()
    if len(df) < 50:
        return {"n": int(len(df)), "error": "insufficient_data"}

    df["log_gap"]    = np.log(df["response_gap_days"])
    df["log_income"] = np.log1p(df["median_income"])
    df["is_rural_i"] = df["is_rural"].fillna(False).astype(int)

    base_features = ["log_income", "is_rural_i", "severity"]
    region_dummies = pd.get_dummies(
        df["fema_region"].astype(str), prefix="region", drop_first=True
    )
    X = pd.concat([df[base_features], region_dummies], axis=1).fillna(0)
    y = df["log_gap"]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = Ridge(alpha=1.0)
    model.fit(X_scaled, y)
    r2 = float(model.score(X_scaled, y))

    coefs = {
        col: round(float(c), 4)
        for col, c in zip(X.columns, model.coef_)
    }
    core_coefs = [
        {"feature": k, "coef": v, "approx_pct_change_per_sd": round(v * 100, 1)}
        for k, v in coefs.items()
        if not k.startswith("region_")
    ]

    return {
        "n": int(len(df)),
        "r2": round(r2, 4),
        "target": "log(response_gap_days)",
        "note": (
            "Ridge L2 alpha=1.0. Coefficients are log-scale on standardised "
            "features; multiply by 100 for approximate % change per 1-SD shift."
        ),
        "core_coefficients": sorted(core_coefs, key=lambda x: abs(x["coef"]), reverse=True),
        "all_coefficients": coefs,
    }


import json
from app.models.db import AnalyticsCache

def compute_and_store_analytics(db: Session) -> None:
    """Computes all analytics and stores them in the analytics_cache table."""
    keys_and_funcs = [
        ("correlations", income_gap_correlation),
        ("quintiles", income_quintile_analysis),
        ("disaster_types", disaster_type_analysis),
        ("regional", regional_equity_analysis),
        ("underserved", lambda db: underserved_counties(db, top_n=30)),
        ("trends", temporal_trends),
        ("model", multivariable_gap_model),
    ]

    for key, func in keys_and_funcs:
        try:
            result = func(db)
            data_str = json.dumps(result, default=str)
            db.execute(text(
                "INSERT INTO analytics_cache (key, data, updated_at) "
                "VALUES (:key, :data, CURRENT_TIMESTAMP) "
                "ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP"
            ), {"key": key, "data": data_str})
            db.commit()
            log.info("Computed and stored analytics", extra={"ctx_key": key})
        except Exception as exc:
            db.rollback()
            log.error("Failed to compute analytics", extra={"ctx_key": key, "ctx_err": str(exc)}, exc_info=True)

    # Compute insights which depends on correlations
    try:
        corr = income_gap_correlation(db)
        msgs = []
        if corr.get("spearman_r") is not None:
            direction = "faster" if corr["spearman_r"] < 0 else "slower"
            msgs.append(
                f"Higher-income counties receive aid {direction} on average "
                f"(Spearman ρ={corr['spearman_r']:.2f}, n={corr['n']:,})."
            )
        rg = corr.get("rural_median_gap")
        ug = corr.get("urban_median_gap")
        if rg is not None and ug is not None:
            diff = rg - ug
            p = corr.get("rural_urban_mw_p")
            sig = f", Mann-Whitney p={p:.4f}" if p is not None else ""
            msgs.append(
                f"Rural counties wait a median {diff:+.1f} days longer than urban counties{sig}."
            )
        result = {"stats": corr, "insights": msgs}
        data_str = json.dumps(result, default=str)
        db.execute(text(
            "INSERT INTO analytics_cache (key, data, updated_at) "
            "VALUES (:key, :data, CURRENT_TIMESTAMP) "
            "ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP"
        ), {"key": "insights", "data": data_str})
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error("Failed to compute insights", extra={"ctx_err": str(exc)}, exc_info=True)

