"""Controller de Obrigações Multi-Empresa — Fase 7.

⭐ **O cadastro manda; o molde só preenche o vazio.** (18/08/2026)

Este controller montava o calendário SÓ com o molde do `ObligationsMonitorAgent` — constantes
derivadas do regime. Consequências medidas: o painel dizia "FGTS venceu 07/08, atrasada" num
dia 18 em que o prazo real ia até o 20, e **toda** obrigação vencida aparecia "atrasada"
mesmo já paga, porque o molde não sabe status, valor nem recibo.

Agora: se a empresa tem obrigação REAL em `fiscal_obligations` vencendo no mês, são ELAS que
aparecem, com o status, o valor e o recibo de verdade. O molde entra só onde não há nada
cadastrado, e vai **rotulado** (`fonte: previsto_pelo_regime`) — obrigação existe por lei
mesmo sem linha no banco, e omiti-la seria pior; apresentá-la como fato também.

⚠️ Não tento casar molde com cadastro por tipo: os vocabulários divergem (`FGTS_GUIA` × `FGTS`,
`ISS_AVULSO` × `ISS`, `INSS_GPS` × `INSS`). Casar por aproximação criaria uma terceira verdade.
Ou a empresa tem cadastro no mês, e ele vale inteiro, ou não tem, e aí é previsão.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.database import get_db
from modules.empresas.agents.obligations_monitor import (
    ObligationsMonitorAgent,
    ObrigacaoCalendario,
)

router = APIRouter(prefix="/obrigacoes", tags=["Obrigações Multi-Empresa"])
_agent = ObligationsMonitorAgent()

#: O corte do fechamento fiscal. Obrigação anterior a isto é do período de homologação, cujo
#: status não conciliado é decisão do Jordan e NÃO se persegue retroativamente.
_CORTE = date(2026, 8, 1)

_SQL_REAIS = """
    SELECT e.slug,
           coalesce(e.nome_fantasia, e.razao_social, e.slug)   AS empresa_nome,
           coalesce(e.regime_tributario, '')                   AS regime,
           coalesce(o.tipo, o.nome, '—')                       AS tipo,
           coalesce(o.descricao, o.nome, o.tipo, '—')          AS descricao,
           coalesce(o.competencia_mes, 0)                      AS comp_mes,
           coalesce(o.competencia_ano, 0)                      AS comp_ano,
           o.data_vencimento,
           lower(coalesce(o.status::text, ''))                 AS status,
           o.valor_devido,
           coalesce(o.numero_recibo, '')                       AS recibo
      FROM fiscal_obligations o
      JOIN empresas e ON e.id = o.empresa_id
     WHERE o.active
       AND o.data_vencimento >= :inicio AND o.data_vencimento <= :fim
     ORDER BY e.slug, o.data_vencimento
"""


def _fim_do_mes(ano: int, mes: int) -> date:
    return date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 1) - timedelta(days=1)


async def _reais_por_periodo(db: AsyncSession, inicio: date, fim: date
                             ) -> dict[str, list[ObrigacaoCalendario]]:
    """Obrigações CADASTRADAS que vencem no intervalo, agrupadas por slug da empresa."""
    hoje = date.today()
    fora: dict[str, list[ObrigacaoCalendario]] = {}
    for r in (await db.execute(text(_SQL_REAIS),
                               {"inicio": inicio, "fim": fim})).mappings():
        # `cumprida` no banco → `concluida` no vocabulário do calendário. Vencida e não
        # cumprida é `atrasada` DE VERDADE (o molde só sabia dizer "passou da data").
        if r["status"] == "cumprida":
            status, urgencia = "concluida", "baixa"
        elif r["data_vencimento"] and r["data_vencimento"] < hoje:
            status, urgencia = "atrasada", "critica"
        else:
            status = "pendente"
            urgencia = _agent._urgencia(r["data_vencimento"], hoje)
        fora.setdefault(r["slug"], []).append(ObrigacaoCalendario(
            empresa_slug=r["slug"], empresa_nome=r["empresa_nome"],
            tipo=r["tipo"], descricao=r["descricao"],
            periodo_referencia=f"{r['comp_mes']:02d}/{r['comp_ano']}",
            data_vencimento=r["data_vencimento"], status=status,
            regime=r["regime"], urgencia=urgencia,
            valor_estimado=float(r["valor_devido"]) if r["valor_devido"] is not None else None,
            fonte="cadastro", numero_recibo=r["recibo"] or None,
        ))
    return fora


async def _reais_por_empresa(db: AsyncSession, mes: int, ano: int
                             ) -> dict[str, list[ObrigacaoCalendario]]:
    """Atalho por competência de VENCIMENTO (mês cheio)."""
    return await _reais_por_periodo(db, date(ano, mes, 1), _fim_do_mes(ano, mes))


def _serializar(o: ObrigacaoCalendario) -> dict:
    return {
        "tipo": o.tipo,
        "descricao": o.descricao,
        "periodo": o.periodo_referencia,
        "vencimento": o.data_vencimento.isoformat(),
        "status": o.status,
        "urgencia": o.urgencia,
        "regime": o.regime,
        "link": o.link_sistema,
        "valor": o.valor_estimado,
        "recibo": o.numero_recibo,
        "fonte": o.fonte,
    }


@router.get("/calendario/grupo")
async def calendario_grupo(
    mes: int = Query(default=date.today().month, ge=1, le=12),
    ano: int = Query(default=date.today().year, ge=2024, le=2030),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Calendário consolidado de obrigações de todas as empresas."""
    cal = _agent.gerar_calendario_grupo(mes, ano)
    reais = await _reais_por_empresa(db, mes, ano)

    # Por empresa: quem tem cadastro no mês aparece pelo cadastro; quem não tem, pelo molde.
    por_empresa = {slug: reais.get(slug, obs) for slug, obs in cal.por_empresa.items()}
    for slug, obs in reais.items():          # empresa com cadastro e sem molde não some
        por_empresa.setdefault(slug, obs)

    todas = [o for obs in por_empresa.values() for o in obs]
    hoje = date.today()
    return {
        "mes": cal.mes,
        "ano": cal.ano,
        "resumo": {
            "total": len(todas),
            "criticas": sum(1 for o in todas if o.urgencia == "critica"),
            "atrasadas": sum(1 for o in todas if o.status == "atrasada"),
            "pendentes": sum(1 for o in todas if o.status == "pendente"),
            "concluidas": sum(1 for o in todas if o.status == "concluida"),
            "do_cadastro": sum(1 for o in todas if o.fonte == "cadastro"),
            "previstos_pelo_regime": sum(1 for o in todas if o.fonte != "cadastro"),
        },
        "por_empresa": {slug: [_serializar(o) for o in obs]
                        for slug, obs in por_empresa.items()},
        "consolidado": [
            {"empresa": o.empresa_nome, "empresa_slug": o.empresa_slug, **_serializar(o)}
            for o in sorted(todas, key=lambda x: (x.data_vencimento or hoje))
        ],
    }


@router.get("/calendario/{empresa_slug}")
async def calendario_empresa(
    empresa_slug: str,
    mes: int = Query(default=date.today().month, ge=1, le=12),
    ano: int = Query(default=date.today().year, ge=2024, le=2030),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Calendário de obrigações de uma empresa específica."""
    regime_map = {
        "conecta_eletronica": "lucro_real",
        "conecta_patrimonial": "simples_nacional",
    }
    nome_map = {
        "conecta_eletronica": "Conecta Mais Eletrônica",
        "conecta_patrimonial": "Conecta Mais Patrimonial",
    }
    regime = regime_map.get(empresa_slug, "lucro_real")
    nome = nome_map.get(empresa_slug, empresa_slug)
    reais = (await _reais_por_empresa(db, mes, ano)).get(empresa_slug)
    obs = reais or _agent.gerar_calendario_empresa(empresa_slug, nome, regime, mes, ano)
    return {
        "empresa_slug": empresa_slug,
        "empresa_nome": nome,
        "regime": regime,
        "mes": mes,
        "ano": ano,
        "total": len(obs),
        "fonte": "cadastro" if reais else "previsto_pelo_regime",
        "obrigacoes": [_serializar(o) for o in obs],
    }


@router.get("/alertas")
async def alertas_vencimentos(
    dias: int = Query(default=10, ge=1, le=60),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Alerta sobre obrigações próximas de vencer em todas as empresas.

    Dois defeitos corrigidos em 18/08/2026, ambos do mesmo tipo — o alerta vinha do MOLDE:

    1. **Alertava sobre obrigação já cumprida.** O molde não sabe status, então as três
       acessórias transmitidas em 11/08 (DCTFWEB, ESOCIAL, EFD_REINF) apareceriam como prazo
       a vencer. Prazo cumprido que continua aceso ensina a ignorar o alerta.
    2. **A janela vazava o mês.** Olhava só o mês CORRENTE, então em 28/08, com 10 dias de
       antecedência, uma obrigação vencendo em 03/09 não avisava — justo o caso em que o
       aviso serviria para alguma coisa. Agora a janela é de datas, não de mês.

    O molde continua como reserva onde não há cadastro: obrigação existe por lei mesmo sem
    linha no banco, e o alerta sai ROTULADO com a origem.
    """
    hoje = date.today()
    # ⚠️ Vencida e não paga NÃO some do alerta. A janela original começava em `hoje-5`, e com
    # dado real isso apagou o ISS de 10/08 (R$740,25, em aberto) no dia 18 — obrigação
    # vencida sumindo por decurso de prazo é o silêncio que este módulo existe para evitar.
    # O início é o CORTE de 01/08/2026: antes dele é o período de homologação, cujo status
    # não conciliado é decisão do Jordan e não se persegue.
    inicio = min(_CORTE, hoje - timedelta(days=5))
    fim = hoje + timedelta(days=dias)
    reais = await _reais_por_periodo(db, inicio, fim)

    alertas = []
    for obs in reais.values():
        for o in obs:
            if o.status == "concluida":     # cumprida NÃO é prazo — é o defeito nº 1
                continue
            alertas.append({
                "empresa": o.empresa_nome, "empresa_slug": o.empresa_slug,
                "tipo": o.tipo, "descricao": o.descricao,
                "vencimento": o.data_vencimento.isoformat(),
                "dias_restantes": (o.data_vencimento - hoje).days,
                "urgencia": o.urgencia, "status": o.status,
                "valor": o.valor_estimado, "link": o.link_sistema, "fonte": o.fonte,
            })

    # Sem NENHUM cadastro na janela, cai no molde — mas dito com todas as letras.
    fonte = "cadastro"
    if not reais:
        fonte = "previsto_pelo_regime"
        alertas = [dict(a, fonte=fonte, valor=None) for a in _agent.alertar_vencimentos(dias)]

    return {"alertas": sorted(alertas, key=lambda a: a["dias_restantes"]),
            "dias_antecedencia": dias, "janela": [inicio.isoformat(), fim.isoformat()],
            "fonte": fonte}


@router.get("/dispensadas-simples")
async def obrigacoes_dispensadas(current_user=Depends(get_current_user)):
    """Lista obrigações das quais o Simples Nacional é dispensado."""
    return {
        "regime": "Simples Nacional",
        "empresa": "Conecta Mais Patrimonial",
        "dispensadas": _agent.obrigacoes_dispensadas_simples(),
        "observacao": "Empresas do Simples Nacional são dispensadas dessas obrigações conforme LC 123/2006",
    }
