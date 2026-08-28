{preamble}

## Your assigned hypothesis: H-DEPENDENCY

> **The payment provider is the problem.** An external dependency is degraded, erroring, timing out
> or rejecting traffic, and our checkout is failing because of something outside our system.

You are the dependency investigator. Test this hypothesis and only this hypothesis. Another
investigator is testing the recent-change theory and another is testing the capacity theory; do not
do their work.

This is the hypothesis every on-call engineer reaches for first, because it is the one where the
problem is somebody else's. Hold it to the same standard you would hold a theory that blamed your
own team.

## How to test it properly

- What exactly does the provider say? `payments.jsonl` records the provider's decision and its
  reason for every attempt. A provider that is *down* looks nothing like a provider that is
  *declining* — the former produces timeouts, connection errors, 5xx and missing responses; the
  latter produces prompt, well-formed answers with a business reason attached. Which pattern is in
  the data?
- If the provider is answering promptly and consistently, that is strong evidence *against* this
  hypothesis, and you should say so plainly.
- Check the shape of the failure. A degraded dependency usually hurts traffic indiscriminately, or
  in proportion to load. Does the failure here fall randomly across checkouts, or does it fall on a
  specific, describable subset? If the failing set is describable in terms of *our* data rather
  than timing, the dependency is unlikely to be the cause.
- Look at latency in `metrics.jsonl` and in the per-order latency in `orders.jsonl`. A struggling
  dependency almost always shows up as elevated or erratic response times before or during the
  errors.
- Read the code path that talks to the provider (`checkout_svc/gateway.py`, `payments/`) and be
  precise in your report about what the integration actually is, including anything about it that
  limits what this evidence can prove.

If you reject this hypothesis, reject it with evidence — a rejection is as useful to the responders
as a confirmation, and it is only useful if it is grounded.

## Reply format

Reply with strict JSON and nothing else:

```json
{
  "hypothesis_id": "H-DEPENDENCY",
  "verdict": "supported | rejected | inconclusive",
  "confidence": 0.0,
  "root_cause": "one paragraph if supported, else null",
  "provider_behaviour": "what the provider actually did, in one or two sentences",
  "evidence": [
    {
      "file": "path relative to the repository root",
      "excerpt": "a verbatim substring copied exactly out of that file",
      "why": "one line: what this excerpt establishes"
    }
  ],
  "falsification_attempted": "what would have confirmed this hypothesis, and whether you found it",
  "recommended_action": "what you would do about it, or null",
  "notes": ["anything the responders should know that does not fit above"]
}
```

`confidence` is a number between 0 and 1. Cite at least two pieces of evidence for any verdict other
than "inconclusive", and at least one of them must be from the bundle rather than the source. A
confident rejection needs evidence exactly as much as a confident confirmation does.
