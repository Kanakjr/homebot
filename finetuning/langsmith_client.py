"""LangSmith trace extractor for distillation-simulation runs.

Queries the configured LangSmith project for chain runs tagged with either
our simulator run-id or the generic "distillation_simulation" tag, and
exports each run's inputs / outputs / metadata to JSONL. Used as Stage 3
of the fine-tune pipeline (see README.md).

Uses server-side filter expressions and auto-paginates so ALL matching
traces are fetched, not just the first 100.
"""

import argparse
import json
import os
from typing import Iterable, List, Optional

from dotenv import load_dotenv
from langsmith import Client

backend_env = os.path.join(os.path.dirname(__file__), "..", "deepagent", ".env")
load_dotenv(backend_env)
load_dotenv(override=True)

# Some environments use LANGCHAIN_API_KEY, some use LANGSMITH_API_KEY
if "LANGSMITH_API_KEY" in os.environ and "LANGCHAIN_API_KEY" not in os.environ:
    os.environ["LANGCHAIN_API_KEY"] = os.environ["LANGSMITH_API_KEY"]

client = Client()

PROJECT_NAME = os.getenv("LANGSMITH_PROJECT", os.getenv("LANGCHAIN_PROJECT", "homebot-deepagent"))


def _build_tag_filter(run_id: Optional[str]) -> str:
    """Build a LangSmith filter expression that matches our simulator traces.

    - If a run_id is supplied, match chain runs that carry that tag.
    - Otherwise fall back to the generic "distillation_simulation" tag that
      `run_deepagent_simulation.py` always attaches.
    """
    if run_id:
        return f'has(tags, "{run_id}")'
    return 'has(tags, "distillation_simulation")'


def _paginated_runs(filter_expr: str) -> Iterable:
    """Yield every chain run from the project matching the filter.

    The LangSmith SDK's list_runs returns a generator that already paginates
    internally; we just iterate it. Passing no explicit `limit` keeps
    pagination on.
    """
    return client.list_runs(
        project_name=PROJECT_NAME,
        run_type="chain",
        filter=filter_expr,
    )


def fetch_top_traces(run_id: Optional[str] = None, limit: Optional[int] = None) -> List[dict]:
    """Fetch synthetic distillation traces. `limit=None` means no cap."""
    print(f"Fetching distilled traces from project: {PROJECT_NAME}")
    filter_expr = _build_tag_filter(run_id)
    if run_id:
        print(f"Filter: by run-id tag '{run_id}'")
    else:
        print("Filter: by tag 'distillation_simulation'")

    extracted_data: List[dict] = []
    rejected_missing_io = 0

    for run in _paginated_runs(filter_expr):
        if limit is not None and len(extracted_data) >= limit:
            break
        if not run.inputs or not run.outputs:
            rejected_missing_io += 1
            continue
        metadata = (run.extra or {}).get("metadata", {}) if run.extra else {}
        extracted_data.append({
            "id": str(run.id),
            "inputs": run.inputs,
            "outputs": run.outputs,
            "tags": list(run.tags or []),
            "thread_id": metadata.get("thread_id", ""),
        })

    print(
        f"Extracted {len(extracted_data)} runs "
        f"(rejected_missing_io={rejected_missing_io})"
    )
    return extracted_data


def export_to_jsonl(data: List[dict], filename: str = "data/langsmith_export.jsonl") -> None:
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    with open(filename, "w") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")
    print(f"Exported to {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LangSmith Extractor for synthetic traces")
    parser.add_argument("--run-id", type=str, default=None, help="Filter by simulator run-id tag")
    parser.add_argument("--limit", type=int, default=None, help="Hard cap on traces (default: none)")
    parser.add_argument("--out", type=str, default="data/langsmith_export.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    runs = fetch_top_traces(run_id=args.run_id, limit=args.limit)
    if runs:
        export_to_jsonl(runs, filename=args.out)
    else:
        print("No usable traces found. Try generating synthetic data first.")
