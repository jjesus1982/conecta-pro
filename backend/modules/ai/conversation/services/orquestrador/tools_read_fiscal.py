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
    # `db` é obrigatório desde 18/08/2026: o calendário passou a ler o CADASTRO real
    # (fiscal_obligations) e só cair no molde do regime onde não há linha. Chamada direta não
    # resolve `Depends`, então a sessão vai explícita — sem ela, TypeError.
    if empresa_slug:  # por empresa (CNPJ isolado)
        return _dump(await ob.calendario_empresa(empresa_slug=str(empresa_slug), mes=m, ano=a,
                                                 db=db, current_user=user))
    # consolidado ROTULADO por empresa (por_empresa/consolidado com empresa_slug em cada item)
    return _dump(await ob.calendario_grupo(mes=m, ano=a, db=db, current_user=user))


async def _nfse_dashboard(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.ged.controllers.nfse_controller import nfse_dashboard
    return _dump(await nfse_dashboard(current_user=user, db=db))


async def _dashboard_fiscal(db, user, scope, **_) -> Any:
    _gate(user)
    from modules.financial.controllers.fiscal_dashboard_controller import get_dashboard_atual
    return _dump(await get_dashboard_atual(_=user))


async def _listar_nfse(db, user, scope, *, competencia=None, cliente=None, status=None,
                       limit=200, offset=0, **_) -> Any:
    _gate(user)
    from modules.ged.controllers.nfse_controller import list_nfse
    return _dump(await list_nfse(competencia=competencia, cliente=cliente, status=status,
                                 limit=int(limit), offset=int(offset), current_user=user, db=db))


async def _listar_nfse_entrada(db, user, scope, *, ano=2026, competencia=None,
                               fornecedor_cnpj=None, categoria=None, empresa=None, **_) -> Any:
    _gate(user)
    from modules.financial.controllers.nfse_entrada_controller import listar_nfse_entrada
    return _dump(await listar_nfse_entrada(ano=int(ano), competencia=competencia,
                                           fornecedor_cnpj=fornecedor_cnpj, categoria=categoria,
                                           empresa=empresa, db=db, _user=user))


async def _resumo_nfse_entrada(db, user, scope, *, ano=2026, mes=None, **_) -> Any:
    _gate(user)
    from modules.financial.controllers.nfse_entrada_controller import resumo_fiscal
    return _dump(await resumo_fiscal(ano=int(ano), mes=(int(mes) if mes else None),
                                     db=db, _user=user))


async def _alertas_obrigacoes(db, user, scope, *, dias=10, **_) -> Any:
    _gate(user)
    from modules.empresas.controllers.obligations_controller import alertas_vencimentos
    # `db` explícito: a rota passou a ler o cadastro real (18/08/2026) e chamada direta não
    # resolve `Depends`. Sem isto, TypeError.
    return _dump(await alertas_vencimentos(dias=int(dias), db=db, current_user=user))


async def _alertas_certificados(db, user, scope, *, tenant_id=None, **_) -> Any:
    _gate(user)
    from modules.government_integrations.controllers.dashboard_controller import (
        listar_alertas_certificados,
    )
    return _dump(await listar_alertas_certificados(current_user=user, tenant_id=tenant_id))


async def _panorama_grupo(db, user, scope, *, mes=None, ano=None, **_) -> Any:
    _gate(user)
    # Panorama fiscal CONSOLIDADO do grupo (receita, impostos, economia de liminares por empresa),
    # dados reais. Base p/ o briefing fiscal executivo.
    from datetime import date as _d
    from modules.empresas.controllers.dashboard_controller import dashboard_fiscal_grupo
    hoje = _d.today()
    return _dump(await dashboard_fiscal_grupo(mes=int(mes or hoje.month), ano=int(ano or hoje.year),
                                              db=db, current_user=user))


async def _guias_pendentes(db, user, scope, *, desde=None, **_) -> Any:
    """Prazo CEGO: obrigação já vencida, sem valor e sem recibo.

    Não é a mesma coisa que "pendente". Pendente COM valor é um prazo a vencer, normal;
    pendente SEM valor é uma pergunta sem resposta — o painel cobra e ninguém sabe quanto
    pagar nem se já foi pago. Foi assim que R$68 mil ficaram acesos de abril a julho de 2026.

    A SQL vive no `calendario_service` (camada de serviço do módulo), não aqui: o agente do
    chat não tem consulta própria, senão a regra passa a existir em dois lugares e diverge.
    """
    _gate(user)
    from datetime import date as _d

    from modules.fiscal_contabil.obrigacoes.calendario_service import sem_guia

    # Default = o CORTE de 01/08/2026. Antes disso é o período de homologação, cujo status
    # não conciliado é decisão do Jordan e NÃO se persegue retroativamente.
    corte = _d.fromisoformat(str(desde)) if desde else _d(2026, 8, 1)
    itens = await sem_guia(db, corte)
    return {"desde": corte.isoformat(), "total": len(itens), "guias_pendentes": itens,
            "leitura": ("Nenhuma obrigação vencida sem guia — prazo cego zerado."
                        if not itens else
                        f"{len(itens)} obrigação(ões) vencida(s) sem valor nem recibo: "
                        "não dá para saber quanto pagar nem se já foi pago.")}


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
registrar_read(_MOD, "dashboard_fiscal",
               "Painel fiscal-financeiro consolidado do mês atual (DRE + notas + fluxo + estoque), "
               "base p/ Lucro Real. Sem filtros.", _dashboard_fiscal)
registrar_read(_MOD, "listar_nfse",
               "Lista NFS-e EMITIDAS (fonte real gov.br nacional, só autorizadas cStat 100). "
               "Filtros: competencia ('AAAA-MM'), cliente (parcial), status, limit, offset.",
               _listar_nfse)
registrar_read(_MOD, "listar_nfse_entrada",
               "Lista NFS-e de ENTRADA (tomadas/recebidas contra os CNPJ) — custos/fornecedores, "
               "com categoria e empresa. Filtros: ano, competencia, fornecedor_cnpj, categoria, "
               "empresa (conecta_eletronica / conecta_patrimonial).", _listar_nfse_entrada)
registrar_read(_MOD, "resumo_nfse_entrada",
               "Resumo fiscal das NFS-e de entrada por fornecedor (base Receita Federal): bruto, "
               "ISS retido. Filtros: ano, mes.", _resumo_nfse_entrada)
registrar_read(_MOD, "alertas_obrigacoes",
               "Alertas de obrigações acessórias/guias próximas de vencer em todas as empresas do "
               "grupo. Filtro: dias (antecedência, default 10).", _alertas_obrigacoes)
registrar_read(_MOD, "alertas_certificados",
               "Alertas de vencimento de certificados digitais A1/A3. Filtro opcional: tenant_id.",
               _alertas_certificados)
registrar_read(_MOD, "panorama_grupo",
               "Panorama fiscal CONSOLIDADO do grupo no mês: receita, impostos e economia de "
               "liminares POR empresa (Eletrônica + Patrimonial), dados reais — briefing fiscal "
               "executivo. Filtros: mes, ano (default = mês/ano atual).", _panorama_grupo)
registrar_read(_MOD, "guias_pendentes",
               "PRAZO CEGO: obrigações já VENCIDAS que não têm nem valor devido nem número de "
               "recibo — o painel cobra e ninguém sabe quanto pagar nem se já foi pago. NÃO "
               "confundir com 'pendente': pendente COM valor é prazo normal a vencer. Mede de "
               "01/08/2026 em diante por padrão (antes disso é o período de homologação, que "
               "não se persegue). Filtro opcional: desde ('AAAA-MM-DD'). Lista vazia é "
               "resultado BOM e verdadeiro.", _guias_pendentes)
