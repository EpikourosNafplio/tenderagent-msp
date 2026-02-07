"""Tests for the historie module (gunningshistorie queries)."""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.historie import (
    is_historie_loaded,
    query_gunningshistorie,
    query_herhalingspatronen,
    query_vooraankondigingen,
)


# ── Graceful degradation (no DB) ─────────────────────────────────────────

def test_is_historie_loaded_false_when_no_db():
    with patch("app.historie.HISTORIE_DB_PATH", Path("/nonexistent/db.sqlite3")):
        assert is_historie_loaded() is False


def test_query_gunningshistorie_empty_when_no_db():
    with patch("app.historie.HISTORIE_DB_PATH", Path("/nonexistent/db.sqlite3")):
        assert query_gunningshistorie("Amsterdam") == []


def test_query_herhalingspatronen_empty_when_no_db():
    with patch("app.historie.HISTORIE_DB_PATH", Path("/nonexistent/db.sqlite3")):
        assert query_herhalingspatronen() == []


def test_query_vooraankondigingen_empty_when_no_db():
    with patch("app.historie.HISTORIE_DB_PATH", Path("/nonexistent/db.sqlite3")):
        assert query_vooraankondigingen() == []


# ── With temporary test database ──────────────────────────────────────────

@pytest.fixture
def historie_db(tmp_path):
    """Create a temporary SQLite database with test data."""
    db_path = tmp_path / "test_historie.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE gunningen (
            publicatie_id TEXT,
            tenderned_kenmerk TEXT,
            publicatiedatum TEXT,
            aanbestedende_dienst TEXT,
            beschrijving TEXT,
            type_opdracht TEXT,
            procedure_type TEXT,
            cpv_codes TEXT,
            publicatie_soort TEXT,
            is_ict INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE percelen (
            publicatie_id TEXT,
            naam_perceel TEXT,
            datum_gunning TEXT,
            aantal_inschrijvingen INTEGER,
            gegunde_ondernemer TEXT,
            gegunde_plaats TEXT,
            geraamde_waarde REAL,
            definitieve_waarde REAL
        )
    """)
    # Insert test gunning
    conn.execute("""
        INSERT INTO gunningen VALUES (
            'PUB001', 'TK-001', '2025-06-15',
            'Gemeente Amsterdam', 'IT werkplekbeheer', 'Diensten',
            'Openbaar', '72000000', 'Aankondiging van een gegunde opdracht', 1
        )
    """)
    conn.execute("""
        INSERT INTO percelen VALUES (
            'PUB001', 'Perceel 1', '2023-07-01', 5,
            'IT Provider BV', 'Amsterdam', 500000.0, 450000.0
        )
    """)
    # Insert vooraankondiging
    conn.execute("""
        INSERT INTO gunningen VALUES (
            'PUB002', 'TK-002', date('now'),
            'Gemeente Utrecht', 'Cloud hosting platform', 'Diensten',
            'Openbaar', '72400000', 'Vooraankondiging', 1
        )
    """)
    conn.commit()
    conn.close()
    return db_path


def test_is_historie_loaded_true(historie_db):
    with patch("app.historie.HISTORIE_DB_PATH", historie_db):
        assert is_historie_loaded() is True


def test_query_gunningshistorie_returns_results(historie_db):
    with patch("app.historie.HISTORIE_DB_PATH", historie_db):
        results = query_gunningshistorie("Amsterdam")
        assert len(results) == 1
        assert results[0]["aanbestedende_dienst"] == "Gemeente Amsterdam"
        assert results[0]["gegunde_ondernemer"] == "IT Provider BV"
        assert results[0]["geraamde_waarde"] == 500000.0


def test_query_gunningshistorie_no_match(historie_db):
    with patch("app.historie.HISTORIE_DB_PATH", historie_db):
        results = query_gunningshistorie("Maastricht")
        assert results == []


def test_query_gunningshistorie_limit(historie_db):
    with patch("app.historie.HISTORIE_DB_PATH", historie_db):
        results = query_gunningshistorie("Gemeente", limit=1)
        assert len(results) <= 1


def test_query_herhalingspatronen_returns_results(historie_db):
    with patch("app.historie.HISTORIE_DB_PATH", historie_db):
        results = query_herhalingspatronen()
        assert isinstance(results, list)
        # PUB001 was awarded 2023-07-01 which is ~2.5 years ago — within 2-5 year window
        assert len(results) >= 1
        assert results[0]["aanbestedende_dienst"] == "Gemeente Amsterdam"


def test_query_vooraankondigingen_returns_results(historie_db):
    with patch("app.historie.HISTORIE_DB_PATH", historie_db):
        results = query_vooraankondigingen()
        assert len(results) == 1
        assert results[0]["aanbestedende_dienst"] == "Gemeente Utrecht"
        assert results[0]["publicatie_soort"] == "Vooraankondiging"
