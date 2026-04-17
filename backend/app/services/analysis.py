"""Statistical analysis of FEMA disaster response gaps."""
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session
from sqlalchemy import text


def _load_base(db: Session) -> pd.DataFrame:
    sql = text("""
        SELECT m.response_gap_days, m.amount_per_capita,
               c.median_income, c.income_percentile, c.population, c.is_rural, c.state
        FROM metrics m JOIN counties c ON c.fips = m.county_fips
        WHERE m.response_gap_days IS NOT NULL
    """)
    result = db.execute(sql)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    df["year"] = pd.to_datetime(df.get("declaration_date", pd.NaT), errors="coerce").dt.year
    return df


def _winsorize(series: pd.Series, low: float = 0.02, high: float = 0.98) -> pd.Series:
    lo, hi = series.quantile(low), series.quantile(high)
    return series.clip(lo, hi)


def income_gap_correlation(db: Session) -> dict:
    df = _load_base(db)
    d = df.dropna(subset=["median_income", "response_gap_days"]).copy()

    # Drop multi-year infrastructure outliers; cap at 730 days
    d = d[d["response_gap_days"].between(0, 730)]

    if len(d) < 10:
        return {"n": 0, "pearson_r": None, "spearman_r": None, "p_value": None}

    # Winsorize both axes before computing correlations
    gap_w    = _winsorize(d["response_gap_days"])
    income_w = _winsorize(d["median_income"])

    # Log-transform income to reduce right-skew before Pearson
    log_income = np.log1p(income_w)
    r_p, p_p = stats.pearsonr(log_income, gap_w)
    r_s, p_s = stats.spearmanr(d["median_income"], d["response_gap_days"])

    # Mann-Whitney U: do rural and urban counties have different gap distributions?
    rural  = d[d["is_rural"] == True]["response_gap_days"]
    urban  = d[d["is_rural"] == False]["response_gap_days"]
    if len(rural) >= 5 and len(urban) >= 5:
        mw_stat, mw_p = stats.mannwhitneyu(rural, urban, alternative="two-sided")
    else:
        mw_stat, mw_p = None, None

    rural_mean = float(rural.mean()) if not rural.empty else None
    urban_mean = float(urban.mean()) if not urban.empty else None

    return {
        "n":           int(len(d)),
        "pearson_r":   round(float(r_p), 4),
        "spearman_r":  round(float(r_s), 4),
        "p_value":     round(float(p_s), 6),
        "rural_mean_gap":  rural_mean,
        "urban_mean_gap":  urban_mean,
        "mann_whitney_u":  float(mw_stat) if mw_stat is not None else None,
        "mann_whitney_p":  round(float(mw_p), 6) if mw_p is not None else None,
    }
