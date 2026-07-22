FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY tool_risk_manifest.py .
COPY test_tool_risk_manifest.py .

# Parede 1: lint fail-closed — build quebra se tool MCP nascer sem classe de risco
RUN python test_tool_risk_manifest.py

EXPOSE 8788

# Streamable HTTP MCP em /mcp + /healthz
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8788"]
