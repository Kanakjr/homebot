"""Push the merged Qwen3.5 training + validation JSONLs to the Hugging Face Hub.

Usage:
    python push_to_hub.py
    python push_to_hub.py --repo kanakjr/homebot-qwen3.5 --public
    python push_to_hub.py --train data/qwen3_5_training.jsonl --val data/qwen3_5_val.jsonl

Requires the HF_TOKEN env var (or --token). The repo is created on push if it
does not exist. Both splits are uploaded to the same dataset repo as `train`
and `validation`.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Optional

from datasets import DatasetDict, load_dataset
from dotenv import load_dotenv
from huggingface_hub import login

load_dotenv()

FINETUNING_DIR = Path(__file__).resolve().parent
DATA_DIR = FINETUNING_DIR / "data"
DEFAULT_TRAIN = DATA_DIR / "qwen3_5_training.jsonl"
DEFAULT_VAL = DATA_DIR / "qwen3_5_val.jsonl"
DEFAULT_REPO = "kanakjr/homebot-qwen3.5"


def push_dataset_to_hub(
    train_path: Path = DEFAULT_TRAIN,
    val_path: Optional[Path] = DEFAULT_VAL,
    dataset_repo: str = DEFAULT_REPO,
    private: bool = True,
    token: Optional[str] = None,
) -> None:
    token = token or os.getenv("HF_TOKEN")
    if not token:
        print("ERROR: HF_TOKEN not set (env or --token)")
        return

    if not train_path.exists():
        print(f"ERROR: training file not found: {train_path}")
        return

    print(f"Logging into Hugging Face (repo={dataset_repo}, private={private})...")
    login(token=token, add_to_git_credential=False)

    print(f"Loading training split from {train_path}...")
    train_ds = load_dataset("json", data_files=str(train_path), split="train")

    splits = {"train": train_ds}
    if val_path and val_path.exists() and val_path.stat().st_size > 0:
        print(f"Loading validation split from {val_path}...")
        splits["validation"] = load_dataset("json", data_files=str(val_path), split="train")
    else:
        print(f"[push] validation file missing or empty, skipping ({val_path})")

    dsd = DatasetDict(splits)

    print("Pushing to Hub...")
    dsd.push_to_hub(dataset_repo, private=private)

    print(f"OK pushed -> https://huggingface.co/datasets/{dataset_repo}")
    for name, ds in splits.items():
        print(f"    {name}: {len(ds)} rows")


def main() -> int:
    parser = argparse.ArgumentParser(description="Push Qwen3.5 fine-tune dataset to HF Hub")
    parser.add_argument("--train", type=str, default=str(DEFAULT_TRAIN))
    parser.add_argument("--val", type=str, default=str(DEFAULT_VAL))
    parser.add_argument("--repo", type=str, default=DEFAULT_REPO)
    parser.add_argument("--public", action="store_true", help="Push as a public dataset (default: private)")
    parser.add_argument("--token", type=str, default=None, help="HF token; falls back to HF_TOKEN env")
    args = parser.parse_args()

    push_dataset_to_hub(
        train_path=Path(args.train),
        val_path=Path(args.val) if args.val else None,
        dataset_repo=args.repo,
        private=not args.public,
        token=args.token,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
