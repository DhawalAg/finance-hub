"""CLI surface over the tool registry.

    finance tools                         list every registered tool
    finance run <name> [--key value ...]  invoke a tool; flags become kwargs
    finance run <name> --args '<json>'    legacy JSON form (still works)
    finance check [--live]                read-only setup diagnostic
"""
from __future__ import annotations

import json
import os
from typing import Optional

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


def _parse_extra_flags(extra: list[str]) -> dict:
    """Convert ['--foo', 'bar', '--baz', 'qux'] into {'foo': 'bar', 'baz': 'qux'}.

    Values that look like JSON (objects, arrays, numbers, booleans, null) are
    decoded so callers don't need to quote them.
    """
    kwargs: dict = {}
    it = iter(extra)
    for token in it:
        if not token.startswith("--"):
            raise typer.BadParameter(f"unexpected positional argument: {token!r}")
        key = token.lstrip("-").replace("-", "_")
        try:
            raw = next(it)
        except StopIteration:
            raise typer.BadParameter(f"flag --{key} has no value")
        try:
            kwargs[key] = json.loads(raw)
        except json.JSONDecodeError:
            kwargs[key] = raw
    return kwargs


@app.command("run", context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def run(
    ctx: typer.Context,
    name: str,
    args: Optional[str] = typer.Option(None, help="JSON object of keyword args (legacy form)."),
) -> None:
    """Invoke a tool by name.

    Preferred: pass kwargs as flags —
        finance run finance.get_theme --key ai_infrastructure

    Legacy JSON form still works —
        finance run finance.get_theme --args '{"key":"ai_infrastructure"}'

    Flag values are auto-decoded from JSON when they look like JSON
    (numbers, booleans, objects, arrays); otherwise treated as strings.
    Both forms can be combined — extra flags take precedence over --args keys.
    """
    if args is not None and ctx.args:
        kwargs = {**json.loads(args), **_parse_extra_flags(ctx.args)}
    elif args is not None:
        kwargs = json.loads(args)
    else:
        kwargs = _parse_extra_flags(ctx.args)

    tool = registry.get(name)
    result = tool.fn(**kwargs)
    typer.echo(json.dumps(result, indent=2, default=str) if not isinstance(result, str) else result)


if __name__ == "__main__":
    app()
