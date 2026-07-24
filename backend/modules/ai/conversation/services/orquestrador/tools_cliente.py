"""Tools CONDOMÍNIO-SCOPED (tier cliente externo). Filtram por scope.client_id (=ged_clients.id),
NUNCA por argumento — o cliente jamais alcança outro condomínio. Reusam os services do portal
(portal_financeiro_service / portal_operacao_service), que já resolvem o escopo por client_id."""
from __future__ import annotations

from typing import Any

from .tool_registry import ToolDef, register

_NO_ARGS = {"type": "object", "properties": {}}


def _cid(scope) -> str | None:
    return getattr(scope, "client_id", None) if scope else None


async def _notas(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.notas(db, cid)


async def _contrato(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.contrato(db, cid)


async def _boletos(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service
    return await portal_financeiro_service.boletos(db, cid)


async def _equipe(db, user, scope, **_) -> dict[str, Any]:
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_operacao_service
    return await portal_operacao_service.equipe(db, cid)


CLIENTE_TOOLS: list[ToolDef] = [
    register(ToolDef("notas_condominio", "cliente",
                     "Notas fiscais (NFS-e) do MEU condomínio.", _NO_ARGS, _notas, scope_kind="cliente")),
    register(ToolDef("contrato_condominio", "cliente",
                     "O contrato vigente do MEU condomínio.", _NO_ARGS, _contrato, scope_kind="cliente")),
    register(ToolDef("boletos_condominio", "cliente",
                     "Os boletos/cobranças do MEU condomínio.", _NO_ARGS, _boletos, scope_kind="cliente")),
    register(ToolDef("equipe_condominio", "cliente",
                     "A equipe/funcionários alocados no MEU condomínio.", _NO_ARGS, _equipe, scope_kind="cliente")),
]


_DOC_ARGS = {
    "type": "object",
    "properties": {"tipo": {"type": "string", "enum": ["boleto", "nota"],
                            "description": "boleto (cobrança) ou nota (NFS-e)"}},
    "required": ["tipo"],
}


async def _buscar_documento(db, user, scope, *, tipo: str, **_) -> dict[str, Any]:
    """BUSCA e entrega um documento EXISTENTE do próprio condomínio (link/anexo).
    NUNCA emite documento novo (emissão fiscal fica fora deste tier).

    Reusa portal_financeiro_service.boletos/.notas — a MESMA fonte que a tela do
    portal usa (financeiro_controller.py) — e herda o escopo por scope.client_id
    (nunca por argumento). `**_` descarta qualquer kwarg extra injetado pelo LLM
    (ex.: tentativa de passar client_id) — a busca sempre usa o client_id do scope.

    Shape real dos itens (portal_financeiro_service, não fabricado):
    - boleto: {numero, valor, vencimento, status, banco, boleto_digitavel?, pix_copia_cola?}
      (boleto_digitavel/pix_copia_cola só existem para cobranças via Cora; Inter
      ainda não tem link/linha digitável armazenados neste service — url vem None).
    - nota: {numero, emissao, competencia, valor, status, link, descricao}
      (link é sempre None hoje — NFS-e ainda não tem URL de PDF persistida aqui).
    Nunca fabricamos um valor para "url": quando a fonte não tem o dado, url é None
    (honesto), não um link inventado.
    """
    cid = _cid(scope)
    if not cid:
        return {"status": "aguardando dado"}
    from modules.client_portal.services import portal_financeiro_service

    if tipo == "boleto":
        data = await portal_financeiro_service.boletos(db, cid)
        itens = data.get("boletos") or data.get("itens") or []
        docs = [
            {"descricao": b.get("numero") or "boleto",
             "valor": b.get("valor"), "vencimento": b.get("vencimento"),
             "status": b.get("status"), "banco": b.get("banco"),
             "url": b.get("boleto_digitavel") or b.get("pix_copia_cola")}
            for b in itens
        ]
    else:  # nota
        data = await portal_financeiro_service.notas(db, cid)
        itens = data.get("notas") or data.get("itens") or []
        docs = [
            # identificador primeiro (numero da NFS-e é único; a descrição do serviço é texto
            # padrão de linha de serviço — se usada como identidade, colide entre condomínios
            # diferentes e faria parecer vazamento sem ser)
            {"descricao": n.get("numero") or n.get("competencia") or "nota",
             "servico": n.get("descricao"), "valor": n.get("valor"), "competencia": n.get("competencia"),
             "url": n.get("link")}
            for n in itens
        ]
    if not docs:
        return {"status": "aguardando dado", "motivo": f"nenhum {tipo} disponível para o seu condomínio"}
    return {"tipo": tipo, "documentos": docs, "aviso": "Documentos do seu condomínio — busca do já existente (não emitimos documento novo)."}


CLIENTE_TOOLS.append(register(ToolDef(
    "buscar_documento_condominio", "cliente",
    "Localizar e ENTREGAR um documento EXISTENTE do meu condomínio (boleto ou nota) — nunca emite novo.",
    _DOC_ARGS, _buscar_documento, scope_kind="cliente",
)))
