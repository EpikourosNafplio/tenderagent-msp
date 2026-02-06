"""TenderNed API client — fetches publications and enriches with detail data."""

import logging
from typing import Any, Dict, List, Optional

import httpx

from .cpv_codes import matches_cpv

logger = logging.getLogger(__name__)

BASE_URL = "https://www.tenderned.nl/papi/tenderned-rs-tns/v2/publicaties"
TIMEOUT = 30.0
# Fetch multiple pages to get a broad set of recent tenders
MAX_PAGES = 10
PAGE_SIZE = 20


async def fetch_publications(pages: int = MAX_PAGES) -> List[dict]:
    """Fetch recent publications from TenderNed list endpoint."""
    all_items: List[dict] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for page in range(pages):
            try:
                resp = await client.get(
                    BASE_URL,
                    params={"size": PAGE_SIZE, "page": page},
                )
                resp.raise_for_status()
                data = resp.json()
                items = data.get("content", [])
                if not items:
                    break
                all_items.extend(items)
                logger.info("Page %d: fetched %d publications", page, len(items))
            except httpx.HTTPError as e:
                logger.error("Error fetching page %d: %s", page, e)
                break
    return all_items


async def fetch_detail(publication_id: str) -> Optional[Dict[str, Any]]:
    """Fetch detail for a single publication (includes CPV codes)."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            resp = await client.get(f"{BASE_URL}/{publication_id}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            logger.error("Error fetching detail %s: %s", publication_id, e)
            return None


async def enrich_with_cpv(publications: List[dict]) -> List[dict]:
    """Fetch detail for each publication and attach CPV codes.

    Only keeps tenders that match at least one IT/MSP CPV code,
    OR tenders where no CPV info could be retrieved (scored on keywords later).
    """
    enriched: List[dict] = []
    seen: set = set()
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for pub in publications:
            pub_id = str(pub.get("publicatieId", ""))
            if not pub_id or pub_id in seen:
                continue
            seen.add(pub_id)
            try:
                resp = await client.get(f"{BASE_URL}/{pub_id}")
                resp.raise_for_status()
                detail = resp.json()
                cpv_codes = detail.get("cpvCodes", [])
                pub["cpvCodes"] = cpv_codes

                # Keep if any CPV code matches our IT/MSP list
                has_it_cpv = any(matches_cpv(c.get("code", "")) for c in cpv_codes)
                if has_it_cpv:
                    enriched.append(pub)
            except httpx.HTTPError as e:
                logger.warning("Skipping detail for %s: %s", pub_id, e)
                # Keep it — will be scored on keywords alone
                enriched.append(pub)

    logger.info(
        "CPV enrichment: %d/%d tenders matched IT/MSP codes",
        len(enriched),
        len(publications),
    )
    return enriched


async def discover_it_tenders() -> List[dict]:
    """Full pipeline: fetch publications, enrich with CPV, return IT-relevant tenders."""
    pubs = await fetch_publications()
    logger.info("Fetched %d total publications from TenderNed", len(pubs))
    enriched = await enrich_with_cpv(pubs)
    return enriched
