# TenderAgent MSP — Handleiding

## Wat is dit?

De TenderAgent scant automatisch alle publicaties op TenderNed en filtert daar de IT-tenders uit die relevant zijn voor Managed Service Providers. Elke tender wordt verrijkt met:

- Een MSP-fit score (is dit iets voor een MSP van 25-100 man?)
- MSP-segmenten (werkplek, cloud, security, netwerk, applicatie, data)
- Verwachte certificeringsvereisten (BIO, ISO 27001, NEN 7510 — afgeleid uit het type opdrachtgever)
- Een geschatte opdrachtwaarde (bandbreedte op basis van opdrachtgevertype en scope)
- Spanning-signalen (disproportionele eisen, opvallende combinaties, MSP-kansen)
- Gunningshistorie (wie won eerder bij deze opdrachtgever, uit de TenderNed dataset 2016-2025)


## Starten en stoppen

### Starten

Open Terminal, ga naar de map, start de server:

```
cd /Users/martinvanleeuwen/tenderagent-msp
python main.py
```

De API draait dan op http://localhost:8000

### Stoppen

Druk `Ctrl+C` in Terminal. Of sluit Terminal.

### Opnieuw starten (als poort bezet is)

```
lsof -ti:8000 | xargs kill
python main.py
```


## Dagelijks gebruik

### De API openen

Ga in je browser naar http://localhost:8000/docs voor het technische overzicht van alle endpoints. Of gebruik de URLs hieronder direct.

### Workflow: Tender van de Week selecteren

Dit is de snelste route naar TvdW-kandidaten:

**Stap 1 — Tenders met signalen bekijken**

```
http://localhost:8000/api/v1/tenders?alleen_signalen=true&sorteer=signalen
```

Dit toont alleen tenders waar de TenderAgent iets opvallends heeft gevonden. Drie soorten signalen:

| Icoon | Betekenis | Voorbeeld |
|-------|-----------|-----------|
| ⚠️ | Disproportioneel | Zware eisen voor kleine opdrachtgever, brede scope voor klein budget |
| 🧩 | Opvallende combinatie | Werkplek met security-focus, leverancierswisseling, meerdere organisaties |
| ✅ | MSP-kans | Sweet spot (overheid + werkplek + diensten), cloud bij overheid |

**Stap 2 — MSP-relevante tenders bekijken**

```
http://localhost:8000/api/v1/tenders?msp_label=relevant
```

Dit filtert op tenders die écht bij een MSP passen. Sorteert op MSP-fit score (hoogste eerst).

**Stap 3 — Gunningshistorie checken**

Als je een interessante tender hebt gevonden, check wie er eerder won:

```
http://localhost:8000/api/v1/gunningshistorie/Amersfoort
```

Vervang "Amersfoort" door de naam van de opdrachtgever (of een deel ervan).

### Workflow: Vooruitkijken

**Wat komt eraan (vooraankondigingen en marktconsultaties):**

```
http://localhost:8000/api/v1/vooraankondigingen
```

Dit zijn tenders die nog niet live zijn maar waar opdrachtgevers al over nadenken. Goud voor proactieve benadering.

**Contracten die aflopen (herhalingspatronen):**

```
http://localhost:8000/api/v1/herhalingspatronen
```

IT-diensten die 3-5 jaar geleden zijn gegund en dus binnenkort opnieuw worden aanbesteed. Dit is de "tender die niemand anders ziet" — je ziet hem voordat hij gepubliceerd is.


## Alle filteropties

De hoofdendpoint `/api/v1/tenders` heeft deze filters:

| Parameter | Waarden | Wat het doet |
|-----------|---------|--------------|
| `msp_label` | relevant, mogelijk, niet | Filter op MSP-geschiktheid |
| `min_msp_fit` | getal (bijv. 20) | Minimale MSP-fit score |
| `min_score` | 0-100 | Minimale IT-relevantiescore |
| `segment` | werkplek, cloud, security, netwerk, applicatie, data | Filter op MSP-segment |
| `alleen_signalen` | true | Alleen tenders met spanning-signalen |
| `alleen_open` | true | Alleen tenders die nog open zijn |
| `zoekterm` | tekst | Vrij zoeken in naam en beschrijving |
| `sorteer` | msp_fit, relevantie, waarde, signalen | Sorteervolgorde |
| `max_results` | getal | Maximum aantal resultaten (standaard 50) |

Combineren kan:

```
http://localhost:8000/api/v1/tenders?msp_label=relevant&segment=cloud&alleen_open=true
```


## Wat de velden betekenen

### MSP-fit score en label

De MSP-fit score bepaalt of een tender past bij een MSP van 25-100 FTE:

| Label | Score | Betekenis |
|-------|-------|-----------|
| MSP-relevant | > 20 | Diensten, MSP-kernactiviteiten, overheidsopdracht |
| Mogelijk relevant | 0-20 | Deels passend, nader bekijken |
| Niet MSP | < 0 | Applicatiesoftware, fysieke infra, leveringen |

Hoe de score wordt berekend:
- +20 als het type opdracht "Diensten" is
- +15 als de scope werkplekbeheer, cloud, hosting of infra bevat
- +10 als de opdrachtgever gemeente, provincie, waterschap of GR is
- +5 als meerdere MSP-segmenten matchen
- -15 als het applicatiesoftware is (ERP, HRM, WOZ)
- -10 als het fysieke infrastructuur is (glasvezel aanleg, camerabewaking)
- -10 als het type "Leveringen" is

### MSP-segmenten

Elke tender krijgt een of meer segmenten op basis van sterke keywords in naam en beschrijving:

| Segment | Sterke keywords |
|---------|-----------------|
| Werkplek & Eindgebruikersbeheer | werkplekbeheer, endpoint management, M365, servicedesk, ITSM |
| Cloud & Hosting | hosting, IaaS, PaaS, compute, storage, backup, VMware, datacenter |
| Cybersecurity & Informatiebeveiliging | SOC, SIEM, penetratietest, cybersecurity, incident response |
| Netwerk & Connectiviteit | SD-WAN, LAN, WAN, firewall, wifi, connectiviteit |
| Applicatiebeheer & Implementatie | applicatiebeheer, zaaksysteem, ITSM, ERP/CRM-implementatie |
| Data & Business Intelligence | datawarehouse, Power BI, Tableau, ETL, data analytics |
| Full-service IT-partner | Automatisch als 3+ segmenten matchen |

### Verwachte vereisten

Certificeringen die niet in de publicatietekst staan maar wettelijk verplicht of gebruikelijk zijn op basis van het type opdrachtgever:

| Opdrachtgevertype | Verplicht | Waarschijnlijk | Gebruikelijk |
|--------------------|-----------|----------------|--------------|
| Gemeente, provincie, waterschap, GR | BIO | ISO 27001 | SROI |
| Rijksoverheid, ZBO | BIO | ISO 27001 | DigiD, ISAE 3402 |
| Vitale infra (ProRail, RWS) | BIO | ISO 27001, ISAE 3402, NIS2 | — |
| Zorg | NEN 7510 | ISO 27001 | BIO |
| Onderwijs | — | — | ISO 27001 |

### Geschatte waarde

Als TenderNed geen bedrag vermeldt (wat vaak het geval is), schat de TenderAgent een bandbreedte:

| Opdrachtgever + scope | Bandbreedte |
|------------------------|-------------|
| Gemeente + IT-infra | €200K-1M |
| Gemeente + applicatie | €100K-500K |
| GR/samenwerkingsverband | €300K-2M |
| Rijksoverheid/ZBO | €500K-5M |
| Onderwijs | €50K-300K |
| Europese aanbesteding (minimum) | ≥€221K |

De bron staat erbij: "exact" (uit TenderNed), "bandbreedte" (geschat), of "onbekend".


## Dataset bijwerken

De historische data (gunningshistorie, herhalingspatronen, vooraankondigingen) komt uit de TenderNed openbare dataset. Die wordt een paar keer per jaar bijgewerkt.

### Nieuwe dataset importeren

1. Download de nieuwste dataset van https://www.tenderned.nl/cms/nl/aanbesteden-in-cijfers/datasets-aanbestedingen
2. Open Terminal:

```
cd /Users/martinvanleeuwen/tenderagent-msp
python import_dataset.py /pad/naar/nieuwe_dataset.xlsx
```

3. Herstart de server:

```
lsof -ti:8000 | xargs kill
python main.py
```


## Technische details

### Bestanden

```
tenderagent-msp/
  main.py              — De v2 API (standalone versie)
  app/                 — De modulaire versie (wat nu draait)
    main.py            — FastAPI applicatie
    scoring.py         — MSP-fit en relevantie scoring
    segments.py        — MSP-segmenten en opdrachtgever-classificatie
    database.py        — SQLite verbinding voor historische data
    historie.py        — Gunningshistorie en herhalingspatronen
    tenderned.py       — TenderNed API-integratie
    cpv_codes.py       — CPV-code definities
  import_dataset.py    — Dataset import script
  data/
    tenderned_historie.db  — SQLite database (125.756 publicaties)
  requirements.txt
  Dockerfile
  docker-compose.yml
```

### Endpoints overzicht

| Endpoint | Wat het doet |
|----------|-------------|
| GET /api/v1/discover | API-overzicht en status |
| GET /api/v1/tenders | Actuele tenders met alle analyses |
| GET /api/v1/tenders/{id} | Detail van één tender |
| GET /api/v1/stats | Statistieken (aantallen, verdeling) |
| GET /api/v1/cpv-codes | Welke CPV-codes worden gemonitord |
| GET /api/v1/gunningshistorie/{naam} | Wie won eerder bij deze opdrachtgever |
| GET /api/v1/vooraankondigingen | Vooraankondigingen en marktconsultaties |
| GET /api/v1/herhalingspatronen | Contracten die aflopen |
| POST /api/v1/refresh | Cache verversen (nieuwe data ophalen) |
| GET / | Dashboard (webinterface) |


## Veelgestelde vragen

**Waarom staat E-HRM bovenaan als "Mogelijk relevant"?**
De MSP-fit scoring filtert applicatiesoftware eruit (-15 punten), maar als het type opdracht "Diensten" is (+20) en er IT-keywords in staan, kan de netto score nog positief zijn. Gebruik `msp_label=relevant` om alleen échte MSP-tenders te zien.

**Waarom zijn sommige certificeringen "verwacht" en niet "bevestigd"?**
De TenderAgent leidt certificeringen af uit het type opdrachtgever (BIO is verplicht voor gemeenten, NEN 7510 voor zorg). De daadwerkelijke eisen staan in de aanbestedingsdocumenten op TenderNed, niet in de publicatietekst die de API levert.

**Hoe actueel is de data?**
De live tenders komen rechtstreeks van de TenderNed API (actueel). De gunningshistorie komt uit de openbare dataset (bijgewerkt tot het moment dat je `import_dataset.py` hebt gedraaid).

**Kan ik dit ook op mijn telefoon gebruiken?**
Zolang je Mac aanstaat en de server draait: ja. Ga naar http://[je-mac-ip]:8000 op je telefoon (zelfde wifi-netwerk).
