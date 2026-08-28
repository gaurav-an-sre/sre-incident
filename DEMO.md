# Northstar Goods incident demo

Presenter script for an approximately ten-minute run. Commands assume the
service is running from the repository root and the browser is open at
<http://localhost:8000>.

## Run of show

| Presenter clock | What to do | What to point out |
| --- | --- | --- |
| 0:00–1:00 | Show the storefront with `make shop` running. | The strip is GREEN and the counter is live; this is real checkout traffic, not a mock status value. |
| 1:00–2:00 | Run `python -m tools.deploy promo` and show its four-line configuration diff. | This is an ordinary free-shipping configuration change; no application restart is needed. |
| 2:00–3:00 | Leave the shopper running and watch the status strip. | RED appears after the measured 15–25 second window; `/healthz` remains green because the failure is a business decline. |
| 3:00–4:00 | Submit the $98 cart and the $100 cart side by side. | The $98 cart succeeds; the $100 cart declines at the free-shipping boundary with `amount_mismatch`. |
| 4:00–5:00 | Open the frozen `incidents/<incident-id>/` directory and its `bundle.json`. | The bundle is immutable and its SHA-256 manifest makes the evidence reproducible. |
| 5:00–6:00 | Run `make demo-dry`. | Three investigators work independently; the citation checker catches the fabricated excerpt before adjudication; the adjudicator accepts only the supported hypothesis. |
| 6:00–7:15 | Run `make verify-wrong-fix`. | This is the centerpiece: apparent recovery passes S1, S2a, S4, and S6, but the independent gate rejects the overcharge through S2b, S3, and S5. |
| 7:15–8:15 | Run `make verify-correct-fix`. | The same oracle now says `verified=True` with all seven signals passing, while the promotion remains active. |
| 8:15–10:00 | Open `out/<incident-id>/postmortem.md` and, if useful, `postmortem_prompt.md`. | The dry-run postmortem is readable on its own; the prompt artifact is exactly what the scribe would receive. |

## Presenter notes

- The incident rate settles at 62–68% success in the measured runs. Say
  “about two thirds,” not “60%.”
- RED appears 15–25 seconds after the promo deploy. The watchdog and browser
  strip use rolling windows, so do not narrate the first few seconds as a
  failed deploy.
- Recovery to GREEN after rollback takes about 85 seconds because the
  60-second rolling window has to clear. Narrate that gap; it is expected
  hysteresis, not a broken rollback.
- If the shopper dies, the strip is grey `NO TRAFFIC`, not falsely green. That
  is a useful reliability moment: the display distinguishes stopped traffic
  from successful traffic.
- The $98 cart is the just-under-threshold control. The $100 cart is the exact
  boundary that exposes the quote/authorization divergence.
- Keep the three verifier runs in order: unfixed refusal, plausible-but-wrong
  refusal with the money discrepancy, then correct-fix acceptance. None of the
  verdicts comes from a model claim.

## Reset for a second run

Run this single command from the repository root after stopping the first
shopper. It rolls the configuration back, clears runtime evidence without
removing the tracked placeholder, and restarts the local service:

```sh
sh -c 'pkill -f "[t]ools.shopper" || true; python -m tools.deploy rollback; find var -mindepth 1 -maxdepth 1 ! -name ".gitkeep" -exec rm -rf -- {} +; pkill -f "[u]vicorn checkout_svc.main:app" || true; nohup .venv/bin/python -m uvicorn checkout_svc.main:app --host 127.0.0.1 --port 8000 >/tmp/sre-incident-service.log 2>&1 & sleep 1; curl -s localhost:8000/healthz'
```

Then reopen the storefront and run `make shop`.
