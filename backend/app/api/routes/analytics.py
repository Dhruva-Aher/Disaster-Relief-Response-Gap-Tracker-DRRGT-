import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.db import AnalyticsCache

router = APIRouter(prefix="/analytics", tags=["analytics"])

def get_precomputed(db: Session, key: str) -> dict | list:
    row = db.query(AnalyticsCache).filter(AnalyticsCache.key == key).first()
    if not row:
        raise HTTPException(status_code=503, detail=f"Analytics not yet computed for {key}. Please run ETL.")
    try:
        return json.loads(row.data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Corrupted analytics cache.")

@router.get("/correlations")
def get_correlations(db: Session = Depends(get_db)):
    return get_precomputed(db, "correlations")

@router.get("/timeseries")
def get_timeseries(db: Session = Depends(get_db)):
    return get_precomputed(db, "timeseries")

@router.get("/insights")
def get_insights(db: Session = Depends(get_db)):
    return get_precomputed(db, "insights")

@router.get("/quintiles")
def get_quintiles(db: Session = Depends(get_db)):
    return get_precomputed(db, "quintiles")

@router.get("/disaster-types")
def get_disaster_types(db: Session = Depends(get_db)):
    return get_precomputed(db, "disaster_types")

@router.get("/regional")
def get_regional(db: Session = Depends(get_db)):
    return get_precomputed(db, "regional")

@router.get("/underserved")
def get_underserved(db: Session = Depends(get_db)):
    return get_precomputed(db, "underserved")

@router.get("/trends")
def get_trends(db: Session = Depends(get_db)):
    return get_precomputed(db, "trends")

@router.get("/model")
def get_model(db: Session = Depends(get_db)):
    return get_precomputed(db, "model")
