import asyncio
from typing import Any
from base import create_worker_app

AGENT_NAME = "sourcing"
AGENT_SVID = "spiffe://company.ru/agents/sourcing_v1"

async def handle_task(task: dict[str, Any]) -> dict[str, Any]:
    lot_id = task.get("lot_id", "unknown")
    category = task.get("category", "IT")
    await asyncio.sleep(0.5)
    return {
        "lot_data": {"lot_id": lot_id, "category": category, "items_count": 5},
        "nomenclature_ok": True,
        "confidence": 0.92,
    }

app = create_worker_app(AGENT_NAME, AGENT_SVID, handle_task)