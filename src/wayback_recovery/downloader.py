"""
Core download engine.

Runs the four-phase recovery pipeline: discovery, wayback download,
common crawl gap-fill, and live CDN detection. Handles rate limiting,
fallback timestamps, and resume state.
"""

import asyncio
import gzip
import random
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

import httpx

from wayback_recovery.config import RecoveryConfig, USER_AGENTS
from wayback_recovery.state import DownloadState
from wayback_recovery.sources.cdx import fetch_cdx_index, build_raw_url, alternative_timestamps
from wayback_recovery.sources.commoncrawl import fetch_all_indexes, build_cc_download_params
from wayback_recovery.sources.cdn import extract_cdn_urls, check_cdn_alive


def _log(msg: str) -> None:
    print(msg, flush=True)


def _progress(current: int, total: int, width: int = 40) -> str:
    """Render a simple ASCII progress bar."""
    if total == 0:
        return ""
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    pct = current * 100 // total
    return f"  [{bar}] {current}/{total} ({pct}%)"


class SiteRecovery:
    def __init__(self, config: RecoveryConfig):
        self.config = config
        self.output_dir = config.output_dir / config.domain
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state = DownloadState(self.output_dir / ".recovery_state.json")
        self.cdn_urls: set[str] = set()
        self.cdx_records: list[dict] = []
        self.all_cdx_records: list[dict] = []

    async def run(self) -> dict:
        """Run the full recovery pipeline. Returns a stats dict."""
        stats = {"wayback": 0, "commoncrawl": 0, "cdn": 0, "skipped": 0, "failed": 0}

        async with httpx.AsyncClient(follow_redirects=True, http2=True) as client:

            _log("\n--- Phase 1: Discovery ---\n")

            if self.config.use_wayback:
                _log("  Querying Wayback Machine CDX API...")
                self.cdx_records, self.all_cdx_records = await fetch_cdx_index(self.config, client)
                _log(f"  Found {len(self.cdx_records)} unique URLs across {len(self.all_cdx_records)} total captures.")

            cc_records = []
            if self.config.use_commoncrawl:
                _log("  Querying Common Crawl indexes...")
                cc_records = await fetch_all_indexes(self.config, client)
                _log(f"  Found {len(cc_records)} Common Crawl records.")

            if self.config.use_wayback and self.cdx_records:
                _log("\n--- Phase 2: Wayback Machine Downloads ---\n")
                wayback_stats = await self._download_wayback(client)
                stats["wayback"] = wayback_stats["downloaded"]
                stats["skipped"] += wayback_stats["skipped"]
                stats["failed"] += wayback_stats["failed"]

            if self.config.use_commoncrawl and cc_records:
                _log("\n--- Phase 3: Common Crawl Gap-Fill ---\n")
                cc_stats = await self._download_commoncrawl(client, cc_records)
                stats["commoncrawl"] = cc_stats["downloaded"]
                stats["skipped"] += cc_stats["skipped"]

            if self.config.use_cdn_detection:
                _log("\n--- Phase 4: Live CDN Detection ---\n")
                cdn_stats = await self._download_cdn_assets(client)
                stats["cdn"] = cdn_stats["downloaded"]

        self._print_report(stats)
        return stats

    async def _download_wayback(self, client: httpx.AsyncClient) -> dict:
        downloaded = 0
        skipped = 0
        failed = 0

        records = self.cdx_records
        if self.config.limit > 0:
            records = records[: self.config.limit]

        total = len(records)
        for i, record in enumerate(records, 1):
            original_url = record["original"]
            timestamp = record["timestamp"]

            if self.state.is_done(original_url):
                skipped += 1
                continue

            url = build_raw_url(timestamp, original_url)
            content = await self._fetch_with_fallback(client, url, original_url, timestamp)

            if content is not None:
                self._save_file(original_url, content)
                self.state.mark_done(original_url)
                downloaded += 1

                if self.config.use_cdn_detection:
                    mimetype = record.get("mimetype", "")
                    if "html" in mimetype:
                        cdn_found = extract_cdn_urls(
                            content.decode("utf-8", errors="ignore"),
                            self.config.domain,
                        )
                        self.cdn_urls.update(cdn_found)
            else:
                self.state.mark_failed(original_url, "all timestamps exhausted")
                failed += 1

            # Print progress every 10 files or on the last one
            if i % 10 == 0 or i == total:
                sys.stdout.write(f"\r{_progress(i, total)}")
                sys.stdout.flush()

            await self._anti_ban_delay()

        print()  # newline after progress bar
        _log(f"  Downloaded: {downloaded} | Skipped: {skipped} | Failed: {failed}")
        return {"downloaded": downloaded, "skipped": skipped, "failed": failed}

    async def _fetch_with_fallback(
        self, client: httpx.AsyncClient, url: str, original_url: str, primary_timestamp: str
    ) -> bytes | None:
        """Try the primary timestamp first, then fall back to alternatives."""
        content = await self._fetch_one(client, url)
        if content is not None:
            return content

        alt_timestamps = alternative_timestamps(primary_timestamp, self.all_cdx_records, original_url)
        for ts in alt_timestamps:
            alt_url = build_raw_url(ts, original_url)
            content = await self._fetch_one(client, alt_url)
            if content is not None:
                return content
            await self._anti_ban_delay()

        return None

    async def _fetch_one(self, client: httpx.AsyncClient, url: str) -> bytes | None:
        """Single fetch attempt with retries. Returns content bytes or None."""
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        for attempt in range(self.config.max_retries):
            try:
                resp = await client.get(url, headers=headers, timeout=self.config.timeout)
                if resp.status_code == 200:
                    return resp.content
                if resp.status_code == 429:
                    wait = (attempt + 1) * 15
                    _log(f"\n  Rate limited. Backing off for {wait}s...")
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code in (404, 503):
                    return None
            except (httpx.TimeoutException, httpx.ConnectError):
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(5)
                    continue
        return None

    async def _download_commoncrawl(self, client: httpx.AsyncClient, records: list[dict]) -> dict:
        downloaded = 0
        skipped = 0

        total = len(records)
        for i, record in enumerate(records, 1):
            url = record.get("url", "")
            if self.state.is_done(url):
                skipped += 1
                continue

            dl_url, headers = build_cc_download_params(record)
            try:
                resp = await client.get(dl_url, headers=headers, timeout=self.config.timeout)
                if resp.status_code in (200, 206):
                    content = self._extract_warc_payload(resp.content)
                    if content:
                        self._save_file(url, content)
                        self.state.mark_done(url)
                        downloaded += 1
            except (httpx.HTTPError, httpx.TimeoutException):
                pass

            if i % 10 == 0 or i == total:
                sys.stdout.write(f"\r{_progress(i, total)}")
                sys.stdout.flush()

            await self._anti_ban_delay()

        print()
        _log(f"  Downloaded: {downloaded} | Skipped: {skipped}")
        return {"downloaded": downloaded, "skipped": skipped}

    async def _download_cdn_assets(self, client: httpx.AsyncClient) -> dict:
        downloaded = 0

        if not self.cdn_urls:
            _log("  No CDN URLs discovered in recovered HTML.")
            return {"downloaded": 0}

        _log(f"  Found {len(self.cdn_urls)} CDN references in HTML. Checking which are still live...")

        alive_urls = []
        for url in self.cdn_urls:
            if self.state.is_done(url):
                continue
            if await check_cdn_alive(url, client):
                alive_urls.append(url)

        _log(f"  {len(alive_urls)} of {len(self.cdn_urls)} CDN assets are still being served.")

        if not alive_urls:
            return {"downloaded": 0}

        _log(f"  Downloading live CDN assets...")
        total = len(alive_urls)
        for i, url in enumerate(alive_urls, 1):
            content = await self._fetch_one(client, url)
            if content:
                self._save_file(url, content)
                self.state.mark_done(url)
                downloaded += 1

            if i % 10 == 0 or i == total:
                sys.stdout.write(f"\r{_progress(i, total)}")
                sys.stdout.flush()

            await self._anti_ban_delay()

        print()
        _log(f"  Downloaded: {downloaded}")
        return {"downloaded": downloaded}

    def _save_file(self, url: str, content: bytes) -> None:
        """Write content to disk, preserving the original URL path structure."""
        parsed = urlparse(url)
        path = unquote(parsed.path).lstrip("/")
        if not path or path.endswith("/"):
            path = path + "index.html"

        dest = self.output_dir / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

    def _extract_warc_payload(self, data: bytes) -> bytes | None:
        """Pull the HTTP response body out of a WARC record (handles gzip)."""
        try:
            data = gzip.decompress(data)
        except (gzip.BadGzipFile, OSError):
            pass

        separator = b"\r\n\r\n"
        idx = data.find(separator)
        if idx == -1:
            return None
        data = data[idx + len(separator):]
        idx = data.find(separator)
        if idx == -1:
            return data
        return data[idx + len(separator):]

    async def _anti_ban_delay(self) -> None:
        """Random delay between requests to avoid triggering rate limits."""
        delay = random.uniform(self.config.delay_min, self.config.delay_max)
        await asyncio.sleep(delay)

    def _print_report(self, stats: dict) -> None:
        total = stats["wayback"] + stats["commoncrawl"] + stats["cdn"]
        _log("\n" + "=" * 50)
        _log("  RECOVERY COMPLETE")
        _log("=" * 50)
        _log(f"  Wayback Machine:  {stats['wayback']} files")
        _log(f"  Common Crawl:     {stats['commoncrawl']} files")
        _log(f"  Live CDN:         {stats['cdn']} assets")
        _log(f"  Skipped (resume): {stats['skipped']}")
        _log(f"  Failed:           {stats['failed']}")
        _log(f"  ----------------------------------------")
        _log(f"  Total recovered:  {total} files")
        _log(f"\n  Output directory: {self.output_dir}")
        if stats["failed"] > 0:
            _log(f"  Failed URLs logged in: {self.state.state_file}")
        _log("")
