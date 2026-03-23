# Institutional Sprint Runbook

## Objective
Drive the app to a verified institutional score of `9.0/10` by improving five gates:

1. Infrastructure Resilience
2. Risk Containment Strength
3. Alpha Durability
4. Audit Integrity
5. Execution and Operational Reliability

## Daily Process
1. Run the scorer:
   - `python ops/institutional_sprint_driver.py`
2. Review outputs:
   - `ops/institutional_daily_scorecard.json`
   - `ops/daily_reports/YYYY-MM-DD.md`
3. Prioritize work on the largest weighted gap.
4. Re-run scorer after fixes and keep one final score entry for the day.

## Strict Rules
- A score is evidence-based only (tests + code checks).
- Hard caps stay active until missing institutional evidence is implemented.
- Do not claim a gate reached 9 without removing its cap condition.

## Suggested Sprint Cadence
Day 1-2:
- Build and validate load/failure-injection harness for resilience gate cap removal.

Day 3-4:
- Build adversarial risk replay (regime flip, gap down, slippage expansion, correlation spike).

Day 5-6:
- Implement point-in-time fundamentals schema and ingestion (`as_of_date`) with tests.

Day 7-8:
- Add OMS reconciliation/idempotency lifecycle with explicit external ack states.

Day 9-10:
- Integrate Monte Carlo (1000-path) and forward degradation analysis into daily pipeline.

## Exit Criteria
- Composite score `>= 9.0`
- No gate cap active
- Full test suite green
- Daily reports show stable or improving trajectory for at least 5 consecutive days
