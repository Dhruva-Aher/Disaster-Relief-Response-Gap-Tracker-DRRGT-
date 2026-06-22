import json
import logging
from sqlalchemy import text
from sqlalchemy.orm import Session
from datetime import datetime
import pandas as pd
import numpy as np

log = logging.getLogger(__name__)

def precompute_insights(db: Session) -> None:
    """
    Computes rigorous County and State insights.
    Stores results in the county_insights and state_insights normalized tables.
    """
    log.info("Starting insights precomputation...")
    
    try:
        # Load all base data required for insights
        sql = text("""
            SELECT 
                c.fips, c.name, c.state, c.population, c.median_income, c.is_rural,
                m.response_gap_days,
                EXTRACT(YEAR FROM d.declaration_date)::int AS year
            FROM counties c
            JOIN metrics m ON c.fips = m.county_fips
            JOIN disasters d ON m.disaster_id = d.id
            WHERE m.response_gap_days >= 0 AND m.response_gap_days <= 730
        """)
        
        # We handle sqlite gracefully in tests
        try:
            result = db.execute(sql)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
        except Exception:
            # SQLite fallback
            sql_sqlite = text("""
                SELECT 
                    c.fips, c.name, c.state, c.population, c.median_income, c.is_rural,
                    m.response_gap_days,
                    CAST(STRFTIME('%Y', d.declaration_date) AS INTEGER) AS year
                FROM counties c
                JOIN metrics m ON c.fips = m.county_fips
                JOIN disasters d ON m.disaster_id = d.id
                WHERE m.response_gap_days >= 0 AND m.response_gap_days <= 730
            """)
            result = db.execute(sql_sqlite)
            df = pd.DataFrame(result.fetchall(), columns=result.keys())

        if df.empty:
            log.warning("No data found for insights precomputation.")
            return

        # --- COUNTY LEVEL ---
        county_agg = df.groupby(["fips", "name", "state", "population", "median_income", "is_rural"], dropna=False).agg(
            avg_gap=("response_gap_days", "mean"),
            n_disasters=("response_gap_days", "count")
        ).reset_index()

        county_agg["national_rank"] = county_agg["avg_gap"].rank(method="min", ascending=False)
        county_agg["national_percentile"] = county_agg["avg_gap"].rank(pct=True, ascending=False) * 100

        # Trends per county
        county_trends = df.groupby(["fips", "year"]).agg(
            avg_gap=("response_gap_days", "mean")
        ).reset_index()

        valid_c = county_agg.dropna(subset=["population", "median_income"]).copy()

        # Clear existing
        db.execute(text("DELETE FROM county_insights"))
        db.execute(text("DELETE FROM state_insights"))

        now = datetime.utcnow()

        county_inserts = []
        for _, row in county_agg.iterrows():
            fips = row["fips"]
            trends_df = county_trends[county_trends["fips"] == fips].sort_values("year")
            trends_list = [{"year": int(t.year), "avg_gap": float(t.avg_gap)} for _, t in trends_df.iterrows()]
            
            comps_list = []
            if not valid_c.empty and pd.notna(row["population"]) and pd.notna(row["median_income"]):
                # Rule-based matching:
                # 1. Same rural/urban category
                # 2. Population within 25% threshold
                # 3. Income within 25% threshold
                
                is_rural = row["is_rural"]
                pop = row["population"]
                inc = row["median_income"]
                
                comps = valid_c[
                    (valid_c["fips"] != fips) &
                    (valid_c["is_rural"] == is_rural) &
                    (valid_c["population"] >= pop * 0.75) & (valid_c["population"] <= pop * 1.25) &
                    (valid_c["median_income"] >= inc * 0.75) & (valid_c["median_income"] <= inc * 1.25)
                ].copy()
                
                # Take top 5 closest by absolute population difference if there are many matches
                if not comps.empty:
                    comps["pop_diff"] = abs(comps["population"] - pop)
                    comps = comps.nsmallest(5, "pop_diff")
                    
                comps_list = [
                    {
                        "fips": str(c.fips), "name": str(c.name), "state": str(c.state),
                        "population": int(c.population), "median_income": float(c.median_income),
                        "avg_response_gap_days": float(c.avg_gap)
                    } for _, c in comps.iterrows()
                ]

            county_inserts.append({
                "fips": str(fips),
                "avg_response_gap_days": float(row["avg_gap"]),
                "national_rank": int(row["national_rank"]),
                "national_percentile": float(row["national_percentile"]),
                # Bug #6 fix: serialize Python lists to JSON strings before passing to
                # SQLAlchemy text() INSERT. text() with named params does not auto-serialize
                # Python objects to JSON — PostgreSQL receives a Python list object and raises
                # "can't adapt type 'list'" without explicit json.dumps().
                "comparable_counties": json.dumps(comps_list),
                "historical_trend": json.dumps(trends_list),
                "updated_at": now
            })

        if county_inserts:
            db.execute(text("""
                INSERT INTO county_insights 
                (fips, avg_response_gap_days, national_rank, national_percentile, comparable_counties, historical_trend, updated_at)
                VALUES (:fips, :avg_response_gap_days, :national_rank, :national_percentile, :comparable_counties, :historical_trend, :updated_at)
            """), county_inserts)

        # --- STATE LEVEL ---
        state_agg = df.groupby("state").agg(
            avg_gap=("response_gap_days", "mean")
        ).reset_index()

        state_agg["national_rank"] = state_agg["avg_gap"].rank(method="min", ascending=False)

        state_trends = df.groupby(["state", "year"]).agg(
            avg_gap=("response_gap_days", "mean")
        ).reset_index()

        state_inserts = []
        for _, row in state_agg.iterrows():
            state = row["state"]
            trends_df = state_trends[state_trends["state"] == state].sort_values("year")
            trends_list = [{"year": int(t.year), "avg_gap": float(t.avg_gap)} for _, t in trends_df.iterrows()]
            
            state_inserts.append({
                "state": str(state),
                "avg_response_gap_days": float(row["avg_gap"]),
                "national_rank": int(row["national_rank"]),
                # Bug #6 fix: same JSON serialization required for state historical_trend
                "historical_trend": json.dumps(trends_list),
                "updated_at": now
            })

        if state_inserts:
            db.execute(text("""
                INSERT INTO state_insights 
                (state, avg_response_gap_days, national_rank, historical_trend, updated_at)
                VALUES (:state, :avg_response_gap_days, :national_rank, :historical_trend, :updated_at)
            """), state_inserts)

        db.commit()
        log.info(f"Successfully precomputed insights for {len(county_inserts)} counties and {len(state_inserts)} states.")
    except Exception as exc:
        db.rollback()
        log.error("Failed to compute insights tables", extra={"ctx_err": str(exc)}, exc_info=True)
