"""Tools GERA-DOC comercial (Fase 6, Fatia 1) — módulo crm, scope_kind="org".

No chat escopado, quem tem o módulo `crm` monta proposta/orçamento BRANDED (rascunho)
reusando os geradores REAIS (build_proposal_pdf / build_orcamento_pdf) com o PREÇO
SEMPRE vindo do motor real (ProposalService / PricingEngine). O LLM passa apenas
PARÂMETROS de negócio (salário base, qtd de postos, meses) — NUNCA um valor final.
Sem lastro pra precificar, ou cliente inexistente → RECUSA, nunca fabrica número.

Paredes (inegociáveis):
- PREÇO só do PricingEngine; LLM nunca passa total. Sem parâmetro → recusa, não estima.
- RBAC na fonte: belt (módulo crm) + suspenders (_gate re-checa user_has_module).
- RASCUNHO: number="RASCUNHO", NADA gravado no banco, nada enviado, nenhum contrato.
- Nenhum campo interno (margem/custo/MRR) vai pro PDF — só o preço de venda e itens.
- Doc só pelos geradores branded reais — nunca PDF genérico.
"""
from __future__ import annotations

import base64
from datetime import date
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register

# produto do portfólio → service_type do motor (define ISS/impostos). Fora do mapa = "default".
_SERVICE_TYPES = {
    "portaria": "portaria",
    "vigilancia": "vigilancia",
    "vigilância": "vigilancia",
    "limpeza": "limpeza",
    "facilities": "facilities",
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "produto": {"type": "string",
                    "description": "Produto do portfólio (ex.: portaria, vigilancia, limpeza, facilities)."},
        "cliente_id": {"type": "string", "description": "UUID do cliente no cadastro (se souber)."},
        "cliente_cnpj": {"type": "string", "description": "CNPJ/CPF do cliente."},
        "cliente_nome": {"type": "string", "description": "Nome/razão social do cliente."},
        "salario_base": {"type": "number", "description": "Salário base MENSAL por posto (R$)."},
        "qtd_postos": {"type": "integer", "description": "Número de postos/funcionários."},
        "meses_contrato": {"type": "integer", "description": "Duração do contrato em meses."},
        "margem_pct": {"type": "number", "description": "Margem alvo em % (opcional; padrão 15)."},
    },
    "required": ["produto", "salario_base", "qtd_postos", "meses_contrato"],
}


def _gate(user) -> None:
    if not user_has_module(user, "crm"):
        raise PermissionError("crm")


def _recusa(motivo: str) -> dict[str, Any]:
    return {"status": "recusado", "motivo": motivo}


def _dec_pos(v) -> Decimal | None:
    """Arg do LLM → Decimal > 0, ou None (ausente/inválido = sem lastro)."""
    if v is None or v == "":
        return None
    try:
        d = Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d if d > 0 else None


def _int_pos(v) -> int | None:
    try:
        n = int(v)
    except (ValueError, TypeError):
        return None
    return n if n > 0 else None


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _slug(nome: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in (nome or "cliente").lower())[:40].strip("_") or "cliente"


def _endereco(c) -> str:
    partes = [getattr(c, k, None) for k in
              ("address_street", "address_number", "address_neighborhood", "address_city")]
    linha = ", ".join(p for p in partes if p)
    uf = getattr(c, "address_state", None)
    if uf:
        linha = f"{linha}/{uf}" if linha else uf
    return linha


async def _resolve_cliente(db, *, cliente_id, cliente_cnpj, cliente_nome):
    from modules.clients.models import Client
    if cliente_id:
        row = (await db.execute(select(Client).where(Client.id == cliente_id))).scalars().first()
        if row:
            return row
    if cliente_cnpj:
        alvo = "".join(ch for ch in str(cliente_cnpj) if ch.isdigit())
        # ponytail: carga completa + match por dígitos (base tem ~dezenas de clientes; doc
        # pode estar formatado no banco). Se a base crescer muito, filtrar no SQL por regexp.
        todos = (await db.execute(select(Client))).scalars().all()
        for c in todos:
            if "".join(ch for ch in (c.document_number or "") if ch.isdigit()) == alvo:
                return c
    if cliente_nome:
        row = (await db.execute(
            select(Client).where(Client.name.ilike(f"%{cliente_nome}%")).limit(1)
        )).scalars().first()
        if row:
            return row
    return None


async def _lastro(db, user, *, produto, cliente_id, cliente_cnpj, cliente_nome,
                  salario_base, qtd_postos, meses_contrato, margem_pct):
    """Gate + validação + resolução de cliente + PREÇO real. Retorna (dados, None) ou (None, recusa)."""
    _gate(user)
    base = _dec_pos(salario_base)
    hc = _int_pos(qtd_postos)
    meses = _int_pos(meses_contrato)
    faltando = [n for n, v in
                (("salário base mensal", base), ("quantidade de postos", hc), ("meses de contrato", meses))
                if v is None]
    if faltando:
        return None, _recusa(
            f"preciso de {', '.join(faltando)} pra precificar pelo motor real (cadastro/CCT); não vou estimar valor."
        )
    cli = await _resolve_cliente(db, cliente_id=cliente_id, cliente_cnpj=cliente_cnpj, cliente_nome=cliente_nome)
    if cli is None:
        return None, _recusa(
            "cliente não encontrado no cadastro real (informe id, CNPJ ou nome exato); não vou inventar cliente."
        )
    margem = _dec_pos(margem_pct) or Decimal("15.00")
    stype = _SERVICE_TYPES.get((produto or "").strip().lower(), "default")
    from modules.crm.services.proposal_service import ProposalService
    try:
        pr = ProposalService().calculate_proposal_pricing(
            base_salary=base, headcount=hc, contract_months=meses,
            service_type=stype, client_state=(getattr(cli, "address_state", None) or "SP"),
            margin_target=margem,
        )
    except ValueError as e:
        return None, _recusa(f"o motor de preço recusou os parâmetros: {e}")
    return (cli, hc, meses, pr), None


async def _gerar_proposta(db, user, scope, *, produto=None, cliente_id=None, cliente_cnpj=None,
                          cliente_nome=None, salario_base=None, qtd_postos=None,
                          meses_contrato=None, margem_pct=None, **_) -> dict[str, Any]:
    dados, recusa = await _lastro(
        db, user, produto=produto, cliente_id=cliente_id, cliente_cnpj=cliente_cnpj,
        cliente_nome=cliente_nome, salario_base=salario_base, qtd_postos=qtd_postos,
        meses_contrato=meses_contrato, margem_pct=margem_pct)
    if recusa:
        return recusa
    cli, hc, meses, pr = dados
    total_mensal = float(pr.total_monthly)  # preço de venda mensal do motor (nunca de arg do LLM)
    titulo = produto or "Serviços de Segurança Patrimonial"
    item = SimpleNamespace(
        name=titulo, description=f"{hc} posto(s) · contrato {meses} meses",
        quantity=hc, unit="posto", unit_price=float(pr.unit_price), total=total_mensal, sort_order=0)
    p = SimpleNamespace(
        number="RASCUNHO", client_name=cli.name, client_document=cli.document_number,
        client_address=_endereco(cli), title=titulo, issue_date=date.today(),
        total=total_mensal, items=[item], description=None)
    from modules.crm.services.proposal_pdf import build_proposal_pdf
    pdf = build_proposal_pdf(p)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"proposta_{_slug(cli.name)}.pdf",
        "total": total_mensal,
        "resumo": f"{titulo} p/ {cli.name}: {_brl(total_mensal)}/mês (preço do motor real — RASCUNHO)",
    }


async def _gerar_orcamento(db, user, scope, *, produto=None, cliente_id=None, cliente_cnpj=None,
                           cliente_nome=None, salario_base=None, qtd_postos=None,
                           meses_contrato=None, margem_pct=None, **_) -> dict[str, Any]:
    dados, recusa = await _lastro(
        db, user, produto=produto, cliente_id=cliente_id, cliente_cnpj=cliente_cnpj,
        cliente_nome=cliente_nome, salario_base=salario_base, qtd_postos=qtd_postos,
        meses_contrato=meses_contrato, margem_pct=margem_pct)
    if recusa:
        return recusa
    cli, hc, meses, pr = dados
    total_mensal = float(pr.total_monthly)
    titulo = produto or "Serviços de segurança patrimonial"
    cidade = getattr(cli, "address_city", None)
    uf = getattr(cli, "address_state", None)
    d = {
        "numero": "RASCUNHO", "cliente": cli.name, "documento": cli.document_number,
        "cidade": (f"{cidade}/{uf}" if cidade and uf else cidade) or "Manaus/AM",
        "titulo": "ORÇAMENTO", "objeto": titulo,
        "itens": [{"descricao": f"{titulo} — {hc} posto(s)", "qtd": 1, "unidade": "mês",
                   "valor_unit": total_mensal, "tipo": "servico"}],
    }
    from modules.crm.services.doc_pdf import build_orcamento_pdf
    pdf = build_orcamento_pdf(d)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"orcamento_{_slug(cli.name)}.pdf",
        "total": total_mensal,
        "resumo": f"{titulo} p/ {cli.name}: {_brl(total_mensal)}/mês (preço do motor real — RASCUNHO)",
    }


register(ToolDef(
    "gerar_proposta_comercial_doc", "crm",
    "Monta uma PROPOSTA COMERCIAL branded (rascunho, PDF) para um cliente do cadastro. "
    "Preço vem do motor real de precificação (CCT/impostos) a partir de salário base, "
    "qtd de postos e meses — nunca de um valor livre. Não grava, não envia.",
    _SCHEMA, _gerar_proposta, scope_kind="org"))

register(ToolDef(
    "gerar_orcamento_doc", "crm",
    "Monta um ORÇAMENTO branded (rascunho, PDF) para um cliente do cadastro. "
    "Preço vem do motor real de precificação — nunca de um valor livre. Não grava, não envia.",
    _SCHEMA, _gerar_orcamento, scope_kind="org"))
