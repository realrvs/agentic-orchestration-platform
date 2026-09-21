FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.0 "uvicorn[standard]==0.32.0" httpx==0.27.2 pydantic==2.9.2 pyyaml==6.0.2
COPY agents/orchestrator/main.py /app/
COPY contracts/ /app/contracts/
EXPOSE 9000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]