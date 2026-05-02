"""Persistent memory meta command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from prompt_toolkit.shortcuts.choice_input import ChoiceInput
from rich.table import Table

from loop import NeoLoop
from memory import MemoryManager
from ui.console import console
from ui.metacmd.registry import SubCommand, meta_command

if TYPE_CHECKING:
    from ui.repl import ShellREPL


def _memory_subcommand_completer(args: list[str]) -> list[str]:
    """Provide completions for /memory subcommands."""
    if len(args) == 0:
        return ["status", "search", "clear", "export"]
    if len(args) == 1 and args[0] == "clear":
        return ["history"]
    return []


@meta_command(
    subcommands=[
        SubCommand(name="status", aliases=[], description="Show persistent memory status"),
        SubCommand(name="search", aliases=[], description="Search SQL and conversation memory"),
        SubCommand(name="clear", aliases=[], description="Clear persistent memory", arg_completer=_memory_subcommand_completer),
        SubCommand(name="export", aliases=[], description="Export persistent memory as JSON"),
    ],
)
async def memory(app: ShellREPL, args: list[str]) -> None:
    """Manage persistent memory"""
    manager = _get_memory_manager(app)

    if not args or args[0] == "status":
        _show_status(manager)
        return

    subcommand = args[0].lower()
    subargs = args[1:]

    match subcommand:
        case "search":
            _search_memory(manager, subargs)
        case "clear":
            await _clear_memory(app, manager, subargs)
        case "export":
            _export_memory(manager)
        case _:
            console.print(f"[red]Unknown memory subcommand: {subcommand}[/red]")
            console.print("[dim]Usage: /memory [status|search <keyword>|clear [history]|export][/dim]")


def _get_memory_manager(app: ShellREPL) -> MemoryManager:
    """Return the active memory manager or create a command-scoped one."""
    if isinstance(app.loop, NeoLoop):
        return app.loop.memory_manager
    return MemoryManager(session_id="standalone")


def _show_status(manager: MemoryManager) -> None:
    """Display persistent memory status."""
    status = manager.status()

    table = Table(title="Persistent Memory", show_header=False, expand=False)
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Value")
    table.add_row("Storage", status.database_path)
    table.add_row("Mode", "SQLite" if status.available else "in-memory fallback")
    table.add_row("Query history", str(status.query_count))
    table.add_row("Checkpoints", str(status.checkpoint_count))
    table.add_row("Conversation memory", str(status.conversation_count))
    table.add_row("Latest session", status.latest_session_id or "-")
    table.add_row("Latest checkpoint", status.latest_session_timestamp or "-")
    if status.error:
        table.add_row("Warning", f"[yellow]{status.error}[/yellow]")

    console.print(table)


def _search_memory(manager: MemoryManager, args: list[str]) -> None:
    """Search persistent memory and display matches."""
    if not args:
        console.print("[red]Usage: /memory search <keyword>[/red]")
        return

    pattern = " ".join(args)
    results = manager.search(pattern, limit=20)
    query_results = results["query_history"]
    conversation_results = results["conversation_memory"]

    if not query_results and not conversation_results:
        console.print(f"[yellow]No memory found for: {pattern}[/yellow]")
        return

    if query_results:
        query_table = Table(title="SQL Memory", expand=False)
        query_table.add_column("Time", style="dim", no_wrap=True)
        query_table.add_column("Status", no_wrap=True)
        query_table.add_column("Database", no_wrap=True)
        query_table.add_column("SQL")
        for record in query_results:
            query_table.add_row(
                str(record.get("timestamp", "")),
                str(record.get("status", "")),
                str(record.get("database_name") or "-"),
                _shorten(str(record.get("sql", ""))),
            )
        console.print(query_table)

    if conversation_results:
        memory_table = Table(title="Conversation Memory", expand=False)
        memory_table.add_column("Time", style="dim", no_wrap=True)
        memory_table.add_column("Type", no_wrap=True)
        memory_table.add_column("Key", no_wrap=True)
        memory_table.add_column("Value")
        for record in conversation_results:
            memory_table.add_row(
                str(record.get("timestamp", "")),
                str(record.get("type", "")),
                str(record.get("key", "")),
                _shorten(str(record.get("value", ""))),
            )
        console.print(memory_table)


async def _clear_memory(app: ShellREPL, manager: MemoryManager, args: list[str]) -> None:
    """Clear persistent memory after confirmation."""
    history_only = bool(args and args[0].lower() == "history")
    target = "query history" if history_only else "all memory"

    try:
        confirm = await ChoiceInput(
            message=f"Clear {target}?",
            options=[
                ("no", "No, cancel"),
                ("yes", f"Yes, clear {target}"),
            ],
            default="no",
        ).prompt_async()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Memory clear cancelled.[/yellow]")
        return

    if confirm != "yes":
        console.print("[yellow]Memory clear cancelled.[/yellow]")
        return

    if history_only:
        manager.clear_history()
        if app.query_history:
            app.query_history.clear_history()
        console.print("[green]Query history memory cleared.[/green]")
        return

    manager.clear_all()
    if app.query_history:
        app.query_history.clear_history()
    console.print("[green]Persistent memory cleared.[/green]")


def _export_memory(manager: MemoryManager) -> None:
    """Print persistent memory as formatted JSON."""
    console.print_json(json.dumps(manager.export(), ensure_ascii=False, indent=2))


def _shorten(value: str, max_length: int = 120) -> str:
    """Shorten a value for table display."""
    normalized = " ".join(value.split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."
