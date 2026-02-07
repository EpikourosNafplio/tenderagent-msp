"""Tests for API endpoints using FastAPI TestClient."""

import json
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Use a temp database for tests
_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp_db.close()

import app.database as db_module
db_module.DB_PATH = _tmp_db.name

from app.main import app

# Sample tender data as returned by TenderNed
SAMPLE_TENDERS = [
    {
        "publicatieId": "100001",
        "publicatieDatum": "2026-02-06",
        "aanbestedingNaam": "SaaS Cloud Platform voor Gemeente",
        "opdrachtgeverNaam": "Gemeente Amsterdam",
        "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
        "typeOpdracht": {"code": "D", "omschrijving": "Diensten"},
        "procedure": {"code": "OPE", "omschrijving": "Openbaar"},
        "europees": True,
        "opdrachtBeschrijving": "Levering van een SaaS cloud hosting platform voor IT-beheer",
        "cpvCodes": [
            {"code": "72000000-5", "omschrijving": "IT-diensten", "isHoofdOpdracht": True}
        ],
        "link": {"href": "https://www.tenderned.nl/aankondigingen/100001"},
    },
    {
        "publicatieId": "100002",
        "publicatieDatum": "2026-02-05",
        "aanbestedingNaam": "Netwerk infrastructuur upgrade",
        "opdrachtgeverNaam": "Rijksoverheid",
        "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
        "typeOpdracht": {"code": "L", "omschrijving": "Leveringen"},
        "procedure": {"code": "OPE", "omschrijving": "Openbaar"},
        "europees": False,
        "opdrachtBeschrijving": "Vervanging netwerk switches en implementatie firewall",
        "cpvCodes": [
            {"code": "30200000-1", "omschrijving": "Computeruitrusting", "isHoofdOpdracht": True}
        ],
        "link": {"href": "https://www.tenderned.nl/aankondigingen/100002"},
    },
    {
        "publicatieId": "100003",
        "publicatieDatum": "2026-02-04",
        "aanbestedingNaam": "Kantoormeubelen",
        "opdrachtgeverNaam": "Gemeente Utrecht",
        "typePublicatie": {"code": "AAO", "omschrijving": "Aankondiging opdracht"},
        "typeOpdracht": {"code": "L", "omschrijving": "Leveringen"},
        "procedure": {"code": "OPE", "omschrijving": "Openbaar"},
        "europees": False,
        "opdrachtBeschrijving": "Levering van meubilair en kantoormeubelen",
        "cpvCodes": [],
        "link": {"href": "https://www.tenderned.nl/aankondigingen/100003"},
    },
]


@pytest.fixture(autouse=True)
def setup_test_db():
    """Initialize a fresh test database and seed with sample data."""
    # Reset DB file
    if os.path.exists(_tmp_db.name):
        os.unlink(_tmp_db.name)
    db_module.DB_PATH = _tmp_db.name
    db_module.init_db()
    db_module.upsert_tenders(SAMPLE_TENDERS)
    yield
    if os.path.exists(_tmp_db.name):
        os.unlink(_tmp_db.name)


@pytest.fixture
def client():
    return TestClient(app)


# ── Root endpoint ────────────────────────────────────────────────────────

def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "TenderAgent" in resp.text
    assert "/api/v1/tenders" in resp.text


# ── CPV codes endpoint ──────────────────────────────────────────────────

def test_cpv_codes(client):
    resp = client.get("/api/v1/cpv-codes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 36
    codes = [c["code"] for c in data["cpv_codes"]]
    assert "72000000" in codes
    assert "48000000" in codes


# ── Discover endpoint ───────────────────────────────────────────────────

def test_discover_returns_tenders(client):
    resp = client.get("/api/v1/discover")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["fetched_from"] == "cache"
    assert data["tender_count"] == 3


def test_discover_sorted_by_score_desc(client):
    resp = client.get("/api/v1/discover")
    tenders = resp.json()["tenders"]
    scores = [t["relevance_score"] for t in tenders]
    assert scores == sorted(scores, reverse=True)


def test_discover_filter_min_score(client):
    resp = client.get("/api/v1/discover?min_score=40")
    tenders = resp.json()["tenders"]
    for t in tenders:
        assert t["relevance_score"] >= 40


def test_discover_filter_level(client):
    resp = client.get("/api/v1/discover?level=hoog")
    tenders = resp.json()["tenders"]
    for t in tenders:
        assert t["relevance_level"] == "hoog"


# ── Tenders list endpoint ───────────────────────────────────────────────

def test_tenders_list(client):
    resp = client.get("/api/v1/tenders")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 3


def test_tenders_pagination(client):
    resp = client.get("/api/v1/tenders?limit=1&offset=0")
    data = resp.json()
    assert len(data) == 1

    resp2 = client.get("/api/v1/tenders?limit=1&offset=1")
    data2 = resp2.json()
    assert len(data2) == 1
    assert data[0]["publicatie_id"] != data2[0]["publicatie_id"]


def test_tenders_filter_type_opdracht(client):
    resp = client.get("/api/v1/tenders?type_opdracht=Diensten")
    data = resp.json()
    for t in data:
        assert t["type_opdracht"] == "Diensten"


def test_tenders_filter_level(client):
    resp = client.get("/api/v1/tenders?level=laag")
    data = resp.json()
    for t in data:
        assert t["relevance_level"] == "laag"


# ── Single tender endpoint ──────────────────────────────────────────────

def test_get_tender_by_id(client):
    resp = client.get("/api/v1/tenders/100001")
    assert resp.status_code == 200
    data = resp.json()
    assert data["publicatie_id"] == "100001"
    assert data["naam"] == "SaaS Cloud Platform voor Gemeente"
    assert data["opdrachtgever"] == "Gemeente Amsterdam"


def test_get_tender_not_found(client):
    with patch("app.main.fetch_detail", new_callable=AsyncMock, return_value=None):
        resp = client.get("/api/v1/tenders/999999")
        assert resp.status_code == 404


# ── Stats endpoint ──────────────────────────────────────────────────────

def test_stats(client):
    resp = client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tenders"] == 3
    assert "hoog" in data["by_relevance"]
    assert "midden" in data["by_relevance"]
    assert "laag" in data["by_relevance"]
    assert sum(data["by_relevance"].values()) == 3
    assert "cache" in data


def test_stats_type_opdracht_breakdown(client):
    resp = client.get("/api/v1/stats")
    data = resp.json()
    assert "Diensten" in data["by_type_opdracht"]
    assert "Leveringen" in data["by_type_opdracht"]


# ── Refresh endpoint ────────────────────────────────────────────────────

def test_refresh(client):
    with patch("app.main.discover_it_tenders", new_callable=AsyncMock, return_value=SAMPLE_TENDERS):
        resp = client.post("/api/v1/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["refreshed_tenders"] == 3


# ── Response schema validation ──────────────────────────────────────────

def test_tender_response_has_required_fields(client):
    resp = client.get("/api/v1/tenders/100001")
    data = resp.json()
    required = [
        "publicatie_id", "naam", "opdrachtgever", "relevance_score",
        "relevance_level", "matched_keywords", "cpv_codes",
    ]
    for field in required:
        assert field in data, f"Missing field: {field}"


def test_discover_response_has_metadata(client):
    resp = client.get("/api/v1/discover")
    data = resp.json()
    assert "status" in data
    assert "fetched_from" in data
    assert "tender_count" in data
    assert "timestamp" in data
    assert "tenders" in data
