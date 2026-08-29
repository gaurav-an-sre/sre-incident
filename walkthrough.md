# Storefront Checkout Incident Demo — Interview Walkthrough

A presenter guide for demonstrating an end-to-end SRE incident workflow powered by the **Cursor SDK**. Use this document to explain the problem, architecture, design decisions, live demo flow, and future roadmap.

---

## Table of contents

1. [Problem statement](#1-problem-statement)
2. [Why this problem (enterprise perspective)](#2-why-this-problem-enterprise-perspective)
3. [Repository status](#3-repository-status)
4. [System architecture](#4-system-architecture)
5. [Where the Cursor SDK is used](#5-where-the-cursor-sdk-is-used)
6. [Key design decisions](#6-key-design-decisions)
7. [Live demo walkthrough (~12 minutes)](#7-live-demo-walkthrough-12-minutes)
8. [Interview talking points](#8-interview-talking-points)
9. [Anticipated questions](#9-anticipated-questions)
10. [Future enhancements](#10-future-enhancements)
11. [Setup and commands reference](#11-setup-and-commands-reference)

---

## 1. Problem statement

**Northstar Goods** runs a checkout service. A routine free-shipping promotion is deployed. Shortly after, checkout success rate drops from 100% to roughly two-thirds — but `/healthz` stays green.

The failure is not an outage. It is a **business decline**: the payment provider rejects transactions with `amount_mismatch` because two independent code paths compute different totals for the same cart.

| Path | Shipping for carts ≥ $100 |
|------|---------------------------|
| `checkout_svc/pricing.py` → `quote()` | Applies free-shipping promo → **$0 shipping** |
| `payments/authorize_request.py` → `build_authorization_request()` | Uses flat configured shipping → **$9.99 shipping** |

The 999-cent gap is rejected by the simulated payment gateway. No exception is raised. No traceback is logged. Health checks pass. Only business metrics reveal the incident.

**The SRE challenge:** detect the incident, investigate root cause with evidence, remediate safely, verify the fix is correct (not just that errors stopped), and publish a postmortem — without letting an LLM self-certify its own conclusions.

---

## 2. Why this problem (enterprise perspective)

This scenario was chosen because it mirrors the hardest class of production incidents enterprises actually face.

### 2.1 Green health checks, red business metrics

Most monitoring stacks alert on process health, HTTP 5xx, and latency. This incident produces **HTTP 200 responses with business-level declines**. On-call engineers see a healthy service while revenue and customer experience degrade. This is common in:

- Payment reconciliation mismatches
- Pricing rule divergence across microservices
- Feature-flag rollouts that change business logic without touching infrastructure
- A/B test configuration drift

### 2.2 Configuration change, not code deploy

The trigger is `python -m tools.deploy promo` — a YAML configuration swap, not an application restart. In enterprise environments, the majority of incidents are caused by config, feature flags, and policy changes rather than application crashes. The demo shows that **"we didn't deploy code" does not mean "we didn't change behaviour."**

### 2.3 Silent arithmetic divergence

The bug is a genuine logic divergence between two calculation paths — not an injected exception or artificial fault. This reflects real-world payment and pricing systems where:

- Customer-facing quotes are computed in one service
- Authorization amounts are computed independently for reconciliation
- Small divergences cause silent revenue loss or customer-facing declines

### 2.4 AI-assisted investigation needs guardrails

Enterprises are adopting AI agents for incident response, but a model that can **propose** a root cause must not also **certify** it. This demo separates:

| Role | Who decides |
|------|-------------|
| Hypothesis generation | Cursor cloud agents (SDK) |
| Evidence validation | Deterministic citation checker |
| Adjudication | Cursor cloud agent (constrained to validated evidence) |
| Fix correctness | Seven-signal verification oracle (no LLM) |
| Postmortem | Cursor cloud agent (scribe, grounded in frozen record) |

This maps to enterprise requirements: **agents explore; deterministic systems decide.**

### 2.5 Reproducible evidence for compliance

Incident bundles are frozen, SHA-256-hashed, and committed to the repository. Cloud agents investigate from this immutable record — the same pattern enterprises need for audit trails, postmortem reviews, and regulatory compliance.

---

## 3. Repository status

| Branch | Status | Contents |
|--------|--------|----------|
| `main` | Merged (PR #1) | Phase 1: storefront, fault, evidence pipeline, watchdog, incident bundles |
| `devin/1787896343-agent-fleet` | Open (PR #2) | Phase 2–3: Cursor SDK fleet, citation validation, verification oracle, Notion publish, `DEMO.md` |

**For the full interview demo, checkout the agent-fleet branch:**

```sh
git checkout devin/1787896343-agent-fleet
```

---

## 4. System architecture

### 4.1 High-level flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PHASE 1: DETECTION                              │
│                                                                         │
│  Shopper traffic ──► Checkout API ──► Pricing quote                     │
│                           │                                             │
│                           ├──► Payment authorization (independent calc)│
│                           │                                             │
│                           └──► Gateway reconcile ──► succeed / decline  │
│                                                                         │
│  Metrics recorder ──► Watchdog ──► Incident bundle (frozen + hashed)    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    PHASE 2: INVESTIGATION (Cursor SDK)                  │
│                                                                         │
│  Frozen bundle ──┬──► H-CHANGE agent (cloud)                           │
│                  ├──► H-DEPENDENCY agent (cloud)                        │
│                  └──► H-CAPACITY agent (cloud)                          │
│                              │                                          │
│                              ▼                                          │
│                    Citation validator (deterministic)                     │
│                              │                                          │
│                              ▼                                          │
│                    Adjudicator agent (cloud)                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    PHASE 3: REMEDIATION + VERIFICATION                  │
│                                                                         │
│  Remediator agent (cloud, auto_create_pr) ──► Pull request              │
│                              │                                          │
│                              ▼                                          │
│  7-signal verification oracle (deterministic, no LLM)                 │
│                              │                                          │
│                              ▼                                          │
│  Scribe agent (cloud) ──► Notion postmortem                             │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Component map

| Component | Path | Purpose |
|-----------|------|---------|
| Storefront + API | `checkout_svc/` | FastAPI service, SQLite, Jinja2 UI |
| Pricing (customer-facing) | `checkout_svc/pricing.py` | Applies promos including free shipping |
| Authorization (payment-facing) | `payments/authorize_request.py` | Independent amount calculation |
| Gateway | `checkout_svc/gateway.py` | Simulated provider; declines on mismatch |
| Evidence pipeline | `checkout_svc/evidence.py` | Append-only JSONL under `var/` |
| Watchdog | `checkout_svc/watchdog.py` | Rolling-window alert + bundle creation |
| Deploy tool | `tools/deploy.py` | Hot-swap pricing config (promo / rollback) |
| Shopper | `tools/shopper.py` | Deterministic traffic generator (~4/sec) |
| SDK wrapper | `incident_agents/sdk.py` | **Only module that imports `cursor_sdk`** |
| Orchestrator | `incident_agents/orchestrate.py` | Parallel investigation + adjudication |
| Citation validator | `incident_agents/validate.py` | Verifies excerpts against bundle + source |
| Remediation | `incident_agents/remediate.py` | Cloud agent with `auto_create_pr` |
| Publisher | `incident_agents/publish.py` | Scribe agent → Notion postmortem |
| Verification oracle | `verify/engine.py` | Seven independent pass/fail signals |
| Reference pricing | `verify/reference.py` | Independent ground truth (no imports from app code) |

### 4.3 Evidence model

**Live stream** (gitignored, under `var/`):

- `orders.jsonl` — per-checkout outcomes, quotes, authorized amounts
- `metrics.jsonl` — per-second success rate and latency
- `payments.jsonl` — requested vs reconciled amounts
- `deploys.jsonl` — config changes with unified diffs
- `alerts.jsonl` — watchdog alert metadata

**Frozen bundle** (committed, under `incidents/<incident-id>/`):

- Trimmed copies of the above for the incident window
- `alert.json` — alert metadata and window boundaries
- `bundle.json` — SHA-256 manifest for reproducibility

Cloud agents read the bundle and allowlisted source paths only. They cannot see the live runtime.

---

## 5. Where the Cursor SDK is used

All SDK interaction is isolated in `incident_agents/sdk.py`. The rest of the codebase never imports `cursor_sdk`.

### 5.1 SDK wrapper (`CloudFleet`)

```python
# incident_agents/sdk.py — the only SDK touchpoint
cloud = sdk.CloudAgentOptions(
    repos=[sdk.CloudRepository(url=REPO_URL, starting_ref=starting_ref)],
    auto_create_pr=auto_create_pr,
    metadata={
        "demo": "sre-incident",
        "incident": incident_id,
        "role": role,
        "hypothesis": hypothesis_id,
    },
)
agent = sdk.Agent.create(model="composer-2.5", cloud=cloud, ...)
```

**SDK capabilities used:**

| SDK API | Where | Purpose |
|---------|-------|---------|
| `Agent.create()` | Investigation, adjudication, remediation, publish | Spin up tagged cloud agents on the repo |
| `Agent.resume()` | Orchestrator | Resume agents across investigation turns |
| `Agent.list()` | CLI `agents` command | List fleet filtered by `demo: sre-incident` metadata |
| `CloudAgentOptions` | All agents | Bind to GitHub repo at a specific ref |
| `CloudRepository` | All agents | Point agents at `github.com/gaurav-an-sre/sre-incident` |
| `auto_create_pr` | Remediator | Open a PR with the proposed fix |
| `Bridge.launch()` | Fallback | Local development bridge when cloud client unavailable |

### 5.2 Agent roles

| Role | Hypothesis | SDK agent? | What it does |
|------|------------|------------|--------------|
| **H-CHANGE** | Recent deploy caused this | Yes | Correlates deploy timing with failure pattern; traces code paths |
| **H-DEPENDENCY** | External provider failure | Yes | Checks gateway/provider health signals |
| **H-CAPACITY** | Resource exhaustion | Yes | Checks latency, throughput, saturation |
| **Adjudicator** | — | Yes | Picks winner from post-validation reports only |
| **Remediator** | — | Yes (`auto_create_pr`) | Proposes and opens a fix PR |
| **Scribe** | — | Yes (Notion MCP) | Writes postmortem from frozen record |

Investigators run **in parallel** via `ThreadPoolExecutor`. Each is blind to the others.

### 5.3 CLI commands

```sh
# Live investigation (requires CURSOR_API_KEY)
python -m incident_agents investigate --incident <id> --starting-ref main --fresh

# Check agent status
python -m incident_agents status --incident <id>
python -m incident_agents agents

# Remediation
python -m incident_agents remediate --incident <id>

# Postmortem publication
python -m incident_agents publish --incident <id> --parent-page <notion-page-id>

# Offline demo (no API key — uses canned fixture replies)
make demo-dry
```

### 5.4 Dry-run mode

`make demo-dry` replays canned JSON replies from `tests/fixtures/replies/` through the same orchestration and validation pipeline. This is the recommended mode for interviews:

- Deterministic output every time
- No API key or network dependency
- Still demonstrates citation catching and adjudication correction
- Completes in ~30 seconds

---

## 6. Key design decisions

### 6.1 Agents propose; deterministic code decides

The single most important architectural principle. Two guardrails enforce it:

**Citation validator** (`incident_agents/validate.py`):
- Every evidence excerpt must exist verbatim in an allowlisted file
- Requires ≥2 valid citations, including ≥1 from the frozen bundle
- Unsupported verdicts downgrade to `inconclusive`
- Fabricated excerpts are caught before adjudication

**Verification oracle** (`verify/engine.py`):
- Seven independent signals; all must pass
- Does not read agent claims, confidence, or conclusions
- Separates "did errors stop?" (S1, S2a, S4, S6) from "is the money right?" (S2b, S3, S5)

### 6.2 Competing hypotheses, not a single prompt

Three blind investigators test orthogonal theories:

| Hypothesis | Theory | Why include it |
|------------|--------|----------------|
| H-CHANGE | Something we shipped caused this | The actual root cause |
| H-DEPENDENCY | External provider is down | Common misdiagnosis — gateway looks fine |
| H-CAPACITY | We're out of resources | Latency is normal — rules this out with evidence |

This prevents anchoring on the first plausible explanation and mirrors how strong incident response teams work.

### 6.3 Frozen bundles, not live runtime access

Cloud agents boot against the GitHub repo at a specific ref. They read committed incident bundles and allowlisted source paths. They cannot SSH into production or tail live logs.

**Why:** Reproducibility, auditability, and safety. Every investigation runs against the same evidence.

### 6.4 SDK isolation in one module

`incident_agents/sdk.py` is the only file that imports `cursor_sdk`. The orchestrator, validator, verifier, and checkout service have zero SDK dependency.

**Why:** The investigation fleet can be swapped (different SDK version, local bridge, dry-run fixtures) without touching application code or verification logic.

### 6.5 Independent reference pricing

`verify/reference.py` computes expected amounts without importing `checkout_svc` or `payments`. It is a third ground-truth path for the oracle.

**Why:** The verifier must not share the same bug as the code it is checking.

### 6.6 The wrong-fix trap

`fixtures/wrong_fix.patch` changes the gateway to only decline undercharges (`<` instead of `!=`). This:

- Passes recovery signals (errors stop, success rate recovers)
- Fails money signals (customers get overcharged)

**Why:** Proves that "the incident looks resolved" is not the same as "the incident is resolved." This is the centerpiece of the verification demo.

### 6.7 Hot config deploy without restart

`tools/deploy.py` swaps `config/pricing.yaml` ↔ `config/pricing.promo.yaml` at runtime.

**Why:** Mirrors enterprise config-management workflows and shows the incident is a business-logic change, not an infrastructure failure.

### 6.8 Committed incident bundles

Bundles under `incidents/` are committed to the repo (unlike live `var/` streams).

**Why:** Cloud agents and interview demos always have a frozen, reproducible artifact available without running the live system first.

---

## 7. Live demo walkthrough (~12 minutes)

### Pre-demo setup

```sh
git checkout devin/1787896343-agent-fleet
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'

# Terminal 1
make up

# Terminal 2
make shop

# Browser
open http://localhost:8000
```

### Act 1 — The incident (4 min)

| Time | Action | What to say |
|------|--------|-------------|
| 0:00 | Show storefront, GREEN strip, live counter | "Real checkout traffic at 4/sec — not a mocked status badge." |
| 1:00 | `python -m tools.deploy promo` | "Ordinary free-shipping config change. No restart." |
| 2:00 | Watch status strip turn RED | "RED in 15–25 seconds. `/healthz` stays green — business decline, not outage." |
| 3:00 | Submit $98 cart vs $100 cart | "$98 succeeds. $100 fails with `amount_mismatch` — exact promo boundary." |

### Act 2 — Frozen evidence (1 min)

```sh
ls incidents/inc-20260828T054250Z-696028f6/
cat incidents/inc-20260828T054250Z-696028f6/bundle.json
```

> "Cloud agents can't see my live machine. They get this immutable bundle with SHA-256 hashes."

### Act 3 — Cursor SDK agent fleet (3 min)

```sh
make demo-dry
```

Point out in the output:

1. Three investigators run independently
2. H-DEPENDENCY fabricates a citation → **citation checker catches it**
3. H-CHANGE finds the real root cause → `supported`
4. Adjudicator first picks wrong hypothesis → corrected to H-CHANGE

> "`incident_agents/sdk.py` is the only module that imports `cursor_sdk`. It creates tagged cloud agents, runs them in parallel, and the adjudicator only accepts post-validation evidence."

Optional live SDK demo (if `CURSOR_API_KEY` is set):

```sh
python -m incident_agents investigate \
  --incident inc-20260828T054250Z-696028f6 --starting-ref main --fresh
```

### Act 4 — Verification oracle (2 min)

```sh
make verify-wrong-fix    # passes recovery, fails money signals
make verify-correct-fix  # all seven signals pass
```

> "A plausible gateway fix stops the errors but silently overcharges customers. The oracle is not an agent — seven deterministic signals decide."

### Act 5 — Postmortem (1 min)

```sh
cat out/inc-20260828T054250Z-696028f6/postmortem.md
```

> "The scribe agent writes a postmortem from the frozen record. Dry-run renders locally; live mode publishes to Notion via MCP."

### Closing (30 sec)

> "Detect → bundle → parallel SDK agents → citation-gated adjudication → remediate with PR → deterministic verification → postmortem. Agents explore; guardrails decide."

---

## 8. Interview talking points

Memorize these five sentences:

1. **"Health checks stayed green; only business metrics revealed the incident."**
2. **"Three competing hypothesis agents run in parallel — the adjudicator can't accept unchecked evidence."**
3. **"The citation validator is the load-bearing guardrail, not the prompts."**
4. **"The wrong-fix demo proves errors stopping is not the same as the incident being over."**
5. **"The Cursor SDK is isolated in one module — everything else is deterministic and testable."**

---

## 9. Anticipated questions

**Why not just ask one agent what's wrong?**
> Competing hypotheses prevent anchoring. Three blind investigators plus an adjudicator constrained to validated citations produces stronger conclusions than a single open-ended prompt.

**How do you prevent hallucinated root causes?**
> `validate.py` checks every citation against actual file contents. Fabricated excerpts downgrade to `inconclusive`. The adjudicator cannot accept them.

**How do you prevent a bad fix from shipping?**
> Seven independent verification signals. The wrong-fix fixture proves that recovery signals alone are insufficient.

**What's the Cursor SDK actually doing?**
> Creating, resuming, and listing tagged cloud agents on the repo; streaming their output; orchestrating parallel investigation; and opening PRs via `auto_create_pr`.

**Why commit incident bundles?**
> Cloud sandboxes can't see live runtime. Frozen, hashed evidence is reproducible across agents, interviews, and compliance reviews.

**How is this different from just using Cursor chat?**
> Chat is a single conversational thread. This is a structured fleet: parallel agents with assigned hypotheses, deterministic validation gates, independent verification, and auditable state under `out/<incident-id>/`.

---

## 10. Future enhancements

### Near term

| Enhancement | Rationale |
|-------------|-----------|
| **Merge agent-fleet branch to `main`** | Single branch for demo and development |
| **Notion MCP live publish** | Requires `NOTION_TOKEN` + authenticated MCP in Cursor Desktop |
| **Cursor skill for demo driving** | PR #3 adds `.agents/skills/testing-incident-demo/SKILL.md` |
| **CI pipeline** | Run `make demo-dry`, `make verify-*`, and `pytest` on every PR |

### Medium term

| Enhancement | Rationale |
|-------------|-----------|
| **Live SDK demo mode** | Run real cloud agents during interview with streaming output in terminal |
| **Multi-incident support** | Investigate and compare multiple bundles; trend analysis across incidents |
| **Slack / PagerDuty integration** | Alert → bundle → auto-trigger investigation fleet |
| **Human-in-the-loop adjudication** | Escalate to on-call engineer before remediation PR is opened |
| **Cost and token budgeting** | Track agent spend per incident; cap parallel investigators |

### Long term

| Enhancement | Rationale |
|-------------|-----------|
| **Production connector** | Ingest real evidence (Datadog, Splunk, deploy webhooks) into bundle format |
| **Policy engine** | Org-specific rules for which hypotheses to run, when to auto-remediate |
| **Feedback loop** | Postmortem action items → tracked tasks → verification on next deploy |
| **Multi-service mesh** | Extend beyond checkout to cross-service pricing/fraud/inventory divergence |
| **Regression suite from incidents** | Each bundle becomes a permanent test case in CI |

---

## 11. Setup and commands reference

### Prerequisites

- Python 3.12
- Branch: `devin/1787896343-agent-fleet`
- Optional: `CURSOR_API_KEY` (live agents), `NOTION_TOKEN` (live publish)

### Install

```sh
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

### Run the live incident

```sh
make up          # Terminal 1 — start service
make shop        # Terminal 2 — start traffic
```

### Trigger and observe

```sh
python -m tools.deploy promo       # trigger incident
python -m tools.deploy rollback    # recover
curl -s http://localhost:8000/api/status | python3 -m json.tool
```

### SDK investigation fleet

```sh
make demo-dry                      # offline (recommended for interviews)

python -m incident_agents investigate --incident <id> --fresh   # live
python -m incident_agents status --incident <id>
python -m incident_agents agents
```

### Verification oracle

```sh
make verify               # unfixed → verified=False
make verify-wrong-fix     # plausible fix → verified=False (money signals fail)
make verify-correct-fix   # real fix → verified=True
```

### Postmortem

```sh
python -m incident_agents publish --incident <id> --dry-run
python -m incident_agents publish --incident <id> --parent-page <notion-id>  # live
```

### Quality checks

```sh
make lint
make test
```

### Reset for a second run

```sh
sh -c 'pkill -f "[t]ools.shopper" || true; python -m tools.deploy rollback; find var -mindepth 1 -maxdepth 1 ! -name ".gitkeep" -exec rm -rf -- {} +; pkill -f "[u]vicorn checkout_svc.main:app" || true; nohup .venv/bin/python -m uvicorn checkout_svc.main:app --host 127.0.0.1 --port 8000 >/tmp/sre-incident-service.log 2>&1 & sleep 1; curl -s localhost:8000/healthz'
```

Then reopen the storefront and run `make shop`.

---

## Presenter notes

- Success rate settles at **62–68%** during the promo. Say "about two thirds."
- RED appears **15–25 seconds** after promo deploy (rolling window).
- Recovery to GREEN after rollback takes **~85 seconds** (60-second window hysteresis).
- If the shopper dies, the strip shows grey **NO TRAFFIC** — not falsely green.
- The $98 cart is the just-under-threshold control; $100 is the exact boundary.
- Run verifier commands in order: unfixed → wrong-fix → correct-fix.

See also: `DEMO.md` (on the agent-fleet branch) for the timed presenter script.
