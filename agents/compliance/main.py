"""
Compliance Agent — worker в agentic-orchestration-platform.

Формат A2A-запроса: {"task": {...}, "caller_svid": "..."} (совместим с base.py).
Ответ: compliance_ok, reasoning, confidence, matched_rules, violations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from base import create_worker_app

from llm import build_llm
from rag import build_store, load_rules

AGENT_NAME = "compliance"
AGENT_SVID = "spiffe://company.ru/agents/compliance_v1"

POLICIES_DIR = Path(__file__).parent / "policies"

store = build_store()
store.add_rules(load_rules(POLICIES_DIR))
llm = build_llm()


async def handle_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    Принимает task от Orchestrator:
      {
        "lot_id": "...",
        "amount": 1500000,
        "region": "Moscow",
        "category": "server hardware",
        "nmc_value": 285000
      }
    Возвращает:
      {
        "compliance_ok": bool,
        "reasoning": str,
        "confidence": float,
        "matched_rules": [str],
        "violations": [str]
      }
    """
    lot_id = task.get("lot_id", "unknown")
    amount = task.get("amount", 0) or 0
    region = task.get("region", "Moscow")
    category = task.get("category", "") or ""

    query = f"{category} {region} {amount}"
    rules = store.search(query, top_k=3)
    result = llm.evaluate(query, rules)

    return {
        "compliance_ok": result.compliance_ok,
        "reasoning": result.reasoning,
        "confidence": result.confidence,
        "matched_rules": [r.rule_id for r in rules],
        "violations": result.violations,
    }


app = create_worker_app(AGENT_NAME, AGENT_SVID, handle_task)
