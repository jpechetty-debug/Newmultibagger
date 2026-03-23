# modules/stress_tester.py
from dataclasses import dataclass
from typing import Dict, List
import math
from enum import Enum

class CrisisType(Enum):
    COVID_CRASH_2020 = "COVID_CRASH_2020"
    NBFC_CRISIS_2018 = "NBFC_CRISIS_2018"
    RATE_SHOCK_2022 = "RATE_SHOCK_2022"
    CUSTOM = "CUSTOM"

@dataclass
class Scenario:
    name: str
    crisis_type: CrisisType
    market_shock_pct: float
    duration_days: int
    sector_shocks: Dict[str, float]
    vix_spike: float = 0.0

class ScenarioLibrary:
    COVID_CRASH_2020 = Scenario(
        name="COVID-19 Crash (Feb-Mar 2020)",
        crisis_type=CrisisType.COVID_CRASH_2020,
        market_shock_pct=-38.0,
        duration_days=40,
        sector_shocks={"Aviation": -70.0, "Hotels": -60.0, "Banking": -45.0, "Pharma": 15.0, "IT": -20.0},
        vix_spike=83.0
    )
    
    NBFC_CRISIS_2018 = Scenario(
        name="IL&FS NBFC Liquidity Crisis (Sep 2018)",
        crisis_type=CrisisType.NBFC_CRISIS_2018,
        market_shock_pct=-15.0,
        duration_days=90,
        sector_shocks={"NBFC": -55.0, "Realty": -40.0, "Auto": -30.0, "FMCG": -5.0}
    )
    
    RATE_SHOCK_2022 = Scenario(
        name="Global Rate Shock (H1 2022)",
        crisis_type=CrisisType.RATE_SHOCK_2022,
        market_shock_pct=-17.0,
        duration_days=180,
        sector_shocks={"IT": -35.0, "Growth": -40.0, "Banking": 5.0, "Energy": 20.0}
    )

    @classmethod
    def create_custom(cls, name: str, market_shock_pct: float, duration_days: int, sector_shocks: Dict[str, float]) -> Scenario:
        return Scenario(
            name=name,
            crisis_type=CrisisType.CUSTOM,
            market_shock_pct=market_shock_pct,
            duration_days=duration_days,
            sector_shocks=sector_shocks
        )

    @classmethod
    def get_all_standard_scenarios(cls) -> List[Scenario]:
        return [cls.COVID_CRASH_2020, cls.NBFC_CRISIS_2018, cls.RATE_SHOCK_2022]

@dataclass
class PositionShock:
    symbol: str
    base_value: float
    shocked_value: float
    loss_pct: float
    loss_inr: float
    applied_shock_type: str

@dataclass
class StressReport:
    scenario_name: str
    portfolio_start_value: float
    portfolio_end_value: float
    portfolio_loss_pct: float
    portfolio_loss_inr: float
    worst_position: PositionShock
    best_position: PositionShock
    recovery_days_estimate: float
    position_details: List[PositionShock]

    def to_markdown(self) -> str:
        md = f"## 🌪️ Stress Test Results: {self.scenario_name}\n\n"
        md += f"**Pre-Shock Value:** ₹{self.portfolio_start_value:,.2f} | **Post-Shock Value:** ₹{self.portfolio_end_value:,.2f}\n"
        md += f"**Portfolio DD:** {self.portfolio_loss_pct:.2f}% (₹{self.portfolio_loss_inr:,.2f})\n"
        md += f"**Est. Recovery Time:** {math.ceil(self.recovery_days_estimate)} trading days\n\n"
        
        md += "### 🛡️ Extremes\n"
        if self.worst_position:
            md += f"- **🩸 Worst Hit:** {self.worst_position.symbol} ({self.worst_position.loss_pct:.2f}% / ₹{self.worst_position.loss_inr:,.2f}) [{self.worst_position.applied_shock_type}]\n"
        if self.best_position:
            md += f"- **🌟 Most Resilient:** {self.best_position.symbol} ({self.best_position.loss_pct:.2f}% / ₹{self.best_position.loss_inr:,.2f}) [{self.best_position.applied_shock_type}]\n\n"
        
        md += "### 📊 Position Breakdown\n"
        md += "| Symbol | Pre-Shock | Post-Shock | Impact | Driver |\n"
        md += "|---|---|---|---|---|\n"
        
        # Sort by loss % (worst first, i.e., most negative)
        sorted_pos = sorted(self.position_details, key=lambda x: x.loss_pct)
        for p in sorted_pos:
            md += f"| {p.symbol} | ₹{p.base_value:,.2f} | ₹{p.shocked_value:,.2f} | {p.loss_pct:.2f}% | {p.applied_shock_type} |\n"
            
        return md


class StressTester:
    def run(self, portfolio: Dict[str, Dict[str, float|str]], scenario: Scenario) -> StressReport:
        position_details = []
        portfolio_start_value = 0.0
        portfolio_end_value = 0.0
        
        for symbol, data in portfolio.items():
            current_value = float(data.get('current_value', 0.0))
            sector = str(data.get('sector', 'Unknown'))
            beta = float(data.get('beta', 1.0))
            
            portfolio_start_value += current_value
            
            # Determine applied shock
            if sector in scenario.sector_shocks:
                shock_pct = scenario.sector_shocks[sector]
                shock_type = f"Sector ({sector})"
            else:
                shock_pct = scenario.market_shock_pct * beta
                shock_type = f"Market Beta ({beta:.2f})"
                
            loss_pct = shock_pct
            shocked_value = current_value * (1 + (loss_pct / 100.0))
            loss_inr = shocked_value - current_value
            
            portfolio_end_value += shocked_value
            
            pos_shock = PositionShock(
                symbol=symbol,
                base_value=current_value,
                shocked_value=shocked_value,
                loss_pct=loss_pct,
                loss_inr=loss_inr,
                applied_shock_type=shock_type
            )
            position_details.append(pos_shock)
            
        portfolio_loss_inr = portfolio_end_value - portfolio_start_value
        portfolio_loss_pct = (portfolio_loss_inr / portfolio_start_value * 100.0) if portfolio_start_value > 0 else 0.0
        
        # Est. Recovery Time: Nifty historical recovery speed is roughly 8.5x the drawdown percentage in trading days
        recovery_days = abs(portfolio_loss_pct) * 8.5
        
        worst_position = min(position_details, key=lambda x: x.loss_pct) if position_details else None
        best_position = max(position_details, key=lambda x: x.loss_pct) if position_details else None
        
        return StressReport(
            scenario_name=scenario.name,
            portfolio_start_value=portfolio_start_value,
            portfolio_end_value=portfolio_end_value,
            portfolio_loss_pct=portfolio_loss_pct,
            portfolio_loss_inr=portfolio_loss_inr,
            worst_position=worst_position,
            best_position=best_position,
            recovery_days_estimate=recovery_days,
            position_details=position_details
        )


def run_all_scenarios(portfolio: Dict[str, Dict[str, float|str]]) -> List[StressReport]:
    tester = StressTester()
    scenarios = ScenarioLibrary.get_all_standard_scenarios()
    
    reports = []
    for scn in scenarios:
        reports.append(tester.run(portfolio, scn))
        
    # Rank by severity (worst portfolio loss first)
    reports.sort(key=lambda r: r.portfolio_loss_pct)
    return reports


if __name__ == "__main__":
    # Demo code block
    sample_portfolio = {
        "HDFCBANK.NS": {"weight": 0.30, "sector": "Banking", "beta": 1.1, "current_value": 300000},
        "TCS.NS": {"weight": 0.25, "sector": "IT", "beta": 0.8, "current_value": 250000},
        "INDIGO.NS": {"weight": 0.15, "sector": "Aviation", "beta": 1.4, "current_value": 150000},
        "SUNPHARMA.NS": {"weight": 0.20, "sector": "Pharma", "beta": 0.6, "current_value": 200000},
        "BAJFINANCE.NS": {"weight": 0.10, "sector": "NBFC", "beta": 1.5, "current_value": 100000}
    }
    
    print("🚀 Initializing Sovereign Stress Tester...\n")
    ranked_reports = run_all_scenarios(sample_portfolio)
    
    for idx, report in enumerate(ranked_reports, 1):
        print(f"--- RANK {idx} SEVERITY ---")
        print(report.to_markdown())
        print("\n" + "="*50 + "\n")

    print("\n--- TEST: CUSTOM SCENARIO ---")
    custom_scn = ScenarioLibrary.create_custom(
        name="Global Tech Meltdown 2026",
        market_shock_pct=-10.0,
        duration_days=30,
        sector_shocks={"IT": -50.0}
    )
    tester = StressTester()
    custom_report = tester.run(sample_portfolio, custom_scn)
    print(custom_report.to_markdown())
