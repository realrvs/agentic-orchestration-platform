"""
LLM abstraction for Compliance Agent.

- stub   — детерминированный JSON, мгновенный ответ, для CI/CD
- ollama — Mistral 7B (или Qwen/Llama3) через httpx

Переключение через env: LLM_MODE=stub|ollama
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import List

from rag import Rule


@dataclass
class LLMResult:
    compliance_ok: bool
    reasoning: str
    confidence: float
    violations: List[str]


class StubLLM:
    """Детерминированный ответ для CI/CD."""

    def evaluate(self, query: str, rules: List[Rule]) -> LLMResult:
        violations: List[str] = []
        for r in rules:
            low = r.text.lower()
            if ("запрещ" in low or "не допускается" in low) and any(
                w in low for w in query.lower().split()
            ):
                violations.append(r.rule_id)

        if violations:
            return LLMResult(
                compliance_ok=False,
                reasoning=f"Stub: обнаружены нарушения в правилах: {', '.join(violations)}",
                confidence=0.92,
                violations=violations,
            )
        return LLMResult(
            compliance_ok=True,
            reasoning="Stub: нарушений не обнаружено, закупка соответствует 223-ФЗ и ЛНА",
            confidence=0.95,
            violations=[],
        )


class OllamaLLM:
    def __init__(self, model: str = "mistral:7b-instruct-q4_K_M") -> None:
        self._model = model
        self._url = os.getenv("OLLAMA_URL", "http://ollama:11434")

    def evaluate(self, query: str, rules: List[Rule]) -> LLMResult:
        import httpx
        context = "\n\n".join(f"[{r.rule_id}] {r.text}" for r in rules)
        prompt = (
            "Ты — compliance-агент в системе закупок по 223-ФЗ.\n"
            "Проанализируй заявку и найденные правила. Верни ТОЛЬКО JSON:\n"
            '{"compliance_ok": bool, "reasoning": str, "confidence": float, "violations": [str]}\n\n'
            f"Заявка: {query}\n\nПравила:\n{context}\n"
        )
        r = httpx.post(
            f"{self._url}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=120.0,
        )
        r.raise_for_status()
        
        raw_response = r.json()["response"].strip()
        # Очистка возможной markdown-обёртки ```json ... ```
        raw_response = re.sub(r"^```(?:json)?\s*", "", raw_response, flags=re.IGNORECASE)
        raw_response = re.sub(r"\s*```$", "", raw_response)
        
        payload = json.loads(raw_response)
        return LLMResult(
            compliance_ok=bool(payload["compliance_ok"]),
            reasoning=str(payload["reasoning"]),
            confidence=float(payload["confidence"]),
            violations=list(payload.get("violations", [])),
        )


def build_llm():
    mode = os.getenv("LLM_MODE", "stub").lower()
    if mode == "ollama":
        return OllamaLLM()
    return StubLLM()
