"""Tools READ do FISCAL (Fase 6, balde VER) — módulo fiscal, scope_kind="org".

No chat escopado, quem tem o módulo `fiscal` (diretoria) CONSULTA a situação fiscal como
faria navegando as telas: situação/débitos no e-CAC, certidões, status das guias
(FGTS Digital, DCTFWeb, Simples Nacional), calendário de obrigações e o dashboard de NFS-e.
Cada handler chama a COROUTINE do controller REAL in-process, com a IDENTIDADE do usuário
logado (`db`/`user` reais) — NUNCA a conta de serviço, NUNCA HTTP.

Paredes (inegociáveis):
- RBAC na fonte: chamar o controller direto PULA o Depends(require_permission) dele, então
  TODO handler faz `_gate(user)` primeiro (re-checa user_has_module(user,"fiscal")). O belt
  (tools_for_modules) já filtra por módulo; o _gate é o suspenders. É gate de DIRETORIA.
- SÓ LEITURA: só coroutines de rota GET entram aqui. Nada emite guia, transmite declaração
  nem move dinheiro.
- Nunca fabricar: devolve o resultado REAL do controller/banco; vazio real = vazio.
- Não misturar CNPJ: e-CAC é por documento (aceita cpf_cnpj; default = o configurado);
  calendário é por empresa OU consolidado ROTULADO por empresa (por_empresa); nfse_dashboard
  é CONSOLIDADO (ambos CNPJ juntos) — dito na descrição p/ o LLM não atribuir a um só CNPJ.

NÃO duplica o gera-doc de NFS-e por empresa (gerar_relatorio_nfse_doc já existe): aqui é só
o dashboard consolidado de leitura.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from core.auth.module_scope import user_has_module

from .read_dispatcher import registrar_read

_MOD = "fiscal"


def _gate(user) -> None:
    # Suspenders: o GET normalmente gateia via Depends no mount; chamado direto isso é pulado,
    # então re-checamos o módulo aqui na fonte com a identidade real (gate de diretoria).
    if not user_has_module(user, _MOD):
        raise PermissionError(_MOD)


def _dump(res) -> Any:
    # Controllers ora devolvem StandardResponse/Pydantic, ora dict cru. Normaliza p/ JSON.
    return res.model_dump(mode="json") if hasattr(res, "model_dump") else res


# ---- handlers (assinaturas heterogêneas dos controllers → handlers explícitos) ----

async def _situacao_ecac(db, user, scope, *, cpf_cnpj=None, **_) -> Any:
    _gate(user)
    from modules.government_integrations.controllers.ecac_controller import (
        consultar_situacao_fiscal,
        get_service,
    )
    return _dump(await consultar_situacao_fiscal(current_user=user, cpf_cnpj=cpf_cnpj,
                                                 service=get_service()))


async def _debitos_ecac(db, user, scope, *, competencia_inicio=None, competencia_fim=None, **_) -> Any:
    _gate(user)
    from modules.government_integrations.controllers.ecac_controller import (
        consultar_debitos,
        get_service,
    )
    # situacao é Enum no controller (faz .value); só leitura sem filtro de situação para não quebrar.
    return _dump(await consultar_debitos(current_user=user, situacao=None,
                                         competencia_inicio=competencia_inicio,
                                         competencia_fim=competencia_fim, service=get_service()))


async def _certidoes(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.ged.controllers.ged_certidoes_controller import listar_certidoes
    return _dump(await listar_certidoes(current_user=user, db=db))


async def _status_fgts_digital(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.government_integrations.controllers.fgts_digital_controller import (
        get_service,
        get_status,
    )
    return _dump(await get_status(current_user=user, service=get_service()))


async def _status_dctfweb(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.government_integrations.controllers.dctfweb_controller import (
        get_service,
        get_status,
    )
    return _dump(await get_status(current_user=user, service=get_service()))


async def _status_simples(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.government_integrations.controllers.simples_nacional_controller import (
        get_service,
        get_status,
    )
    return _dump(await get_status(current_user=user, service=get_service()))


async def _calendario_obrigacoes(db, user, scope, *, mes=None, ano=None, empresa_slug=None, **_) -> Any:
    _gate(user)
    from modules.empresas.controllers import obligations_controller as ob
    hoje = date.today()
    m, a = int(mes or hoje.month), int(ano or hoje.year)
    if empresa_slug:  # por empresa (CNPJ isolado)
        return _dump(await ob.calendario_empresa(empresa_slug=str(empresa_slug), mes=m, ano=a,
                                                 current_user=user))
    # consolidado ROTULADO por empresa (por_empresa/consolidado com empresa_slug em cada item)
    return _dump(await ob.calendario_grupo(mes=m, ano=a, current_user=user))


async def _nfse_dashboard(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.ged.controllers.nfse_controller import nfse_dashboard
    return _dump(await nfse_dashboard(current_user=user, db=db))


# ---- registro das ops READ no dispatcher consultar_fiscal (filtros vão em `filtros`) ----

registrar_read(_MOD, "situacao_ecac",
               "Situação fiscal no e-CAC (regular/com pendências) do contribuinte, derivada dos "
               "débitos reais do ERP. Filtro opcional: cpf_cnpj (default = o CNPJ configurado; "
               "informe p/ não misturar os dois CNPJ).", _situacao_ecac)
registrar_read(_MOD, "debitos_ecac",
               "Débitos fiscais reais no e-CAC (do puxador de guias/folha do ERP). Filtros "
               "opcionais: competencia_inicio, competencia_fim ('AAAA-MM').", _debitos_ecac)
registrar_read(_MOD, "certidoes",
               "Lista as certidões (CND/FGTS/trabalhista) com status calculado (válida/a vencer/"
               "vencida) e resumo. Sem filtros.", _certidoes)
registrar_read(_MOD, "status_fgts_digital",
               "Status da configuração/integração do FGTS Digital. Sem filtros.",
               _status_fgts_digital)
registrar_read(_MOD, "status_dctfweb",
               "Status da configuração/integração da DCTFWeb. Sem filtros.", _status_dctfweb)
registrar_read(_MOD, "status_simples",
               "Status do Simples Nacional (configuração/enquadramento). Sem filtros.",
               _status_simples)
registrar_read(_MOD, "calendario_obrigacoes",
               "Calendário de obrigações acessórias/guias. Sem empresa_slug = CONSOLIDADO "
               "rotulado por empresa (por_empresa); com empresa_slug (conecta_eletronica / "
               "conecta_patrimonial) = só aquele CNPJ. Filtros: mes, ano, empresa_slug.",
               _calendario_obrigacoes)
registrar_read(_MOD, "nfse_dashboard",
               "Dashboard de faturamento de NFS-e emitidas (métricas por competência). "
               "CONSOLIDADO: soma os DOIS CNPJ (Eletrônica + Patrimonial) — não é de um só. "
               "Sem filtros.", _nfse_dashboard)
