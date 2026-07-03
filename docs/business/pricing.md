# Pricing — the current anchors (pre-PMF; no decision recorded)

> **Status: there is no canonical pricing decision.** Three different price anchors appear across the
> business docs; this page reconciles them so none is mistaken for a decision. The pricing call is
> **pending the Tehran discovery wave** ([interview-kit.md](interview-kit.md) §H tests
> willingness-to-pay) — and Tehran WTP over-indexes the national market, so even that wave sets
> Tehran-segment anchors only (interview-kit §1.6).

## The three anchors on record

| Anchor | Basic | Pro | Unit | Source & basis |
|---|--:|--:|---|---|
| Minimum profitable @ 80% GM | ~$29 | ~$50 | per **clinic** / mo | [compute-cost-model.md](compute-cost-model.md) §7 — June COGS model (gemini-lite, deterministic report) |
| Interview test anchors (H11) | $15 | $30 | per **clinic** / mo + per-extra-doctor fee | [interview-kit.md](interview-kit.md) §H Q25 + hypothesis H11 — deliberate low probes for the Tehran wave |
| AI-budget working price | — | $15 | per **seat** / mo | [ai-usage-limits.md](ai-usage-limits.md) §3 — assumes a $15/seat Pro price; the $10/seat monthly AI budget is ~67% of it |

Note the **unit smear**: the cost model prices per clinic, the interview anchor is per clinic plus a
per-seat fee, and the usage-limit system reasons per seat (at the modeled 2 aesthetics seats,
$15/seat ≈ the $30/clinic test anchor). Interview Q26 explicitly tests which unit feels fair; the
decision must settle on one.

## Do the test anchors clear cost?

Measured COGS ([ai-usage-limits.md](ai-usage-limits.md)) came in **below** what the June model's
80%-GM prices imply, so the low interview anchors still clear break-even — but not the 80% target:

- **Basic $15/clinic** vs. COGS ≈ $5.7 (infra only, unchanged) → **~62% GM**.
- **Pro $30/clinic** (or $15 × 2 seats) vs. measured AI at today's per-capture synthesis
  (typical ≈ $9.0, heavy ≈ $19.7 per clinic/mo) + infra ≈ $5.9 → **~50% GM typical**, thinning
  toward break-even for heavy clinics — which is exactly what the $10/seat AI budget cap bounds.
  With the synthesis debounce enabled (~8.8× synthesis cut, built but off — ai-usage-limits §5),
  typical Pro COGS drops to ≈ $9.9 → **~67% GM**.

So the test anchors sit at roughly **50–65% gross margin** — profitable on compute, **short of the
80% target** that funds support/sales/humans (compute-cost-model §7). Two further honesty notes:
the GMs above assume the 50-clinic fixed-compute amortization (a small alpha fleet runs materially
lower), and the debounce is recorded COGS headroom, not yet realized.

## What decides it

The Tehran wave's WTP readout (Van Westendorp band + reactions to the $15/$30 + per-seat probe)
against the measured-COGS floor. Until then: treat every number above as a **working anchor**, cite
this page rather than any single figure, and do not present the interview probes as list prices.
