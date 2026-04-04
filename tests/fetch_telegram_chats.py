#!/usr/bin/env python3
"""Fetch Telegram chat history from LangSmith traces.

Reads credentials from ../deepagent/.env and queries the LangSmith REST API
to reconstruct full Telegram conversations: user messages, tool calls, and
agent responses.

Usage:
    python fetch_telegram_chats.py              # last 20 conversations
    python fetch_telegram_chats.py --limit 50   # last 50
    python fetch_telegram_chats.py --expand     # show tool call details
    python fetch_telegram_chats.py --thread telegram-890867052  # specific thread
    python fetch_telegram_chats.py --all-threads  # show reactor/skill threads too
"""

import argparse
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


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content) if content else ""


def _extract_user_message(run: dict) -> str:
    """Pull user message from a root run's inputs."""
    inputs = run.get("inputs", {})
    messages = inputs.get("messages", [])
    for m in messages:
        if isinstance(m, dict):
            role = m.get("role", m.get("type", ""))
            if role in ("user", "human"):
                return _extract_text(m.get("content", ""))
    return ""


def _extract_final_response(run: dict) -> str:
    """Pull the final AI response from a root run's outputs."""
    outputs = run.get("outputs") or {}
    messages = outputs.get("messages") or []
    for m in reversed(messages):
        if isinstance(m, dict):
            msg_type = m.get("type", "")
            role = m.get("role", "")
            if msg_type == "constructor":
                id_parts = m.get("id", [])
                if id_parts and "AIMessage" in id_parts[-1]:
                    kwargs = m.get("kwargs", {})
                    content = kwargs.get("content", "")
                    if content and not kwargs.get("tool_calls"):
                        return _extract_text(content)
            elif msg_type in ("ai", "AIMessage") or role == "assistant":
                content = m.get("content", "")
                if content and not m.get("tool_calls"):
                    return _extract_text(content)
    return "(no response captured)"


def _get_thread_id(run: dict) -> str:
    """Extract thread_id from run metadata."""
    extra = run.get("extra", {})
    metadata = extra.get("metadata", {})
    thread_id = metadata.get("thread_id", "")
    if not thread_id:
        config = metadata.get("configurable", {})
        thread_id = config.get("thread_id", "")
    return thread_id


def _format_timestamp(ts_str: str) -> str:
    if not ts_str:
        return "?"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        ist = dt + timedelta(hours=5, minutes=30)
        return ist.strftime("%Y-%m-%d %H:%M:%S IST")
    except Exception:
        return ts_str[:19]


def main():
    parser = argparse.ArgumentParser(description="Fetch Telegram chats from LangSmith")
    parser.add_argument("--limit", type=int, default=20, help="Number of traces to fetch")
    parser.add_argument("--expand", action="store_true", help="Show tool call details")
    parser.add_argument("--thread", type=str, default="", help="Filter by thread_id")
    parser.add_argument("--all-threads", action="store_true", help="Include reactor/skill threads")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--days", type=int, default=30, help="Look back N days")
    args = parser.parse_args()

    env = _load_env(DOTENV)
    api_key = env.get("LANGSMITH_API_KEY", "")
    base = env.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com").rstrip("/")
    project = env.get("LANGSMITH_PROJECT", "homebot-deepagent")

    if not api_key:
        print("ERROR: LANGSMITH_API_KEY not found in", DOTENV, file=sys.stderr)
        sys.exit(1)

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    # Resolve project ID
    resp = requests.get(
        f"{base}/api/v1/sessions",
        headers=headers,
        params={"name": project, "limit": 1},
    )
    resp.raise_for_status()
    sessions = resp.json()
    if not sessions:
        print(f"No project named '{project}' found.", file=sys.stderr)
        sys.exit(1)

    project_id = sessions[0]["id"]

    # Fetch root runs (each = one user message -> agent response cycle)
    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    payload = {
        "session": [project_id],
        "is_root": True,
        "limit": min(args.limit, 100),
        "start_time": since.isoformat(),
        "order_by": ["-start_time"],
    }
    resp = requests.post(f"{base}/api/v1/runs/query", headers=headers, json=payload)
    if resp.status_code != 200:
        print(f"Query failed {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        sys.exit(1)

    runs = resp.json().get("runs", [])

    # Filter and organize
    chats = []
    for run in runs:
        thread_id = _get_thread_id(run)

        if args.thread and thread_id != args.thread:
            continue

        if not args.all_threads and not args.thread:
            if not thread_id.startswith("telegram-"):
                continue

        user_msg = _extract_user_message(run)
        # Strip the context prefix injected by main.py
        if "[Context:" in user_msg:
            parts = user_msg.split("]\n\n", 1)
            if len(parts) == 2:
                user_msg = parts[1]

        response = _extract_final_response(run)
        status = run.get("status", "?")
        latency = run.get("latency")
        error = run.get("error")
        tool_count = run.get("child_tool_runs", 0) or 0

        chat = {
            "timestamp": _format_timestamp(run.get("start_time", "")),
            "thread_id": thread_id,
            "user_message": user_msg,
            "response": response,
            "status": status,
            "latency_s": round(latency, 1) if latency else None,
            "tool_calls": tool_count,
            "error": error,
            "trace_id": run.get("trace_id", run.get("id", "")),
        }
        chats.append(chat)

    chats.reverse()

    if args.json:
        print(json.dumps(chats, indent=2, ensure_ascii=False))
        return

    # Pretty print
    print(f"=== Telegram Chat History ({len(chats)} messages, last {args.days} days) ===\n")

    current_thread = None
    for chat in chats:
        if chat["thread_id"] != current_thread:
            current_thread = chat["thread_id"]
            print(f"--- Thread: {current_thread} ---\n")

        ts = chat["timestamp"]

        print(f"  [{ts}]")
        print(f"  USER: {chat['user_message'][:500]}")

        if chat["tool_calls"]:
            print(f"  TOOLS: {chat['tool_calls']} tool call(s)")

        resp_preview = chat["response"][:600]
        if len(chat["response"]) > 600:
            resp_preview += "..."
        print(f"  BOT:  {resp_preview}")

        meta_parts = []
        if chat["latency_s"]:
            meta_parts.append(f"{chat['latency_s']}s")
        if chat["status"] != "success":
            meta_parts.append(chat["status"])
        if chat["error"]:
            meta_parts.append(f"ERROR: {chat['error'][:100]}")
        if meta_parts:
            print(f"  [{', '.join(meta_parts)}]")
        print()

    # Expand tool calls for each trace if requested
    if args.expand and chats:
        print("\n=== Tool Call Details ===\n")
        for chat in chats:
            if not chat["tool_calls"]:
                continue

            trace_id = chat["trace_id"]
            print(f"  [{chat['timestamp']}] {chat['user_message'][:80]}")

            child_payload = {
                "session": [project_id],
                "trace": trace_id,
                "run_type": "tool",
                "order_by": ["start_time"],
                "limit": 20,
            }
            resp = requests.post(
                f"{base}/api/v1/runs/query", headers=headers, json=child_payload
            )
            if resp.status_code != 200:
                print("    (failed to fetch children)")
                continue

            children = resp.json().get("runs", [])
            for c in children:
                name = c.get("name", "?")
                cstatus = c.get("status", "?")
                clat = c.get("latency")
                clat_str = f"{clat:.2f}s" if clat else "?"
                inp = json.dumps(c.get("inputs", {}), default=str)[:120]
                out = json.dumps(c.get("outputs", {}), default=str)[:120]
                print(f"    {name:<35} {cstatus:<9} {clat_str:>7}")
                print(f"      in:  {inp}")
                print(f"      out: {out}")
            print()


if __name__ == "__main__":
    main()
