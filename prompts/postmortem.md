You are writing the incident postmortem for Northstar Goods and publishing it to the team's Notion
workspace. You have the Notion MCP server available; use it to create the page.

## Ground rules

1. **Every fact in this document comes from the record below.** Do not recompute a number, do not
   estimate one, and do not round one into a nicer shape. If something is not in the record, it is
   not known, and the correct thing to write is that it is not known.
2. **No blame.** Name systems, changes and gaps in tooling; do not name a person as the cause. The
   deploy actor appears in the record because it is part of the timeline, not because they are at
   fault — a system in which one routine config change can take out checkout is a system problem.
3. **Write for two audiences at once.** An executive reads the summary and the customer impact and
   stops there; those must stand alone and be free of jargon. An engineer reads the rest and needs
   the mechanism precisely.
4. **The verification verdict is not yours to characterise.** It was produced by an independent
   harness, not by an agent. Report it exactly as given, including a rejection. If the fix was
   rejected, the postmortem says so — a postmortem that claims a resolution the verifier refused is
   worse than no postmortem.

## The record

### Alert and impact
{alert}

### Timeline
{timeline}

### Investigation: three independent hypotheses
{hypotheses}

### Incident commander's decision
{decision}

### Remediation
{remediation}

### Independent verification
{verification}

## The document

Create one Notion page under parent page `{parent_page_id}`, titled
`Incident {incident_id} — checkout failures after promotion deploy`, with these sections:

- **Summary** — three or four sentences. What broke, for whom, for how long, and whether it is
  resolved.
- **Customer impact** — in business terms and with the real numbers: how many checkout attempts
  failed, over what period, and what a customer experienced. State plainly that no error was shown
  to operators and the service reported itself healthy throughout, because that is the point.
- **Detection** — what fired, how long after the change, and what did *not* fire. Be explicit that
  process health checks stayed green: this incident was only visible in business metrics.
- **Timeline** — a table: time, event, source. Include the deploy, the first failure, the alert, the
  investigation, the fix and the verification.
- **Root cause** — the mechanism, precisely, including why some checkouts succeeded and others did
  not. An engineer who has never seen this codebase should be able to read this section and
  understand exactly how the two amounts diverged.
- **Hypotheses considered** — a table of all three, with each verdict and one line of the evidence
  that supported or rejected it. Do not hide the rejected ones: they are how we know the accepted
  cause was not simply the first idea anybody had.
- **What went wrong beyond the bug** — the contributing factors. The duplicated arithmetic, the
  absence of any check that the quote and the authorization agree, the fact that a pricing change
  could ship without exercising the payment path, and any telemetry the investigators reported as
  missing.
- **Mitigation and remediation** — what stopped the bleeding, and what actually fixed it, with the
  pull request link.
- **Verification** — what was checked, by what, and the verdict. Name the specific signals.
- **Action items** — a checklist. Each item concrete, each with a rationale that traces to something
  in this document. Include at least one that would have caught this *before* deploy and one that
  would have detected it faster.

## Reply format

After the page exists, reply with strict JSON and nothing else:

```json
{
  "published": true,
  "page_url": "the Notion URL of the page you created",
  "page_id": "the Notion page id",
  "sections_written": ["..."],
  "facts_unavailable": ["anything the record did not contain that the template asked for"]
}
```

If publishing fails, reply with `"published": false` and a `"error"` field describing what the
Notion API rejected. Do not invent a page URL under any circumstances.
