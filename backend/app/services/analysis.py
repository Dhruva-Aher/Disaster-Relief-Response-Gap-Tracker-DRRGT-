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
               c.median_income, c.income_percentile, c.population, c.is_rural, c.state,
               dis.incident_type
        FROM metrics m
        JOIN counties  c   ON c.fips = m.county_fips
        JOIN disasters dis ON dis.id = m.disaster_id
        WHERE m.response_gap_days IS NOT NULL
    """)
    result = db.execute(sql)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    return df


def _winsorize(series: pd.Series, low: float = 0.02, high: float = 0.98) -> pd.Series:
    lo, hi = series.quantile(low), series.quantile(high)
    return series.clip(lo, hi)


def _f(v, ndigits: int = 4):
    """Round a float for JSON output; return None if nan/inf."""
    if v is None:
        return None
    fv = float(v)
    return round(fv, ndigits) if np.isfinite(fv) else None


def income_gap_correlation(db: Session) -> dict:
    df = _load_base(db)
    d = df.dropna(subset=["median_income", "response_gap_days"]).copy()

    # Drop multi-year infrastructure outliers; cap at 730 days
    d = d[d["response_gap_days"].between(0, 730)]

    if len(d) < 10:
        return {"n": 0, "pearson_r": None, "spearman_r": None, "p_value": None}

    # Compute type-adjusted excess gap.
    # Each disaster type has a different inherent response timeline — flooding
    # historically takes longer than wildfire response. Raw gap conflates
    # "this county was served slowly" with "this disaster type is always slow."
    # Subtracting the per-type median isolates the county-level deviation.
    if "incident_type" in d.columns and d["incident_type"].notna().any():
        type_medians = d.groupby("incident_type")["response_gap_days"].median()
        d["type_baseline"] = d["incident_type"].map(type_medians)
        d["excess_gap"] = d["response_gap_days"] - d["type_baseline"]
    else:
        d["excess_gap"] = d["response_gap_days"]

    # Winsorize both axes before computing correlations
    gap_w    = _winsorize(d["response_gap_days"])
    income_w = _winsorize(d["median_income"])

    # Log-transform income to reduce right-skew before Pearson
    log_income = np.log1p(income_w)
    r_p, p_p = stats.pearsonr(log_income, gap_w)
    r_s, p_s = stats.spearmanr(d["median_income"], d["response_gap_days"])

    # Excess-gap correlation: does income predict above-baseline delays?
    excess_clean = d.dropna(subset=["excess_gap"])
    if len(excess_clean) >= 10:
        r_excess, p_excess = stats.spearmanr(
            excess_clean["median_income"], excess_clean["excess_gap"]
        )
    else:
        r_excess, p_excess = None, None

    # Mann-Whitney U: do rural and urban counties have different gap distributions?
    rural = d[d["is_rural"] == True]["response_gap_days"]
    urban = d[d["is_rural"] == False]["response_gap_days"]
    if len(rural) >= 5 and len(urban) >= 5:
        mw_stat, mw_p = stats.mannwhitneyu(rural, urban, alternative="two-sided")
    else:
        mw_stat, mw_p = None, None

    rural_mean = _f(rural.mean()) if not rural.empty else None
    urban_mean = _f(urban.mean()) if not urban.empty else None

    return {
        "n":                  int(len(d)),
        "pearson_r":          _f(r_p),
        "spearman_r":         _f(r_s),
        "p_value":            _f(p_s, 6),
        # excess_gap_spearman_r: correlation after removing the per-disaster-type
        # baseline. A stronger signal here means income predicts above-average
        # delays even after controlling for the type of disaster.
        "excess_gap_spearman_r": _f(r_excess),
        "excess_gap_p_value":    _f(p_excess, 6),
        "rural_mean_gap":     rural_mean,
        "urban_mean_gap":     urban_mean,
        "mann_whitney_u":     _f(mw_stat) if mw_stat is not None else None,
        "mann_whitney_p":     _f(mw_p, 6) if mw_p is not None else None,
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
        p25, p75 = gap.quantile(0.25), gap.quantile(0.75)
        out.append({
            "quintile":        str(label),
            "n":               int(len(group)),
            "median_gap_days": round(float(gap.median()), 1),
            "mean_gap_days":   round(float(gap.mean()), 1),
            "p25_gap":         round(float(p25), 1),
            "p75_gap":         round(float(p75), 1),
            "iqr_gap":         round(float(p75 - p25), 1),
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
    Composite underserved score with disaster-frequency weighting.

    Score = 0.45 * z(avg_gap * log1p(n_disasters))
           + 0.35 * z(-median_income)
           + 0.20 * is_rural

    Weighting avg_gap by log1p(n_disasters) means a county that consistently
    waits 120 days across five disasters ranks higher than one with a single
    120-day event. The log transform dampens the effect so one extra disaster
    doesn't dominate — it rewards consistent underservice, not outlier events.

    Income weight increased from 0.30 → 0.35 because the gap component now
    carries more information (disaster frequency), so income needs a slightly
    larger coefficient to stay proportionally influential.
    """
    sql = text("""
        SELECT m.county_fips, c.name, c.state,
               AVG(m.response_gap_days) AS avg_gap,
               COUNT(*)                 AS n_disasters,
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

    # Frequency-weighted gap: rewards counties with consistently long waits
    df["weighted_gap"] = df["avg_gap"] * np.log1p(df["n_disasters"])

    df["score"] = (
        0.45 * _zscore(df["weighted_gap"])
        + 0.35 * _zscore(-df["median_income"])
        + 0.20 * df["is_rural"].astype(float)
    )

    top = df.nlargest(top_n, "score")
    return [
        {
            "county_fips":       r.county_fips,
            "county_name":       r.name,
            "state":             r.state,
            "avg_gap_days":      round(float(r.avg_gap), 1),
            "n_disasters":       int(r.n_disasters),
            "median_income":     int(r.median_income),
            "is_rural":          bool(r.is_rural),
            "population":        int(r.population) if r.population else None,
            "underserved_score": round(float(r.score), 4),
        }
        for r in top.itertuples()
    ]


def temporal_trends(db: Session) -> list[dict]:
    sql = text("""
        SELECT EXTRACT(YEAR FROM d.declaration_date)::int AS year,
               AVG(m.response_gap_days)                   AS avg_gap,
               PERCENTILE_CONT(0.5) WITHIN GROUP
                   (ORDER BY m.response_gap_days)         AS median_gap,
               COUNT(*)                                   AS n,
               AVG(CASE WHEN c.is_rural THEN m.response_gap_days END)  AS rural_avg,
               AVG(CASE WHEN NOT c.is_rural THEN m.response_gap_days END) AS urban_avg
        FROM metrics m
        JOIN disasters d ON d.id = m.disaster_id
        JOIN counties  c ON c.fips = m.county_fips
        WHERE m.response_gap_days BETWEEN 0 AND 730
          AND d.declaration_date IS NOT NULL
        GROUP BY year
        ORDER BY year
    """)
    result = db.execute(sql)
    rows = result.fetchall()
    return [
        {
            "year":       int(r.year),
            "n":          int(r.n),
            "avg_gap":    round(float(r.avg_gap or 0), 1),
            "median_gap": round(float(r.median_gap or 0), 1),
            "rural_avg":  round(float(r.rural_avg), 1) if r.rural_avg is not None else None,
            "urban_avg":  round(float(r.urban_avg), 1) if r.urban_avg is not None else None,
        }
        for r in rows
    ]


def stratified_correlation(db: Session) -> list[dict]:
    """
    Spearman ρ between county median income and response gap, computed
    separately for each FEMA disaster type.

    Motivation: pooling all disaster types in one global correlation masks
    type-level signals. Flooding disproportionately affects low-income
    coastal and river-basin counties; wildfires skew toward higher-income
    western counties. Stratifying removes that confound and surfaces whether
    the income-delay relationship is consistent or specific to certain events.

    Only types with n >= 30 are included — below that Spearman ρ is unstable.
    """
    df = _load_base(db)
    d = df.dropna(subset=["median_income", "response_gap_days", "incident_type"]).copy()
    d = d[d["response_gap_days"].between(0, 730)]
    if d.empty:
        return []

    out = []
    for dtype, grp in d.groupby("incident_type"):
        n = len(grp)
        if n < 30:
            continue
        r_s, p_s = stats.spearmanr(grp["median_income"], grp["response_gap_days"])
        rural = grp[grp["is_rural"] == True]["response_gap_days"]
        urban = grp[grp["is_rural"] == False]["response_gap_days"]
        out.append({
            "incident_type": str(dtype),
            "n":             int(n),
            "spearman_r":    _f(r_s),
            "p_value":       _f(p_s, 6),
            "median_gap":    round(float(grp["response_gap_days"].median()), 1),
            "p25_gap":       round(float(grp["response_gap_days"].quantile(0.25)), 1),
            "p75_gap":       round(float(grp["response_gap_days"].quantile(0.75)), 1),
            "rural_median":  _f(rural.median()) if not rural.empty else None,
            "urban_median":  _f(urban.median()) if not urban.empty else None,
        })

    # Strongest absolute correlation first so the most informative types lead
    return sorted(out, key=lambda x: abs(x["spearman_r"] or 0), reverse=True)


def multivariable_gap_model(db: Session) -> dict:
    from sklearn.linear_model import Ridge
    from sklearn.preprocessing import StandardScaler

    sql = text("""
        SELECT m.response_gap_days, c.median_income, c.is_rural,
               c.state, dis.incident_type,
               COUNT(m2.disaster_id) AS disaster_count
        FROM metrics m
        JOIN counties  c   ON c.fips = m.county_fips
        JOIN disasters dis ON dis.id = m.disaster_id
        LEFT JOIN disbursements m2 ON m2.disaster_id = m.disaster_id
        WHERE m.response_gap_days BETWEEN 0 AND 730
          AND c.median_income IS NOT NULL
        GROUP BY m.response_gap_days, c.median_income, c.is_rural,
                 c.state, dis.incident_type
    """)
    result = db.execute(sql)
    df = pd.DataFrame(result.fetchall(), columns=result.keys())

    if len(df) < 20:
        return {"n": 0, "r2": None, "coefficients": {}}

    df["log_income"] = np.log1p(df["median_income"].clip(lower=1))
    df["is_rural"]   = df["is_rural"].astype(float)
    df["fema_region"] = df["state"].map(_FEMA_REGION).fillna(0).astype(int)

    # One-hot encode FEMA region (drop first to avoid multicollinearity)
    region_dummies = pd.get_dummies(df["fema_region"], prefix="region", drop_first=True)
    X = pd.concat([df[["log_income", "is_rural"]], region_dummies], axis=1).astype(float)
    y = np.log1p(df["response_gap_days"].clip(lower=0))

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = Ridge(alpha=1.0)
    model.fit(X_scaled, y)

    r2 = float(model.score(X_scaled, y))
    coef = {name: round(float(c), 4) for name, c in zip(X.columns, model.coef_)}

    return {
        "n":            int(len(df)),
        "r2":           round(r2, 4),
        "target":       "log(response_gap_days + 1)",
        "features":     list(X.columns),
        "coefficients": coef,
        "note":         "Coefficients on standardised features; negative = faster aid.",
    }
