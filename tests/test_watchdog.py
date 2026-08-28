import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from checkout_svc.evidence import append_jsonl
from checkout_svc.watchdog import Watchdog


def test_watchdog_fires_after_two_bad_windows_and_hashes_bundle(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    for offset in (29, 15, 1):
        timestamp = (now - timedelta(seconds=offset)).isoformat()
        append_jsonl(
            "metrics.jsonl",
            {
                "timestamp": timestamp,
                "second": int((now - timedelta(seconds=offset)).timestamp()),
                "attempts": 10,
                "succeeded": 8,
                "declined": 2,
                "success_rate": 0.8,
                "p95_latency_ms": 2.0,
            },
            tmp_path,
        )
    for name in ("orders.jsonl", "payments.jsonl", "deploys.jsonl"):
        append_jsonl(name, {"timestamp": now.isoformat()}, tmp_path)

    watchdog = Watchdog(tmp_path, tmp_path / "incidents")
    assert watchdog.check_once() is None
    bundle_path = watchdog.check_once()
    assert bundle_path is not None
    assert (bundle_path / "alert.json").exists()
    assert (bundle_path / "bundle.json").exists()
    manifest = json.loads((bundle_path / "bundle.json").read_text())
    for name, expected_hash in manifest["files"].items():
        assert hashlib.sha256((bundle_path / name).read_bytes()).hexdigest() == expected_hash

    original = (bundle_path / "orders.jsonl").read_bytes()
    assert watchdog.check_once() is None
    assert (bundle_path / "orders.jsonl").read_bytes() == original


def test_watchdog_exact_threshold_does_not_alert(tmp_path: Path) -> None:
    timestamp = datetime.now(UTC).isoformat()
    append_jsonl(
        "metrics.jsonl",
        {
            "timestamp": timestamp,
            "second": 1,
            "attempts": 10,
            "succeeded": 9,
            "declined": 1,
            "success_rate": 0.9,
            "p95_latency_ms": 1.0,
        },
        tmp_path,
    )
    watchdog = Watchdog(tmp_path, tmp_path / "incidents")
    assert watchdog.check_once() is None
    assert watchdog.check_once() is None
