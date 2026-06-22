import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.core.database import get_db
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.db import Base, County

# Use SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def test_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    # Seed data
    c1 = County(fips="12345", name="Test County", state="TX", population=1000, median_income=50000.0, is_rural=True, income_percentile=0.5, rural_urban_code=1)
    db.add(c1)
    db.commit()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_get_counties():
    response = client.get("/counties?state=TX")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test County"

def test_export_counties_csv():
    response = client.get("/export/counties?format=csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "Test County" in response.text
