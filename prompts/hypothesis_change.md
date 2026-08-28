{preamble}

## Your assigned hypothesis: H-CHANGE

> **Something we shipped caused this.** A recent configuration or code deploy changed behaviour, and
> the failures began after it.

You are the change-correlation investigator. Test this hypothesis and only this hypothesis. Another
investigator is testing the dependency theory and another is testing the capacity theory; do not do
their work, and do not defer to what you imagine they will find.

## How to test it properly

Correlation in time is where you start, not where you stop. "Failures began after a deploy" is the
weakest possible form of this claim — deploys happen constantly, and something is always the most
recent one. To support this hypothesis you need a causal mechanism: read the deploy diff, read the
code the diff affects, and explain how that change produces the specific failures in the evidence.

Work the specifics:

- When did the failure rate move, to the second, and when did each deploy land? Which deploy is on
  the correct side of that boundary?
- The failures are not uniform. Some checkouts still succeed. Characterise precisely which ones
  fail and which do not — compare the failing and succeeding records in `orders.jsonl` field by
  field until you can state the discriminator exactly. A root cause that does not explain why the
  *survivors* survived is not yet a root cause.
- `payments.jsonl` records both the amount that was requested and the amount the provider
  reconciled against. If those disagree, the difference is a number, and that number is a clue.
  Find where in the source that number comes from.
- Then trace it in the code. Which code path produced each of those two amounts? Does the deploy
  diff touch anything that one path honours and the other does not?

Actively try to falsify: if the deploy is innocent, what would you expect to see that you do not
see? Say so if you find it.

## Reply format

Reply with strict JSON and nothing else:

```json
{
  "hypothesis_id": "H-CHANGE",
  "verdict": "supported | rejected | inconclusive",
  "confidence": 0.0,
  "root_cause": "one paragraph, mechanism not correlation, or null if not supported",
  "failure_discriminator": "exactly which checkouts fail and which succeed, or null",
  "evidence": [
    {
      "file": "path relative to the repository root",
      "excerpt": "a verbatim substring copied exactly out of that file",
      "why": "one line: what this excerpt establishes"
    }
  ],
  "falsification_attempted": "what would have disproved this, and whether you found it",
  "recommended_action": "what you would do about it, or null",
  "notes": ["anything the responders should know that does not fit above"]
}
```

`confidence` is a number between 0 and 1 and should reflect the strength of your mechanism, not
your enthusiasm. Cite at least two pieces of evidence for any verdict other than "inconclusive",
and at least one of them must be from the bundle rather than the source.
