---
name: testing-incident-demo
description: How to run and end-to-end test the Northstar Goods red-to-green checkout incident demo (FastAPI + SQLite + JSONL evidence) in a browser.
---

# Testing the Northstar Goods incident demo

## Bring it up (repo root, `/home/ubuntu/repos/sre-incident`)

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # only if .venv missing
pkill -f 'uvicorn checkout_svc.main:app'                      # a stale service may hold :8000
mv var /tmp/var-stale-$(date +%s)                             # stale JSONL pollutes the 60s status window
nohup .venv/bin/python -m uvicorn checkout_svc.main:app --host 127.0.0.1 --port 8000 > /tmp/svc.log 2>&1 &
curl -s localhost:8000/healthz   # {"status":"ok"}
```

`var/` is recreated on startup (SQLite reseeded from `config/schema.sql` + `config/seed.sql`), so order
numbers restart near 1 — a clean `var/` also makes the demo's counters truthful.

Traffic: `nohup .venv/bin/python -m tools.shopper > /tmp/shopper.log 2>&1 &` (4 checkouts/s, ~40% carts ≥ $100).
Stop it with `pkill -f tools.shopper`. Incident: `.venv/bin/python -m tools.deploy promo`, revert with
`... deploy rollback`. Deploys only rewrite `config/pricing.yaml`; **no service restart is needed**, which is
what lets you watch the browser flip without reloading.

## Where the behaviour comes from

- `checkout_svc/pricing.py` zeroes shipping when `subtotal >= min_subtotal_cents` (10000) but
  `payments/authorize_request.py` always adds `shipping_cents`, so the authorization is 999 cents higher →
  `gateway.py` returns `declined/amount_mismatch`. The boundary is therefore **exactly $100.00 subtotal**.
- `/api/checkout` returns **HTTP 200** with `status: "declined"` (business decline, not an error) — assert 200 in
  the DevTools network tab, not 4xx/5xx.
- `/api/status` (`checkout_svc/main.py`) uses a 60 s window and 18 × 10 s buckets, polled every 1 s by the page.
  With **zero attempts it returns `success_rate: 1.0` / `state: GREEN`**, and empty buckets (`success_rate: null`)
  render as full-height green bars — an idle or dead service looks identical to a healthy one. If you are asked
  whether the display is honest, this is the thing to flag; a "NO TRAFFIC" state would fix it.
- A watchdog thread writes an immutable bundle to `incidents/inc-*/` after two bad 30 s windows, so a test run
  leaves a new untracked incident directory behind. Expect it; don't treat it as breakage.

## Useful exact carts (prices from `config/seed.sql`)

- Small: Stoneware Mug → subtotal $14.00, total $25.11.
- Just under threshold: Picnic Set + Canvas Tote + House Coffee Beans → subtotal **$98.00** (ships $9.99, total $115.83) — succeeds during the incident.
- Exactly at threshold: Desk Lamp + House Coffee Beans + Stoneware Mug → subtotal **$100.00** (promo zeroes shipping, total $108.00) — declines during the incident, and totals $117.99 / succeeds after rollback.

Sanity-check any cart before clicking through the UI:
`curl -s -X POST -H 'Content-Type: application/json' -d '{"items":[{"product_id":4,"quantity":1}]}' localhost:8000/api/quote`

## Cross-checking the strip against ground truth

The strip must equal an independent count of the last 60 s of `var/orders.jsonl` (`outcome` field; decline
reason lives in `decline_reason`, not `reason`). Timings to budget: RED appears ~15-25 s after the promo deploy
and settles near 60-68%; after rollback allow ~85 s for the 60 s window to clear back to 100%.

## Devin secrets needed

None — the app is entirely local with no auth or external calls.
