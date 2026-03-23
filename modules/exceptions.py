class TradingEngineError(Exception):
    """Base exception class for Sovereign AI Trading Engine."""
    pass

class FetchError(TradingEngineError):
    """Raised when there is an error fetching data from external APIs."""
    pass

class DataQualityError(TradingEngineError):
    """Raised when data retrieved fails quality validation checks."""
    pass

class ScoringError(TradingEngineError):
    """Raised when applying scoring logic fails."""
    pass

class DatabaseConcurrencyError(TradingEngineError):
    """Raised when a database concurrent write lock issue occurs."""
    pass

class RateLimitError(FetchError):
    """Raised when hitting an API rate limit."""
    pass
