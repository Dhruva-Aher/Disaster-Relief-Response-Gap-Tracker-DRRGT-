"""Statistical analysis and simple ML predictor for response gap."""
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import LinearRegression
from sqlalchemy.orm import Session
from sqlalchemy import text


def load_joined(db: Session) -> pd.DataFrame:
    sql = text("""
        SELECT m.response_gap_days, m.amount_per_capita,
               c.median_income, c.income_percentile, c.population, c.is_rural, c.state
        FROM metrics m JOIN counties c ON c.fips = m.county_fips
        WHERE m.response_gap_days IS NOT NULL
    """)
    return pd.read_sql(sql, db.bind)


def income_gap_correlation(db: Session) -> dict:
    df = load_joined(db)
    if df.empty or df["median_income"].notna().sum() < 5:
        return {"n": 0, "pearson_r": None, "p_value": None}
    d = df.dropna(subset=["median_income", "response_gap_days"])
    r, p = stats.pearsonr(d["median_income"], d["response_gap_days"])
    rural_mean = df[df["is_rural"] == True]["response_gap_days"].mean()
    urban_mean = df[df["is_rural"] == False]["response_gap_days"].mean()
    return {
        "n": int(len(d)),
        "pearson_r": float(r),
        "p_value": float(p),
        "rural_mean_gap": None if np.isnan(rural_mean) else float(rural_mean),
        "urban_mean_gap": None if np.isnan(urban_mean) else float(urban_mean),
    }


def predict_gap(median_income: float, population: int, is_rural: bool, db: Session) -> float | None:
    df = load_joined(db).dropna(subset=["median_income", "population", "response_gap_days"])
    if len(df) < 20:
        return None
    X = df[["median_income", "population"]].assign(is_rural=df["is_rural"].astype(int))
    y = df["response_gap_days"]
    model = LinearRegression().fit(X, y)
    return float(model.predict([[median_income, population, int(is_rural)]])[0])
