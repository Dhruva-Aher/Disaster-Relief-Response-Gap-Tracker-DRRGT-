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


def income_quintile_analysis(db: Session) -> list[dict]:
    df = _load_base(db)
    d = df.dropna(subset=["median_income", "response_gap_days"]).copy()
    d = d[d["response_gap_days"].between(0, 730)]
    if len(d) < 10:
        return []

    try:
        d["quintile"] = pd.qcut(d["median_income"], q=5,
                                labels=["Q1 (lowest)", "Q2", "Q3", "Q4", "Q5 (highest)"])
    except ValueError:
        return []

    out = []
    for label, group in d.groupby("quintile", observed=True):
        gap = group["response_gap_days"]
        income = group["median_income"]
        out.append({
            "quintile":        str(label),
            "n":               int(len(group)),
            "median_gap_days": round(float(gap.median()), 1),
            "mean_gap_days":   round(float(gap.mean()), 1),
            "p25_gap":         round(float(gap.quantile(0.25)), 1),
            "p75_gap":         round(float(gap.quantile(0.75)), 1),
            "median_income":   round(float(income.median()), 0),
            "pct_rural":       round(float(group["is_rural"].mean()) * 100, 1),
        })
    return out


def underserved_counties(db: Session, top_n: int = 25) -> list[dict]:
    """
    Composite underserved score = 0.50*z(gap) + 0.30*z(-income) + 0.20*rural.

    A high score means: long wait for aid AND low income AND likely rural —
    the triple disadvantage that raw gap rankings miss.
    """
    sql = text("""
        SELECT m.county_fips, c.name, c.state,
               AVG(m.response_gap_days)   AS avg_gap,
               c.median_income, c.is_rural, c.population
        FROM metrics m JOIN counties c ON c.fips = m.county_fips
        WHERE m.response_gap_days BETWEEN 0 AND 730
          AND c.median_income IS NOT NULL
        GROUP BY m.county_fips, c.name, c.state, c.median_income, c.is_rural, c.population
    """)
    result = db.execute(sql)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())

    if len(df) < 10:
        return []

    def _zscore(s: pd.Series) -> pd.Series:
        std = s.std()
        return (s - s.mean()) / std if std > 0 else pd.Series(0.0, index=s.index)

    df["score"] = (
        0.50 * _zscore(df["avg_gap"])
        + 0.30 * _zscore(-df["median_income"])
        + 0.20 * df["is_rural"].astype(float)
    )

    top = df.nlargest(top_n, "score")
    return [
        {
            "county_fips":    r.county_fips,
            "county_name":    r.name,
            "state":          r.state,
            "avg_gap_days":   round(float(r.avg_gap), 1),
            "median_income":  int(r.median_income),
            "is_rural":       bool(r.is_rural),
            "population":     int(r.population) if r.population else None,
            "underserved_score": round(float(r.score), 4),
        }
        for r in top.itertuples()
    ]
