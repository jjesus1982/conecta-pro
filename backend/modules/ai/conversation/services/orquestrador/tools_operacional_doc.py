"""Tool GERA-DOC operacional (Fase 6, Fatia 4) — módulo operacional, scope_kind="org".

No chat escopado, quem tem o módulo `operacional` renderiza o PDF branded de um
RELATÓRIO DE VISITA JÁ EXISTENTE (registro real de `visitas`), reusando o gerador real
(build_visit_report_pdf) e a mesma montagem do endpoint /campo/visitas/{id}/pdf
(visita_to_pdf_dict — fonte única, sem drift). Render fiel de registro existente = leitura.

Paredes (inegociáveis):
- Operacional é READ-ONLY p/ agentes: NUNCA cria/edita/apaga visita. Nada gravado.
- Conteúdo do doc vem SÓ do registro (texto redigido no passo de CRIAR a visita — não aqui).
- Fail-closed: não achou a visita → RECUSA, nunca inventa.
- RBAC na fonte: belt (módulo operacional) + suspenders (_gate re-checa user_has_module).
- Doc só pelo gerador branded real — nunca PDF genérico.
"""
from __future__ import annotations

import base64
from typing import Any
from uuid import UUID

from core.auth.module_scope import user_has_module

from .tool_registry import ToolDef, register

_SCHEMA = {
    "type": "object",
    "properties": {
        "visita_id": {"type": "string", "description": "UUID da visita no cadastro."},
        "visita_numero": {"type": "string", "description": "Número da visita (ex.: VIS-2026-00001)."},
    },
    "required": [],
}


def _gate(user) -> None:
    if not user_has_module(user, "operacional"):
        raise PermissionError("operacional")


def _recusa(motivo: str) -> dict[str, Any]:
    return {"status": "recusado", "motivo": motivo}


async def _resolve_visita(db, *, visita_id, visita_numero):
    """Resolve a Visita REAL (por id ou número). Nunca cria — só render de existente."""
    from modules.campo.services.visita_service import VisitaService
    svc = VisitaService(db)
    if visita_id:
        try:
            vid = UUID(str(visita_id))
        except (ValueError, TypeError):  # UUID malformado = não encontrado (fail-closed)
            vid = None
        if vid is not None:
            v = await svc.obter_visita(vid)
            if v:
                return v
    if visita_numero:
        v = await svc.obter_visita_por_numero(str(visita_numero))
        if v:
            return v
    return None


async def _gerar_relatorio_visita_doc(db, user, scope, *, visita_id=None, visita_numero=None, **_) -> dict[str, Any]:
    _gate(user)
    v = await _resolve_visita(db, visita_id=visita_id, visita_numero=visita_numero)
    if v is None:
        return _recusa("relatório de visita não encontrado; informe o id (ou número) da visita.")
    from modules.campo.services.visita_service import visita_to_pdf_dict
    from modules.crm.services.doc_pdf import build_visit_report_pdf
    d = visita_to_pdf_dict(v)  # mesma montagem do endpoint — render fiel, sem fabricar, sem gravar
    pdf = build_visit_report_pdf(d)
    numero = d.get("numero") or visita_id or "visita"
    return {
        "arquivo_base64": base64.b64encode(pdf).decode(),
        "nome": f"visita_{numero}.pdf",
        "resumo": f"Relatório de visita {d.get('numero') or '—'} — {d.get('cliente_nome') or '—'} "
                  "(render do registro real; nada foi criado/alterado)",
    }


register(ToolDef(
    "gerar_relatorio_visita_doc", "operacional",
    "Renderiza o PDF branded de um RELATÓRIO DE VISITA JÁ EXISTENTE (por id ou número). "
    "Apenas render fiel do registro real — NÃO cria, não edita nem apaga visita. Não grava.",
    _SCHEMA, _gerar_relatorio_visita_doc, scope_kind="org"))
