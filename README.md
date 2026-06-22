# Disaster Relief Response Gap Tracker (DRRGT)

When a natural disaster strikes, federal relief funds are essential for recovery. However, historical data reveals disparities in how quickly this aid reaches different communities. Lower-income and rural counties frequently experience longer delays between the date a disaster is declared and the date the first relief funds are disbursed. 

The Disaster Relief Response Gap Tracker (DRRGT) exists to quantify these disparities. By analyzing millions of records from FEMA and the US Census Bureau, this platform tracks the "response gap" across thousands of counties. It is designed to help researchers, journalists, and policymakers hold administrative bodies accountable by highlighting exactly where and when disaster relief is systematically delayed.

---

## Architecture

The system is designed to automatically ingest, normalize, and serve millions of disaster records:

1. **Ingestion & ETL**: A scheduled Celery worker retrieves real-time data from the OpenFEMA API (Declarations, Public Assistance Projects) and the Census API (Income, Population). 
2. **Data Store**: PostgreSQL serves as the primary database, storing normalized disaster metrics and executing complex analytical window functions.
3. **API**: A FastAPI backend exposes cached `O(1)` endpoints for instantaneous report generation.
4. **Client**: A React Single Page Application provides interactive reports, maps, and CSV exports.

---

## ETL Workflow

The Extract, Transform, Load (ETL) pipeline runs autonomously to keep the dashboard up to date:

1. **Extract**: Pulls county demographics (population, median income) from the Census API. Pulls all declared disasters and their associated Public Assistance (PA) funded projects from the OpenFEMA API using pagination and exponential backoff.
2. **Transform**: Links FEMA projects to Census counties via FIPS codes. Calculates the critical "Response Gap" (days between disaster declaration and project obligation). Computes rural/urban flags and income percentiles.
3. **Load**: Upserts the raw records into the database. A post-processing step then runs aggregate SQL queries to precompute performance quintiles, historical trends, and correlation coefficients. 

---

## Reports

DRRGT generates comprehensive data reports available both interactively in the browser and as downloadable CSVs.

### County Reports
Analyzes a specific county's historical relief performance, comparing its response times to demographically similar peer counties.
![County Report Placeholder](placeholder-county-report.png)

### State Reports
Aggregates performance across an entire state, mapping out the best and worst-performing counties within that jurisdiction.
![State Report Placeholder](placeholder-state-report.png)

### Outlier Reports
Highlights systemic failures and successes by identifying the most chronically underserved communities nationwide.
![Outlier Report Placeholder](placeholder-outlier-report.png)

---

## Methodology

To ensure analytical rigor, DRRGT uses the following strictly defined metrics:

* **Response Gap Calculation**: `Response Gap = Project Obligation Date - Disaster Declaration Date`. This represents the time it takes for a community to receive actionable financial support after an emergency is declared.
* **County Rankings**: Counties are ranked nationally based on their average response gaps and composite underserved scores.
* **Comparable County Selection**: To accurately judge a county's performance, it is compared only to "peer" counties. Peers are strictly defined as counties matching the same rural/urban classification, with populations within ±25%, and median household incomes within ±25%.
* **Outlier Definitions**: 
  * *Most Underserved*: Counties with the highest overall average response gaps.
  * *Consistently Underserved*: Counties that have experienced >90-day response gaps across multiple distinct disaster events.
  * *Most Improved*: Counties that historically had terrible response times but have shown a sharp decrease in gap duration in recent years.

---

## Deployment (Docker Compose)

The entire DRRGT stack (PostgreSQL, Redis, FastAPI, Celery, React) can be launched locally using Docker Compose.

**Prerequisites:** Docker and Docker Compose must be installed. Ports 5432, 6379, 8000, and 5173 must be available.

```bash
# 1. Clone the repository
git clone https://github.com/Dhruva-Aher/Disaster-Relief-Response-Gap-Tracker-DRRGT- drrgt
cd drrgt

# 2. Configure environment (optional but recommended for real Census data)
cp .env.example .env
# Edit .env and add your CENSUS_API_KEY if you have one.

# 3. Start the application stack
docker compose up --build -d

# On first boot, the API container automatically runs migrations and the initial ETL pipeline.
```

Once running, the applications are available at:
* **Frontend Dashboard**: `http://localhost:5173`
* **API Documentation**: `http://localhost:8000/docs`

To manually trigger a fresh ETL run:
```bash
docker compose exec api python -m app.etl.pipeline
```

---

## API Examples

The backend provides a RESTful JSON API. All report endpoints can also output raw CSV data by appending `?format=csv`.

```bash
# Get health status
curl http://localhost:8000/health/deep

# Fetch a comprehensive report for Miami-Dade County (FIPS 12086)
curl http://localhost:8000/reports/county/12086

# Download the same county report as a CSV file
curl "http://localhost:8000/reports/county/12086?format=csv" -o miami_dade.csv

# Fetch a statewide aggregate report for Florida
curl http://localhost:8000/reports/state/FL

# Retrieve national outliers (most underserved counties)
curl http://localhost:8000/reports/outliers

# Download national outliers as a CSV file
curl "http://localhost:8000/reports/outliers?format=csv" -o outliers.csv
```

---

## Limitations

1. **Census API Key**: Without a valid `CENSUS_API_KEY` in your `.env` file, the pipeline will fall back to a hardcoded demo set of 20 sample counties. A free key can be obtained from the US Census Bureau.
2. **Data Sparsity**: The `quintiles` analysis requires a minimum of 25 matched metric records to generate statistically valid quintile buckets. If running exclusively on the sample fallback data, this endpoint may return empty arrays.
3. **Database Dependency**: The `/analytics/trends` endpoint utilizes PostgreSQL-specific SQL functions (`PERCENTILE_CONT`). As a result, the application requires a PostgreSQL database to run correctly and will fail if run against SQLite.
4. **PDF Exports**: The "Print to PDF" functionality utilizes the browser's native `window.print()` functionality and CSS `@media print` rules. The exact formatting of the generated PDF depends heavily on the specific web browser being used.
5. **Security**: By default, all API endpoints are unauthenticated and public. If deploying with sensitive or proprietary data, an authentication layer must be added.

---

## License

MIT License — see `LICENSE` for details.
