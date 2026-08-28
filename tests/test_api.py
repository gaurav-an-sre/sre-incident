import json
from pathlib import Path

from fastapi.testclient import TestClient

from checkout_svc.main import app
from tools.deploy import deploy


def test_checkout_decline_is_http_200_and_health_stays_green(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    root = Path(__file__).resolve().parents[1]
    for name in ("pricing.yaml", "pricing.promo.yaml"):
        (config_dir / name).write_text(
            (root / "config" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    var_dir = tmp_path / "var"
    monkeypatch.setenv("CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("VAR_DIR", str(var_dir))
    monkeypatch.setenv("DB_PATH", str(tmp_path / "store.sqlite3"))

    deploy("promo")
    with TestClient(app) as client:
        response = client.post("/api/checkout", json={"items": [{"product_id": 7, "quantity": 1}]})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "declined"
        assert body["decline_reason"] == "amount_mismatch"
        assert client.get("/healthz").status_code == 200
        assert client.get("/api/status").json()["declined_last_60s"] == 1

    orders = [json.loads(line) for line in (var_dir / "orders.jsonl").read_text().splitlines()]
    assert orders[0]["outcome"] == "declined"
