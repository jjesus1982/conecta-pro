FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY tool_risk_manifest.py .
# escopo do catálogo por assunto — sem ele o filtro MCP_ESCOPO não aplica
COPY tool_scopes.py .
# F1: a parede que faz a etiqueta de risco AGIR (sem ela, conector de agente NAO sobe)
COPY gate_propose.py .
COPY gate_escopo.py .
COPY identidade.py .
COPY test_tool_risk_manifest.py .
# trava: quem se diz `read` prova que nao escreve (SQL/verbo HTTP no corpo)
COPY test_read_nao_escreve.py .
COPY changelog.json .
COPY test_identidade.py .
COPY test_segundo_plano.py .

# Parede 1: lint fail-closed — build quebra se tool MCP nascer sem classe de risco
RUN python test_tool_risk_manifest.py && python test_read_nao_escreve.py && python test_identidade.py && python test_segundo_plano.py

EXPOSE 8788

# Streamable HTTP MCP em /mcp + /healthz
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8788"]
