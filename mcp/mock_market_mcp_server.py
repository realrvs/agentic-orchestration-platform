"""
Mock-Market MCP Server.

Транспорт: SSE + JSON-RPC 2.0.
Tools:
  - get_market_prices  — средние/мин/макс цены по категории
  - get_price_index    — индекс роста цен
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

FIXTURES = Path(__file__).resolve().parent / "fixtures"
app = FastAPI(title="Mock-Market MCP Server", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SVID_ALLOWLIST = {
    "spiffe://company.ru/agents/pricing_v1",
    "spiffe://company.ru/agents/orchestrator_v1",
}


def _load_prices() -> dict:
    return json.loads((FIXTURES / "market_prices.json").read_text(encoding="utf-8"))


def _check_svid(request: Request) -> str | None:
    svid = request.headers.get("X-Agent-SVID")
    if svid not in SVID_ALLOWLIST:
        return None
    return svid


def _tool_get_market_prices(args: dict) -> dict:
    data = _load_prices()
    category = (args.get("category") or "").lower()
    entry = data["prices"].get(category)
    if entry is None:
        return {"category": category, "found": False, "available": list(data["prices"].keys())}
    return {"category": category, "found": True, **entry}


def _tool_get_price_index(args: dict) -> dict:
    data = _load_prices()
    return data["index"]


TOOLS = {
    "get_market_prices": _tool_get_market_prices,
    "get_price_index": _tool_get_price_index,
}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "server": "mock-market", "tools": list(TOOLS.keys())}


@app.post("/mcp/messages")
async def mcp_messages(request: Request) -> JSONResponse:
    svid = _check_svid(request)
    if svid is None:
        return JSONResponse(
            status_code=403,
            content={"jsonrpc": "2.0", "id": None,
                     "error": {"code": -32000, "message": "invalid or missing X-Agent-SVID"}},
        )

    body = await request.json()
    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})

    if method != "tools/call":
        return JSONResponse(content={
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        })

    tool_name = params.get("name")
    arguments = params.get("arguments", {})
    handler = TOOLS.get(tool_name)
    if handler is None:
        return JSONResponse(content={
            "jsonrpc": "2.0", "id": req_id,
            "error": {"code": -32602, "message": f"unknown tool: {tool_name}"},
        })

    result = handler(arguments)
    return JSONResponse(content={
        "jsonrpc": "2.0", "id": req_id,
        "result": {"content": [{"type": "json", "json": result}]},
    })


@app.get("/mcp/sse")
async def mcp_sse(request: Request):
    async def event_generator():
        yield {"event": "ready", "data": json.dumps({"server": "mock-market"})}
    return EventSourceResponse(event_generator())
