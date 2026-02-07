"""TenderAgent MSP — FastAPI app for Dutch IT tender discovery."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
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
  .container { max-width: 1280px; margin: 0 auto; padding: 24px; }
  header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin-bottom: 24px; }
  header h1 { font-size: 1.6rem; font-weight: 700; color: #0f172a; }
  header h1 span { color: #3b82f6; }
  .header-right { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
  .meta { font-size: 0.82rem; color: #64748b; }
  .badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; }
  .badge-hoog  { background: #dcfce7; color: #166534; }
  .badge-midden { background: #fff7ed; color: #9a3412; }
  .badge-laag  { background: #f1f5f9; color: #64748b; }
  .controls { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
  .controls label { font-size: 0.85rem; font-weight: 500; color: #475569; }
  select, input[type="text"] { padding: 6px 12px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 0.85rem; background: #fff; color: #1e293b; }
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
  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.06); }
  thead { background: #f8fafc; }
  th { padding: 10px 14px; text-align: left; font-size: 0.78rem; font-weight: 600; color: #64748b; text-transform: uppercase; letter-spacing: .04em; border-bottom: 2px solid #e2e8f0; white-space: nowrap; }
  td { padding: 10px 14px; font-size: 0.88rem; border-bottom: 1px solid #f1f5f9; vertical-align: top; }
  tr:last-child td { border-bottom: none; }
  tr.row-hoog  { border-left: 3px solid #22c55e; }
  tr.row-midden { border-left: 3px solid #f97316; }
  tr.row-laag  { border-left: 3px solid #cbd5e1; }
  tr:hover { background: #f8fafc; }
  .tender-naam { font-weight: 500; color: #0f172a; max-width: 380px; }
  .tender-opdrachtgever { color: #475569; max-width: 200px; }
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
  .keywords { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
  .kw { background: #eff6ff; color: #1d4ed8; padding: 1px 7px; border-radius: 4px; font-size: 0.72rem; }
  @media (max-width: 768px) {
    .container { padding: 12px; }
    header { flex-direction: column; align-items: flex-start; }
    table { font-size: 0.8rem; }
    td, th { padding: 8px 10px; }
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
    <label for="filterLevel">Filter:</label>
    <select id="filterLevel" onchange="renderTable()">
      <option value="">Alle niveaus</option>
      <option value="hoog">Hoog</option>
      <option value="midden">Midden</option>
      <option value="hoog,midden" selected>Hoog + Midden</option>
      <option value="laag">Laag</option>
    </select>
    <label for="filterType">Type:</label>
    <select id="filterType" onchange="renderTable()">
      <option value="">Alle typen</option>
      <option value="Diensten">Diensten</option>
      <option value="Leveringen">Leveringen</option>
      <option value="Werken">Werken</option>
    </select>
    <input type="text" id="searchBox" placeholder="Zoek op naam of opdrachtgever..." oninput="renderTable()" style="min-width:220px;">
    <span class="meta" id="resultCount"></span>
  </div>

  <table>
    <thead>
      <tr>
        <th>Naam</th>
        <th>Opdrachtgever</th>
        <th>Score</th>
        <th>Type</th>
        <th>Sluitingsdatum</th>
        <th>TenderNed</th>
      </tr>
    </thead>
    <tbody id="tenderBody">
      <tr><td colspan="6" class="empty">Tenders laden...</td></tr>
    </tbody>
  </table>
</div>

<div class="toast" id="toast"></div>

<script>
let allTenders = [];

async function loadTenders() {
  try {
    const res = await fetch('/api/v1/tenders?limit=500');
    if (!res.ok) throw new Error(res.statusText);
    allTenders = await res.json();
    allTenders.sort((a, b) => b.relevance_score - a.relevance_score);
    updateStats();
    renderTable();
    document.getElementById('lastUpdate').textContent =
      'Laatste update: ' + new Date().toLocaleString('nl-NL');
  } catch (e) {
    document.getElementById('tenderBody').innerHTML =
      '<tr><td colspan="6" class="empty">Fout bij laden: ' + e.message + '</td></tr>';
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

function renderTable() {
  const levelFilter = document.getElementById('filterLevel').value;
  const typeFilter = document.getElementById('filterType').value;
  const search = document.getElementById('searchBox').value.toLowerCase();
  const levels = levelFilter ? levelFilter.split(',') : [];

  let filtered = allTenders.filter(t => {
    if (levels.length && !levels.includes(t.relevance_level)) return false;
    if (typeFilter && (!t.type_opdracht || !t.type_opdracht.toLowerCase().includes(typeFilter.toLowerCase()))) return false;
    if (search && !t.naam.toLowerCase().includes(search) && !t.opdrachtgever.toLowerCase().includes(search)) return false;
    return true;
  });

  document.getElementById('resultCount').textContent = filtered.length + ' resultaten';

  if (filtered.length === 0) {
    document.getElementById('tenderBody').innerHTML =
      '<tr><td colspan="6" class="empty">Geen tenders gevonden voor dit filter.</td></tr>';
    return;
  }

  const rows = filtered.map(t => {
    const lvl = t.relevance_level || 'laag';
    const score = t.relevance_score || 0;
    const datum = t.sluitings_datum ? new Date(t.sluitings_datum).toLocaleDateString('nl-NL') : '—';
    const link = t.link
      ? '<a class="link-ext" href="' + escHtml(t.link) + '" target="_blank" rel="noopener">Bekijk &#8599;</a>'
      : '—';
    const kws = (t.matched_keywords || []).slice(0, 5).map(k => '<span class="kw">' + escHtml(k) + '</span>').join('');
    return '<tr class="row-' + lvl + '">' +
      '<td><div class="tender-naam">' + escHtml(t.naam) + '</div>' + (kws ? '<div class="keywords">' + kws + '</div>' : '') + '</td>' +
      '<td class="tender-opdrachtgever">' + escHtml(t.opdrachtgever) + '</td>' +
      '<td><div class="score-bar score-' + lvl + '">' +
        '<span class="score-num">' + score + '</span>' +
        '<div class="score-fill" style="width:' + score + 'px;"></div>' +
      '</div><span class="badge badge-' + lvl + '">' + lvl + '</span></td>' +
      '<td>' + escHtml(t.type_opdracht || '—') + '</td>' +
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
    showToast('Refresh voltooid — ' + data.refreshed_tenders + ' tenders bijgewerkt');
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
