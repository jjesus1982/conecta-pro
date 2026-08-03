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
