"""Tool GERA-DOC FISCAL (Fase 6, Fatia 8) — módulo fiscal, scope_kind="org".

No chat escopado, diretoria (belt fiscal) pede "relatório de NFS-e da Eletrônica"
(ou Patrimonial) e recebe o PDF branded das notas REAIS daquela empresa. NUNCA mistura
CNPJ: EXIGE a empresa. Números só de `nfse_emitidas_nacional`, nunca fabricados pelo LLM.

Paredes (inegociáveis) [[feedback_nfse_rbac_diretoria_empresa]]:
- SÓ diretoria (belt fiscal): `_gate` re-checa (suspenders sobre o belt que já filtra as tools).
- Escopado por empresa: sem empresa → RECUSA (não assume nem consolida os 2 CNPJ).
- Números só das notas REAIS (WHERE empresa_id). Sem nota → RECUSA (não gera relatório vazio).
- Read-only, fail-closed. Doc INTERNO de gestão (diretoria) pelo gerador branded.

Reusa 1:1 de tools_financeiro_doc: `_resolve_empresa`, `_brl`, `_recusa`. Reusa o mesmo
gerador `gerar_relatorio_pdf` do DRE/balancete — o chat não recalcula nada.
"""
from __future__ import annotations

import base64
from typing import Any

from sqlalchemy import text

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register
from .tools_financeiro_doc import _brl, _recusa, _resolve_empresa


def _gate(user) -> None:
    if not user_has_module(user, "fiscal"):
        raise PermissionError("fiscal")


async def _gerar_relatorio_nfse_doc(db, user, scope, *, empresa=None, competencia=None, **_) -> dict[str, Any]:  # noqa: ARG001
    _gate(user)
    if not (empresa and str(empresa).strip()):
        return _recusa("NFS-e é por empresa; diga Eletrônica ou Patrimonial — não misturo CNPJ.")
    emp, recusa = await _resolve_empresa(db, str(empresa))
    if recusa:
        return recusa

    conds = ["empresa_id = :eid"]
    params: dict[str, Any] = {"eid": str(emp.id)}
    comp = str(competencia).strip() if competencia else ""
    if comp:
        conds.append("competencia = :comp")
        params["comp"] = comp
    where = " AND ".join(conds)
    rows = (await db.execute(text(
        "SELECT numero, competencia, tomador_nome, valor_servicos, iss_valor, cancelada "
        f"FROM nfse_emitidas_nacional WHERE {where} "
        "ORDER BY competencia, data_emissao NULLS LAST, numero"
    ), params)).mappings().all()

    if not rows:
        return _recusa(f"nenhuma NFS-e real de {emp.razao_social}"
                       f"{f' na competência {comp}' if comp else ''}; não gero relatório vazio.")

    total_serv = sum(float(r["valor_servicos"] or 0) for r in rows)
    total_iss = sum(float(r["iss_valor"] or 0) for r in rows)
    secoes = [
        {"titulo": "Totais", "linhas": [
            ("Quantidade de notas", str(len(rows))),
            ("Valor dos serviços", total_serv),
            ("ISS", total_iss, True),
        ]},
        {"titulo": "Notas emitidas", "linhas": [
            (f"{r['numero']} · {r['competencia']} · {(r['tomador_nome'] or '')[:38]}"
             + (" [CANCELADA]" if r["cancelada"] else ""),
             float(r["valor_servicos"] or 0))
            for r in rows
        ]},
    ]
    from modules.financial.services.relatorio_financeiro_pdf import gerar_relatorio_pdf
    sub = emp.razao_social + (f" · {comp}" if comp else "")
    pdf = gerar_relatorio_pdf("NFS-e Emitidas", sub, secoes)
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"nfse_{emp.slug}.pdf",
        "resumo": f"NFS-e Emitidas — escopado em {emp.razao_social} (CNPJ isolado)"
                  f"{f', competência {comp}' if comp else ''}: {len(rows)} notas, "
                  f"valor {_brl(total_serv)}, ISS {_brl(total_iss)} "
                  "— números reais (nfse_emitidas_nacional), doc INTERNO de gestão.",
    }


_SCHEMA_NFSE = {
    "type": "object",
    "properties": {
        "empresa": {"type": "string",
                    "description": "Empresa/CNPJ das NFS-e: Eletrônica ou Patrimonial "
                                   "(OBRIGATÓRIO — NFS-e é por CNPJ, nunca misturo os dois)."},
        "competencia": {"type": "string",
                        "description": "Competência 'AAAA-MM' (opcional; vazio = todas as notas da empresa)."},
    },
    "required": ["empresa"],
}

register(ToolDef(
    "gerar_relatorio_nfse_doc", "fiscal",
    "Gera o RELATÓRIO de NFS-e EMITIDAS em PDF branded, das notas REAIS "
    "(nfse_emitidas_nacional). SÓ diretoria (belt fiscal). É POR EMPRESA "
    "(Eletrônica ou Patrimonial): informe a empresa — sem ela, recusa; NUNCA mistura os "
    "dois CNPJ. Sem nota real → recusa. Relatório INTERNO de gestão. Não grava, read-only.",
    _SCHEMA_NFSE, _gerar_relatorio_nfse_doc, scope_kind="org"))
