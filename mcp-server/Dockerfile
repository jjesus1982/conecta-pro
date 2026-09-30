FROM python:3.12-slim

# De qual commit esta imagem nasceu. Sem isto não havia como responder "o que está no ar é
# o que está no git?" — e não havia: a imagem em produção ficou 11 dias atrás da fonte, com
# a parede de testes vermelha, e ninguém soube. O default `desconhecido` é recusado pelo
# vigia de propósito: imagem sem procedência conta como deriva.
ARG GIT_SHA=desconhecido
LABEL br.pro.conectamais.mcp.git_sha=$GIT_SHA

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
COPY carimbo.py .
COPY pendencias.py .
COPY lgpd_escopo.py .
COPY changelog.json .
COPY test_identidade.py .
COPY test_segundo_plano.py .
COPY test_efeito_externo.py .
COPY test_capabilities_sem_fantasma.py .
COPY test_lgpd_escopo.py .
COPY test_envelope_de_erro.py .
COPY test_defaults_nao_apagam.py .
# trava: modo bearer sem token (ou com token curto) NÃO sobe — fail-closed no import
COPY test_bearer_fail_closed.py .
# a varredura paramétrica roda DENTRO da imagem: fora dela mede outro código
COPY varredura_envelope.py .
# ⚠️ a suíte de regressão vai na imagem mas NÃO roda no build: ela exige o ERP de pé.
# Parede de build não pode depender de produção — aprendido derrubando o build hoje.
COPY test_regressao_mcp.py .
# 12/09/2026: os 21 aceites rodavam SÓ do disco — nunca estiveram na imagem, então
# `docker exec … test_aceites_cowork.py` falhava com "No such file". Suíte que não
# acompanha o artefato mede o computador de quem a rodou, não o que subiu.
COPY test_aceites_cowork.py .

# Parede 1: lint fail-closed — build quebra se tool MCP nascer sem classe de risco
RUN python test_tool_risk_manifest.py && python test_read_nao_escreve.py && python test_identidade.py && python test_segundo_plano.py && python test_efeito_externo.py && python test_capabilities_sem_fantasma.py && python test_lgpd_escopo.py && python test_envelope_de_erro.py && python test_defaults_nao_apagam.py && python test_bearer_fail_closed.py

EXPOSE 8788

# Streamable HTTP MCP em /mcp + /healthz
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8788"]
