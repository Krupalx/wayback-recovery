# wayback-recovery

A command-line tool for recovering dead websites from web archives.

Most site recovery tools only hit the Wayback Machine and call it a day. This one
cross-references three independent sources — Wayback Machine, Common Crawl, and
live CDN endpoints — to pull back as much of a site as possible. It was built out
of frustration with the existing Ruby tool (`wayback_machine_downloader`), which
hasn't been maintained since 2021 and routinely gets IP-banned mid-crawl.

## How it works

The recovery runs in four phases:

**1. Discovery** — Queries the Wayback Machine CDX API and Common Crawl indexes
to build a complete map of every URL ever captured for your domain. Deduplicates
by URL, keeping the most recent capture while retaining older timestamps as
fallbacks.

**2. Wayback Machine downloads** — Fetches raw content (no Wayback toolbar) for
each unique URL. If a capture returns a 503 or times out, it automatically tries
alternative timestamps from the CDX index before giving up.

**3. Common Crawl gap-fill** — Any URLs that Wayback missed (or that failed) get
a second chance via Common Crawl's WARC archives. These are fetched with byte-range
requests so we only download the specific records we need.

**4. Live CDN detection** — Scans recovered HTML for references to platform CDNs
(Squarespace, WordPress, Wix, Cloudinary) and checks if those assets are still
being served. Many hosting platforms keep image CDN endpoints alive long after a
site goes down. This is where the big wins come from — in testing, this phase alone
recovered 40x more images than the Ruby tool finds in total.

## Anti-ban measures

Getting blocked by the Wayback Machine mid-recovery defeats the purpose. The tool
uses HTTPS (not HTTP), rotates through realistic browser User-Agent strings, and
inserts random delays between requests (5-10 seconds by default). If it gets a 429
rate-limit response, it backs off progressively rather than hammering the endpoint.

## Resume support

Recovery state is written to a JSON file after each successful download. If the
process is interrupted (network drop, laptop sleep, ctrl-c), just run the same
command again and it picks up where it left off. No re-downloading, no duplicates.

## Installation

```
pip install -e .
```

Requires Python 3.10+.

## Usage

Recover a full site:

```
wayback-recovery recover example.com
```

Reduce delays between requests (faster, but higher chance of getting rate-limited):

```
wayback-recovery recover example.com --fast
```

Only use Wayback Machine (skip Common Crawl and CDN checks):

```
wayback-recovery recover example.com --no-commoncrawl --no-cdn
```

Limit to N files (useful for testing or partial recovery):

```
wayback-recovery recover example.com --limit 50
```

Custom output directory:

```
wayback-recovery recover example.com -o ./recovered-sites
```

Check progress on a recovery in progress:

```
wayback-recovery status example.com
```

See what's missing and why:

```
wayback-recovery report example.com
```

## Output structure

Files are saved in their original directory structure under `output/<domain>/`.
A homepage at `example.com/about/` becomes `output/example.com/about/index.html`.
CDN assets keep their full path, so Squarespace images end up under
`output/example.com/images.squarespace-cdn.com/...`.

## Benchmarks

Tested against `airparisagency.com` (a Squarespace site that went offline in 2023):

```
Ruby wayback_machine_downloader:  484 HTML pages,   57 images
wayback-recovery:                 539 HTML pages, 2287 images
```

The difference is almost entirely from live CDN detection — Squarespace was still
serving those images years after the site was taken down.

## Options reference

```
wayback-recovery recover [OPTIONS] DOMAIN

  --output, -o       Output directory (default: output)
  --delay-min        Minimum seconds between requests (default: 5)
  --delay-max        Maximum seconds between requests (default: 10)
  --no-wayback       Skip Wayback Machine source
  --no-commoncrawl   Skip Common Crawl source
  --no-cdn           Skip live CDN detection
  --no-resume        Ignore previous progress, start fresh
  --fast             Use shorter delays (1-3s)
  --limit            Cap the number of files to download (0 = no limit)
```

## License

MIT
