"""Tools READ do JURÍDICO (Fase 6, balde VER) — módulo juridico, scope_kind="org".

No chat escopado, quem tem o módulo `juridico` CONSULTA o escritório jurídico como faria
navegando as telas: processos & defesa (lista real), painel/hub consolidado, prazos/compliance
com status calculado e o panorama de regularidade da empresa. Cada handler chama a COROUTINE do
controller REAL in-process, com a IDENTIDADE do usuário logado (`db`/`user` reais) — NUNCA a
conta de serviço, NUNCA HTTP.

Paredes (inegociáveis):
- RBAC na fonte: `_gate(user)` primeiro (re-checa user_has_module(user,"juridico")); chamar o
  controller direto pula o Depends dele. O belt filtra por módulo; o _gate é o suspenders.
- SÓ LEITURA: só rotas GET entram aqui.
- READ-ONLY DE VERDADE: aqui NÃO se gera parecer/análise. Gerar parecer é produzir texto
  jurídico novo (fabricação do LLM) — proibido neste balde. Só consulta de REGISTROS reais já
  gravados (processos analisados, prazos, contratos, panorama do banco). Por isso `analisar_por_texto`
  / `parecer_service` ficam DE FORA — são geração, não leitura.
- Nunca fabricar: devolve o resultado REAL do controller/banco; vazio real = vazio.
"""
from __future__ import annotations

from typing import Any

from core.auth.module_scope import user_has_module

from .read_dispatcher import registrar_read

_MOD = "juridico"


def _gate(user) -> None:
    if not user_has_module(user, _MOD):
        raise PermissionError(_MOD)


def _dump(res) -> Any:
    return res.model_dump(mode="json") if hasattr(res, "model_dump") else res


# ---- handlers ----

async def _processos(db, user, scope, *, limit=50, **_) -> Any:
    _gate(user)
    from modules.juridico.processos_controller import listar
    return _dump(await listar(limit=int(limit), current_user=user, db=db))


async def _painel(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.juridico.hub_controller import hub
    return _dump(await hub(current_user=user, db=db))


async def _prazos(db, user, scope, *, incluir_automaticos=True, status=None, **_) -> Any:
    _gate(user)
    from modules.juridico.hub_controller import listar_prazos
    return _dump(await listar_prazos(current_user=user, db=db,
                                     incluir_automaticos=bool(incluir_automaticos), status=status))


async def _panorama(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.juridico.context_controller import contexto_panorama
    return _dump(await contexto_panorama(current_user=user, db=db))


async def _obter_processo(db, user, scope, *, id=None, processo_id=None, **_) -> Any:
    _gate(user)
    pid = id or processo_id
    if not pid:
        return {"status": "informe id (id do processo) para ver o detalhe"}
    from fastapi import HTTPException
    from modules.juridico.processos_controller import obter
    try:
        return _dump(await obter(id=str(pid), current_user=user, db=db))
    except HTTPException as e:
        return {"status": "não encontrado", "motivo": str(e.detail)}


async def _analise_contrato(db, user, scope, *, contrato_id=None, id=None, **_) -> Any:
    _gate(user)
    cid = contrato_id or id
    if not cid:
        return {"status": "informe contrato_id (id do contrato) para a análise de cláusulas"}
    # Análise READ-ONLY (regex+scoring) das cláusulas de UM contrato, rotulada HIPÓTESE de máquina.
    # NÃO gera parecer nem texto jurídico novo — só roda padrões sobre o texto já gravado.
    from modules.juridico.consultor_service import _analise_contrato_hipotese
    bloco = await _analise_contrato_hipotese(db, str(cid))
    if not bloco:
        return {"contrato_id": str(cid), "status": "sem texto de contrato para analisar "
                "(contrato inexistente ou sem conteúdo) — aguardando dado real."}
    return {"contrato_id": str(cid),
            "aviso": "HIPÓTESE de máquina (regex+scoring), NÃO é fato jurídico — valide o texto original.",
            "analise": bloco.strip()}


async def _dossie(db, user, scope, *, tipo=None, identificador=None, **_) -> Any:
    _gate(user)
    # Dossiê READ-ONLY cross-módulo: só cruza REGISTROS reais (DP/folha/ponto/contratos/GED).
    # Não gera texto jurídico novo — é leitura, não parecer.
    from fastapi import HTTPException
    from modules.juridico import context_controller as CC
    t = (tipo or "").strip().lower()
    try:
        if t == "panorama":
            return _dump(await CC.contexto_panorama(current_user=user, db=db))
        if not identificador:
            return {"status": "informe identificador (nome/CPF/id) para o dossiê"}
        if t in ("funcionario", "funcionário", "pessoa"):
            return _dump(await CC.contexto_funcionario(identificador=str(identificador),
                                                       current_user=user, db=db))
        if t == "contrato":
            return _dump(await CC.contexto_contrato(contrato_id=str(identificador),
                                                    current_user=user, db=db))
        if t == "cliente":
            return _dump(await CC.contexto_cliente(cliente_id=str(identificador),
                                                   current_user=user, db=db))
        return {"status": "tipo inválido", "tipos_validos": ["panorama", "funcionario", "contrato", "cliente"]}
    except HTTPException as e:
        return {"status": "não encontrado", "motivo": str(e.detail)}


# ---- registro das ops READ (roteadas por consultar_juridico(consulta, filtros)) ----

registrar_read(_MOD, "processos",
               "Lista os processos jurídicos JÁ analisados/gravados (defesa trabalhista etc.). "
               "Filtro opcional: limit. Só leitura — não analisa/gera parecer novo aqui.",
               _processos)
registrar_read(_MOD, "painel",
               "Hub Jurídico — painel consolidado real (contratos, consultas IA, pareceres, "
               "análises, prazos e certidões, em números). Sem filtros.", _painel)
registrar_read(_MOD, "prazos",
               "Prazos/compliance (gravados + automáticos de contratos/certidões) com status "
               "calculado. Filtros: incluir_automaticos (bool), status (aberto|cumprido|atrasado).",
               _prazos)
registrar_read(_MOD, "panorama",
               "Panorama jurídico da empresa: regime, quadro, certidões e obrigações fiscais "
               "(regularidade/passivo, dado real). Sem filtros.", _panorama)
registrar_read(_MOD, "obter_processo",
               "Detalhe de UM processo jurídico já gravado (dossiê + defesa). Filtro: id "
               "(obrigatório, id do processo). Só leitura.", _obter_processo)
registrar_read(_MOD, "dossie",
               "Dossiê jurídico READ-ONLY cross-módulo (cruza registros reais, não gera parecer). "
               "Filtros: tipo (panorama|funcionario|contrato|cliente), identificador "
               "(nome/CPF/id — dispensável em 'panorama').", _dossie)
registrar_read(_MOD, "analise_contrato",
               "Análise READ-ONLY das cláusulas de UM contrato (regex+scoring): tipo detectado, "
               "nível/score de risco, cláusulas arriscadas e recomendações — rotulada HIPÓTESE de "
               "máquina, NÃO gera parecer nem fato jurídico. Filtro: contrato_id (obrigatório).",
               _analise_contrato)


# ── DET — COMUNICAÇÕES (8ª das 14 — leitura) ─────────────────────────────────────────
# Rota real: GET /juridico/det/comunicacoes · corrotina `juridico/det_controller.py:59`.
# É caixa postal de GOVERNO: comunicação do DET tem prazo, e prazo perdido vira revelia.
# Só LEITURA — transmitir/responder ao DET é ato irreversível e não passa pelo chat.
async def _det_comunicacoes(db, user, scope, *, limit=50, **_) -> Any:
    _gate(user)
    from modules.juridico.det_controller import listar

    return _dump(await listar(limit=int(limit), current_user=user, db=db))


registrar_read(_MOD, "det_comunicacoes",
               "Comunicações recebidas no DET (Domicílio Eletrônico Trabalhista) — caixa "
               "postal do governo, com prazo. Filtros: limit. Só leitura: responder ou "
               "transmitir ao DET é ato irreversível e não passa por aqui.",
               _det_comunicacoes)
