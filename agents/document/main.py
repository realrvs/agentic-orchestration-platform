"""
Document Agent — worker в agentic-orchestration-platform.

Формирует ПЗД (пояснительная записка к договору) и проект договора
по Jinja2-шаблонам после решения OPA: allow.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from base import create_worker_app

AGENT_NAME = "document"
AGENT_SVID = "spiffe://company.ru/agents/document_v1"

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(enabled_extensions=()),
    trim_blocks=True,
    lstrip_blocks=True,
)


async def handle_task(task: dict[str, Any]) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Нормализация числовых полей
    amount = float(task.get("amount", 0) or 0)
    nmc_value = float(task.get("nmc_value", amount) or amount)
    market = task.get("market", {}) or {}
    market_avg = float(market.get("avg_price", nmc_value) or nmc_value)
    market_min = float(market.get("min_price", nmc_value) or nmc_value)
    market_max = float(market.get("max_price", nmc_value) or nmc_value)
    items = task.get("items", []) or []
    items_count = int(task.get("items_count", len(items)) or len(items))

    # Уверенность зависит от решения OPA — вычисляем ДО рендера шаблонов
    confidence_map = {"allow": 0.95, "escalate": 0.75, "deny": 0.60}
    confidence = confidence_map.get(task.get("opa_decision", "escalate"), 0.70)

    context = {
        "lot_id": task.get("lot_id", "UNKNOWN"),
        "amount": amount,
        "nmc_value": nmc_value,
        "region": task.get("region", "Moscow"),
        "category": task.get("category", "server hardware"),
        "supplier_id": task.get("supplier_id"),
        "items": items,
        "items_count": items_count,
        "market_avg": market_avg,
        "market_min": market_min,
        "market_max": market_max,
        "market_source": task.get("market_source", "mock-market"),
        "market_sample": int(task.get("market_sample", 0) or 0),
        "compliance_ok": bool(task.get("compliance_ok", False)),
        "compliance_reasoning": task.get("compliance_reasoning", ""),
        "matched_rules": task.get("matched_rules", []) or [],
        "opa_decision": task.get("opa_decision", "escalate"),
        "opa_deny_reasons": task.get("opa_deny_reasons", []) or [],
        "opa_escalate_reasons": task.get("opa_escalate_reasons", []) or [],
        "policy_version": task.get("policy_version", "unknown"),
        "generated_at": generated_at,
        "confidence": confidence,
    }

    pzd_text = env.get_template("pzd.j2").render(**context)
    contract_text = env.get_template("contract.j2").render(**context)


    return {
        "pzd_text": pzd_text,
        "contract_draft_text": contract_text,
        "confidence": confidence,
        "generated_at": generated_at,
        "documents": [
            {"type": "pzd", "format": "markdown", "size": len(pzd_text)},
            {"type": "contract_draft", "format": "markdown", "size": len(contract_text)},
        ],
    }


app = create_worker_app(AGENT_NAME, AGENT_SVID, handle_task)
