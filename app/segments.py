"""MSP segment labelling and certification detection for tenders."""

import re
from typing import List, Dict

# ── MSP Segments ─────────────────────────────────────────────────────────
# Each segment has STRONG keywords (sufficient alone) and CPV codes.
# WEAK keywords only trigger a segment if combined with a strong keyword
# or a matching CPV code.

SEGMENTS = {
    "Werkplek & Eindgebruikersbeheer": {
        "cpv": ["30200000", "30210000", "30230000"],
        "strong": [
            "werkplekbeheer", "workplace management", "endpoint management",
            "dwr", "digitale werkomgeving", "printbeheer", "printer",
            "multifunctional", "mfp", "repro", "kantoorautomatisering",
            "desktop beheer", "modern workplace", "microsoft 365", "m365",
            "office 365",
        ],
        "weak": ["werkplek", "desktop", "laptop", "print", "endpoint",
                 "servicedesk", "telefonie"],
    },
    "Cloud & Hosting": {
        "cpv": ["72400000", "72410000"],
        "strong": [
            "hosting", "iaas", "paas", "cloudmigratie", "vmware",
            "virtualisatie", "compute", "storage", "backup", "datacenter",
            "azure", "aws", "containerisatie", "hybride cloud",
        ],
        "weak": ["cloud", "saas", "as a service", "online platform",
                 "webapplicatie", "migratie"],
    },
    "Cybersecurity": {
        "cpv": ["48730000"],
        "strong": [
            "soc", "siem", "penetratietest", "pentest",
            "vulnerability scan", "vulnerability assessment",
            "informatiebeveiliging", "cybersecurity",
            "security operations", "soar", "dreigingsanalyse",
            "incident response",
        ],
        "weak": ["security", "beveiliging", "toegangscontrole",
                 "access control", "identity", "iam", "authenticatie",
                 "autorisatie"],
    },
    "Netwerk & Connectiviteit": {
        "cpv": ["64200000", "32400000", "32420000"],
        "strong": [
            "sd-wan", "lan", "wan", "firewall", "connectiviteit",
            "glasvezel", "wifi", "wlan", "switching", "routing",
            "vpn",
        ],
        "weak": ["netwerk", "telecom"],
    },
    "Applicatiebeheer": {
        "cpv": ["72260000"],
        "strong": [
            "applicatiebeheer", "softwareimplementatie", "zaaksysteem",
            "servicemanagement", "itsm", "erp-implementatie",
            "crm-implementatie", "document management",
        ],
        "weak": ["systeem", "applicatie", "platform", "portaal",
                 "software", "erp", "crm", "hrm", "dms", "cms",
                 "ticketing", "informatiebeheer", "klantvolgsysteem",
                 "salarisadministratie"],
    },
    "Data & BI": {
        "cpv": ["48600000"],
        "strong": [
            "datawarehouse", "business intelligence", "power bi",
            "tableau", "datafundament", "data-integratie", "etl",
            "analytics", "rapportage",
        ],
        "weak": ["data", "bi", "dashboard", "digitaal"],
    },
}

FULL_SERVICE_LABEL = "Full-service"
FULL_SERVICE_THRESHOLD = 3


def _text_has_any(text: str, keywords: list) -> bool:
    """Check if any keyword appears in text as substring (case-insensitive)."""
    text_lower = text.lower()
    for kw in keywords:
        if kw.lower() in text_lower:
            return True
    return False


def _cpv_matches(tender_cpv_codes: list, segment_cpv_prefixes: list) -> bool:
    """Check if any tender CPV code starts with one of the segment prefixes."""
    for cpv_entry in tender_cpv_codes:
        code = cpv_entry.get("code", "") if isinstance(cpv_entry, dict) else str(cpv_entry)
        code_digits = code.split("-")[0].replace(" ", "")
        for prefix in segment_cpv_prefixes:
            if code_digits.startswith(prefix):
                return True
    return False


def detect_segments(naam: str, beschrijving: str, cpv_codes: list) -> List[str]:
    """Detect which MSP segments a tender belongs to.

    Strong keywords or CPV codes alone assign a segment.
    Weak keywords only assign a segment when combined with a strong keyword
    or a matching CPV code for that segment.
    """
    text = f"{naam} {beschrijving}"
    matched = []

    for label, config in SEGMENTS.items():
        has_strong = _text_has_any(text, config["strong"])
        has_weak = _text_has_any(text, config["weak"])
        has_cpv = _cpv_matches(cpv_codes, config["cpv"])

        if has_strong or has_cpv:
            matched.append(label)
        elif has_weak and has_cpv:
            matched.append(label)
        # weak-only: no segment assigned

    if len(matched) >= FULL_SERVICE_THRESHOLD:
        matched.append(FULL_SERVICE_LABEL)

    return matched


# ── MSP-fit Scoring ──────────────────────────────────────────────────────

# IT infrastructure scope — core MSP territory
_MSP_INFRA = [
    "compute", "storage", "backup", "datacenter", "werkplekbeheer",
    "endpoint management", "sd-wan", "firewall", "connectiviteit",
    "dwr", "digitale werkomgeving", "cloudmigratie",
]

# Managed services context — ongoing operations, not one-time delivery
_MSP_MANAGED = [
    "beheer en onderhoud", "managed service", "hosting en beheer",
    "monitoring", "as a service",
]

# Software product delivery — buying/implementing a specific system
_SOFTWARE_DELIVERY = [
    "erp", "hrm", "e-hrm", "salarisverwerking", "salarisadministratie",
    "salaris-", "financieel systeem", "financieel pakket",
    "woz applicatie", "woz-applicatie", "woz waardering",
    "zaaksysteem", "klantvolgsysteem", "promotie volgsysteem",
    "financieel applicatie",
]

# Physical/civil infrastructure — not IT managed services
_PHYSICAL_INFRA = [
    "glasvezel", "civiel", "toegangscontrole", "fysieke beveiliging",
    "meettrein", "voertuigvolg", "audiovisuele middelen",
    "touchscreen", "reizigerstrein", "beeldmateriaal",
    "telsysteem", "laboratorium",
]

# Niche vendor-specific software requiring specific vendor
_NICHE_SOFTWARE = [
    "arcgis", "safe exam", "splunk licentie", "epic connect",
    "afas", "exact online", "cris",
]

# Primary MSP client categories
_MSP_CLIENT_TYPES = {"GEMEENTE", "PROVINCIE", "WATERSCHAP", "GR"}


def score_msp_fit(
    tender_naam: str,
    beschrijving: str,
    type_opdracht: str,
    opdrachtgever_type: str,
    segments: List[str],
) -> Dict:
    """Score how well a tender fits an MSP's service portfolio.

    Returns dict with keys: score, level.
    Level: 'MSP-relevant' (>20), 'Mogelijk relevant' (0-20), 'Niet MSP' (<0).
    """
    text = f"{tender_naam} {beschrijving}".lower()
    score = 0

    # +10 for services (MSP's deliver services, not products)
    if type_opdracht and "diensten" in type_opdracht.lower():
        score += 10

    # +15 for IT infrastructure scope (core MSP territory)
    if _text_has_any(text, _MSP_INFRA):
        score += 15

    # +15 for managed services context
    if _text_has_any(text, _MSP_MANAGED):
        score += 15

    # +10 for primary MSP clients
    if opdrachtgever_type in _MSP_CLIENT_TYPES:
        score += 10

    # -25 for software product delivery
    if _text_has_any(text, _SOFTWARE_DELIVERY):
        score -= 25

    # -25 for physical/civil infrastructure
    if _text_has_any(text, _PHYSICAL_INFRA):
        score -= 25

    # -25 for niche vendor-specific software
    if _text_has_any(text, _NICHE_SOFTWARE):
        score -= 25

    if score > 20:
        level = "MSP-relevant"
    elif score >= 0:
        level = "Mogelijk relevant"
    else:
        level = "Niet MSP"

    return {"score": score, "level": level}


# ── Certification Detection ──────────────────────────────────────────────

# Explicit certifications: detected with high confidence
CERTIFICATIONS = [
    {"name": "ISO 27001", "pattern": r"(?i)ISO[\s\-]?27001", "category": "security"},
    {"name": "ISO 9001", "pattern": r"(?i)ISO[\s\-]?9001", "category": "quality"},
    {"name": "ISO 14001", "pattern": r"(?i)ISO[\s\-]?14001", "category": "other"},
    {"name": "NEN 7510", "pattern": r"(?i)NEN[\s\-]?7510", "category": "security"},
    {"name": "ISAE 3402", "pattern": r"(?i)ISAE[\s\-]?3402", "category": "quality"},
    {"name": "SOC 2", "pattern": r"(?i)\bSOC[\s\-]?2\b", "category": "security"},
    {"name": "BIO", "pattern": r"(?i)(?:\bBIO\b|Baseline\s+Informatiebeveiliging)", "category": "security"},
    {"name": "DigiD", "pattern": r"(?i)\bDigiD\b", "category": "security"},
    {"name": "Wpg", "pattern": r"(?i)(?:\bWpg\b|\bWet\s+politiegegeven)", "category": "other"},
    {"name": "NIS2", "pattern": r"(?i)\bNIS[\s\-]?2\b", "category": "security"},
    {"name": "DORA", "pattern": r"(?i)\bDORA\b", "category": "security"},
    {"name": "PSO", "pattern": r"(?i)(?:\bPSO\b|Prestatieladder\s+Social|socialer\s+ondernemen)", "category": "social"},
    {"name": "CO2-prestatieladder", "pattern": r"(?i)CO2[\s\-]?prestatieladder", "category": "social"},
    {"name": "SROI", "pattern": r"(?i)(?:\bSROI\b|Social\s+Return)", "category": "social"},
]

# Implied certifications: inferred from context, shown with "?" suffix
IMPLIED_CERTIFICATIONS = [
    {
        "name": "ISO 27001",
        "pattern": r"(?i)informatiebeveilig",
        "category": "security",
        "excludes": ["ISO 27001"],  # don't imply if already explicit
    },
    {
        "name": "NEN 7510",
        "pattern": r"(?i)(?:zorg.*informatiebeveilig|informatiebeveilig.*zorg)",
        "category": "security",
        "excludes": ["NEN 7510"],
    },
    {
        "name": "BIO",
        "pattern": r"(?i)(?:informatiebeveilig.*(?:overheid|gemeente|provincie|rijks|waterschap)|(?:overheid|gemeente|provincie|rijks|waterschap).*informatiebeveilig)",
        "category": "security",
        "excludes": ["BIO"],
    },
]


# ── Opdrachtgever Classification & Expected Requirements ─────────────

OPDRACHTGEVER_RULES = [
    # Order matters: more specific matches first
    ("RIJK_VITAAL", ["rijkswaterstaat", "prorail"]),
    ("GR", ["gemeenschappelijke regeling", "gemeenschappelijk regeling", "samenwerkingsverband"]),
    ("ZORG", ["ziekenhuis", "ggz", "ggd", "zorggroep", "huisartsen",
              "medisch centrum", "umc "]),
    ("RIJK", ["ministerie", "politie", "raad van state", "hoge raad",
              "eerste kamer", "tweede kamer", "rekenkamer"]),
    ("ZBO", ["uwv", "svb", "duo", "belastingdienst", "rivm", "rvo",
             "rdw", "dienst wegverkeer", "kadaster", "knmi", "cbs",
             "autoriteit persoonsgegevens"]),
    ("WATERSCHAP", ["waterschap", "hoogheemraadschap", "wetterskip"]),
    ("GEMEENTE", ["gemeente"]),
    ("PROVINCIE", ["provincie"]),
    ("ONDERWIJS", ["universiteit", "hogeschool", " roc ", "lyceum", "scholengemeenschap"]),
    ("PUBLIEK_SOCIAAL", ["emco", "sociale werkvoorziening", "sw-bedrijf"]),
]

# "rws" checked separately to avoid matching inside other words
_RWS_PATTERN = re.compile(r"(?i)\bRWS\b")
# "stichting ... onderwijs" combination
_STICHTING_ONDERWIJS = re.compile(r"(?i)stichting.*onderwijs|onderwijs.*stichting")
# "GR " prefix (e.g. "GR Drechtsteden")
_GR_PREFIX = re.compile(r"(?i)\bGR\s+[A-Z]")

# Level priority: verplicht > waarschijnlijk > gebruikelijk > mogelijk
LEVEL_PRIORITY = {"verplicht": 4, "waarschijnlijk": 3, "gebruikelijk": 2, "mogelijk": 1}

EXPECTED_REQUIREMENTS: Dict[str, List[Dict]] = {
    "GEMEENTE": [
        {"name": "BIO", "level": "verplicht", "category": "security"},
        {"name": "ISO 27001", "level": "waarschijnlijk", "category": "security"},
        {"name": "SROI", "level": "gebruikelijk", "category": "social"},
    ],
    "PROVINCIE": [
        {"name": "BIO", "level": "verplicht", "category": "security"},
        {"name": "ISO 27001", "level": "waarschijnlijk", "category": "security"},
        {"name": "SROI", "level": "gebruikelijk", "category": "social"},
    ],
    "WATERSCHAP": [
        {"name": "BIO", "level": "verplicht", "category": "security"},
        {"name": "ISO 27001", "level": "waarschijnlijk", "category": "security"},
        {"name": "SROI", "level": "gebruikelijk", "category": "social"},
    ],
    "GR": [
        {"name": "BIO", "level": "verplicht", "category": "security"},
        {"name": "ISO 27001", "level": "waarschijnlijk", "category": "security"},
        {"name": "SROI", "level": "gebruikelijk", "category": "social"},
    ],
    "RIJK": [
        {"name": "BIO", "level": "verplicht", "category": "security"},
        {"name": "ISO 27001", "level": "waarschijnlijk", "category": "security"},
        {"name": "DigiD", "level": "mogelijk", "category": "security"},
        {"name": "ISAE 3402", "level": "mogelijk", "category": "quality"},
    ],
    "ZBO": [
        {"name": "BIO", "level": "verplicht", "category": "security"},
        {"name": "ISO 27001", "level": "waarschijnlijk", "category": "security"},
        {"name": "DigiD", "level": "mogelijk", "category": "security"},
        {"name": "ISAE 3402", "level": "mogelijk", "category": "quality"},
    ],
    "RIJK_VITAAL": [
        {"name": "BIO", "level": "verplicht", "category": "security"},
        {"name": "ISO 27001", "level": "waarschijnlijk", "category": "security"},
        {"name": "ISAE 3402", "level": "waarschijnlijk", "category": "quality"},
        {"name": "NIS2", "level": "waarschijnlijk", "category": "security"},
    ],
    "ZORG": [
        {"name": "NEN 7510", "level": "verplicht", "category": "security"},
        {"name": "ISO 27001", "level": "waarschijnlijk", "category": "security"},
        {"name": "BIO", "level": "mogelijk", "category": "security"},
    ],
    "ONDERWIJS": [
        {"name": "ISO 27001", "level": "mogelijk", "category": "security"},
        {"name": "AVG/DPIA", "level": "waarschijnlijk", "category": "security"},
    ],
    "PUBLIEK_SOCIAAL": [
        {"name": "BIO", "level": "waarschijnlijk", "category": "security"},
        {"name": "PSO", "level": "waarschijnlijk", "category": "social"},
        {"name": "SROI", "level": "gebruikelijk", "category": "social"},
    ],
}


def classify_opdrachtgever(opdrachtgever: str) -> str:
    """Classify opdrachtgever into a category based on name."""
    name_lower = opdrachtgever.lower()

    # Special patterns
    if _RWS_PATTERN.search(opdrachtgever):
        return "RIJK_VITAAL"
    if _GR_PREFIX.search(opdrachtgever):
        return "GR"
    if _STICHTING_ONDERWIJS.search(opdrachtgever):
        return "ONDERWIJS"

    for category, keywords in OPDRACHTGEVER_RULES:
        for kw in keywords:
            if kw.lower() in name_lower:
                return category

    return "OVERIG"


def get_expected_requirements(
    opdrachtgever: str, segments: List[str]
) -> List[Dict[str, str]]:
    """Get expected certification requirements based on opdrachtgever type.

    Returns list of dicts with keys: name, category, level.
    Level is one of: verplicht, waarschijnlijk, gebruikelijk, mogelijk.
    """
    category = classify_opdrachtgever(opdrachtgever)
    reqs = EXPECTED_REQUIREMENTS.get(category, [])

    # Build result with deduplication by name (keep highest level)
    result: Dict[str, Dict] = {}
    for req in reqs:
        result[req["name"]] = {
            "name": req["name"],
            "category": req["category"],
            "level": req["level"],
        }

    # Cybersecurity segment upgrade: ISO 27001 → waarschijnlijk
    if "Cybersecurity" in segments:
        if "ISO 27001" in result:
            current = LEVEL_PRIORITY.get(result["ISO 27001"]["level"], 0)
            if current < LEVEL_PRIORITY["waarschijnlijk"]:
                result["ISO 27001"]["level"] = "waarschijnlijk"
        elif category != "OVERIG":
            result["ISO 27001"] = {
                "name": "ISO 27001",
                "category": "security",
                "level": "waarschijnlijk",
            }

    return list(result.values())


# ── Value Estimation ─────────────────────────────────────────────────────

EU_THRESHOLD_DIENSTEN = 221_000
EU_THRESHOLD_WERKEN = 5_538_000

# (opdrachtgever_type, segment_category) → (min, max)
# segment_category is derived from segment labels
_SEGMENT_CATEGORIES = {
    "Werkplek & Eindgebruikersbeheer": "infra",
    "Cloud & Hosting": "infra",
    "Netwerk & Connectiviteit": "infra",
    "Cybersecurity": "infra",
    "Applicatiebeheer": "applicatie",
    "Data & BI": "applicatie",
    "Full-service": "infra",
}

_VALUE_MATRIX: Dict[tuple, tuple] = {
    ("GEMEENTE", "infra"): (200_000, 1_000_000),
    ("GEMEENTE", "applicatie"): (100_000, 500_000),
    ("GR", "infra"): (300_000, 2_000_000),
    ("GR", "applicatie"): (300_000, 2_000_000),
    ("PROVINCIE", "infra"): (300_000, 2_000_000),
    ("PROVINCIE", "applicatie"): (300_000, 2_000_000),
    ("WATERSCHAP", "infra"): (200_000, 1_000_000),
    ("WATERSCHAP", "applicatie"): (200_000, 1_000_000),
    ("RIJK", "infra"): (500_000, 5_000_000),
    ("RIJK", "applicatie"): (500_000, 5_000_000),
    ("ZBO", "infra"): (500_000, 5_000_000),
    ("ZBO", "applicatie"): (500_000, 5_000_000),
    ("RIJK_VITAAL", "infra"): (500_000, 5_000_000),
    ("RIJK_VITAAL", "applicatie"): (500_000, 5_000_000),
    ("ONDERWIJS", "infra"): (50_000, 300_000),
    ("ONDERWIJS", "applicatie"): (50_000, 300_000),
    ("PUBLIEK_SOCIAAL", "infra"): (50_000, 300_000),
    ("PUBLIEK_SOCIAAL", "applicatie"): (50_000, 300_000),
    ("ZORG", "infra"): (100_000, 1_000_000),
    ("ZORG", "applicatie"): (100_000, 1_000_000),
}


def _format_eur(val: int) -> str:
    """Format integer value as '200K', '1M', '5.5M' etc."""
    if val >= 1_000_000:
        m = val / 1_000_000
        if m == int(m):
            return f"{int(m)}M"
        return f"{m:.1f}M".replace(".0M", "M")
    if val >= 1_000:
        k = val / 1_000
        if k == int(k):
            return f"{int(k)}K"
        return f"{k:.0f}K"
    return str(val)


def estimate_value(
    europees: bool,
    type_opdracht: str,
    opdrachtgever_type: str,
    segments: List[str],
    naam: str,
    beschrijving: str,
) -> Dict:
    """Estimate the monetary value range of a tender heuristically.

    Returns dict with keys: min_value, max_value, display, confidence.
    """
    # Determine segment categories present
    seg_cats = set()
    for seg in segments:
        cat = _SEGMENT_CATEGORIES.get(seg)
        if cat:
            seg_cats.add(cat)

    if not seg_cats and opdrachtgever_type == "OVERIG":
        return {"min_value": None, "max_value": None, "display": "?", "confidence": "laag"}

    # Collect ranges from matrix
    min_vals = []
    max_vals = []
    for cat in (seg_cats or ["infra"]):  # default to infra if no segments
        key = (opdrachtgever_type, cat)
        if key in _VALUE_MATRIX:
            lo, hi = _VALUE_MATRIX[key]
            min_vals.append(lo)
            max_vals.append(hi)

    if not min_vals:
        # Unknown opdrachtgever_type with segments — use a generic range
        return {"min_value": None, "max_value": None, "display": "?", "confidence": "laag"}

    # Broadest range: min of mins, max of maxes
    est_min = min(min_vals)
    est_max = max(max_vals)

    # EU floor: if europees=True, minimum is at least the EU threshold
    if europees:
        type_lower = (type_opdracht or "").lower()
        if "werken" in type_lower:
            eu_floor = EU_THRESHOLD_WERKEN
        else:
            eu_floor = EU_THRESHOLD_DIENSTEN
        est_min = max(est_min, eu_floor)
        if est_max < est_min:
            est_max = est_min * 3  # EU tender likely much larger

    # Confidence level
    if europees and seg_cats:
        confidence = "hoog"
    elif seg_cats:
        confidence = "midden"
    else:
        confidence = "laag"

    display = f"\u20ac{_format_eur(est_min)}-{_format_eur(est_max)}"
    return {
        "min_value": est_min,
        "max_value": est_max,
        "display": display,
        "confidence": confidence,
    }


# ── Signal Detection ─────────────────────────────────────────────────────

_DIENST_KEYWORDS = ["beheer", "onderhoud", "managed", "hosting", "monitoring"]
_TRANSITIE_KEYWORDS = [
    "huidige leverancier", "transitie", "huidige dienstverlener",
    "huidige omgeving", "huidige partij", "huidige contractant",
    "overname van", "overdracht",
]
_SYSTEM_CATEGORIES = {
    "salaris": ["salaris", "loon"],
    "hrm": ["hrm", "e-hrm", "personeels"],
    "klantvolg": ["klantvolg", "crm", "relatiebeheersysteem"],
    "erp": ["erp", "financieel systeem", "financieel pakket"],
    "zaak": ["zaaksysteem", "zaakgericht"],
    "dms": ["dms", "document management", "documentbeheer"],
}
_INFRA_SEGMENTS = {"Werkplek & Eindgebruikersbeheer", "Cloud & Hosting", "Netwerk & Connectiviteit"}
_HEAVY_REQUIREMENTS = {"verplicht", "waarschijnlijk"}


def _is_small_opdrachtgever(opdrachtgever: str, opdrachtgever_type: str) -> bool:
    """Check if opdrachtgever is a small organisation."""
    if opdrachtgever_type in ("ONDERWIJS", "PUBLIEK_SOCIAAL"):
        return True
    if opdrachtgever.lower().startswith("stichting"):
        return True
    return False


def _count_distinct_systems(text: str) -> int:
    """Count how many distinct system categories are mentioned."""
    text_lower = text.lower()
    count = 0
    for _cat, keywords in _SYSTEM_CATEGORIES.items():
        for kw in keywords:
            if kw in text_lower:
                count += 1
                break
    return count


def detect_signals(
    naam: str,
    beschrijving: str,
    opdrachtgever: str,
    opdrachtgever_type: str,
    type_opdracht: str,
    europees: bool,
    segments: List[str],
    certifications: List[Dict],
    expected_requirements: List[Dict],
    estimated_value: Dict,
) -> List[Dict]:
    """Detect noteworthy signals in a tender.

    Returns list of dicts with keys: type, icon, label, detail.
    """
    signals: List[Dict] = []
    text = f"{naam} {beschrijving}"
    text_lower = text.lower()

    # ── DISPROPORTIONEEL ──

    # D1: Small opdrachtgever + 3+ heavy requirements
    if _is_small_opdrachtgever(opdrachtgever, opdrachtgever_type):
        heavy_count = sum(
            1 for r in expected_requirements if r.get("level") in _HEAVY_REQUIREMENTS
        )
        if heavy_count >= 3:
            signals.append({
                "type": "disproportioneel",
                "icon": "warning",
                "label": "Zware eisen voor kleine opdrachtgever",
                "detail": f"{heavy_count} zware vereisten bij {opdrachtgever_type}",
            })

    # D2: Low max value + broad scope
    max_val = estimated_value.get("max_value")
    if max_val is not None and max_val <= 300_000:
        n_segments = len([s for s in segments if s != "Full-service"])
        n_systems = _count_distinct_systems(text)
        if n_segments >= 3 or n_systems >= 3:
            signals.append({
                "type": "disproportioneel",
                "icon": "warning",
                "label": "Brede scope voor beperkt budget",
                "detail": f"{n_segments} segmenten, {n_systems} systemen, max \u20ac{_format_eur(max_val)}",
            })

    # D3: Type=Leveringen but description has service characteristics
    type_lower = (type_opdracht or "").lower()
    if "leveringen" in type_lower:
        dienst_found = [kw for kw in _DIENST_KEYWORDS if kw in text_lower]
        if dienst_found:
            signals.append({
                "type": "disproportioneel",
                "icon": "warning",
                "label": "Levering of dienst?",
                "detail": f"Type is Leveringen maar beschrijving bevat: {', '.join(dienst_found)}",
            })

    # ── OPVALLEND ──

    # O1: GR or gemeenschappelijke regeling
    if opdrachtgever_type == "GR" or "gemeenschappelijke regeling" in text_lower:
        signals.append({
            "type": "opvallend",
            "icon": "puzzle",
            "label": "Meerdere organisaties, een contract",
            "detail": "Gemeenschappelijke regeling \u2014 meerdere deelnemende organisaties",
        })

    # O2: Werkplek + Cybersecurity together
    seg_set = set(segments)
    if "Werkplek & Eindgebruikersbeheer" in seg_set and "Cybersecurity" in seg_set:
        signals.append({
            "type": "opvallend",
            "icon": "puzzle",
            "label": "Werkplek met security-focus",
            "detail": "Combineert werkplekbeheer met cybersecurity",
        })

    # ── MSP-KANSEN ──

    # K1: GEMEENTE + infra + diensten + ≥200K
    if opdrachtgever_type == "GEMEENTE":
        has_infra = bool(seg_set & _INFRA_SEGMENTS)
        has_dienst = _text_has_any(text, _DIENST_KEYWORDS)
        min_val = estimated_value.get("min_value")
        if has_infra and has_dienst and min_val is not None and min_val >= 200_000:
            signals.append({
                "type": "msp-kans",
                "icon": "check",
                "label": "Sweet spot MSP",
                "detail": "Gemeente + infra + dienstenkenmerken + \u20ac200K+",
            })

    # K2: Possible supplier switch
    if any(kw in text_lower for kw in _TRANSITIE_KEYWORDS):
        signals.append({
            "type": "msp-kans",
            "icon": "check",
            "label": "Mogelijke leverancierswisseling",
            "detail": "Tekst suggereert overstap van huidige leverancier",
        })

    return signals


def detect_certifications(naam: str, beschrijving: str) -> List[Dict[str, str]]:
    """Detect certification requirements mentioned in a tender.

    Returns list of dicts with keys: name, category, implied (bool).
    Explicit matches are high-confidence. Implied matches are shown with "?".
    """
    text = f"{naam} {beschrijving}"
    found = []
    found_names = set()

    # Explicit certifications
    for cert in CERTIFICATIONS:
        if re.search(cert["pattern"], text):
            found.append({
                "name": cert["name"],
                "category": cert["category"],
                "implied": False,
            })
            found_names.add(cert["name"])

    # Implied certifications (only if not already found explicitly)
    for cert in IMPLIED_CERTIFICATIONS:
        if cert["name"] in found_names:
            continue
        skip = False
        for excl in cert.get("excludes", []):
            if excl in found_names:
                skip = True
                break
        if skip:
            continue
        if re.search(cert["pattern"], text):
            found.append({
                "name": cert["name"] + "?",
                "category": cert["category"],
                "implied": True,
            })
            found_names.add(cert["name"])

    return found
