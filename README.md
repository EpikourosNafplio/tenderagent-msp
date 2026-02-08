# TenderAgent MSP v2.5

AI-gestuurde API voor IT-aanbestedingen in Nederland, specifiek voor Managed Service Providers (25-100 FTE).

## Features

**Core (werkt zonder dataset):**
- 7 MSP-segmenten met sterke/zwakke keyword-matching
- Opdrachtgever-classificatie (gemeente, GR, zorg, onderwijs, etc.)
- Afgeleide certificeringsvereisten per opdrachtgevertype (BIO, ISO 27001, NEN 7510, etc.)
- MSP-fit scoring (filtert applicatiesoftware vs. managed services)
- Geschatte opdrachtwaarde (bandbreedte op basis van opdrachtgevertype + scope)
- Spanning-detectie (disproportionele eisen, opvallende combinaties, MSP-kansen)

**Dataset-features (vereist TenderNed openbare dataset):**
- Gunningshistorie per opdrachtgever (wie won eerder, hoeveel inschrijvingen, geraamde waarde)
- Herhalingspatronen (contracten die aflopen, verwachte heraanbestedingen)
- Vooraankondigingen en marktconsultaties (wat komt eraan)

## Installatie

```bash
pip3 install -r requirements.txt
```

## Gebruik

### Stap 1: Start de API (werkt direct)

```bash
python3 main.py
```

Dashboard: http://localhost:8000

### Stap 2: Laad de TenderNed dataset (optioneel maar aanbevolen)

Download de dataset van https://www.tenderned.nl/cms/nl/aanbesteden-in-cijfers/datasets-aanbestedingen

```bash
# Excel (alle jaren in een bestand)
python3 import_dataset.py /pad/naar/tenderned_2016_2025.xlsx

# JSON (per jaar, meerdere bestanden)
python3 import_dataset.py /pad/naar/2024.json /pad/naar/2025.json
```

Het script maakt een SQLite database aan in `data/tenderned_historie.db`.
Herstart de API om de data te gebruiken.

## API Endpoints

| Endpoint | Beschrijving |
|----------|-------------|
| GET /api/v1/discover | Overzicht van alle endpoints |
| GET /api/v1/tenders | Actuele tenders met MSP-analyse |
| GET /api/v1/tenders/{id} | Tender detail |
| GET /api/v1/stats | Statistieken |
| GET /api/v1/cpv-codes | Gemonitorde CPV-codes |
| GET /api/v1/gunningshistorie/{opdrachtgever} | Gunningshistorie (dataset vereist) |
| GET /api/v1/vooraankondigingen | Vooraankondigingen (dataset vereist) |
| GET /api/v1/herhalingspatronen | Verwachte heraanbestedingen (dataset vereist) |

### Filteropties /api/v1/tenders

- `min_score` - Minimale IT-relevantiescore (0-100)
- `min_msp_fit` - Minimale MSP-fit score
- `msp_label` - Filter: relevant, mogelijk, niet
- `segment` - Filter op MSP-segment (bijv. "werkplek", "cloud")
- `alleen_open` - Alleen tenders met openstaande sluitingsdatum
- `alleen_signalen` - Alleen tenders met spanning-signalen
- `sorteer` - Sorteer op: msp_fit (default), relevantie, waarde, signalen

### Voorbeelden

```bash
# MSP-relevante tenders, gesorteerd op fit
curl "http://localhost:8000/api/v1/tenders?msp_label=relevant"

# Tenders met spanning-signalen (TvdW-kandidaten)
curl "http://localhost:8000/api/v1/tenders?alleen_signalen=true&sorteer=signalen"

# Cloud-tenders bij overheid
curl "http://localhost:8000/api/v1/tenders?segment=cloud&msp_label=relevant"

# Gunningshistorie gemeente Amersfoort
curl "http://localhost:8000/api/v1/gunningshistorie/Amersfoort"

# Verwachte heraanbestedingen
curl "http://localhost:8000/api/v1/herhalingspatronen"
```

## MSP-segmenten

| Segment | Voorbeelden |
|---------|-------------|
| Werkplek & Eindgebruikersbeheer | Werkplekbeheer, Microsoft 365, servicedesk, endpoint management |
| Cloud & Hosting | IaaS, PaaS, hosting, compute, storage, backup, VMware |
| Cybersecurity & Informatiebeveiliging | SOC, SIEM, penetratietests, security monitoring |
| Netwerk & Connectiviteit | SD-WAN, LAN/WAN, firewall, wifi, connectiviteit |
| Applicatiebeheer & Implementatie | Zaaksystemen, ERP/CRM, softwareimplementatie |
| Data & Business Intelligence | Datawarehouse, Power BI, analytics, ETL |
| Full-service IT-partner | 3+ segmenten in een tender |

## Spanning-signalen

| Icoon | Type | Voorbeeld |
|-------|------|-----------|
| ⚠️ | Disproportioneel | Zware eisen voor kleine opdrachtgever |
| 🧩 | Opvallend | Werkplek met security-focus, leverancierswisseling |
| ✅ | MSP-kans | Sweet spot MSP, cloud bij overheid |

## Projectstructuur

```
tenderagent-msp/
  main.py              - FastAPI applicatie
  import_dataset.py    - TenderNed dataset import
  requirements.txt
  data/
    tenderned_historie.db  - SQLite (na import)
  Dockerfile
  docker-compose.yml
```

## Gemaakt voor

Epikouros Trading & Consulting Company
https://github.com/martinvanleeuwen/tenderagent-msp
