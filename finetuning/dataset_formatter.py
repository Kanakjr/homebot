"""Convert distillation-simulation LangSmith traces into multi-turn ChatML JSONL.

Historical behavior: the old formatter only captured the FIRST AI tool_call per
trace. That trained the model to emit a tool call but not how to interpret the
tool result or produce the final natural-language response -- which is half of
the agent loop.

New behavior: for every unique user query we pick the canonical LLM run
(the one whose `inputs.messages` has the longest history) and emit a single
multi-turn example covering the full loop:

    system -> user -> assistant+tool_calls -> tool -> ... -> assistant (final text)

If the canonical run's input history already contains the final AI text as the
last message, we use it as-is. Otherwise we attempt to append the final
assistant response from `outputs.output[*].update.messages`.

Entry point: `process_langsmith_traces(input_file, output_file)`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_telegram_dataset import (  # noqa: E402
    _chain_has_drop,
    _chain_is_valid,
    _extract_messages_from_langchain,
    _extract_text,
    _normalize_langchain_message,
    _sanitize_chain,
    _splice_repair_turns,
    _strip_reasoning_from_chain,
    _truncate_tool_content,
)


def build_system_prompt(files: Optional[Dict[str, Any]]) -> str:
    """Construct the DeepAgent system prompt dynamically from captured SKILL.md files.

    Falls back to importing the live system prompt from deepagent.agent if the
    trace did not capture the skill files. That guarantees training always has
    a real system prompt rather than a placeholder sentence.
    """
    base_prompt = (
        "You are HomeBotAI, a helpful home automation assistant communicating "
        "with the user via Telegram. You have access to various tools and "
        "integrations built into the HomeBot ecosystem.\n\n"
    )

    contexts: List[str] = []
    if files:
        for _, filedata in files.items():
            if not isinstance(filedata, dict):
                continue
            content = filedata.get("content")
            if not content:
                continue
            text = "\n".join(content) if isinstance(content, list) else str(content)
            contexts.append(text)

    if contexts:
        return base_prompt + "<SKILL_CONTEXT>\n" + "\n\n---\n\n".join(contexts) + "\n</SKILL_CONTEXT>\n"

    try:
        app_dir = Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(app_dir))
        from deepagent.agent import get_system_prompt  # type: ignore

        return get_system_prompt(include_render_ui=False, include_telegram=True)
    except Exception:
        return base_prompt


def _extract_messages_field(messages_field: Any) -> List[Dict[str, Any]]:
    """Normalize the shape of inputs.messages (may be flat list or [[...]])."""
    if not messages_field:
        return []
    if isinstance(messages_field, list) and messages_field and isinstance(messages_field[0], list):
        return messages_field[0]
    return messages_field


def _append_final_ai_from_outputs(chain: List[Dict[str, Any]], outputs: Any) -> List[Dict[str, Any]]:
    """Walk LangGraph-style outputs and append any final assistant text message.

    Expected shapes:
        outputs.output: None
        outputs.output: [{update: {messages: [{...ai}]}}, ...]
        outputs.messages: [...]  # flat LC list
        outputs.generations: [[{message: {...}}]]  # LLM-run style
    """
    if isinstance(outputs, dict):
        msgs = outputs.get("messages")
        if msgs:
            for m in _extract_messages_from_langchain(msgs):
                if m.get("role") == "assistant":
                    chain.append(m)
                    return chain

        out_list = outputs.get("output")
        if isinstance(out_list, list):
            for entry in out_list:
                if not isinstance(entry, dict):
                    continue
                update = entry.get("update") or {}
                sub_msgs = update.get("messages") if isinstance(update, dict) else None
                if sub_msgs:
                    for m in _extract_messages_from_langchain(sub_msgs):
                        if m.get("role") == "assistant":
                            chain.append(m)
                            return chain

        generations = outputs.get("generations")
        if isinstance(generations, list):
            flat: List[Dict[str, Any]] = []
            for g in generations:
                if isinstance(g, list):
                    flat.extend([x for x in g if isinstance(x, dict)])
                elif isinstance(g, dict):
                    flat.append(g)
            for cand in flat:
                if isinstance(cand.get("message"), dict):
                    cand = cand["message"]
                norm = _normalize_langchain_message(cand)
                if norm and norm.get("role") == "assistant":
                    chain.append(norm)
                    return chain

    return chain


def _find_first_user_text(messages: List[Dict[str, Any]]) -> Optional[str]:
    for m in messages:
        if not isinstance(m, dict):
            continue
        if m.get("type") in ("human", "user") or m.get("role") in ("user", "human"):
            return _extract_text(m.get("content", ""))
        if m.get("type") == "constructor":
            hint = (m.get("id") or [""])[-1]
            if "HumanMessage" in hint:
                return _extract_text((m.get("kwargs") or {}).get("content", ""))
    return None


def _chain_hash(messages: List[Dict[str, Any]]) -> str:
    """Stable hash of a conversation to dedup across near-identical traces."""
    payload = []
    for m in messages:
        role = m.get("role", "")
        if role == "system":
            continue
        content = m.get("content", "")
        tool_calls = m.get("tool_calls", [])
        tc_sig = [
            {"name": tc.get("function", {}).get("name"), "args": tc.get("function", {}).get("arguments")}
            for tc in tool_calls
        ]
        payload.append({"role": role, "content": content, "tool_calls": tc_sig, "name": m.get("name")})
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _pick_canonical_trace(traces: List[Dict[str, Any]]) -> Dict[str, Any]:
    """From all LangSmith traces sharing the same user query, pick the most complete."""
    def score(t: Dict[str, Any]) -> tuple:
        msgs = _extract_messages_field(t.get("inputs", {}).get("messages", []))
        hist_len = len(msgs)
        has_final_text = 0
        if msgs:
            last = msgs[-1]
            if isinstance(last, dict):
                if last.get("type") == "ai" and not (last.get("tool_calls") or last.get("additional_kwargs", {}).get("tool_calls")):
                    txt = _extract_text(last.get("content", ""))
                    if txt.strip():
                        has_final_text = 1
        return (has_final_text, hist_len)
    return max(traces, key=score)


def process_langsmith_traces(input_file: str, output_file: str) -> None:
    if not os.path.exists(input_file):
        print(f"File {input_file} not found. Run LangSmith extractor first.")
        return

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    with open(input_file, "r") as f:
        for line_index, line in enumerate(f):
            if not line.strip():
                continue
            try:
                trace = json.loads(line)
            except json.JSONDecodeError:
                print(f"Failed to parse JSON on line {line_index}.")
                continue
            inputs = trace.get("inputs", {}) or {}
            msgs = _extract_messages_field(inputs.get("messages", []))
            if not msgs:
                continue
            user_text = _find_first_user_text(msgs)
            if not user_text or not user_text.strip():
                continue
            key = user_text.strip()
            grouped.setdefault(key, []).append(trace)

    print(f"[format] {len(grouped)} distinct user queries across {sum(len(v) for v in grouped.values())} traces")

    formatted: List[Dict[str, Any]] = []
    seen_hashes: set = set()
    skipped_invalid = 0
    skipped_dup = 0
    skipped_dropped_entity = 0

    for user_query, traces in grouped.items():
        canonical = _pick_canonical_trace(traces)
        inputs = canonical.get("inputs", {}) or {}
        msgs = _extract_messages_field(inputs.get("messages", []))
        files = inputs.get("files", {}) or canonical.get("files", {})

        chain = _extract_messages_from_langchain(msgs)

        if not chain or chain[-1].get("role") != "assistant" or chain[-1].get("tool_calls") or not (chain[-1].get("content") or "").strip():
            chain = _append_final_ai_from_outputs(chain, canonical.get("outputs", {}) or {})

        chain = _truncate_tool_content(chain)
        chain = _splice_repair_turns(chain)
        chain = _strip_reasoning_from_chain(chain)
        chain = _sanitize_chain(chain)
        if _chain_has_drop(chain):
            skipped_dropped_entity += 1
            continue

        system_prompt = build_system_prompt(files)
        if chain and chain[0].get("role") == "system":
            chain[0]["content"] = system_prompt
        else:
            chain = [{"role": "system", "content": system_prompt}] + chain

        if not _chain_is_valid(chain):
            skipped_invalid += 1
            continue

        h = _chain_hash(chain)
        if h in seen_hashes:
            skipped_dup += 1
            continue
        seen_hashes.add(h)

        formatted.append({"messages": chain, "source": "synthetic", "trace_id": canonical.get("id", "")})

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w") as fh:
        for row in formatted:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        f"[format] wrote {len(formatted)} multi-turn records "
        f"(skipped_invalid={skipped_invalid} skipped_dup={skipped_dup} "
        f"skipped_dropped_entity={skipped_dropped_entity}) "
        f"-> {output_file}"
    )


if __name__ == "__main__":
    input_path = os.path.join(os.path.dirname(__file__), "data", "langsmith_export.jsonl")
    output_path = os.path.join(os.path.dirname(__file__), "data", "qwen_training_dataset.jsonl")
    process_langsmith_traces(input_path, output_path)
