"""Merge real + synthetic conversation JSONLs and produce a train/val split.

Input:
    data/real_telegram.jsonl      (from extract_telegram_dataset.py)
    data/qwen_training_dataset.jsonl (from dataset_formatter.py)

Output:
    data/qwen3_5_training.jsonl   (90% of unique examples)
    data/qwen3_5_val.jsonl        (10%)

Dedup strategy: hash of the ordered list of (role, content, tool_call sig)
EXCLUDING the system message, so minor system-prompt drift between runs does
not produce false duplicates.

Safety:
- If both real and synthetic variants of the same chain exist, the REAL one
  wins (more authentic data).
- Rows missing a final assistant text are dropped (already filtered upstream,
  but we re-check defensively).
- Seeded shuffle for reproducible splits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

FINETUNING_DIR = Path(__file__).resolve().parent
DATA_DIR = FINETUNING_DIR / "data"

DEFAULT_REAL = DATA_DIR / "real_telegram.jsonl"
DEFAULT_SYNTHETIC = DATA_DIR / "qwen_training_dataset.jsonl"
DEFAULT_TRAIN = DATA_DIR / "qwen3_5_training.jsonl"
DEFAULT_VAL = DATA_DIR / "qwen3_5_val.jsonl"

# Real data is rarer and more valuable -- sort order puts it first so it wins
# on dedup collisions.
SOURCE_PRIORITY = {"telegram": 0, "synthetic": 1}


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        print(f"[merge] WARNING: {path} not found, skipping")
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"[merge] bad json at {path.name}:{i}, skipping")
    print(f"[merge] loaded {len(rows)} rows from {path}")
    return rows


def _chain_signature(messages: List[Dict[str, Any]]) -> str:
    """Hash that IGNORES the system prompt but keeps user + assistant + tool calls."""
    payload = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        entry = {
            "role": role,
            "content": m.get("content", ""),
            "name": m.get("name"),
        }
        tc = m.get("tool_calls") or []
        if tc:
            entry["tool_calls"] = [
                {
                    "name": t.get("function", {}).get("name"),
                    "arguments": t.get("function", {}).get("arguments"),
                }
                for t in tc
            ]
        payload.append(entry)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _chain_is_valid(messages: List[Dict[str, Any]]) -> bool:
    if len(messages) < 2:
        return False
    roles = {m.get("role") for m in messages}
    if "user" not in roles:
        return False
    last = messages[-1]
    if last.get("role") != "assistant" or last.get("tool_calls"):
        return False
    content = last.get("content", "")
    return isinstance(content, str) and bool(content.strip())


def merge_and_split(
    real_path: Path,
    synthetic_path: Path,
    train_path: Path,
    val_path: Path,
    val_fraction: float = 0.1,
    seed: int = 42,
) -> Tuple[int, int]:
    real = _load_jsonl(real_path)
    synthetic = _load_jsonl(synthetic_path)

    combined = real + synthetic
    combined.sort(key=lambda r: SOURCE_PRIORITY.get(r.get("source", "synthetic"), 2))

    seen: set = set()
    kept: List[Dict[str, Any]] = []
    dropped_invalid = 0
    dropped_dup = 0

    for row in combined:
        messages = row.get("messages") or []
        if not _chain_is_valid(messages):
            dropped_invalid += 1
            continue
        sig = _chain_signature(messages)
        if sig in seen:
            dropped_dup += 1
            continue
        seen.add(sig)
        kept.append(row)

    if not kept:
        print("[merge] ERROR: no valid examples found in input files")
        return 0, 0

    rng = random.Random(seed)
    rng.shuffle(kept)

    val_size = max(1, int(len(kept) * val_fraction)) if len(kept) >= 10 else 0
    val_rows = kept[:val_size]
    train_rows = kept[val_size:]

    train_path.parent.mkdir(parents=True, exist_ok=True)
    with train_path.open("w") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with val_path.open("w") as f:
        for r in val_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(
        f"[merge] total={len(kept)} train={len(train_rows)} val={len(val_rows)} "
        f"dropped_invalid={dropped_invalid} dropped_dup={dropped_dup}"
    )
    _print_source_breakdown(train_rows, "train")
    _print_source_breakdown(val_rows, "val")
    _warn_source_ratio(kept)
    _spot_check_samples(train_rows, k=5, seed=seed)
    print(f"[merge] wrote -> {train_path}")
    print(f"[merge] wrote -> {val_path}")
    return len(train_rows), len(val_rows)


def _print_source_breakdown(rows: List[Dict[str, Any]], label: str) -> None:
    counts: Dict[str, int] = {}
    for r in rows:
        src = r.get("source", "unknown")
        counts[src] = counts.get(src, 0) + 1
    if counts:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"[merge] {label} sources: {summary}")


def _warn_source_ratio(rows: List[Dict[str, Any]]) -> None:
    """Surface a warning if synthetic data massively outweighs real data."""
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r.get("source", "unknown")] = counts.get(r.get("source", "unknown"), 0) + 1
    real_n = counts.get("telegram", 0)
    synth_n = counts.get("synthetic", 0)
    if real_n == 0 and synth_n > 0:
        print(f"[merge] WARNING: dataset has {synth_n} synthetic and 0 real examples -- consider oversampling real during training.")
        return
    if real_n > 0 and synth_n / max(real_n, 1) >= 5.0:
        print(
            f"[merge] WARNING: synthetic/real ratio is {synth_n}/{real_n} (>=5x). "
            f"Real data is more authentic; consider oversampling real in the trainer "
            f"(sample_weights) or capping synthetic."
        )


def _format_sample_preview(row: Dict[str, Any], max_chars_per_msg: int = 200) -> str:
    """Compact preview of one training row: source tag + each non-system message."""
    source = row.get("source", "?")
    msgs = row.get("messages") or []
    lines: List[str] = [f"--- source={source} trace_id={str(row.get('trace_id',''))[:8]}"]
    for m in msgs:
        role = m.get("role", "?")
        if role == "system":
            continue
        content = m.get("content", "") or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        content = content.replace("\n", " ")
        if len(content) > max_chars_per_msg:
            content = content[:max_chars_per_msg] + "..."
        tc_sig = ""
        tc_list = m.get("tool_calls") or []
        if tc_list:
            names = [ (tc.get("function") or {}).get("name", "?") for tc in tc_list ]
            tc_sig = f"  [tool_calls: {', '.join(names)}]"
        lines.append(f"  [{role}] {content}{tc_sig}")
    return "\n".join(lines)


def _spot_check_samples(rows: List[Dict[str, Any]], k: int = 5, seed: int = 42) -> None:
    if not rows:
        return
    rng = random.Random(seed + 1)
    sample = rng.sample(rows, min(k, len(rows)))
    print(f"\n[merge] spot-check: {len(sample)} random train examples (content truncated)")
    print("=" * 70)
    for r in sample:
        print(_format_sample_preview(r))
    print("=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge real + synthetic JSONL datasets")
    parser.add_argument("--real", type=str, default=str(DEFAULT_REAL))
    parser.add_argument("--synthetic", type=str, default=str(DEFAULT_SYNTHETIC))
    parser.add_argument("--train-out", type=str, default=str(DEFAULT_TRAIN))
    parser.add_argument("--val-out", type=str, default=str(DEFAULT_VAL))
    parser.add_argument("--val-fraction", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    train_n, val_n = merge_and_split(
        real_path=Path(args.real),
        synthetic_path=Path(args.synthetic),
        train_path=Path(args.train_out),
        val_path=Path(args.val_out),
        val_fraction=args.val_fraction,
        seed=args.seed,
    )
    return 0 if train_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
