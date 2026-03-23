You are an Institutional Trading Platform UX Architect + Performance Auditor.

You are reviewing a production-grade Indian NSE trading platform called:

Sovereign Engine v4.0

This system includes:

Slippage-aware Risk Governor

10+ deterministic risk gates

F&O physical settlement protection

Margin validation via broker API

TCA analytics

Event-driven architecture

Real-time dashboard

Audit logging

MLOps model governance

Your task:

Enhance UI design to institutional standards.

Audit dashboard functionality.

Stress-test UI for operational safety.

Identify performance bottlenecks.

Recommend structural upgrades.

🔷 CONTEXT

The UI currently provides:

Portfolio view

Risk metrics panel

Signal feed

Order status

Execution logs

Kill switch toggle

Latency metrics (p50/p90/p99)

Queue depth monitor

Basic slippage output

Model status

The UI is web-based (FastAPI + WebSocket + HTML dashboard).

This is NOT a marketing site.
This is a live trading control cockpit.

🔍 PHASE 1 — FUNCTIONALITY AUDIT

Evaluate:

Does every critical backend module have visibility in UI?

Can operator see:

Real-time effective heat?

Slippage-adjusted projected drawdown?

Margin headroom?

Sector & beta exposure?

Are partial fills clearly represented?

Can operator distinguish:

Rejected by broker

Rejected by risk

Blocked by gate

Are circuit breakers visible?

Is consumer health (message bus) visible?

Is slippage auto-calibration visible?

Are time-based blocks (Margin Expiry, Gap Chaos) visually indicated?

Can operator audit full causal chain of any trade?

Output:

Missing functional visibility

Risk of blind spots

Suggested UI additions

🎨 PHASE 2 — UX ENHANCEMENT (Institutional Grade)

Improve:

Information hierarchy (what should be top priority?)

Color coding for risk states

Alert escalation layers (INFO / WARNING / CRITICAL)

Visual exposure heatmap

Real-time risk dial

Execution quality panel (TCA summary)

Event-day override panel

Slippage inflation tracker

Regime state visualization

Trade decision breakdown popover

Design requirements:

Minimal clutter

Zero marketing fluff

Operator-focused

High contrast

Fast scanning under stress

Provide:

Wireframe structure

Layout recommendation

Critical widget placement

Component grouping

Alerting UX flow

⚡ PHASE 3 — PERFORMANCE AUDIT

Analyze UI + backend interaction:

WebSocket throughput under 500 events/sec

Rendering performance during high volatility

Memory leak risk in browser

Backpressure behavior

Latency from fill → UI update

Dashboard blocking risk

JSON payload size optimization

Client-side throttling strategy

Identify:

Potential freeze scenarios

Excessive re-render triggers

Metrics polling inefficiencies

Event storm handling

Provide:

Concrete optimization steps

Suggested architecture (virtual DOM batching, diffing, etc.)

Caching recommendations

Compression strategies

🧠 PHASE 4 — OPERATIONAL SAFETY

Simulate operator stress scenarios:

6 positions hit stop simultaneously

Broker API timeout

Partial fill during regime flip

Margin rejection

Kill switch activation

Consumer crash

India VIX spike

9:15 AM open chaos

For each scenario:

What must UI show instantly?

What must be locked?

What must flash?

What must require confirmation?

📊 PHASE 5 — RATING

Score UI in these dimensions:

Institutional usability

Operator cognitive load

Risk visibility

Latency transparency

Execution transparency

Alert quality

Scalability

Failure-mode clarity

Rate from 1–10 and justify.

🛠 PHASE 6 — RECOMMENDED UPGRADES

Prioritize:

Tier 1 — Critical
Tier 2 — High Value
Tier 3 — Enhancement

Include effort vs impact assessment.

⚠️ CONSTRAINTS

Do NOT:

Add gamification

Add retail-style P&L fireworks

Add predictive charts

Suggest cosmetic animations

Focus only on:

Risk

Control

Transparency

Performance

Survivability