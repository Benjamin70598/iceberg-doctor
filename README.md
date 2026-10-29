# iceberg-doctor

Health checks for Apache Iceberg tables. Point it at a table and it tells you what's wrong
and how to fix it, before the problem shows up as slow queries or a failing maintenance job.

```
$ iceberg-doctor check demo.logs
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Severity ┃ Check           ┃ Detail                                                           ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ HIGH     │ snapshot_growth │ 500 commits in the hour before the latest snapshot (60/hr limit) │
│ MEDIUM   │ snapshot_count  │ 500 live snapshots (warn at 100, high at 1,000)                  │
│ MEDIUM   │ small_files     │ 500 of 500 data files are under 10% of the 512 MB target         │
│ MEDIUM   │ manifest_count  │ 500 manifests in the current snapshot; slows planning            │
│ LOW      │ retention_props │ Snapshot retention table properties not set                      │
└──────────┴─────────────────┴──────────────────────────────────────────────────────────────────┘
```

Each finding includes a recommended fix: the Spark SQL procedure or table property change to run.
iceberg-doctor is read-only and never modifies your table.

## Why

Iceberg tables degrade quietly. A streaming job that commits every few seconds can pile up
hundreds of thousands of snapshots until `expire_snapshots` itself can't finish. Frequent small
writes leave thousands of tiny files and manifests that slow down every query plan.
Merge-on-read tables accumulate delete files that every read has to merge. These problems are
easy to fix early and painful to fix late.

## Checks

| Check | What it catches | Recommended fix |
|---|---|---|
| `snapshot_count` | Too many live snapshots | `expire_snapshots` |
| `snapshot_growth` | Commit rate high enough to cause runaway snapshots | Batch writes, schedule expiry |
| `small_files` | Most data files far below the target file size | `rewrite_data_files` |
| `delete_files` | High delete-file to data-file ratio on merge-on-read tables | `rewrite_data_files` with `delete-file-threshold` |
| `manifest_count` | Manifest bloat that slows query planning | `rewrite_manifests` |
| `retention_props` | Snapshot retention table properties not set | `ALTER TABLE ... SET TBLPROPERTIES` |

## Install

```bash
uv tool install git+https://github.com/Benjamin70598/iceberg-doctor
```

## Configure

iceberg-doctor uses standard [PyIceberg catalog configuration](https://py.iceberg.apache.org/configuration/),
so it works with REST, Glue, Hive, SQL, and any other catalog PyIceberg supports. Example `~/.pyiceberg.yaml`:

```yaml
catalog:
  default:
    uri: https://my-rest-catalog.example.com
    token: <token>
    warehouse: my_warehouse
```

Note: with the SQL catalog, the catalog name in your config must match the name the tables were
created under, since PyIceberg stores it alongside each table.

## Usage

```bash
iceberg-doctor check db.events                  # table output
iceberg-doctor check db.events --json           # machine-readable output
iceberg-doctor check db.events -c prod          # use a named catalog
iceberg-doctor check db.events --fail-on medium # exit 1 on medium or higher (CI / Airflow gate)
```

Exit codes: `0` no findings at or above `--fail-on` (default `high`), `1` findings found, `2` table could not be loaded.

## MCP server

iceberg-doctor also runs as an MCP server, so AI agents (Claude Desktop, Claude Code, Cursor,
and others) can diagnose tables directly. It exposes two read-only tools: `list_tables(namespace)`
and `diagnose_table(table)`.

Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "iceberg-doctor": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Benjamin70598/iceberg-doctor", "iceberg-doctor-mcp"],
      "env": { "ICEBERG_DOCTOR_CATALOG": "default" }
    }
  }
}
```

Catalog settings come from `~/.pyiceberg.yaml` as usual (or set `PYICEBERG_HOME` in `env`).
If Claude Desktop can't find `uvx`, use its full path (`which uvx`).

## Try it locally

```bash
git clone https://github.com/Benjamin70598/iceberg-doctor && cd iceberg-doctor
uv sync
uv run python scripts/make_sick_table.py   # creates a deliberately unhealthy table
```

## Roadmap

- Spark-generated merge-on-read test tables for the delete-file check
- Generated, safely ordered maintenance plans (`--plan`)
- Trend view across snapshots
