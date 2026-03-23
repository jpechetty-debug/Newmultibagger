# modules/llm_engine.py
import requests
import logging
from .llm_validator import FactValidator, patch_thesis

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "deepseek-r1:32b"

def generate_rule_based_thesis(stock_data):
    """
    Generates a deterministic quantitative thesis summary when the LLM is unavailable.
    """
    symbol = stock_data.get('symbol') or stock_data.get('Symbol', 'UNKNOWN')
    score = stock_data.get('Score', stock_data.get('score', 0))
    rating = stock_data.get('Rating', stock_data.get('rating', 'N/A'))
    f_score = stock_data.get('F_Score', stock_data.get('f_score', 0))
    sales_growth = stock_data.get('Sales_Growth_5Y%', stock_data.get('sales_cagr_5y', 0))
    roe = stock_data.get('Avg_ROE_5Y%', stock_data.get('avg_roe_5y', 0))
    pe = stock_data.get('PE_Ratio', stock_data.get('pe_ratio', 0))
    value_gap = stock_data.get('Value_Gap%', stock_data.get('value_gap', 0))
    ml_predict = stock_data.get('ML_Predicted_Return', stock_data.get('ml_predicted_return', 'N/A'))

    # Contextual Strength Indicator
    strength = "exceptional" if score > 80 else "robust" if score > 65 else "moderate"
    
    thesis = (
        f"{symbol} exhibits a Sovereign Score of {score}/100 with a {rating} rating, reflecting {strength} fundamental alignment. "
        f"The investment profile is supported by a Piotroski F-Score of {f_score}/9 and a 5-year sales CAGR of {sales_growth}%, demonstrating structural quality. "
        f"Valuation metrics show a P/E of {pe} with a {value_gap}% margin to fair value, while hybrid ML models forecast a {ml_predict}% forward return."
    )
    return f"{thesis}\n\n[Sovereign Rule-Based Engine: Quantitative Fallback Active]"

def generate_thesis(stock_data):
    """
    Generates a concise, fundamentally-driven technical thesis for a given stock
    using a local Ollama LLM.
    """
    if not stock_data:
        return "Insufficient data to generate thesis."
        
    symbol = stock_data.get('symbol') or stock_data.get('Symbol', 'UNKNOWN')
    score = stock_data.get('Score', stock_data.get('score', 0))
    rating = stock_data.get('Rating', stock_data.get('rating', 'N/A'))
    f_score = stock_data.get('F_Score', stock_data.get('f_score', 0))
    sales_growth = stock_data.get('Sales_Growth_5Y%', stock_data.get('sales_cagr_5y', 0))
    roe = stock_data.get('Avg_ROE_5Y%', stock_data.get('avg_roe_5y', 0))
    pe = stock_data.get('PE_Ratio', stock_data.get('pe_ratio', 0))
    value_gap = stock_data.get('Value_Gap%', stock_data.get('value_gap', 0))
    ml_predict = stock_data.get('ML_Predicted_Return', stock_data.get('ml_predicted_return', 'N/A'))
    
    prompt = f"""
    You are an expert institutional equity researcher. Based on the following quantitative profile of the Indian stock {symbol}, write a concise, strictly 3-sentence investment thesis.
    Do NOT include disclaimers or conversational filler. State the facts logically.
    
    PROFILE:
    - Sovereign Rank Score: {score}/100 (Rating: {rating})
    - Piotroski F-Score (Quality): {f_score}/9
    - 5-Year Sales CAGR: {sales_growth}%
    - 5-Year Avg ROE: {roe}%
    - Valuation: P/E is {pe}, Value Gap to Fair Value is {value_gap}%
    - Hybrid ML Alpha Forecast: {ml_predict}% expected return
    
    Write the thesis now:
    """
    
    payload = {
        "model": DEFAULT_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 150
        }
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=20)
        response.raise_for_status()
        data = response.json()
        raw_thesis = data.get('response', '').strip()
        
        # Rigorous Fact-Checking Middleware
        try:
            validator = FactValidator(tolerance_pct=15.0)
            report = validator.validate(raw_thesis, stock_data)
            patched_thesis = patch_thesis(raw_thesis, report)
            
            # Log any silent hallucinations we caught
            if not report.is_valid or report.flagged_claims:
                logging.warning(f"[LLM Validator] Caught hallucinations for {symbol}.")
                for audit_log in report.audit_trail:
                    logging.info(f"  {audit_log}")
                    
            return patched_thesis
        except Exception as ve:
            logging.error(f"LLM Validation logic failed for {symbol}: {ve}")
            return f"{raw_thesis}\n\n[Warning: AI thesis could not be verified due to an internal error.]"
            
        logging.warning(f"Ollama thesis generation failed for {symbol}: {e}")
        # Return a quantitative fallback instead of just an error message
        return generate_rule_based_thesis(stock_data)


class ScenarioPlanner:
    """Uses LLM to plan qualitative scenarios (Bull, Base, Bear) based on fundamentals."""
    
    def __init__(self, model=DEFAULT_MODEL):
        self.model = model

    def generate_scenarios(self, stock_data: dict) -> dict:
        """Generate Bull, Base, and Bear scenarios for a stock."""
        symbol = stock_data.get('symbol', 'UNKNOWN')
        prompt = f"""
        Analyze the following data for {symbol} and provide three qualitative investment scenarios:
        1. BULL CASE: What happens if everything goes right?
        2. BASE CASE: Most likely outcome.
        3. BEAR CASE: Key risks and downside potential.
        
        DATA: {stock_data}
        
        Format your response as a valid JSON object with keys "bull", "base", and "bear".
        Do not include any other text.
        """
        
        try:
            response = requests.post(OLLAMA_URL, json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.4}
            }, timeout=30)
            response.raise_for_status()
            import json
            raw_text = response.json().get('response', '{}')
            # Extract JSON if nested in text
            if "{" in raw_text:
                json_part = raw_text[raw_text.find("{"):raw_text.rfind("}")+1]
                return json.loads(json_part)
            return {"error": "Invalid LLM Response Format"}
        except Exception as e:
            logging.error(f"Scenario planning failed for {symbol}: {e}")
            return {"error": str(e)}
