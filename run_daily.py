"""Entrypoint for the daily automated run (spec section 15).

Usage:
    python run_daily.py                       # incremental run from last state
    python run_daily.py --start 2026-08-01 --end 2026-08-19   # explicit backfill range

Called by the scheduled cloud agent: pull repo -> run this -> commit data/ -> push.
"""

from __future__ import annotations

import argparse
import datetime as dt

import digest
import pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the US trade policy monitor pipeline once.")
    parser.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="YYYY-MM-DD")
    args = parser.parse_args()

    if bool(args.start) != bool(args.end):
        parser.error("--start and --end must both be provided together, or both omitted")

    start_date = dt.date.fromisoformat(args.start) if args.start else None
    end_date = dt.date.fromisoformat(args.end) if args.end else None

    result = pipeline.run_pipeline(start_date, end_date)

    digest_date = end_date or dt.date.today()
    existing_digest = digest.DIGESTS_DIR / f"{digest_date.isoformat()}.md"
    if result["new_documents"] == 0 and existing_digest.exists():
        # A same-day rerun (e.g. a retried cron trigger) found nothing new --
        # leave the earlier, more informative digest for today in place
        # rather than overwriting it with an empty one.
        print(f"Fetched: {result['fetched']} | New documents: 0 | digest for {digest_date.isoformat()} left unchanged")
        return

    content = digest.build_daily_digest(result, digest_date)
    path = digest.save_digest(content, digest_date)

    print(f"Fetched: {result['fetched']} | New documents: {result['new_documents']} | "
          f"New HIGH/CRITICAL alerts: {result['new_alerts']}")
    print(f"Digest written to: {path}")


if __name__ == "__main__":
    main()
