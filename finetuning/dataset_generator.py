"""Generate diverse synthetic user queries, clustered by skill family.

The teacher-student distillation pipeline needs broad, realistic training
queries across every skill the DeepAgent exposes. A single flat prompt asking
Gemini for 300 queries tends to collapse onto the easy skills (lights, media)
and under-represents niche ones (Obsidian, memory, link-processor). So we
iterate per SKILL.md cluster, asking for a quota of queries that trigger that
specific skill, then concatenate + shuffle.

Entry point: generate_clustered_queries(api_key, total=300) -> list[str].
"""

import glob
import json
import os
import random
import re
from typing import Dict, List

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

MODEL_ID = "gemini-2.5-pro"
DEFAULT_TOTAL = 300

SKILLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "deepagent", "skills"))

# Simulation-time self-destruct guard: any query that would cut power to the
# machine running the DeepAgent (or reboot the mesh node it's connected through)
# must never reach the live server. The regexes are deliberately broad --
# false positives just cost us a few queries; false negatives cost us an outage.
_BANNED_QUERY_RE = re.compile(
    r"(?i)("
    r"(turn[\s_-]*off|shut[\s_-]*down|shutdown|power[\s_-]*off|cut[\s_-]*power|"
    r"kill|disable|toggle|restart|reboot)"
    r"[^.\n]{0,60}?"
    r"(workstation|\bpc\b|pc[\s_-]*plug|\bdesk\b|desk[\s_-]*plug|"
    r"monitor[\s_-]*plug|\bmonitor\b|switch\.workstation|switch\.monitor|"
    r"gaming[\s_-]*pc|deco[\s_-]*(master|main|root))"
    r"|"
    r"reboot[^.\n]{0,60}?(mesh|all[\s_-]*nodes|everything)"
    r")",
)


def _is_dangerous_query(q: str) -> bool:
    return bool(_BANNED_QUERY_RE.search(q or ""))


def _read_skill(skill_dir: str) -> str:
    path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(path):
        return ""
    with open(path, "r") as f:
        return f.read()


def _discover_skill_clusters() -> Dict[str, str]:
    """Return {skill_name: skill_md_content} for every skill folder."""
    clusters: Dict[str, str] = {}
    for skill_path in sorted(glob.glob(os.path.join(SKILLS_DIR, "*"))):
        if not os.path.isdir(skill_path):
            continue
        name = os.path.basename(skill_path)
        content = _read_skill(skill_path)
        if content.strip():
            clusters[name] = content
    return clusters


def _read_global_skill_blob() -> str:
    """Concatenated SKILL.md content used as shared context across all clusters."""
    skill_files = glob.glob(os.path.join(SKILLS_DIR, "*", "SKILL.md"))
    contents = []
    for sf in sorted(skill_files):
        with open(sf, "r") as f:
            contents.append(f.read())
    return "\n\n---\n\n".join(contents)


def get_skill_contexts() -> str:
    """Backwards-compatible accessor used by older callers."""
    return _read_global_skill_blob()


def _parse_json_array(raw_text: str) -> List[str]:
    text = raw_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
    except Exception:
        pass

    salvaged = re.findall(r'"([^"]{5,})"', text)
    return [s.strip() for s in salvaged if len(s) > 5 and not s.startswith("http")]


def _build_cluster_prompt(skill_name: str, skill_md: str, other_skills_blob: str, quota: int) -> str:
    """Per-skill prompt that forces queries to exercise THIS skill's tools."""
    return f"""
You are simulating a human who lives in a smart home and texts a personal
Telegram assistant. Below is the FOCUS skill you should target. Other skills
are listed for disambiguation (do NOT produce queries that primarily trigger
those other skills).

<FOCUS_SKILL name="{skill_name}">
{skill_md}
</FOCUS_SKILL>

<OTHER_SKILLS_FOR_DISAMBIGUATION>
{other_skills_blob}
</OTHER_SKILLS_FOR_DISAMBIGUATION>

Generate EXACTLY {quota} diverse, realistic, conversational user queries that
should primarily trigger the FOCUS skill's tools.

Rules:
1. Reference real entity/device/tool names from the FOCUS skill where possible.
2. Mix short/terse messages ("lights off"), natural sentences ("turn off the
   living room lights please"), and complex multi-step asks ("turn on kitchen
   lights and start the purifier on silent").
3. Include casual texting variations: lowercase, occasional typos, slang,
   missing punctuation.
4. Spread across all sub-capabilities of this skill (read/query, write/mutate,
   search, diagnostics). Do NOT repeat the same entity 3+ times.
5. Return ONLY a valid JSON array of strings. No markdown fences, no prose.

SAFETY (HARD CONSTRAINT -- do not violate):
- NEVER generate a query that would cut power to the workstation or desk plug
  (the fine-tuned agent itself runs on that machine). Banned subjects:
  workstation, PC, gaming PC, desk plug, monitor plug, `switch.workstation`,
  `switch.monitor_plug`, and any colloquial variant ("the desk", "my PC").
- NEVER generate a query that would reboot the master/main Deco mesh node,
  "all nodes", or the whole mesh -- that kills network for everything
  including the bot. Targeted reboots of a satellite by nickname are fine.
- You MAY generate "turn ON" or status queries for those devices. Only the
  off / shutdown / toggle / reboot verbs are banned.

Example shape (pretend {skill_name}):
["turn off the living room lights", "living room lamp 40%", "dim bedside to 10"]
""".strip()


def _generate_cluster(
    llm: ChatGoogleGenerativeAI,
    skill_name: str,
    skill_md: str,
    other_skills_blob: str,
    quota: int,
) -> List[str]:
    prompt = _build_cluster_prompt(skill_name, skill_md, other_skills_blob, quota)
    response = llm.invoke([HumanMessage(content=prompt)])
    queries = _parse_json_array(response.content or "")
    if len(queries) > quota:
        queries = queries[:quota]
    return queries


def _quota_allocation(clusters: List[str], total: int) -> Dict[str, int]:
    """Split `total` evenly across clusters, absorbing the remainder in the first few."""
    if not clusters:
        return {}
    base = total // len(clusters)
    remainder = total - base * len(clusters)
    allocation = {name: base for name in clusters}
    for name in clusters[:remainder]:
        allocation[name] += 1
    return allocation


def generate_clustered_queries(api_key: str, total: int = DEFAULT_TOTAL) -> List[str]:
    clusters = _discover_skill_clusters()
    if not clusters:
        print("ERROR: no SKILL.md files discovered under", SKILLS_DIR)
        return []

    llm = ChatGoogleGenerativeAI(
        model=MODEL_ID,
        google_api_key=api_key,
        temperature=1.0,
    )

    names = list(clusters.keys())
    allocation = _quota_allocation(names, total)
    all_queries: List[str] = []

    print(f"Generating {total} queries across {len(names)} skill families: {allocation}")

    for name in names:
        quota = allocation.get(name, 0)
        if quota <= 0:
            continue
        skill_md = clusters[name]
        other_blob = "\n\n---\n\n".join(md for k, md in clusters.items() if k != name)
        print(f"  [{name}] requesting {quota} queries...")
        try:
            cluster_queries = _generate_cluster(llm, name, skill_md, other_blob, quota)
        except Exception as e:
            print(f"  [{name}] generation failed: {e}")
            cluster_queries = []
        print(f"  [{name}] received {len(cluster_queries)}")
        all_queries.extend(cluster_queries)

    seen = set()
    deduped: List[str] = []
    banned = 0
    for q in all_queries:
        key = q.lower().strip()
        if not key or key in seen:
            continue
        if _is_dangerous_query(q):
            banned += 1
            continue
        seen.add(key)
        deduped.append(q)

    if banned:
        print(f"  [safety] dropped {banned} dangerous query(ies) that target the workstation/mesh")

    random.shuffle(deduped)
    return deduped


def generate_queries(api_key: str, num_queries: int = DEFAULT_TOTAL):
    """Backwards-compatible entry point used by older scripts."""
    return generate_clustered_queries(api_key, total=num_queries)


if __name__ == "__main__":
    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not gemini_key:
        print("Error: GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set in .env")
        exit(1)

    queries = generate_clustered_queries(gemini_key, total=DEFAULT_TOTAL)

    if queries:
        out_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(out_dir, exist_ok=True)
        out_file = os.path.join(out_dir, "synthetic_queries.json")
        with open(out_file, "w") as f:
            json.dump(queries, f, indent=2)
        print(f"Successfully generated {len(queries)} queries and saved to {out_file}")
