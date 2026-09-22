"""
Mock-1С MCP Server.

Транспорт: SSE + JSON-RPC 2.0 (совместим с mcp-gateway-poc/eis_mcp_server.py).
Tools:
  - get_nomenclature    — поиск позиции номенклатуры по коду или названию
  - get_lot_data        — данные лота по lot_id
  - verify_nomenclature — проверка, что все позиции лота существуют в ЕСУ НСИ
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

FIXTURES = Path(__file__).resolve().parent / "fixtures"
app = FastAPI(title="Mock-1С MCP Server", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SVID_ALLOWLIST = {
    "spiffe://company.ru/agents/sourcing_v1",
    "spiffe://company.ru/agents/orchestrator_v1",
}


def _load_nomenclature() -> dict:
    return json.loads((FIXTURES / "nomenclature.json").read_text(encoding="utf-8"))


def _check_svid(request: Request) -> str | None:
    svid = request.headers.get("X-Agent-SVID")
    if svid not in SVID_ALLOWLIST:
        return None
    return svid


def _tool_get_nomenclature(args: dict) -> dict:
    data = _load_nomenclature()
    query = (args.get("query") or "").lower()
    matches = [
        item for item in data["items"]
        if query in item["name"].lower() or query in item["code"].lower()
    ]
    return {"items": matches, "count": len(matches)}


def _tool_get_lot_data(args: dict) -> dict:
    lot_id = args.get("lot_id", "UNKNOWN")
    category = args.get("category", "server hardware")
    data = _load_nomenclature()
    items = [i for i in data["items"] if i["category"] == category]
    return {
        "lot_id": lot_id,
        "category": category,
        "items_count": len(items),
        "items": items,
        "nomenclature_ok": len(items) > 0,
        "source": "mock-1c",
    }


def _tool_verify_nomenclature(args: dict) -> dict:
    codes = args.get("codes", [])
    data = _load_nomenclature()
    known = {i["code"] for i in data["items"]}
    missing = [c for c in codes if c not in known]
    return {
        "verified": len(missing) == 0,
        "missing_codes": missing,
        "source": "mock-1c",
    }


TOOLS = {
    "get_nomenclature": _tool_get_nomenclature,
    "get_lot_data": _tool_get_lot_data,
    "verify_nomenclature": _tool_verify_nomenclature,
}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "server": "mock-1c", "tools": list(TOOLS.keys())}


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
    """SSE endpoint — для совместимости с mcp-gateway-poc."""
    async def event_generator():
        yield {"event": "ready", "data": json.dumps({"server": "mock-1c"})}
    return EventSourceResponse(event_generator())
