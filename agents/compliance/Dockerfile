FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.0 "uvicorn[standard]==0.32.0" pydantic==2.9.2 pyyaml==6.0.2 httpx==0.27.2
COPY agents/workers/base.py /app/
COPY agents/compliance/main.py /app/
COPY agents/compliance/rag.py /app/
COPY agents/compliance/llm.py /app/
COPY agents/compliance/policies/ /app/policies/
COPY contracts/ /app/contracts/
EXPOSE 9003
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9003"]
