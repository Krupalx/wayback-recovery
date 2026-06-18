"""
Wayback Machine CDX API client.

The CDX API returns a list of every capture (snapshot) for a given domain.
We query it once to build a complete picture of what's available, then
deduplicate by URL — keeping the most recent timestamp as the primary
download target, with older timestamps as fallbacks.
"""

import random

import httpx

from wayback_recovery.config import USER_AGENTS, RecoveryConfig


async def fetch_cdx_index(config: RecoveryConfig, client: httpx.AsyncClient) -> tuple[list[dict], list[dict]]:
    """
    Query the CDX API for all captures of a domain.

    Returns (unique_records, all_records). unique_records has one entry per
    URL (most recent timestamp). all_records is the full set, used for
    finding fallback timestamps when a download fails.
    """
    url = "https://web.archive.org/cdx/search/cdx"
    params = {
        "url": f"{config.domain}/*",
        "output": "json",
        "fl": "timestamp,original,mimetype,statuscode,digest",
        "collapse": "digest",
    }

    headers = {"User-Agent": random.choice(USER_AGENTS)}
    resp = await client.get(url, params=params, headers=headers, timeout=config.timeout)
    resp.raise_for_status()

    rows = resp.json()
    if not rows or len(rows) < 2:
        return [], []

    fields = rows[0]
    all_records = []
    for row in rows[1:]:
        record = dict(zip(fields, row))
        if record.get("statuscode") == "200":
            all_records.append(record)

    # Keep only the most recent capture of each URL for the download queue.
    # All records are preserved for alternative_timestamps() lookups.
    seen = {}
    for record in all_records:
        orig = record["original"]
        if orig not in seen or record["timestamp"] > seen[orig]["timestamp"]:
            seen[orig] = record
    unique_records = sorted(seen.values(), key=lambda r: r["timestamp"], reverse=True)

    return unique_records, all_records


def build_raw_url(timestamp: str, original_url: str) -> str:
    """
    Build the direct-download URL for a Wayback capture.

    The 'id_' suffix tells Wayback to serve the original file without
    injecting its toolbar/rewrite scripts.
    """
    return f"https://web.archive.org/web/{timestamp}id_/{original_url}"


def alternative_timestamps(timestamp: str, records: list[dict], original_url: str) -> list[str]:
    """
    Find other timestamps for the same URL, in case the primary one fails.
    Returns up to 5 alternatives, most recent first.
    """
    alts = []
    for r in records:
        if r["original"] == original_url and r["timestamp"] != timestamp:
            alts.append(r["timestamp"])
    return sorted(alts, reverse=True)[:5]
