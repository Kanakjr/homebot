#!/usr/bin/env python3
"""Extract real multi-turn Telegram conversations from LangSmith.

Walks every telegram-prefixed thread in the configured LangSmith project,
pulls the child LLM runs for each conversation turn, and stitches the full
message chain into ChatML training examples:

    system -> user -> assistant+tool_calls -> tool -> ... -> assistant (final text)

Output: data/real_telegram.jsonl (one conversation per line).

Usage (env loaded from ../deepagent/.env):
    python extract_telegram_dataset.py
    python extract_telegram_dataset.py --days 60 --limit 500
    python extract_telegram_dataset.py --thread telegram-123456 --out data/my.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

FINETUNING_DIR = Path(__file__).resolve().parent
APP_DIR = FINETUNING_DIR.parent
DEEPAGENT_DOTENV = APP_DIR / "deepagent" / ".env"

sys.path.insert(0, str(APP_DIR))
try:
    from deepagent.agent import get_system_prompt  # type: ignore
except Exception:
    get_system_prompt = None  # type: ignore

try:
    from deepagent.config import HA_HIDDEN_ENTITIES  # type: ignore
except Exception:
    HA_HIDDEN_ENTITIES = frozenset({"light.printer_chamber_light"})  # type: ignore

DEFAULT_OUTPUT = FINETUNING_DIR / "data" / "real_telegram.jsonl"
CHANNEL_PREFIX_MARKERS = ("[Telegram]", "[Context:", "[Dashboard]", "[CLI]")
MAX_TOOL_OUTPUT_CHARS = 4000

# Entity IDs that were renamed server-side (commit c3656cf). Historical traces
# from before the rename still reference the old IDs; we rewrite them so the
# fine-tuned model learns the current names. Full-string keys only -- order
# does not matter because keys and values share no substrings.
ENTITY_RENAMES: Dict[str, str] = {
    "fan.xiaomi_smart_air_purifier_4": "fan.air_purifier",
    "fan.a1_03919d550407275_cooling_fan": "fan.printer_fan",
    "camera.a1_03919d550407275_camera": "camera.printer",
    "sensor.sensor_temperature": "sensor.room_temperature",
    "sensor.sensor_humidity": "sensor.room_humidity",
    "sensor.xiaomi_smart_air_purifier_4_temperature": "sensor.air_purifier_temperature",
    "sensor.xiaomi_smart_air_purifier_4_humidity": "sensor.air_purifier_humidity",
    "sensor.xiaomi_smart_air_purifier_4_pm2_5": "sensor.air_purifier_pm2_5",
    "sensor.pixel_9_pro_battery_level": "sensor.pixel_battery_level",
    "sensor.galaxy_watch8_classic_krbx_battery_level": "sensor.watch_battery_level",
}

# Entities that were fully removed from the inventory or deliberately hidden.
# Any chain containing one of these tokens is dropped rather than rewritten --
# we don't want to teach the model to call dead or blocked entities.
DROP_ENTITY_TOKENS = frozenset({
    "light.a1_03919d550407275_chamber_light",
    "person.sarath",
    "scene.movie_time",
    "scene.movie_time_paused",
    "scene.relax",
}) | frozenset(HA_HIDDEN_ENTITIES)


def _apply_renames(text: str) -> str:
    if not text or not isinstance(text, str):
        return text
    for old, new in ENTITY_RENAMES.items():
        if old in text:
            text = text.replace(old, new)
    return text


def _chain_has_drop(chain: List[Dict[str, Any]]) -> bool:
    """True if any message content / tool_call argument mentions a removed entity."""
    for m in chain:
        content = m.get("content", "")
        if isinstance(content, str) and any(tok in content for tok in DROP_ENTITY_TOKENS):
            return True
        for tc in m.get("tool_calls", []) or []:
            args = (tc.get("function") or {}).get("arguments", "")
            if isinstance(args, str) and any(tok in args for tok in DROP_ENTITY_TOKENS):
                return True
    return False


def _sanitize_chain(chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Rewrite renamed entity IDs in-place inside content + tool_call arguments."""
    for m in chain:
        if isinstance(m.get("content"), str):
            m["content"] = _apply_renames(m["content"])
        for tc in m.get("tool_calls", []) or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments", "")
            if isinstance(args, str):
                fn["arguments"] = _apply_renames(args)
    return chain


def _load_env(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def _extract_text(content: Any) -> str:
    """Flatten LangChain content (str or [{type,text,...}]) into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type")
                if btype == "text":
                    parts.append(block.get("text", ""))
                elif btype == "tool_use":
                    continue
                elif "text" in block:
                    parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


def _strip_channel_prefix(user_msg: str) -> str:
    if not user_msg or not any(m in user_msg for m in CHANNEL_PREFIX_MARKERS):
        return user_msg
    parts = user_msg.split("\n\n", 1)
    if len(parts) == 2 and any(m in parts[0] for m in CHANNEL_PREFIX_MARKERS):
        return parts[1].lstrip()
    return user_msg


def _convert_tool_calls(raw_tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize LangChain / OpenAI tool_calls to Qwen ChatML tool_calls."""
    out: List[Dict[str, Any]] = []
    for tc in raw_tool_calls or []:
        if not isinstance(tc, dict):
            continue
        if "function" in tc and isinstance(tc["function"], dict):
            fn = tc["function"]
            name = fn.get("name", "")
            arguments = fn.get("arguments", "")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            out.append({
                "id": tc.get("id") or f"call_{len(out)}",
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            })
            continue

        name = tc.get("name", "")
        args = tc.get("args", {})
        if not isinstance(args, str):
            args = json.dumps(args, ensure_ascii=False)
        out.append({
            "id": tc.get("id") or f"call_{len(out)}",
            "type": "function",
            "function": {"name": name, "arguments": args},
        })
    return out


def _normalize_langchain_message(msg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a LangChain dict message (direct or 'constructor' serialized) to ChatML."""
    if not isinstance(msg, dict):
        return None

    if msg.get("type") == "constructor":
        id_parts = msg.get("id", []) or []
        hint = id_parts[-1] if id_parts else ""
        kwargs = msg.get("kwargs", {}) or {}
        if "SystemMessage" in hint:
            return {"role": "system", "content": _extract_text(kwargs.get("content", ""))}
        if "HumanMessage" in hint:
            return {"role": "user", "content": _extract_text(kwargs.get("content", ""))}
        if "AIMessage" in hint:
            content = _extract_text(kwargs.get("content", ""))
            tool_calls = kwargs.get("tool_calls") or kwargs.get("additional_kwargs", {}).get("tool_calls", [])
            out: Dict[str, Any] = {"role": "assistant", "content": content}
            converted = _convert_tool_calls(tool_calls)
            if converted:
                out["tool_calls"] = converted
            return out
        if "ToolMessage" in hint:
            return {
                "role": "tool",
                "tool_call_id": kwargs.get("tool_call_id", ""),
                "name": kwargs.get("name", ""),
                "content": _extract_text(kwargs.get("content", "")),
            }
        return None

    mtype = msg.get("type") or msg.get("role") or ""
    if mtype in ("system", "SystemMessage"):
        return {"role": "system", "content": _extract_text(msg.get("content", ""))}
    if mtype in ("human", "user", "HumanMessage"):
        return {"role": "user", "content": _extract_text(msg.get("content", ""))}
    if mtype in ("ai", "assistant", "AIMessage"):
        content = _extract_text(msg.get("content", ""))
        tool_calls = msg.get("tool_calls") or msg.get("additional_kwargs", {}).get("tool_calls", [])
        out = {"role": "assistant", "content": content}
        converted = _convert_tool_calls(tool_calls)
        if converted:
            out["tool_calls"] = converted
        return out
    if mtype in ("tool", "ToolMessage"):
        return {
            "role": "tool",
            "tool_call_id": msg.get("tool_call_id", ""),
            "name": msg.get("name", ""),
            "content": _extract_text(msg.get("content", "")),
        }
    return None


def _truncate_tool_content(chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clamp very long tool outputs to keep sequences below context budgets."""
    for m in chain:
        if m.get("role") == "tool":
            c = m.get("content", "")
            if isinstance(c, str) and len(c) > MAX_TOOL_OUTPUT_CHARS:
                m["content"] = c[:MAX_TOOL_OUTPUT_CHARS] + "\n... [truncated]"
    return chain


# Canonical text of the simulator's repair nudge. Any user turn that starts
# with this phrase is an artifact of the simulator, NOT a real user, so we
# splice it out along with the empty hallucinated assistant turn that
# triggered it.
_REPAIR_PROMPT_PREFIX = "You did not actually perform the action using the tool"

# Regex for vendor-specific "reasoning" blocks. Gemini 2.5/3 emit these in the
# assistant text; stripping them keeps the distilled output clean for Qwen.
_THINKING_TAG_RE = re.compile(
    r"<thinking>.*?</thinking>|<think>.*?</think>",
    flags=re.DOTALL | re.IGNORECASE,
)
_REASONING_TAG_RE = re.compile(
    r"<reasoning>.*?</reasoning>",
    flags=re.DOTALL | re.IGNORECASE,
)


def _strip_reasoning_tags(text: str) -> str:
    if not isinstance(text, str):
        return text
    text = _THINKING_TAG_RE.sub("", text)
    text = _REASONING_TAG_RE.sub("", text)
    return text.strip()


def _strip_reasoning_from_chain(chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for m in chain:
        if m.get("role") == "assistant" and isinstance(m.get("content"), str):
            m["content"] = _strip_reasoning_tags(m["content"])
    return chain


def _splice_repair_turns(chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Remove simulator repair-prompt user turns and the preceding empty assistant
    hallucination so the chain looks like a natural conversation.

    A repair segment looks like:
        [user]         original query
        [assistant]    hallucinated TEXT (no tool_calls, short answer)
        [user]         "You did not actually perform..."
        [assistant]    tool_calls   <-- the real answer we want to keep

    We walk the chain and drop the repair user + the preceding hallucinated
    assistant turn whenever we find them.
    """
    if not chain:
        return chain
    cleaned: List[Dict[str, Any]] = []
    i = 0
    while i < len(chain):
        msg = chain[i]
        if (
            msg.get("role") == "user"
            and isinstance(msg.get("content"), str)
            and msg["content"].lstrip().startswith(_REPAIR_PROMPT_PREFIX)
        ):
            # Drop the preceding hallucinated assistant turn (if it was a
            # tool-less text that came right after a user turn).
            if (
                cleaned
                and cleaned[-1].get("role") == "assistant"
                and not cleaned[-1].get("tool_calls")
            ):
                cleaned.pop()
            # Skip the repair user turn itself.
            i += 1
            continue
        cleaned.append(msg)
        i += 1
    return cleaned


def _tool_calls_json_valid(chain: List[Dict[str, Any]]) -> bool:
    """Return False if any assistant tool_call has malformed JSON arguments."""
    for m in chain:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls", []) or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments", "")
            if args is None or args == "":
                continue
            if not isinstance(args, str):
                continue
            try:
                json.loads(args)
            except (ValueError, json.JSONDecodeError):
                return False
    return True


def _final_assistant_word_count(chain: List[Dict[str, Any]]) -> int:
    if not chain:
        return 0
    last = chain[-1]
    if last.get("role") != "assistant":
        return 0
    content = last.get("content", "")
    if not isinstance(content, str):
        return 0
    return len([w for w in content.split() if w.strip()])


def _chain_is_valid(chain: List[Dict[str, Any]]) -> bool:
    """A valid chain ends with a meaningful assistant text and has at least user+assistant."""
    if len(chain) < 2:
        return False
    roles = [m.get("role") for m in chain]
    if "user" not in roles:
        return False
    last = chain[-1]
    if last.get("role") != "assistant":
        return False
    if last.get("tool_calls"):
        return False
    content = last.get("content", "")
    if not isinstance(content, str) or not content.strip():
        return False
    if _final_assistant_word_count(chain) < 3:
        return False
    if not _tool_calls_json_valid(chain):
        return False
    return True


def _extract_messages_from_langchain(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize a LangChain messages array to ChatML, stripping duplicates & empties."""
    out: List[Dict[str, Any]] = []
    for m in messages or []:
        norm = _normalize_langchain_message(m)
        if not norm:
            continue
        out.append(norm)
    return out


def _pick_canonical_llm_run(llm_runs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return the LLM run whose input history is the longest complete conversation."""
    if not llm_runs:
        return None

    def history_len(r: Dict[str, Any]) -> int:
        inp = r.get("inputs", {}) or {}
        msgs = inp.get("messages", [])
        if msgs and isinstance(msgs[0], list):
            msgs = msgs[0]
        return len(msgs or [])

    return max(llm_runs, key=history_len)


def _build_chain_from_llm_run(llm_run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Combine the LLM run's input history + its output into one ChatML chain."""
    inputs = llm_run.get("inputs", {}) or {}
    msgs = inputs.get("messages", [])
    if msgs and isinstance(msgs[0], list):
        msgs = msgs[0]
    chain = _extract_messages_from_langchain(msgs or [])

    outputs = llm_run.get("outputs", {}) or {}
    final_candidates: List[Dict[str, Any]] = []
    for key in ("messages", "generations", "output"):
        val = outputs.get(key)
        if not val:
            continue
        if isinstance(val, list):
            for v in val:
                if isinstance(v, list):
                    final_candidates.extend([x for x in v if isinstance(x, dict)])
                elif isinstance(v, dict):
                    final_candidates.append(v)
        elif isinstance(val, dict):
            final_candidates.append(val)

    for cand in final_candidates:
        if "message" in cand and isinstance(cand["message"], dict):
            cand = cand["message"]
        norm = _normalize_langchain_message(cand)
        if norm and norm.get("role") == "assistant":
            chain.append(norm)
            break

    return chain


def _build_chain_from_root(root_run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Walk root.outputs.messages (which LangChain populates with the final state)."""
    outputs = root_run.get("outputs", {}) or {}
    msgs = outputs.get("messages", []) or []
    return _extract_messages_from_langchain(msgs)


class LangSmithClient:
    # LangSmith /runs/query hard-caps per-request limit at 100; we paginate
    # using the response cursor to fetch larger sets.
    _PAGE_LIMIT = 100

    def __init__(self, api_key: str, base: str, project_id: str):
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.project_id = project_id
        self.headers = {"x-api-key": api_key, "Content-Type": "application/json"}

    def _post_with_retry(self, path: str, json_payload: Dict[str, Any], max_retries: int = 6) -> Dict[str, Any]:
        """POST with exponential backoff on 429 / 5xx."""
        backoff = 2.0
        for attempt in range(max_retries + 1):
            resp = requests.post(f"{self.base}{path}", headers=self.headers, json=json_payload)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < max_retries:
                print(f"[extract] LangSmith {resp.status_code}; backing off {backoff:.1f}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)
                continue
            raise RuntimeError(f"LangSmith query failed {resp.status_code}: {resp.text[:400]}")
        raise RuntimeError("LangSmith query retries exhausted")

    def query_runs(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Auto-paginate over /runs/query until caller-supplied limit is met.

        The caller may pass limit > 100; this method transparently breaks it
        into 100-sized pages, retries on 429/5xx, and follows next-cursor.
        """
        caller_limit = int(payload.get("limit") or 0)
        remaining = caller_limit if caller_limit > 0 else None

        collected: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        page_idx = 0
        while True:
            page_limit = self._PAGE_LIMIT
            if remaining is not None:
                page_limit = min(self._PAGE_LIMIT, remaining)
                if page_limit <= 0:
                    break
            page_payload = dict(payload)
            page_payload["limit"] = page_limit
            if cursor:
                page_payload["cursor"] = cursor

            body = self._post_with_retry("/api/v1/runs/query", page_payload)
            runs = body.get("runs", []) or []
            if not runs:
                break
            collected.extend(runs)
            page_idx += 1
            if remaining is not None:
                remaining -= len(runs)
                if remaining <= 0:
                    break
            cursor = body.get("cursors", {}).get("next") or body.get("next_cursor") or body.get("nextCursor")
            if not cursor:
                break
            # Be nice to LangSmith -- pause between pages to avoid 429s.
            time.sleep(0.3)

        if page_idx > 1:
            print(f"[extract] fetched {len(collected)} runs across {page_idx} pages")
        return collected

    def resolve_project_id(self, name: str) -> str:
        resp = requests.get(
            f"{self.base}/api/v1/sessions",
            headers=self.headers,
            params={"name": name, "limit": 1},
        )
        resp.raise_for_status()
        sessions = resp.json()
        if not sessions:
            raise RuntimeError(f"No LangSmith project named '{name}' found.")
        return sessions[0]["id"]


def _get_thread_id(run: Dict[str, Any]) -> str:
    extra = run.get("extra", {}) or {}
    metadata = extra.get("metadata", {}) or {}
    thread_id = metadata.get("thread_id", "")
    if not thread_id:
        config = metadata.get("configurable", {}) or {}
        thread_id = config.get("thread_id", "")
    return thread_id or ""


def _inject_system_prompt(chain: List[Dict[str, Any]], system_prompt: str) -> List[Dict[str, Any]]:
    """Ensure the chain starts with a consistent homebot system message."""
    if not chain:
        return chain
    if chain[0].get("role") == "system":
        chain[0]["content"] = system_prompt
        return chain
    return [{"role": "system", "content": system_prompt}] + chain


def _strip_chain_channel_prefix(chain: List[Dict[str, Any]]) -> None:
    """Strip [Telegram] framing from the FIRST user message; leave downstream turns."""
    for m in chain:
        if m.get("role") == "user":
            m["content"] = _strip_channel_prefix(m.get("content", ""))
            break


def extract_telegram_conversations(
    client: LangSmithClient,
    days: int,
    limit: int,
    thread_filter: Optional[str],
    system_prompt: str,
) -> Iterable[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    payload = {
        "session": [client.project_id],
        "is_root": True,
        # Pagination handles large limits; cap keeps accidental 100k pulls in check.
        "limit": max(int(limit), 1),
        "start_time": since.isoformat(),
        "order_by": ["-start_time"],
    }
    root_runs = client.query_runs(payload)
    print(f"[extract] pulled {len(root_runs)} root runs from last {days} days")

    kept = 0
    skipped_not_telegram = 0
    skipped_failed = 0
    skipped_invalid = 0
    skipped_dropped_entity = 0

    for run in root_runs:
        thread_id = _get_thread_id(run)
        if thread_filter:
            if thread_id != thread_filter:
                continue
        elif not thread_id.startswith("telegram-"):
            skipped_not_telegram += 1
            continue

        status = run.get("status", "")
        error = run.get("error")
        if status != "success" or error:
            skipped_failed += 1
            continue

        chain = _build_chain_from_root(run)
        if not _chain_is_valid(chain):
            trace_id = run.get("trace_id", run.get("id", ""))
            llm_payload = {
                "session": [client.project_id],
                "trace": trace_id,
                "run_type": "llm",
                "order_by": ["start_time"],
                "limit": 50,
            }
            try:
                llm_children = client.query_runs(llm_payload)
            except Exception as exc:
                print(f"[extract] child-run query failed for {trace_id[:8]}: {exc}")
                llm_children = []
            canonical = _pick_canonical_llm_run(llm_children)
            if canonical:
                chain = _build_chain_from_llm_run(canonical)

        chain = _truncate_tool_content(chain)
        chain = _splice_repair_turns(chain)
        chain = _strip_reasoning_from_chain(chain)
        chain = _sanitize_chain(chain)
        if _chain_has_drop(chain):
            skipped_dropped_entity += 1
            continue
        chain = _inject_system_prompt(chain, system_prompt)
        _strip_chain_channel_prefix(chain)

        if not _chain_is_valid(chain):
            skipped_invalid += 1
            continue

        kept += 1
        yield {"messages": chain, "source": "telegram", "thread_id": thread_id, "trace_id": run.get("trace_id", run.get("id", ""))}

    print(
        f"[extract] kept={kept} skipped_not_telegram={skipped_not_telegram} "
        f"skipped_failed={skipped_failed} skipped_invalid={skipped_invalid} "
        f"skipped_dropped_entity={skipped_dropped_entity}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract Telegram conversations to ChatML JSONL")
    parser.add_argument("--days", type=int, default=60, help="Look back N days (default 60)")
    parser.add_argument("--limit", type=int, default=500, help="Max root runs to pull (default 500)")
    parser.add_argument("--thread", type=str, default=None, help="Optional single thread_id filter")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUTPUT), help="Output JSONL path")
    parser.add_argument("--env", type=str, default=str(DEEPAGENT_DOTENV), help=".env path")
    args = parser.parse_args()

    env = _load_env(Path(args.env))
    api_key = env.get("LANGSMITH_API_KEY") or os.environ.get("LANGSMITH_API_KEY", "")
    base = env.get("LANGSMITH_ENDPOINT") or os.environ.get("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    project = env.get("LANGSMITH_PROJECT") or os.environ.get("LANGSMITH_PROJECT", "homebot-deepagent")

    if not api_key:
        print(f"ERROR: LANGSMITH_API_KEY not found in {args.env}", file=sys.stderr)
        return 1

    if get_system_prompt is None:
        print("WARNING: could not import deepagent.agent.get_system_prompt; using fallback system prompt", file=sys.stderr)
        system_prompt = "You are HomeBotAI, a helpful home automation assistant."
    else:
        system_prompt = get_system_prompt(include_render_ui=False, include_telegram=True)

    client = LangSmithClient(api_key=api_key, base=base, project_id="")
    client.project_id = client.resolve_project_id(project)
    print(f"[extract] project='{project}' id={client.project_id[:8]}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with out_path.open("w") as fh:
        for row in extract_telegram_conversations(
            client,
            days=args.days,
            limit=args.limit,
            thread_filter=args.thread,
            system_prompt=system_prompt,
        ):
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1

    print(f"[extract] wrote {n} telegram conversations -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
