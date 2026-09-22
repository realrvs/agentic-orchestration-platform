"""
Pricing Agent.

Дёргает Mock-Market через MCP (JSON-RPC 2.0 + X-Agent-SVID).
При недоступности MCP — fallback на stub.
"""
import asyncio
import os
from typing import Any

import httpx

from base import create_worker_app

AGENT_NAME = "pricing"
AGENT_SVID = "spiffe://company.ru/agents/pricing_v1"

MOCK_MARKET_URL = os.getenv("MOCK_MARKET_URL", "http://mock-market:9102")
MCP_TIMEOUT = float(os.getenv("MCP_TIMEOUT", "5.0"))


def _stub(amount: float, methodology: str) -> dict[str, Any]:
    return {
        "nmc_value": float(amount or 0) * 0.95,
        "justification": f"Calculated using {methodology}",
        "confidence": 0.88,
        "source": "stub",
    }


async def _call_mcp_market(category: str, amount: float, methodology: str) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "get_market_prices",
            "arguments": {"category": category},
        },
    }
    headers = {
        "Content-Type": "application/json",
        "X-Agent-SVID": AGENT_SVID,
    }
    async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
        r = await client.post(f"{MOCK_MARKET_URL}/mcp/messages", json=payload, headers=headers)
        r.raise_for_status()
        body = r.json()

    if "error" in body:
        raise RuntimeError(f"MCP error: {body['error']}")

    market = body["result"]["content"][0]["json"]
    if not market.get("found", False):
        raise RuntimeError(f"category not found in mock-market: {category}")

    avg = float(market.get("avg_price", 0))
    min_p = float(market.get("min_price", 0))
    max_p = float(market.get("max_price", 0))

    # Консервативная оценка НМЦ
    num_amount = float(amount) if amount is not None else 0.0
    nmc_value = min(avg, num_amount) if num_amount > 0 else avg

    return {
        "nmc_value": nmc_value,
        "justification": (
            f"Mock-market {methodology}: avg={avg:.0f}, "
            f"min={min_p:.0f}, max={max_p:.0f}, sample={market.get('sample_size', 0)}"
        ),
        "confidence": 0.90,
        "source": "mock-market",
        "market": {
            "avg_price": avg,
            "min_price": min_p,
            "max_price": max_p,
        },
    }


async def handle_task(task: dict[str, Any]) -> dict[str, Any]:
    lot_id = task.get("lot_id", "unknown")
    amount = task.get("amount", 0)
    methodology = task.get("methodology", "method_1")
    category = task.get("category", "server hardware")

    try:
        return await _call_mcp_market(category, amount, methodology)
    except Exception as exc:
        print(f"[pricing] MCP fallback to stub: {exc}")
        await asyncio.sleep(0.1)
        return _stub(amount, methodology)


app = create_worker_app(AGENT_NAME, AGENT_SVID, handle_task)
