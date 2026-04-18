#!/usr/bin/env python3
"""
DeepAgent Simulation Runner (HTTP Mode)
Sends synthetic queries to the live DeepAgent FastAPI server as if from a user chat input.
This guarantees exact environment matches and allows the live server to record traces exactly as it does for real users.
"""

import os
import sys
import json
import time
import requests
import argparse
from dotenv import load_dotenv

# Load the backend's .env so we get the correct API_KEY
backend_env = os.path.join(os.path.dirname(__file__), "..", "deepagent", ".env")
load_dotenv(backend_env)
# Load local .env to override any specific keys (like MODEL)
load_dotenv(override=True)

def run_simulation(
    limit=None,
    skip=0,
    base_url="http://localhost:8322",
    model="google_genai:gemini-3-flash-preview",
    run_id=None,
    timeout=180,
    delay=1.0,
    error_delay=None,
):
    queries_file = os.path.join(os.path.dirname(__file__), "data", "synthetic_queries.json")
    if not os.path.exists(queries_file):
        print(f"Error: {queries_file} not found. Please run dataset generator first.")
        sys.exit(1)

    with open(queries_file, "r") as f:
        queries = json.load(f)

    total_before_slice = len(queries)

    if skip:
        if skip >= len(queries):
            print(f"--skip {skip} >= total {len(queries)} queries; nothing to do.")
            return
        queries = queries[skip:]
        print(f"Skipping first {skip} queries, resuming from query #{skip + 1}.")

    if limit is not None:
        queries = queries[:limit]
        print(f"Limiting execution to {limit} queries.")

    run_prefix = run_id if run_id else f"run_{int(time.time())}"

    if error_delay is None:
        error_delay = max(delay * 3.0, 15.0)

    print(f"Ready to run {len(queries)} simulation queries against {base_url}.")
    print(f"  (total in file: {total_before_slice}, skipped: {skip}, per-query timeout: {timeout}s)")
    print(f"  base delay: {delay:.1f}s   error-triggered delay: {error_delay:.1f}s")
    print(f"Teacher Model: {model}")
    print(f"Run ID: {run_prefix}")
    print("-" * 50)

    ok = 0
    failed = 0
    hallucinated = 0
    repaired = 0
    timed_out = 0
    server_errors = 0

    url = f"{base_url}/api/chat/stream"
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": os.getenv("API_KEY", ""),
    }

    for idx, q in enumerate(queries):
        global_i = skip + idx
        print(f"[{global_i + 1}/{total_before_slice}] Executing: '{q}'")

        def attempt_query(message_text):
            payload = {
                "message": message_text,
                "thread_id": f"{run_prefix}_{global_i}",
                "model": model,
                "tags": ["distillation_simulation", run_prefix],
            }
            response = requests.post(url, json=payload, headers=headers, stream=True, timeout=timeout)
            response.raise_for_status()
            tool_called = False
            saw_error = False
            for line in response.iter_lines():
                if not line:
                    continue
                decoded = line.decode("utf-8", errors="replace")
                if decoded.startswith("event: error"):
                    print(f"  -> WARNING: Server emitted an error event!")
                    saw_error = True
                elif decoded.startswith("event: tool_call"):
                    tool_called = True
            return tool_called, saw_error

        saw_error = False
        try:
            tool_used, saw_error = attempt_query(q)

            if tool_used:
                print(f"  -> Successfully generated zero-shot trace. (Thread ID: distill_sim_{run_prefix}_{global_i})")
                ok += 1
            else:
                print(f"  -> Model hallucinated text instead of using tools. Retrying via multi-turn repair...")
                hallucinated += 1
                repair_prompt = (
                    "You did not actually perform the action using the tool. Please do not "
                    "reply with text only. Use the appropriate tool to fulfill my previous request."
                )
                tool_used_retry, saw_error_retry = attempt_query(repair_prompt)
                saw_error = saw_error or saw_error_retry
                if tool_used_retry:
                    print(f"  -> Successfully repaired trace! (Thread ID: distill_sim_{run_prefix}_{global_i})")
                    repaired += 1
                else:
                    print(f"  -> ERROR: Model refused to use tools even after repair.")

        except requests.exceptions.ReadTimeout:
            print(f"  -> TIMEOUT after {timeout}s. Skipping and continuing. (query #{global_i + 1})")
            timed_out += 1
            failed += 1
        except requests.exceptions.ConnectionError as e:
            print(f"  -> CONNECTION ERROR: {e}")
            print("  Backend is unreachable. Retrying once after 15s pause...")
            time.sleep(15)
            try:
                tool_used, saw_error = attempt_query(q)
                if tool_used:
                    print(f"  -> Recovered after reconnect. (Thread ID: distill_sim_{run_prefix}_{global_i})")
                    ok += 1
                    _pause = error_delay if saw_error else delay
                    time.sleep(_pause)
                    continue
                server_errors += 1
                failed += 1
            except requests.exceptions.RequestException as e2:
                print(f"  -> Still failing after retry: {e2}. Skipping.")
                server_errors += 1
                failed += 1
        except requests.exceptions.RequestException as e:
            print(f"  -> REQUEST FAILED: {e}. Skipping.")
            server_errors += 1
            failed += 1

        pause = error_delay if saw_error else delay
        if saw_error:
            print(f"  -> Rate-limit detected; sleeping {pause:.1f}s before next query.")
        time.sleep(pause)

    print("-" * 50)
    print(
        f"Summary: ok={ok} hallucinated={hallucinated} repaired={repaired} "
        f"timed_out={timed_out} server_errors={server_errors} total_failed={failed} "
        f"of {len(queries)} attempted (run_id={run_prefix})"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DeepAgent HTTP Simulator")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of queries after skip.")
    parser.add_argument("--skip", type=int, default=0, help="Resume: skip the first N queries.")
    parser.add_argument("--host", type=str, default="http://localhost:8322", help="FastAPI host URL")
    parser.add_argument("--model", type=str, default="google_genai:gemini-3-flash-preview", help="Model to inject into DeepAgent")
    parser.add_argument("--run-id", type=str, default=None, help="Custom Run ID to tag the batch.")
    parser.add_argument("--timeout", type=int, default=180, help="Per-query HTTP timeout in seconds (default 180)")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Seconds to sleep between queries to pace the teacher model (default 1.0).")
    parser.add_argument("--error-delay", type=float, default=None,
                        help="Seconds to sleep after a rate-limit / error event. Defaults to max(delay*3, 15).")
    args = parser.parse_args()

    run_simulation(
        limit=args.limit,
        skip=args.skip,
        base_url=args.host,
        model=args.model,
        run_id=args.run_id,
        timeout=args.timeout,
        delay=args.delay,
        error_delay=args.error_delay,
    )
