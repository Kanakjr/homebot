"""Local sanity-check mirror of the Colab notebook's data pipeline steps.

Runs the same code paths as the first few cells of
`unsloth_qwen3_5_4b_homebot.ipynb`:

    step 0  -- configuration (HF token, repo id)
    step 2  -- load dataset (with raw-parquet fallback + JSON-decode shim)
    step 5.5 -- real-row oversample

against the published HF dataset repo. This does NOT run the GPU-only
cells (model load, LoRA attach, chat template render, training). Its
purpose is to catch auth / schema / data-shape bugs on your laptop
before burning a Colab session.

Usage:
    source ~/Workspace/set-proxy.sh
    source finetuning/.venv/bin/activate
    python finetuning/verify_colab_load.py
    python finetuning/verify_colab_load.py --force-fallback
    python finetuning/verify_colab_load.py --repo kanakjr/homebot-qwen3.5 --oversample 4
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # dotenv is optional -- we still fall back to env vars
    load_dotenv = None  # type: ignore[assignment]

try:
    from datasets import Dataset, DatasetDict, concatenate_datasets, load_dataset
except ImportError as e:
    raise SystemExit(
        "`datasets` is not installed. Activate the finetuning venv: "
        "`source finetuning/.venv/bin/activate`, or install deps via "
        "`source ~/Workspace/set-proxy.sh && pip install -r finetuning/requirements.txt`"
    ) from e


FT_DIR = Path(__file__).resolve().parent
DEFAULT_REPO = "kanakjr/homebot-qwen3.5"


def _load_hub_with_parquet_fallback(
    repo_id: str,
    token: str,
    force_fallback: bool = False,
) -> DatasetDict:
    """Mirror of notebook cell 6's loader.

    Kept byte-for-byte identical to the notebook so that local verification
    exercises the exact same code. The only addition is `force_fallback`
    -- set it True to skip `load_dataset()` and exercise the raw-parquet
    path (the code path that triggers on Colab's older `datasets`)."""
    if not force_fallback:
        try:
            return load_dataset(repo_id, token=token)
        except (TypeError, ValueError) as e:
            print(
                f"[load] load_dataset() schema parse failed: "
                f"{type(e).__name__}: {e}"
            )
            print("[load] falling back to raw parquet via huggingface_hub...")
    else:
        print("[load] --force-fallback: skipping load_dataset() primary path")
        print("[load] going straight to raw-parquet loader")

    import json as _json

    from huggingface_hub import hf_hub_download, list_repo_files
    import pyarrow.parquet as pq

    files = list_repo_files(repo_id, repo_type="dataset", token=token)
    parquet_files = [f for f in files if f.endswith(".parquet")]
    if not parquet_files:
        raise RuntimeError(
            f"No parquet files found in {repo_id} (files: {files[:10]})"
        )

    splits: dict[str, list[str]] = {}
    for path in parquet_files:
        basename = path.split("/")[-1]
        split = basename.split("-")[0]
        if split not in ("train", "validation", "test"):
            split = "train"
        splits.setdefault(split, []).append(path)

    out: dict[str, Dataset] = {}
    for split, paths in splits.items():
        records: list[dict] = []
        for p in paths:
            lp = hf_hub_download(
                repo_id, filename=p, repo_type="dataset", token=token
            )
            records.extend(pq.read_table(lp).to_pylist())

        if records:
            # The newer `datasets` library's `Json` feature type serializes
            # to parquet in one of two shapes depending on the source data:
            #   (a) SCALAR:  whole value as a single JSON string per row
            #                e.g. `messages` becomes str("[{...}, {...}]")
            #   (b) PER-ELEM: a list<string> where each element is itself
            #                 a JSON-encoded dict, e.g.
            #                 `messages` = ["{\"role\":\"user\",...}", ...]
            # We have to handle both when bypassing the feature parser.
            json_scalar_cols: set[str] = set()
            json_list_cols: set[str] = set()
            for col in records[0].keys():
                for r in records:
                    v = r.get(col)
                    if isinstance(v, str) and v[:1] in ("[", "{"):
                        json_scalar_cols.add(col)
                        break
                    if (
                        isinstance(v, list)
                        and v
                        and isinstance(v[0], str)
                        and v[0][:1] in ("[", "{")
                    ):
                        json_list_cols.add(col)
                        break
            for col in sorted(json_scalar_cols):
                decoded = 0
                for r in records:
                    v = r.get(col)
                    if isinstance(v, str):
                        try:
                            r[col] = _json.loads(v)
                            decoded += 1
                        except _json.JSONDecodeError:
                            pass
                if decoded:
                    print(
                        f"[load]   {split}.{col}: decoded {decoded} "
                        f"scalar JSON string(s) (shape: whole value per row)"
                    )
            for col in sorted(json_list_cols):
                decoded_rows = 0
                for r in records:
                    v = r.get(col)
                    if not isinstance(v, list):
                        continue
                    new_list = []
                    row_changed = False
                    for item in v:
                        if isinstance(item, str) and item[:1] in ("[", "{"):
                            try:
                                new_list.append(_json.loads(item))
                                row_changed = True
                                continue
                            except _json.JSONDecodeError:
                                pass
                        new_list.append(item)
                    if row_changed:
                        r[col] = new_list
                        decoded_rows += 1
                if decoded_rows:
                    print(
                        f"[load]   {split}.{col}: decoded per-element JSON "
                        f"strings in {decoded_rows} list(s) (shape: "
                        f"list<string> where each string is a JSON-encoded dict)"
                    )

        out[split] = Dataset.from_list(records)

        sample = out[split][0] if len(out[split]) > 0 else {}
        msgs = sample.get("messages")
        if msgs is not None and (
            not isinstance(msgs, list)
            or (msgs and not isinstance(msgs[0], dict))
        ):
            raise RuntimeError(
                f"[load] messages column in split '{split}' is not list[dict] "
                f"after fallback; type={type(msgs).__name__}, "
                f"inner={type(msgs[0]).__name__ if isinstance(msgs, list) and msgs else 'n/a'}"
            )

        print(
            f"[load] {split}: {len(out[split])} rows from {len(paths)} "
            f"parquet file(s)"
        )

    return DatasetDict(out)


def _summarize(ds: DatasetDict) -> None:
    print()
    print(ds)
    print()
    train_sources = Counter(r.get("source", "?") for r in ds["train"])
    val_sources = Counter(r.get("source", "?") for r in ds["validation"])
    print(f"train sources: {dict(train_sources)}")
    print(f"val   sources: {dict(val_sources)}")
    print()

    ex = ds["train"][0]
    print(f"train[0] keys          : {list(ex.keys())}")
    print(f"train[0].messages type : {type(ex['messages']).__name__}")
    if isinstance(ex["messages"], list) and ex["messages"]:
        m0 = ex["messages"][0]
        print(f"train[0].messages[0]   : role={m0.get('role')} "
              f"content[:80]={str(m0.get('content', ''))[:80]!r}")
        roles = [m.get("role") for m in ex["messages"]]
        print(f"train[0] role sequence : {roles}")

    first_user = next(
        (m["content"][:140] for m in ds["train"][0]["messages"] if m["role"] == "user"),
        "(no user turn found)",
    )
    print(f"first user turn (ex0)  : {first_user!r}")

    tool_calls_total = 0
    tool_rows = 0
    for r in ds["train"]:
        row_has_tc = False
        for m in r["messages"]:
            tcs = m.get("tool_calls") or []
            if m.get("role") == "assistant" and tcs:
                tool_calls_total += len(tcs)
                row_has_tc = True
        if row_has_tc:
            tool_rows += 1
    print(
        f"tool_calls in train    : {tool_calls_total} across {tool_rows}/"
        f"{len(ds['train'])} rows"
    )


def _oversample(ds: DatasetDict, factor: int) -> Dataset:
    """Mirror of notebook cell 14 (step 5.5)."""
    real_rows = ds["train"].filter(lambda r: r.get("source") == "telegram")
    synth_rows = ds["train"].filter(lambda r: r.get("source") != "telegram")
    if len(real_rows) == 0:
        print("[oversample] no real rows found; skipping")
        return ds["train"]
    real_repeated = concatenate_datasets([real_rows] * factor)
    final = concatenate_datasets([synth_rows, real_repeated]).shuffle(seed=3407)
    print(
        f"[oversample] real rows {len(real_rows)} -> {len(real_repeated)} "
        f"({factor}x); synth unchanged at {len(synth_rows)}; "
        f"final train size = {len(final)}"
    )
    return final


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--repo",
        default=os.getenv("HUB_DATASET_REPO", DEFAULT_REPO),
        help="HF dataset repo id (default: %(default)s)",
    )
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help=(
            "Skip load_dataset() and go straight to the raw-parquet fallback "
            "-- the code path that actually runs on Colab's older `datasets`"
        ),
    )
    parser.add_argument(
        "--oversample",
        type=int,
        default=int(os.getenv("REAL_OVERSAMPLE", "4")),
        help="REAL_OVERSAMPLE factor to test (default: %(default)s; set to 0 to skip)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="HF token; falls back to HF_TOKEN env / finetuning/.env",
    )
    args = parser.parse_args()

    if load_dotenv is not None:
        load_dotenv(FT_DIR / ".env")
    token = (
        args.token
        or os.getenv("HF_TOKEN")
        or os.getenv("HUGGING_FACE_HUB_TOKEN")
        or ""
    )
    if not token:
        print(
            "ERROR: HF_TOKEN not set. Put it in finetuning/.env or pass --token.",
            file=sys.stderr,
        )
        return 1
    os.environ["HF_TOKEN"] = token
    os.environ["HUGGING_FACE_HUB_TOKEN"] = token

    print("=" * 72)
    print(f"[config] repo          = {args.repo}")
    print(f"[config] HF_TOKEN      = set (len={len(token)})")
    print(f"[config] force-fallback= {args.force_fallback}")
    print(f"[config] oversample    = {args.oversample}")
    print("=" * 72)

    ds = _load_hub_with_parquet_fallback(
        args.repo, token, force_fallback=args.force_fallback
    )
    _summarize(ds)

    if args.oversample > 0:
        print()
        _oversample(ds, factor=args.oversample)

    print()
    print("=" * 72)
    print(
        "OK -- local verify passed. The Colab notebook's Step 2 + Step 5.5 "
        "should behave the same."
    )
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
