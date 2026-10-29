import json

import typer
from pyiceberg.catalog import load_catalog
from rich.console import Console
from rich.table import Table

from iceberg_doctor.checks import SEVERITY_ORDER, run_all_checks

app = typer.Typer(no_args_is_help=True)
console = Console()
COLORS = {"high": "bold red", "medium": "yellow", "low": "cyan"}


@app.callback()
def main():
    """Health checks for Apache Iceberg tables."""


@app.command()
def check(
    table: str = typer.Argument(..., help="Table identifier, e.g. db.events"),
    catalog: str = typer.Option("default", "--catalog", "-c",
                                help="Catalog name from .pyiceberg.yaml / env vars"),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table"),
    fail_on: str = typer.Option("high", "--fail-on",
                                help="Exit 1 on findings at/above: high|medium|low|none"),
):
    """Diagnose a table and recommend fixes."""
    try:
        tbl = load_catalog(catalog).load_table(table)
    except Exception as e:
        console.print(f"[bold red]Could not load {table} from catalog '{catalog}':[/] {e}")
        raise typer.Exit(2)

    findings = run_all_checks(tbl, table)

    if as_json:
        typer.echo(json.dumps([f.to_dict() for f in findings], indent=2))
    elif not findings:
        console.print(f"[bold green]✓ {table} looks healthy[/]")
    else:
        t = Table(title=f"iceberg-doctor: {table}", show_lines=True)
        t.add_column("Severity", no_wrap=True)
        t.add_column("Check", no_wrap=True)
        t.add_column("Detail")
        t.add_column("Fix", style="dim")
        for f in findings:
            t.add_row(f"[{COLORS[f.severity]}]{f.severity.upper()}[/]", f.check, f.detail, f.fix)
        console.print(t)

    if fail_on != "none" and any(
        SEVERITY_ORDER[f.severity] <= SEVERITY_ORDER[fail_on] for f in findings
    ):
        raise typer.Exit(1)
