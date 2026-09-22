# Agentic Orchestration Platform

**Мультиагентная платформа оркестрации** с протоколом A2A (Agent-to-Agent), формальными контрактами, WIMSE-идентичностью и policy enforcement через OPA/Rego.

Референсная реализация паттернов из [enterprise-agent-orchestration-blueprint](https://github.com/realrvs/enterprise-agent-orchestration-blueprint) — разделы **3.1 (Иерархическая оркестрация)**, **3.2 (A2A-протокол)**, **4.1 (Agent Policies)**, **4.2 (WIMSE Identity)**.

---

## Содержание

1. [Что это](#что-это)
2. [Архитектура](#архитектура)
3. [Быстрый старт](#быстрый-старт)
4. [Сервисы](#сервисы)
5. [Компоненты](#компоненты)
6. [Безопасность](#безопасность)
7. [Конфигурация](#конфигурация)
8. [Verified Scenarios](#verified-scenarios)
9. [Дорожная карта](#дорожная-карта)
10. [Структура репозитория](#структура-репозитория)
11. [Связь с Blueprint](#связь-с-blueprint)
12. [Ссылки](#ссылки)

---

## Что это

End-to-end PoC автоматизации закупок по 223-ФЗ. Полный конвейер от заявки до проекта договора — **8 микросервисов**, работающих на моках и реальной логике:

```text
Orchestrator (9000)
    ├─→ Sourcing (9001)   ──→ Mock-1С (9101)           [ЕСУ НСИ, номенклатура]
    ├─→ Pricing (9002)    ──→ Mock-Market (9102)       [рыночные цены, НМЦ]
    ├─→ Compliance (9003) ──→ RAG (10 ЛНА)             [223-ФЗ + локальные акты]
    ├─→ OPA (9210)        ──→ procurement.rego         [allow | escalate | deny]
    └─→ Document (9004)   ──→ Jinja2 (ПЗД + договор)   [финальные документы]
```

**Verified scenario:** закупка серверного оборудования на 1,5 млн руб. → `allow` за секунды (вместо 8 дней вручную).

---

## Архитектура

### Слои

| Слой | Компонент | Технология |
| --- | --- | --- |
| **Orchestration** | Orchestrator Agent | FastAPI + httpx |
| **Workers** | Sourcing, Pricing, Compliance, Document | FastAPI + `base.py` |
| **Policy** | OPA | Rego v1 |
| **Integration** | MCP Gateway | SSE + JSON-RPC 2.0 |
| **Identity** | WIMSE SVID | `spiffe://company.ru/agents/*` |
| **RAG** | VectorStore abstraction | InMemory (default) \| Qdrant |
| **LLM** | LLM abstraction | stub (default) \| ollama |
| **Templates** | Jinja2 | pzd.j2 + contract.j2 |

### C4 Level 1 — System Context

```text
┌─────────────────────────────────────────────────────────────────┐
│  System Context — Agentic Orchestration Platform               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌──────────┐                          ┌──────────┐            │
│   │  Client  │──POST /a2a/task─────────▶│ Platform │            │
│   └──────────┘                          │  (8 svc) │            │
│                                         └────┬─────┘            │
│   ┌──────────┐                               │                  │
│   │ Operator │──GET /health, /contract──────▶│                  │
│   └──────────┘                               │                  │
│                                              ▼                  │
│                                         ┌──────────┐            │
│                                         │   OPA    │            │
│                                         │ (policy) │            │
│                                         └──────────┘            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### C4 Level 2 — Containers

```text
┌─────────────────────────────────────────────────────────────────┐
│  Docker Compose — aop-network                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   Client ──▶ Orchestrator Agent  (FastAPI / Python :9000)       │
│                    │                                            │
│                    ├──▶ Sourcing Agent   (FastAPI :9001)        │
│                    │         └──▶ Mock-1С  (FastAPI :9101)      │
│                    │                                            │
│                    ├──▶ Pricing Agent    (FastAPI :9002)        │
│                    │         └──▶ Mock-Market (FastAPI :9102)   │
│                    │                                            │
│                    ├──▶ Compliance Agent (FastAPI :9003)        │
│                    │         └──▶ RAG (10 ЛНА)                  │
│                    │                                            │
│                    ├──▶ Document Agent   (FastAPI :9004)        │
│                    │         └──▶ Jinja2 (ПЗД + договор)        │
│                    │                                            │
│                    └──▶ OPA              (Rego v1 :9210)        │
│                              └──▶ procurement.rego              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Быстрый старт

### Требования

- Docker Desktop >= 4.89 (Compose v5+)
- PowerShell (Windows) или Bash (Linux/macOS)

### 1. Запустить все сервисы

```powershell
docker compose up --build -d
docker compose ps
```

Ожидаемо — **8 контейнеров** в статусе `Up`:

```text
aop-orchestrator   :9000
aop-sourcing       :9001
aop-pricing        :9002
aop-compliance     :9003
aop-document       :9004
aop-opa            :9210
aop-mock-1c        :9101
aop-mock-market    :9102
```

### 2. Health-check

```powershell
9000..9004 | ForEach-Object { Invoke-RestMethod "http://localhost:$_/health" }
Invoke-RestMethod "http://localhost:9101/health"
Invoke-RestMethod "http://localhost:9102/health"
```

### 3. Полный сценарий — закупка серверного оборудования

```powershell
$body = @{
    task_type = "procurement"
    payload   = @{
        lot_id   = "LOT-001"
        amount   = 1500000
        region   = "Moscow"
        category = "server hardware"
    }
    context   = @{}
} | ConvertTo-Json -Depth 10

$response = Invoke-RestMethod -Uri "http://localhost:9000/a2a/task" `
    -Method Post -ContentType "application/json" -Body $body

$response.decision
$response.reasoning
$response.document.documents | Format-Table -AutoSize
```

Ожидаемый результат:

```text
decision:   allow
reasoning:  sourcing: OK; pricing: OK; compliance: OK; document: OK; opa: allow

documents:
type              format     size
----              ------     ----
pzd               markdown   2026
contract_draft    markdown   3045
```

---

## Сервисы

| Сервис | Порт | Назначение | Технология |
| --- | --- | --- | --- |
| `orchestrator` | 9000 | Координация, агрегация confidence, policy enforcement | FastAPI |
| `sourcing` | 9001 | Номенклатура, ЕСУ НСИ | MCP → mock-1c |
| `pricing` | 9002 | НМЦ, рыночные цены | MCP → mock-market |
| `compliance` | 9003 | 223-ФЗ + ЛНА через RAG | VectorStore + LLM |
| `document` | 9004 | ПЗД + проект договора | Jinja2 |
| `opa` | 9210 | Policy enforcement | Rego v1 |
| `mock-1c` | 9101 | Эмуляция 1С (ЕСУ НСИ) | SSE + JSON-RPC 2.0 |
| `mock-market` | 9102 | Эмуляция рыночных цен | SSE + JSON-RPC 2.0 |

---

## Компоненты

### Orchestrator Agent

- Принимает `{"task_type": "procurement", "payload": {...}}`
- Вызывает Sourcing → Pricing (если `nomenclature_ok`) → Compliance
- Агрегирует `avg_confidence`
- Вызывает OPA с полным контекстом
- Если `decision == "allow"` → вызывает Document Agent
- Возвращает: `decision`, `confidence`, `reasoning`, `opa`, `document`, `worker_results`

### Sourcing Agent

- Дёргает Mock-1С через MCP: `get_lot_data`
- Fallback на stub при недоступности MCP
- Возвращает: `lot_data.items[]`, `nomenclature_ok`, `confidence`, `source`

### Pricing Agent

- Дёргает Mock-Market через MCP: `get_market_prices`
- Fallback на stub
- Возвращает: `nmc_value`, `market{avg,min,max}`, `confidence`, `source`

### Compliance Agent

- RAG-поиск по 10 атомарным ЛНА (keyword-based в `InMemoryVectorStore`)
- LLM-режимы: `stub` (default, для CI/CD) \| `ollama` (для демо)
- Возвращает: `compliance_ok`, `reasoning`, `confidence`, `matched_rules`, `violations`

### Document Agent

- Jinja2-шаблоны: `pzd.j2`, `contract.j2`
- Вызывается только при `opa.decision == "allow"`
- Возвращает: `pzd_text`, `contract_draft_text`, `confidence`, `generated_at`, `documents[]`

### OPA Policy

- `policies/procurement.rego` — решение `allow | escalate | deny`
- Лимиты: `max_amount = 50M`, `min_confidence = 0.85`
- Allow-list регионов: Moscow, Saint-Petersburg, Novosibirsk
- Проверки: `amount`, `confidence`, `nomenclature_ok`, `compliance_ok`, `region`

---

## Безопасность

### WIMSE SVID

Каждый агент имеет уникальный SPIFFE-ID:

```text
spiffe://company.ru/agents/orchestrator_v1
spiffe://company.ru/agents/sourcing_v1
spiffe://company.ru/agents/pricing_v1
spiffe://company.ru/agents/compliance_v1
spiffe://company.ru/agents/document_v1
```

Передаётся в заголовке `X-Agent-SVID` на каждом A2A/MCP-вызове. Mock-серверы проверяют SVID по allow-list.

### Policy Enforcement

OPA проверяет **каждое** решение перед финализацией. Никакие агенты не могут обойти политику — Orchestrator всегда вызывает OPA.

---

## Конфигурация

### LLM (Compliance Agent)

```yaml
environment:
  LLM_MODE: "stub"     # stub | ollama
  OLLAMA_URL: "http://ollama:11434"
```

### VectorStore (Compliance Agent)

```yaml
environment:
  VECTOR_STORE: "memory"   # memory | qdrant
```

### MCP timeout (Sourcing, Pricing)

```yaml
environment:
  MCP_TIMEOUT: "5.0"
```

### Fallback

Все агенты имеют fallback на stub при недоступности MCP — PoC не падает.

---

## Verified Scenarios

| Scenario | Input | Ожидаемый output |
| --- | --- | --- |
| **Allow** | amount=1.5M, category=server hardware | `decision: allow`, документы сформированы |
| **Deny (amount)** | amount=75M | `decision: deny`, `deny_reasons: ["amount 75000000 exceeds max_amount 50000000"]` |
| **Deny (compliance)** | compliance_ok=false | `decision: deny`, `deny_reasons: ["compliance_ok is false"]` |
| **Escalate** | confidence < 0.85 | `decision: escalate`, документы не формируются |

---

## Дорожная карта

- [x] Multi-agent A2A (Orchestrator + 4 worker'а)
- [x] WIMSE SVID на всех вызовах
- [x] MCP Gateway → Mock-1С, Mock-Market
- [x] Compliance Agent + RAG (10 ЛНА)
- [x] OPA/Rego policy enforcement
- [x] Document Agent (Jinja2: ПЗД + договор)
- [ ] Camunda User Task + Form (Human-in-the-Loop для escalate)
- [ ] Hash-chain audit trail
- [ ] Qdrant + Ollama для production-grade RAG
- [ ] Реальные интеграции с 1С, ЕИС, SAP (через MCP Gateway)

---

## Структура репозитория

```text
agentic-orchestration-platform/
├── agents/
│   ├── orchestrator/      # A2A координация + OPA + Document
│   ├── workers/
│   │   ├── base.py        # Общий FastAPI-каркас для worker'ов
│   │   ├── sourcing.py    # Sourcing Agent
│   │   ├── pricing.py     # Pricing Agent
│   │   ├── Dockerfile.sourcing
│   │   └── Dockerfile.pricing
│   ├── compliance/        # Compliance Agent + RAG + 10 ЛНА
│   │   ├── main.py
│   │   ├── rag.py         # VectorStore abstraction
│   │   ├── llm.py         # LLM abstraction
│   │   └── policies/      # 10 атомарных .md ЛНА
│   └── document/          # Document Agent + Jinja2
│       ├── main.py
│       └── templates/
│           ├── pzd.j2
│           └── contract.j2
├── mcp/
│   ├── mock_1c_mcp_server.py
│   ├── mock_market_mcp_server.py
│   └── fixtures/
│       ├── nomenclature.json
│       └── market_prices.json
├── policies/
│   ├── procurement.rego   # OPA policy
│   └── data.json          # Limits, regions
├── contracts/
│   ├── compliance_agent_v1.yaml
│   └── document_agent.yaml
├── docker-compose.yml     # 8 сервисов
└── README.md
```

---

## Связь с Blueprint

| Раздел blueprint | Реализация |
| --- | --- |
| **3.1 Иерархическая оркестрация** | Orchestrator + Worker-агенты |
| **3.2.1 Контракты агентов** | YAML-контракты в `contracts/` |
| **3.2.2 Шина сообщений** | A2A на HTTP (в production: RabbitMQ) |
| **4.1 Agent Policies** | OPA/Rego (`policies/procurement.rego`) |
| **4.2 WIMSE-идентичность** | Заголовок `X-Agent-SVID` на каждом вызове |
| **4.3 Immutable Audit** | Запланировано (hash-chain roadmap) |

---

## Ссылки

- **Blueprint:** [github.com/realrvs/enterprise-agent-orchestration-blueprint](https://github.com/realrvs/enterprise-agent-orchestration-blueprint)
- **Reference PoC (BPMN + LLM + Policy):** [github.com/realrvs/agentic-orchestration-poc](https://github.com/realrvs/agentic-orchestration-poc)
- **MCP Gateway PoC:** [github.com/realrvs/mcp-gateway-poc](https://github.com/realrvs/mcp-gateway-poc)