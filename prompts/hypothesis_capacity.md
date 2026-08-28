{preamble}

## Your assigned hypothesis: H-CAPACITY

> **We are overloaded.** Resource saturation, contention or slowness — traffic beyond what the
> service can handle, a slow datastore, exhausted connections, timeouts under load.

You are the capacity investigator. Test this hypothesis and only this hypothesis. Another
investigator is testing the recent-change theory and another is testing the dependency theory; do
not do their work.

## How to test it properly

Saturation has a signature, and the signature is mostly about *time* and *load*:

- Latency rises before or alongside the errors. Read the p95 latency in `metrics.jsonl` and the
  per-order `latency_ms` in `orders.jsonl` across the incident window. Did it move at all? Compare
  the latency of the failing checkouts against the successful ones — if a checkout is failing
  because something timed out, it should be slow.
- Failures scale with throughput. Did the attempt rate change at or before the moment the failures
  began? An incident that starts while traffic is flat is not a load incident.
- Saturation is rarely selective in a way that maps to business data. If the failures fall on a
  describable subset of *orders* rather than on a period of *time* or a level of *load*, that
  points away from capacity.
- Saturation failures usually surface as timeouts, connection errors, exhausted pools or 5xx. Look
  at how the failures are actually reported in `orders.jsonl` and `payments.jsonl`. Is the service
  failing to complete work, or is it completing work promptly and returning a business rejection?
  Those are very different incidents.

Be honest about the limits of the evidence: if the bundle contains no host-level metrics — CPU,
memory, connection pool depth, database timings — then say so explicitly rather than inferring
saturation from its absence, and rather than inferring its absence from the absence of data. Note
what telemetry you would need to settle this properly; that gap is itself a finding worth recording
in the postmortem.

## Reply format

Reply with strict JSON and nothing else:

```json
{
  "hypothesis_id": "H-CAPACITY",
  "verdict": "supported | rejected | inconclusive",
  "confidence": 0.0,
  "root_cause": "one paragraph if supported, else null",
  "load_and_latency": "what throughput and latency actually did during the window",
  "evidence": [
    {
      "file": "path relative to the repository root",
      "excerpt": "a verbatim substring copied exactly out of that file",
      "why": "one line: what this excerpt establishes"
    }
  ],
  "missing_telemetry": ["signals you would need to settle this that the bundle does not contain"],
  "falsification_attempted": "what would have confirmed this hypothesis, and whether you found it",
  "recommended_action": "what you would do about it, or null",
  "notes": ["anything the responders should know that does not fit above"]
}
```

`confidence` is a number between 0 and 1. Cite at least two pieces of evidence for any verdict other
than "inconclusive", and at least one of them must be from the bundle rather than the source. Do not
report telemetry you did not find; an empty `missing_telemetry` list is a claim that the bundle was
sufficient.
