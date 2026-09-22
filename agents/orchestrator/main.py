import json
import os
from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ORCHESTRATOR_SVID = "spiffe://company.ru/agents/orchestrator_v1"
CONTRACTS_DIR = Path(__file__).resolve().parent / "contracts"

OPA_URL = os.getenv("OPA_URL", "http://opa:8181")
OPA_DECISION_PATH = "/v1/data/procurement/result"

WORKERS = {
    "sourcing": {
        "url": os.getenv("SOURCING_AGENT_URL", "http://sourcing:9001"),
        "svid": "spiffe://company.ru/agents/sourcing_v1",
    },
    "pricing": {
        "url": os.getenv("PRICING_AGENT_URL", "http://pricing:9002"),
        "svid": "spiffe://company.ru/agents/pricing_v1",
    },
    "compliance": {
        "url": os.getenv("COMPLIANCE_AGENT_URL", "http://compliance:9003"),
        "svid": "spiffe://company.ru/agents/compliance_v1",
    },
}

class TaskRequest(BaseModel):
    task_type: str
    payload: dict[str, Any]
    context: dict[str, Any] = {}

class WorkerCall(BaseModel):
    worker: str
    svid: str
    request: dict[str, Any]
    response: dict[str, Any]
    success: bool

app = FastAPI(title="Orchestrator Agent")

async def call_worker(worker_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    worker = WORKERS.get(worker_name)
    if not worker:
        raise ValueError(f"Unknown worker: {worker_name}")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{worker['url']}/a2a/task",
            json={"task": payload, "caller_svid": ORCHESTRATOR_SVID},
            headers={
                "X-Agent-SVID": ORCHESTRATOR_SVID,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        return response.json()

async def call_opa(input_payload: dict[str, Any]) -> dict[str, Any]:
    """Вызов OPA с решением allow | escalate | deny."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.post(
            f"{OPA_URL}{OPA_DECISION_PATH}",
            json={"input": input_payload},
        )
        r.raise_for_status()
        body = r.json()
    return body.get("result", {"decision": "escalate", "deny_reasons": [], "escalate_reasons": ["opa unavailable"]})

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "orchestrator"}

@app.get("/contract")
async def get_contract():
    contract_path = CONTRACTS_DIR / "orchestrator.yaml"
    if not contract_path.exists():
        raise HTTPException(status_code=500, detail=f"Contract not found: {contract_path}")
    with open(contract_path) as f:
        return yaml.safe_load(f)

@app.post("/a2a/task")
async def handle_task(request: TaskRequest) -> dict[str, Any]:
    task_type = request.task_type
    results: list[WorkerCall] = []

    if task_type == "procurement":
        # ── Шаг 1: Sourcing ──
        try:
            sourcing_result = await call_worker("sourcing", request.payload)
            results.append(WorkerCall(
                worker="sourcing",
                svid=WORKERS["sourcing"]["svid"],
                request=request.payload,
                response=sourcing_result,
                success=True,
            ))
        except Exception as e:
            return {
                "decision": "escalate",
                "confidence": 0.0,
                "reasoning": f"Sourcing agent failed: {e}",
                "worker_results": [],
            }

        # ── Шаг 2: Pricing (только если nomenclature_ok) ──
        pricing_result: dict[str, Any] = {}
        if sourcing_result.get("nomenclature_ok"):
            try:
                pricing_result = await call_worker("pricing", {
                    "lot_id": request.payload.get("lot_id"),
                    "amount": request.payload.get("amount"),
                    "category": request.payload.get("category", "server hardware"),
                    "methodology": "method_1",
                })
                results.append(WorkerCall(
                    worker="pricing",
                    svid=WORKERS["pricing"]["svid"],
                    request=request.payload,
                    response=pricing_result,
                    success=True,
                ))
            except Exception as e:
                results.append(WorkerCall(
                    worker="pricing",
                    svid=WORKERS["pricing"]["svid"],
                    request=request.payload,
                    response={"error": str(e)},
                    success=False,
                ))

        # ── Шаг 3: Compliance ──
        compliance_result: dict[str, Any] = {}
        try:
            compliance_result = await call_worker("compliance", {
                "lot_id": request.payload.get("lot_id"),
                "amount": request.payload.get("amount", 0),
                "region": request.payload.get("region", "Moscow"),
                "category": request.payload.get("category", "server hardware"),
                "nmc_value": pricing_result.get("nmc_value"),
            })
            results.append(WorkerCall(
                worker="compliance",
                svid=WORKERS["compliance"]["svid"],
                request=request.payload,
                response=compliance_result,
                success=True,
            ))
        except Exception as e:
            results.append(WorkerCall(
                worker="compliance",
                svid=WORKERS["compliance"]["svid"],
                request=request.payload,
                response={"error": str(e)},
                success=False,
            ))

        # ── Шаг 4: Агрегация confidence ──
        confidences = [r.response.get("confidence", 0.0) for r in results if r.success]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # ── Шаг 5: Policy Enforcement через OPA ──
        opa_input = {
            "amount": request.payload.get("amount", 0),
            "region": request.payload.get("region", "Moscow"),
            "confidence": avg_confidence,
            "nomenclature_ok": bool(sourcing_result.get("nomenclature_ok", False)),
            "compliance_ok": bool(compliance_result.get("compliance_ok", False)),
            "nmc_value": pricing_result.get("nmc_value"),
        }
        try:
            opa_result = await call_opa(opa_input)
        except Exception as e:
            opa_result = {
                "decision": "escalate",
                "deny_reasons": [],
                "escalate_reasons": [f"opa call failed: {e}"],
            }

        reasoning_parts = [f"{r.worker}: {'OK' if r.success else 'FAILED'}" for r in results]
        reasoning_parts.append(f"opa: {opa_result.get('decision')}")

        return {
            "decision": opa_result.get("decision", "escalate"),
            "confidence": avg_confidence,
            "reasoning": "; ".join(reasoning_parts),
            "opa": opa_result,
            "worker_results": [r.model_dump() for r in results],
        }

    elif task_type in WORKERS:
        try:
            result = await call_worker(task_type, request.payload)
            results.append(WorkerCall(
                worker=task_type,
                svid=WORKERS[task_type]["svid"],
                request=request.payload,
                response=result,
                success=True,
            ))
        except Exception as e:
            return {
                "decision": "escalate",
                "confidence": 0.0,
                "reasoning": f"Worker {task_type} failed: {e}",
                "worker_results": [],
            }
    else:
        raise HTTPException(status_code=400, detail=f"Unknown task_type: {task_type}")

    confidences = [r.response.get("confidence", 0.0) for r in results if r.success]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    reasoning_parts = [f"{r.worker}: OK" if r.success else f"{r.worker}: FAILED" for r in results]

    return {
        "decision": "approve" if avg_confidence >= 0.85 else "escalate",
        "confidence": avg_confidence,
        "reasoning": "; ".join(reasoning_parts),
        "worker_results": [r.model_dump() for r in results],
    }
