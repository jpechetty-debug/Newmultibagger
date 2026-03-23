from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List

class DataQualityFlags(BaseModel):
    PE_Ratio: bool = False
    PEG_Ratio: bool = False
    ROE_pct: bool = Field(False, alias="ROE%")
    Avg_ROE_5Y_pct: bool = Field(False, alias="Avg_ROE_5Y%")
    Debt_Equity: bool = False
    EPS_Growth_pct: bool = Field(False, alias="EPS_Growth%")
    Sales_Growth_5Y_pct: bool = Field(False, alias="Sales_Growth_5Y%")
    Sales_Growth_TTM_pct: bool = Field(False, alias="Sales_Growth_TTM%")
    CFO_PAT_Ratio: bool = False
    F_Score: bool = False
    Market_Cap_Cr: bool = False

class StockDataPayload(BaseModel):
    Symbol: str
    Price: float
    Data_Source: str = "unknown"
    History_Bars_1Y: int = 0
    Last_Price_Date: Optional[str] = None
    Price_Age_Days: Optional[int] = None
    Avg_Volume_10D: float = 0.0
    Sector: str = "Unknown"
    Industry: str = "Unknown"
    Market_Cap_Cr: float = 0.0
    DMA_200: float = Field(0.0, alias="200_DMA")
    DMA_50: float = Field(0.0, alias="50_DMA")
    RSI: float = 0.0
    Sales_Growth_TTM_pct: float = Field(0.0, alias="Sales_Growth_TTM%")
    Sales_Growth_5Y_pct: float = Field(0.0, alias="Sales_Growth_5Y%")
    ROE_pct: float = Field(0.0, alias="ROE%")
    Avg_ROE_5Y_pct: float = Field(0.0, alias="Avg_ROE_5Y%")
    Profit_Margin_pct: float = Field(0.0, alias="Profit_Margin%")
    Debt_Equity: float = 0.0
    PEG_Ratio: float = 0.0
    PE_Ratio: float = 0.0
    Down_From_52W_High_pct: float = Field(0.0, alias="Down_From_52W_High%")
    Smart_Money_pct: float = Field(0.0, alias="Smart_Money%")
    Free_Cashflow: float = 0.0
    CFO_PAT_Ratio: float = 0.0
    EPS_Growth_pct: float = Field(0.0, alias="EPS_Growth%")
    F_Score: float = 0.0
    F_Score_Method: str = ""
    RS_Rating: float = 0.0
    Earnings_Accel: bool = False
    Earnings_Inflection_Score: float = 0.0
    Graham_Number: float = 0.0
    Value_Gap_pct: float = Field(0.0, alias="Value_Gap%")
    Technical_Signal: str = "Neutral"
    MACD_Bullish: bool = False
    Analyst_Rating: str = "none"
    Target_Mean_Price: float = 0.0
    Analyst_Upside_pct: float = Field(0.0, alias="Analyst_Upside%")
    Analyst_Count: int = 0
    Promoter_Holding_pct: float = Field(0.0, alias="Promoter_Holding%")
    Inst_Holding_pct: float = Field(0.0, alias="Inst_Holding%")
    ATR: float = 0.0
    Stop_Loss_ATR: float = 0.0
    Max_Qty_1L: float = 0.0
    Estimate_Score_Adj: float = 0.0
    Momentum_Signal: str = "STABLE"
    High_52W: float = 0.0
    Low_52W: float = 0.0
    ROCE_pct: float = Field(0.0, alias="ROCE%")
    Median_PAT_Growth_5Y_pct: float = Field(0.0, alias="Median_PAT_Growth_5Y%")
    Pledge_Pct: float = 0.0
    Ret_1M: float = 0.0
    Ret_3M: float = 0.0
    Ret_6M: float = 0.0
    Vol_Breakout: float = 1.0
    Dist_From_52W_High: float = 0.0
    dq_flags: Optional[DataQualityFlags] = Field(None, alias="_dq_flags")
    
    # Catch-all for extra fields
    model_config = {
        "extra": "allow",
        "populate_by_name": True
    }

class FactorBreakdown(BaseModel):
    Fundamentals: float = 0.0
    Value: float = 0.0
    Risk: float = 0.0
    Momentum: float = 0.0
    Smart_Money: float = 0.0
    Sector: float = 0.0

class ScoringResult(BaseModel):
    total_score: float
    raw_score: float
    checklist_score: str
    data_confidence: float
    conviction_score: float
    conviction_boost: float
    institutional_interest: int
    super_investors: str
    scoring_strategy: str
    factor_penalties: List[Dict[str, Any]] = []
    factor_breakdown: FactorBreakdown
