from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import timedelta

import pyarrow as pa
import pyarrow.compute as pc

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
DEFAULT_TARGET_FILE_SIZE = 512 * 1024 * 1024
RETENTION_PROPS = [
    "history.expire.max-snapshot-age-ms",
    "history.expire.min-snapshots-to-keep",
]


@dataclass
class Finding:
    severity: str
    check: str
    detail: str
    fix: str

    def to_dict(self) -> dict:
        return asdict(self)


def check_snapshot_count(tbl, name, warn=100, high=1000):
    n = tbl.inspect.snapshots().num_rows
    if n < warn:
        return []
    sev = "high" if n >= high else "medium"
    return [Finding(
        sev, "snapshot_count",
        f"{n:,} live snapshots (warn at {warn:,}, high at {high:,})",
        f"CALL <catalog>.system.expire_snapshots(table => '{name}', "
        f"older_than => TIMESTAMP '<cutoff>', retain_last => 100)",
    )]


def check_snapshot_growth(tbl, name, max_per_hour=60):
    ts = tbl.inspect.snapshots().column("committed_at")
    if len(ts) < 2:
        return []
    newest = pc.max(ts).as_py()
    cutoff = pa.scalar(newest - timedelta(hours=1), type=ts.type)
    last_hour = pc.sum(pc.greater_equal(ts, cutoff)).as_py()
    if last_hour <= max_per_hour:
        return []
    return [Finding(
        "high", "snapshot_growth",
        f"{last_hour:,} commits in the hour before the latest snapshot "
        f"(threshold {max_per_hour}/hr); snapshot count will keep climbing",
        "Batch writes (longer streaming trigger interval) and schedule "
        "expire_snapshots; set snapshot retention table properties",
    )]


def check_small_files(tbl, name, min_files=20, small_ratio=0.5):
    files = tbl.inspect.data_files()
    n = files.num_rows
    if n < min_files:
        return []
    target = int(tbl.properties.get("write.target-file-size-bytes", DEFAULT_TARGET_FILE_SIZE))
    sizes = files.column("file_size_in_bytes")
    small = pc.sum(pc.less(sizes, target // 10)).as_py()
    if small / n < small_ratio:
        return []
    avg_kb = pc.mean(sizes).as_py() / 1024
    sev = "high" if small > 1000 else "medium"
    return [Finding(
        sev, "small_files",
        f"{small:,} of {n:,} data files are under 10% of the "
        f"{target // (1024 * 1024)} MB target (avg {avg_kb:,.1f} KB)",
        f"CALL <catalog>.system.rewrite_data_files(table => '{name}')",
    )]


def check_delete_files(tbl, name, max_ratio=0.2):
    if not hasattr(tbl.inspect, "delete_files"):
        return []
    deletes = tbl.inspect.delete_files().num_rows
    data = tbl.inspect.data_files().num_rows
    if deletes == 0 or data == 0 or deletes / data < max_ratio:
        return []
    return [Finding(
        "medium", "delete_files",
        f"{deletes:,} delete files vs {data:,} data files "
        f"(ratio {deletes / data:.2f}); reads pay merge-on-read cost",
        f"CALL <catalog>.system.rewrite_data_files(table => '{name}', "
        f"options => map('delete-file-threshold', '1'))",
    )]


def check_manifests(tbl, name, warn=100):
    m = tbl.inspect.manifests()
    n = m.num_rows
    if n < warn:
        return []
    avg_kb = pc.mean(m.column("length")).as_py() / 1024
    return [Finding(
        "medium", "manifest_count",
        f"{n:,} manifests in the current snapshot (avg {avg_kb:,.1f} KB); "
        f"slows planning",
        f"CALL <catalog>.system.rewrite_manifests(table => '{name}')",
    )]


def check_retention_props(tbl, name):
    missing = [p for p in RETENTION_PROPS if p not in tbl.properties]
    if not missing:
        return []
    return [Finding(
        "low", "retention_props",
        f"Not set: {', '.join(missing)}; expire_snapshots falls back to defaults",
        f"ALTER TABLE {name} SET TBLPROPERTIES "
        f"('history.expire.max-snapshot-age-ms'='86400000', "
        f"'history.expire.min-snapshots-to-keep'='100')",
    )]


ALL_CHECKS = [
    check_snapshot_count,
    check_snapshot_growth,
    check_small_files,
    check_delete_files,
    check_manifests,
    check_retention_props,
]


def run_all_checks(tbl, name) -> list[Finding]:
    findings: list[Finding] = []
    for check in ALL_CHECKS:
        try:
            findings.extend(check(tbl, name))
        except Exception as e:  # one broken check shouldn't kill the report
            findings.append(Finding("low", check.__name__, f"check failed: {e}", "n/a"))
    return sorted(findings, key=lambda f: SEVERITY_ORDER[f.severity])
