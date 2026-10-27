"""Route handlers for telemetry history and run inspection."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query

from backend.app.telemetry.db import telemetry_db

router = APIRouter()


@router.get("/history")
async def get_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> List[Dict[str, Any]]:
    """Returns paginated history of past de-obfuscation runs."""
    return telemetry_db.get_history(limit=limit, offset=offset)


@router.get("/runs/{run_id}")
async def get_run_detail(run_id: str) -> Dict[str, Any]:
    """Returns detailed information for a specific run including its verification attempts."""
    run = telemetry_db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found.")
    return run
