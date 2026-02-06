# TenderAgent MSP

FastAPI applicatie voor het automatisch ontdekken van Nederlandse IT-aanbestedingen die relevant zijn voor Managed Service Providers (MSP's).

Haalt live data op van de [TenderNed API](https://www.tenderned.nl), filtert op 36 IT/MSP-relevante CPV-codes, en scoort tenders op relevantie via keyword matching en CPV-code analyse.

## Features

- **Live TenderNed data** — haalt 200 recente publicaties op (10 pagina's)
- **CPV-code filtering** — 36 IT-relevante codes (72xxx, 48xxx, 302xx, 642xx)
- **Relevantie-scoring** — keyword matching (hoog/midden/laag) + CPV-bonus (+25 punten)
- **SQLite cache** — 30 minuten TTL, handmatig te verversen
- **REST API** — JSON endpoints met filtering en paginering

## Quickstart

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://localhost:8000/docs voor de Swagger UI.

## Docker

```bash
docker build -t tenderagent-msp .
docker run -p 8000:8000 tenderagent-msp
```

## API Endpoints

| Methode | Endpoint | Beschrijving |
|---------|----------|--------------|
| GET | `/api/v1/discover` | Ontdek IT-tenders (ververst cache indien nodig) |
| GET | `/api/v1/tenders` | Lijst met filtering en paginering |
| GET | `/api/v1/tenders/{id}` | Enkele tender op publicatie-ID |
| GET | `/api/v1/stats` | Statistieken per relevantie, type en procedure |
| GET | `/api/v1/cpv-codes` | Alle 36 IT/MSP CPV-codes |
| POST | `/api/v1/refresh` | Forceer cache-verversing |

### Query parameters

**`/api/v1/discover`** en **`/api/v1/tenders`**:
- `min_score` — minimale relevantiescore (0-100)
- `level` — filter op `hoog`, `midden` of `laag`

**`/api/v1/tenders`** (extra):
- `type_opdracht` — `Diensten`, `Leveringen` of `Werken`
- `limit` — aantal resultaten (default 50, max 500)
- `offset` — paginering offset

## Relevantie-scoring

Elke tender krijgt een score op basis van:

| Component | Punten |
|-----------|--------|
| Hoog-relevantie keyword (bijv. SaaS, cybersecurity, inhuur) | +15 per match |
| Midden-relevantie keyword (bijv. software, implementatie) | +5 per match |
| IT-relevante CPV-code (72/48/302/642) | +25 bonus |
| Negatief keyword (bijv. bouw, medisch, transport) | -10 per match |

**Niveaus:** hoog (50+), midden (20-49), laag (0-19)

## Projectstructuur

```
tenderagent-msp/
├── app/
│   ├── main.py          # FastAPI app en endpoints
│   ├── tenderned.py     # TenderNed API client
│   ├── cpv_codes.py     # 36 IT/MSP CPV-codes
│   ├── scoring.py       # Relevantie-scoring engine
│   └── database.py      # SQLite cache
├── requirements.txt
├── Dockerfile
└── README.md
```
