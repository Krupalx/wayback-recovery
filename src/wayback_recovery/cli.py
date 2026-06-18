"""
Command-line interface for wayback-recovery.

Provides three commands: recover (main pipeline), status (check progress),
and report (see what's missing and why).
"""

import asyncio
from pathlib import Path

import click

from wayback_recovery.config import RecoveryConfig
from wayback_recovery.downloader import SiteRecovery


@click.group()
@click.version_option()
def main():
    """Recover websites from Wayback Machine, Common Crawl, and live CDNs."""
    pass


@main.command()
@click.argument("domain")
@click.option("-o", "--output", default="output", help="Output directory.")
@click.option("--delay-min", default=5.0, help="Minimum delay between requests (seconds).")
@click.option("--delay-max", default=10.0, help="Maximum delay between requests (seconds).")
@click.option("--no-wayback", is_flag=True, help="Skip Wayback Machine.")
@click.option("--no-commoncrawl", is_flag=True, help="Skip Common Crawl.")
@click.option("--no-cdn", is_flag=True, help="Skip live CDN detection.")
@click.option("--no-resume", is_flag=True, help="Start fresh, ignore previous progress.")
@click.option("--fast", is_flag=True, help="Reduce delays to 1-3s (higher ban risk).")
@click.option("--limit", default=0, help="Max files to download (0 = unlimited).")
def recover(domain, output, delay_min, delay_max, no_wayback, no_commoncrawl, no_cdn, no_resume, fast, limit):
    """Recover a website from web archives.

    DOMAIN is the site to recover, e.g. example.com
    """
    if fast:
        delay_min, delay_max = 1.0, 3.0

    config = RecoveryConfig(
        domain=domain,
        output_dir=Path(output),
        delay_min=delay_min,
        delay_max=delay_max,
        use_wayback=not no_wayback,
        use_commoncrawl=not no_commoncrawl,
        use_cdn_detection=not no_cdn,
        resume=not no_resume,
        limit=limit,
    )

    sources = []
    if config.use_wayback:
        sources.append("wayback")
    if config.use_commoncrawl:
        sources.append("commoncrawl")
    if config.use_cdn_detection:
        sources.append("cdn")

    print(f"\n  wayback-recovery v0.1.0")
    print(f"  Target:  {domain}")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Delays:  {config.delay_min}-{config.delay_max}s between requests")
    if config.limit > 0:
        print(f"  Limit:   {config.limit} files")
    if config.resume:
        print(f"  Resume:  enabled (will skip already-downloaded files)")
    print()

    recovery = SiteRecovery(config)
    asyncio.run(recovery.run())


@main.command()
@click.argument("domain")
@click.option("-o", "--output", default="output", help="Output directory.")
def status(domain, output):
    """Show recovery progress for a domain."""
    from wayback_recovery.state import DownloadState

    state_file = Path(output) / domain / ".recovery_state.json"
    if not state_file.exists():
        print(f"  No recovery state found for {domain}.")
        print(f"  (looked in {state_file})")
        return

    state = DownloadState(state_file)
    stats = state.stats
    print(f"\n  Recovery status: {domain}")
    print(f"  Completed: {stats['completed']}")
    print(f"  Failed:    {stats['failed']}")

    if state.failed:
        print(f"\n  Most recent failures:")
        for url, reason in list(state.failed.items())[:10]:
            print(f"    {url}")
            print(f"      reason: {reason}")
        if len(state.failed) > 10:
            print(f"    ... and {len(state.failed) - 10} more (see {state_file})")
    print()


@main.command()
@click.argument("domain")
@click.option("-o", "--output", default="output", help="Output directory.")
def report(domain, output):
    """Show what was recovered, what's missing, and why."""
    from wayback_recovery.state import DownloadState

    state_file = Path(output) / domain / ".recovery_state.json"
    if not state_file.exists():
        print(f"  No recovery state found for {domain}.")
        print(f"  (looked in {state_file})")
        return

    state = DownloadState(state_file)
    total = len(state.completed) + len(state.failed)
    pct = (len(state.completed) / total * 100) if total else 0

    print(f"\n  Completeness report: {domain}")
    print(f"  {'=' * 40}")
    print(f"  Total URLs discovered: {total}")
    print(f"  Successfully recovered: {len(state.completed)} ({pct:.1f}%)")
    print(f"  Failed: {len(state.failed)}")

    if state.failed:
        reasons = {}
        for reason in state.failed.values():
            reasons[reason] = reasons.get(reason, 0) + 1
        print(f"\n  Failure breakdown:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"    {count}x  {reason}")
    print()


if __name__ == "__main__":
    main()
