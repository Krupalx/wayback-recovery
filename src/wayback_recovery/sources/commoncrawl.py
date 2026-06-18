"""
Common Crawl index client.

Common Crawl is an independent web archive (separate from Wayback Machine).
Its data is stored as WARC files on S3 and indexed by crawl batch.
We search multiple recent indexes to find captures that Wayback may have missed.
"""

import json
import random

import httpx

from wayback_recovery.config import USER_AGENTS, RecoveryConfig

CC_INDEX_URL = "https://index.commoncrawl.org"
CC_DATA_URL = "https://data.commoncrawl.org"

# A reasonable spread of recent crawl indexes to check.
RECENT_INDEXES = [
    "CC-MAIN-2024-51",
    "CC-MAIN-2024-46",
    "CC-MAIN-2024-42",
    "CC-MAIN-2024-38",
    "CC-MAIN-2024-33",
    "CC-MAIN-2024-30",
    "CC-MAIN-2024-26",
    "CC-MAIN-2024-22",
    "CC-MAIN-2024-18",
    "CC-MAIN-2024-10",
    "CC-MAIN-2023-50",
    "CC-MAIN-2023-40",
    "CC-MAIN-2023-23",
    "CC-MAIN-2023-14",
    "CC-MAIN-2023-06",
]


async def search_index(
    config: RecoveryConfig, client: httpx.AsyncClient, index: str
) -> list[dict]:
    """Search a single Common Crawl index for captures of the target domain."""
    url = f"{CC_INDEX_URL}/{index}-index"
    params = {"url": f"*.{config.domain}", "output": "json"}
    headers = {"User-Agent": random.choice(USER_AGENTS)}

    try:
        resp = await client.get(url, params=params, headers=headers, timeout=config.timeout)
        if resp.status_code == 404:
            return []
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.TimeoutException):
        return []

    records = []
    for line in resp.text.strip().split("\n"):
        if line.strip():
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


async def fetch_all_indexes(config: RecoveryConfig, client: httpx.AsyncClient) -> list[dict]:
    """Search across all recent Common Crawl indexes for the domain."""
    all_records = []
    for index in RECENT_INDEXES:
        records = await search_index(config, client, index)
        all_records.extend(records)
    return all_records


def build_cc_download_params(record: dict) -> tuple[str, dict[str, str]]:
    """
    Given a Common Crawl index record, return the URL and headers needed
    to fetch just that record's WARC segment from S3.

    Common Crawl stores everything in huge WARC files, but the index tells
    us the exact byte offset and length, so we can request just our slice.
    """
    filename = record["filename"]
    offset = int(record["offset"])
    length = int(record["length"])
    end = offset + length - 1

    url = f"{CC_DATA_URL}/{filename}"
    headers = {
        "Range": f"bytes={offset}-{end}",
        "User-Agent": random.choice(USER_AGENTS),
    }
    return url, headers
