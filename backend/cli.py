#!/usr/bin/env python3
"""
HomeBotAI Interactive CLI -- a developer-friendly chat interface
that streams tool calls and responses in real time, styled with Rich.

Usage:
    python cli.py                  # default: connect to HA, chat_id=0
    python cli.py --no-ha          # skip HA WebSocket (faster startup)
    python cli.py --chat-id 42     # use a specific conversation thread
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import termios
import time

from rich.console import Console
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

import config

THEME = Theme({
    "user": "bold green",
    "bot": "bold cyan",
    "tool.name": "bold yellow",
    "tool.result": "green",
    "tool.error": "bold red",
    "dim": "dim",
    "info": "bold bright_white",
    "status": "italic bright_black",
})

console = Console(theme=THEME)
log_console = Console(stderr=True, theme=THEME)

COMMANDS = {
    "/help":     "Show this help message",
    "/quit":     "Exit the CLI  (also Ctrl+C or /q)",
    "/clear":    "Clear conversation history for this chat_id",
    "/tools":    "List all registered tools",
    "/skills":   "List learned skills",
    "/entities": "List HA entity domains and counts",
    "/state":    "Get state of an entity:  /state light.bedroom",
    "/system":   "Show the current system prompt",
}

BANNER = r"""
  _   _                      ____        _     _    ___
 | | | | ___  _ __ ___   ___| __ )  ___ | |_  / \  |_ _|
 | |_| |/ _ \| '_ ` _ \ / _ \  _ \ / _ \| __|/ _ \  | |
 |  _  | (_) | | | | | |  __/ |_) | (_) | |_/ ___ \ | |
 |_| |_|\___/|_| |_| |_|\___|____/ \___/ \__/_/   \_\___|
"""


def print_banner():
    console.print(Panel(
        Text(BANNER, style="bold cyan", justify="center"),
        subtitle="[dim]Type /help for commands, Ctrl+C to quit[/dim]",
        border_style="bright_blue",
    ))


def render_tool_call(name: str, args: dict):
    """Print a tool invocation block inline."""
    console.print(f"\n  [tool.name]>>> {name}[/tool.name]")
    if args:
        for k, v in args.items():
            val_str = v if isinstance(v, str) else json.dumps(v, default=str)
            if len(val_str) > 120:
                val_str = val_str[:117] + "..."
            console.print(f"      [dim]{k}:[/dim] {val_str}")


def render_tool_result(name: str, content: str, duration_ms: int):
    """Print a tool result block inline."""
    style = "tool.result"
    prefix = "OK"
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict) and "error" in parsed:
            style = "tool.error"
            prefix = "ERR"
    except (json.JSONDecodeError, TypeError):
        pass

    short = content if len(content) <= 200 else content[:197] + "..."
    dur = f"  [dim]({duration_ms}ms)[/dim]" if duration_ms else ""
    console.print(f"      [{style}]{prefix}: {short}[/{style}]{dur}")


def render_response(text: str):
    """Render the final bot response in a panel."""
    console.print()
    try:
        md = Markdown(text)
        console.print(Panel(md, title="[bot]HomeBotAI[/bot]", border_style="cyan", padding=(0, 1)))
    except Exception:
        console.print(Panel(text, title="[bot]HomeBotAI[/bot]", border_style="cyan", padding=(0, 1)))


async def handle_command(cmd: str, app, chat_id: int) -> bool:
    """Handle slash commands. Returns False to quit, True to continue."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q"):
        return False

    if command == "/help":
        tbl = Table(show_header=False, box=None, padding=(0, 2))
        tbl.add_column(style="bold yellow")
        tbl.add_column(style="dim")
        for c, desc in COMMANDS.items():
            tbl.add_row(c, desc)
        console.print(Panel(tbl, title="[info]Commands[/info]", border_style="bright_blue"))
        return True

    if command == "/clear":
        await app.episodic.clear(chat_id)
        console.print("[info]Conversation history cleared.[/info]")
        return True

    if command == "/tools":
        tools = app.tool_map.get_tools()
        tbl = Table(title="Registered Tools", show_lines=False, border_style="bright_blue")
        tbl.add_column("#", style="dim", width=3)
        tbl.add_column("Name", style="bold yellow")
        tbl.add_column("Description", style="dim", max_width=70)
        for i, t in enumerate(tools, 1):
            desc = (t.description or "").split("\n")[0][:70]
            tbl.add_row(str(i), t.name, desc)
        console.print(tbl)
        return True

    if command == "/skills":
        skills = await app.procedural.list_skills()
        if not skills:
            console.print("[dim]No skills learned yet.[/dim]")
        else:
            tbl = Table(title="Learned Skills", border_style="bright_blue")
            tbl.add_column("Name", style="bold yellow")
            tbl.add_column("Trigger", style="dim")
            tbl.add_column("Description")
            for s in skills:
                trigger_label = s.get("trigger", {}).get("type", "manual")
                tbl.add_row(s["name"], trigger_label, s["description"])
            console.print(tbl)
        return True

    if command == "/entities":
        domains: dict[str, int] = {}
        for eid in app.state_cache.all_entity_ids():
            d = eid.split(".")[0]
            domains[d] = domains.get(d, 0) + 1
        if not domains:
            console.print("[dim]No HA entities loaded (HA not connected?).[/dim]")
        else:
            tbl = Table(title="HA Entity Domains", border_style="bright_blue")
            tbl.add_column("Domain", style="bold yellow")
            tbl.add_column("Count", style="cyan", justify="right")
            for d, count in sorted(domains.items()):
                tbl.add_row(d, str(count))
            tbl.add_row("[bold]Total[/bold]", f"[bold]{sum(domains.values())}[/bold]")
            console.print(tbl)
        return True

    if command == "/state":
        if not arg:
            console.print("[tool.error]Usage: /state <entity_id>[/tool.error]")
            return True
        entity = app.state_cache.get(arg)
        if not entity:
            console.print(f"[tool.error]Entity '{arg}' not found.[/tool.error]")
        else:
            console.print_json(json.dumps(entity, indent=2, default=str))
        return True

    if command == "/system":
        prompt = await app.agent._build_system_prompt()
        console.print(Panel(prompt, title="[info]System Prompt[/info]", border_style="bright_blue"))
        return True

    console.print(f"[tool.error]Unknown command: {command}[/tool.error]  (try /help)")
    return True


async def chat_turn(app, chat_id: int, user_input: str):
    """Run one conversation turn, streaming events to the console in real time."""
    t0 = time.monotonic()
    tool_count = 0
    got_response = False
    thinking_shown = False

    async for event in app.agent.run_stream(chat_id=chat_id, user_message=user_input):
        etype = event["type"]

        if etype == "thinking":
            console.print("  [status]Thinking...[/status]")
            thinking_shown = True
            continue

        if etype == "tool_call":
            tool_count += 1
            render_tool_call(event["name"], event["args"])

        elif etype == "tool_result":
            render_tool_result(event["name"], event["content"], event.get("duration_ms", 0))

        elif etype == "response":
            render_response(event["content"])
            got_response = True

        elif etype == "error":
            console.print(f"\n  [tool.error]{event['content']}[/tool.error]")
            got_response = True

    if not got_response and not thinking_shown:
        console.print()

    elapsed = int((time.monotonic() - t0) * 1000)
    meta = [f"{elapsed}ms"]
    if tool_count:
        meta.append(f"{tool_count} tool call{'s' if tool_count != 1 else ''}")
    console.print(f"  [dim]{' | '.join(meta)}[/dim]")


def _flush_stdin():
    """Discard any buffered keystrokes accumulated during slow initialization."""
    try:
        fd = sys.stdin.fileno()
        termios.tcflush(fd, termios.TCIFLUSH)
    except (termios.error, ValueError, OSError):
        pass


async def main_loop(app, chat_id: int):
    """Main interactive REPL."""
    console.print(Rule(style="bright_blue"))
    entity_count = len(app.state_cache.all_entity_ids())
    tool_count = len(app.tool_map)
    console.print(
        f"  [info]Ready:[/info] {tool_count} tools | "
        f"{entity_count} HA entities | chat_id={chat_id}"
    )
    console.print(Rule(style="bright_blue"))
    console.print()

    _flush_stdin()

    while True:
        try:
            user_input = console.input("[user] You > [/user]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        if user_input.startswith("/"):
            should_continue = await handle_command(user_input, app, chat_id)
            if not should_continue:
                console.print("[dim]Goodbye![/dim]")
                break
            console.print()
            continue

        await chat_turn(app, chat_id, user_input)
        console.print()


async def run(args):
    stderr_handler = RichHandler(
        console=log_console,
        show_path=False,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
    )
    logging.basicConfig(
        level=logging.CRITICAL,
        handlers=[stderr_handler],
    )
    if args.verbose:
        logging.getLogger("homebot").setLevel(logging.INFO)

    print_banner()
    console.print("[dim]Initializing (this takes ~40s on first import)...[/dim]")

    from bootstrap import create_app, shutdown_app
    app = await create_app(connect_ha=not args.no_ha)

    try:
        await main_loop(app, args.chat_id)
    finally:
        await shutdown_app(app)


def main():
    parser = argparse.ArgumentParser(description="HomeBotAI Interactive CLI")
    parser.add_argument(
        "--chat-id", type=int, default=0,
        help="Conversation thread ID (default: 0)",
    )
    parser.add_argument(
        "--no-ha", action="store_true",
        help="Skip HA WebSocket connection for faster startup",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Show INFO-level logs",
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
