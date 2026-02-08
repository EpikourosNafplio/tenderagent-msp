# TenderAgent MSP v2.5 — Handleiding

## Wat is dit?

De TenderAgent scant automatisch alle publicaties op TenderNed en filtert daar de IT-tenders uit die relevant zijn voor Managed Service Providers. Elke tender wordt verrijkt met:

- Een IT-relevantie gate (filtert niet-IT tenders volledig weg)
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
python3 main.py
```

De server draait dan op http://localhost:8000. Het dashboard opent direct in je browser.

### Stoppen

Druk `Ctrl+C` in Terminal. Of sluit Terminal.

### Opnieuw starten (als poort bezet is)

```
kill $(lsof -ti:8000) 2>/dev/null
python3 main.py
```


## Het dashboard

Open http://localhost:8000 in je browser. Je ziet:

### Bovenbalk — tellers

| Teller | Wat het toont |
|--------|--------------|
| IT-tenders | Totaal aantal tenders dat door de IT-filter komt |
| MSP-relevant | Tenders met MSP-fit > 20 |
| Met signalen | Tenders waar iets opvallends is gevonden |
| MSP-kansen | Tenders met een positief kans-signaal |
| Nog open | Tenders waar je nog op kunt inschrijven |
| Herhalingen | Contracten die binnenkort aflopen |
| Vooraank. | Vooraankondigingen en marktconsultaties |

### Tabs

- **Tenders** — actuele IT-tenders van TenderNed
- **Herhalingen** — contracten die 3-5 jaar geleden zijn gegund en dus binnenkort opnieuw worden aanbesteed
- **Vooraankondigingen** — tenders die nog niet live zijn maar waar opdrachtgevers al over nadenken

### Filterknoppen

| Filter | Wat het doet |
|--------|-------------|
| Alle | Alle IT-tenders |
| MSP-relevant | Alleen tenders met MSP-fit > 20 |
| Met signalen | Alleen tenders met spanning-signalen |
| MSP-kansen | Alleen tenders met een kans-signaal |
| Nog open | Alleen tenders die nog niet gesloten zijn |

### Zoekbalk

Type een naam of opdrachtgever om te filteren. Werkt direct.

### Tender-kaarten

Elke tender toont:
- Naam en opdrachtgever
- Type opdrachtgever (Gemeente, Provincie, Rijk, etc.)
- Geschatte waarde
- Dagen tot sluiting (of "Gesloten")
- MSP-segmenten (gekleurde badges)
- MSP-fit label en score
- Signalen (indien aanwezig)

Klik op een kaart om de details te zien (beschrijving, vereisten, gunningshistorie).

### Handleiding-knop

Rechtsboven in de header staat een "Handleiding" knop die deze tekst toont.


## De IT-filter (v2.5)

Niet elke tender op TenderNed is IT. De TenderAgent filtert in vier stappen:

0. **Negatieve gate** — als de tendernaam een niet-IT keyword bevat (verhuisdiensten, schoonmaak, renovatie, openbare verlichting, objectbeveiliging, etc.) wordt de tender direct geblokkeerd. Dit voorkomt false positives bij tenders die toevallig een IT-CPV-code of ambigu keyword hebben.
1. **CPV-codes** — als minstens een code begint met 72* (IT-diensten), 48* (software), 30.2* (hardware), 64.2* (telecom), 50.3* (reparatie IT) of 51.6* (installatie IT). Extra check: als de naam puur fysiek klinkt, wordt de CPV-match genegeerd.
2. **Sterke IT-keywords** — woorden als "hosting", "cloud", "cybersecurity", "werkplek", "software" in naam of beschrijving. Context-aware: "hosting" telt alleen als er ook IT-context bij zit (zodat "hosting meldkamer" voor fysieke beveiliging niet matcht).
3. **MSP-segment keywords** — als een sterke keyword van een MSP-segment matcht (bijv. "SIEM", "SD-WAN", "applicatiebeheer").

Tenders die geen van deze checks halen worden volledig verwijderd. Je ziet ze nooit.

Korte keywords (4 tekens of minder, zoals "LAN", "SOC", "VPN") worden als heel woord gematcht. Dat voorkomt dat "kLANtvolgsysteem" matcht op "LAN" of "SOCiaal" op "SOC".


## Workflow: Tender van de Week selecteren

### Via het dashboard

1. Open http://localhost:8000
2. Klik **MSP-kansen** — dit toont tenders met positieve signalen
3. Bekijk de tenders met het hoogste MSP-fit nummer
4. Klik op een kaart voor details en gunningshistorie

### Via de API

**Stap 1 — Tenders met signalen bekijken**

```
http://localhost:8000/api/v1/tenders?alleen_signalen=true&sorteer=signalen
```

Drie soorten signalen:

| Icoon | Betekenis | Voorbeeld |
|-------|-----------|-----------|
| ⚠️ | Disproportioneel | Zware eisen voor kleine opdrachtgever, brede scope voor klein budget |
| 🧩 | Opvallende combinatie | Werkplek met security-focus, leverancierswisseling, meerdere organisaties |
| ✅ | MSP-kans | Sweet spot (overheid + werkplek + diensten), cloud bij overheid |

**Stap 2 — MSP-relevante tenders bekijken**

```
http://localhost:8000/api/v1/tenders?msp_label=relevant
```

**Stap 3 — Gunningshistorie checken**

```
http://localhost:8000/api/v1/gunningshistorie/Amersfoort
```

Vervang "Amersfoort" door de naam van de opdrachtgever (of een deel ervan). Toont alleen IT-gerelateerde gunningen.


## Workflow: Vooruitkijken

**Wat komt eraan (vooraankondigingen en marktconsultaties):**

```
http://localhost:8000/api/v1/vooraankondigingen
```

**Contracten die aflopen (herhalingspatronen):**

```
http://localhost:8000/api/v1/herhalingspatronen
```

IT-diensten die 3-5 jaar geleden zijn gegund en dus binnenkort opnieuw worden aanbesteed.


## Alle filteropties

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

| Label | Score | Betekenis |
|-------|-------|-----------|
| MSP-relevant | > 20 | Diensten, MSP-kernactiviteiten, overheidsopdracht |
| Mogelijk relevant | 0-20 | Deels passend, nader bekijken |
| Niet MSP | < 0 | Applicatiesoftware, fysieke infra, leveringen |

Score-opbouw:
- +20 als het type opdracht "Diensten" is
- +15 als de scope werkplekbeheer, cloud, hosting of infra bevat (geblokkeerd bij applicatiesoftware)
- +10 als de opdrachtgever gemeente, provincie, waterschap of GR is
- +5 als meerdere MSP-segmenten matchen
- -25 als het applicatiesoftware is (ERP, HRM, WOZ, salarisverwerking)
- -10 als het fysieke infrastructuur is (glasvezel aanleg, camerabewaking)
- -10 als het type "Leveringen" is

### MSP-segmenten

| Segment | Voorbeelden sterke keywords |
|---------|----------------------------|
| Werkplek & Eindgebruikersbeheer | werkplekbeheer, endpoint management, M365, servicedesk, ITSM |
| Cloud & Hosting | hosting, IaaS, PaaS, compute, storage, backup, VMware, datacenter |
| Cybersecurity & Informatiebeveiliging | SOC, SIEM, penetratietest, cybersecurity, incident response |
| Netwerk & Connectiviteit | SD-WAN, LAN, WAN, firewall, wifi, connectiviteit |
| Applicatiebeheer & Implementatie | applicatiebeheer, zaaksysteem, ITSM, ERP/CRM-implementatie |
| Data & Business Intelligence | datawarehouse, Power BI, Tableau, ETL, data analytics |
| Full-service IT-partner | Automatisch als 3+ segmenten matchen |

Korte keywords worden als heel woord gematcht om false positives te voorkomen.

### Verwachte vereisten

| Opdrachtgevertype | Verplicht | Waarschijnlijk | Gebruikelijk |
|--------------------|-----------|----------------|--------------|
| Gemeente, provincie, waterschap, GR | BIO | ISO 27001 | SROI |
| Rijksoverheid, ZBO | BIO | ISO 27001 | DigiD, ISAE 3402 |
| Vitale infra (ProRail, RWS) | BIO | ISO 27001, ISAE 3402, NIS2 | — |
| Zorg | NEN 7510 | ISO 27001 | BIO |
| Onderwijs | — | — | ISO 27001 |

### Geschatte waarde

| Opdrachtgever + scope | Bandbreedte |
|------------------------|-------------|
| Gemeente + IT-infra | €200K-1M |
| Gemeente + applicatie | €100K-500K |
| GR/samenwerkingsverband | €300K-2M |
| Rijksoverheid/ZBO | €500K-5M |
| Onderwijs | €50K-300K |
| Europese aanbesteding (minimum) | ≥€221K |


## Dataset bijwerken

1. Download de nieuwste dataset van https://www.tenderned.nl/cms/nl/aanbesteden-in-cijfers/datasets-aanbestedingen
2. Open Terminal:

```
cd /Users/martinvanleeuwen/tenderagent-msp
python3 import_dataset.py /pad/naar/nieuwe_dataset.xlsx
```

3. Herstart de server:

```
kill $(lsof -ti:8000) 2>/dev/null
python3 main.py
```


## Technische details

### Bestanden

```
tenderagent-msp/
  main.py                — De complete applicatie (API + dashboard)
  import_dataset.py      — Dataset import script
  data/
    tenderned_historie.db   — SQLite database (125.756 publicaties)
  requirements.txt
  Dockerfile
  docker-compose.yml
  HANDLEIDING.md         — Dit bestand
```

### Endpoints

| Endpoint | Wat het doet |
|----------|-------------|
| GET / | Dashboard (webinterface) |
| GET /handleiding | Deze handleiding |
| GET /api/v1/discover | API-overzicht en status |
| GET /api/v1/tenders | Actuele tenders met alle analyses |
| GET /api/v1/tenders/{id} | Detail van een tender |
| GET /api/v1/stats | Statistieken |
| GET /api/v1/cpv-codes | Welke CPV-codes worden gemonitord |
| GET /api/v1/gunningshistorie/{naam} | Wie won eerder bij deze opdrachtgever |
| GET /api/v1/vooraankondigingen | Vooraankondigingen en marktconsultaties |
| GET /api/v1/herhalingspatronen | Contracten die aflopen |
| POST /api/v1/refresh | Cache verversen |


## Versiegeschiedenis

| Versie | Datum | Wijzigingen |
|--------|-------|-------------|
| v2.0 | feb 2026 | Eerste versie met MSP-segmenten, scoring, signalen, dataset |
| v2.1 | feb 2026 | Bugfix: tegenstrijdige signalen, segment-matching, gunningshistorie IT-filter, APP_SOFTWARE scoring |
| v2.2 | feb 2026 | Dashboard (HTML webinterface), handleiding-knop |
| v2.3 | feb 2026 | IT-relevantie gate: filtert niet-IT tenders volledig weg |
| v2.4 | feb 2026 | No-cache headers, cache-busting, word-boundary matching in IT-gate, bijgewerkte handleiding |
| v2.5 | feb 2026 | Negatieve keyword-gate (blokkeerlijst niet-IT tenders), context-aware "hosting" matching, AI-referentienummer fix |


## Veelgestelde vragen

**Waarom staan er minder tenders dan ik op TenderNed zie?**
De IT-filter verwijdert alles wat geen IT-signaal heeft. Van de ~1000 recente publicaties blijft typisch 40-50% over. Dat is precies de bedoeling: je ziet alleen wat relevant is.

**Waarom staat E-HRM als "Mogelijk relevant"?**
De MSP-fit scoring filtert applicatiesoftware eruit (-25 punten), maar als het type opdracht "Diensten" is (+20) en er IT-keywords in staan, kan de netto score nog positief zijn. Gebruik de filter "MSP-relevant" om alleen echte MSP-tenders te zien.

**Waarom zijn sommige certificeringen "verwacht" en niet "bevestigd"?**
De TenderAgent leidt certificeringen af uit het type opdrachtgever. De daadwerkelijke eisen staan in de aanbestedingsdocumenten op TenderNed.

**Hoe actueel is de data?**
De live tenders komen rechtstreeks van de TenderNed API (actueel). De gunningshistorie komt uit de openbare dataset (bijgewerkt tot het moment dat je import_dataset.py hebt gedraaid).

**Kan ik dit ook op mijn telefoon gebruiken?**
Zolang je Mac aanstaat en de server draait: ja. Ga naar http://[je-mac-ip]:8000 op je telefoon (zelfde wifi-netwerk).
