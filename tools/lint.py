#!/usr/bin/env python3
"""
Wiki Lint — Automated health checks.
Run weekly or on-demand: python tools/lint.py

Handles:
- Log rotation (>500 lines → archive)
- Stale active markets past resolution date
- Cluster validation against allowed vocabulary
- Orphan detection (pages with no inbound links)
"""

import re
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_PATH = ROOT / "log.md"
ARCHIVE_DIR = ROOT / "wiki" / "logs"
MARKETS_DIR = ROOT / "wiki" / "markets"

ALLOWED_CLUSTERS = {
    "inflation", "fed_policy", "labor_market", "growth_gdp",
    "crypto_beta", "political_cycle", "oil_energy",
    "weather_temp", "weather_precip", "uncorrelated",
}

MAX_LOG_LINES = 500


def rotate_log():
    """Archive old log entries if log.md exceeds MAX_LOG_LINES."""
    if not LOG_PATH.exists():
        return

    lines = LOG_PATH.read_text().splitlines()
    if len(lines) <= MAX_LOG_LINES:
        print(f"Log: {len(lines)} lines (under {MAX_LOG_LINES}, no rotation needed)")
        return

    # Keep last 200 lines, archive the rest
    keep = 200
    archive_lines = lines[:-keep]
    keep_lines = lines[-keep:]

    # Archive
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    archive_path = ARCHIVE_DIR / f"archive-{month}.md"

    with open(archive_path, "a") as f:
        f.write("\n".join(archive_lines) + "\n")

    LOG_PATH.write_text("\n".join(keep_lines) + "\n")
    print(f"Log rotated: archived {len(archive_lines)} lines to {archive_path}")


def check_stale_markets():
    """Find active markets past their resolution date."""
    now = datetime.now(timezone.utc).date()
    stale = []

    for md_file in MARKETS_DIR.glob("*.md"):
        content = md_file.read_text()
        # Check frontmatter for status and resolution_date
        if "status: active" not in content:
            continue

        match = re.search(r"resolution_date:\s*(\d{4}-\d{2}-\d{2})", content)
        if match:
            res_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
            if res_date < now:
                stale.append((md_file.stem, match.group(1)))

    if stale:
        print(f"\n⚠️  STALE MARKETS ({len(stale)}):")
        for ticker, date in stale:
            print(f"  {ticker} — resolved {date}, still marked active")
    else:
        print("Markets: no stale active markets found")


def validate_clusters():
    """Check that all correlation_cluster values are from allowed list."""
    invalid = []

    for md_file in MARKETS_DIR.glob("*.md"):
        content = md_file.read_text()
        match = re.search(r"correlation_cluster:\s*(\S+)", content)
        if match:
            cluster = match.group(1)
            if cluster != "null" and cluster not in ALLOWED_CLUSTERS:
                invalid.append((md_file.stem, cluster))

    if invalid:
        print(f"\n⚠️  INVALID CLUSTERS ({len(invalid)}):")
        for ticker, cluster in invalid:
            print(f"  {ticker} — '{cluster}' not in allowed list")
    else:
        print("Clusters: all valid")


def check_orphans():
    """Find wiki pages with no inbound wikilinks."""
    all_pages = set()
    linked_pages = set()

    wiki_dir = ROOT / "wiki"
    for md_file in wiki_dir.rglob("*.md"):
        rel = md_file.relative_to(wiki_dir)
        all_pages.add(md_file.stem)

        content = md_file.read_text()
        links = re.findall(r"\[\[([^\]]+)\]\]", content)
        linked_pages.update(links)

    # Also check index and log
    for f in [ROOT / "wiki" / "index.md", LOG_PATH]:
        if f.exists():
            links = re.findall(r"\[\[([^\]]+)\]\]", f.read_text())
            linked_pages.update(links)

    orphans = all_pages - linked_pages - {"index", "overview"}
    if orphans:
        print(f"\n⚠️  ORPHAN PAGES ({len(orphans)}):")
        for o in sorted(orphans):
            print(f"  {o}")
    else:
        print("Orphans: none found")


def main():
    print(f"=== Wiki Lint — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===\n")
    rotate_log()
    check_stale_markets()
    validate_clusters()
    check_orphans()
    print("\nDone.")


if __name__ == "__main__":
    main()
