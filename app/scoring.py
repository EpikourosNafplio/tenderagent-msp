"""Relevance scoring for IT/MSP tenders based on keyword matching."""

import re
from typing import List

# High relevance keywords (Dutch + English) — directly MSP/IT staffing related
HIGH_KEYWORDS = [
    "MSP", "managed service", "inhuur", "detachering", "flexibele schil",
    "ICT-inhuur", "IT-inhuur", "raamovereenkomst ICT", "raamovereenkomst IT",
    "DAS ICT", "DAS IT", "dynamisch aankoopsysteem",
    "IT-personeel", "ICT-personeel", "IT-professionals",
    "softwareontwikkeling", "software development",
    "applicatiebeheer", "application management",
    "cloud", "SaaS", "IaaS", "PaaS",
    "cybersecurity", "informatiebeveiliging",
    "data center", "datacentrum", "hosting",
    "werkplekbeheer", "werkplekdiensten",
    "IT-beheer", "ICT-beheer", "IT-dienstverlening",
    "system integration", "systeemintegratie",
    "CRM", "HRM-systeem",
    "netwerk", "infrastructuur",
    "DevOps", "agile", "scrum",
    "toegangscontrolesysteem", "servicemanagementsysteem",
    "klantportaal", "datadistributie",
]

# Medium relevance keywords
MEDIUM_KEYWORDS = [
    "digitalisering", "digitale transformatie",
    "informatievoorziening", "informatiesysteem",
    "licentie", "software", "applicatie",
    "server", "storage", "backup",
    "helpdesk", "servicedesk", "support",
    "migratie", "implementatie",
    "advies", "consultancy",
    "project management", "projectmanagement",
    "telefonie", "telecom", "telecommunicatie",
    "website", "webapplicatie", "portaal",
    "database", "databank",
    "training ICT", "opleiding IT",
]

# Negative keywords — reduce score when present (non-IT domains)
NEGATIVE_KEYWORDS = [
    "bouw", "wegenbouw", "groenvoorziening", "grondwerk",
    "schoonmaak", "catering", "beveiliging gebouw",
    "medisch", "medicijn", "zorg", "huisarts",
    "transport", "vervoer", "busvervoer",
    "meubilair", "kantoormeubel",
    "drukwerk", "print",
]

# CPV code prefixes that indicate IT/MSP relevance
IT_CPV_PREFIXES = ("72", "48", "302", "642")

# Precompile patterns (case-insensitive)
_high_patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in HIGH_KEYWORDS]
_medium_patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in MEDIUM_KEYWORDS]
_negative_patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in NEGATIVE_KEYWORDS]


def _cpv_bonus(cpv_codes: List[dict]) -> int:
    """Return +25 if any CPV code starts with an IT-relevant prefix."""
    for cpv in cpv_codes:
        code = cpv.get("code", "").split("-")[0]
        if code.startswith(IT_CPV_PREFIXES):
            return 25
    return 0


def score_tender(title: str, description: str, cpv_codes: List[dict] = None) -> dict:
    """Score a tender for IT/MSP relevance.

    Returns dict with:
        score: 0-100 relevance score
        level: "hoog" / "midden" / "laag"
        matched_keywords: list of matched keyword strings
    """
    text = f"{title} {description}"

    high_matches = [kw for kw, pat in zip(HIGH_KEYWORDS, _high_patterns) if pat.search(text)]
    medium_matches = [kw for kw, pat in zip(MEDIUM_KEYWORDS, _medium_patterns) if pat.search(text)]
    negative_matches = [kw for kw, pat in zip(NEGATIVE_KEYWORDS, _negative_patterns) if pat.search(text)]

    score = len(high_matches) * 15 + len(medium_matches) * 5 - len(negative_matches) * 10

    # CPV code bonus
    cpv_bonus = _cpv_bonus(cpv_codes or [])
    score += cpv_bonus

    score = max(0, min(100, score))

    if score >= 50:
        level = "hoog"
    elif score >= 20:
        level = "midden"
    else:
        level = "laag"

    return {
        "score": score,
        "level": level,
        "matched_keywords": high_matches + medium_matches,
        "negative_keywords": negative_matches,
        "cpv_bonus": cpv_bonus,
    }
