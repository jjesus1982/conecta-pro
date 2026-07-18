"""
Financial MCP Server — Conecta PRO
8 ferramentas financeiras da Conecta Mais via Model Context Protocol.
Dados 100% reais via API interna autenticada.

Não requer a biblioteca 'mcp' — implementação standalone com httpx.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta

import httpx

logger = logging.getLogger(__name__)

API_BASE = os.getenv("API_BASE_URL", "http://localhost:8080/api/v1")
_cached_token: str | None = None
_token_expiry: datetime | None = None


async def _get_token() -> str:
    """Token de serviço com cache de 50 minutos."""
    global _cached_token, _token_expiry

    if _cached_token and _token_expiry and datetime.now() < _token_expiry:
        return _cached_token

    email = os.getenv("MCP_SERVICE_EMAIL", "jjesus@conectamais.pro")
    password = os.getenv("MCP_SERVICE_PASSWORD", "JsJ618908@#%")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"{API_BASE}/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        data = resp.json()
        _cached_token = data.get("access_token", "")
        _token_expiry = datetime.now() + timedelta(minutes=50)
        return _cached_token


async def _get(endpoint: str) -> dict:
    """GET autenticado com retry em caso de 401."""
    global _cached_token
    token = await _get_token()
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{API_BASE}{endpoint}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 401:
            # Token expirou — forçar refresh
            _cached_token = None
            token = await _get_token()
            resp = await client.get(
                f"{API_BASE}{endpoint}",
                headers={"Authorization": f"Bearer {token}"},
            )
        return resp.json()


# ── 8 Ferramentas MCP ───────────────────────────────────────────────────────────


async def get_financial_summary() -> dict:
    """Resumo financeiro completo: saldo, MRR, compliance, health score."""
    dashboard = await _get("/financial/dashboard")
    banking = await _get("/integrations/banking/balances")
    saldo_inter = 0.0
    balances = banking.get("balances", [])
    if balances:
        saldo_inter = float(balances[0].get("balance", 0))
    saude = dashboard.get("saude_financeira", {})
    return {
        "empresa": "GRUPO CONECTA MAIS (2 CNPJs — dados CONSOLIDADOS salvo indicação)",
        "estrutura": [
            {"razao": "CONECTAMAIS ELETRONICA LTDA", "papel": "seg. eletrônica/portaria remota",
             "regime": "Lucro Real", "banco": "Inter 077"},
            {"razao": "CONECTAMAIS PATRIMONIAL LTDA", "papel": "terceirização de mão de obra",
             "regime": "Simples Nacional", "banco": "Cora 403"},
        ],
        "timestamp": datetime.now().isoformat(),
        "saldo_inter": saldo_inter,
        "nota": "saldo_inter = só conta Inter (Eletrônica); saldo Cora (Patrimonial) via extrato/bank_transactions",
        "mrr_bruto": dashboard.get("mrr", 0),
        "saude_score": saude.get("score", 0),
        "saude_classificacao": saude.get("classificacao", ""),
        "alertas": saude.get("alertas", []),
        "entradas_mes": dashboard.get("mes_atual", {}).get("entradas", 0),
        "saidas_mes": dashboard.get("mes_atual", {}).get("saidas", 0),
        "contas_pagar_total": dashboard.get("contas_pagar", {}).get("total", 0),
        "contas_receber_total": dashboard.get("contas_receber", {}).get("total", 0),
    }


async def get_cashflow_status() -> dict:
    """Fluxo de caixa: saldo atual, entradas/saídas, projeção 30d."""
    return await _get("/financial/cashflow/cashflow/dashboard")


async def get_overdue_receivables() -> dict:
    """Inadimplentes com aging (até 30d, 31-60d, 60d+), valor total."""
    return await _get("/financial/receivables/aging")


async def get_kpis() -> dict:
    """KPIs financeiros em tempo real."""
    return await _get("/financial/bi/kpis")


async def get_agents_status() -> dict:
    """Status dos agentes GEDEON: skills carregadas, schedules."""
    return await _get("/financial/ai/agents/status")


async def get_lucro_real_compliance() -> dict:
    """Compliance Lucro Real: % classificadas, sem categoria, valor pendente."""
    return await _get("/justificativa/compliance")


async def get_aging_report() -> dict:
    """Aging completo: contas a pagar e receber por faixa de vencimento."""
    payables = await _get("/financial/payables/aging")
    receivables = await _get("/financial/receivables/aging")
    return {
        "contas_pagar": payables,
        "contas_receber": receivables,
        "timestamp": datetime.now().isoformat(),
    }


async def get_forecast() -> dict:
    """Projeção cashflow 30/60/90 dias — 3 cenários."""
    return await _get("/financial/cashflow/forecast")


async def get_custeio_abc() -> dict:
    """Custeio ABC por tipo de serviço: margem real, classificação estrela/atenção/abacaxi, CCT SINDECOMPRESTS 2026."""
    return await _get("/financial/custeio/abc")


async def get_precificacao_analise() -> dict:
    """Contratos subprecificados vs benchmarks Manaus 2026: potencial de reajuste mensal e anual."""
    return await _get("/financial/precificacao/contratos/analise")


async def get_bi_kpis() -> dict:
    """KPIs financeiros ao vivo: MRR, saldo Inter, compliance Lucro Real, inadimplência, score saúde 0-100."""
    return await _get("/financial/bi/kpis")


async def get_bi_dashboards() -> dict:
    """Configuração dos dashboards BI com widgets, métricas e alertas do painel executivo."""
    return await _get("/financial/bi/dashboards")


# ── Registro das ferramentas ────────────────────────────────────────────────────

MCP_TOOLS: dict = {
    "get_financial_summary": get_financial_summary,
    "get_cashflow_status": get_cashflow_status,
    "get_overdue_receivables": get_overdue_receivables,
    "get_kpis": get_kpis,
    "get_agents_status": get_agents_status,
    "get_lucro_real_compliance": get_lucro_real_compliance,
    "get_aging_report": get_aging_report,
    "get_forecast": get_forecast,
    "get_custeio_abc": get_custeio_abc,
    "get_precificacao_analise": get_precificacao_analise,
    "get_bi_kpis": get_bi_kpis,
    "get_bi_dashboards": get_bi_dashboards,
}

MCP_TOOLS_SCHEMA: list = [
    {
        "name": "get_financial_summary",
        "description": (
            "Resumo financeiro Conecta Mais: saldo Inter, MRR, health score, alertas. "
            "Use para visão geral rápida do estado financeiro da empresa."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_cashflow_status",
        "description": (
            "Fluxo de caixa: saldo atual (ao vivo do Inter), entradas/saídas dos últimos 7d "
            "e projeção 30d. Use para análise de liquidez e planejamento de caixa."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_overdue_receivables",
        "description": (
            "Inadimplência com aging por faixa: até 30d, 31-60d, acima 60d. "
            "Retorna valor total em atraso e quantidade de clientes inadimplentes."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_kpis",
        "description": (
            "KPIs financeiros ao vivo: MRR R$270k, margem, liquidez, inadimplência. "
            "Use para monitoramento contínuo de performance financeira."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_agents_status",
        "description": (
            "Status dos 8 agentes GEDEON Layer 2: skills carregadas vs. ausentes, schedules de execução. "
            "Use para diagnóstico do sistema de inteligência financeira."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_lucro_real_compliance",
        "description": (
            "Compliance Lucro Real: 616/616 transações classificadas (100%), "
            "zero pendentes críticos, valor justificado R$177k."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_aging_report",
        "description": (
            "Aging completo: contas a pagar e receber agrupadas por faixa de vencimento. "
            "Essencial para gestão de fluxo de caixa e negociação com fornecedores/clientes."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_forecast",
        "description": (
            "Projeção de cashflow 30/60/90 dias nos cenários pessimista, esperado e otimista. "
            "Base: MRR R$270k, histórico banco Inter."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_custeio_abc",
        "description": (
            "Custeio ABC por tipo de serviço (kit_mensal, portaria_remota, cftv, taxa_condominial). "
            "Margem real calculada com CCT SINDECOMPRESTS 2026 (custo all-in R$3.354,74/posto). "
            "Classifica cada tipo: estrela (≥35%), atenção (20-35%), abacaxi (<20%)."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_precificacao_analise",
        "description": (
            "Contratos ativos comparados com benchmarks Manaus 2026 (vigilante diurno R$2.800-3.800/posto). "
            "Identifica subprecificados, calcula potencial de reajuste mensal e anual por contrato."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_bi_kpis",
        "description": (
            "KPIs financeiros ao vivo da tabela financial_kpis: MRR R$272k, saldo Inter, "
            "compliance Lucro Real, inadimplência em %, score saúde financeira 0-100."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_bi_dashboards",
        "description": (
            "Configuração dos dashboards BI com widgets, métricas e alertas do painel executivo. "
            "Use para entender estrutura dos painéis e quais indicadores estão sendo monitorados."
        ),
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
]


# ── Handler MCP protocol ────────────────────────────────────────────────────────


async def handle_mcp_request(request: dict) -> dict:
    """Processa requisição no formato MCP (tools/list ou tools/call)."""
    method = request.get("method", "")

    if method == "tools/list":
        return {"tools": MCP_TOOLS_SCHEMA}

    if method == "tools/call":
        params = request.get("params", {})
        tool_name = params.get("name", "")
        if tool_name not in MCP_TOOLS:
            return {
                "error": {
                    "code": -32601,
                    "message": f"Tool '{tool_name}' não encontrada. Disponíveis: {list(MCP_TOOLS.keys())}",
                }
            }
        try:
            result = await MCP_TOOLS[tool_name]()
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, default=str),
                    }
                ]
            }
        except Exception as exc:
            logger.exception("Erro na ferramenta MCP %s", tool_name)
            return {"error": {"code": -32603, "message": str(exc)}}

    return {
        "error": {
            "code": -32601,
            "message": f"Método '{method}' não suportado. Use 'tools/list' ou 'tools/call'.",
        }
    }


# ── Teste standalone ────────────────────────────────────────────────────────────

if __name__ == "__main__":

    async def _test() -> None:
        print(f"=== MCP Financial Server — {len(MCP_TOOLS)} ferramentas ===\n")
        for name, func in MCP_TOOLS.items():
            print(f"--- {name} ---")
            try:
                result = await func()
                preview = json.dumps(result, ensure_ascii=False, default=str)[:300]
                print(preview)
            except Exception as exc:
                print(f"ERRO: {exc}")
            print()

    asyncio.run(_test())
