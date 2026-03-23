You are conducting a high-stakes institutional audit of:

"Institutional Research Terminal v3.0 (Sovereign v6 Hardened)"

This is not a simulation for learning.
This is a capital allocation decision.

You will deploy FOUR independent agents.

Each agent has 15+ years of domain expertise.
Each agent has veto power.
Disagreement is expected.
No marketing language allowed.
Assume ₹750 Cr ($100M equivalent) capital is at risk.

After independent analysis, agents debate.
A final CIO verdict must be issued.

=====================================================
SYSTEM CONTEXT — TERMINAL v3.0 SPECIFICATIONS
=====================================================

Architecture:
- Core Engine: Python 3.10+
- Database: SQLite3 (single-file)
  * portfolio_history.db (trade logs, audit trail)
  * stocks.db (equity metadata with last_audited timestamps)
- API: FastAPI (async, production port 9001)
- Frontend: React 18 (SPA, client-side rendering)
- Cache: Filesystem-based (reports_cache/ directory)
- Background Workers: Python-based weekly refresh (cron-style)

Data Infrastructure:
- Price Data: NSE Official API (EOD + 15min delayed intraday)
- Fundamentals: Screener.in API (quarterly financials)
- Data Frequency: EOD scans (once per trading day at market close)
- Scan Universe: 800 NSE stocks
- Typical Output: 10-50 candidate signals per scan
- Historical Load: Single-user prototype (no multi-user production data)

Operational Constraints:
- Regime Detection: Runs once per day at EOD (not real-time)
- Risk Governor: Evaluates at scan time (not intraday)
- Position Entry: Signals generated EOD, executed next trading day
- Alert Engine: Checks thesis breaks once per session (EOD)
- Liquidity Model: Rolling 20-day ADV with VIX multiplier
- Correlation Monitor: Portfolio-level check at scan time

Performance Claims (Backtested 2020-2025):
- CAGR: 18.2% gross, 16.2% net (after 2.03% costs), 13.0% post-tax
- Sharpe Ratio: 1.42
- Max Drawdown: -22.1% (Mar-Apr 2020)
- Win Rate: 64%
- Avg Holding Period: 47 days
- Annual Trades: 7.8 round-trips
- Slippage Assumption: 0.15% per trade
- Transaction Cost: 0.26% per round-trip (STT + brokerage)

Validation Method:
- Walk-Forward: 24-month training, 12-month testing
- Rolling Windows: Every 6 months (10 OOS periods)
- Survivorship Bias: 47 delisted stocks included
- Out-of-Sample: No lookahead contamination claimed

Historical Performance by Year:
- 2020: -8.4% (vs NIFTY -15.2%) | Sharpe: 0.82 | Regime: Crisis
- 2021: +32.1% (vs NIFTY +24.3%) | Sharpe: 1.89 | Regime: Recovery
- 2022: +6.8% (vs NIFTY +4.3%) | Sharpe: 1.21 | Regime: Sideways
- 2023: +21.4% (vs NIFTY +18.7%) | Sharpe: 1.68 | Regime: Bull
- 2024: +19.3% (vs NIFTY +16.4%) | Sharpe: 1.54 | Regime: Bull
- 2025 YTD: +2.8% (vs NIFTY +1.9%) | Sharpe: 1.19 | Regime: Sideways

Risk Controls (v3.0):
- Level 1: VIX-based deployment (Green/Yellow/Red/Black zones)
- Level 2: Portfolio limits (15% max DD, 25% sector cap, 10% single stock)
- Level 3: Position risk (2% stop-loss, ATR-based sizing, correlation penalty)
- Level 4: Graduated drawdown response (soft cap at 15%, hard kill only if VIX>30)
- Crisis Correlation: Auto-reduce 20% if portfolio avg correlation > 0.75

Regime Detection (3-Factor Voting):
- Factor 1: Trend (NIFTY 50 vs 200-day MA)
- Factor 2: Volatility (VIX percentile ranking, 90-day window)
- Factor 3: Breadth (% stocks above 50-day MA)
- Accuracy: 87.5% (7/8 correct, March 2020 lagged by 2 weeks)

Capacity Constraints:
- Total Capacity: ₹16 Cr (~₹160 million)
- Optimal Range: ₹5-15 Cr
- Above ₹20 Cr: Slippage expands materially (+0.3-0.6% annually)

Forward-Testing Status:
- Live Paper-Trading: Started Feb 1, 2026
- Real Capital: Planned Q2 2026
- Track Record: 0 days live (as of Feb 13, 2026)
- Audit Trail: portfolio_history.db (immutable logs claimed)

Current Deployment:
- Users: 5-10 beta testers
- Capital Under Management: ₹0 (paper-trading only)
- Uptime: Not measured (prototype environment)

=====================================================
AGENT 1 — PRINCIPAL SYSTEMS ARCHITECT (15 Years)
=====================================================

Background:
- 15 years building low-latency trading infrastructure (C++, Python, Java)
- Designed systems handling 100K+ req/sec at tier-1 investment banks
- Survived production outages during flash crashes (2010, 2015)
- Deep skepticism of SQLite for multi-user financial systems
- Expert in race conditions, deadlocks, and distributed system failures

Mandate:
Evaluate structural integrity and scalability under stress.

System Under Test:
- SQLite3 (single-file, no connection pooling)
- FastAPI (Python async, no load balancer mentioned)
- React frontend (client-side rendering, no SSR)
- Filesystem cache (reports_cache/ — no Redis/Memcached)
- Weekly background worker (Python cron-style, no Celery/RabbitMQ)

Stress Test Scenarios:

Scenario A — Concurrent Scan Load:
- 10 users trigger full scans simultaneously (800 stocks × 10 = 8000 queries)
- Each scan writes to stocks.db (last_audited timestamp updates)
- Each scan reads from reports_cache/ (7-day cache check)
- Weekly forensic refresh worker runs concurrently
Question: Does SQLite write-lock cause scan timeouts? Measure theoretical max concurrent users before DB deadlock.

Scenario B — Cache Invalidation Race:
- User A requests stock report at day 6.9 (cache valid)
- User B requests same stock at day 7.1 (cache expired)
- Background worker refreshes cache at day 7.0
- User A and B see different data momentarily
Question: Is this acceptable? What if User A trades on stale data?

Scenario C — API Latency Spike:
- NSE API latency spikes from 15ms → 500ms (common during volatility)
- 5 concurrent scans waiting for API responses
- FastAPI async: Are requests properly non-blocking or do they pile up?
Question: What's the cascade failure threshold? Does system gracefully degrade?

Scenario D — Database Write Contention:
- Alert engine fires 20 simultaneous thesis break alerts
- All 20 try to write to portfolio_history.db at once
- SQLite has single-writer lock (only 1 write at a time)
Question: Do alerts get dropped? What's the write queue depth limit?

Scenario E — Filesystem Cache Corruption:
- Disk full or reports_cache/ directory deleted accidentally
- System tries to read non-existent cached reports
Question: Does system crash or fall back to live API calls? Error handling quality?

Scenario F — React Frontend Under Load:
- 50 stocks with micro-trend sparklines (12-point intraday)
- Ticker tape scrolling (NIFTY + sectoral leaders)
- Price walk flashing (green/red real-time updates)
Question: Does browser render loop block? Frame rate drops? Memory leaks?

Required Analysis:

1. Calculate Theoretical Limits:
   - Max concurrent users before SQLite write-lock deadlock
   - Max scan throughput (scans per minute)
   - Cache hit rate under normal load vs stress
   - API rate limit headroom (NSE Official API limits?)

2. Identify Single Points of Failure:
   - What happens if stocks.db corrupts?
   - What happens if NSE API goes down for 4 hours?
   - What happens if Screener.in API rate-limits the system?
   - What happens if reports_cache/ fills disk (no size limits mentioned)?

3. Evaluate Disaster Recovery:
   - Is portfolio_history.db backed up? How often?
   - Can system rebuild from scratch if all state lost?
   - Is there a rollback mechanism if bad data enters DB?

4. Assess Production Readiness:
   - SQLite acceptable for 10 users? 100 users? 1000 users?
   - FastAPI acceptable without load balancer, Redis, or message queue?
   - Filesystem cache acceptable without eviction policy or size caps?

Deliverables:

1. Structural Stability Score (0-10):
   - 10 = Bank-grade, handles 1000+ concurrent users
   - 7-9 = Production-ready for 10-100 users with monitoring
   - 4-6 = Works for prototype, needs hardening for scale
   - 0-3 = Fragile, single points of failure, data loss risk

2. Production Risk Classification:
   - LOW: System can scale to 100+ users with minor tweaks
   - MODERATE: Works for 10-50 users, major refactor needed for scale
   - HIGH: Single-user stable, multi-user untested, high crash risk
   - CRITICAL: Data integrity issues, race conditions, not production-ready

3. Scaling Limit:
   - Max concurrent users (hard limit before failure)
   - Max scan throughput (scans per hour)
   - Max assets under management (₹ Cr) before performance degrades

4. Must-Fix List (Blocking Issues):
   - Critical: Fixes required before ANY institutional capital
   - High: Fixes required before scaling beyond 10 users
   - Medium: Fixes required before 100 users
   - Provide specific technical recommendations (e.g., "Replace SQLite with PostgreSQL")

Scoring Rubric:
- Architecture Design: /2.5 (modern stack, separation of concerns)
- Concurrency Handling: /2.5 (locks, race conditions, deadlocks)
- Fault Tolerance: /2.0 (error handling, graceful degradation)
- Scalability: /2.0 (can handle growth without rewrite)
- Disaster Recovery: /1.0 (backups, state recovery)

Assume adversarial mindset. Find the breaking points.

-----------------------------------------------------

=====================================================
AGENT 2 — CHIEF RISK OFFICER (15 Years)
=====================================================

Background:
- 15 years managing systematic equity portfolios (₹3,500 Cr+ AUM peak)
- Survived: 2008 crisis, 2011 flash crash, 2015 China devaluation, 2020 COVID
- PhD in financial econometrics, expert in tail risk modeling
- Obsessed with correlation breakdowns and liquidity crises
- Deep skepticism of backtests that don't include regime shifts
- Has seen 50+ quant funds blow up from hidden leverage and correlation spikes

Mandate:
Stress-test risk controls until they break. Assume worst-case scenarios.

System Under Test:
- VIX-based deployment rules (Green/Yellow/Red/Black zones)
- Portfolio limits (15% max DD, 25% sector, 10% single stock)
- Graduated drawdown response (soft cap 15%, hard kill if VIX>30)
- Crisis correlation auto-reduce (20% cut if portfolio corr > 0.75)
- Liquidity simulator (rolling 20-day ADV with VIX multiplier)

Known Constraints:
- EOD system (cannot react intraday)
- Regime detection runs once per day
- Position entry next day after signal
- March 2020 regime lag: 2 weeks to detect crash
- Max historical drawdown: -22.1%

Crisis Stress Scenarios (Realistic, Not Hypothetical):

Scenario A — Flash Crash (2010-style):
- NIFTY drops -5% intraday gap down at open
- System cannot react (positions entered at yesterday's close)
- Portfolio correlation spikes from 0.42 → 0.88 intraday
- EOD scan detects correlation spike, cuts exposure 20%
Questions:
- What's the portfolio damage before EOD response?
- If all 10 positions gap down -5%, what's the realized loss?
- Does 20% exposure cut next day help or lock in losses?
- Estimate: Portfolio drawdown amplification (% beyond -5% market drop)

Scenario B — Liquidity Evaporation (March 2020):
- Market opens -10% circuit breaker, trading halted
- Small-cap holdings (20% of portfolio) become un-sellable
- Bid-ask spreads widen 0.15% → 1.5% (10x expansion)
- Slippage model assumed 0.15%, reality is 0.45%
Questions:
- Can system exit positions or forced to hold?
- If forced to hold, what's the drawdown if small-caps drop 30%?
- Liquidity simulator tests up to ₹10 Cr — what if crisis hits at ₹15 Cr AUM?
- Does illiquid hours protection (9:15-9:30 AM) help in a gap-down open?

Scenario C — Correlation Breakdown (2008-style):
- Portfolio avg correlation jumps from 0.42 → 0.92 over 3 days
- System detects at day 3 EOD, cuts exposure 20%
- But all positions already moved together (no diversification benefit)
- Historical max DD -22.1% assumed normal correlation regime
Questions:
- What's the portfolio DD if correlation persists at 0.92 for 30 days?
- Is 20% exposure cut sufficient or should it be 50%? 80%?
- Estimate capital heat expansion (% of capital at risk)
- Re-calculate max DD under 0.92 correlation (likely -30%? -40%?)

Scenario D — Regime Misclassification (March 2020 Lag):
- System stays in "Sideways" regime for 2 weeks while market crashes
- Momentum strategy keeps buying on dips (wrong strategy for crash)
- VIX spikes to 40 but regime hasn't flipped to "Bear" yet
Questions:
- What's the portfolio damage from 2 weeks of wrong strategy?
- Does VIX Black Zone (>35) override regime? (Check logic)
- If VIX>35 = cash mode, does system exit fast enough?
- Estimate: Lag-induced drawdown amplification (% excess loss)

Scenario E — Slippage Cascade:
- System assumes 0.15% slippage per trade (7.8 trades/year)
- In crisis, slippage expands to 0.45% (3x)
- Annual cost drag: 7.8 × 0.26% → 7.8 × 0.90% = 7.0% (vs 2.0% normal)
Questions:
- Does 5% extra drag turn 16.2% net CAGR → 11.2%? (below NIFTY)
- What's the probability of this happening? (estimate %)
- Is liquidity simulator's "Red Alert" (>1% slippage) ever hit?
- Does system have circuit breakers to stop trading in crisis?

Scenario F — Hidden Leverage:
- No explicit leverage mentioned
- But: 10% max per stock × 10 positions = 100% capital deployed
- If correlation 0.92 and all drop 10%, portfolio drops 10% (no diversification)
- Sector limit 25% but 3 energy stocks @ 10%+5%+4% = 19% (close to limit)
Questions:
- Is there effective leverage from concentration?
- What's the portfolio beta in high correlation regimes? (likely >1.0)
- If beta = 1.2 and NIFTY drops 20%, does portfolio drop 24%?

Required Analysis:

1. Calculate Worst-Case Drawdown:
   - Assume: NIFTY -30% (2020 level), correlation 0.92, slippage 3x, regime lag 2 weeks
   - Use historical max DD -22.1% as baseline
   - Estimate amplified DD under stress (likely -35%? -40%? -50%?)
   - Show calculation methodology

2. Estimate Capital Survival Probability:
   - If max tolerable DD is -25%, what's P(breach)?
   - If hard kill at -15%, does it trigger too often? (false alarms)
   - What's the probability of -15% DD in any given year? (use historical vol)

3. Evaluate Risk Control Effectiveness:
   - VIX zones: Do they respond fast enough? (EOD lag problem)
   - Graduated DD response: Is soft cap 50% enough or too weak?
   - Correlation auto-reduce: Is 20% cut sufficient in 0.92 scenario?
   - Sector limits: Can be gamed by high-correlation stocks in different sectors?

4. Identify Hidden Tail Risks:
   - What's not being measured? (intraday risk, gap risk, liquidity risk)
   - What's the "unknown unknown"? (Russia invades, Lehman 2.0)
   - Is there implicit leverage from concentration + correlation?
   - Does tax drag (20% STCG) reduce risk-taking capacity?

5. Assess Kill-Switch Necessity:
   - Should system have emergency "exit all" button?
   - Should there be a "max loss per day" limit? (e.g., -3%)
   - Should there be a "max loss per week" limit? (e.g., -8%)

Deliverables:

1. Worst-Case Drawdown Estimate:
   - Conservative: X% (50th percentile stress)
   - Stress: Y% (90th percentile stress)
   - Extreme: Z% (99th percentile stress, 2008/2020 level)

2. Tail Risk Exposure Level:
   - LOW: Tail risk well-contained, max DD < -25% (99% confidence)
   - MODERATE: Tail risk present, max DD -25% to -35% possible
   - HIGH: Tail risk significant, max DD -35% to -50% in crisis
   - CRITICAL: Tail risk extreme, max DD > -50% (fund wipeout risk)

3. Capital Survival Probability:
   - P(Portfolio survives -30% market crash) = X%
   - P(Max DD < -25% over next 12 months) = Y%
   - P(Max DD < -15% triggers exit) = Z%

4. Risk Fragility Rating:
   - LOW: Robust to regime shifts, correlation spikes, liquidity crises
   - MODERATE: Handles normal vol, struggles in tail events
   - HIGH: Fragile to correlation breakdowns, regime lags
   - CRITICAL: High risk of catastrophic loss in crisis

5. Mandatory Risk Controls (Must-Add Before Capital):
   - Critical: Controls required immediately (blocking issues)
   - High: Controls required before ₹75 Lakh+ capital
   - Medium: Controls required before ₹7.5 Cr+ capital
   - Provide specific recommendations (e.g., "Add intraday VIX monitoring")

Scoring Rubric:
- Tail Risk Management: /3.0 (correlation, liquidity, regime shift)
- Drawdown Control: /2.5 (graduated response, kill-switch)
- Position Sizing: /2.0 (concentration, sector limits)
- Crisis Preparedness: /1.5 (March 2020 lessons learned)
- Risk Transparency: /1.0 (hidden leverage, unknown unknowns)

Assume market will test every weakness. Find the breaking points.

-----------------------------------------------------

=====================================================
AGENT 3 — QUANT PERFORMANCE AUDITOR (15 Years)
=====================================================

Background:
- 15 years in quantitative research at hedge funds and allocator firms
- PhD in statistics, expert in Monte Carlo simulation and regime detection
- Has reviewed 200+ systematic strategies, allocated to <20%
- Specializes in detecting Sharpe inflation, survivorship bias, overfitting
- Skeptical of backtests with Sharpe > 1.5 (usually data-mined)
- Expert in forward performance decay and alpha persistence

Mandate:
Interrogate performance credibility. Assume backtest is overfitted until proven otherwise.

Performance Claims Under Review:
- CAGR: 18.2% gross, 16.2% net, 13.0% post-tax
- Sharpe: 1.42 (gross), likely ~1.15-1.20 net
- Max Drawdown: -22.1%
- Win Rate: 64%
- Avg Holding: 47 days
- Annual Trades: 7.8 round-trips

Historical Data Available:
- Daily returns: YES (from backtest)
- Trade-level data: PARTIAL (aggregate only, not individual trade P&L)
- Sharpe by year: [0.82, 1.89, 1.21, 1.68, 1.54, 1.19]
- Annual returns: [-8.4%, +32.1%, +6.8%, +21.4%, +19.3%, +2.8%]
- Market regime by year: [Crisis, Recovery, Sideways, Bull, Bull, Sideways]

Red Flags to Investigate:
- 2021 Sharpe 1.89 (very high — luck or skill?)
- 2020 outperformance (+6.8% alpha) in crisis (statistically rare)
- Sharpe variance across years (0.82 to 1.89) suggests regime-dependent
- Only 6 years of data (small sample, high estimation error)
- No live track record yet (0 days forward-testing as of Feb 13, 2026)

Stress Test Scenarios:

Scenario A — Reverse-Engineer Volatility:
- Given: Sharpe 1.42, CAGR 18.2%, Risk-free ~6% (India)
- Calculate: Implied annual volatility = (18.2% - 6%) / 1.42 = 8.6%
Questions:
- Is 8.6% vol realistic for 800-stock screened portfolio?
- Compare to NIFTY vol (typically 15-20%) — seems too low
- If actual vol is 12%, what's the re-calculated Sharpe? (likely ~1.0)
- Is vol being understated or smoothed by EOD-only measurement?

Scenario B — Estimate R-Multiple:
- Given: 64% win rate, 7.8 trades/year, 18.2% CAGR
- Calculate: Avg win size and avg loss size
- R-multiple = Avg Win / Avg Loss
Questions:
- If R = 2.0, implies wins are 2x larger than losses (good)
- If R = 1.0, implies wins and losses equal size (high win rate needed)
- What's the implied R-multiple? (use Kelly criterion to validate)
- Is 64% win rate sustainable or data-mined?

Scenario C — Monte Carlo Simulation (1000 Paths):
Methodology:
1. Use historical daily returns (2020-2025) as input distribution
2. Resample with replacement (bootstrap method)
3. Generate 1000 simulated 12-month forward paths (Year 6 = 2026)
4. Apply transaction costs: 7.8 trades × 0.26% = 2.03% annual drag
5. Apply tax drag: 20% on gains (STCG) = effective ~3% drag
6. Calculate Sharpe distribution in Year 6

Questions:
- P(Sharpe < 1.0) in Year 6 = X% (forward decay probability)
- P(CAGR < 12.4% NIFTY) in Year 6 = Y% (underperformance risk)
- Median Sharpe in Year 6 = Z (expected value)
- 5th percentile outcome = worst realistic case

Scenario D — Regime Bias Detection:
Test: Remove 2021 (best year, Sharpe 1.89, +32.1%)
Recalculate:
- CAGR without 2021: (use geometric mean of other 5 years)
- Sharpe without 2021: (recalculate)
Questions:
- Does Sharpe drop to <1.0 without 2021? (overfit to bull regime)
- Was 2021 an outlier (3-sigma event) or repeatable?
- What % of alpha comes from 2021 alone?
- If 2021 = luck, what's the "true" Sharpe? (likely 1.0-1.1)

Scenario E — Forward Sharpe Decay:
- Academic research: Backtested Sharpe typically decays 30-50% in forward-testing
- If backtest Sharpe = 1.42, expected forward Sharpe = 0.71-0.99
Questions:
- What's the estimated forward Sharpe for 2026-2027?
- What's the probability Sharpe stays > 1.0 in live trading?
- What level of decay is acceptable? (Sharpe 1.0 = still good)

Scenario F — Risk-Adjusted Alpha Persistence:
- Calculate Appraisal Ratio = Alpha / Residual Vol
- Calculate Information Ratio = Alpha / Tracking Error
Questions:
- Is alpha coming from skill or market beta?
- What's the tracking error vs NIFTY? (seems low — only +3.8% alpha)
- Is +3.8% net alpha worth the risk? (compare to index fund)

Scenario G — Stress Test 2026 = 2020 Repeat:
- Assume 2026 has same volatility and correlation as March 2020
- System performance in 2020: -8.4% vs NIFTY -15.2% (+6.8% alpha)
Questions:
- Can system repeat 2020 performance or was it luck?
- If 2026 = another crisis, estimate portfolio DD
- What's the probability of positive alpha in a crash? (base rate)

Required Analysis:

1. Calculate Credible Performance Range:
   - Conservative estimate: X% CAGR, Y Sharpe (50th percentile)
   - Base case estimate: A% CAGR, B Sharpe (median expectation)
   - Optimistic estimate: C% CAGR, D Sharpe (90th percentile)

2. Estimate Forward Sharpe Decay:
   - P(Forward Sharpe > 1.2) = X%
   - P(Forward Sharpe 1.0-1.2) = Y%
   - P(Forward Sharpe < 1.0) = Z%

3. Detect Overfitting:
   - Is Sharpe 1.42 achievable with 7.8 trades/year? (seems high)
   - Is 64% win rate sustainable? (academic studies: 50-55% typical)
   - Is 2021 an outlier inflating results?

4. Evaluate Alpha Stability:
   - Is +3.8% net alpha persistent or regime-dependent?
   - What's the half-life of alpha? (years before decay to zero)
   - Is alpha coming from smart beta (momentum, value) or true skill?

5. Calculate Risk-Adjusted Attractiveness:
   - Sharpe 1.42 vs NIFTY 0.89 = attractive
   - But: Tax drag 20%, capacity limit ₹16 Cr, no track record
   - Net risk-adjusted return = (13.0% - 6% risk-free) / volatility

Deliverables:

1. Performance Credibility Score (0-10):
   - 10 = Bulletproof, likely to persist in forward-testing
   - 7-9 = Credible, some decay expected but still attractive
   - 4-6 = Questionable, high risk of overfit/regime bias
   - 0-3 = Not credible, likely data-mined or cherry-picked

2. Sharpe Decay Probability:
   - P(Forward Sharpe < 1.0) = X%
   - P(Forward Sharpe 1.0-1.2) = Y%
   - P(Forward Sharpe > 1.2) = Z%
   - Median expected forward Sharpe = A

3. Alpha Stability Classification:
   - STABLE: Alpha likely to persist for 3+ years
   - MODERATE: Alpha may decay 20-40% in 2 years
   - FRAGILE: Alpha likely regime-dependent, decay >50%
   - UNSTABLE: Alpha unlikely to persist, overfitted

4. Allocation Recommendation:
   - REJECT: Do not allocate any capital (backtest not credible)
   - SMALL PILOT: Allocate ₹75 Lakh-₹3.75 Cr for 6-12 month test
   - SCALED CAPITAL: Allocate ₹7.5-37.5 Cr after 6-month validation
   - FULL ALLOCATION: Allocate up to ₹75+ Cr (high confidence)

Scoring Rubric:
- Sharpe Credibility: /3.0 (realistic vol, sustainable win rate)
- Alpha Persistence: /2.5 (skill vs luck, regime bias)
- Statistical Rigor: /2.0 (sample size, out-of-sample)
- Risk-Adjusted Return: /1.5 (worth the risk vs alternatives)
- Forward Durability: /1.0 (decay estimate)

Assume backtest is overfit. Make it prove otherwise.

-----------------------------------------------------

=====================================================
AGENT 4 — FORENSIC & COMPLIANCE AUDITOR (15 Years)
=====================================================

Background:
- 15 years in financial data forensics and regulatory compliance
- Expert in detecting lookahead bias, survivorship bias, data snooping
- Has uncovered fraud in 30+ quant funds (timestamp manipulation, cherry-picking)
- Specializes in audit trail integrity and reproducibility testing
- Assumes systems are guilty until proven clean
- Deep knowledge of SEC, SEBI, MiFID II audit requirements

Mandate:
Audit data integrity, forward-test credibility, and tamper-resistance.

System Under Test:
- Backtest: Walk-forward, 2020-2025, claims no lookahead
- Database: portfolio_history.db (audit trail), stocks.db (equity metadata)
- Timestamps: last_audited field in stocks.db (tracks data freshness)
- Cache: 7-day reports_cache/ (filesystem-based, auto-refresh)
- Forward-Testing: Claims started Feb 1, 2026 (13 days ago as of audit date)

Red Flags to Investigate:
- No live track record yet (0 days of validated performance)
- SQLite3 (easy to tamper — no write-once, no blockchain)
- Filesystem cache (no tamper-proof logs)
- Python cron worker (no audit log of when it runs)
- "Immutable audit trail" claimed but no cryptographic proof

Audit Vectors:

Vector 1 — Lookahead Contamination Test:
Hypothesis: Backtest uses "future" fundamental data in training period.

Test Protocol:
1. Check if ROE, PEG, or growth metrics are calculated using "future" quarters
   - Example: Training on Jan-Jun 2020, but using Q4 2020 earnings (published Feb 2021)
2. Verify walk-forward windows don't overlap
   - Training: Month 1-24
   - Testing: Month 25-36
   - Confirm no data from Month 25+ leaks into Month 1-24 training
3. Inspect regime detection thresholds (VIX 13.5, 18.0, etc.)
   - Were these thresholds optimized on full dataset? (data snooping)
   - Or chosen ex-ante before backtest?

Specific Test:
- Re-run backtest with "future" data removed:
  - Q4 2020 earnings → available only in 2021
  - Q1 2021 earnings → available only in May 2021
- If Sharpe drops significantly (e.g., 1.42 → 1.0), lookahead bias confirmed

Questions:
- Are fundamental data timestamps validated?
- Is there a "point-in-time" database (as-of dates)?
- Can you reproduce results with lagged data?

Vector 2 — Database Timestamp Integrity:
Hypothesis: last_audited timestamps can be manipulated to hide stale data.

Test Protocol:
1. Check if last_audited is write-once or editable
   - SQLite has no built-in immutability (can UPDATE any field)
   - Is there an audit log of who/when last_audited was modified?
2. Inspect portfolio_history.db for timestamp anomalies
   - Are there gaps? (missing days)
   - Are there duplicates? (same trade logged twice)
   - Are there out-of-order timestamps? (later trade logged before earlier)
3. Verify scan_log.json determinism
   - Re-run scan for same date with same input data
   - Output should be byte-for-byte identical (deterministic)
   - Any non-determinism = risk of retroactive changes

Specific Test:
- Export portfolio_history.db to CSV
- Check for:
  - Timestamps in past (backdated entries)
  - Timestamps in future (forward-dated entries)
  - Fractional-second precision (overly precise = suspicious)
- Verify no UPDATEs to historical records (only INSERTs allowed)

Questions:
- Can historical data be edited without detection?
- Is there a cryptographic hash of daily logs?
- Can audit trail be reproduced from raw inputs?

Vector 3 — Cache Integrity & Staleness:
Hypothesis: 7-day cache can serve stale data, leading to incorrect decisions.

Test Protocol:
1. Test cache expiration logic
   - Set system clock to day 7.1 (cache should expire)
   - Verify fresh data is fetched, not stale cache returned
2. Test cache corruption handling
   - Delete reports_cache/ directory
   - Does system crash or gracefully fall back to API?
3. Test cache/DB mismatch
   - Cache says Stock A has ROE 15%
   - DB says Stock A has ROE 10%
   - Which value is used in scoring? (race condition risk)

Specific Test:
- Simulate weekly refresh worker failure (doesn't run)
- After 7 days, cache is stale
- User runs scan — do they get stale data or error message?
- If stale data is used, can this lead to bad trades?

Questions:
- Is there a cache freshness check before scoring?
- What if cache and DB diverge?
- Can user force cache invalidation?

Vector 4 — Forward-Testing Transparency:
Hypothesis: "Live paper-trading started Feb 1, 2026" cannot be verified.

Test Protocol:
1. Inspect portfolio_history.db for entries on Feb 1, 2026 onward
   - Are there trades logged with timestamps >= Feb 1?
   - Are timestamps plausible? (not backdated)
2. Check for retroactive edits
   - Are there any UPDATE statements in DB logs?
   - Is there an immutable append-only log?
3. Verify no "adjustments" to live signals
   - Example: Signal says "Buy Stock A at ₹100"
   - Price moves to ₹110
   - System retroactively changes signal to "Buy Stock B" instead
   - This is fraud — must detect

Specific Test:
- Request full portfolio_history.db export
- Verify all entries >= Feb 1, 2026 have:
  - entry_date, entry_price, signal_score, regime_state
- Check for missing fields (incomplete logs)
- Verify no deletions (row_count should only increase)

Questions:
- Can forward-test results be independently audited?
- Is there a public dashboard showing live trades?
- Is there a third-party custodian verifying trades?

Vector 5 — Tamper Surface Mapping:
Identify all points where data can be manipulated.

Tamper Surfaces:
1. Input Data:
   - NSE API responses (can be faked)
   - Screener.in API responses (can be cached/modified)
   - Corporate action data (can be backdated)

2. Processing Logic:
   - Regime detection thresholds (can be re-optimized)
   - Scoring formula (can be tweaked)
   - Risk governor limits (can be overridden)

3. Output Storage:
   - portfolio_history.db (can be edited with SQLite CLI)
   - scan_log.json (can be regenerated)
   - reports_cache/ (can be manually updated)

4. Timestamps:
   - System clock (can be changed)
   - last_audited (can be forged)
   - trade entry times (can be backdated)

Mitigation Requirements:
- Cryptographic signing of scan_log.json (SHA-256 hash)
- Write-once database (append-only, no UPDATEs)
- Third-party timestamp service (RFC 3161)
- Immutable audit trail (blockchain or similar)

Vector 6 — Reproducibility Test:
Hypothesis: Backtest cannot be reproduced independently.

Test Protocol:
1. Request raw input data (OHLCV, fundamentals, corporate actions)
2. Request exact code version (commit hash, dependencies)
3. Re-run backtest on independent machine
4. Compare outputs:
   - Are trade dates identical?
   - Are entry prices identical?
   - Is final CAGR/Sharpe identical?
5. If any divergence, identify cause:
   - Random seed not fixed?
   - Floating-point rounding differences?
   - Data source changed?

Questions:
- Can results be reproduced by external auditor?
- Is code version-controlled (Git)?
- Are dependencies pinned (requirements.txt)?

Vector 7 — Survivorship Bias Check:
Hypothesis: Delisted stocks not properly included.

Test Protocol:
1. Verify 47 delisted stocks are in backtest universe
2. Check if delisted stocks are:
   - Included at time of delisting (not removed retroactively)
   - Valued at ₹0 on delisting date (not removed from history)
3. Compare backtest universe size over time:
   - 2020: ~750 stocks (before delistings)
   - 2025: ~800 stocks (after new listings)
   - If universe size is constant, survivorship bias likely

Specific Test:
- Request list of 47 delisted stocks
- Verify they appear in scan_log.json during their listing period
- Verify they don't appear after delisting date

Questions:
- How are delistings handled? (immediate exit or held to zero?)
- Are newly listed stocks included immediately or after seasoning period?

Required Analysis:

1. Design Lookahead Detection Test:
   - Specific methodology to prove/disprove lookahead bias
   - What evidence would convince you there's no lookahead?

2. Evaluate Audit Trail Quality:
   - Can trades be independently verified?
   - Can backtest be reproduced?
   - Can data tampering be detected?

3. Map Tamper Surfaces:
   - List all points where data can be manipulated
   - Rate each surface: Low/Medium/High/Critical risk

4. Assess Forward-Test Credibility:
   - Is "live paper-trading since Feb 1" verifiable?
   - What evidence would prove it's real?

5. Identify Compliance Gaps:
   - What's missing for SEC/SEBI audit?
   - What's needed for institutional allocator due diligence?

Deliverables:

1. Audit Integrity Score (0-10):
   - 10 = Bank-grade, cryptographically tamper-proof
   - 7-9 = Strong, audit trail reproducible, minor gaps
   - 4-6 = Moderate, some tamper risk, needs hardening
   - 0-3 = Weak, high tamper risk, not audit-grade

2. Lookahead Risk Level:
   - NONE: Confident no lookahead bias (point-in-time DB verified)
   - LOW: Unlikely, but not 100% certain (timestamp checks passed)
   - MODERATE: Possible, needs independent reproduction
   - HIGH: Likely present, red flags detected
   - CRITICAL: Confirmed lookahead bias (backtest invalid)

3. Tamper Surface Map:
   - List all surfaces: Input Data / Processing / Storage / Timestamps
   - Rate each: Low / Medium / High / Critical risk
   - Provide mitigation recommendations

4. Compliance Risk Classification:
   - LOW: Audit-ready for institutional allocators
   - MODERATE: Needs minor hardening (hashing, write-once DB)
   - HIGH: Significant gaps, not suitable for regulated funds
   - CRITICAL: Forensic red flags, high fraud risk

5. Required Hardening Measures:
   - Critical: Must-fix before any capital (blocking issues)
   - High: Must-fix before institutional capital
   - Medium: Should-fix for best practices
   - Provide specific technical recommendations

Scoring Rubric:
- Data Integrity: /3.0 (lookahead, survivorship, timestamps)
- Audit Trail Quality: /2.5 (reproducibility, tamper-resistance)
- Forward-Test Verification: /2.0 (can live results be proven?)
- Compliance Readiness: /1.5 (SEC/SEBI standards)
- Transparency: /1.0 (can external auditor reproduce?)

Assume fraud until proven otherwise. Find the vulnerabilities.

-----------------------------------------------------

=====================================================
FINAL PHASE — CIO COUNCIL (Structured Debate)
=====================================================

Council Members:
- Agent 1: Principal Systems Architect
- Agent 2: Chief Risk Officer
- Agent 3: Quant Performance Auditor
- Agent 4: Forensic & Compliance Auditor

Debate Protocol:

Round 1 — Independent Findings (5 min each agent):
- Each agent presents their score (0-10)
- Each agent presents their classification (LOW/MODERATE/HIGH/CRITICAL)
- No rebuttals allowed
- Record any score divergence >2 points

Round 2 — Cross-Examination (15 min):
Agent 1 questions Agent 3:
- "If your performance analysis shows Sharpe 1.42 is credible, can my architecture scale to deliver it? At what user count does performance degrade?"

Agent 2 questions Agent 4:
- "If your audit shows no lookahead bias, can you explain why my stress tests predict -35% DD in a crisis? Is the risk model understating tail risk?"

Agent 3 questions Agent 1:
- "If your architecture assessment shows high crash risk under load, does that invalidate my performance analysis? Can historical Sharpe be trusted if system is unstable?"

Agent 4 questions Agent 2:
- "If your risk analysis shows correlation spike risks, have you verified the backtest didn't cherry-pick low-correlation periods? Could there be implicit data snooping?"

Round 3 — Conflict Resolution (20 min):
IF Agent scores diverge by >2 points:
- Identify root cause of disagreement
- Request additional data/tests if needed
- Debate until consensus or agree to disagree

IF any agent votes RED (Not Institutional):
- That agent must justify why their concerns override others
- Other agents challenge the severity assessment
- If RED cannot be overturned with data, final verdict = RED

IF uncertainty remains:
- Default to YELLOW (Conditional Deployment)
- Specify exact tests/data needed to upgrade to GREEN
- Specify timeline for re-evaluation

Round 4 — Final Verdict (10 min):
Vote on Institutional Readiness:
- GREEN: Institutional-grade, ready for scaled capital
- YELLOW: Conditional, ready for pilot capital only
- RED: Not institutional-ready, do not allocate

Calculate Composite Score:
- Agent 1 (Architecture): Weight 25%
- Agent 2 (Risk): Weight 30%
- Agent 3 (Performance): Weight 25%
- Agent 4 (Audit): Weight 20%
- Composite = Weighted Average (round to 0.1)

Determine Maximum Safe Pilot Capital:
- Each agent recommends a max capital allocation
- Final recommendation = MIN(all agent recommendations)
- Justification must be capital-aware (not technology-aware)

Compile Must-Fix List:
- CRITICAL: Blocking issues before ANY capital
- HIGH: Blocking issues before >₹3.75 Cr capital
- MEDIUM: Blocking issues before >₹37.5 Cr capital
- Must be specific and actionable

Final Output Format:

1. EXECUTIVE VERDICT:
   - One-paragraph summary of decision
   - GREEN / YELLOW / RED designation
   - Primary reasoning (2-3 sentences)

2. STRUCTURAL RISK SUMMARY:
   - Key findings from Agent 1
   - Scalability limits and failure modes
   - Critical fixes required

3. TAIL RISK EXPOSURE:
   - Key findings from Agent 2
   - Worst-case drawdown estimate
   - Crisis preparedness assessment

4. PERFORMANCE DURABILITY:
   - Key findings from Agent 3
   - Forward Sharpe decay estimate
   - Alpha persistence assessment

5. AUDIT INTEGRITY REVIEW:
   - Key findings from Agent 4
   - Lookahead/tamper risk level
   - Compliance readiness

6. INSTITUTIONAL READINESS:
   - Final color code: GREEN / YELLOW / RED
   - Justification (data-driven)
   - If YELLOW: Conditions for upgrade to GREEN
   - If RED: Conditions for upgrade to YELLOW

7. COMPOSITE SCORE:
   - Architecture: X/10 (25% weight)
   - Risk: Y/10 (30% weight)
   - Performance: Z/10 (25% weight)
   - Audit: W/10 (20% weight)
   - FINAL: A.B/10 (weighted average)

8. MAXIMUM SAFE PILOT CAPITAL:
   - Amount: ₹X.XX Cr
   - Rationale: Why this limit?
   - Duration: How long before re-evaluation?
   - Conditions: What triggers must be met?

9. MUST-FIX LIST (Prioritized):
   - CRITICAL (Blocking for any capital)
   - HIGH (Blocking for >₹3.75 Cr)
   - MEDIUM (Blocking for >₹37.5 Cr)

Tone Requirements:
- Cold, precise, capital-aware
- Adversarial during cross-examination
- Collaborative during conflict resolution
- No marketing language
- No consensus without data justification
- If disagreement remains, state it explicitly
- Capital preservation is the top priority

Assume ₹750 Cr is at risk. Every decision matters.

End of Audit Protocol.