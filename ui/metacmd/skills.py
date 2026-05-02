"""Skill management meta commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.table import Table

from loop import NeoLoop
from loop.skills import SkillError
from ui.console import console
from ui.metacmd.registry import SubCommand, meta_command

if TYPE_CHECKING:
    from ui.repl import ShellREPL


@meta_command(
    loop_only=True,
    subcommands=[
        SubCommand(name="list", aliases=["ls"], description="List installed skills"),
        SubCommand(name="enable", aliases=[], description="Enable a skill"),
        SubCommand(name="disable", aliases=[], description="Disable a skill"),
        SubCommand(name="install", aliases=[], description="Install a skill from a local path"),
        SubCommand(name="uninstall", aliases=["remove", "rm"], description="Uninstall a skill"),
    ],
)
def skills(app: ShellREPL, args: list[str]) -> None:
    """Manage skills. Usage: /skills [list|enable|disable|install|uninstall]"""
    assert isinstance(app.loop, NeoLoop)

    if not args:
        _skills_list(app, [])
        return

    subcommand = args[0].lower()
    subargs = args[1:]

    match subcommand:
        case "list" | "ls":
            _skills_list(app, subargs)
        case "enable":
            _skills_enable(app, subargs)
        case "disable":
            _skills_disable(app, subargs)
        case "install":
            _skills_install(app, subargs)
        case "uninstall" | "remove" | "rm":
            _skills_uninstall(app, subargs)
        case _:
            console.print(f"[red]Unknown command: {subcommand}[/red]")
            console.print("[dim]Usage: /skills [list|enable|disable|install|uninstall][/dim]")


def _skills_list(app: ShellREPL, args: list[str]) -> None:
    """List installed skills."""
    skill_manager = app.loop.runtime.skill_manager
    if skill_manager is None:
        console.print("[yellow]Skills are not available.[/yellow]")
        return

    installed_skills = skill_manager.all_skills()
    if not installed_skills:
        console.print("[yellow]No skills installed.[/yellow]")
        return

    table = Table(show_header=True, header_style="bold", expand=False)
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Version", style="dim")
    table.add_column("Enabled", justify="center")

    for skill in installed_skills:
        enabled = "[green]✓[/green]" if skill.enabled else "[dim]○[/dim]"
        table.add_row(f"[cyan]{skill.name}[/cyan]", skill.description, skill.version, enabled)

    console.print(table)


def _skills_enable(app: ShellREPL, args: list[str]) -> None:
    """Enable a skill."""
    if not args:
        console.print("[red]Usage: /skills enable <name>[/red]")
        return
    skill_manager = app.loop.runtime.skill_manager
    if skill_manager is None:
        console.print("[yellow]Skills are not available.[/yellow]")
        return
    if skill_manager.enable_skill(args[0]):
        console.print(f"[green]✓[/green] Enabled skill: [cyan]{args[0]}[/cyan]")
    else:
        console.print(f"[red]Skill '{args[0]}' not found.[/red]")


def _skills_disable(app: ShellREPL, args: list[str]) -> None:
    """Disable a skill."""
    if not args:
        console.print("[red]Usage: /skills disable <name>[/red]")
        return
    skill_manager = app.loop.runtime.skill_manager
    if skill_manager is None:
        console.print("[yellow]Skills are not available.[/yellow]")
        return
    if skill_manager.disable_skill(args[0]):
        console.print(f"[green]✓[/green] Disabled skill: [cyan]{args[0]}[/cyan]")
    else:
        console.print(f"[red]Skill '{args[0]}' not found.[/red]")


def _skills_install(app: ShellREPL, args: list[str]) -> None:
    """Install a skill from a local path."""
    if not args:
        console.print("[red]Usage: /skills install <source>[/red]")
        return
    skill_manager = app.loop.runtime.skill_manager
    if skill_manager is None:
        console.print("[yellow]Skills are not available.[/yellow]")
        return
    try:
        skill = skill_manager.install_skill(args[0])
    except SkillError as e:
        console.print(f"[red]Failed to install skill: {e}[/red]")
        return
    console.print(f"[green]✓[/green] Installed skill: [cyan]{skill.name}[/cyan]")


def _skills_uninstall(app: ShellREPL, args: list[str]) -> None:
    """Uninstall a skill."""
    if not args:
        console.print("[red]Usage: /skills uninstall <name>[/red]")
        return
    skill_manager = app.loop.runtime.skill_manager
    if skill_manager is None:
        console.print("[yellow]Skills are not available.[/yellow]")
        return
    if skill_manager.uninstall_skill(args[0]):
        console.print(f"[green]✓[/green] Uninstalled skill: [cyan]{args[0]}[/cyan]")
    else:
        console.print(f"[red]Skill '{args[0]}' not found.[/red]")
