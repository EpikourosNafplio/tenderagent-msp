"""TenderAgent MSP — FastAPI app for Dutch IT tender discovery."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
from .segments import (
    classify_opdrachtgever,
    detect_certifications,
    detect_segments,
    detect_signals,
    estimate_value,
    get_expected_requirements,
    score_msp_fit,
)
from .historie import is_historie_loaded, query_gunningshistorie, query_herhalingspatronen, query_vooraankondigingen
from .tenderned import discover_it_tenders, fetch_detail

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Database initialized")
    if is_historie_loaded():
        logger.info("Gunningshistorie dataset loaded")
    else:
        logger.info("Gunningshistorie dataset not found — historie endpoints will return empty results")
    yield


app = FastAPI(
    title="TenderAgent MSP",
    description="Nederlandse IT-aanbestedingen discovery API voor MSP's",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    segments: List[str] = []
    certifications: List[Dict] = []
    opdrachtgever_type: str = "OVERIG"
    expected_requirements: List[Dict] = []
    msp_fit_score: int = 0
    msp_fit_level: str = "Niet MSP"
    geschatte_waarde: Optional[Dict] = None
    signalen: List[Dict] = []
    gunningshistorie: List[Dict] = []
    waarde_bron: Optional[str] = None
    link: Optional[str] = None


class GunningshistorieResponse(BaseModel):
    opdrachtgever: str
    aantal: int
    resultaten: List[Dict]


class Vooraankondiging(BaseModel):
    opdrachtgever: str
    opdrachtgever_type: str
    beschrijving: str
    publicatiedatum: str
    type: str
    cpv_codes: List[str] = []
    segmenten: List[str] = []
    tenderned_kenmerk: Optional[str] = None


class Herhalingspatroon(BaseModel):
    opdrachtgever: str
    beschrijving_vorig: str
    gunningsdatum_vorig: str
    gegunde_partij: Optional[str] = None
    geraamde_waarde: Optional[float] = None
    verwachte_heraanbesteding: str
    status: str
    segmenten: List[str] = []


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

    segments = detect_segments(naam, beschrijving, cpv_codes)
    certifications = detect_certifications(naam, beschrijving)
    opdrachtgever_naam = raw.get("opdrachtgeverNaam", "")
    og_type = classify_opdrachtgever(opdrachtgever_naam)
    expected_reqs = get_expected_requirements(opdrachtgever_naam, segments)
    msp_fit = score_msp_fit(naam, beschrijving, type_opr, og_type, segments)
    europees = raw.get("europees", False)
    geschatte_waarde = estimate_value(europees, type_opr, og_type, segments, naam, beschrijving, raw_tender=raw)
    signalen = detect_signals(
        naam, beschrijving, opdrachtgever_naam, og_type, type_opr,
        europees, segments, certifications, expected_reqs, geschatte_waarde,
        sluitings_datum=raw.get("sluitingsDatum"),
        msp_fit_score=msp_fit["score"],
    )
    historie = query_gunningshistorie(opdrachtgever_naam, limit=5)

    return TenderSummary(
        publicatie_id=str(raw.get("publicatieId", "")),
        naam=naam,
        opdrachtgever=opdrachtgever_naam,
        publicatie_datum=raw.get("publicatieDatum"),
        sluitings_datum=raw.get("sluitingsDatum"),
        type_publicatie=type_pub,
        type_opdracht=type_opr,
        procedure=procedure,
        beschrijving=beschrijving,
        europees=europees,
        cpv_codes=raw.get("cpvCodes", []),
        relevance_score=scoring["score"],
        relevance_level=scoring["level"],
        matched_keywords=scoring["matched_keywords"],
        segments=segments,
        certifications=certifications,
        opdrachtgever_type=og_type,
        expected_requirements=expected_reqs,
        msp_fit_score=msp_fit["score"],
        msp_fit_level=msp_fit["level"],
        geschatte_waarde=geschatte_waarde,
        signalen=signalen,
        gunningshistorie=historie,
        waarde_bron=geschatte_waarde.get("waarde_bron"),
        link=link,
    )


def _deduplicate(tenders: list) -> list:
    """Deduplicate tenders by naam + opdrachtgever, keeping highest score."""
    seen: dict = {}
    for t in tenders:
        key = (t.naam.lower().strip(), t.opdrachtgever.lower().strip())
        if key not in seen or t.relevance_score > seen[key].relevance_score:
            seen[key] = t
    return list(seen.values())


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
    tenders = _deduplicate([_format_tender(t) for t in raw_tenders])

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
    alleen_signalen: bool = Query(False, description="Alleen tenders met signalen"),
    alleen_open: bool = Query(False, description="Alleen open tenders"),
    zoekterm: Optional[str] = Query(None, description="Vrije zoekterm"),
    sorteer: Optional[str] = Query(None, description="Sorteer: msp_fit, relevantie, waarde, signalen"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List cached tenders with filtering and pagination."""
    await _ensure_cache()
    raw = get_all_tenders()
    tenders = _deduplicate([_format_tender(t) for t in raw])

    if min_score > 0:
        tenders = [t for t in tenders if t.relevance_score >= min_score]
    if level:
        tenders = [t for t in tenders if t.relevance_level == level.lower()]
    if type_opdracht:
        tenders = [t for t in tenders if t.type_opdracht and type_opdracht.lower() in t.type_opdracht.lower()]
    if alleen_signalen:
        tenders = [t for t in tenders if t.signalen]
    if alleen_open:
        now = datetime.now(timezone.utc).isoformat()
        tenders = [t for t in tenders if t.sluitings_datum and t.sluitings_datum >= now]
    if zoekterm:
        zl = zoekterm.lower()
        tenders = [t for t in tenders if zl in t.naam.lower() or zl in (t.beschrijving or "").lower() or zl in t.opdrachtgever.lower()]

    if sorteer == "msp_fit":
        tenders.sort(key=lambda t: (-t.msp_fit_score, -t.relevance_score))
    elif sorteer == "waarde":
        tenders.sort(key=lambda t: (-((t.geschatte_waarde or {}).get("max_value") or 0), -t.msp_fit_score))
    elif sorteer == "signalen":
        tenders.sort(key=lambda t: (-len(t.signalen), -t.msp_fit_score))
    else:
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


@app.get("/api/v1/gunningshistorie/{opdrachtgever}", response_model=GunningshistorieResponse)
async def get_gunningshistorie(opdrachtgever: str):
    """Get gunningshistorie for a specific opdrachtgever."""
    resultaten = query_gunningshistorie(opdrachtgever)
    return GunningshistorieResponse(
        opdrachtgever=opdrachtgever,
        aantal=len(resultaten),
        resultaten=resultaten,
    )


@app.get("/api/v1/herhalingspatronen", response_model=List[Herhalingspatroon])
async def get_herhalingspatronen():
    """Get herhalingspatronen — ICT contracts likely to be re-tendered."""
    rows = query_herhalingspatronen()
    result = []
    for r in rows:
        gd = r.get("datum_gunning", "")
        try:
            d = datetime.fromisoformat(gd[:10]) if gd else None
            verwacht = f"{d.year + 3}-{d.year + 5}" if d else "onbekend"
        except (ValueError, TypeError):
            verwacht = "onbekend"
        result.append(Herhalingspatroon(
            opdrachtgever=r.get("aanbestedende_dienst", ""),
            beschrijving_vorig=r.get("beschrijving", ""),
            gunningsdatum_vorig=gd,
            gegunde_partij=r.get("gegunde_ondernemer"),
            geraamde_waarde=r.get("geraamde_waarde"),
            verwachte_heraanbesteding=verwacht,
            status="Verwacht",
            segmenten=detect_segments(
                r.get("aanbestedende_dienst", ""),
                r.get("beschrijving", ""),
                [],
            ),
        ))
    return result


@app.get("/api/v1/vooraankondigingen", response_model=List[Vooraankondiging])
async def get_vooraankondigingen():
    """Get vooraankondigingen, marktconsultaties, and vrijwillige transparantie."""
    rows = query_vooraankondigingen()
    result = []
    for r in rows:
        og_naam = r.get("aanbestedende_dienst", "")
        result.append(Vooraankondiging(
            opdrachtgever=og_naam,
            opdrachtgever_type=classify_opdrachtgever(og_naam),
            beschrijving=r.get("beschrijving", ""),
            publicatiedatum=r.get("publicatiedatum", ""),
            type=r.get("publicatie_soort", ""),
            cpv_codes=[c.strip() for c in (r.get("cpv_codes") or "").split(",") if c.strip()],
            segmenten=detect_segments(og_naam, r.get("beschrijving", ""), []),
            tenderned_kenmerk=r.get("tenderned_kenmerk"),
        ))
    return result


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Web dashboard for TenderAgent MSP."""
    return """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TenderAgent MSP — Dashboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f5f7fa; color: #1a1a2e; line-height: 1.5; }
  .container { max-width: 1440px; margin: 0 auto; padding: 24px; }
  header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin-bottom: 24px; }
  header h1 { font-size: 1.6rem; font-weight: 700; color: #0f172a; }
  header h1 span { color: #3b82f6; }
  .header-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .meta { font-size: 0.82rem; color: #64748b; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.72rem; font-weight: 600; white-space: nowrap; }
  .badge-hoog  { background: #dcfce7; color: #166534; }
  .badge-midden { background: #fff7ed; color: #9a3412; }
  .badge-laag  { background: #f1f5f9; color: #64748b; }
  /* Segment badge colors */
  .seg-werkplek { background: #dbeafe; color: #1e40af; }
  .seg-cloud { background: #ede9fe; color: #5b21b6; }
  .seg-cyber { background: #fee2e2; color: #991b1b; }
  .seg-netwerk { background: #ccfbf1; color: #115e59; }
  .seg-applicatie { background: #ffedd5; color: #9a3412; }
  .seg-data { background: #d1fae5; color: #065f46; }
  .seg-fullservice { background: #fef3c7; color: #92400e; }
  /* Certification badge colors */
  .cert-security { background: #fee2e2; color: #991b1b; }
  .cert-quality { background: #dbeafe; color: #1e40af; }
  .cert-social { background: #d1fae5; color: #065f46; }
  .cert-other { background: #f1f5f9; color: #475569; }
  .cert-implied { opacity: 0.65; font-style: italic; }
  /* Expected requirement levels */
  .req-verplicht { font-weight: 700; }
  .req-waarschijnlijk { opacity: 0.85; }
  .req-gebruikelijk, .req-mogelijk { opacity: 0.6; border: 1px solid currentColor; background: transparent !important; }
  .req-info { display: inline-block; width: 15px; height: 15px; border-radius: 50%; background: #e2e8f0; color: #64748b; font-size: 0.65rem; text-align: center; line-height: 15px; cursor: help; margin-left: 4px; vertical-align: middle; }
  /* MSP-fit badges */
  .msp-relevant { background: #dcfce7; color: #166534; }
  .msp-mogelijk { background: #fef9c3; color: #854d0e; }
  .msp-niet { background: #fee2e2; color: #991b1b; }
  .sort-toggle { font-size: 0.78rem; color: #3b82f6; cursor: pointer; text-decoration: underline; background: none; border: none; padding: 0; font-weight: 500; }
  .controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; }
  .controls label { font-size: 0.82rem; font-weight: 500; color: #475569; }
  select, input[type="text"] { padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 0.82rem; background: #fff; color: #1e293b; }
  select:focus, input:focus { outline: none; border-color: #3b82f6; box-shadow: 0 0 0 2px rgba(59,130,246,.15); }
  button { padding: 8px 18px; border: none; border-radius: 6px; font-size: 0.85rem; font-weight: 600; cursor: pointer; transition: background .15s; }
  .btn-primary { background: #3b82f6; color: #fff; }
  .btn-primary:hover { background: #2563eb; }
  .btn-primary:disabled { background: #93c5fd; cursor: wait; }
  .stats-bar { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
  .stat-card { background: #fff; border-radius: 8px; padding: 14px 20px; box-shadow: 0 1px 3px rgba(0,0,0,.06); min-width: 120px; }
  .stat-card .num { font-size: 1.6rem; font-weight: 700; }
  .stat-card .label { font-size: 0.78rem; color: #64748b; text-transform: uppercase; letter-spacing: .04em; }
  .stat-hoog .num  { color: #16a34a; }
  .stat-midden .num { color: #ea580c; }
  .stat-laag .num  { color: #94a3b8; }
  .table-wrap { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  thead { background: #f8fafc; }
  th { padding: 10px 12px; text-align: left; font-size: 0.75rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .04em; border-bottom: 2px solid #e2e8f0; white-space: nowrap; }
  td { padding: 10px 12px; font-size: 0.85rem; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  tr.row-hoog  { border-left: 3px solid #22c55e; }
  tr.row-midden { border-left: 3px solid #f97316; }
  tr.row-laag  { border-left: 3px solid #cbd5e1; }
  tr:hover { background: #f8fafc; }
  .tender-naam { font-weight: 500; color: #0f172a; max-width: 320px; }
  .tender-opdrachtgever { color: #475569; max-width: 180px; }
  .score-bar { display: flex; align-items: center; gap: 6px; }
  .score-fill { height: 6px; border-radius: 3px; }
  .score-hoog  .score-fill { background: #22c55e; }
  .score-midden .score-fill { background: #f97316; }
  .score-laag  .score-fill { background: #cbd5e1; }
  .score-num { font-weight: 600; font-size: 0.82rem; min-width: 28px; text-align: right; }
  a.link-ext { color: #3b82f6; text-decoration: none; font-weight: 500; }
  a.link-ext:hover { text-decoration: underline; }
  .empty { text-align: center; padding: 48px; color: #94a3b8; }
  .spinner { display: inline-block; width: 16px; height: 16px; border: 2px solid #93c5fd; border-top-color: #fff; border-radius: 50%; animation: spin .6s linear infinite; vertical-align: middle; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .toast { position: fixed; bottom: 24px; right: 24px; background: #0f172a; color: #fff; padding: 12px 20px; border-radius: 8px; font-size: 0.85rem; opacity: 0; transform: translateY(10px); transition: all .3s; z-index: 99; }
  .toast.show { opacity: 1; transform: translateY(0); }
  .tags { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; }
  .kw { background: #eff6ff; color: #1d4ed8; padding: 1px 7px; border-radius: 4px; font-size: 0.7rem; }
  .certs { display: flex; flex-wrap: wrap; gap: 3px; }
  /* Value estimation */
  .waarde { font-weight: 600; font-size: 0.82rem; white-space: nowrap; }
  .conf-hoog { color: #166534; }
  .conf-midden { color: #9a3412; }
  .conf-laag { color: #94a3b8; }
  /* Signal icons */
  .signal { display: inline-flex; align-items: center; gap: 3px; padding: 2px 8px; border-radius: 6px; font-size: 0.7rem; font-weight: 600; white-space: nowrap; cursor: help; margin: 1px 0; }
  .signal-warning { background: #fff7ed; color: #c2410c; border: 1px solid #fed7aa; }
  .signal-puzzle { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }
  .signal-check { background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }
  .signals { display: flex; flex-direction: column; gap: 2px; }
  @media (max-width: 768px) {
    .container { padding: 12px; }
    header { flex-direction: column; align-items: flex-start; }
    table { font-size: 0.78rem; }
    td, th { padding: 8px 8px; }
    .tender-naam, .tender-opdrachtgever { max-width: none; }
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1><span>TenderAgent</span> MSP</h1>
    <div class="header-right">
      <span class="meta" id="lastUpdate">Laden...</span>
      <button class="btn-primary" id="btnRefresh" onclick="doRefresh()">Refresh data</button>
    </div>
  </header>

  <div class="stats-bar" id="statsBar"></div>

  <div class="controls">
    <label for="filterStatus">Status:</label>
    <select id="filterStatus" onchange="renderTable()">
      <option value="open" selected>Open tenders</option>
      <option value="marktconsultatie">Marktconsultaties</option>
      <option value="gegund">Gegund</option>
      <option value="alles">Alles</option>
    </select>
    <label for="filterLevel">Relevantie:</label>
    <select id="filterLevel" onchange="renderTable()">
      <option value="">Alle niveaus</option>
      <option value="hoog">Hoog</option>
      <option value="midden">Midden</option>
      <option value="hoog,midden" selected>Hoog + Midden</option>
      <option value="laag">Laag</option>
    </select>
    <label for="filterSegment">Segment:</label>
    <select id="filterSegment" onchange="renderTable()">
      <option value="">Alle segmenten</option>
      <option value="Werkplek">Werkplek</option>
      <option value="Cloud">Cloud & Hosting</option>
      <option value="Cyber">Cybersecurity</option>
      <option value="Netwerk">Netwerk</option>
      <option value="Applicatie">Applicatiebeheer</option>
      <option value="Data">Data & BI</option>
      <option value="Full-service">Full-service</option>
    </select>
    <label for="filterCert">Vereiste:</label>
    <select id="filterCert" onchange="renderTable()">
      <option value="">Alle vereisten</option>
      <option value="ISO 27001">ISO 27001</option>
      <option value="ISO 9001">ISO 9001</option>
      <option value="NEN 7510">NEN 7510</option>
      <option value="BIO">BIO</option>
      <option value="DigiD">DigiD</option>
      <option value="ISAE 3402">ISAE 3402</option>
      <option value="SOC 2">SOC 2</option>
      <option value="NIS2">NIS2</option>
      <option value="PSO">PSO</option>
      <option value="SROI">SROI</option>
      <option value="AVG/DPIA">AVG/DPIA</option>
      <option value="ISAE 3402">ISAE 3402</option>
    </select>
    <label for="filterType">Type:</label>
    <select id="filterType" onchange="renderTable()">
      <option value="">Alle typen</option>
      <option value="Diensten">Diensten</option>
      <option value="Leveringen">Leveringen</option>
      <option value="Werken">Werken</option>
    </select>
    <label for="filterSignaal">Signalen:</label>
    <select id="filterSignaal" onchange="renderTable()">
      <option value="">Alle</option>
      <option value="any">Alleen met signalen</option>
      <option value="msp-kans">MSP-kansen</option>
      <option value="disproportioneel">Disproportioneel</option>
      <option value="opvallend">Opvallend</option>
    </select>
    <input type="text" id="searchBox" placeholder="Zoek..." oninput="renderTable()" style="min-width:160px;">
    <button class="sort-toggle" id="sortToggle" onclick="toggleSort()">Sorteer: MSP-fit</button>
    <span class="meta" id="resultCount"></span>
  </div>

  <div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>Naam</th>
        <th>Segmenten</th>
        <th>Opdrachtgever</th>
        <th>MSP-fit</th>
        <th>Score</th>
        <th>Waarde</th>
        <th>Signalen</th>
        <th>Vereisten <span class="req-info" title="Verwachte vereisten op basis van opdrachtgevertype en regelgeving. Check altijd de aanbestedingsstukken voor de definitieve eisen.">i</span></th>
        <th>Type</th>
        <th>Sluitingsdatum</th>
        <th>Link</th>
      </tr>
    </thead>
    <tbody id="tenderBody">
      <tr><td colspan="11" class="empty">Tenders laden...</td></tr>
    </tbody>
  </table>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const SEG_CSS = {
  'Werkplek': 'seg-werkplek', 'Cloud': 'seg-cloud', 'Cyber': 'seg-cyber',
  'Netwerk': 'seg-netwerk', 'Applicatie': 'seg-applicatie',
  'Data': 'seg-data', 'Full-service': 'seg-fullservice'
};
const CERT_CSS = { security: 'cert-security', quality: 'cert-quality', social: 'cert-social', other: 'cert-other' };

function mspClass(level) {
  if (level === 'MSP-relevant') return 'msp-relevant';
  if (level === 'Mogelijk relevant') return 'msp-mogelijk';
  return 'msp-niet';
}

function segClass(label) {
  for (const [key, cls] of Object.entries(SEG_CSS)) {
    if (label.toLowerCase().includes(key.toLowerCase())) return cls;
  }
  return 'seg-fullservice';
}

let allTenders = [];
let sortMode = 0; // 0=MSP-fit, 1=Relevantie, 2=Waarde
const SORT_LABELS = ['Sorteer: MSP-fit', 'Sorteer: Relevantie', 'Sorteer: Waarde'];

function getMaxValue(t) {
  return (t.geschatte_waarde && t.geschatte_waarde.max_value) || 0;
}

function sortTenders() {
  if (sortMode === 0) {
    allTenders.sort((a, b) => b.msp_fit_score - a.msp_fit_score || b.relevance_score - a.relevance_score);
  } else if (sortMode === 1) {
    allTenders.sort((a, b) => b.relevance_score - a.relevance_score || b.msp_fit_score - a.msp_fit_score);
  } else {
    allTenders.sort((a, b) => getMaxValue(b) - getMaxValue(a) || b.msp_fit_score - a.msp_fit_score);
  }
}

function toggleSort() {
  sortMode = (sortMode + 1) % 3;
  document.getElementById('sortToggle').textContent = SORT_LABELS[sortMode];
  sortTenders();
  renderTable();
}

function renderWaarde(gw) {
  if (!gw || !gw.display) return '\\u2014';
  var conf = gw.confidence || 'laag';
  return '<span class="waarde conf-' + conf + '" title="Schatting (betrouwbaarheid: ' + conf + ')">' + escHtml(gw.display) + '</span>';
}

function renderSignalen(signalen) {
  if (!signalen || !signalen.length) return '';
  var ICON_MAP = { warning: '\\u26a0\\ufe0f', puzzle: '\\ud83e\\udde9', check: '\\u2705' };
  return '<div class="signals">' + signalen.map(function(s) {
    var iconCls = 'signal-' + s.icon;
    var icon = ICON_MAP[s.icon] || '';
    return '<span class="signal ' + iconCls + '" title="' + escHtml(s.detail) + '">' + icon + ' ' + escHtml(s.label) + '</span>';
  }).join('') + '</div>';
}

async function loadTenders() {
  try {
    const res = await fetch('/api/v1/tenders?limit=500');
    if (!res.ok) throw new Error(res.statusText);
    allTenders = await res.json();
    sortTenders();
    updateStats();
    renderTable();
    document.getElementById('lastUpdate').textContent =
      'Laatste update: ' + new Date().toLocaleString('nl-NL');
  } catch (e) {
    document.getElementById('tenderBody').innerHTML =
      '<tr><td colspan="11" class="empty">Fout bij laden: ' + e.message + '</td></tr>';
  }
}

function updateStats() {
  const counts = { hoog: 0, midden: 0, laag: 0 };
  allTenders.forEach(t => counts[t.relevance_level] = (counts[t.relevance_level] || 0) + 1);
  document.getElementById('statsBar').innerHTML =
    '<div class="stat-card"><div class="num">' + allTenders.length + '</div><div class="label">Totaal</div></div>' +
    '<div class="stat-card stat-hoog"><div class="num">' + counts.hoog + '</div><div class="label">Hoog</div></div>' +
    '<div class="stat-card stat-midden"><div class="num">' + counts.midden + '</div><div class="label">Midden</div></div>' +
    '<div class="stat-card stat-laag"><div class="num">' + counts.laag + '</div><div class="label">Laag</div></div>';
}

function isGegund(t) {
  const tp = (t.type_publicatie || '').toLowerCase();
  return tp.includes('gegunde') || tp.includes('beëindiging') || tp.includes('beeindiging');
}

function isMarktconsultatie(t) {
  return (t.procedure || '').toLowerCase().includes('marktconsultatie');
}

function isOpen(t) {
  if (isGegund(t) || isMarktconsultatie(t)) return false;
  if (!t.sluitings_datum) return false;
  return new Date(t.sluitings_datum) >= new Date(new Date().toDateString());
}

function renderTable() {
  const statusFilter = document.getElementById('filterStatus').value;
  const levelFilter = document.getElementById('filterLevel').value;
  const segFilter = document.getElementById('filterSegment').value;
  const certFilter = document.getElementById('filterCert').value;
  const typeFilter = document.getElementById('filterType').value;
  const signaalFilter = document.getElementById('filterSignaal').value;
  const search = document.getElementById('searchBox').value.toLowerCase();
  const levels = levelFilter ? levelFilter.split(',') : [];

  let filtered = allTenders.filter(t => {
    if (statusFilter === 'open' && !isOpen(t)) return false;
    if (statusFilter === 'marktconsultatie' && !isMarktconsultatie(t)) return false;
    if (statusFilter === 'gegund' && !isGegund(t)) return false;
    if (levels.length && !levels.includes(t.relevance_level)) return false;
    if (segFilter && !(t.segments || []).some(s => s.toLowerCase().includes(segFilter.toLowerCase()))) return false;
    if (certFilter) {
      const hasCert = (t.certifications || []).some(c => c.name === certFilter);
      const hasExpected = (t.expected_requirements || []).some(r => r.name === certFilter);
      if (!hasCert && !hasExpected) return false;
    }
    if (typeFilter && (!t.type_opdracht || !t.type_opdracht.toLowerCase().includes(typeFilter.toLowerCase()))) return false;
    if (signaalFilter) {
      const sigs = t.signalen || [];
      if (signaalFilter === 'any' && sigs.length === 0) return false;
      if (signaalFilter !== 'any' && !sigs.some(s => s.type === signaalFilter)) return false;
    }
    if (search && !t.naam.toLowerCase().includes(search) && !t.opdrachtgever.toLowerCase().includes(search)) return false;
    return true;
  });

  document.getElementById('resultCount').textContent = filtered.length + ' resultaten';

  if (filtered.length === 0) {
    document.getElementById('tenderBody').innerHTML =
      '<tr><td colspan="11" class="empty">Geen tenders gevonden voor dit filter.</td></tr>';
    return;
  }

  const rows = filtered.map(t => {
    const lvl = t.relevance_level || 'laag';
    const score = t.relevance_score || 0;
    const datum = t.sluitings_datum ? new Date(t.sluitings_datum).toLocaleDateString('nl-NL') : '\\u2014';
    const link = t.link
      ? '<a class="link-ext" href="' + escHtml(t.link) + '" target="_blank" rel="noopener">Bekijk &#8599;</a>'
      : '\\u2014';
    const segs = (t.segments || []).map(s => '<span class="badge ' + segClass(s) + '">' + escHtml(s) + '</span>').join(' ');
    const explicitCerts = (t.certifications || []).map(c => '<span class="badge ' + (CERT_CSS[c.category] || 'cert-other') + (c.implied ? ' cert-implied' : '') + '">' + escHtml(c.name) + '</span>');
    const expectedReqs = (t.expected_requirements || []).map(r => '<span class="badge ' + (CERT_CSS[r.category] || 'cert-other') + ' req-' + r.level + '" title="' + escHtml(r.level) + '">' + escHtml(r.name) + '</span>');
    const certs = explicitCerts.concat(expectedReqs).join(' ');
    const kws = (t.matched_keywords || []).slice(0, 4).map(k => '<span class="kw">' + escHtml(k) + '</span>').join('');
    return '<tr class="row-' + lvl + '">' +
      '<td><div class="tender-naam">' + escHtml(t.naam) + '</div>' + (kws ? '<div class="tags">' + kws + '</div>' : '') + '</td>' +
      '<td><div class="tags">' + (segs || '\\u2014') + '</div></td>' +
      '<td class="tender-opdrachtgever">' + escHtml(t.opdrachtgever) + '</td>' +
      '<td><span class="badge ' + mspClass(t.msp_fit_level) + '">' + escHtml(t.msp_fit_level) + '</span><div class="meta" style="margin-top:2px">' + (t.msp_fit_score || 0) + ' pt</div></td>' +
      '<td><div class="score-bar score-' + lvl + '">' +
        '<span class="score-num">' + score + '</span>' +
        '<div class="score-fill" style="width:' + score + 'px;"></div>' +
      '</div><span class="badge badge-' + lvl + '">' + lvl + '</span></td>' +
      '<td>' + renderWaarde(t.geschatte_waarde) + '</td>' +
      '<td>' + renderSignalen(t.signalen) + '</td>' +
      '<td><div class="certs">' + (certs || '') + '</div></td>' +
      '<td>' + escHtml(t.type_opdracht || '\\u2014') + '</td>' +
      '<td>' + datum + '</td>' +
      '<td>' + link + '</td>' +
      '</tr>';
  });
  document.getElementById('tenderBody').innerHTML = rows.join('');
}

async function doRefresh() {
  const btn = document.getElementById('btnRefresh');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Refreshing...';
  try {
    const res = await fetch('/api/v1/refresh', { method: 'POST' });
    const data = await res.json();
    showToast('Refresh voltooid \\u2014 ' + data.refreshed_tenders + ' tenders bijgewerkt');
    await loadTenders();
  } catch (e) {
    showToast('Refresh mislukt: ' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh data';
  }
}

function showToast(msg) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3500);
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

loadTenders();
</script>
</body>
</html>"""
