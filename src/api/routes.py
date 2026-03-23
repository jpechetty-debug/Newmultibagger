from fastapi import APIRouter, HTTPException, BackgroundTasks
from src.data.database import db_manager
from src.services.screener_service import screener_service
from src.core.logging_config import get_logger

router = APIRouter()
logger = get_logger(__name__)

@router.get("/stocks")
def get_multibaggers():
    """Fetch Top Multibagger Picks from DB"""
    try:
        df = db_manager.load_dataframe("multibaggers")
        if df.empty:
            return []
        return df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error fetching multibaggers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/microcaps")
def get_microcaps():
    """Fetch Hidden Microcap Gems from DB"""
    try:
        df = db_manager.load_dataframe("microcaps")
        if df.empty:
            return []
        return df.to_dict(orient="records")
    except Exception as e:
        logger.error(f"Error fetching microcaps: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/scan/microcaps")
async def trigger_microcap_scan(background_tasks: BackgroundTasks):
    """Trigger a new Microcap Scan in the background."""
    background_tasks.add_task(screener_service.run_screener)
    return {"message": "Microcap scan started in background."}
