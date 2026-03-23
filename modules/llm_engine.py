# modules/llm_engine.py
"""
LLM Engine — generates investment theses via a local Ollama instance.
OLLAMA_URL is read from config (which reads from .env), not hardcoded.
This means the Docker container correctly picks up:
    OLLAMA_URL=http://host.docker.internal:11434/api/generate
instead of hitting localhost (which is the container itself).
"""
import requests
import logging
import config
from .llm_validator import FactValidator, patch_thesis

log = logging.getLogger(__name__)

# ── Source from config, not hardcoded ──────────────────────────────────────
OLLAMA_URL: str = config.OLLAMA_URL
DEFAULT_MODEL = "deepseek-r1:32b"


def generate_rule_based_thesis(stock_data: dict) -> str:
    """
    Deterministic quantitative thesis — used when Ollama is unavailable.
    No external calls; always succeeds.
    """
    symbol     = stock_data.get("symbol") or stock_data.get("Symbol", "UNKNOWN")
    score      = stock_data.get("Score",          stock_data.get("score", 0))
    rating     = stock_data.get("Rating",         stock_data.get("rating", "N/A"))
    f_score    = stock_data.get("F_Score",         stock_data.get("f_score", 0))
    sales_cagr = stock_data.get("Sales_Growth_5Y%", stock_data.get("sales_cagr_5y", 0))
    roe        = stock_data.get("Avg_ROE_5Y%",     stock_data.get("avg_roe_5y", 0))
    pe         = stock_data.get("PE_Ratio",        stock_data.get("pe_ratio", 0))
    value_gap  = stock_data.get("Value_Gap%",      stock_data.get("value_gap", 0))
    ml_predict = stock_data.get("ML_Predicted_Return", stock_data.get("ml_predicted_return", "N/A"))

    strength = "exceptional" if score > 80 else "robust" if score > 65 else "moderate"

    thesis = (
        f"{symbol} exhibits a Sovereign Score of {score}/100 with a {rating} rating, "
        f"reflecting {strength} fundamental alignment. "
        f"The investment profile is supported by a Piotroski F-Score of {f_score}/9 "
        f"and a 5-year sales CAGR of {sales_cagr}%, demonstrating structural quality. "
        f"Valuation metrics show a P/E of {pe} with a {value_gap}% margin to fair value, "
        f"while hybrid ML models forecast a {ml_predict}% forward return."
    )
    return f"{thesis}\n\n[Sovereign Rule-Based Engine: Quantitative Fallback Active]"


def generate_thesis(stock_data: dict) -> str:
    """
    Generate a concise, fundamentally-driven investment thesis via Ollama.
    Falls back to the rule-based engine if Ollama is unreachable.
    """
    if not stock_data:
        return "Insufficient data to generate thesis."

    symbol     = stock_data.get("symbol") or stock_data.get("Symbol", "UNKNOWN")
    score      = stock_data.get("Score",          stock_data.get("score", 0))
    rating     = stock_data.get("Rating",         stock_data.get("rating", "N/A"))
    f_score    = stock_data.get("F_Score",         stock_data.get("f_score", 0))
    sales_cagr = stock_data.get("Sales_Growth_5Y%", stock_data.get("sales_cagr_5y", 0))
    roe        = stock_data.get("Avg_ROE_5Y%",     stock_data.get("avg_roe_5y", 0))
    pe         = stock_data.get("PE_Ratio",        stock_data.get("pe_ratio", 0))
    value_gap  = stock_data.get("Value_Gap%",      stock_data.get("value_gap", 0))
    ml_predict = stock_data.get("ML_Predicted_Return", stock_data.get("ml_predicted_return", "N/A"))

    prompt = f"""You are a senior equity analyst. Generate a concise 3-paragraph investment thesis.

Stock: {symbol}
Sovereign Score: {score}/100 | Rating: {rating}
Piotroski F-Score: {f_score}/9
5Y Sales CAGR: {sales_cagr}% | Avg ROE (5Y): {roe}%
P/E Ratio: {pe} | Value Gap: {value_gap}% | ML Forecast: {ml_predict}%

Focus on: (1) business quality & moat, (2) valuation context, (3) key risks.
Be specific. Avoid generic statements."""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={"model": DEFAULT_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        response.raise_for_status()
        raw_thesis = response.json().get("response", "").strip()
        if not raw_thesis:
            raise ValueError("Empty response from Ollama")

        # Validate factual consistency
        validator = FactValidator(stock_data)
        patched = patch_thesis(raw_thesis, validator)
        return patched

    except requests.exceptions.ConnectionError:
        log.warning(
            "Ollama unreachable at %s — using rule-based fallback", OLLAMA_URL
        )
        return generate_rule_based_thesis(stock_data)
    except Exception as exc:
        log.error("LLM thesis generation failed for %s: %s", symbol, exc)
        return generate_rule_based_thesis(stock_data)
