# Storefront Checkout Incident Demo

This repository is a deliberately small SRE incident demonstration. A browser
storefront and a deterministic SQLite checkout service run normally until a
routine-looking free-shipping configuration is deployed. Orders over $100 then
decline as a business result while health checks remain green.

The fault is a genuine arithmetic divergence, not an injected exception:
`pricing.quote()` applies the free-shipping promo, while the independent
payment authorization calculation still uses configured flat shipping. The
simulated payment provider rejects the 999-cent mismatch without raising or
logging a traceback.

## Run the demo

Python 3.12 is required. Install the pinned runtime and development
dependencies:

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

Start the service:

```sh
make up
```

Open <http://localhost:8000>. The status strip is driven by real checkout
outcomes. In another terminal, start deterministic traffic:

```sh
make shop
```

The shopper runs continuously at four checkouts per second. For a bounded
demo, use `.venv/bin/python -m tools.shopper --duration 20`.

Deploy and roll back the business configuration without restarting the service:

```sh
python -m tools.deploy promo
python -m tools.deploy rollback
```

The shopper's mix is approximately 40% carts at or above $100. Before the
promo, all carts succeed. During the promo, the larger carts decline with
`amount_mismatch`, leaving approximately 60% success. The watchdog observes
the rolling 30-second windows and creates an incident bundle after two bad
checks.

## Evidence files

Runtime evidence is append-only JSONL under `var/` and is intentionally
gitignored:

* `orders.jsonl`: `order_id`, `timestamp`, `line_items`, `quote`,
  `authorized_amount_cents`, `outcome`, `decline_reason`, and `latency_ms`.
* `metrics.jsonl`: one line per active second with `timestamp`, `second`,
  `attempts`, `succeeded`, `declined`, `success_rate`, and `p95_latency_ms`.
* `payments.jsonl`: `timestamp`, `order_id`, `requested_amount_cents`,
  `reconciliation_amount_cents`, `decision`, and `reason`.
* `deploys.jsonl`: `timestamp`, `deploy_id`, `actor`,
  `change_description`, and the unified config `diff`.
* `alerts.jsonl`: watchdog alert metadata, including the incident window.

These schemas are intentionally stable read-only inputs for the investigation
agents.

## Offline investigation fleet

Phase 2 wires three independent Cursor cloud hypothesis investigators and a
cloud adjudicator. A live run requires `CURSOR_API_KEY`:

```sh
python -m incident_agents investigate --incident <incident-id> \
  --starting-ref main
python -m incident_agents status --incident <incident-id>
python -m incident_agents agents
```

The investigators run independently, cite only the frozen bundle and
allowlisted source paths, and write their typed event streams and durable
state under `out/<incident-id>/`. The citation checker independently verifies
each excerpt and the adjudicator may accept only a post-validation
`supported` hypothesis.

The complete fleet can be demonstrated without credentials:

```sh
make demo-dry
```

## Incident bundles

On alert, `checkout_svc.watchdog` writes
`incidents/<incident_id>/`. The directory contains the four evidence files
trimmed to the incident window, `alert.json`, and `bundle.json`. The manifest
contains SHA-256 hashes for each evidence file and the alert. A bundle is
created once and never rewritten.

Incident bundles are deliberately committed to the repository rather than
ignored. This makes a frozen, reproducible artifact available to later Cursor
cloud agents investigating the incident. The live `var/` stream remains
ignored so a demo run does not dirty the working tree.

## Independent verification and follow-up phases

The verifier runs a candidate with the promotion configuration active and does
not use an agent's confidence or conclusion as its oracle:

```sh
make verify
make verify-wrong-fix
```

`verify` writes `out/verification.json`. It runs 200 deterministic shopper
attempts, derives the real-product S2a boundary matrix from the promotion
threshold, checks the one-cent S2b boundary directly through both pricing
implementations and the independent reference pricer, compares every quote
with the authorized and reference amounts, exercises gateway reconciliation,
and runs another 200-attempt compressed soak. The latter is a bounded
no-new-declines/no-new-alerts check; it represents a soak test without
pretending that real elapsed soak time passed.

`make verify-wrong-fix` applies `fixtures/wrong_fix.patch` only to a scratch
candidate. That plausible gateway change restores apparent recovery while
silently overcharging qualifying customers, so S3 rejects it even though the
other recovery signals pass.

After an adjudicated investigation, remediation can be requested with:

```sh
python -m incident_agents remediate --incident <incident-id> --dry-run
python -m incident_agents publish --incident <incident-id> --dry-run
```

Remediation refuses inconclusive adjudications and records the cloud agent's
claim separately from verification. Publish dry-run renders
`out/<incident-id>/postmortem.md` from the frozen alert bundle,
investigation, remediation, and verification artifacts. Live publication
requires `NOTION_TOKEN` and an explicit `--parent-page`; neither is needed for
dry-run mode.

## Quality checks

```sh
ruff check .
mypy checkout_svc tools payments incident_agents verify
pytest
```
