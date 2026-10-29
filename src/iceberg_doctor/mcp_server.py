import os

from mcp.server.mcpserver import MCPServer
from pyiceberg.catalog import load_catalog

from iceberg_doctor.checks import run_all_checks

DEFAULT_CATALOG = os.environ.get("ICEBERG_DOCTOR_CATALOG", "default")

mcp = MCPServer("iceberg-doctor")


@mcp.tool()
def list_tables(namespace: str, catalog: str = DEFAULT_CATALOG) -> list[str]:
    """List Iceberg tables in a namespace. Read-only."""
    return [".".join(ident) for ident in load_catalog(catalog).list_tables(namespace)]


@mcp.tool()
def diagnose_table(table: str, catalog: str = DEFAULT_CATALOG) -> list[dict]:
    """Run iceberg-doctor health checks on an Iceberg table (e.g. 'db.events').

    Returns findings sorted by severity (high/medium/low), each with a detail
    and a recommended fix (Spark SQL procedure or table property change).
    Read-only: nothing is executed against the table.
    """
    tbl = load_catalog(catalog).load_table(table)
    return [f.to_dict() for f in run_all_checks(tbl, table)]


def main():
    mcp.run()


if __name__ == "__main__":
    main()
