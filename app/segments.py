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
