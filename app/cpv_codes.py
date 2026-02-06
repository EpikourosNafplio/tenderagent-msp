"""IT/MSP-relevant CPV codes for Dutch tender filtering."""

from typing import Dict, Set

# 37 IT/MSP-relevant CPV codes with descriptions
CPV_CODES: Dict[str, str] = {
    # IT Services (72xxxxxx)
    "72000000": "IT-diensten: adviezen, softwareontwikkeling, internet en ondersteuning",
    "72100000": "Advies inzake hardware",
    "72200000": "Softwareprogrammering en -advies",
    "72210000": "Programmering van softwarepakketten",
    "72220000": "Advies inzake systemen en technisch advies",
    "72230000": "Ontwikkeling van gebruikerspecifieke software",
    "72240000": "Systeemanalyse en programmering",
    "72250000": "Systeem- en ondersteuningsdiensten",
    "72260000": "Diensten in verband met software",
    "72300000": "Uitwisseling van gegevens",
    "72310000": "Gegevensverwerking",
    "72320000": "Databanken",
    "72400000": "Internetdiensten",
    "72500000": "Informaticadiensten",
    "72600000": "Diensten voor computerondersteuning en -advies",
    "72700000": "Computernetwerkdiensten",
    "72800000": "Computeraudit- en computertestdiensten",
    "72900000": "Computerback-up en computercatalogisering",
    # Software (48xxxxxx)
    "48000000": "Software en informatiesystemen",
    "48100000": "Branchespecifiek softwarepakket",
    "48200000": "Software voor netwerken, internet en intranet",
    "48300000": "Software voor het aanmaken van documenten, tekeningen, beelden, dienstregelingen en productiviteit",
    "48400000": "Software voor zakelijke transacties en persoonlijke zaken",
    "48500000": "Communicatie- en multimediasoftware",
    "48600000": "Software voor databanken en -exploitatie",
    "48700000": "Hulpprogramma's voor softwarepakketten",
    "48800000": "Informatiesystemen en servers",
    "48900000": "Diverse software en computersystemen",
    # Hardware (30xxxxxx)
    "30200000": "Computeruitrusting en -benodigdheden",
    "30210000": "Machines voor gegevensverwerking (hardware)",
    "30230000": "Computerapparatuur",
    # Telecom (64xxxxxx)
    "64200000": "Telecommunicatiediensten",
    "64210000": "Telefoon- en datatransmissiediensten",
    "64220000": "Telecommunicatiediensten, met uitzondering van telefoon- en datatransmissiediensten",
    # Managed services
    "79500000": "Kantoorgerelateerde ondersteunende diensten",
    "50300000": "Reparatie, onderhoud en aanverwante diensten voor pc's, kantooruitrusting, telecommunicatie- en audiovisuele uitrusting",
}

# Set of just the codes for fast lookup
CPV_CODE_SET: Set[str] = set(CPV_CODES.keys())


def matches_cpv(code: str) -> bool:
    """Check if a CPV code (with or without -X suffix) matches our IT/MSP list."""
    # Strip the "-5" check digit suffix if present: "72000000-5" -> "72000000"
    clean = code.split("-")[0].strip()
    # Exact match
    if clean in CPV_CODE_SET:
        return True
    # Parent match: "72413000" starts with "72400000"[:3] = "724" -> check parent
    for cpv in CPV_CODE_SET:
        if clean.startswith(cpv[:3]) and cpv.endswith("00000"):
            return True
    return False
