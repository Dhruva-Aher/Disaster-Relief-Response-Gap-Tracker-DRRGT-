"""Statistical analysis of FEMA disaster response gaps."""
import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy.orm import Session
from sqlalchemy import text

# FEMA administrative regions (state FIPS prefix → region number)
_FEMA_REGION: dict[str, int] = {
    "09": 1, "23": 1, "25": 1, "33": 1, "44": 1, "50": 1,
    "34": 2, "36": 2, "72": 2, "78": 2,
    "10": 3, "11": 3, "24": 3, "42": 3, "51": 3, "54": 3,
    "01": 4, "12": 4, "13": 4, "21": 4, "28": 4, "37": 4, "45": 4, "47": 4,
    "17": 5, "18": 5, "26": 5, "27": 5, "39": 5, "55": 5,
    "05": 6, "22": 6, "35": 6, "40": 6, "48": 6,
    "19": 7, "20": 7, "29": 7, "31": 7,
    "08": 8, "30": 8, "38": 8, "46": 8, "49": 8, "56": 8,
    "04": 9, "06": 9, "15": 9, "32": 9,
    "02": 10, "16": 10, "41": 10, "53": 10,
}


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


def disaster_type_analysis(db: Session) -> list[dict]:
    sql = text("""
        SELECT dis.incident_type, m.response_gap_days, c.is_rural
        FROM metrics m
        JOIN disasters dis ON dis.id = m.disaster_id
        JOIN counties  c   ON c.fips = m.county_fips
        WHERE m.response_gap_days BETWEEN 0 AND 730
          AND dis.incident_type IS NOT NULL
    """)
    result = db.execute(sql)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if df.empty:
        return []

    out = []
    for dtype, grp in df.groupby("incident_type"):
        gap = grp["response_gap_days"]
        rural_gap  = grp[grp["is_rural"] == True]["response_gap_days"]
        urban_gap  = grp[grp["is_rural"] == False]["response_gap_days"]
        out.append({
            "incident_type":    str(dtype),
            "n":                int(len(grp)),
            "median_gap_days":  round(float(gap.median()), 1),
            "mean_gap_days":    round(float(gap.mean()), 1),
            "rural_median_gap": round(float(rural_gap.median()), 1) if not rural_gap.empty else None,
            "urban_median_gap": round(float(urban_gap.median()), 1) if not urban_gap.empty else None,
        })
    return sorted(out, key=lambda x: x["n"], reverse=True)


def regional_equity_analysis(db: Session) -> list[dict]:
    sql = text("""
        SELECT c.state, AVG(m.response_gap_days) AS avg_gap,
               AVG(c.median_income) AS avg_income,
               AVG(c.is_rural::int) AS pct_rural, COUNT(*) AS n
        FROM metrics m JOIN counties c ON c.fips = m.county_fips
        WHERE m.response_gap_days BETWEEN 0 AND 730
          AND c.state IS NOT NULL
        GROUP BY c.state
    """)
    result = db.execute(sql)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    if df.empty:
        return []

    df["fema_region"] = df["state"].map(_FEMA_REGION)

    out = []
    for region, grp in df.groupby("fema_region"):
        if pd.isna(region):
            continue
        out.append({
            "fema_region":    int(region),
            "states":         sorted(grp["state"].tolist()),
            "n":              int(grp["n"].sum()),
            "avg_gap_days":   round(float((grp["avg_gap"] * grp["n"]).sum() / grp["n"].sum()), 1),
            "avg_income":     round(float((grp["avg_income"] * grp["n"]).sum() / grp["n"].sum()), 0),
            "pct_rural":      round(float((grp["pct_rural"] * grp["n"]).sum() / grp["n"].sum()) * 100, 1),
        })
    return sorted(out, key=lambda x: x["fema_region"])


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
