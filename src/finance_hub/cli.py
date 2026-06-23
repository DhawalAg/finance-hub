"""CLI surface over the tool registry.

    finance tools                       list every registered tool
    finance run <name> --args '<json>'  invoke a tool with JSON kwargs
    finance check [--live]              read-only setup diagnostic
"""
from __future__ import annotations

import json
import os

import typer

from finance_hub import bootstrap as _bootstrap
from finance_hub.runtime import registry

_bootstrap.load_dotenv()
_bootstrap.bootstrap()

app = typer.Typer(help="finance-hub: run finance capabilities from the shell.")
registry.load_all()

_SEVERITY_ICONS = {"green": "✓", "yellow": "!", "red": "✗"}
_SEVERITY_COLORS = {
    "green": typer.colors.GREEN,
    "yellow": typer.colors.YELLOW,
    "red": typer.colors.RED,
}


@app.command("check")
def check(
    live: bool = typer.Option(False, "--live", help="Add a real price fetch to the check."),
) -> None:
    """Report setup status as green / yellow / red with a fix hint for each problem."""
    from finance_hub.checks import run_checks

    results = run_checks(dict(os.environ), live=live)
    any_red = False
    for r in results:
        icon = _SEVERITY_ICONS.get(r.severity, "?")
        color = _SEVERITY_COLORS.get(r.severity)
        prefix = typer.style(f"[{icon}]", fg=color, bold=True)
        typer.echo(f"{prefix} {r.name}: {r.message}")
        if r.fix:
            typer.echo(f"    fix: {r.fix}")
        if r.severity == "red":
            any_red = True
    raise typer.Exit(code=1 if any_red else 0)


@app.command("tools")
def list_tools() -> None:
    """List every registered tool."""
    for t in sorted(registry.all_tools().values(), key=lambda x: x.name):
        typer.echo(f"{t.name:28}  {t.description}")


@app.command("run")
def run(name: str, args: str = typer.Option("{}", help="JSON object of keyword args.")) -> None:
    """Invoke a tool by name with JSON kwargs."""
    tool = registry.get(name)
    result = tool.fn(**json.loads(args))
    typer.echo(json.dumps(result, indent=2, default=str) if not isinstance(result, str) else result)


if __name__ == "__main__":
    app()
