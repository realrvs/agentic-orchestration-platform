import json
from pathlib import Path
from typing import Any
import yaml
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

CONTRACTS_DIR = Path(__file__).resolve().parent / "contracts"

def create_worker_app(agent_name: str, agent_svid: str, handler) -> FastAPI:
    app = FastAPI(title=f"{agent_name.capitalize()} Agent")

    class TaskRequest(BaseModel):
        task: dict[str, Any]
        caller_svid: str

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent": agent_name}

    @app.get("/contract")
    async def get_contract():
        contract_path = CONTRACTS_DIR / f"{agent_name}_agent.yaml"
        if not contract_path.exists():
            raise HTTPException(status_code=500, detail=f"Contract not found: {contract_path}")
        with open(contract_path) as f:
            return yaml.safe_load(f)

    @app.post("/a2a/task")
    async def handle_task(request: TaskRequest, raw_request: Request):
        try:
            return await handler(request.task)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app