"""Gunningshistorie queries against the TenderNed openbare dataset (SQLite)."""

import sqlite3
from pathlib import Path
from typing import List

HISTORIE_DB_PATH = Path(__file__).parent.parent / "data" / "tenderned_historie.db"


def is_historie_loaded() -> bool:
    """Check if the gunningshistorie database file exists."""
    return HISTORIE_DB_PATH.exists()


def query_gunningshistorie(opdrachtgever: str, limit: int = 20) -> List[dict]:
    """Query gunningshistorie for a specific opdrachtgever.

    Returns list of dicts with gunning + perceel data.
    Returns [] if the database doesn't exist.
    """
    if not HISTORIE_DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(HISTORIE_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT DISTINCT
                g.publicatie_id, g.tenderned_kenmerk, g.publicatiedatum,
                g.aanbestedende_dienst, g.beschrijving, g.type_opdracht,
                g.procedure_type, g.cpv_codes,
                p.naam_perceel, p.datum_gunning, p.aantal_inschrijvingen,
                p.gegunde_ondernemer, p.gegunde_plaats,
                p.geraamde_waarde, p.definitieve_waarde
            FROM gunningen g
            LEFT JOIN percelen p ON g.publicatie_id = p.publicatie_id
            WHERE LOWER(g.aanbestedende_dienst) LIKE ?
            ORDER BY g.publicatiedatum DESC
            LIMIT ?
            """,
            (f"%{opdrachtgever.lower()}%", limit),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def query_herhalingspatronen(limit: int = 50) -> List[dict]:
    """Query ICT service contracts awarded 2-5 years ago (likely re-tenders).

    Returns [] if the database doesn't exist.
    """
    if not HISTORIE_DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(HISTORIE_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT
                g.aanbestedende_dienst, g.beschrijving, g.publicatiedatum,
                g.cpv_codes, g.type_opdracht,
                p.datum_gunning, p.gegunde_ondernemer, p.geraamde_waarde
            FROM gunningen g
            LEFT JOIN percelen p ON g.publicatie_id = p.publicatie_id
            WHERE g.publicatie_soort = 'Aankondiging van een gegunde opdracht'
            AND g.is_ict = 1
            AND g.type_opdracht = 'Diensten'
            AND p.datum_gunning IS NOT NULL
            AND p.datum_gunning BETWEEN date('now', '-5 years') AND date('now', '-2 years')
            ORDER BY p.datum_gunning DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def query_vooraankondigingen(limit: int = 50) -> List[dict]:
    """Query vooraankondigingen, marktconsultaties, and vrijwillige transparantie.

    Returns [] if the database doesn't exist.
    """
    if not HISTORIE_DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(HISTORIE_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            """
            SELECT
                g.aanbestedende_dienst, g.beschrijving, g.publicatiedatum,
                g.publicatie_soort, g.cpv_codes, g.tenderned_kenmerk,
                g.type_opdracht
            FROM gunningen g
            WHERE g.publicatie_soort IN (
                'Vooraankondiging',
                'Marktconsultatie',
                'Vrijwillige transparantie vooraf'
            )
            AND g.is_ict = 1
            AND g.publicatiedatum >= date('now', '-6 months')
            ORDER BY g.publicatiedatum DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()
