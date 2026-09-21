import asyncio
from typing import Any
from base import create_worker_app

AGENT_NAME = "pricing"
AGENT_SVID = "spiffe://company.ru/agents/pricing_v1"

async def handle_task(task: dict[str, Any]) -> dict[str, Any]:
    lot_id = task.get("lot_id", "unknown")
    amount = task.get("amount", 0)
    methodology = task.get("methodology", "method_1")
    await asyncio.sleep(0.7)
    return {
        "nmc_value": float(amount) * 0.95,
        "justification": f"Calculated using {methodology}",
        "confidence": 0.88,
    }

app = create_worker_app(AGENT_NAME, AGENT_SVID, handle_task)