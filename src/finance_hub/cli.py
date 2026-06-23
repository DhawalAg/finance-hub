"""CLI surface over the tool registry.

    finance tools                       list every registered tool
    finance run <name> --args '<json>'  invoke a tool with JSON kwargs
"""
from __future__ import annotations

import json

import typer

from finance_hub import bootstrap as _bootstrap
from finance_hub.runtime import registry

_bootstrap.load_dotenv()
_bootstrap.bootstrap()

app = typer.Typer(help="finance-hub: run finance capabilities from the shell.")
registry.load_all()


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
