"""One-off maintenance: prune the LangGraph SQLite checkpoint DB.

Why this exists
---------------
DeepAgent uses ``langgraph.checkpoint.sqlite`` to persist conversation state
per ``thread_id``. Every step within every turn emits a new row in both
``checkpoints`` and ``writes``, and the serialized payload contains the FULL
``messages`` list for that step. With ~5 steps per turn and 500+ turns on the
live Telegram thread we ended up with a 1.6 GB SQLite file, most of it stale:

- hundreds of ``run_*`` threads from the fine-tune distillation pipeline
- dozens of ``smoke-*`` / ``verify-*`` / ``test-*`` / ``diag-*`` / ``t1776*``
  threads from debugging sessions
- the real ``telegram-*`` thread keeping every historical step

Under disk pressure this starts rejecting writes, which manifests as Telegram
reply duplication (python-telegram-bot retries the send when the SQLite
commit path gets slow/unstable).

What this script does
---------------------
1. Keeps only the latest checkpoint per "real" thread (``telegram-*``,
   ``api-skill-*``). LangGraph only needs the tip to resume a thread, so
   older rows are only useful for time-travel debugging which we don't do.
2. Drops every checkpoint row for stale/test thread prefixes entirely.
3. Cleans up orphan ``writes`` rows.
4. ``VACUUM`` to reclaim the freed pages.

Run with the agent stopped (or docker down) so there is no writer contention::

    python prune_checkpoints.py            # dry-run, prints stats
    python prune_checkpoints.py --apply    # actually delete + vacuum
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import config

KEEP_PREFIXES = ("telegram-", "api-skill-")


def _classify(thread_id: str) -> str:
    if thread_id.startswith(KEEP_PREFIXES):
        return "keep-latest"
    return "drop"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=config.CHECKPOINT_DB,
        help="Path to the SQLite checkpoint DB (default: %(default)s)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually perform the deletes + VACUUM. Omit for a dry run.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.is_file():
        print(f"ERROR: DB not found at {db_path}")
        return 1

    size_before = db_path.stat().st_size
    print(f"DB: {db_path}  size_before={size_before / (1024*1024):.1f} MiB")

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = OFF")

    threads = conn.execute(
        "SELECT thread_id, COUNT(*) FROM checkpoints GROUP BY thread_id"
    ).fetchall()

    to_drop = [tid for tid, _ in threads if _classify(tid) == "drop"]
    to_keep_latest = [tid for tid, _ in threads if _classify(tid) == "keep-latest"]

    total_rows = sum(n for _, n in threads)
    drop_rows = sum(n for tid, n in threads if tid in to_drop)
    keep_total_rows = sum(n for tid, n in threads if tid in to_keep_latest)

    print()
    print(f"  total threads:              {len(threads):>6}")
    print(f"  drop entirely (stale/test): {len(to_drop):>6}  rows={drop_rows}")
    print(
        f"  keep latest only (real):    {len(to_keep_latest):>6}  "
        f"rows_before={keep_total_rows}"
    )
    print(f"  total checkpoint rows:      {total_rows:>6}")

    if not args.apply:
        print("\nDRY RUN -- rerun with --apply to delete and vacuum.")
        conn.close()
        return 0

    cur = conn.cursor()

    if to_drop:
        placeholders = ",".join("?" for _ in to_drop)
        cur.execute(
            f"DELETE FROM writes WHERE thread_id IN ({placeholders})", to_drop,
        )
        deleted_writes = cur.rowcount
        cur.execute(
            f"DELETE FROM checkpoints WHERE thread_id IN ({placeholders})", to_drop,
        )
        deleted_ckpts = cur.rowcount
        print(
            f"  deleted: checkpoints={deleted_ckpts}  writes={deleted_writes} "
            f"(from {len(to_drop)} stale threads)"
        )

    deleted_history_ckpts = 0
    deleted_history_writes = 0
    for tid in to_keep_latest:
        cur.execute(
            """
            DELETE FROM writes
             WHERE thread_id = ?
               AND checkpoint_id NOT IN (
                   SELECT checkpoint_id
                     FROM checkpoints
                    WHERE thread_id = ?
                 ORDER BY checkpoint_id DESC
                    LIMIT 1
               )
            """,
            (tid, tid),
        )
        deleted_history_writes += cur.rowcount
        cur.execute(
            """
            DELETE FROM checkpoints
             WHERE thread_id = ?
               AND checkpoint_id NOT IN (
                   SELECT checkpoint_id
                     FROM (
                       SELECT checkpoint_id
                         FROM checkpoints
                        WHERE thread_id = ?
                     ORDER BY checkpoint_id DESC
                        LIMIT 1
                     )
               )
            """,
            (tid, tid),
        )
        deleted_history_ckpts += cur.rowcount

    if to_keep_latest:
        print(
            f"  trimmed history: checkpoints={deleted_history_ckpts} "
            f"writes={deleted_history_writes} "
            f"(from {len(to_keep_latest)} real threads, latest checkpoint preserved)"
        )

    conn.commit()

    print("\nVACUUM...")
    conn.execute("VACUUM")
    conn.close()

    size_after = db_path.stat().st_size
    freed = size_before - size_after
    print(
        f"Done. size_after={size_after / (1024*1024):.1f} MiB  "
        f"freed={freed / (1024*1024):.1f} MiB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
