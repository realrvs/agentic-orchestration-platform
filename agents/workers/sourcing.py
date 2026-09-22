"""
Sourcing Agent.

Дёргает Mock-1С через MCP (JSON-RPC 2.0 + X-Agent-SVID).
При недоступности MCP — fallback на stub, чтобы PoC не падал.
"""
import asyncio
import os
from typing import Any

import httpx

from base import create_worker_app

AGENT_NAME = "sourcing"
AGENT_SVID = "spiffe://company.ru/agents/sourcing_v1"

MOCK_1C_URL = os.getenv("MOCK_1C_URL", "http://mock-1c:9101")
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT", "5.0"))


def _stub(lot_id: str, category: str) -> dict[str, Any]:
    return {
        "lot_data": {"lot_id": lot_id, "category": category, "items_count": 5},
        "nomenclature_ok": True,
        "confidence": 0.92,
        "source": "stub",
    }


async def _call_mcp_1c(lot_id: str, category: str) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "get_lot_data",
            "arguments": {"lot_id": lot_id, "category": category},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Agent-SVID": AGENT_SVID,
    }
    async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
        r = await client.post(f"{MOCK_1C_URL}/mcp/messages", json=payload, headers=headers)
        r.raise_for_status()
        body = r.json()

    if "error" in body:
        raise RuntimeError(f"MCP error: {body['error']}")

    lot_data = body["result"]["content"][0]["json"]
    items_count = lot_data.get("items_count", 0)
    nomenclature_ok = bool(lot_data.get("nomenclature_ok", items_count > 0))
    confidence = 0.95 if nomenclature_ok else 0.60

    return {
        "lot_data": {
            "lot_id": lot_data.get("lot_id", lot_id),
            "category": lot_data.get("category", category),
            "items_count": items_count,
            "items": lot_data.get("items", []),
        },
        "nomenclature_ok": nomenclature_ok,
        "confidence": confidence,
        "source": "mock-1c",
    }


async def handle_task(task: dict[str, Any]) -> dict[str, Any]:
    lot_id = task.get("lot_id", "unknown")
    category = task.get("category", "IT")

    try:
        return await _call_mcp_1c(lot_id, category)
    except Exception as exc:
        print(f"[sourcing] MCP fallback to stub: {exc}")
        await asyncio.sleep(0.1)
        return _stub(lot_id, category)


app = create_worker_app(AGENT_NAME, AGENT_SVID, handle_task)
