"""MSP segment labelling and certification detection for tenders."""

import re
from typing import List, Dict

# ── MSP Segments ─────────────────────────────────────────────────────────

SEGMENTS = {
    "Werkplek & Eindgebruikersbeheer": {
        "cpv_requires_keyword": True,
        "cpv": ["30200000", "30210000", "30230000", "48000000"],
        "keywords": [
            "werkplek", "werkplekbeheer", "desktop", "laptop",
            "modern workplace", "microsoft 365", "m365", "office 365",
            "telefonie", "servicedesk", "endpoint", "itsm",
            "printbeheer", "client management",
            "print", "printer", "multifunctional", "mfp", "repro",
            "kantoorautomatisering", "dwr", "digitale werkomgeving",
        ],
    },
    "Cloud & Hosting": {
        "cpv_requires_keyword": True,
        "cpv": ["72400000", "72410000", "72300000"],
        "keywords": [
            "cloud", "hosting", "iaas", "paas", "saas", "azure", "aws",
            "migratie", "hybride cloud", "datacenter", "virtualisatie",
            "vmware", "containerisatie",
            "as a service", "online platform", "webapplicatie",
        ],
    },
    "Cybersecurity": {
        "cpv_requires_keyword": True,
        "cpv": ["48730000", "72200000"],
        "keywords": [
            "security", "cybersecurity", "informatiebeveiliging",
            "soc", "siem", "soar", "penetratietest", "pentest",
            "vulnerability", "bio", "nis2", "dora",
            "dreigingsanalyse", "incident response",
            "toegangscontrole", "access control", "identity", "iam",
            "authenticatie", "autorisatie", "beveiligingssysteem",
        ],
    },
    "Netwerk & Connectiviteit": {
        "cpv_requires_keyword": False,
        "cpv": ["64200000", "32400000", "32420000"],
        "keywords": [
            "netwerk", "lan", "wan", "sd-wan", "firewall",
            "connectiviteit", "telecom", "vpn", "switching",
            "routing", "wifi", "wlan",
        ],
    },
    "Applicatiebeheer": {
        "cpv_requires_keyword": True,
        "cpv": ["72200000", "72260000", "48000000"],
        "keywords": [
            "applicatiebeheer", "softwareimplementatie", "erp", "crm",
            "zaaksysteem", "dms", "integratie", "api",
            "maatwerk software", "platform", "portaal",
            "systeem", "applicatie", "hrm", "salarisadministratie",
            "klantvolgsysteem", "cms", "toegangscontrole",
            "itsm", "servicemanagement", "ticketing",
            "document management", "informatiebeheer",
        ],
    },
    "Data & BI": {
        "cpv_requires_keyword": False,
        "cpv": ["72300000", "48600000"],
        "keywords": [
            "data", "bi", "business intelligence", "dashboard",
            "analytics", "datawarehouse", "datafundament",
            "data-integratie", "rapportage", "power bi", "tableau",
        ],
    },
}

FULL_SERVICE_LABEL = "Full-service"
FULL_SERVICE_THRESHOLD = 3


def _text_has_keyword(text: str, keywords: list) -> bool:
    """Check if any keyword appears in text as a substring (case-insensitive)."""
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

    Uses substring matching for keywords and prefix matching for CPV codes.
    Returns list of segment labels.
    """
    text = f"{naam} {beschrijving}"
    matched = []

    for label, config in SEGMENTS.items():
        has_keyword = _text_has_keyword(text, config["keywords"])
        has_cpv = _cpv_matches(cpv_codes, config["cpv"])

        if has_keyword:
            matched.append(label)
        elif has_cpv and not config["cpv_requires_keyword"]:
            matched.append(label)
        elif has_cpv and has_keyword:
            matched.append(label)

    if len(matched) >= FULL_SERVICE_THRESHOLD:
        matched.append(FULL_SERVICE_LABEL)

    return matched


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
