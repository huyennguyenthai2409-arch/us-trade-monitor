"""Entrypoint for the daily automated run (spec section 15).

Usage:
    python run_daily.py                       # incremental run from last state
    python run_daily.py --start 2026-08-01 --end 2026-08-19   # explicit range
    python run_daily.py --start 2025-01-01 --end 2026-08-19 --chunk-days 30   # large backfill

Called by the scheduled cloud agent: pull repo -> run this -> commit data/ -> push.

--chunk-days splits a large --start/--end range into smaller windows before
calling the pipeline, since a single very long range can exceed a single
query's pagination cap (federal_register.py's MAX_PAGES). It also skips
digest generation -- a digest listing hundreds/thousands of backfilled events
isn't a useful "daily digest", so a chunked run just prints aggregate counts.
"""

from __future__ import annotations

import argparse
import datetime as dt

import digest
import pipeline


def _run_chunked(start_date: dt.date, end_date: dt.date, chunk_days: int) -> None:
    total_fetched = total_new = total_alerts = 0
    current = start_date
    while current <= end_date:
        chunk_end = min(current + dt.timedelta(days=chunk_days - 1), end_date)
        result = pipeline.run_pipeline(current, chunk_end)
        total_fetched += result["fetched"]
        total_new += result["new_documents"]
        total_alerts += result["new_alerts"]
        print(f"  {current} to {chunk_end}: fetched {result['fetched']}, new {result['new_documents']}, "
              f"Cao-priority {result['new_alerts']}")
        current = chunk_end + dt.timedelta(days=1)

    print(f"\nBackfill done ({start_date} to {end_date}): fetched {total_fetched}, "
          f"new documents {total_new}, new Cao-priority alerts {total_alerts}. No digest generated for backfills.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the US trade policy monitor pipeline once.")
    parser.add_argument("--start", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--end", type=str, default=None, help="YYYY-MM-DD")
    parser.add_argument("--chunk-days", type=int, default=None,
                         help="Split --start/--end into N-day chunks (for large backfills)")
    args = parser.parse_args()

    if bool(args.start) != bool(args.end):
        parser.error("--start and --end must both be provided together, or both omitted")
    if args.chunk_days and not args.start:
        parser.error("--chunk-days requires --start and --end")
    if args.chunk_days is not None and args.chunk_days < 1:
        parser.error("--chunk-days must be >= 1")

    start_date = dt.date.fromisoformat(args.start) if args.start else None
    end_date = dt.date.fromisoformat(args.end) if args.end else None

    if args.chunk_days:
        _run_chunked(start_date, end_date, args.chunk_days)
        return

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
          f"New Cao-priority alerts: {result['new_alerts']}")
    print(f"Digest written to: {path}")


if __name__ == "__main__":
    main()
