#!/usr/bin/env python3
"""Fetch recent LangSmith traces for the homebot-deepagent project.

Reads credentials from ../deepagent/.env and queries the LangSmith REST API
directly (no SDK dependency).
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

DOTENV = Path(__file__).resolve().parent.parent / "deepagent" / ".env"


def _load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def main():
    env = _load_env(DOTENV)
    api_key = env.get("LANGSMITH_API_KEY", "")
    base = env.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").rstrip("/")
    project = env.get("LANGSMITH_PROJECT", "homebot-deepagent")

    if not api_key:
        print("ERROR: LANGSMITH_API_KEY not found in", DOTENV)
        sys.exit(1)

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    print(f"Project: {project}")
    print(f"Endpoint: {base}")
    print()

    # -- Resolve project ID ---------------------------------------------------
    resp = requests.get(
        f"{base}/api/v1/sessions",
        headers=headers,
        params={"name": project, "limit": 1},
    )
    resp.raise_for_status()
    sessions = resp.json()
    if not sessions:
        print(f"No project named '{project}' found.")
        sys.exit(1)

    proj = sessions[0]
    project_id = proj["id"]
    print(f"Project ID: {project_id}")
    print(f"Run count:  {proj.get('run_count', '?')}")
    print()

    # -- Fetch recent root runs (traces) --------------------------------------
    payload = {
        "session": [project_id],
        "is_root": True,
        "limit": 15,
    }
    resp = requests.post(f"{base}/api/v1/runs/query", headers=headers, json=payload)
    if resp.status_code != 200:
        print(f"Runs query failed {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)
    runs = resp.json().get("runs", [])
    print(f"=== Recent traces (last 24h): {len(runs)} ===\n")

    for i, run in enumerate(runs, 1):
        status = run.get("status", "?")
        start = run.get("start_time", "")[:19]
        latency = run.get("latency")
        lat_str = f"{latency:.1f}s" if latency else "?"
        tokens_in = run.get("prompt_tokens", 0) or 0
        tokens_out = run.get("completion_tokens", 0) or 0
        total_tok = run.get("total_tokens", 0) or 0
        trace_id = run.get("trace_id", run.get("id", ""))
        error = run.get("error")

        messages = run.get("inputs", {}).get("messages", [])
        user_msg = ""
        for m in messages:
            if isinstance(m, dict):
                role = m.get("role", m.get("type", ""))
                if role in ("user", "human"):
                    content = m.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            b.get("text", "") for b in content if isinstance(b, dict)
                        )
                    user_msg = content[:120]
                    break

        print(f"[{i:2d}] {start}  {status:<10} {lat_str:>7}  tok={total_tok:>5} ({tokens_in}+{tokens_out})")
        if user_msg:
            print(f"     User: {user_msg}")
        if error:
            print(f"     ERROR: {error[:200]}")
        print(f"     trace: {trace_id}")
        print()

    # -- Expand latest trace to show child runs and LLM input -----------------
    if not runs:
        return

    latest = runs[0]
    trace_id = latest.get("trace_id", latest.get("id"))
    print(f"=== Expanding latest trace: {trace_id} ===\n")

    child_payload = {
        "session": [project_id],
        "trace": trace_id,
        "order_by": ["start_time"],
        "limit": 50,
    }
    resp = requests.post(f"{base}/api/v1/runs/query", headers=headers, json=child_payload)
    resp.raise_for_status()
    children = resp.json().get("runs", [])

    for c in children:
        rt = c.get("run_type", "?")
        cname = c.get("name", "?")
        cstatus = c.get("status", "?")
        clat = c.get("latency")
        clat_str = f"{clat:.2f}s" if clat else "?"
        ctok = c.get("total_tokens", 0) or 0

        inp_preview = ""
        out_preview = ""
        if rt == "tool":
            inp_preview = json.dumps(c.get("inputs", {}), default=str)[:150]
            out = c.get("outputs", {})
            out_preview = json.dumps(out, default=str)[:150]
        elif rt == "llm":
            msgs = c.get("inputs", {}).get("messages", [])
            msg_count = sum(len(g) if isinstance(g, list) else 1 for g in msgs)
            inp_preview = f"{msg_count} messages in context"

        indent = "  " if rt != "chain" else ""
        print(f"{indent}{rt:>10} | {cname:<30} | {cstatus:<9} | {clat_str:>7} | tok={ctok}")
        if inp_preview:
            print(f"{indent}           input:  {inp_preview}")
        if out_preview:
            print(f"{indent}           output: {out_preview}")

    # -- Show messages sent to the first LLM call (history check) -------------
    print("\n--- Messages sent to first LLM call (history check) ---\n")
    for c in children:
        if c.get("run_type") != "llm":
            continue
        msgs = c.get("inputs", {}).get("messages", [])
        for group in msgs:
            items = group if isinstance(group, list) else [group]
            for m in items:
                if not isinstance(m, dict):
                    continue
                # LangChain serializes as {"type": "constructor", "id": [...], "kwargs": {...}}
                if m.get("type") == "constructor":
                    kwargs = m.get("kwargs", {})
                    id_parts = m.get("id", [])
                    role = id_parts[-1] if id_parts else "?"
                    content = kwargs.get("content", "")
                    tool_calls = kwargs.get("tool_calls", [])
                    tool_call_id = kwargs.get("tool_call_id", "")
                    name = kwargs.get("name", "")
                else:
                    role = m.get("type", m.get("role", "?"))
                    content = m.get("content", "")
                    tool_calls = m.get("tool_calls", [])
                    tool_call_id = ""
                    name = m.get("name", "")

                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict)
                    )

                tag = f"[{role}]"
                extra = ""
                if tool_calls:
                    tc_names = [tc.get("name", "?") for tc in tool_calls]
                    extra = f"  -> tool_calls: {tc_names}"
                if tool_call_id:
                    extra += f"  (tool_call_id={tool_call_id[:12]}...)"
                if name:
                    extra += f"  name={name}"

                preview = str(content)[:200] if content else "(empty)"
                print(f"  {tag:<25} {preview}{extra}")
        break


if __name__ == "__main__":
    main()
