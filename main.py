"""
TenderAgent MSP v2 - IT-aanbestedingen voor Managed Service Providers

Features:
  - 7 MSP-segmenten met sterke/zwakke keyword-matching
  - Opdrachtgever-classificatie en afgeleide certificeringsvereisten
  - MSP-fit scoring (filtert applicatiesoftware vs. managed services)
  - Geschatte waarde (bandbreedte op basis van opdrachtgevertype + scope)
  - Spanning-detectie (disproportionele eisen, opvallende combi's, MSP-kansen)
  - Gunningshistorie uit TenderNed openbare dataset (SQLite)
  - Herhalingspatronen (verwachte heraanbestedingen)
  - Vooraankondigingen en marktconsultaties

Endpoints:
  /api/v1/discover              - Overzicht van alle endpoints
  /api/v1/tenders               - Actuele IT/MSP-relevante tenders
  /api/v1/tenders/{id}          - Tender detail + gunningshistorie
  /api/v1/stats                 - Statistieken
  /api/v1/cpv-codes             - Gemonitorde CPV-codes
  /api/v1/vooraankondigingen    - Vooraankondigingen en marktconsultaties
  /api/v1/herhalingspatronen    - Verwachte heraanbestedingen
  /api/v1/gunningshistorie/{opdrachtgever} - Historie per opdrachtgever

Gemaakt voor: Epikouros Trading & Consulting Company
"""

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, date
from typing import Optional
from pathlib import Path

import httpx
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuratie
# ---------------------------------------------------------------------------

TENDERNED_TNS = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"
TENDERNED_BASE = "https://www.tenderned.nl/aankondigingen/overzicht"
DB_PATH = Path(__file__).parent / "data" / "tenderned_historie.db"

# ---------------------------------------------------------------------------
# CPV-codes relevant voor MSP's / IT-dienstverleners
# ---------------------------------------------------------------------------

CPV_CODES_IT = {
    "72000000": "IT-diensten: adviezen, softwareontwikkeling, internet en ondersteuning",
    "72100000": "Advies inzake hardware",
    "72200000": "Softwareprogrammering en -advies",
    "72210000": "Programmering van softwarepakketten",
    "72220000": "Advies inzake systemen en technisch advies",
    "72230000": "Ontwikkeling van gebruikerspecifieke software",
    "72240000": "Systeemanalyse en programmering",
    "72250000": "Systeem- en ondersteuningsdiensten",
    "72260000": "Softwaregerelateerde diensten",
    "72300000": "Datadiensten",
    "72310000": "Gegevensverwerking",
    "72320000": "Databanken",
    "72400000": "Internetdiensten",
    "72500000": "Informaticadiensten",
    "72600000": "Diensten voor computerondersteuning en -advies",
    "72700000": "Computernetwerkdiensten",
    "72800000": "Computeraudit- en computertestdiensten",
    "72900000": "Computer-back-up en computercatalogusdiensten",
    "48000000": "Softwarepakketten en informatiesystemen",
    "48100000": "Branchespecifieke softwarepakketten",
    "48200000": "Software voor netwerken, internet en intranet",
    "48300000": "Software voor het aanmaken van documenten en dergelijke",
    "48400000": "Software voor zakelijke transacties en persoonlijke zaken",
    "48500000": "Communicatie- en multimediasoftware",
    "48600000": "Database- en besturingssoftware",
    "48700000": "Softwarehulpmiddelen",
    "48800000": "Informatiesystemen en servers",
    "48900000": "Diverse softwarepakketten en computersystemen",
    "30200000": "Computeruitrusting en -benodigdheden",
    "30210000": "Machines voor gegevensverwerking (hardware)",
    "30230000": "Computerapparatuur",
    "64200000": "Telecommunicatiediensten",
    "64210000": "Telefoon- en datatransmissiediensten",
    "64216000": "Elektronische berichten- en informatiediensten",
    "50300000": "Reparatie en onderhoud van computers en randapparatuur",
    "51600000": "Installatie van computers en kantooruitrusting",
}

# ---------------------------------------------------------------------------
# MSP-segmenten: sterke en zwakke keywords
# ---------------------------------------------------------------------------

MSP_SEGMENTS = {
    "Werkplek & Eindgebruikersbeheer": {
        "strong": [
            "werkplekbeheer", "workplace management", "endpoint management",
            "digitale werkomgeving", "DWR", "printbeheer", "multifunctional",
            "MFP", "modern workplace", "Microsoft 365", "M365", "Office 365",
            "servicedesk", "ITSM", "client management", "end user computing",
            "kantoorautomatisering", "repro",
        ],
        "weak": ["werkplek", "printer", "print", "desktop", "laptop", "telefonie"],
        "cpv": ["30200000", "30210000", "30230000", "50300000", "51600000"],
    },
    "Cloud & Hosting": {
        "strong": [
            "hosting", "IaaS", "PaaS", "cloudmigratie", "VMware",
            "virtualisatie", "compute", "storage", "backup",
            "disaster recovery", "datacenter", "datacentrum", "containerisatie",
            "hybride cloud", "private cloud", "public cloud",
        ],
        "weak": ["cloud", "SaaS", "Azure", "AWS", "migratie", "as a service"],
        "cpv": ["72400000", "72300000", "72900000", "48800000"],
    },
    "Cybersecurity & Informatiebeveiliging": {
        "strong": [
            "SOC", "SIEM", "SOAR", "penetratietest", "pentest",
            "vulnerability scan", "informatiebeveiliging", "cybersecurity",
            "security operations", "dreigingsanalyse", "incident response",
            "security monitoring",
        ],
        "weak": ["security", "beveiliging", "NIS2", "DORA", "BIO"],
        "cpv": ["72800000"],
    },
    "Netwerk & Connectiviteit": {
        "strong": [
            "SD-WAN", "LAN", "WAN", "firewall", "connectiviteit",
            "glasvezel", "wifi", "WLAN", "switching", "routing",
            "VPN", "netwerkbeheer", "netwerk infrastructuur",
        ],
        "weak": ["netwerk", "telecom", "VoIP", "unified communications"],
        "cpv": ["64200000", "64210000", "72700000"],
    },
    "Applicatiebeheer & Implementatie": {
        "strong": [
            "applicatiebeheer", "softwareimplementatie", "zaaksysteem",
            "servicemanagement", "ITSM", "ERP-implementatie",
            "CRM-implementatie", "document management", "DMS",
            "informatiebeheer", "maatwerk software",
        ],
        "weak": [
            "applicatie", "software", "platform", "portaal", "systeem",
            "ERP", "CRM", "HRM", "integratie", "API", "koppeling",
        ],
        "cpv": ["72200000", "72260000", "72230000", "48000000", "48100000"],
    },
    "Data & Business Intelligence": {
        "strong": [
            "datawarehouse", "business intelligence", "Power BI", "Tableau",
            "datafundament", "data-integratie", "ETL", "data analytics",
            "rapportage-omgeving", "dataverzameling",
        ],
        "weak": ["data", "BI", "analytics", "dashboard", "rapportage"],
        "cpv": ["72300000", "72310000", "48600000"],
    },
}

NEGATIVE_KEYWORDS = [
    "niet-iv", "niet-ict", "schoonmaak", "catering",
    "groenvoorziening", "bouwwerk", "sloopwerk",
    "speelgroep", "kinderopvang", "peutergroep",
]

# Hard-block: als de tender NAAM (niet beschrijving) een van deze bevat,
# is het geen IT-tender, ongeacht CPV of keywords in beschrijving.
NOT_IT_NAAM_KEYWORDS = [
    # Fysieke diensten
    "verhuisdiensten", "verhuizing", "schoonmaak", "catering",
    "pendeldiensten", "pendeldienst", "vervoerdiensten", "vervoerdienst",
    "reisorganisatiediensten", "reisorganisatie",
    # Groen / openbare ruimte
    "groenonderhoud", "groenvoorziening", "ruw gras", "bloemrijk gras",
    "watergangen", "openbare ruimte", "herinrichting",
    # Bouw / renovatie / vastgoed
    "bouwkundig onderhoud", "renovatie", "nieuwbouw", "herinrichting",
    "sportpark", "sportaccommodatie", "kindcentrum",
    "kavel op", "bestek",
    # Openbare verlichting
    "openbare verlichting", "straatverlichting",
    # Fysieke beveiliging
    "objectbeveiliging",
    # Deuren/fysiek onderhoud
    "deurdrangers", "schuifdeuren", "roldeuren", "slagbomen",
    # Afval/glas
    "verpakkingsglas", "afvoer en verwerking",
    # Zorg/sociaal fysiek
    "persoonsgebonden was", "wasgoed", "woningaanpassingen",
    "speelgroepen", "samenspeelgroepen",
    # Verzekering
    "car verzekering",
    # Foto/video
    "foto- en video", "fotografie en video",
    # Veiligheidsinspecties (fysiek, niet IT)
    "veiligheidsinspecties elektrische",
    # Verkeersregeltechniek
    "verkeersregeltechnische",
    # ANPR = verkeershandhaving, niet MSP
    "anpr-camera",
    # Logistiek/laadinfra
    "logistiek laadadvies", "laadadvies",
    "bedrijventerreinaanpak",
    # Raamovereenkomsten fysiek onderhoud
    "correctief bouwkundig",
    "raamovereenkomst onderhoud",
    # Civiel/natuur/spoor
    "ingenieursdiensten",
    "natuurherstel",
    "wissels",
    # Beleid/coördinatie/subsidie
    "bio-coalitie",
    "coördinatie en realisatie",
    # Milieu-vergunningen
    "vergunningverlening milieu",
    "meldingen en vergunningverlening",
]

APP_SOFTWARE_INDICATORS = [
    "salarisverwerking", "salarissoftware", "salaris applicatie", "salarissysteem",
    "e-hrm", "hrm-systeem", "hrm systeem", "personeelsinformatie",
    "woz-applicatie", "woz applicatie", "woz taxatie", "woz waardering",
    "financieel pakket", "financiele applicatie",
    "basisregistratie", "burgerzaken", "vergunningen",
    "klantvolgsysteem", "clientvolgsysteem", "cliëntvolgsysteem",
    "sociaal domein software", "jeugdhulp applicatie",
]

PHYSICAL_INFRA_INDICATORS = [
    "meettrein", "civiel", "graafwerk", "aanleg glasvezel",
    "straatverlichting", "verkeersregelinstallatie",
    "fysieke toegangscontrole", "tourniquets", "slagboom",
    "camerabewaking", "cctv", "installatie gebouw",
    "elektrotechnisch", "werktuigbouwkundig",
]

# ---------------------------------------------------------------------------
# Opdrachtgever-classificatie
# ---------------------------------------------------------------------------

OPDRACHTGEVER_PATTERNS = {
    "GEMEENTE": ["gemeente"],
    "GR": ["gemeenschappelijke regeling", "GR ", "samenwerkingsverband"],
    "PROVINCIE": ["provincie"],
    "WATERSCHAP": ["waterschap", "hoogheemraadschap", "wetterskip"],
    "RIJK": [
        "ministerie", "rijkswaterstaat", "RWS", "politie",
        "Defensie", "Justitie", "dienst uitvoering",
    ],
    "RIJK_VITAAL": ["ProRail", "Tennet", "Gasunie", "Rijkswaterstaat", "RWS"],
    "ZBO": [
        "UWV", "SVB", "DUO", "Belastingdienst", "RIVM", "RVO",
        "KNMI", "CBR", "IND", "Kadaster", "KvK",
        "Kamer van Koophandel", "CJIB", "NFI", "NVWA",
    ],
    "ZORG": [
        "ziekenhuis", "GGZ", "GGD", "zorggroep", "huisartsen",
        "verpleeghuis", "thuiszorg", "VVT", "gehandicaptenzorg",
    ],
    "ONDERWIJS": [
        "universiteit", "hogeschool", "ROC", "lyceum",
        "scholengemeenschap", "SURF", "mbo",
    ],
    "PUBLIEK_SOCIAAL": [
        "sociale werkvoorziening", "SW-bedrijf", "EMCO",
        "werkvoorzieningschap", "Ergon", "Patijnenburg",
    ],
}

VERWACHTE_VEREISTEN = {
    "GEMEENTE": {"BIO": "verplicht", "ISO 27001": "waarschijnlijk", "SROI": "gebruikelijk"},
    "GR": {"BIO": "verplicht", "ISO 27001": "waarschijnlijk", "SROI": "gebruikelijk"},
    "PROVINCIE": {"BIO": "verplicht", "ISO 27001": "waarschijnlijk"},
    "WATERSCHAP": {"BIO": "verplicht", "ISO 27001": "waarschijnlijk"},
    "RIJK": {"BIO": "verplicht", "ISO 27001": "waarschijnlijk", "DigiD": "mogelijk", "ISAE 3402": "mogelijk"},
    "RIJK_VITAAL": {"BIO": "verplicht", "ISO 27001": "waarschijnlijk", "ISAE 3402": "waarschijnlijk", "NIS2": "waarschijnlijk"},
    "ZBO": {"BIO": "verplicht", "ISO 27001": "waarschijnlijk", "DigiD": "mogelijk", "ISAE 3402": "mogelijk"},
    "ZORG": {"NEN 7510": "verplicht", "ISO 27001": "waarschijnlijk", "BIO": "mogelijk"},
    "ONDERWIJS": {"ISO 27001": "mogelijk"},
    "PUBLIEK_SOCIAAL": {"BIO": "waarschijnlijk", "PSO": "waarschijnlijk", "SROI": "gebruikelijk"},
}

CERT_KEYWORDS = {
    "ISO 27001": ["iso 27001", "iso27001", "iso-27001"],
    "ISO 9001": ["iso 9001", "iso9001", "iso-9001"],
    "ISO 14001": ["iso 14001", "iso14001", "iso-14001"],
    "NEN 7510": ["nen 7510", "nen7510", "nen-7510"],
    "ISAE 3402": ["isae 3402", "isae3402"],
    "SOC 2": ["soc 2", "soc2", "soc-2"],
    "BIO": ["baseline informatiebeveiliging", " bio "],
    "DigiD": ["digid"],
    "NIS2": ["nis2", "nis 2", "nis-2"],
    "DORA": [" dora "],
    "PSO": ["prestatieladder socialer ondernemen", " pso "],
    "CO2-prestatieladder": ["co2-prestatieladder", "co2 prestatieladder"],
    "SROI": ["sroi", "social return"],
}

# ---------------------------------------------------------------------------
# Pydantic modellen
# ---------------------------------------------------------------------------

class TenderSummary(BaseModel):
    id: str
    naam: str
    opdrachtgever: str
    opdrachtgever_type: str
    publicatie_datum: str
    type_publicatie: str
    type_opdracht: str
    procedure: str
    sluitingsdatum: Optional[str] = None
    dagen_tot_sluiting: Optional[int] = None
    europees: bool
    digitaal: bool
    beschrijving: str
    relevantie_score: Optional[float] = None
    relevantie_reden: Optional[list[str]] = None
    msp_fit: Optional[float] = None
    msp_fit_label: Optional[str] = None
    segmenten: list[str] = []
    verwachte_vereisten: dict[str, str] = {}
    expliciete_vereisten: list[str] = []
    geschatte_waarde_min: Optional[int] = None
    geschatte_waarde_max: Optional[int] = None
    waarde_bron: Optional[str] = None
    waarde_weergave: Optional[str] = None
    signalen: list[dict] = []
    gunningshistorie: list[dict] = []
    tenderned_url: str
    tsender_url: Optional[str] = None

class Vooraankondiging(BaseModel):
    opdrachtgever: str
    opdrachtgever_type: str
    beschrijving: str
    publicatiedatum: str
    type: str
    cpv_codes: list[str] = []
    segmenten: list[str] = []
    tenderned_kenmerk: Optional[str] = None

class Herhalingspatroon(BaseModel):
    opdrachtgever: str
    beschrijving_vorig: str
    gunningsdatum_vorig: str
    gegunde_partij: Optional[str] = None
    geraamde_waarde: Optional[float] = None
    verwachte_heraanbesteding: str
    status: str
    segmenten: list[str] = []

class DiscoverResponse(BaseModel):
    service: str
    version: str
    description: str
    endpoints: dict
    data_source: str
    cpv_codes_monitored: int
    msp_segments: int
    dataset_loaded: bool
    last_updated: str

class StatsResponse(BaseModel):
    totaal_tenders: int
    msp_relevant: int
    mogelijk_relevant: int
    niet_msp: int
    europees: int
    nationaal: int
    gemiddelde_dagen_tot_sluiting: Optional[float]
    top_opdrachtgevers: list[dict]
    segmenten_verdeling: dict[str, int]
    tenders_met_signalen: int
    datum: str

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TenderAgent MSP",
    description="AI-gestuurde API voor IT-aanbestedingen in Nederland, "
                "specifiek voor Managed Service Providers (25-100 FTE).",
    version="2.5.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

app.add_middleware(NoCacheMiddleware)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tenderagent")

# ---------------------------------------------------------------------------
# SQLite - Gunningshistorie
# ---------------------------------------------------------------------------

def get_db():
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn
    return None

def query_gunningshistorie(opdrachtgever):
    conn = get_db()
    if not conn:
        return []
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
            AND g.is_ict = 1
            ORDER BY g.publicatiedatum DESC
            LIMIT 20
            """,
            (f"%{opdrachtgever.lower()}%",),
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def query_herhalingspatronen():
    conn = get_db()
    if not conn:
        return []
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
            LIMIT 50
            """,
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

def query_vooraankondigingen():
    conn = get_db()
    if not conn:
        return []
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
            LIMIT 50
            """,
        )
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()

# ---------------------------------------------------------------------------
# Classificatie-functies
# ---------------------------------------------------------------------------

def classify_opdrachtgever(naam):
    naam_lower = naam.lower()
    for og_type in ["RIJK_VITAAL", "ZBO", "PUBLIEK_SOCIAAL", "GR",
                     "GEMEENTE", "PROVINCIE", "WATERSCHAP", "RIJK",
                     "ZORG", "ONDERWIJS"]:
        for pattern in OPDRACHTGEVER_PATTERNS[og_type]:
            if pattern.lower() in naam_lower:
                return og_type
    if "stichting" in naam_lower:
        if any(h in naam_lower for h in ["onderwijs", "school", "lyceum", "college"]):
            return "ONDERWIJS"
    return "OVERIG"

import re as _re

def keyword_in_text(kw, text):
    """Korte keywords (<=4 chars) als heel woord matchen, langere als substring."""
    kw_lower = kw.lower()
    if len(kw_lower) <= 4:
        return bool(_re.search(r'\b' + _re.escape(kw_lower) + r'\b', text))
    return kw_lower in text

def match_segments(naam, beschrijving, cpv_codes=None):
    combined = f"{naam} {beschrijving}".lower()
    cpv_set = set()
    if cpv_codes:
        for c in cpv_codes:
            code = c.get("code", "") if isinstance(c, dict) else str(c)
            # Alleen het numerieke deel voor prefix-matching
            code_num = code.split("-")[0] if "-" in code else code
            cpv_set.add(code_num)

    matched = []
    for segment_name, config in MSP_SEGMENTS.items():
        # Strong keywords → direct match
        has_strong = any(keyword_in_text(kw, combined) for kw in config["strong"])
        if has_strong:
            matched.append(segment_name)
            continue

        # Weak keywords → alleen met passende CPV-code
        has_weak = any(keyword_in_text(kw, combined) for kw in config["weak"])
        if has_weak and cpv_set:
            has_cpv = any(
                tender_cpv.startswith(seg_cpv.split("-")[0])
                or seg_cpv.split("-")[0].startswith(tender_cpv)
                for tender_cpv in cpv_set
                for seg_cpv in config["cpv"]
            )
            if has_cpv:
                matched.append(segment_name)

    if len(matched) >= 3:
        matched.append("Full-service IT-partner")
    return matched

def detect_explicit_certs(tekst):
    tekst_lower = f" {tekst.lower()} "
    found = []
    for cert, keywords in CERT_KEYWORDS.items():
        if any(kw in tekst_lower for kw in keywords):
            found.append(cert)
    return found

def get_verwachte_vereisten(og_type, segmenten):
    vereisten = dict(VERWACHTE_VEREISTEN.get(og_type, {}))
    if "Cybersecurity & Informatiebeveiliging" in segmenten:
        if "ISO 27001" not in vereisten or vereisten["ISO 27001"] in ("mogelijk",):
            vereisten["ISO 27001"] = "waarschijnlijk"
    return vereisten

# ---------------------------------------------------------------------------
# MSP-fit scoring
# ---------------------------------------------------------------------------

def calculate_msp_fit(tender, og_type, segmenten):
    score = 0.0
    naam = (tender.get("aanbestedingNaam") or "").lower()
    beschrijving = (tender.get("opdrachtBeschrijving") or "").lower()
    combined = f"{naam} {beschrijving}"
    type_opdracht = tender.get("typeOpdracht", {}).get("code", "")

    # Check applicatiesoftware EERST — blokkeert MSP-core bonus
    is_app_software = any(kw in combined for kw in APP_SOFTWARE_INDICATORS)
    is_physical = any(kw in combined for kw in PHYSICAL_INFRA_INDICATORS)

    if type_opdracht == "D":
        score += 20
    if not is_app_software:
        # MSP-core bonus alleen als het NIET applicatiesoftware is
        msp_core = [
            "werkplekbeheer", "werkplek", "compute", "storage", "backup",
            "hosting", "cloud", "datacenter", "infrastructuur", "connectiviteit",
            "managed service", "servicedesk", "helpdesk", "endpoint",
            "digitale werkomgeving", "disaster recovery",
        ]
        if any(kw in combined for kw in msp_core):
            score += 15
    if og_type in ("GEMEENTE", "PROVINCIE", "WATERSCHAP", "GR"):
        score += 10
    real_segs = [s for s in segmenten if s != "Full-service IT-partner"]
    if len(real_segs) >= 2:
        score += 5

    # Penalties
    if is_app_software:
        score -= 25  # Zwaarder: applicatiesoftware is geen MSP-dienst
    if is_physical:
        score -= 10
    if type_opdracht == "L":
        score -= 10

    if score > 20:
        label = "MSP-relevant"
    elif score >= 0:
        label = "Mogelijk relevant"
    else:
        label = "Niet MSP"
    return score, label

# ---------------------------------------------------------------------------
# Geschatte waarde
# ---------------------------------------------------------------------------

def format_bedrag(waarde):
    if waarde is None:
        return "?"
    if waarde >= 1_000_000:
        return f"\u20ac{waarde / 1_000_000:.1f}M"
    if waarde >= 1_000:
        return f"\u20ac{waarde // 1_000}K"
    return f"\u20ac{waarde}"

def schat_waarde(tender, og_type, segmenten):
    geraamd = tender.get("geraamdeWaarde") or (tender.get("aanbestedingDetail") or {}).get("geraamdeWaarde")
    if geraamd and isinstance(geraamd, (int, float)) and geraamd > 0:
        return int(geraamd), int(geraamd), "exact", format_bedrag(int(geraamd))

    europees = tender.get("europees", False)
    naam = (tender.get("aanbestedingNaam") or "").lower()
    beschrijving = (tender.get("opdrachtBeschrijving") or "").lower()
    combined = f"{naam} {beschrijving}"

    is_infra = any(kw in combined for kw in [
        "compute", "storage", "hosting", "datacenter", "cloud",
        "infrastructuur", "connectiviteit", "werkplekbeheer",
    ])
    is_app = any(kw in combined for kw in APP_SOFTWARE_INDICATORS)

    v_min, v_max = None, None
    if og_type == "GEMEENTE":
        if is_infra:
            v_min, v_max = 200_000, 1_000_000
        elif is_app:
            v_min, v_max = 100_000, 500_000
        else:
            v_min, v_max = 100_000, 750_000
    elif og_type == "GR":
        v_min, v_max = 300_000, 2_000_000
    elif og_type in ("RIJK", "RIJK_VITAAL", "ZBO"):
        v_min, v_max = 500_000, 5_000_000
    elif og_type == "ZORG":
        v_min, v_max = 100_000, 500_000
    elif og_type == "ONDERWIJS":
        v_min, v_max = 50_000, 300_000
    elif og_type == "PUBLIEK_SOCIAAL":
        v_min, v_max = 100_000, 500_000
    elif og_type in ("PROVINCIE", "WATERSCHAP"):
        v_min, v_max = 200_000, 1_500_000

    if europees and v_min is not None:
        v_min = max(v_min, 221_000)

    if v_min is not None:
        return v_min, v_max, "bandbreedte", f"{format_bedrag(v_min)}-{format_bedrag(v_max)}"
    if europees:
        return 221_000, None, "bandbreedte", "\u2265\u20ac221K"
    return None, None, "onbekend", "?"

# ---------------------------------------------------------------------------
# Spanning-detectie
# ---------------------------------------------------------------------------

def detect_signalen(tender, og_type, segmenten, vereisten, waarde_min, waarde_max, msp_fit_score):
    signalen = []
    naam = (tender.get("aanbestedingNaam") or "").lower()
    beschrijving = (tender.get("opdrachtBeschrijving") or "").lower()
    combined = f"{naam} {beschrijving}"
    type_opdracht = tender.get("typeOpdracht", {}).get("code", "")
    real_segments = [s for s in segmenten if s != "Full-service IT-partner"]

    # DISPROPORTIONELE EISEN
    kleine_og = og_type in ("ONDERWIJS", "PUBLIEK_SOCIAAL", "OVERIG")
    verplichte = [c for c, n in vereisten.items() if n in ("verplicht", "waarschijnlijk")]
    if kleine_og and len(verplichte) >= 3:
        signalen.append({
            "type": "disproportioneel",
            "tekst": f"Zware eisen voor kleine opdrachtgever ({len(verplichte)} certificeringen verwacht)",
            "icoon": "\u26a0\ufe0f",
        })

    if waarde_max and waarde_max <= 300_000 and len(real_segments) >= 3:
        signalen.append({
            "type": "disproportioneel",
            "tekst": f"Brede scope ({len(real_segments)} segmenten) voor beperkt budget ({format_bedrag(waarde_max)})",
            "icoon": "\u26a0\ufe0f",
        })

    if type_opdracht == "L":
        dienst_hints = ["beheer", "onderhoud", "support", "service", "hosting", "managed"]
        if any(h in combined for h in dienst_hints):
            signalen.append({
                "type": "disproportioneel",
                "tekst": "Getypeerd als Levering, maar scope beschrijft dienstverlening",
                "icoon": "\u26a0\ufe0f",
            })

    # OPVALLENDE COMBINATIES
    werkplek = "Werkplek & Eindgebruikersbeheer" in segmenten
    security = "Cybersecurity & Informatiebeveiliging" in segmenten
    if werkplek and security:
        signalen.append({
            "type": "opvallend",
            "tekst": "Werkplek met security-focus \u2014 kijk naar verhouding scope vs. eisen",
            "icoon": "\U0001f9e9",
        })

    if og_type == "GR":
        signalen.append({
            "type": "opvallend",
            "tekst": "Meerdere organisaties, \u00e9\u00e9n contract \u2014 check governance en complexiteit",
            "icoon": "\U0001f9e9",
        })

    dagen = tender.get("aantalDagenTotSluitingsDatum")
    if len(real_segments) >= 3 and dagen and dagen < 21:
        signalen.append({
            "type": "opvallend",
            "tekst": f"Complexe scope ({len(real_segments)} segmenten) maar korte inschrijftermijn ({dagen} dagen)",
            "icoon": "\U0001f9e9",
        })

    transitie_hints = ["huidige leverancier", "transitie", "migratie van", "overgang van", "contract loopt af"]
    if any(h in combined for h in transitie_hints):
        signalen.append({
            "type": "opvallend",
            "tekst": "Mogelijke leverancierswisseling \u2014 check transitierisico",
            "icoon": "\U0001f9e9",
        })

    # MSP-KANSEN — alleen als tender minimaal "Mogelijk relevant" is EN geen applicatiesoftware
    is_app_software = any(kw in combined for kw in APP_SOFTWARE_INDICATORS)
    if msp_fit_score >= 0 and not is_app_software:
        if (og_type in ("GEMEENTE", "GR", "PROVINCIE", "WATERSCHAP")
                and werkplek and type_opdracht == "D"
                and waarde_min and waarde_min >= 200_000):
            signalen.append({
                "type": "kans",
                "tekst": "Sweet spot MSP \u2014 overheid + werkplekbeheer + diensten + substanti\u00eble waarde",
                "icoon": "\u2705",
            })

        cloud = "Cloud & Hosting" in segmenten
        if (og_type in ("GEMEENTE", "GR", "PROVINCIE", "WATERSCHAP", "RIJK", "ZBO")
                and cloud and type_opdracht == "D"):
            signalen.append({
                "type": "kans",
                "tekst": "Cloud/hosting bij overheid \u2014 groeimarkt voor MSP's",
                "icoon": "\u2705",
            })

    if msp_fit_score > 20 and waarde_min and waarde_min >= 500_000:
        signalen.append({
            "type": "kans",
            "tekst": f"MSP-relevant met subsanti\u00eble waarde ({format_bedrag(waarde_min)}+)",
            "icoon": "\u2705",
        })

    return signalen

# ---------------------------------------------------------------------------
# IT-relevantie (basis)
# ---------------------------------------------------------------------------

def is_it_relevant(tender):
    """Hard gate: heeft deze tender überhaupt iets met IT te maken?
    Checkt eerst negatieve keywords in naam, dan CPV-codes, dan IT-keywords.
    Tenders zonder enig IT-signaal worden volledig uitgefilterd."""
    naam = (tender.get("aanbestedingNaam") or "").lower()
    beschrijving = (tender.get("opdrachtBeschrijving") or "").lower()
    combined = f"{naam} {beschrijving}"

    # Check 0: Hard negative — als de NAAM een niet-IT keyword bevat, blokkeer
    for neg in NOT_IT_NAAM_KEYWORDS:
        if neg in naam:
            return False

    # Check 1: CPV-codes — volledige prefix-match (minimaal 4 cijfers)
    cpv_codes = tender.get("cpvCodes", [])
    has_it_cpv = False
    for cpv in cpv_codes:
        code = cpv.get("code", "") if isinstance(cpv, dict) else str(cpv)
        code_num = code.split("-")[0] if "-" in code else code
        for it_cpv in CPV_CODES_IT:
            if code_num.startswith(it_cpv[:4]):
                has_it_cpv = True
                break
        if has_it_cpv:
            break

    # Als CPV matcht, controleer of het niet puur fysiek is (bv. "onderhoud" zonder IT)
    if has_it_cpv:
        # Extra check: als naam puur fysiek klinkt, vertrouw CPV niet blind
        fysiek_in_naam = any(f in naam for f in [
            "onderhoud gras", "onderhoud verlichting", "onderhoud deuren",
            "onderhoud gebouw", "correctief bouwkundig", "raamovereenkomst onderhoud",
        ])
        if not fysiek_in_naam:
            return True

    # Check 2: Sterke IT-keywords in naam of beschrijving
    # Context-aware: "hosting" alleen als er ook IT-context bij zit
    it_context_words = [
        "ict", "it-", "software", "cloud", "server", "data", "digitaal",
        "web", "applicatie", "informatievoorziening", "cyber", "saas",
        "iaas", "paas", "azure", "microsoft",
    ]
    for kw in IT_KEYWORDS_HIGH:
        if keyword_in_text(kw, combined):
            # "hosting" is ambigu: "hosting meldkamer" is fysiek
            if kw == "hosting":
                has_it_context = any(ctx in combined for ctx in it_context_words)
                if not has_it_context:
                    continue  # Skip "hosting" zonder IT-context
            return True

    # Check 3: MSP-segment strong keywords
    for config in MSP_SEGMENTS.values():
        if any(keyword_in_text(kw, combined) for kw in config["strong"]):
            return True

    return False


IT_KEYWORDS_HIGH = [
    "ict", "it-dienst", "software", "hosting", "cloud", "saas", "iaas", "paas",
    "datacenter", "datacentrum", "cybersecurity", "informatiebeveiliging",
    "digitalisering", "applicatie", "licentie", "microsoft", "azure", "aws",
    "informatievoorziening", "erp", "crm", "dms", "zaaksysteem", "siem",
    "managed services", "servicedesk", "helpdesk", "werkplek",
    "server", "storage", "backup", "disaster recovery",
    "voip", "unified communications", "multifunctional",
    "informatiesysteem", "informatiesystemen", "netwerk", "firewall", "wifi", "wlan",
    "document management", "datawarehouse", "business intelligence",
    "informatiemanagement", "digitale werkplek", "end user",
]

IT_KEYWORDS_MEDIUM = [
    "outsourcing", "telefonie", "print", "printer",
    "infrastructuur", "systeem", "platform", "portaal",
    "data-analyse", "kunstmatige intelligentie",
    "digitaal", "automatisering", "koppelingen", "api",
]

def calculate_relevance(tender):
    score = 0.0
    reasons = []
    naam = (tender.get("aanbestedingNaam") or "").lower()
    beschrijving = (tender.get("opdrachtBeschrijving") or "").lower()
    combined = f"{naam} {beschrijving}"

    neg_hits = [kw for kw in NEGATIVE_KEYWORDS if kw in combined]
    if neg_hits:
        score -= 40
        reasons.append(f"Negatief: {', '.join(neg_hits[:3])}")

    if tender.get("typeOpdracht", {}).get("code") == "D":
        score += 15
        reasons.append("Type: Diensten")

    high_hits = [kw for kw in IT_KEYWORDS_HIGH if kw in combined]
    if high_hits:
        score += min(len(high_hits) * 25, 50)
        reasons.append(f"IT-kernwoorden: {', '.join(high_hits[:5])}")

    med_hits = [kw for kw in IT_KEYWORDS_MEDIUM if kw in combined]
    if med_hits:
        score += min(len(med_hits) * 10, 20)
        reasons.append(f"IT-gerelateerd: {', '.join(med_hits[:5])}")

    if tender.get("europees"):
        score += 5
        reasons.append("Europese aanbesteding")
    if tender.get("digitaal"):
        score += 5
        reasons.append("Digitaal via TenderNed")

    return max(min(score, 100), 0), reasons

# ---------------------------------------------------------------------------
# Tender verrijken
# ---------------------------------------------------------------------------

def enrich_tender(tender):
    pub_id = tender.get("publicatieId", "")
    naam = tender.get("aanbestedingNaam", "Onbekend")
    opdrachtgever = tender.get("opdrachtgeverNaam", "Onbekend")
    beschrijving = tender.get("opdrachtBeschrijving", "")

    og_type = classify_opdrachtgever(opdrachtgever)
    cpv_codes = tender.get("cpvCodes", [])
    segmenten = match_segments(naam, beschrijving, cpv_codes)
    verwacht = get_verwachte_vereisten(og_type, segmenten)
    expliciet = detect_explicit_certs(f"{naam} {beschrijving}")
    rel_score, rel_reasons = calculate_relevance(tender)
    msp_score, msp_label = calculate_msp_fit(tender, og_type, segmenten)
    w_min, w_max, w_bron, w_weergave = schat_waarde(tender, og_type, segmenten)
    signalen = detect_signalen(tender, og_type, segmenten, verwacht, w_min, w_max, msp_score)
    historie = query_gunningshistorie(opdrachtgever) if DB_PATH.exists() else []

    return TenderSummary(
        id=pub_id,
        naam=naam,
        opdrachtgever=opdrachtgever,
        opdrachtgever_type=og_type,
        publicatie_datum=tender.get("publicatieDatum", ""),
        type_publicatie=tender.get("typePublicatie", {}).get("omschrijving", ""),
        type_opdracht=tender.get("typeOpdracht", {}).get("omschrijving", ""),
        procedure=tender.get("procedure", {}).get("omschrijving", ""),
        sluitingsdatum=tender.get("sluitingsDatum"),
        dagen_tot_sluiting=tender.get("aantalDagenTotSluitingsDatum"),
        europees=tender.get("europees", False),
        digitaal=tender.get("digitaal", False),
        beschrijving=beschrijving,
        relevantie_score=rel_score,
        relevantie_reden=rel_reasons if rel_reasons else None,
        msp_fit=msp_score,
        msp_fit_label=msp_label,
        segmenten=segmenten,
        verwachte_vereisten=verwacht,
        expliciete_vereisten=expliciet,
        geschatte_waarde_min=w_min,
        geschatte_waarde_max=w_max,
        waarde_bron=w_bron,
        waarde_weergave=w_weergave,
        signalen=signalen,
        gunningshistorie=historie[:5],
        tenderned_url=f"{TENDERNED_BASE}/{pub_id}",
        tsender_url=tender.get("tsenderLink"),
    )

# ---------------------------------------------------------------------------
# TenderNed API
# ---------------------------------------------------------------------------

async def fetch_tenderned_page(client, page, size=100):
    try:
        resp = await client.get(TENDERNED_TNS, params={"page": page, "size": size}, timeout=30.0)
        resp.raise_for_status()
        return resp.json().get("content", [])
    except Exception as e:
        logger.error(f"Fout bij ophalen pagina {page}: {e}")
        return []

async def fetch_all_tenders(max_pages=10):
    all_tenders = []
    async with httpx.AsyncClient() as client:
        for page in range(max_pages):
            tenders = await fetch_tenderned_page(client, page)
            if not tenders:
                break
            all_tenders.extend(tenders)
            if len(tenders) < 100:
                break
    return all_tenders

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/discover", response_model=DiscoverResponse)
async def discover():
    return DiscoverResponse(
        service="TenderAgent MSP",
        version="2.5.0",
        description="API voor IT-aanbestedingen in Nederland, specifiek voor "
                    "Managed Service Providers (25-100 FTE). MSP-fit scoring, "
                    "spanning-detectie en gunningshistorie.",
        endpoints={
            "/api/v1/discover": "Dit overzicht",
            "/api/v1/tenders": "Actuele IT/MSP-relevante tenders met analyse",
            "/api/v1/tenders/{id}": "Tender detail",
            "/api/v1/stats": "Statistieken",
            "/api/v1/cpv-codes": "Gemonitorde CPV-codes",
            "/api/v1/vooraankondigingen": "Vooraankondigingen en marktconsultaties (dataset vereist)",
            "/api/v1/herhalingspatronen": "Verwachte heraanbestedingen (dataset vereist)",
            "/api/v1/gunningshistorie/{opdrachtgever}": "Gunningshistorie (dataset vereist)",
        },
        data_source="TenderNed TNS + openbare dataset 2016-2025",
        cpv_codes_monitored=len(CPV_CODES_IT),
        msp_segments=len(MSP_SEGMENTS),
        dataset_loaded=DB_PATH.exists(),
        last_updated=datetime.now().isoformat(),
    )

@app.get("/api/v1/tenders", response_model=list[TenderSummary])
async def get_tenders(
    min_score: float = Query(0, description="Minimale IT-relevantiescore (0-100)"),
    min_msp_fit: Optional[float] = Query(None, description="Minimale MSP-fit score"),
    msp_label: Optional[str] = Query(None, description="Filter: relevant, mogelijk, niet"),
    segment: Optional[str] = Query(None, description="Filter op MSP-segment"),
    type: Optional[str] = Query(None, description="Filter op type publicatie"),
    max_results: int = Query(50, description="Maximum resultaten"),
    zoekterm: Optional[str] = Query(None, description="Vrije zoekterm"),
    alleen_open: bool = Query(False, description="Alleen open tenders"),
    alleen_signalen: bool = Query(False, description="Alleen tenders met signalen"),
    sorteer: str = Query("msp_fit", description="Sorteer: msp_fit, relevantie, waarde, signalen"),
):
    raw = await fetch_all_tenders()
    # Hard IT-gate: alleen tenders met IT-signaal verrijken
    it_tenders = [t for t in raw if is_it_relevant(t)]
    logger.info(f"IT-filter: {len(it_tenders)}/{len(raw)} tenders zijn IT-relevant")
    summaries = [enrich_tender(t) for t in it_tenders]

    if min_score > 0:
        summaries = [s for s in summaries if (s.relevantie_score or 0) >= min_score]
    if min_msp_fit is not None:
        summaries = [s for s in summaries if (s.msp_fit or 0) >= min_msp_fit]
    if msp_label:
        lmap = {"relevant": "MSP-relevant", "mogelijk": "Mogelijk relevant", "niet": "Niet MSP"}
        target = lmap.get(msp_label.lower(), msp_label)
        summaries = [s for s in summaries if s.msp_fit_label == target]
    if segment:
        sl = segment.lower()
        summaries = [s for s in summaries if any(sl in seg.lower() for seg in s.segmenten)]
    if type:
        tu = type.upper()
        summaries = [s for s in summaries if tu in s.type_publicatie.upper()]
    if zoekterm:
        zl = zoekterm.lower()
        summaries = [s for s in summaries if zl in s.naam.lower() or zl in s.beschrijving.lower()]
    if alleen_open:
        summaries = [s for s in summaries if s.dagen_tot_sluiting and s.dagen_tot_sluiting > 0]
    if alleen_signalen:
        summaries = [s for s in summaries if s.signalen]

    if sorteer == "msp_fit":
        summaries.sort(key=lambda s: (-(s.msp_fit or -100), -(s.relevantie_score or 0)))
    elif sorteer == "relevantie":
        summaries.sort(key=lambda s: -(s.relevantie_score or 0))
    elif sorteer == "waarde":
        summaries.sort(key=lambda s: -(s.geschatte_waarde_min or 0))
    elif sorteer == "signalen":
        summaries.sort(key=lambda s: (-len(s.signalen), -(s.msp_fit or -100)))

    return summaries[:max_results]

@app.get("/api/v1/tenders/{tender_id}", response_model=TenderSummary)
async def get_tender_detail(tender_id: str):
    raw = await fetch_all_tenders(max_pages=5)
    for t in raw:
        if t.get("publicatieId") == tender_id:
            return enrich_tender(t)
    raise HTTPException(status_code=404, detail=f"Tender {tender_id} niet gevonden")

@app.get("/api/v1/stats", response_model=StatsResponse)
async def get_stats():
    raw = await fetch_all_tenders()
    it_tenders = [t for t in raw if is_it_relevant(t)]
    summaries = [enrich_tender(t) for t in it_tenders]
    it = [s for s in summaries if (s.relevantie_score or 0) > 0]

    return StatsResponse(
        totaal_tenders=len(it),
        msp_relevant=len([s for s in it if s.msp_fit_label == "MSP-relevant"]),
        mogelijk_relevant=len([s for s in it if s.msp_fit_label == "Mogelijk relevant"]),
        niet_msp=len([s for s in it if s.msp_fit_label == "Niet MSP"]),
        europees=len([s for s in it if s.europees]),
        nationaal=len([s for s in it if not s.europees]),
        gemiddelde_dagen_tot_sluiting=round(
            sum(s.dagen_tot_sluiting for s in it if s.dagen_tot_sluiting and s.dagen_tot_sluiting > 0) /
            max(len([s for s in it if s.dagen_tot_sluiting and s.dagen_tot_sluiting > 0]), 1), 1
        ),
        top_opdrachtgevers=sorted(
            [{"naam": k, "aantal": v} for k, v in
             {s.opdrachtgever: sum(1 for x in it if x.opdrachtgever == s.opdrachtgever) for s in it}.items()],
            key=lambda x: -x["aantal"]
        )[:10],
        segmenten_verdeling={seg: sum(1 for s in it if seg in s.segmenten)
                             for seg in set(seg for s in it for seg in s.segmenten)},
        tenders_met_signalen=len([s for s in it if s.signalen]),
        datum=date.today().isoformat(),
    )

@app.get("/api/v1/cpv-codes")
async def get_cpv_codes():
    return {"totaal": len(CPV_CODES_IT),
            "codes": [{"code": k, "beschrijving": v} for k, v in sorted(CPV_CODES_IT.items())]}

@app.get("/api/v1/gunningshistorie/{opdrachtgever}")
async def get_gunningshistorie(opdrachtgever: str):
    if not DB_PATH.exists():
        return {"error": "Dataset niet geladen. Draai import_dataset.py eerst.", "resultaten": []}
    resultaten = query_gunningshistorie(opdrachtgever)
    return {"opdrachtgever": opdrachtgever, "aantal": len(resultaten), "resultaten": resultaten}

@app.get("/api/v1/vooraankondigingen", response_model=list[Vooraankondiging])
async def get_vooraankondigingen():
    if not DB_PATH.exists():
        return []
    rows = query_vooraankondigingen()
    return [Vooraankondiging(
        opdrachtgever=r.get("aanbestedende_dienst", ""),
        opdrachtgever_type=classify_opdrachtgever(r.get("aanbestedende_dienst", "")),
        beschrijving=r.get("beschrijving", ""),
        publicatiedatum=r.get("publicatiedatum", ""),
        type=r.get("publicatie_soort", ""),
        cpv_codes=(r.get("cpv_codes") or "").split(", "),
        segmenten=match_segments(r.get("aanbestedende_dienst", ""), r.get("beschrijving", "")),
        tenderned_kenmerk=r.get("tenderned_kenmerk"),
    ) for r in rows]

@app.get("/api/v1/herhalingspatronen", response_model=list[Herhalingspatroon])
async def get_herhalingspatronen():
    if not DB_PATH.exists():
        return []
    rows = query_herhalingspatronen()
    result = []
    for r in rows:
        gd = r.get("datum_gunning", "")
        try:
            d = datetime.strptime(gd[:10], "%Y-%m-%d")
            verwacht = f"{d.year + 3}-{d.year + 5}"
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
            segmenten=match_segments(r.get("aanbestedende_dienst", ""), r.get("beschrijving", "")),
        ))
    return result

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="nl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TenderAgent MSP</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
.header { background: #1a1a2e; color: white; padding: 20px 30px; }
.header h1 { font-size: 22px; font-weight: 600; }
.header p { font-size: 13px; color: #aaa; margin-top: 4px; }
.controls { background: white; padding: 16px 30px; border-bottom: 1px solid #ddd; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }
.btn { padding: 8px 16px; border: 1px solid #ddd; border-radius: 6px; background: white; cursor: pointer; font-size: 13px; transition: all 0.15s; }
.btn:hover { background: #f0f0f0; }
.btn.active { background: #1a1a2e; color: white; border-color: #1a1a2e; }
.stats { display: flex; gap: 20px; padding: 16px 30px; background: white; border-bottom: 1px solid #eee; }
.stat { text-align: center; }
.stat-num { font-size: 24px; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; }
.container { padding: 20px 30px; }
.tender { background: white; border-radius: 8px; margin-bottom: 12px; border: 1px solid #e0e0e0; overflow: hidden; }
.tender-header { display: flex; justify-content: space-between; align-items: flex-start; padding: 16px 20px; cursor: pointer; }
.tender-header:hover { background: #fafafa; }
.tender-naam { font-size: 15px; font-weight: 600; flex: 1; }
.tender-badges { display: flex; gap: 6px; margin-left: 16px; flex-shrink: 0; }
.badge { padding: 3px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.badge-relevant { background: #d4edda; color: #155724; }
.badge-mogelijk { background: #fff3cd; color: #856404; }
.badge-niet { background: #f8d7da; color: #721c24; }
.tender-meta { font-size: 12px; color: #888; margin-top: 4px; }
.tender-meta span { margin-right: 16px; }
.tender-signalen { display: flex; gap: 6px; margin-top: 8px; flex-wrap: wrap; }
.signaal { padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.signaal-kans { background: #d4edda; color: #155724; }
.signaal-opvallend { background: #e8e0f0; color: #4a3070; }
.signaal-disproportioneel { background: #fff3cd; color: #856404; }
.tender-detail { padding: 0 20px 16px; display: none; border-top: 1px solid #eee; margin-top: 0; }
.tender-detail.open { display: block; padding-top: 16px; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.detail-section h4 { font-size: 12px; text-transform: uppercase; color: #888; letter-spacing: 0.5px; margin-bottom: 8px; }
.detail-section p { font-size: 13px; line-height: 1.5; }
.cert-list { list-style: none; }
.cert-list li { font-size: 13px; padding: 2px 0; }
.cert-verplicht { color: #d32f2f; font-weight: 600; }
.cert-waarschijnlijk { color: #f57c00; }
.cert-mogelijk { color: #888; }
.cert-gebruikelijk { color: #888; font-style: italic; }
.historie-item { font-size: 12px; padding: 6px 0; border-bottom: 1px solid #f0f0f0; }
.historie-item:last-child { border-bottom: none; }
.link-tn { display: inline-block; margin-top: 12px; color: #1a73e8; text-decoration: none; font-size: 13px; }
.link-tn:hover { text-decoration: underline; }
.empty { text-align: center; padding: 60px; color: #888; }
.loader { text-align: center; padding: 60px; color: #888; }
.tabs { display: flex; gap: 0; margin-bottom: 20px; }
.tab { padding: 10px 20px; border: 1px solid #ddd; background: white; cursor: pointer; font-size: 13px; font-weight: 500; }
.tab:first-child { border-radius: 6px 0 0 6px; }
.tab:last-child { border-radius: 0 6px 6px 0; }
.tab.active { background: #1a1a2e; color: white; border-color: #1a1a2e; }
.tab-content { display: none; }
.tab-content.active { display: block; }
.search-input { padding: 8px 14px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; width: 220px; }
</style>
</head>
<body>
<div class="header">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
            <h1>TenderAgent MSP</h1>
            <p>IT-aanbestedingen voor Managed Service Providers &middot; Epikouros Trading & Consulting</p>
        </div>
        <a href="/handleiding" target="_blank" style="color:white;background:rgba(255,255,255,0.15);padding:8px 16px;border-radius:6px;text-decoration:none;font-size:13px;">Handleiding</a>
    </div>
</div>
<div class="stats" id="stats"><div class="loader">Laden...</div></div>
<div class="controls">
    <div class="tabs" id="main-tabs">
        <div class="tab active" data-tab="tenders">Tenders</div>
        <div class="tab" data-tab="herhalingen">Herhalingen</div>
        <div class="tab" data-tab="vooraank">Vooraankondigingen</div>
    </div>
    <input class="search-input" id="search" type="text" placeholder="Zoek in naam of opdrachtgever...">
</div>
<div class="controls" id="filters">
    <span style="font-size:12px;color:#888;margin-right:8px;">Filter:</span>
    <button class="btn active" data-filter="alle">Alle</button>
    <button class="btn" data-filter="relevant">MSP-relevant</button>
    <button class="btn" data-filter="signalen">Met signalen</button>
    <button class="btn" data-filter="kansen">MSP-kansen</button>
    <button class="btn" data-filter="open">Nog open</button>
</div>
<div class="container" id="content"><div class="loader">Tenders ophalen van TenderNed...</div></div>

<script>
let allTenders = [];
let activeFilter = 'alle';
let activeTab = 'tenders';
let searchTerm = '';

async function loadData() {
    try {
        const cb = Date.now();
        const [tRes, hRes, vRes] = await Promise.all([
            fetch('/api/v1/tenders?_=' + cb),
            fetch('/api/v1/herhalingspatronen?_=' + cb),
            fetch('/api/v1/vooraankondigingen?_=' + cb)
        ]);
        allTenders = await tRes.json();
        window.herhalingen = await hRes.json();
        window.vooraank = await vRes.json();
        renderStats();
        renderTenders();
    } catch(e) {
        document.getElementById('content').innerHTML = '<div class="empty">Fout bij laden: ' + e.message + '</div>';
    }
}

function renderStats() {
    const relevant = allTenders.filter(t => t.msp_fit_label === 'MSP-relevant').length;
    const signalen = allTenders.filter(t => (t.signalen||[]).length > 0).length;
    const kansen = allTenders.filter(t => (t.signalen||[]).some(s => s.type === 'kans')).length;
    const open = allTenders.filter(t => t.dagen_tot_sluiting && t.dagen_tot_sluiting > 0).length;
    document.getElementById('stats').innerHTML = `
        <div class="stat"><div class="stat-num">${allTenders.length}</div><div class="stat-label">IT-tenders</div></div>
        <div class="stat"><div class="stat-num">${relevant}</div><div class="stat-label">MSP-relevant</div></div>
        <div class="stat"><div class="stat-num">${signalen}</div><div class="stat-label">Met signalen</div></div>
        <div class="stat"><div class="stat-num">${kansen}</div><div class="stat-label">MSP-kansen</div></div>
        <div class="stat"><div class="stat-num">${open}</div><div class="stat-label">Nog open</div></div>
        <div class="stat"><div class="stat-num">${(window.herhalingen||[]).length}</div><div class="stat-label">Herhalingen</div></div>
        <div class="stat"><div class="stat-num">${(window.vooraank||[]).length}</div><div class="stat-label">Vooraank.</div></div>
    `;
}

function filterTenders() {
    let filtered = [...allTenders];
    if (searchTerm) {
        const s = searchTerm.toLowerCase();
        filtered = filtered.filter(t => (t.naam||'').toLowerCase().includes(s) || (t.opdrachtgever||'').toLowerCase().includes(s));
    }
    switch(activeFilter) {
        case 'relevant': filtered = filtered.filter(t => t.msp_fit_label === 'MSP-relevant'); break;
        case 'signalen': filtered = filtered.filter(t => (t.signalen||[]).length > 0); break;
        case 'kansen': filtered = filtered.filter(t => (t.signalen||[]).some(s => s.type === 'kans')); break;
        case 'open': filtered = filtered.filter(t => t.dagen_tot_sluiting && t.dagen_tot_sluiting > 0); break;
    }
    return filtered.sort((a,b) => (b.msp_fit||0) - (a.msp_fit||0));
}

function badgeClass(label) {
    if (label === 'MSP-relevant') return 'badge-relevant';
    if (label === 'Mogelijk relevant') return 'badge-mogelijk';
    return 'badge-niet';
}

function signaalClass(type) {
    if (type === 'kans') return 'signaal-kans';
    if (type === 'opvallend') return 'signaal-opvallend';
    return 'signaal-disproportioneel';
}

function certClass(level) {
    return 'cert-' + (level || 'mogelijk');
}

function renderTenders() {
    if (activeTab !== 'tenders') return;
    const filtered = filterTenders();
    if (filtered.length === 0) {
        document.getElementById('content').innerHTML = '<div class="empty">Geen tenders gevonden</div>';
        return;
    }
    document.getElementById('content').innerHTML = filtered.map((t, i) => `
        <div class="tender">
            <div class="tender-header" onclick="toggle(${i})">
                <div>
                    <div class="tender-naam">${esc(t.naam)}</div>
                    <div class="tender-meta">
                        <span>${esc(t.opdrachtgever)}</span>
                        <span>${t.opdrachtgever_type || ''}</span>
                        <span>${t.waarde_weergave || '?'}</span>
                        ${t.dagen_tot_sluiting ? '<span>' + t.dagen_tot_sluiting + ' dagen</span>' : '<span style="color:#ccc">Gesloten</span>'}
                    </div>
                    ${(t.signalen||[]).length ? '<div class="tender-signalen">' + t.signalen.map(s =>
                        '<span class="signaal ' + signaalClass(s.type) + '">' + s.icoon + ' ' + esc(s.tekst) + '</span>'
                    ).join('') + '</div>' : ''}
                </div>
                <div class="tender-badges">
                    ${t.segmenten.map(s => '<span class="badge" style="background:#e8f0fe;color:#1a56db">' + esc(s) + '</span>').join('')}
                    <span class="badge ${badgeClass(t.msp_fit_label)}">${esc(t.msp_fit_label)} (${t.msp_fit})</span>
                </div>
            </div>
            <div class="tender-detail" id="detail-${i}">
                <div class="detail-grid">
                    <div class="detail-section">
                        <h4>Beschrijving</h4>
                        <p>${esc(t.beschrijving || 'Geen beschrijving')}</p>
                        <h4 style="margin-top:16px">Details</h4>
                        <p>Type: ${esc(t.type_opdracht || '?')} &middot; Procedure: ${esc(t.procedure || '?')} &middot; ${t.europees ? 'Europees' : 'Nationaal'}</p>
                        <p>Publicatie: ${t.publicatie_datum || '?'} &middot; Sluiting: ${t.sluitingsdatum ? t.sluitingsdatum.substring(0,10) : '?'}</p>
                    </div>
                    <div class="detail-section">
                        <h4>Verwachte vereisten</h4>
                        <ul class="cert-list">
                            ${Object.entries(t.verwachte_vereisten||{}).map(([c,l]) => '<li class="' + certClass(l) + '">' + esc(c) + ' — ' + l + '</li>').join('') || '<li style="color:#888">Geen</li>'}
                        </ul>
                        ${(t.expliciete_vereisten||[]).length ? '<h4 style="margin-top:12px">Expliciet genoemd</h4><p>' + t.expliciete_vereisten.join(', ') + '</p>' : ''}
                        <h4 style="margin-top:16px">Gunningshistorie (IT)</h4>
                        ${(t.gunningshistorie||[]).length ? t.gunningshistorie.map(h => '<div class="historie-item">' +
                            '<strong>' + esc(h.gegunde_ondernemer || 'Onbekend') + '</strong>' +
                            (h.datum_gunning ? ' &middot; ' + h.datum_gunning.substring(0,10) : '') +
                            (h.definitieve_waarde ? ' &middot; &euro;' + Number(h.definitieve_waarde).toLocaleString('nl') : '') +
                            '<br><span style="color:#888">' + esc((h.beschrijving||'').substring(0,120)) + '</span></div>'
                        ).join('') : '<p style="color:#888;font-size:13px">Geen IT-gunningen gevonden</p>'}
                    </div>
                </div>
                <a class="link-tn" href="${t.tenderned_url}" target="_blank">Bekijk op TenderNed &rarr;</a>
            </div>
        </div>
    `).join('');
}

function renderHerhalingen() {
    const data = (window.herhalingen || []).filter(h => {
        if (!searchTerm) return true;
        const s = searchTerm.toLowerCase();
        return (h.opdrachtgever||'').toLowerCase().includes(s) || (h.beschrijving_vorig||'').toLowerCase().includes(s);
    });
    if (data.length === 0) {
        document.getElementById('content').innerHTML = '<div class="empty">Geen herhalingspatronen gevonden</div>';
        return;
    }
    document.getElementById('content').innerHTML = data.map(h => `
        <div class="tender">
            <div class="tender-header">
                <div>
                    <div class="tender-naam">${esc(h.opdrachtgever)}</div>
                    <div class="tender-meta">
                        <span>Vorige gunning: ${(h.gunningsdatum_vorig||'').substring(0,10)}</span>
                        <span>Verwacht: ${esc(h.verwachte_heraanbesteding)}</span>
                        ${h.gegunde_partij ? '<span>Won: ' + esc(h.gegunde_partij) + '</span>' : ''}
                        ${h.geraamde_waarde ? '<span>&euro;' + Number(h.geraamde_waarde).toLocaleString('nl') + '</span>' : ''}
                    </div>
                    <p style="font-size:13px;margin-top:8px;color:#666">${esc((h.beschrijving_vorig||'').substring(0,200))}</p>
                </div>
            </div>
        </div>
    `).join('');
}

function renderVooraank() {
    const data = (window.vooraank || []).filter(v => {
        if (!searchTerm) return true;
        const s = searchTerm.toLowerCase();
        return (v.opdrachtgever||'').toLowerCase().includes(s) || (v.beschrijving||'').toLowerCase().includes(s);
    });
    if (data.length === 0) {
        document.getElementById('content').innerHTML = '<div class="empty">Geen vooraankondigingen gevonden</div>';
        return;
    }
    document.getElementById('content').innerHTML = data.map(v => `
        <div class="tender">
            <div class="tender-header">
                <div>
                    <div class="tender-naam">${esc(v.opdrachtgever)}</div>
                    <div class="tender-meta">
                        <span>${(v.publicatiedatum||'').substring(0,10)}</span>
                        <span>${esc(v.type||'')}</span>
                    </div>
                    <p style="font-size:13px;margin-top:8px;color:#666">${esc((v.beschrijving||'').substring(0,250))}</p>
                </div>
            </div>
        </div>
    `).join('');
}

function render() {
    if (activeTab === 'tenders') renderTenders();
    else if (activeTab === 'herhalingen') renderHerhalingen();
    else renderVooraank();
}

function toggle(i) { document.getElementById('detail-' + i)?.classList.toggle('open'); }
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

// Event listeners
document.querySelectorAll('[data-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('[data-filter]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        activeFilter = btn.dataset.filter;
        render();
    });
});
document.querySelectorAll('[data-tab]').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('[data-tab]').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        activeTab = tab.dataset.tab;
        document.getElementById('filters').style.display = activeTab === 'tenders' ? 'flex' : 'none';
        render();
    });
});
document.getElementById('search').addEventListener('input', (e) => { searchTerm = e.target.value; render(); });

loadData();
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML

@app.get("/handleiding", response_class=HTMLResponse)
async def handleiding():
    md_path = Path(__file__).parent / "HANDLEIDING.md"
    if not md_path.exists():
        raise HTTPException(404, "HANDLEIDING.md niet gevonden")
    content = md_path.read_text(encoding="utf-8")
    # Simple markdown to HTML conversion
    import re
    html_body = ""
    in_table = False
    in_code = False
    for line in content.split("\n"):
        if line.startswith("```"):
            if in_code:
                html_body += "</code></pre>"
                in_code = False
            else:
                html_body += "<pre><code>"
                in_code = True
            continue
        if in_code:
            html_body += line.replace("<", "&lt;").replace(">", "&gt;") + "\n"
            continue
        if line.startswith("# "):
            html_body += f"<h1>{line[2:]}</h1>"
        elif line.startswith("## "):
            html_body += f"<h2>{line[3:]}</h2>"
        elif line.startswith("### "):
            html_body += f"<h3>{line[4:]}</h3>"
        elif line.startswith("| ") and "---" in line:
            continue
        elif line.startswith("| "):
            if not in_table:
                html_body += "<table>"
                in_table = True
            cells = [c.strip() for c in line.split("|")[1:-1]]
            tag = "th" if not in_table else "td"
            html_body += "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
        else:
            if in_table:
                html_body += "</table>"
                in_table = False
            if line.strip() == "":
                html_body += "<br>"
            elif line.startswith("- "):
                html_body += f"<p style='margin-left:20px'>• {line[2:]}</p>"
            else:
                # Bold
                line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                # Inline code
                line = re.sub(r'`(.+?)`', r'<code style="background:#f0f0f0;padding:2px 6px;border-radius:3px">\1</code>', line)
                # Links
                line = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2" target="_blank">\1</a>', line)
                html_body += f"<p>{line}</p>"
    if in_table:
        html_body += "</table>"
    return f"""<!DOCTYPE html>
<html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Handleiding — TenderAgent MSP</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 20px; color: #333; line-height: 1.6; }}
h1 {{ color: #1a1a2e; border-bottom: 2px solid #1a1a2e; padding-bottom: 8px; }}
h2 {{ color: #1a1a2e; margin-top: 32px; }}
h3 {{ color: #555; margin-top: 24px; }}
table {{ border-collapse: collapse; width: 100%; margin: 12px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; font-size: 14px; }}
th {{ background: #f5f5f5; font-weight: 600; }}
pre {{ background: #1a1a2e; color: #e0e0e0; padding: 16px; border-radius: 6px; overflow-x: auto; }}
code {{ font-family: 'SF Mono', Monaco, monospace; font-size: 13px; }}
a {{ color: #1a73e8; }}
p {{ margin: 4px 0; }}
.back {{ display: inline-block; margin-bottom: 20px; color: #1a73e8; text-decoration: none; }}
.back:hover {{ text-decoration: underline; }}
</style></head><body>
<a class="back" href="/">&larr; Terug naar dashboard</a>
{html_body}
</body></html>"""


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    if DB_PATH.exists():
        conn = get_db()
        if conn:
            try:
                count = conn.execute("SELECT COUNT(*) FROM gunningen").fetchone()[0]
                logger.info(f"Dataset geladen: {count} publicaties")
            except Exception:
                logger.warning("Database bestaat maar tabellen ontbreken")
            finally:
                conn.close()
    else:
        logger.info("Geen dataset. Dashboard werkt, maar gunningshistorie/herhalingspatronen/vooraankondigingen niet beschikbaar.")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
