import json
from pathlib import Path

from tools.deploy import deploy


def test_deploy_and_rollback_record_unified_diffs(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for name in ("pricing.yaml", "pricing.promo.yaml", "pricing.baseline.yaml"):
        (config_dir / name).write_text(
            (root / "config" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("VAR_DIR", str(tmp_path / "var"))
    assert deploy("promo").startswith("deploy-")
    assert "FREESHIP100" in (config_dir / "pricing.yaml").read_text()
    deploy("rollback")
    assert "FREESHIP100" not in (config_dir / "pricing.yaml").read_text()
    records = [
        json.loads(line)
        for line in (tmp_path / "var" / "deploys.jsonl").read_text().splitlines()
    ]
    assert len(records) == 2
    assert all(record["diff"].startswith("--- pricing.yaml") for record in records)


def test_rollback_before_promo_uses_committed_baseline(tmp_path: Path, monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for name in ("pricing.yaml", "pricing.baseline.yaml"):
        (config_dir / name).write_text(
            (root / "config" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (config_dir / "pricing.yaml").write_text(
        (root / "config" / "pricing.promo.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("VAR_DIR", str(tmp_path / "var"))
    deploy("rollback")
    assert (config_dir / "pricing.yaml").read_text() == (
        config_dir / "pricing.baseline.yaml"
    ).read_text()
