"""Tools GERA-DOC FINANCEIRO (Fase 6, Fatia 3) — módulo financeiro, scope_kind="org".

No chat escopado, quem tem o módulo `financeiro` (= diretoria: jjesus/pjesus) pede
"gera o DRE", "balancete do mês", "fluxo de caixa" e recebe o PDF branded — dos números
REAIS apurados sobre accounting_entries pelos serviços reais, NUNCA fabricados pelo LLM.

Reusa 1:1 as funções de dados e a montagem de seções dos endpoints /relatorios/*/pdf
(get_dre / balancete_real / FluxoCaixaService.dfc_mensal + _dre_pdf_bytes / _balancete_pdf_bytes /
_fluxo_caixa_pdf_bytes) — o chat não recalcula nada.

Paredes (inegociáveis):
- Números SÓ dos serviços reais; o LLM nunca passa valor. Período sem lançamento → RECUSA (não
  gera DRE/balancete vazio como se fosse real).
- Doc INTERNO de gestão (diretoria) — não é material de cliente; pode conter tudo. Belt financeiro
  gateia (só diretoria) + `_gate` re-checa (suspenders).
- Não move dinheiro, NÃO lança/edita accounting_entries. Fail-closed. (Ressalva honesta: o fluxo
  de caixa reusa dfc_mensal, que faz um UPDATE idempotente de CATEGORIZAÇÃO em bank_transactions
  antes de ler — não é razão nem movimento financeiro, é o mesmo efeito do endpoint /fluxo-caixa/pdf.)
- empresa_id / multi-CNPJ:
  * Fluxo de caixa é POR CNPJ (Inter=Eletrônica, Cora=Patrimonial). Exige a empresa; sem ela →
    RECUSA pedindo qual (não assume um CNPJ default).
  * DRE e Balancete, hoje, são apurados CONSOLIDADOS do grupo (as queries de accounting_entries/
    NFS-e não filtram empresa). Não dá pra recortar por CNPJ sem reescrever o serviço → saem
    rotulados honestamente como "grupo consolidado (todas as empresas)", nunca como um CNPJ só.
  * Aging (contas a receber/pagar) idem: receivable_accounts/payable_accounts NÃO têm coluna
    empresa_id (chaveiam condominio/cliente/fornecedor) → aging é intrinsecamente CONSOLIDADO;
    sai rotulado como grupo consolidado, sem parâmetro de empresa (aceitar um seria mentira).
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register

_MANAUS = ZoneInfo("America/Manaus")
_CONSOLIDADO = "grupo consolidado (todas as empresas)"


def _gate(user) -> None:
    if not user_has_module(user, "financeiro"):
        raise PermissionError("financeiro")


def _recusa(motivo: str) -> dict[str, Any]:
    return {"status": "recusado", "motivo": motivo}


def _int_pos(v) -> int | None:
    try:
        n = int(v)
    except (ValueError, TypeError):
        return None
    return n if n > 0 else None


def _periodo(mes, ano) -> tuple[int | None, int]:
    """(mes|None, ano). Default ano = ano corrente TZ Manaus; mês só se 1..12."""
    a = _int_pos(ano) or datetime.now(_MANAUS).year
    m = _int_pos(mes)
    return (m if m and 1 <= m <= 12 else None), a


def _brl(v) -> str:
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return str(v)


async def _gerar_dre_doc(db, user, scope, *, mes=None, ano=None, **_) -> dict[str, Any]:
    _gate(user)
    m, a = _periodo(mes, ano)
    from modules.financial.controllers.relatorios_controller import _dre_pdf_bytes, get_dre
    # get_dre apura sobre o razão real (accounting_entries + NFS-e); consolidado do grupo.
    dados = await get_dre(ano=a, mes_inicio=(m or 1), mes_fim=(m or 12), comparativo=False,
                          condominio_id=None, db=db, _current_user=user)
    grupos = dados.get("grupos", [])
    ver = dados.get("veracidade") or {}
    # RECUSA fail-closed: DRE sem NADA de real no período. "receita estimada por contratos" (sem NFS-e)
    # SOMADA a zero folha lançada = DRE puramente projetado → não é apuração real, não gero.
    tem_valor = any(abs(float(g.get("valor") or 0)) > 0.005 for g in grupos)
    so_projecao = bool(ver.get("receita_estimada")) and int(ver.get("meses_com_folha_lancada") or 0) == 0
    if not grupos or not tem_valor or so_projecao:
        return _recusa(f"sem lançamento real no período ({a}{f'/{m:02d}' if m else ''}) para apurar o DRE; "
                       "não vou gerar um DRE só com projeção/estimativa como se fosse real.")
    pdf = _dre_pdf_bytes(dados, a, escopo=_CONSOLIDADO)
    ll = next((float(g.get("valor") or 0) for g in grupos
               if g.get("grupo") in ("lucro_liquido", "resultado_liquido")), None)
    aviso = ver.get("aviso")
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"dre_{a}{f'_{m:02d}' if m else ''}.pdf",
        "resumo": f"DRE {a}{f'/{m:02d}' if m else ''} — {_CONSOLIDADO}"
                  + (f", lucro líquido {_brl(ll)}" if ll is not None else "")
                  + " (números reais do razão; doc INTERNO de gestão)"
                  + (f". Atenção: {aviso}" if aviso else ""),
    }


async def _gerar_balancete_doc(db, user, scope, *, mes=None, ano=None, **_) -> dict[str, Any]:
    _gate(user)
    m, a = _periodo(mes, ano)
    from modules.financial.controllers.relatorios_controller import _balancete_pdf_bytes, balancete_real
    dados = await balancete_real(ano=a, mes=m, db=db, _user=user)  # accounting_entries reais
    if not dados.get("linhas"):
        return _recusa(f"balancete sem lançamento real no período ({a}{f'/{m:02d}' if m else ''}); "
                       "não vou gerar balancete vazio.")
    pdf = _balancete_pdf_bytes(dados, a, m, escopo=_CONSOLIDADO)
    fecha = dados.get("fecha")
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"balancete_{a}{f'_{m:02d}' if m else ''}.pdf",
        "resumo": f"Balancete {a}{f'/{m:02d}' if m else ''} — {_CONSOLIDADO}: "
                  f"débito {_brl(dados.get('total_debito'))}, crédito {_brl(dados.get('total_credito'))}, "
                  f"diferença {_brl(dados.get('diferenca'))}"
                  + (" (fecha)" if fecha else " (NÃO fecha — verificar)")
                  + " — números reais, doc INTERNO de gestão.",
    }


async def _resolve_empresa(db, termo: str):
    """Resolve a Empresa REAL por slug/razão/fantasia. Retorna (empresa, None) ou (None, recusa)."""
    from modules.empresas.models.empresa import Empresa
    t = f"%{termo.strip()}%"
    rows = (await db.execute(select(Empresa).where(or_(
        Empresa.slug.ilike(t), Empresa.razao_social.ilike(t), Empresa.nome_fantasia.ilike(t),
    )))).scalars().all()
    if not rows:
        return None, _recusa(f"não achei a empresa '{termo}' no cadastro real; diga Eletrônica ou Patrimonial.")
    if len(rows) > 1:
        nomes = ", ".join(e.razao_social for e in rows[:5])
        return None, _recusa(f"'{termo}' casou com mais de uma empresa ({nomes}); seja mais específico.")
    return rows[0], None


async def _gerar_fluxo_caixa_doc(db, user, scope, *, empresa=None, ano=None, mes=None, **_) -> dict[str, Any]:  # noqa: ARG001
    _gate(user)
    _, a = _periodo(mes, ano)
    if not (empresa and str(empresa).strip()):
        return _recusa("o fluxo de caixa é por CNPJ (Inter=Eletrônica, Cora=Patrimonial). "
                       "Diga a empresa (Eletrônica ou Patrimonial) — não vou assumir um CNPJ default.")
    emp, recusa = await _resolve_empresa(db, str(empresa))
    if recusa:
        return recusa
    from modules.financial.controllers.relatorios_controller import _fluxo_caixa_pdf_bytes
    from modules.financial.services.fluxo_caixa_service import FluxoCaixaService
    # dfc_mensal é escopado por empresa_id (extrato do banco daquele CNPJ). Sync (psycopg2), read-only.
    dados = FluxoCaixaService().dfc_mensal(ano=a, empresa_id=str(emp.id))
    if not dados.get("meses"):
        return _recusa(f"sem movimento de caixa real de {emp.razao_social} em {a}; não vou gerar fluxo vazio.")
    escopo = f"{emp.razao_social} (CNPJ isolado)"
    pdf = _fluxo_caixa_pdf_bytes(dados, a, escopo=escopo)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"fluxo_caixa_{emp.slug}_{a}.pdf",
        "resumo": f"Fluxo de caixa {a} — {escopo}: saídas {_brl(dados.get('saidas_total_ano'))} "
                  f"(não categorizadas {_brl(dados.get('saidas_nao_categorizadas_ano'))}) — "
                  "números reais do extrato, doc INTERNO de gestão.",
    }


async def _gerar_aging_receber_doc(db, user, scope, **_) -> dict[str, Any]:  # noqa: ARG001
    _gate(user)
    from modules.financial.controllers.receivable_controller import get_receivables_aging
    from modules.financial.services.receivable_service import ReceivableService
    from modules.financial.services.relatorio_financeiro_pdf import aging_pdf_bytes
    # Aging consolidado: receivable_accounts NÃO tem empresa_id (chaveia condominio/cliente),
    # não dá pra recortar por CNPJ sem reescrever → sai rotulado como grupo consolidado.
    dados = await get_receivables_aging(condominio_id=None, service=ReceivableService(db), current_user=user)
    if not dados.get("faixas") or float(dados.get("total_em_aberto") or 0) <= 0.005:
        return _recusa("não há títulos a receber em aberto; não vou gerar aging vazio como se fosse real.")
    pdf = aging_pdf_bytes(dados, "Contas a Receber — Aging")
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"aging_receber_{dados.get('aging_date', '')}.pdf",
        "resumo": f"Aging de contas a receber (posição em {dados.get('aging_date', '')}) — {_CONSOLIDADO}: "
                  f"em aberto {_brl(dados.get('total_em_aberto'))}, vencido {_brl(dados.get('total_vencido'))} "
                  "— números reais, doc INTERNO de gestão.",
    }


async def _gerar_aging_pagar_doc(db, user, scope, **_) -> dict[str, Any]:  # noqa: ARG001
    _gate(user)
    from modules.financial.controllers.payable_controller import get_payables_aging
    from modules.financial.services.payable_service import PayableService
    from modules.financial.services.relatorio_financeiro_pdf import aging_pdf_bytes
    # Aging consolidado: payable_accounts NÃO tem empresa_id → grupo consolidado (mesmo caso do receber).
    dados = await get_payables_aging(condominio_id=None, service=PayableService(db), current_user=user)
    if not dados.get("faixas") or float(dados.get("total_em_aberto") or 0) <= 0.005:
        return _recusa("não há títulos a pagar em aberto; não vou gerar aging vazio como se fosse real.")
    pdf = aging_pdf_bytes(dados, "Contas a Pagar — Aging")
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"aging_pagar_{dados.get('aging_date', '')}.pdf",
        "resumo": f"Aging de contas a pagar (posição em {dados.get('aging_date', '')}) — {_CONSOLIDADO}: "
                  f"em aberto {_brl(dados.get('total_em_aberto'))}, vencido {_brl(dados.get('total_vencido'))} "
                  "— números reais, doc INTERNO de gestão.",
    }


_SCHEMA_VAZIO = {"type": "object", "properties": {}, "required": []}

_SCHEMA_PERIODO = {
    "type": "object",
    "properties": {
        "mes": {"type": "integer", "description": "Mês 1..12 (opcional; vazio = ano inteiro)."},
        "ano": {"type": "integer", "description": "Ano (opcional; padrão = ano corrente)."},
    },
    "required": [],
}

_SCHEMA_FLUXO = {
    "type": "object",
    "properties": {
        "empresa": {"type": "string",
                    "description": "Empresa/CNPJ do fluxo: Eletrônica ou Patrimonial (obrigatório — fluxo é por CNPJ)."},
        "ano": {"type": "integer", "description": "Ano (opcional; padrão = ano corrente)."},
    },
    "required": ["empresa"],
}

register(ToolDef(
    "gerar_dre_doc", "financeiro",
    "Gera o DRE (Demonstração do Resultado) em PDF branded, a partir dos números REAIS apurados "
    "sobre o razão (accounting_entries + NFS-e). Relatório INTERNO de gestão (diretoria) — grupo "
    "consolidado. Período sem lançamento real → recusa. Não grava, não move dinheiro.",
    _SCHEMA_PERIODO, _gerar_dre_doc, scope_kind="org"))

register(ToolDef(
    "gerar_balancete_doc", "financeiro",
    "Gera o BALANCETE (saldos por conta, com prova de fechamento) em PDF branded, dos lançamentos "
    "REAIS (accounting_entries). Relatório INTERNO de gestão (diretoria) — grupo consolidado. "
    "Período sem lançamento → recusa. Não grava, não move dinheiro.",
    _SCHEMA_PERIODO, _gerar_balancete_doc, scope_kind="org"))

register(ToolDef(
    "gerar_fluxo_caixa_doc", "financeiro",
    "Gera o FLUXO DE CAIXA mensal (DFC) em PDF branded, do extrato REAL do banco. É POR CNPJ "
    "(Inter=Eletrônica, Cora=Patrimonial): informe a empresa — sem ela, recusa (não assume default). "
    "Relatório INTERNO de gestão (diretoria). Não move dinheiro (só categoriza transações do extrato).",
    _SCHEMA_FLUXO, _gerar_fluxo_caixa_doc, scope_kind="org"))

register(ToolDef(
    "gerar_aging_receber_doc", "financeiro",
    "Gera o AGING de CONTAS A RECEBER em PDF branded (títulos em aberto por faixa de "
    "vencimento, posição de hoje), dos números REAIS (receivable_accounts). Relatório INTERNO "
    "de gestão (diretoria) — grupo consolidado (todas as empresas; a base não separa por CNPJ). "
    "Sem títulos em aberto → recusa. Não grava, não move dinheiro.",
    _SCHEMA_VAZIO, _gerar_aging_receber_doc, scope_kind="org"))

register(ToolDef(
    "gerar_aging_pagar_doc", "financeiro",
    "Gera o AGING de CONTAS A PAGAR em PDF branded (títulos em aberto por faixa de vencimento, "
    "posição de hoje), dos números REAIS (payable_accounts). Relatório INTERNO de gestão "
    "(diretoria) — grupo consolidado (todas as empresas; a base não separa por CNPJ). "
    "Sem títulos em aberto → recusa. Não grava, não move dinheiro.",
    _SCHEMA_VAZIO, _gerar_aging_pagar_doc, scope_kind="org"))
