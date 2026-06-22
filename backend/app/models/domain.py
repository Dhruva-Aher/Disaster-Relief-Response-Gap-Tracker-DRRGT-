from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any

class CountyBase(BaseModel):
    fips: str
    name: str
    state: str
    median_income: Optional[float]
    population: Optional[int]
    is_rural: Optional[bool]
    income_percentile: Optional[float]

    model_config = ConfigDict(from_attributes=True)

class MetricItem(BaseModel):
    disaster_id: str
    county_fips: str
    county_name: str
    state: str
    response_gap_days: Optional[int]
    amount_per_capita: Optional[float]
    median_income: Optional[float]
    is_rural: Optional[bool]

class MetricsResponse(BaseModel):
    total: int
    items: List[MetricItem]

class OutlierItem(BaseModel):
    county: str
    state: str
    fips: str
    response_gap_days: Optional[int]
    median_income: Optional[float]
    is_rural: Optional[bool]
    disaster_id: str

class TimeseriesItem(BaseModel):
    year: int
    avg_gap: float
    n: int

class InsightStats(BaseModel):
    n: int
    pearson_r: Optional[float]
    spearman_r: Optional[float]
    rural_median_gap: Optional[float]
    urban_median_gap: Optional[float]
    rural_n: Optional[int]
    urban_n: Optional[int]
    rural_urban_mw_p: Optional[float]

class InsightsResponse(BaseModel):
    stats: Dict[str, Any]
    insights: List[str]

class QuintileItem(BaseModel):
    quintile: str
    n: int
    median_gap_days: float
    mean_gap_days: float
    p25_gap: float
    p75_gap: float
    median_income: float
    median_aid_per_capita: Optional[float]
    pct_rural: float

class DisasterTypeItem(BaseModel):
    incident_type: str
    n: int
    median_gap_days: float
    mean_gap_days: float
    rural_median_gap: Optional[float]
    urban_median_gap: Optional[float]
    rural_n: int
    urban_n: int

class RegionalItem(BaseModel):
    fema_region: int
    n: int
    median_gap_days: float
    mean_gap_days: float
    median_income: Optional[float]
    median_aid_per_capita: Optional[float]
    pct_rural: float
    states: List[str]

class UnderservedItem(BaseModel):
    fips: str
    county: str
    state: str
    underserved_score: float
    avg_gap_days: float
    median_income: int
    is_rural: bool
    n_disasters: int
    avg_aid_per_capita: Optional[float]

class TrendItem(BaseModel):
    year: int
    is_rural: bool
    median_gap_days: float
    mean_gap_days: float
    n: int

class ModelResponse(BaseModel):
    n: int
    r2: float
    target: str
    note: str
    core_coefficients: List[Dict[str, Any]]
    all_coefficients: Dict[str, Any]

class TrendData(BaseModel):
    year: int
    avg_gap: float

class ComparableCounty(BaseModel):
    fips: str
    name: str
    state: str
    population: int
    median_income: float
    avg_response_gap_days: float

class CountyReportResponse(BaseModel):
    fips: str
    name: str
    state: str
    population: Optional[int]
    median_income: Optional[float]
    is_rural: Optional[bool]
    avg_response_gap_days: Optional[float]
    national_average_gap: float
    national_percentile: Optional[float]
    national_rank: Optional[int]
    total_counties_ranked: int
    historical_trend: List[TrendData]
    comparable_counties: List[ComparableCounty]
    methodology: str
    limitations: str
    sources: str
    last_updated: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "fips": "01001",
                "name": "Autauga County",
                "state": "AL",
                "population": 55000,
                "median_income": 58000.0,
                "is_rural": False,
                "avg_response_gap_days": 45.2,
                "national_average_gap": 73.0,
                "national_percentile": 85.0,
                "national_rank": 400,
                "total_counties_ranked": 3142,
                "historical_trend": [{"year": 2020, "avg_gap": 40.0}],
                "comparable_counties": [],
                "methodology": "Calculated by averaging the days between disaster declaration and first disbursement...",
                "limitations": "Does not account for disaster severity or PA vs IA program differences.",
                "sources": "FEMA OpenFEMA Dataset: Disaster Declarations Summaries v2, Public Assistance Funded Projects Details v1",
                "last_updated": "2026-06-22T00:00:00Z"
            }
        }
    )

class CountyRank(BaseModel):
    fips: str
    name: str
    avg_response_gap_days: float
    state_rank: int

class StateReportResponse(BaseModel):
    state: str
    avg_response_gap_days: Optional[float]
    national_average_gap: float
    national_state_rank: Optional[int]
    total_states_ranked: int
    county_rankings: List[CountyRank]
    historical_trend: List[TrendData]
    methodology: str
    limitations: str
    sources: str
    last_updated: str

class OutlierCounty(BaseModel):
    fips: str
    name: str
    state: str
    value: float
    reasoning: str

class OutlierReportResponse(BaseModel):
    most_underserved: List[OutlierCounty]
    most_improved: List[OutlierCounty]
    consistently_underserved: List[OutlierCounty]
    methodology: str
    limitations: str
    sources: str
    last_updated: str
