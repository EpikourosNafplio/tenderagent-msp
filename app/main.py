"""TenderAgent MSP — FastAPI app for Dutch IT tender discovery."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .cpv_codes import CPV_CODES
from .database import (
    get_all_tenders,
    get_cache_stats,
    get_tender_by_id,
    init_db,
    is_cache_fresh,
    upsert_tenders,
)
from .scoring import score_tender
from .tenderned import discover_it_tenders, fetch_detail

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")
    yield


app = FastAPI(
    title="TenderAgent MSP",
    description="Nederlandse IT-aanbestedingen discovery API voor MSP's",
    version="1.0.0",
    lifespan=lifespan,
)


# ── Pydantic response models ──────────────────────────────────────────────

class CpvCode(BaseModel):
    code: str
    description: str


class TenderSummary(BaseModel):
    publicatie_id: str
    naam: str
    opdrachtgever: str
    publicatie_datum: Optional[str] = None
    sluitings_datum: Optional[str] = None
    type_publicatie: Optional[str] = None
    type_opdracht: Optional[str] = None
    procedure: Optional[str] = None
    beschrijving: Optional[str] = None
    europees: bool = False
    cpv_codes: List[Dict] = []
    relevance_score: int = 0
    relevance_level: str = "laag"
    matched_keywords: List[str] = []
    link: Optional[str] = None


class DiscoverResponse(BaseModel):
    status: str
    fetched_from: str
    tender_count: int
    timestamp: str
    tenders: List[TenderSummary]


class StatsResponse(BaseModel):
    total_tenders: int
    by_relevance: Dict[str, int]
    by_type_opdracht: Dict[str, int]
    by_procedure: Dict[str, int]
    cache: Dict


class CpvListResponse(BaseModel):
    count: int
    cpv_codes: List[CpvCode]


# ── Helpers ───────────────────────────────────────────────────────────────

def _format_tender(raw: dict) -> TenderSummary:
    """Convert raw TenderNed data to our response model with scoring."""
    naam = raw.get("aanbestedingNaam", "")
    beschrijving = raw.get("opdrachtBeschrijving", "")

    cpv_codes = raw.get("cpvCodes", [])
    scoring = score_tender(naam, beschrijving, cpv_codes)

    type_pub = raw.get("typePublicatie")
    if isinstance(type_pub, dict):
        type_pub = type_pub.get("omschrijving", "")

    type_opr = raw.get("typeOpdracht")
    if isinstance(type_opr, dict):
        type_opr = type_opr.get("omschrijving", "")

    procedure = raw.get("procedure")
    if isinstance(procedure, dict):
        procedure = procedure.get("omschrijving", "")

    link = raw.get("link")
    if isinstance(link, dict):
        link = link.get("href", "")

    return TenderSummary(
        publicatie_id=str(raw.get("publicatieId", "")),
        naam=naam,
        opdrachtgever=raw.get("opdrachtgeverNaam", ""),
        publicatie_datum=raw.get("publicatieDatum"),
        sluitings_datum=raw.get("sluitingsDatum"),
        type_publicatie=type_pub,
        type_opdracht=type_opr,
        procedure=procedure,
        beschrijving=beschrijving,
        europees=raw.get("europees", False),
        cpv_codes=raw.get("cpvCodes", []),
        relevance_score=scoring["score"],
        relevance_level=scoring["level"],
        matched_keywords=scoring["matched_keywords"],
        link=link,
    )


async def _ensure_cache() -> str:
    """Refresh cache if stale. Returns source label."""
    if is_cache_fresh():
        return "cache"
    logger.info("Cache stale — fetching from TenderNed...")
    tenders = await discover_it_tenders()
    upsert_tenders(tenders)
    logger.info("Cached %d IT-relevant tenders", len(tenders))
    return "tenderned_api"


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/v1/discover", response_model=DiscoverResponse)
async def discover(
    min_score: int = Query(0, ge=0, le=100, description="Minimum relevance score"),
    level: Optional[str] = Query(None, description="Filter by relevance level: hoog, midden, laag"),
):
    """Discover IT/MSP tenders — fetches fresh data if cache is stale."""
    source = await _ensure_cache()
    raw_tenders = get_all_tenders()
    tenders = [_format_tender(t) for t in raw_tenders]

    if min_score > 0:
        tenders = [t for t in tenders if t.relevance_score >= min_score]
    if level:
        tenders = [t for t in tenders if t.relevance_level == level.lower()]

    tenders.sort(key=lambda t: t.relevance_score, reverse=True)

    return DiscoverResponse(
        status="ok",
        fetched_from=source,
        tender_count=len(tenders),
        timestamp=datetime.now(timezone.utc).isoformat(),
        tenders=tenders,
    )


@app.get("/api/v1/tenders", response_model=List[TenderSummary])
async def list_tenders(
    min_score: int = Query(0, ge=0, le=100),
    level: Optional[str] = Query(None),
    type_opdracht: Optional[str] = Query(None, description="Filter: Diensten, Leveringen, Werken"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List cached tenders with filtering and pagination."""
    await _ensure_cache()
    raw = get_all_tenders()
    tenders = [_format_tender(t) for t in raw]

    if min_score > 0:
        tenders = [t for t in tenders if t.relevance_score >= min_score]
    if level:
        tenders = [t for t in tenders if t.relevance_level == level.lower()]
    if type_opdracht:
        tenders = [t for t in tenders if t.type_opdracht and type_opdracht.lower() in t.type_opdracht.lower()]

    tenders.sort(key=lambda t: t.relevance_score, reverse=True)
    return tenders[offset : offset + limit]


@app.get("/api/v1/tenders/{publication_id}", response_model=TenderSummary)
async def get_tender(publication_id: str):
    """Get a single tender by publication ID. Fetches from API if not cached."""
    raw = get_tender_by_id(publication_id)
    if not raw:
        detail = await fetch_detail(publication_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Tender niet gevonden")
        raw = detail
    return _format_tender(raw)


@app.get("/api/v1/stats", response_model=StatsResponse)
async def stats():
    """Statistics about cached tenders."""
    await _ensure_cache()
    raw = get_all_tenders()
    tenders = [_format_tender(t) for t in raw]

    by_relevance = {"hoog": 0, "midden": 0, "laag": 0}
    by_type = {}
    by_procedure = {}

    for t in tenders:
        by_relevance[t.relevance_level] = by_relevance.get(t.relevance_level, 0) + 1
        if t.type_opdracht:
            by_type[t.type_opdracht] = by_type.get(t.type_opdracht, 0) + 1
        if t.procedure:
            by_procedure[t.procedure] = by_procedure.get(t.procedure, 0) + 1

    return StatsResponse(
        total_tenders=len(tenders),
        by_relevance=by_relevance,
        by_type_opdracht=by_type,
        by_procedure=by_procedure,
        cache=get_cache_stats(),
    )


@app.get("/api/v1/cpv-codes", response_model=CpvListResponse)
async def list_cpv_codes():
    """List all 37 IT/MSP-relevant CPV codes used for filtering."""
    codes = [CpvCode(code=k, description=v) for k, v in CPV_CODES.items()]
    return CpvListResponse(count=len(codes), cpv_codes=codes)


@app.post("/api/v1/refresh")
async def refresh_cache():
    """Force refresh the cache from TenderNed, ignoring TTL."""
    logger.info("Manual cache refresh triggered")
    tenders = await discover_it_tenders()
    count = upsert_tenders(tenders)
    return {
        "status": "ok",
        "refreshed_tenders": count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/")
async def root():
    return {
        "app": "TenderAgent MSP",
        "version": "1.0.0",
        "description": "Nederlandse IT-aanbestedingen discovery API",
        "endpoints": [
            "/api/v1/discover",
            "/api/v1/tenders",
            "/api/v1/tenders/{id}",
            "/api/v1/stats",
            "/api/v1/cpv-codes",
            "/api/v1/refresh (POST)",
        ],
        "docs": "/docs",
    }
