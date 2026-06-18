"""
Live CDN detection.

Many website platforms (Squarespace, WordPress, Wix) host images and assets
on their own CDN subdomains. When a site goes down, the CDN often keeps
serving those files for months or years — the platform just doesn't bother
cleaning them up.

This module scans recovered HTML for references to known CDN hosts, then
checks which ones are still responding. It's the single biggest advantage
over Wayback-only recovery tools.
"""

import re
import random
from urllib.parse import urlparse

import httpx

from wayback_recovery.config import USER_AGENTS

# Known CDN hostnames by platform.
CDN_PATTERNS = {
    "squarespace": [
        "images.squarespace-cdn.com",
        "static1.squarespace.com",
    ],
    "wordpress": [
        "i0.wp.com",
        "i1.wp.com",
        "i2.wp.com",
    ],
    "wix": [
        "static.wixstatic.com",
    ],
    "cloudinary": [
        "res.cloudinary.com",
    ],
}


def extract_cdn_urls(html_content: str, domain: str) -> list[str]:
    """
    Parse HTML for image/asset URLs that point to known CDN hosts.

    Only returns absolute URLs (http/https). Relative paths are ignored
    since they'd need to be resolved against the original site's base URL
    and we can't be sure what that was.
    """
    urls = set()
    patterns = [
        r'src=["\']([^"\']+)["\']',
        r'href=["\']([^"\']+\.(?:jpg|jpeg|png|gif|webp|svg|mp4|mov))["\']',
        r'url\(["\']?([^"\')\s]+)["\']?\)',
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, html_content, re.IGNORECASE):
            url = match.group(1)
            if not url.startswith(("http://", "https://")):
                continue
            if any(cdn_host in url for hosts in CDN_PATTERNS.values() for cdn_host in hosts):
                urls.add(url)

    return sorted(urls)


async def check_cdn_alive(url: str, client: httpx.AsyncClient) -> bool:
    """
    Send a HEAD request to see if a CDN URL still serves content.
    Returns True if we get a 200, False for anything else.
    """
    if not url.startswith(("http://", "https://")):
        return False
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        resp = await client.head(url, headers=headers, timeout=10, follow_redirects=True)
        return resp.status_code == 200
    except (httpx.HTTPError, httpx.TimeoutException, ValueError):
        return False
