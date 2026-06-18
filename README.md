# wayback-recovery

A recon tool for pulling full site archives from the Wayback Machine without getting banned.

## The problem

If you've done any target recon, you know the pain. You need to map out an application's
full attack surface — old endpoints, deprecated API routes, JavaScript files with hardcoded
secrets, admin panels that got "removed" but never actually taken down. The Wayback Machine
has all of this archived, but the moment you start scraping it at any reasonable speed,
you get rate-limited or straight up IP-banned mid-crawl.

The existing tools make this worse. The popular Ruby `wayback_machine_downloader` hasn't
been updated since 2021, uses HTTP instead of HTTPS, sends the same User-Agent on every
request, and has zero retry logic. It gets blocked within minutes on most targets.

## What this does differently

This tool was built specifically to handle the rate-limiting problem while maximizing
the data you pull back. It cross-references three independent archive sources so you
get the most complete picture of a target's history:

**Wayback Machine** — The primary source. Queries the CDX API to discover every URL
ever archived for your target, then downloads the raw content with anti-ban measures
baked in: rotating User-Agents, HTTPS-only, randomized delays between requests, and
automatic backoff when rate-limited.

**Common Crawl** — An independent web archive that often has pages Wayback missed.
Fetches via byte-range requests from their S3 storage — different infrastructure,
different rate limits, fills gaps.

**Live CDN detection** — Scans recovered HTML for references to platform CDNs
(Squarespace, WordPress, Wix, Cloudinary). Many hosting platforms keep their CDN
endpoints serving content long after a site is "taken down." This pulls back images,
scripts, and assets that no other archival tool finds.

## Why this matters for recon

Once you have a full site archive locally, you can grep through it offline without
any rate limits or detection:

- Old JavaScript files with API keys, tokens, internal URLs
- Deprecated endpoints that may still be live but removed from the current sitemap
- Admin panels and debug pages that existed in earlier versions
- Email addresses, internal hostnames, S3 bucket names buried in HTML comments
- Full URL structure history showing how the application evolved
- Source maps and unminified code from older deploys

You pull everything once, then analyze at your own pace without touching the target again.

## Anti-ban measures

- HTTPS only (HTTP requests to archive.org get flagged faster)
- Rotates through 5 realistic browser User-Agent strings
- Random delays between requests (5-10s default, configurable)
- Progressive backoff on 429 responses (15s, 30s, 45s)
- Automatic fallback to alternative timestamps when a capture returns 503
- Three independent sources means you're not hammering any single endpoint

## Installation

```
git clone https://github.com/Krupalx/wayback-recovery.git
cd wayback-recovery
pip install -e .
```

Requires Python 3.10+.

## Usage

Pull everything for a target:

```
wayback-recovery recover target.com
```

Fast mode (shorter delays, higher risk of rate limiting):

```
wayback-recovery recover target.com --fast
```

Only Wayback Machine (quickest, skip Common Crawl and CDN):

```
wayback-recovery recover target.com --no-commoncrawl --no-cdn
```

Limit downloads (good for testing or when you only need a sample):

```
wayback-recovery recover target.com --limit 100
```

Custom output path:

```
wayback-recovery recover target.com -o ./recon/target
```

Check progress on a long-running recovery:

```
wayback-recovery status target.com
```

See what failed and why:

```
wayback-recovery report target.com
```

## Resume support

Recovery state is tracked in a JSON file. If your connection drops, your VPN
reconnects, or you just ctrl-c out — run the same command again and it picks up
exactly where it left off. No wasted time re-downloading what you already have.

## Output structure

Files are saved in their original path structure:

```
output/target.com/
  index.html
  api/v1/users/index.html
  static/js/app.bundle.js
  admin/login/index.html
  ...
```

From here you can run whatever analysis you want — `grep -r "api_key"`, feed it
into your own tooling, diff it against the current live version, etc.

## Benchmarks

Tested against a mid-size Squarespace site:

```
Ruby wayback_machine_downloader:  484 pages,   57 assets
wayback-recovery:                 539 pages, 2287 assets
```

The 40x difference in assets is from live CDN detection — a feature no other
archival tool implements.

## Options

```
wayback-recovery recover [OPTIONS] DOMAIN

  -o, --output       Output directory (default: output)
  --delay-min        Min seconds between requests (default: 5)
  --delay-max        Max seconds between requests (default: 10)
  --no-wayback       Skip Wayback Machine
  --no-commoncrawl   Skip Common Crawl
  --no-cdn           Skip CDN detection
  --no-resume        Start fresh, ignore previous state
  --fast             Use 1-3s delays instead of 5-10s
  --limit            Cap number of files to download
```

## License

MIT
