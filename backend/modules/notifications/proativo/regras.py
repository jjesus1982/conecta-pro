"""Fase 5.3 — Registry de regras proativas (SQL determinístico, read-only).

Cada Regra re-deriva sua condição direto da FONTE (idempotente por natureza).
A Regra DECIDE se dispara, para quem e a severidade — o LLM (redator) só escreve
o texto depois. Fail-closed: regra sem destinatário não é registrada.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from modules.financial.services.periodo_contabil import SQL_CONTA_EM_ABERTO

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

FALLBACK_CAIXA_SEM_FOLHA = 10000.0  # spec: CNPJ sem folha própria → R$ 10k fixo


@dataclass(frozen=True)
class Achado:
    """Uma ocorrência concreta de uma condição. `dados` carrega os números EXATOS
    da query (groundedness do redator/template)."""
    correlation_id: str
    dados: dict


@dataclass(frozen=True)
class Regra:
    nome: str
    familia: str
    severidade: str  # info | atencao | critico
    roles_destino: tuple[str, ...]
    action_url: str
    detectar: Callable[[AsyncSession], Awaitable[list[Achado]]]
    template: Callable[[dict], tuple[str, str]]  # dados -> (title, body) determinístico


REGISTRY: dict[str, Regra] = {}


def register(regra: Regra) -> None:
    """Registra a regra. Fail-closed: sem roles_destino não entra (nunca dispara órfão)."""
    if not regra.roles_destino:
        logger.warning("[proativo] regra %r sem roles_destino — NÃO registrada", regra.nome)
        return
    REGISTRY[regra.nome] = regra


# ─────────────────────────── posto_descoberto ───────────────────────────
async def _detectar_posto_descoberto(db: AsyncSession) -> list[Achado]:
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(name,'') AS name, "
        "       required_headcount AS req, current_headcount AS cur "
        "FROM posts "
        "WHERE is_active AND current_headcount < required_headcount"
    ))).mappings().all()
    out = []
    for r in rows:
        faltam = int(r["req"]) - int(r["cur"])
        out.append(Achado(
            correlation_id=f"posto_descoberto:{r['id']}",
            dados={"post_id": r["id"], "posto": r["name"], "faltam": faltam,
                   "req": int(r["req"]), "cur": int(r["cur"])},
        ))
    return out


def _tpl_posto(d: dict) -> tuple[str, str]:
    return (
        f"Posto descoberto: {d['posto']}",
        f"O posto {d['posto']} está com {d['faltam']} vaga(s) descoberta(s) "
        f"({d['cur']}/{d['req']}). Verificar cobertura.",
    )


register(Regra(
    nome="posto_descoberto", familia="operacional", severidade="critico",
    roles_destino=("admin", "gerente_operacional", "supervisor"),
    action_url="/modulos/operacional/postos",
    detectar=_detectar_posto_descoberto, template=_tpl_posto,
))


# ─────────────────────────── certidao_vencendo ───────────────────────────
async def _detectar_certidao_vencendo(db: AsyncSession) -> list[Achado]:
    # TZ canônico: dia-de-negócio = Manaus, NUNCA current_date (sessão Postgres em UTC) —
    # janela diária 20h-23h59 Manaus cairia no dia UTC seguinte e erraria o corte.
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(name,'certidão') AS name, "
        "       expiry_date, "
        "       (expiry_date - (now() AT TIME ZONE 'America/Manaus')::date) AS dias "
        "FROM ged_certidoes "
        "WHERE expiry_date <= (now() AT TIME ZONE 'America/Manaus')::date + 30"
    ))).mappings().all()
    out = []
    for r in rows:
        dias = int(r["dias"])
        vencida = dias < 0
        out.append(Achado(
            correlation_id=f"certidao:{r['id']}:{r['expiry_date']}",
            dados={"cert_id": r["id"], "nome": r["name"], "dias": dias,
                   "expiry": str(r["expiry_date"]), "vencida": vencida,
                   # per-achado: vencida é sempre crítico; a vencer (<=30d) mantém atencao
                   "severidade": "critico" if vencida else "atencao"},
        ))
    return out


def _tpl_certidao(d: dict) -> tuple[str, str]:
    if d["vencida"]:
        return (f"Certidão VENCIDA: {d['nome']}",
                f"A certidão {d['nome']} venceu em {d['expiry']} "
                f"(há {abs(d['dias'])} dia(s)). Regularizar.")
    return (f"Certidão vencendo: {d['nome']}",
            f"A certidão {d['nome']} vence em {d['dias']} dia(s) ({d['expiry']}).")


register(Regra(
    nome="certidao_vencendo", familia="documentos", severidade="atencao",
    roles_destino=("admin",),
    action_url="/modulos/juridico/certidoes",
    detectar=_detectar_certidao_vencendo, template=_tpl_certidao,
))


# ─────────────────────────── caixa_baixo_cnpj ───────────────────────────
async def _detectar_caixa_baixo(db: AsyncSession) -> list[Achado]:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from modules.financial.services.caixa_service import caixa_por_cnpj

    caixa = await caixa_por_cnpj(db)
    competencia = datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m")
    out = []
    for natureza in ("eletronica", "patrimonial"):
        bloco = caixa.get(natureza) or {}
        saldo = bloco.get("saldo")
        if saldo is None:  # sem saldo disponível → silêncio honesto (não fabricar)
            continue
        folha = bloco.get("folha")
        limiar = float(folha) if folha not in (None, 0) else FALLBACK_CAIXA_SEM_FOLHA
        if float(saldo) < limiar:
            slug = bloco.get("slug") or natureza
            out.append(Achado(
                correlation_id=f"caixa_baixo:{slug}:{competencia}",
                dados={"cnpj": bloco.get("nome") or natureza, "slug": slug,
                       "saldo": float(saldo), "limiar": limiar,
                       "banco": bloco.get("banco"),
                       "usou_fallback": folha in (None, 0)},
            ))
    return out


def _tpl_caixa(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl

    base = ("folha do CNPJ" if not d["usou_fallback"] else "piso R$ 10.000")
    return (
        f"Caixa baixo: {d['cnpj']}",
        f"O caixa de {d['cnpj']} ({d['banco']}) está em R$ {_brl(d['saldo'])}, "
        f"abaixo do limiar de R$ {_brl(d['limiar'])} ({base}).",
    )


register(Regra(
    nome="caixa_baixo_cnpj", familia="financeiro", severidade="critico",
    roles_destino=("admin",),  # LGPD: financeiro SÓ diretoria
    action_url="/modulos/financeiro/caixa",
    detectar=_detectar_caixa_baixo, template=_tpl_caixa,
))


# ─────────────────────────── aging_reforcado ───────────────────────────
async def _detectar_aging(db: AsyncSession) -> list[Achado]:
    # MESMA fonte/filtro de notifications.reconciliar_alertas (não duplica).
    row = (await db.execute(text(
        "SELECT count(*), coalesce(sum(net_value),0) FROM receivable_accounts "
        "WHERE due_date < current_date "
        f"AND {SQL_CONTA_EM_ABERTO}"))).fetchone()
    n, total = int(row[0] or 0), float(row[1] or 0)
    if n == 0:
        return []
    return [Achado(
        correlation_id="financeiro_aging:portfolio:None",  # namespace do enqueue_alert
        # espelha notifications.tasks.py:61 (mesmo corte do reconciliador)
        dados={"n": n, "total": total,
               "severidade": "critico" if total >= 50000 else "atencao"},
    )]


def _tpl_aging(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl

    return (
        f"{d['n']} recebível(is) vencido(s)",
        f"Há {d['n']} título(s) vencido(s) em aberto, total R$ {_brl(d['total'])}.",
    )


register(Regra(
    nome="aging_reforcado", familia="financeiro", severidade="atencao",
    roles_destino=("admin",),  # LGPD: financeiro SÓ diretoria
    action_url="/modulos/financeiro/recebiveis",
    detectar=_detectar_aging, template=_tpl_aging,
))


# ─────────────────────────── tributo_a_vencer (B3) ───────────────────────────
async def _detectar_tributo_vencer(db: AsyncSession) -> list[Achado]:
    row = (await db.execute(text(
        "SELECT count(*), coalesce(sum(valor_devido),0) FROM fiscal_obligations "
        "WHERE status='pendente' AND data_vencimento BETWEEN current_date AND current_date + 7"))).fetchone()
    n, total = int(row[0] or 0), float(row[1] or 0)
    if n == 0:
        return []
    return [Achado(correlation_id="financeiro_tributo_vencer:portfolio:None",
                   dados={"n": n, "total": total, "severidade": "atencao"})]


def _tpl_tributo_vencer(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl
    return (f"{d['n']} tributo(s)/guia(s) a vencer em 7 dias",
            f"{d['n']} obrigação(ões) fiscal(is) pendente(s) vence(m) nos próximos 7 dias, total R$ {_brl(d['total'])}.")


register(Regra(
    nome="tributo_a_vencer", familia="financeiro", severidade="atencao",
    roles_destino=("admin",), action_url="/modulos/financeiro/fiscal",
    detectar=_detectar_tributo_vencer, template=_tpl_tributo_vencer,
))


# ─────────────────────────── tributo_VENCIDO ─────────────────────────────────
# A regra acima olha `BETWEEN current_date AND current_date + 7`: só o FUTURO. Ela avisa
# que vai vencer e emudece exatamente no dia em que vence — quando a multa começa a correr.
#
# Medido em 15/08/2026: o ISS de 07/2026 da Eletrônica venceu em 10/08 (guias DAM 21499343
# e 21499344, R$740,25) e passou cinco dias vencido **sem um único alerta**. O vigia
# desligava no instante em que passava a ser necessário.
async def _detectar_tributo_vencido(db: AsyncSession) -> list[Achado]:
    linhas = (await db.execute(text(
        "SELECT e.slug, o.tipo, o.data_vencimento, coalesce(o.valor_devido, 0) "
        "  FROM fiscal_obligations o JOIN empresas e ON e.id = o.empresa_id "
        " WHERE o.active AND o.status = 'pendente' "
        "   AND o.data_vencimento < current_date "
        # Corte de 01/08/2026 (decisão do Jordan): abril a julho é status não conciliado do
        # período de homologação, não dívida — a CRF de FGTS de 11/08 prova. Alertar sobre
        # aquilo devolveria ao sino os R$68 mil de ruído que ninguém mais lia.
        "   AND o.data_vencimento >= DATE '2026-08-01' "
        " ORDER BY o.data_vencimento"))).fetchall()
    if not linhas:
        return []
    total = float(sum(float(x[3]) for x in linhas))
    detalhe = "; ".join(f"{s} {t} venceu {v:%d/%m}" for s, t, v, _ in linhas[:5])
    return [Achado(correlation_id="financeiro_tributo_vencido:portfolio:None",
                   dados={"n": len(linhas), "total": total, "detalhe": detalhe,
                          "severidade": "critico"})]


def _tpl_tributo_vencido(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl
    return (f"{d['n']} tributo(s) VENCIDO(S) sem baixa",
            f"{d['n']} obrigação(ões) fiscal(is) já venceu(ram) e continua(m) pendente(s), "
            f"total R$ {_brl(d['total'])}. {d['detalhe']}. "
            f"Multa e juros correm a partir do vencimento.")


register(Regra(
    nome="tributo_vencido", familia="financeiro", severidade="critico",
    roles_destino=("admin",), action_url="/modulos/financeiro/fiscal",
    detectar=_detectar_tributo_vencido, template=_tpl_tributo_vencido,
))


# ─────────────────────────── concentracao_pagaveis (B3) ───────────────────────────
async def _detectar_pagaveis_7d(db: AsyncSession) -> list[Achado]:
    row = (await db.execute(text(
        "SELECT count(*), coalesce(sum(net_value),0) FROM payable_accounts "
        "WHERE due_date BETWEEN current_date AND current_date + 7 "
        f"AND {SQL_CONTA_EM_ABERTO}"))).fetchone()
    n, total = int(row[0] or 0), float(row[1] or 0)
    if total < 10000:  # só alerta concentração relevante
        return []
    return [Achado(correlation_id="financeiro_pagaveis_7d:portfolio:None",
                   dados={"n": n, "total": total, "severidade": "critico" if total >= 50000 else "atencao"})]


def _tpl_pagaveis_7d(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl
    return (f"{d['n']} conta(s) a pagar vencendo em 7 dias",
            f"R$ {_brl(d['total'])} em {d['n']} conta(s) a pagar vence(m) nos próximos 7 dias — planeje o caixa.")


register(Regra(
    nome="concentracao_pagaveis", familia="financeiro", severidade="atencao",
    roles_destino=("admin",), action_url="/modulos/financeiro/pagar",
    detectar=_detectar_pagaveis_7d, template=_tpl_pagaveis_7d,
))


# ─────────────────────────── recebivel_grande_vencendo (B3) ───────────────────────────
async def _detectar_receb_grande(db: AsyncSession) -> list[Achado]:
    # Título individual alto (≥R$5k) vencendo nos próximos 3 dias — pegar ANTES de atrasar.
    rows = (await db.execute(text(
        "SELECT customer_name, net_value, due_date FROM receivable_accounts "
        "WHERE due_date BETWEEN current_date AND current_date + 3 AND coalesce(net_value,0) >= 5000 "
        f"AND {SQL_CONTA_EM_ABERTO} "
        "ORDER BY net_value DESC LIMIT 5"))).fetchall()
    out = []
    for r in rows:
        cli = str(r[0] or "cliente")
        out.append(Achado(
            correlation_id=f"financeiro_receb_grande:{cli}:{r[2]}",  # dedup por cliente+vencimento
            dados={"cliente": cli, "valor": float(r[1] or 0), "venc": str(r[2]), "severidade": "atencao"}))
    return out


def _tpl_receb_grande(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl
    return (f"Recebível de {d['cliente'][:30]} a vencer",
            f"R$ {_brl(d['valor'])} de {d['cliente']} vence em {d['venc']} — confirme o recebimento no dia.")


register(Regra(
    nome="recebivel_grande_vencendo", familia="financeiro", severidade="atencao",
    roles_destino=("admin",), action_url="/modulos/financeiro/recebiveis",
    detectar=_detectar_receb_grande, template=_tpl_receb_grande,
))


# ─────────────────────────── justificativa_parada ───────────────────────────
async def _detectar_justificativa(db: AsyncSession) -> list[Achado]:
    rows = (await db.execute(text(
        "SELECT id, coalesce(employee_id,'') AS emp, "
        "       EXTRACT(EPOCH FROM (now() - created_at))/3600 AS horas "
        "FROM gp_justifications "
        "WHERE lower(coalesce(status,'')) IN ('pending','pendente') "
        "AND created_at < now() - interval '48 hours'"))).mappings().all()
    out = []
    for r in rows:
        out.append(Achado(
            correlation_id=f"justificativa_parada:{r['id']}",
            dados={"just_id": int(r["id"]), "horas": int(r["horas"] or 0)},
        ))
    return out


def _tpl_justificativa(d: dict) -> tuple[str, str]:
    return (
        "Justificativa de ponto parada",
        f"Uma justificativa de ponto está pendente de análise há {d['horas']}h "
        f"(id {d['just_id']}). Revisar.",
    )


register(Regra(
    nome="justificativa_parada", familia="ponto", severidade="atencao",
    roles_destino=("admin", "gerente_operacional"),
    action_url="/modulos/operacional/ponto/justificativas",
    detectar=_detectar_justificativa, template=_tpl_justificativa,
))


# ─────────────────────────── juridico_prazo (silenciosa até ter dado) ────────
async def _detectar_juridico(db: AsyncSession) -> list[Achado]:
    # TZ canônico: dia-de-negócio = Manaus, NUNCA a data crua da sessão Postgres (UTC).
    # Vocabulário real da tabela é {aberto, cumprido, atrasado} (prazos_service._STATUS_VALIDOS);
    # os dois valores excluídos antes (ver git blame) nunca existem na tabela — exclusão
    # morta que fazia prazos já resolvidos alertarem pra sempre. Só 'cumprido' sai do radar.
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(titulo,'prazo') AS titulo, data_limite, "
        "       (data_limite - (now() AT TIME ZONE 'America/Manaus')::date) AS dias "
        "FROM juridico_prazos "
        "WHERE data_limite <= (now() AT TIME ZONE 'America/Manaus')::date + 7 "
        "AND lower(coalesce(status,'')) NOT IN ('cumprido')"))).mappings().all()
    out = []
    for r in rows:
        out.append(Achado(
            correlation_id=f"juridico_prazo:{r['id']}:{r['data_limite']}",
            dados={"prazo_id": r["id"], "titulo": r["titulo"], "dias": int(r["dias"]),
                   # per-achado: prazo já vencido é sempre crítico; a vencer mantém atencao
                   "severidade": "critico" if int(r["dias"]) < 0 else "atencao"},
        ))
    return out


def _tpl_juridico(d: dict) -> tuple[str, str]:
    return (
        f"Prazo jurídico: {d['titulo']}",
        f"O prazo '{d['titulo']}' vence em {d['dias']} dia(s).",
    )


register(Regra(
    nome="juridico_prazo", familia="juridico", severidade="critico",
    roles_destino=("admin",),
    action_url="/modulos/juridico/prazos",
    detectar=_detectar_juridico, template=_tpl_juridico,
))


# ─────────────────────────── recrutamento_parado (silenciosa até funil) ──────
async def _detectar_recrutamento(db: AsyncSession) -> list[Achado]:
    # Hoje candidates.status só tem 'ativo' (sem estágio de funil). A regra existe e
    # acorda quando houver funil: candidato parado num estágio 'em_analise'/'triagem'
    # há >7d. Enquanto só houver 'ativo', é silenciosa (não fabricar movimento).
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(name,'candidato') AS name "
        "FROM candidates "
        "WHERE coalesce(is_active,true) AND coalesce(is_deleted,false)=false "
        "AND lower(coalesce(status,'')) IN ('em_analise','em_análise','triagem','entrevista') "
        "AND updated_at < now() - interval '7 days'"))).mappings().all()
    out = []
    for r in rows:
        out.append(Achado(
            correlation_id=f"recrutamento_parado:{r['id']}",
            dados={"candidate_id": r["id"], "nome": r["name"]},
        ))
    return out


def _tpl_recrutamento(d: dict) -> tuple[str, str]:
    return (
        f"Candidato parado: {d['nome']}",
        f"O candidato {d['nome']} está há mais de 7 dias sem movimento no funil.",
    )


register(Regra(
    nome="recrutamento_parado", familia="recrutamento", severidade="info",
    roles_destino=("admin", "gerente_operacional"),
    action_url="/modulos/rh/recrutamento",
    detectar=_detectar_recrutamento, template=_tpl_recrutamento,
))


# ═══════════════════════ DP · VIGÍLIA DE PRAZOS (Fase F2) ═══════════════════════
# O quadro branco da Pyetra é 100% PRAZO, e vivia só na parede: o aviso prévio do Keyson
# venceu e o funcionário seguiu trabalhando 7 dias — risco trabalhista puro. Estas regras
# são o vigia que faltava.
#
# LEI (travada no plano): **captura ≥ vigília**. Um watcher sobre dado de baixa cobertura
# MENTE. Por isso cada detector aqui devolve TAMBÉM o denominador (`universo`) — quantos
# casos existem no mundo vs quantos estão registrados —, e o template DIZ isso na cara.
# Silêncio de watcher cego é pior que alerta, porque parece "está tudo certo".

# O Conecta PRO está EM CONSTRUÇÃO: hoje o dado vem em boa parte da Portte/eSocial e o
# fluxo nativo vai sendo assumido módulo a módulo. Então "não está no sistema" quase nunca
# é negligência do DP — é migração em curso. O texto do alerta precisa dizer isso, senão
# soa como cobrança e a pessoa para de confiar no vigia.
MSG_SEM_REGISTRO = ("⚠️ Este vigia só enxerga o que já está no fluxo nativo. Enquanto o "
                    "dado vier da Portte/eSocial, o caso pode existir e não aparecer aqui.")


# ─────────────────────── dp_aviso_previo_vencendo ───────────────────────
async def _detectar_aviso_previo(db: AsyncSession) -> list[Achado]:
    """Aviso prévio vencendo em ≤7 dias ou JÁ VENCIDO (o caso Keyson).

    Fonte: o último dia de trabalho, por DUAS leituras — nessa ordem de precedência:
      1. `notice_start_date + notice_period_days` (o cálculo formal do aviso);
      2. `last_working_day` (o dado que o DP realmente preenche).

    Por que as duas: em 13/08/2026 medi a taxa de preenchimento em produção —
    `notice_start_date` 1/3, `last_working_day` 3/3. Lendo só a primeira, o KEYSON
    (último dia 14/08, `notice_start_date` NULL) era filtrado para FORA do alarme e o
    prazo dele venceria em silêncio. Campo esparso não é fonte: é metade de uma fonte.

    Vencido é CRÍTICO: cada dia trabalhado além do prazo é passivo.
    """
    # `fim` calculado uma vez em subquery — repetir a expressão em SELECT e WHERE foi
    # exatamente o que escondeu o COALESCE quando o campo formal era nulo.
    rows = (await db.execute(text(
        "SELECT id, nome, fim, (fim - current_date) AS dias, origem FROM ("
        "  SELECT t.id::text AS id, e.nome AS nome, "
        "         CASE WHEN t.notice_start_date IS NOT NULL AND coalesce(t.notice_period_days,0) > 0 "
        "              THEN (t.notice_start_date "
        "                    + (t.notice_period_days || ' days')::interval)::date "
        "              ELSE t.last_working_day END AS fim, "
        "         CASE WHEN t.notice_start_date IS NOT NULL AND coalesce(t.notice_period_days,0) > 0 "
        "              THEN 'aviso' ELSE 'ultimo_dia' END AS origem "
        "  FROM termination_processes t JOIN employees e ON e.id = t.employee_id "
        "  WHERE lower(coalesce(t.status::text,'')) "
        "        NOT IN ('completed','cancelled') "
        # Só quem ainda está ATIVO tem aviso prévio a vencer. Colaborador já desligado no
        # cadastro (data_demissao) com processo esquecido em 'initiated' ficava no quadro como
        # "último dia JÁ PASSOU" por 25 dias (KEYSON, 07/09/2026) — processo pendente é assunto
        # da regra dp_desligamento_sem_processo, não deste prazo.
        "    AND e.status = 'ativo'"
        ") s WHERE fim IS NOT NULL AND fim <= current_date + 7"
    ))).mappings().all()
    # denominador honesto: desligamentos em curso que NENHUMA das duas leituras enxerga
    sem_registro = (await db.execute(text(
        "SELECT count(*) FROM termination_processes "
        "WHERE last_working_day IS NULL "
        "AND (notice_start_date IS NULL OR coalesce(notice_period_days,0) = 0) "
        "AND lower(coalesce(status::text,'')) NOT IN ('completed','cancelled')"
    ))).scalar() or 0
    return [Achado(
        correlation_id=f"dp_aviso_previo:{r['id']}:{r['fim']}",
        dados={"nome": r["nome"], "fim": str(r["fim"]), "dias": int(r["dias"]),
               "vencido": int(r["dias"]) < 0, "sem_registro": int(sem_registro),
               "origem": r["origem"]},
    ) for r in rows]


def _tpl_aviso_previo(d: dict) -> tuple[str, str]:
    # O texto diz QUAL leitura achou o caso. Quando o aviso não está registrado, chamar o
    # `last_working_day` de "aviso prévio" seria afirmar um registro que não existe — e o RH
    # iria procurar na tela um campo vazio.
    por_ultimo_dia = d.get("origem") == "ultimo_dia"
    termo = "O último dia de trabalho" if por_ultimo_dia else "O aviso prévio"
    if d["vencido"]:
        cabeca = f"🔴 {'Último dia JÁ PASSOU' if por_ultimo_dia else 'Aviso prévio VENCIDO'}: {d['nome']}"
        corpo = (f"{termo} de {d['nome']} foi em {d['fim']} — há {abs(d['dias'])} dia(s). "
                 f"Se a pessoa continua trabalhando, cada dia é passivo trabalhista. "
                 f"Formalize o desligamento ou registre a prorrogação.")
    else:
        cabeca = (f"{'Último dia' if por_ultimo_dia else 'Aviso prévio vence'} "
                  f"em {d['dias']} dia(s): {d['nome']}")
        corpo = (f"{termo} de {d['nome']} é {d['fim']} ({d['dias']} dia(s)). "
                 f"Prepare a rescisão para não estourar o prazo.")
    if por_ultimo_dia:
        corpo += (" ⚠️ Este processo NÃO tem aviso prévio registrado "
                  "(`notice_start_date` vazio) — o prazo veio do último dia de trabalho. "
                  "Registre o aviso para o cálculo da rescisão fechar.")
    if d["sem_registro"]:
        corpo += (f" {MSG_SEM_REGISTRO} Há {d['sem_registro']} desligamento(s) em curso sem "
                  f"NENHUMA data de prazo — nem aviso, nem último dia. Esses eu não enxergo.")
    return cabeca, corpo


register(Regra(
    nome="dp_aviso_previo_vencendo", familia="dp", severidade="critico",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_aviso_previo, template=_tpl_aviso_previo,
))


# ─────────────────────── dp_ferias_limite_gozo ───────────────────────
async def _detectar_ferias_limite(db: AsyncSession) -> list[Achado]:
    """Período aquisitivo com limite para gozo vencendo/vencido e saldo (art. 137).

    Fonte: employee_vacation_periods (períodos REAIS, carregados da programação da Portte).

    Duas exclusões que evitam alerta mentiroso — aprendidas medindo em 05/08:
      • CONTRATO SUSPENSO não corre aquisitivo (caso ARYELTON: rescisão indireta em curso,
        suspensão orientada pelo jurídico). Sem isso ele reaparece como falso positivo todo mês.
      • Quem TEM verba de gozo na folha (rubrica 0060/1061) gozou de fato mesmo sem
        solicitação — é buraco de LANÇAMENTO do DP, não risco art. 137. Rubrica genérica
        (`LIKE '%FERIAS%'`) NÃO serve: 0061/0062 incluem proporcionais de RESCISÃO, que são
        indenização e marcariam demitido como "gozou".
    """
    rows = (await db.execute(text(
        "SELECT p.id::text AS id, e.nome AS nome, p.expires_at AS limite, "
        "       p.days_remaining AS saldo, (p.expires_at - current_date) AS dias, "
        "       EXISTS (SELECT 1 FROM folha_verba_espelho v "
        "               WHERE v.employee_id = p.employee_id AND v.codigo IN ('0060','1061')) AS gozou "
        "FROM employee_vacation_periods p JOIN employees e ON e.id = p.employee_id "
        "WHERE coalesce(p.days_remaining,0) > 0 AND p.expires_at IS NOT NULL "
        "  AND p.expires_at <= current_date + 30 "
        # PJ não tem férias CLT. O ORLAILSON caiu aqui como falso 'art.137': foi desligado
        # como CLT com férias INDENIZADAS (verba 0062, rescisão) e recontratado como PJ.
        "  AND lower(coalesce(e.status,'')) NOT IN ('suspenso','demitido','inativo') "
        "  AND lower(coalesce(e.status,'')) NOT LIKE 'pj%' "
        "  AND lower(coalesce(e.tipo_contrato,'')) <> 'pj' "
        "ORDER BY p.expires_at"
    ))).mappings().all()
    return [Achado(
        correlation_id=f"dp_ferias_limite:{r['id']}",
        dados={"nome": r["nome"], "limite": str(r["limite"]), "saldo": int(r["saldo"]),
               "dias": int(r["dias"]), "gozou_sem_registro": bool(r["gozou"])},
    ) for r in rows]


def _tpl_ferias_limite(d: dict) -> tuple[str, str]:
    if d["gozou_sem_registro"]:
        return (
            f"Férias sem registro: {d['nome']}",
            f"A folha mostra que {d['nome']} gozou férias, mas não há solicitação registrada — "
            f"o saldo aparece como {d['saldo']} dia(s) e o limite é {d['limite']}. "
            f"NÃO é risco de férias em dobro; é lançamento faltando. Registre para o saldo bater.",
        )
    if d["dias"] < 0:
        return (
            f"🔴 Férias em DOBRO (art. 137): {d['nome']}",
            f"O limite para gozo de {d['nome']} venceu em {d['limite']} — há {abs(d['dias'])} dia(s) — "
            f"e ainda restam {d['saldo']} dia(s). Férias não concedidas no prazo são pagas EM DOBRO. "
            f"{MSG_SEM_REGISTRO}",
        )
    return (
        f"Férias vencem em {d['dias']} dia(s): {d['nome']}",
        f"{d['nome']} tem {d['saldo']} dia(s) e o limite para gozo é {d['limite']} "
        f"({d['dias']} dia(s)). Programe antes de virar pagamento em dobro.",
    )


register(Regra(
    nome="dp_ferias_limite_gozo", familia="dp", severidade="critico",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_ferias_limite, template=_tpl_ferias_limite,
))


# ─────────────────────── dp_desligamento_sem_processo ───────────────────────
async def _detectar_desligamento_sem_processo(db: AsyncSession) -> list[Achado]:
    """Pessoa com data de desligamento no cadastro e SEM processo de rescisão.

    Este é o vigia do próprio vigia. O watcher de aviso prévio só enxerga o que virou
    `termination_processes` — e o caso Keyson provou que o desligamento pode existir no
    mundo (e no quadro da parede) sem existir no sistema. Sem esta regra, o silêncio do
    watcher de prazo seria lido como "está tudo em ordem", que é a falha original.

    E este vigia tem o MESMO ponto cego que ele vigia. Medido em 13/08/2026: 25 pessoas
    com status `demitido`/`inativo` e só 10 com data — as outras **15 não têm nem
    `data_desligamento` nem `data_demissao`**, e o corte de 90 dias não tem o que cortar.
    Elas não viram achado e nunca virariam.

    Não invento data para elas (seria fabricação) e não jogo as 15 no sino de uma vez
    (alarme que toca sempre ninguém lê). Levo o número JUNTO com os achados, como
    `dp_aviso_previo_vencendo` faz: silêncio vira quantidade declarada.
    """
    rows = (await db.execute(text(
        "SELECT e.id::text AS id, e.nome AS nome, "
        "       coalesce(e.data_desligamento, e.data_demissao) AS dt "
        "FROM employees e "
        "WHERE coalesce(e.data_desligamento, e.data_demissao) IS NOT NULL "
        "  AND coalesce(e.data_desligamento, e.data_demissao) >= current_date - 90 "
        "  AND NOT EXISTS (SELECT 1 FROM termination_processes t WHERE t.employee_id = e.id) "
        "ORDER BY 3 DESC"
    ))).mappings().all()
    # o que esta regra NÃO consegue ver: desligado pelo status, sem data nenhuma.
    sem_data = (await db.execute(text(
        "SELECT count(*) FROM employees "
        "WHERE lower(coalesce(status,'')) IN ('demitido','inativo') "
        "  AND coalesce(data_desligamento, data_demissao) IS NULL"
    ))).scalar() or 0
    return [Achado(
        correlation_id=f"dp_desligamento_sem_processo:{r['id']}",
        dados={"nome": r["nome"], "dt": str(r["dt"]), "sem_data": int(sem_data)},
    ) for r in rows]


def _tpl_desligamento_sem_processo(d: dict) -> tuple[str, str]:
    corpo = (
        f"{d['nome']} tem desligamento em {d['dt']} no cadastro e ainda não tem processo de "
        f"rescisão aqui — normal enquanto o Conecta PRO consome dado da Portte/eSocial e o "
        f"fluxo nativo vai sendo assumido. Vale trazer para cá: é o processo que faz o "
        f"aviso prévio ser vigiado, o TRCT sair e o S-2299 nascer."
    )
    if d.get("sem_data"):
        corpo += (f" Além destes, há {d['sem_data']} pessoa(s) com status demitido/inativo e "
                  f"SEM data de desligamento no cadastro — essas eu não consigo datar, então "
                  f"não sei se são recentes. Preencher a data é o que as traz para este vigia.")
    return (f"Desligamento a migrar para o fluxo nativo: {d['nome']}", corpo)


register(Regra(
    nome="dp_desligamento_sem_processo", familia="dp", severidade="atencao",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_desligamento_sem_processo, template=_tpl_desligamento_sem_processo,
))


# ─────────────────────── dp_termino_experiencia ───────────────────────
async def _detectar_termino_experiencia(db: AsyncSession) -> list[Achado]:
    """Fim de contrato de experiência (30 e 90 dias) chegando — a coluna "Términos de
    Contrato" do quadro da Pyetra.

    DERIVA DA ADMISSÃO, não do `tipo_contrato` — que é NULL em 50 de 52 ativos e faria o
    watcher nascer cego. A derivação foi CONFERIDA contra o quadro dela (06/08):
        ALEXANDRE/KELLY/NAILSON  adm 19/07 + 30 = 18/08  ← quadro diz 18/08
        RENE/PAULO/EULER         adm 19/06 + 90 = 17/09  ← quadro diz 17/09
    Bate ao dia nos dois marcos, então a convenção 30+60 está certa para esta empresa.

    ⚠️ Assume contrato de experiência padrão. Quem entrou direto por prazo indeterminado
    aparece aqui como falso positivo — por isso o corpo DIZ que é derivado da admissão e
    pede para ignorar se não se aplica. Preencher `tipo_contrato` elimina o ruído; enquanto
    ele for NULL, prefiro alertar de mais a deixar a coluna do quadro sem vigia nenhum.
    Perder o marco converte o contrato em indeterminado por decurso de prazo.
    """
    rows = (await db.execute(text(
        "SELECT e.id::text AS id, e.nome AS nome, e.data_admissao AS adm, m.marco AS marco, "
        "       (e.data_admissao + m.marco) AS venc, "
        "       ((e.data_admissao + m.marco) - current_date) AS dias "
        "FROM employees e CROSS JOIN (VALUES (30), (90)) AS m(marco) "
        "WHERE lower(coalesce(e.status,'')) = 'ativo' AND e.data_admissao IS NOT NULL "
        "  AND lower(coalesce(e.tipo_contrato,'')) <> 'pj' "
        "  AND (e.data_admissao + m.marco) BETWEEN current_date AND current_date + 15 "
        "ORDER BY 5"
    ))).mappings().all()
    return [Achado(
        correlation_id=f"dp_termino_exp:{r['id']}:{r['marco']}",
        dados={"nome": r["nome"], "adm": str(r["adm"]), "marco": int(r["marco"]),
               "venc": str(r["venc"]), "dias": int(r["dias"])},
    ) for r in rows]


def _tpl_termino_experiencia(d: dict) -> tuple[str, str]:
    etapa = "1º período (30 dias)" if d["marco"] == 30 else "2º período (90 dias — final)"
    fim = ("Decida a PRORROGAÇÃO para os 60 dias seguintes."
           if d["marco"] == 30 else
           "Decida entre EFETIVAR ou RESCINDIR. Passar da data converte o contrato em "
           "prazo indeterminado por decurso, e aí a saída vira rescisão comum (com aviso "
           "prévio e multa de FGTS).")
    return (
        f"Experiência vence em {d['dias']} dia(s): {d['nome']}",
        f"{d['nome']} (admitido em {d['adm']}) fecha o {etapa} em {d['venc']}. {fim} "
        f"Derivado da data de admissão — se esta pessoa não está em contrato de "
        f"experiência, ignore e preencha `tipo_contrato` no cadastro para não repetir.",
    )


register(Regra(
    nome="dp_termino_experiencia", familia="dp", severidade="critico",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_termino_experiencia, template=_tpl_termino_experiencia,
))


# ─────────────────────── dp_admissao_em_curso ───────────────────────
async def _detectar_admissao_em_curso(db: AsyncSession) -> list[Achado]:
    """Admissão parada antes da data prevista de início — a coluna "Admissões" do quadro.

    O quadro dela encadeia prazos por etapa (docs → revisão → ASO → admissão). Aqui a regra
    é mais simples e honesta: alerta quando a data prevista de início está chegando (ou
    passou) e o processo NÃO está concluído. Não invento as sub-datas dela; uso a única
    âncora que o sistema tem de verdade, que é `expected_start_date`.

    Não alerta sobre admissão sem processo: enquanto o Conecta PRO consome dado da
    Portte/eSocial, gente entra na folha sem passar por aqui, e cobrar isso como pendência
    seria ruído de migração, não risco.
    """
    rows = (await db.execute(text(
        "SELECT a.id::text AS id, coalesce(a.candidate_name, '—') AS nome, "
        "       a.expected_start_date AS inicio, a.status::text AS st, "
        "       (a.expected_start_date - current_date) AS dias, "
        "       a.medical_exam_date AS aso "
        "FROM admission_processes a "
        "WHERE a.expected_start_date IS NOT NULL "
        "  AND lower(coalesce(a.status::text,'')) NOT IN "
        "      ('completed','concluido','concluído','cancelled','cancelado') "
        "  AND a.expected_start_date <= current_date + 10 "
        "ORDER BY a.expected_start_date"
    ))).mappings().all()
    return [Achado(
        correlation_id=f"dp_admissao_curso:{r['id']}",
        dados={"nome": r["nome"], "inicio": str(r["inicio"]), "dias": int(r["dias"]),
               "status": (r["st"] or "").replace("_", " "), "tem_aso": r["aso"] is not None},
    ) for r in rows]


def _tpl_admissao_em_curso(d: dict) -> tuple[str, str]:
    quando = (f"começa em {d['dias']} dia(s)" if d["dias"] > 0
              else ("começa hoje" if d["dias"] == 0 else f"deveria ter começado há {abs(d['dias'])} dia(s)"))
    aso = "" if d["tem_aso"] else " O ASO admissional ainda não tem data — sem ele a pessoa não pode iniciar."
    return (
        f"Admissão {quando}: {d['nome']}",
        f"A admissão de {d['nome']} está em '{d['status']}' e o início previsto é "
        f"{d['inicio']}.{aso} Conclua o processo para o vínculo, o contrato e o S-2200 nascerem.",
    )


register(Regra(
    nome="dp_admissao_em_curso", familia="dp", severidade="atencao",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_admissao_em_curso, template=_tpl_admissao_em_curso,
))


# ─────────────────────── dp_aso_vencendo ───────────────────────
async def _detectar_aso_vencendo(db: AsyncSession) -> list[Achado]:
    """ASO vencendo em ≤30 dias ou vencido. Sem ASO válido o colaborador não pode trabalhar
    (NR-7) e a empresa responde em fiscalização."""
    rows = (await db.execute(text(
        # a coluna é `data_validade` (não data_vencimento) e o nome vem só do join
        "SELECT a.id::text AS id, coalesce(e.nome, '—') AS nome, "
        "       a.data_validade AS venc, (a.data_validade - current_date) AS dias, "
        "       coalesce(a.tipo::text, '') AS tipo "
        "FROM gp_asos a JOIN employees e ON CAST(e.id AS TEXT) = CAST(a.employee_id AS TEXT) "
        "WHERE a.data_validade IS NOT NULL "
        "  AND a.data_validade <= current_date + 30 "
        "  AND lower(coalesce(e.status,'')) = 'ativo' "
        # só o ASO MAIS RECENTE de cada pessoa: um antigo vencido não é pendência se já
        # existe um novo válido — alertar sobre ele seria falso positivo
        "  AND a.data_validade = (SELECT max(a2.data_validade) FROM gp_asos a2 "
        "                         WHERE CAST(a2.employee_id AS TEXT) = CAST(a.employee_id AS TEXT)) "
        "ORDER BY a.data_validade"
    ))).mappings().all()
    # AGREGA quando são muitos: 25 alertas individuais soterrariam a mesa e a Pyetra
    # pararia de olhar — o alerta que enterra os outros é tão ruim quanto o que não existe.
    # Até 5, alerta nominal (dá para agir um a um). Acima disso, 1 cartão com a contagem.
    if len(rows) > 5:
        vencidos = [r for r in rows if int(r["dias"]) < 0]
        return [Achado(
            correlation_id=f"dp_aso_lote:{len(rows)}:{len(vencidos)}",
            dados={"lote": True, "total": len(rows), "vencidos": len(vencidos),
                   "nomes": ", ".join(r["nome"] for r in rows[:6])
                            + (f" e mais {len(rows) - 6}" if len(rows) > 6 else "")},
        )]
    return [Achado(
        correlation_id=f"dp_aso_vencendo:{r['id']}",
        dados={"nome": r["nome"], "venc": str(r["venc"]), "dias": int(r["dias"]),
               "tipo": r["tipo"], "lote": False},
    ) for r in rows]


def _tpl_aso(d: dict) -> tuple[str, str]:
    if d.get("lote"):
        return (f"ASO: {d['vencidos']} vencido(s) de {d['total']} a renovar",
                f"{d['vencidos']} colaborador(es) estão com ASO VENCIDO e {d['total']} no total "
                f"precisam de renovação em até 30 dias. Sem ASO válido a pessoa não pode "
                f"trabalhar (NR-7) e a empresa responde em fiscalização. "
                f"São: {d['nomes']}. Agende o lote na tela de SST.")
    if d["dias"] < 0:
        return (f"🔴 ASO VENCIDO: {d['nome']}",
                f"O ASO de {d['nome']} venceu em {d['venc']} — há {abs(d['dias'])} dia(s). "
                f"Sem ASO válido a pessoa não pode trabalhar (NR-7) e a empresa responde em "
                f"fiscalização. Agende a renovação.")
    return (f"ASO vence em {d['dias']} dia(s): {d['nome']}",
            f"O ASO de {d['nome']} vence em {d['venc']}. Agende a renovação antes para não "
            f"parar o colaborador.")


register(Regra(
    nome="dp_aso_vencendo", familia="dp", severidade="critico",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_aso_vencendo, template=_tpl_aso,
))


# ─────────────────────── dp_folha_devida ───────────────────────
async def _detectar_folha_devida(db: AsyncSession) -> list[Achado]:
    """Competência fechada e sem folha calculada — o ritmo mensal do quadro.

    Dispara a partir do dia 1º do mês seguinte, se a competência anterior não tem nenhuma
    linha `source_system='conecta'`. Só uma vez por competência (correlation_id).
    """
    from datetime import date

    hoje = date.today()
    ano, mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    n = (await db.execute(text(
        "SELECT count(*) FROM hr_payslips WHERE reference_year=:a AND reference_month=:m "
        "AND source_system='conecta'"), {"a": ano, "m": mes})).scalar() or 0
    if n:
        return []
    ativos = (await db.execute(text(
        "SELECT count(*) FROM employees WHERE status='ativo'"))).scalar() or 0
    if not ativos:  # base vazia → silêncio honesto
        return []
    return [Achado(
        correlation_id=f"dp_folha_devida:{ano}-{mes:02d}",
        dados={"comp": f"{mes:02d}/{ano}", "ativos": int(ativos)},
    )]


def _tpl_folha_devida(d: dict) -> tuple[str, str]:
    return (f"Folha de {d['comp']} ainda não calculada",
            f"A competência {d['comp']} fechou e não há folha calculada aqui "
            f"({d['ativos']} colaborador(es) ativos). Gere pela tela de folha — é ela que "
            f"alimenta holerite, eSocial e o pagamento.")


register(Regra(
    nome="dp_folha_devida", familia="dp", severidade="atencao",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_folha_devida, template=_tpl_folha_devida,
))


# ─────────────────────── dp_ponto_a_fechar ───────────────────────
async def _detectar_ponto_a_fechar(db: AsyncSession) -> list[Achado]:
    """Mês virado e ponto do mês anterior sem fechamento, para quem TEM batida.

    Só alerta sobre quem bateu ponto — quem não bateu não tem o que fechar, e cobrar
    fechamento de quem não tem batida seria ruído da migração (o ponto vem do Sólides).
    """
    from datetime import date

    hoje = date.today()
    ano, mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    n = (await db.execute(text(
        "SELECT count(DISTINCT p.employee_id) FROM gp_clock_punches p "
        "JOIN employees e ON CAST(e.id AS TEXT) = CAST(p.employee_id AS TEXT) "
        "WHERE EXTRACT(MONTH FROM p.punch_timestamp)=:m AND EXTRACT(YEAR FROM p.punch_timestamp)=:a "
        "  AND lower(coalesce(e.status,'')) = 'ativo' "
        "  AND NOT EXISTS (SELECT 1 FROM gp_monthly_closings c "
        "                  WHERE CAST(c.employee_id AS TEXT) = CAST(p.employee_id AS TEXT) "
        "                    AND c.month=:m AND c.year=:a AND coalesce(c.fechado,false))"),
        {"a": ano, "m": mes})).scalar() or 0
    if not n:
        return []
    return [Achado(
        correlation_id=f"dp_ponto_a_fechar:{ano}-{mes:02d}",
        dados={"comp": f"{mes:02d}/{ano}", "n": int(n)},
    )]


def _tpl_ponto_a_fechar(d: dict) -> tuple[str, str]:
    return (f"Ponto de {d['comp']}: {d['n']} sem fechamento",
            f"{d['n']} colaborador(es) bateram ponto em {d['comp']} e o mês não foi fechado. "
            f"O fechamento consolida horas, extras e faltas — é o que a folha consome.")


register(Regra(
    nome="dp_ponto_a_fechar", familia="dp", severidade="atencao",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_ponto_a_fechar, template=_tpl_ponto_a_fechar,
))


# ─────────────────────── dp_ferias_sem_decisao ───────────────────────
async def _detectar_ferias_sem_decisao(db: AsyncSession) -> list[Achado]:
    """Pedido de férias cujo período JÁ PASSOU e ninguém aprovou nem rejeitou.

    Buraco encontrado em 13/08/2026, e nenhuma das outras regras de férias o cobria:
    `dp_ferias_limite_gozo` olha o período AQUISITIVO (art. 137) e `dp_retorno_ferias` só
    olha quem já foi APROVADO. Um pedido que fica em `SUBMITTED` até o período vencer não
    aparece em lugar nenhum — some entre as duas.

    Medido: **13 pedidos SUBMITTED com o período já vencido**, o mais antigo de 01/04, e
    todos ainda pendentes em agosto. Um deles é do ADAILSON, que TEM verba de férias na
    folha — ou seja, gozou de fato e o pedido continua "aguardando aprovação".

    Isso é passivo dos dois lados: se a pessoa gozou, falta o registro que sustenta o
    pagamento; se não gozou, o direito continua correndo e ninguém decidiu.

    Não julga QUAL decisão é a certa — aprovar retroativo, rejeitar ou cancelar é do RH.
    Só garante que a ausência de decisão pare de ser silenciosa.
    """
    rows = (await db.execute(text(
        "SELECT v.id::text AS id, e.nome AS nome, v.start_date AS ini, v.end_date AS fim, "
        "       (current_date - v.end_date) AS dias_vencido, "
        "       EXISTS (SELECT 1 FROM folha_verba_espelho f "
        "               WHERE f.employee_id = v.employee_id "
        "                 AND f.codigo IN ('0060','1061')) AS tem_verba "
        "FROM hr_vacation_requests v JOIN employees e ON e.id = v.employee_id "
        "WHERE upper(coalesce(v.status,'')) = 'SUBMITTED' "
        "  AND v.end_date < current_date "
        "ORDER BY v.end_date"
    ))).mappings().all()
    return [Achado(
        correlation_id=f"dp_ferias_sem_decisao:{r['id']}",
        dados={"nome": r["nome"], "ini": str(r["ini"]), "fim": str(r["fim"]),
               "dias": int(r["dias_vencido"]), "tem_verba": bool(r["tem_verba"]),
               "total": len(rows)},
    ) for r in rows]


def _tpl_ferias_sem_decisao(d: dict) -> tuple[str, str]:
    corpo = (f"O pedido de férias de {d['nome']} ({d['ini']} a {d['fim']}) continua "
             f"'aguardando aprovação' e o período terminou há {d['dias']} dia(s). "
             f"Aprovar retroativo, rejeitar ou cancelar — qualquer uma resolve; deixar "
             f"pendente é a única que não.")
    if d["tem_verba"]:
        corpo += (" ⚠️ A folha desta pessoa TEM verba de férias (0060/1061): ela gozou de "
                  "fato, e o registro que sustenta esse pagamento é justamente este pedido "
                  "que nunca foi aprovado.")
    if d.get("total", 0) > 1:
        corpo += f" Há {d['total']} pedido(s) nesta situação."
    return (f"Férias sem decisão há {d['dias']} dia(s): {d['nome']}", corpo)


register(Regra(
    nome="dp_ferias_sem_decisao", familia="dp", severidade="atencao",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/departamento-pessoal?t=g-ferias",
    detectar=_detectar_ferias_sem_decisao, template=_tpl_ferias_sem_decisao,
))


# ─────────────────────── dp_retorno_ferias ───────────────────────
async def _detectar_retorno_ferias(db: AsyncSession) -> list[Achado]:
    """Retorno de férias em ≤3 dias (o quadro da Pyetra rastreia isso à mão).

    Só solicitações APROVADAS: em julho havia 5 SUBMITTED de 30 dias de gente que trabalhou
    o mês inteiro (uma delas bateu ponto 116 vezes). Pedido não aprovado não é férias.
    """
    rows = (await db.execute(text(
        "SELECT v.id::text AS id, e.nome AS nome, v.end_date AS fim, "
        "       (v.end_date - current_date) AS dias "
        "FROM hr_vacation_requests v JOIN employees e ON e.id = v.employee_id "
        "WHERE upper(coalesce(v.status,'')) = 'APPROVED' "
        "  AND v.end_date BETWEEN current_date - 1 AND current_date + 3 "
        "ORDER BY v.end_date"
    ))).mappings().all()
    return [Achado(
        correlation_id=f"dp_retorno_ferias:{r['id']}",
        dados={"nome": r["nome"], "fim": str(r["fim"]), "dias": int(r["dias"])},
    ) for r in rows]


def _tpl_retorno_ferias(d: dict) -> tuple[str, str]:
    quando = "hoje" if d["dias"] == 0 else (f"em {d['dias']} dia(s)" if d["dias"] > 0 else "ontem")
    return (
        f"Retorno de férias {quando}: {d['nome']}",
        f"{d['nome']} volta de férias em {d['fim']}. Confirme a escala e o retorno ao posto.",
    )


register(Regra(
    nome="dp_retorno_ferias", familia="dp", severidade="atencao",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/aprovacoes",
    detectar=_detectar_retorno_ferias, template=_tpl_retorno_ferias,
))


if __name__ == "__main__":
    import asyncio
    import inspect
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            # ---- posto_descoberto: Achados == oráculo vivo ----
            oráculo_postos = (await db.execute(text(
                "SELECT count(*) FROM posts WHERE is_active "
                "AND current_headcount < required_headcount"))).scalar()
            achados_postos = await REGISTRY["posto_descoberto"].detectar(db)
            assert len(achados_postos) == oráculo_postos, (len(achados_postos), oráculo_postos)
            if achados_postos:
                a = achados_postos[0]
                assert a.correlation_id.startswith("posto_descoberto:")
                t, b = REGISTRY["posto_descoberto"].template(a.dados)
                assert str(a.dados["faltam"]) in b  # groundedness do template

            # ---- certidao_vencendo: Achados == oráculo (<=30d OU vencida), dia de Manaus ----
            oráculo_cert = (await db.execute(text(
                "SELECT count(*) FROM ged_certidoes "
                "WHERE expiry_date <= (now() AT TIME ZONE 'America/Manaus')::date + 30"
            ))).scalar()
            achados_cert = await REGISTRY["certidao_vencendo"].detectar(db)
            assert len(achados_cert) == oráculo_cert, (len(achados_cert), oráculo_cert)
            for a in achados_cert:
                esperado = "critico" if a.dados["vencida"] else "atencao"
                assert a.dados["severidade"] == esperado, (a.dados["severidade"], esperado)

            # ---- caixa_baixo_cnpj: cada Achado tem saldo < limiar; limiar>0 ----
            achados_caixa = await REGISTRY["caixa_baixo_cnpj"].detectar(db)
            for a in achados_caixa:
                assert a.dados["saldo"] < a.dados["limiar"]
                assert a.dados["limiar"] > 0
                assert a.correlation_id.startswith("caixa_baixo:")

            # ---- aging_reforcado: Achado agregado == existe vencido? (mesma fonte do reconciliador) ----
            venc = (await db.execute(text(
                "SELECT count(*), coalesce(sum(net_value),0) FROM receivable_accounts "
                "WHERE due_date < current_date "
                f"AND {SQL_CONTA_EM_ABERTO}"))).fetchone()
            achados_aging = await REGISTRY["aging_reforcado"].detectar(db)
            assert len(achados_aging) == (1 if int(venc[0]) > 0 else 0)
            if achados_aging:
                assert achados_aging[0].dados["n"] == int(venc[0])
                assert achados_aging[0].correlation_id == "financeiro_aging:portfolio:None"
                # fix pós-review (4): severidade dinâmica espelha notifications/tasks.py:61
                esperado_sev = "critico" if achados_aging[0].dados["total"] >= 50000 else "atencao"
                assert achados_aging[0].dados["severidade"] == esperado_sev, (
                    achados_aging[0].dados["severidade"], achados_aging[0].dados["total"])

            # ---- justificativa_parada: == pending/pendente há >48h (fix pós-review 3) ----
            j = (await db.execute(text(
                "SELECT count(*) FROM gp_justifications "
                "WHERE lower(coalesce(status,'')) IN ('pending','pendente') "
                "AND created_at < now() - interval '48 hours'"))).scalar()
            achados_just = await REGISTRY["justificativa_parada"].detectar(db)
            assert len(achados_just) == int(j)
            src_just = inspect.getsource(_detectar_justificativa)
            assert "'pending','pendente'" in src_just, "SQL de justificativa deve cobrir os dois vocabulários"

            # ---- mudas honestas: hoje 0, mas registradas (acordam sozinhas) ----
            assert "juridico_prazo" in REGISTRY and "recrutamento_parado" in REGISTRY
            achados_jur = await REGISTRY["juridico_prazo"].detectar(db)
            assert len(achados_jur) == (await db.execute(text(
                "SELECT count(*) FROM juridico_prazos "
                "WHERE data_limite <= (now() AT TIME ZONE 'America/Manaus')::date + 7 "
                "AND lower(coalesce(status,'')) NOT IN ('cumprido')"))).scalar()
            for a in achados_jur:
                esperado = "critico" if a.dados["dias"] < 0 else "atencao"
                assert a.dados["severidade"] == esperado, (a.dados["severidade"], esperado)

            # ---- fix pós-review (1)+(2): SQL do juridico sem current_date cru; usa Manaus; vocabulário real ----
            src_jur = inspect.getsource(_detectar_juridico)
            assert "current_date" not in src_jur, "juridico_prazo não pode usar current_date cru (TZ UTC)"
            assert "America/Manaus" in src_jur
            assert "NOT IN ('cumprido')" in src_jur
            assert "concluido" not in src_jur and "cancelado" not in src_jur

            achados_rec = await REGISTRY["recrutamento_parado"].detectar(db)
            assert len(achados_rec) == (await db.execute(text(
                "SELECT count(*) FROM candidates "
                "WHERE coalesce(is_active,true) AND coalesce(is_deleted,false)=false "
                "AND lower(coalesce(status,'')) IN ('em_analise','em_análise','triagem','entrevista') "
                "AND updated_at < now() - interval '7 days'"))).scalar()

            # ---- fail-closed: regra sem roles não entra ----
            n0 = len(REGISTRY)
            register(Regra(nome="__x__", familia="x", severidade="info",
                           roles_destino=(), action_url="/",
                           detectar=achados_postos.__class__,  # dummy, não usado
                           template=lambda d: ("", "")))
            assert "__x__" not in REGISTRY and len(REGISTRY) == n0

            print(f"OK regras — postos={len(achados_postos)} cert={len(achados_cert)} "
                  f"caixa={len(achados_caixa)} aging={len(achados_aging)} "
                  f"just={len(achados_just)} jur={len(achados_jur)} rec={len(achados_rec)}")
        await eng.dispose()

    asyncio.run(main())


# ─────────────────────── dp_ponto_de_afastado ───────────────────────
async def _detectar_ponto_de_afastado(db: AsyncSession) -> list[Achado]:
    """Batida de ponto de quem está AFASTADO ou SUSPENSO.

    Quem está afastado pelo INSS não deveria bater ponto. Quando bate, só há três explicações
    e as três exigem alguém olhando hoje, não no fechamento:
      • voltou e ninguém encerrou o afastamento (a folha vai pagar errado);
      • outra pessoa está cobrindo o posto e batendo COM O CRACHÁ DELE — o ponto fica no nome
        errado, e isso é o que mais dói numa reclamatória;
      • o cadastro está errado (não está afastado de verdade).

    Nasceu de um caso real em 09/08: CINTIA, afastada pelo INSS, apareceu com 3 noites
    batidas. Só foi vista porque eu estava conferindo outra coisa — por isso virou vigília.

    Não apaga nada: a batida é registro e, se for crachá de terceiro, é a evidência.
    """
    rows = (await db.execute(text(
        "SELECT CAST(e.id AS TEXT) AS id, coalesce(e.nome,'—') AS nome, "
        "       coalesce(e.status,'') AS status, count(*) AS n, "
        "       max(k.punch_timestamp)::date AS ultima "
        "FROM gp_clock_punches k JOIN employees e ON e.id = k.employee_id "
        "WHERE lower(coalesce(e.status,'')) IN "
        "        ('afastado_inss','afastado','suspenso','licenca','afastado_acidente') "
        "  AND k.punch_timestamp >= current_date - 30 "
        "  AND coalesce(e.is_homologacao,false) = false "
        "GROUP BY 1,2,3"
    ))).mappings().all()
    return [Achado(correlation_id=f"dp_ponto_de_afastado:{r['id']}:{r['ultima']}",
                   dados=dict(r)) for r in rows]


def _tpl_ponto_afastado(d: dict) -> tuple[str, str]:
    return (f"Ponto batido por quem está afastado: {d['nome']}",
            f"{d['nome']} está com status '{d['status']}' e registrou {d['n']} batida(s) nos "
            f"últimos 30 dias, a última em {d['ultima']}. Ou voltou e o afastamento não foi "
            f"encerrado, ou outra pessoa está batendo com o crachá dele. Confira com o posto "
            f"antes do fechamento — não apague a batida.")


register(Regra(
    nome="dp_ponto_de_afastado", familia="dp", severidade="critico",
    roles_destino=("admin", "rh", "dp"),
    action_url="/redesign/departamento-pessoal?t=g-ponto&tab=ponto",
    detectar=_detectar_ponto_de_afastado, template=_tpl_ponto_afastado,
))


# ─────────────────────────── razao_parado ───────────────────────────
# Nasceu do fechamento contábil parado desde julho/2026: um holerite sem data
# derrubava a transação inteira, o beat diário escrevia a exceção no log TODO
# DIA, e ninguém leu. O sinal existia; faltava alguém olhando.
#
# A guarda de competência FUTURA não é detalhe: sem ela a regra dispara 94
# achados no primeiro dia (holerites de 2026-11/12 que o fechamento barra de
# propósito), e alarme ruidoso é alarme desligado em duas semanas.
SQL_RAZAO_PARADO = """
    SELECT h.reference_period AS competencia, count(*) AS holerites
    FROM hr_payslips h
    WHERE coalesce(h.total_earnings, 0) > 0
      AND h.payslip_code IS NOT NULL
      AND h.reference_period IS NOT NULL
      AND h.reference_period <= to_char(now() AT TIME ZONE 'America/Manaus', 'YYYY-MM')
      -- O razão nasce no corte contábil (01/08/2026): folha anterior a ele NUNCA terá
      -- lançamento, por desenho. Sem este filtro a regra segurou 7 alertas permanentes
      -- (jan–jul/2026) de 11/08 a 07/09/2026 — sete 'persistentes' que não eram de ninguém.
      AND h.reference_period >= :corte
      AND NOT EXISTS (
          SELECT 1 FROM accounting_entries a
          WHERE a.documento_ref = 'FOLHA-' || h.payslip_code
      )
    GROUP BY h.reference_period
    ORDER BY h.reference_period
"""


async def _detectar_razao_parado(db: AsyncSession) -> list[Achado]:
    from modules.financial.services.periodo_contabil import CORTE_CONTABIL  # noqa: PLC0415

    rows = (await db.execute(text(SQL_RAZAO_PARADO),
                             {"corte": str(CORTE_CONTABIL)[:7]})).mappings().all()
    return [
        Achado(
            correlation_id=f"razao_parado:{r['competencia']}",
            dados={"competencia": r["competencia"], "holerites": int(r["holerites"])},
        )
        for r in rows
    ]


def _tpl_razao_parado(d: dict) -> tuple[str, str]:
    return (
        f"Razão sem lançamento: folha {d['competencia']}",
        f"{d['holerites']} holerite(s) da competência {d['competencia']} não têm "
        f"lançamento no razão contábil. O fechamento pode ter parado em silêncio — "
        f"foi assim que julho/2026 ficou com 63 lançamentos contra 181 de junho. "
        f"Rodar o fechamento e conferir o log do beat financial.fechar_razao_auto.",
    )


register(Regra(
    nome="razao_parado", familia="financeiro", severidade="critico",
    roles_destino=("admin",),
    action_url="/redesign/financeiro?t=g-contabil",
    detectar=_detectar_razao_parado, template=_tpl_razao_parado,
))


# ─────────────────────────── extrato_duplicado ───────────────────────────
# Em 2026-08-10 removi 880 linhas duplicadas do extrato (R$212 mil de entrada e
# R$326 mil de saída em dobro): o MESMO PIX importado pela API do Inter e por um
# CSV avulso, cada um com sua própria chave. O índice único em `external_id`
# nunca teve chance — o importador inventava a chave.
#
# Por que ALARME e não índice único: neste domínio o mesmo valor, no mesmo dia,
# para a mesma contraparte É legítimo (3 saques de R$1.000 no Banco24h = limite
# por operação). Só o ID do próprio banco distinguiria, e ele é nulo em 3.036 das
# 4.502 linhas. Então detecta-se o AUMENTO, não a existência.
#
# Linha de base MEDIDA em 2026-08-10: 123 grupos / 130 linhas excedentes, todas
# de mesma origem (80 csv_import, 50 inter) e plausivelmente legítimas.
# Quem limpar duplicata de verdade deve BAIXAR este número.
#
# 07/09/2026: a regra contava GÊMEOS LEGÍTIMOS como dobro — dois VT de R$ 32 à mesma pessoa
# no mesmo dia têm ids DISTINTOS no banco (idx_bank_tx_external_id é UNIQUE) e não são
# duplicata. Medido: 256 "excedentes", 135 eram gêmeos com ids distintos. Só grupo com ao
# menos UMA linha sem external_id pode ser importação repetida: 121 hoje, todas herdadas
# (csv_import antigo). O alerta gritou "126 novas em dobro" todo dia por um mês por isso.
BASE_DUPLICATAS_EXCEDENTES = 121

_CANONICA_SQL = (
    "regexp_replace(regexp_replace(regexp_replace("
    "upper(coalesce(description,'')), 'CP :[0-9]+-', '', 'g'), "
    "'[^A-Z0-9 ]', ' ', 'g'), ' +', ' ', 'g')"
)

SQL_EXTRATO_DUPLICADO = f"""
    SELECT coalesce(sum(n - 1), 0) AS excedentes, count(*) AS grupos
    FROM (
        SELECT bank_account_id, transaction_date::date AS d, amount,
               {_CANONICA_SQL} AS f, count(*) AS n
        FROM bank_transactions
        GROUP BY 1, 2, 3, 4
        HAVING count(*) > 1 AND count(*) > count(external_id)  -- gêmeos com ids distintos não são dobro
    ) t
"""


async def _detectar_extrato_duplicado(db: AsyncSession) -> list[Achado]:
    r = (await db.execute(text(SQL_EXTRATO_DUPLICADO))).mappings().first()
    if not r:
        return []
    excedentes = int(r["excedentes"] or 0)
    if excedentes <= BASE_DUPLICATAS_EXCEDENTES:
        return []
    novas = excedentes - BASE_DUPLICATAS_EXCEDENTES
    return [Achado(
        correlation_id=f"extrato_duplicado:{excedentes}",
        dados={"excedentes": excedentes, "grupos": int(r["grupos"] or 0),
               "base": BASE_DUPLICATAS_EXCEDENTES, "novas": novas},
    )]


def _tpl_extrato_duplicado(d: dict) -> tuple[str, str]:
    return (
        f"Extrato duplicado: {d['novas']} linha(s) novas em dobro",
        f"O extrato tem {d['excedentes']} linhas excedentes em {d['grupos']} grupos "
        f"(linha de base conhecida: {d['base']}). Apareceram {d['novas']} novas desde "
        f"a última limpeza — provável importação repetida. Em 08/2026 isso somou "
        f"R$563 mil contados em dobro. Conferir antes de confiar em saldo e fluxo.",
    )


register(Regra(
    nome="extrato_duplicado", familia="financeiro", severidade="critico",
    roles_destino=("admin",),
    action_url="/redesign/financeiro?t=g-bancos",
    detectar=_detectar_extrato_duplicado, template=_tpl_extrato_duplicado,
))


# ─────────────────────────── caixa_divergente ───────────────────────────
# O razão precisa provar contra o extrato. Antes da escrituração ele conhecia
# 266 de 4.517 movimentações e dizia R$1.401.547,03 no banco — nada avisava.
#
# O oráculo NÃO é `bank_accounts.current_balance`: esse campo está parado desde
# 14/04/2026 (a âncora `balance_after` de 13/04 projeta R$20.081,84 e o cadastro
# diz R$9.619,35). Alarme sobre número velho toca sozinho e é desligado.
#
# O oráculo é o EXTRATO: toda movimentação tem que ter lançamento e todo
# lançamento em conta de banco tem que vir de uma movimentação. Isso é exato,
# não estatístico — por isso a tolerância cobre só arredondamento.
TOLERANCIA_CAIXA = 1.00

# Só cobra o que JÁ VENCEU: movimentação de hoje ainda não passou pela
# escrituração (beat 08:40, depois dos syncs de 08:00/08:10). Sem este corte o
# alarme acusaria a defasagem normal do dia e tocaria quase todo dia — alarme que
# toca sempre é alarme que ninguém lê. Os dois lados usam o MESMO corte, senão a
# comparação fica torta.
SQL_CAIXA_DIVERGENTE = """
    -- Compara até D-2, não D-1: o extrato de ontem chega às 08:10 (Cora) e é escriturado
    -- depois; a regra roda a cada 15 min e, das 08:15 às 08:46, via o meio do caminho e
    -- tocava o sino DUAS vezes por manhã, todo dia (15 avisos em 7 dias até 07/09/2026,
    -- valores diferentes a cada um, e às 09:00 já não havia diferença). D-2 está em repouso.
    WITH corte AS (
        SELECT (now() AT TIME ZONE 'America/Manaus')::date AS hoje,
               CAST(:inicio AS date) AS inicio
    )
    SELECT
        (SELECT coalesce(sum(CASE WHEN conta_debito LIKE '1.1.1%' THEN valor ELSE -valor END), 0)
         FROM accounting_entries, corte
         WHERE (conta_debito LIKE '1.1.1%' OR conta_credito LIKE '1.1.1%')
           AND data_lancamento >= corte.inicio
           AND data_lancamento < corte.hoje - 1) AS razao,
        -- ordem de pagamento INICIADA (status='pendente') não é movimento: a escrituração a
        -- pula de propósito (14/08). Somá-la aqui fabricava "Caixa não bate" (07/09/2026).
        (SELECT coalesce(sum(amount), 0) FROM bank_transactions, corte
          WHERE transaction_date >= corte.inicio
            AND transaction_date < corte.hoje - 1
            AND coalesce(status, '') <> 'pendente') AS extrato,
        (SELECT count(*) FROM bank_transactions b, corte
          WHERE b.amount <> 0
            AND b.transaction_date >= corte.inicio
            AND b.transaction_date < corte.hoje - 1
            AND coalesce(b.status, '') <> 'pendente'
            AND NOT EXISTS (SELECT 1 FROM accounting_entries a
                            WHERE a.bank_transaction_id = b.id)) AS sem_lancamento
"""


async def _detectar_caixa_divergente(db: AsyncSession) -> list[Achado]:
    # Só o período ABERTO. Antes do corte a escrituração recusa lançamento novo
    # (período fechado) — sem esta janela, uma movimentação histórica que
    # aparecesse depois seria barrada na entrada E contada aqui como pendente:
    # o alarme tocaria para sempre sem nenhuma ação capaz de calá-lo.
    from modules.financial.services.periodo_contabil import CORTE_CONTABIL

    r = (await db.execute(text(SQL_CAIXA_DIVERGENTE),
                          {"inicio": CORTE_CONTABIL})).mappings().first()
    if not r:
        return []
    razao = float(r["razao"] or 0)
    extrato = float(r["extrato"] or 0)
    dif = abs(razao - extrato)
    sem = int(r["sem_lancamento"] or 0)
    if dif <= TOLERANCIA_CAIXA and sem == 0:
        return []
    return [Achado(
        # Correlaciona pelo par (diferença, pendentes): enquanto o furo não muda
        # não repica o sino todo dia; mudou, avisa de novo.
        correlation_id=f"caixa_divergente:{round(dif)}:{sem}",
        dados={"razao": round(razao, 2), "extrato": round(extrato, 2),
               "divergencia": round(dif, 2), "sem_lancamento": sem,
               "tolerancia": TOLERANCIA_CAIXA},
    )]


def _tpl_caixa_divergente(d: dict) -> tuple[str, str]:
    if d["sem_lancamento"] and d["divergencia"] <= d["tolerancia"]:
        titulo = f"{d['sem_lancamento']} movimentação(ões) do banco sem lançamento"
    else:
        titulo = f"Caixa não bate: R$ {d['divergencia']:,.2f} de diferença"
    return (
        titulo,
        f"O razão diz R$ {d['razao']:,.2f} nas contas de banco e o extrato soma "
        f"R$ {d['extrato']:,.2f} — diferença de R$ {d['divergencia']:,.2f}.\n\n"
        f"Movimentações sem lançamento no razão: {d['sem_lancamento']}.\n\n"
        f"Ou entrou movimentação que não foi escriturada, ou lançou-se algo que o "
        f"extrato não tem. Conferir o beat financeiro-escriturar-extrato (05:20) e "
        f"a prova de caixa no balancete.",
    )


register(Regra(
    nome="caixa_divergente", familia="financeiro", severidade="critico",
    roles_destino=("admin",),  # LGPD: financeiro SÓ diretoria
    action_url="/redesign/financeiro?t=g-contabil",
    detectar=_detectar_caixa_divergente, template=_tpl_caixa_divergente,
))


# ─────────────────────────── saida_sem_origem ───────────────────────────
# O padrão que o Jordan quer: nada sai da conta sem ter nascido no sistema como
# um pagável. Em 11/08/2026 isso era 0 de 175 saídas — o sistema anota depois,
# não autoriza antes.
#
# Alarmar em TODAS as 175 seria inútil: 51 são a folha (1 pagável ↔ 51 PIX, um
# vínculo 1:N que ainda não existe) e 88 são miúdos abaixo de R$100. Alarme que
# aponta o que ninguém pode resolver hoje é desligado na primeira semana.
# Acima do limiar são 2 saídas — as duas para o sócio. Isso é acionável.
#
# `< hoje` porque a escrituração e a conciliação rodam 08:30/08:40: cobrar a
# movimentação do próprio dia é cobrar a defasagem normal.
SQL_SAIDA_SEM_ORIGEM = """
    SELECT bt.id::text AS id, bt.transaction_date::date AS dia, abs(bt.amount) AS valor,
           coalesce(bt.justificativa_categoria, '?') AS categoria,
           left(coalesce(bt.counterparty_name, bt.description, ''), 60) AS quem
    FROM bank_transactions bt
    WHERE bt.amount < 0
      AND abs(bt.amount) >= :limiar
      AND bt.transaction_date >= CAST(:inicio AS date)
      AND bt.transaction_date < (now() AT TIME ZONE 'America/Manaus')::date
      -- as DUAS direções: 1:1 (pagável→saída) e N:1 (saída→pagável), que é o
      -- caso da folha — um pagável para 51 PIX. Olhar só uma direção faria o
      -- alarme cobrar salário já coberto.
      AND NOT EXISTS (SELECT 1 FROM payable_accounts p
                      WHERE p.transacao_bancaria_id = bt.id::text)
      AND bt.payable_payment_id IS NULL
    ORDER BY abs(bt.amount) DESC
    LIMIT 20
"""


async def _detectar_saida_sem_origem(db: AsyncSession) -> list[Achado]:
    from modules.financial.services.cobertura_sistema import LIMIAR_SAIDA_SEM_ORIGEM
    from modules.financial.services.periodo_contabil import CORTE_CONTABIL

    rows = (await db.execute(text(SQL_SAIDA_SEM_ORIGEM),
                             {"limiar": LIMIAR_SAIDA_SEM_ORIGEM,
                              "inicio": CORTE_CONTABIL})).mappings().all()
    return [Achado(
        # Um achado POR SAÍDA: cada uma exige uma decisão diferente (registrar o
        # pagável, ou explicar por que saiu sem ele). Agrupar viraria um número
        # que ninguém age em cima.
        correlation_id=f"saida_sem_origem:{r['id']}",
        dados={"valor": round(float(r["valor"]), 2), "dia": str(r["dia"]),
               "categoria": r["categoria"], "quem": r["quem"],
               "limiar": LIMIAR_SAIDA_SEM_ORIGEM},
    ) for r in rows]


def _tpl_saida_sem_origem(d: dict) -> tuple[str, str]:
    return (
        f"R$ {d['valor']:,.2f} saiu sem estar registrado no sistema",
        f"Saída de R$ {d['valor']:,.2f} em {d['dia']} para {d['quem']} "
        f"(categoria: {d['categoria']}) não tem nenhum pagável correspondente.\n\n"
        f"O dinheiro saiu da conta sem ter passado pelo sistema — não há o que "
        f"aprovou, nem contra o que conferir. Registrar o pagável (ainda que "
        f"depois) ou explicar a saída.\n\n"
        f"Só saídas acima de R$ {d['limiar']:,.2f} entram neste aviso.",
    )


register(Regra(
    nome="saida_sem_origem", familia="financeiro", severidade="atencao",
    roles_destino=("admin",),  # LGPD: financeiro SÓ diretoria
    action_url="/redesign/financeiro?t=g-pagar",
    detectar=_detectar_saida_sem_origem, template=_tpl_saida_sem_origem,
))



# ─────────────────────────── pj_sem_nota_fiscal ───────────────────────────
# POLÍTICA do Jordan a partir de 12/08/2026: **PJ só recebe apresentando nota
# fiscal.** Antes não era exigido — daí os 9 prestadores cadastrados como PJ
# terem ZERO NFS-e tomada numa base de 135 notas que vai de 2022 a 2026.
#
# A regra é do CADASTRO, não do extrato: quem só olha o extrato enxerga apenas
# quem já foi pago, e a política precisa avisar ANTES de pagar. Os 9 vêm de
# `employees.status IN ('pj_ativo','pj_pendente')` — confirmado pelo Jordan.
#
# Dois bloqueios distintos, e a ordem importa:
#   1. sem CNPJ cadastrado (7 de 9) — não dá para exigir nota de quem não tem
#      CNPJ registrado, nem para conferir se a nota chegou. Bloqueia a política
#      inteira, então vem primeiro.
#   2. sem nota no período — o bloqueio do pagamento em si.
SQL_PJ_SEM_NOTA = """
    SELECT e.nome,
           e.status,
           regexp_replace(coalesce(e.cnpj, ''), '[^0-9]', '', 'g') AS cnpj,
           EXISTS (
               SELECT 1 FROM nfse_tomadas_nacional t
               WHERE t.data_emissao >= CAST(:inicio AS date)
                 AND (
                     (coalesce(e.cnpj, '') <> ''
                      AND regexp_replace(coalesce(t.prestador_cnpj, ''), '[^0-9]', '', 'g')
                          = regexp_replace(e.cnpj, '[^0-9]', '', 'g'))
                  OR unaccent(upper(coalesce(t.prestador_nome, ''))) LIKE
                     '%' || split_part(unaccent(upper(e.nome)), ' ', 1) || '%'
                 )
           ) AS tem_nota,
           (SELECT coalesce(sum(abs(bt.amount)), 0) FROM bank_transactions bt
             WHERE bt.amount < 0
               AND bt.transaction_date >= CAST(:inicio AS date)
               AND unaccent(upper(coalesce(bt.counterparty_name, ''))) LIKE
                   '%' || split_part(unaccent(upper(e.nome)), ' ', 1) || '%'
               AND unaccent(upper(coalesce(bt.counterparty_name, ''))) LIKE
                   '%' || split_part(unaccent(upper(e.nome)), ' ',
                        array_length(string_to_array(e.nome, ' '), 1)) || '%') AS pago
    FROM employees e
    WHERE e.status IN ('pj_ativo', 'pj_pendente')
    ORDER BY e.nome
"""


async def _detectar_pj_sem_nota(db: AsyncSession) -> list[Achado]:
    from modules.financial.services.periodo_contabil import CORTE_CONTABIL

    rows = (await db.execute(text(SQL_PJ_SEM_NOTA),
                             {"inicio": CORTE_CONTABIL})).mappings().all()
    sem_cnpj = [r["nome"] for r in rows if not r["cnpj"]]
    sem_nota = [{"nome": r["nome"], "pago": round(float(r["pago"] or 0), 2),
                 "cnpj": r["cnpj"] or ""} for r in rows if not r["tem_nota"]]
    if not sem_cnpj and not sem_nota:
        return []
    pago_sem_nota = round(sum(x["pago"] for x in sem_nota), 2)
    return [Achado(
        correlation_id=f"pj_sem_nota:{len(sem_cnpj)}:{len(sem_nota)}:{round(pago_sem_nota)}",
        dados={"total_pj": len(rows), "sem_cnpj": sem_cnpj, "sem_nota": sem_nota,
               "pago_sem_nota": pago_sem_nota},
    )]


def _tpl_pj_sem_nota(d: dict) -> tuple[str, str]:
    partes = []
    if d["sem_cnpj"]:
        partes.append(
            f"SEM CNPJ CADASTRADO ({len(d['sem_cnpj'])} de {d['total_pj']}) — não dá para "
            f"exigir nota de quem não tem CNPJ registrado, nem conferir se ela chegou:\n"
            + "\n".join(f"  • {n}" for n in d["sem_cnpj"]))
    if d["sem_nota"]:
        partes.append(
            f"SEM NOTA NO PERÍODO ({len(d['sem_nota'])}):\n"
            + "\n".join(f"  • {x['nome']}"
                        + (f" — já recebeu R$ {x['pago']:,.2f}" if x["pago"] else " — ainda não recebeu")
                        for x in d["sem_nota"]))
    titulo = (f"{len(d['sem_nota'])} PJ sem nota fiscal"
              + (f", {len(d['sem_cnpj'])} sem CNPJ cadastrado" if d["sem_cnpj"] else ""))
    corpo = ("Política em vigor: PJ só recebe apresentando nota fiscal.\n\n"
             + "\n\n".join(partes))
    if d["pago_sem_nota"]:
        corpo += (f"\n\nJá saíram R$ {d['pago_sem_nota']:,.2f} sem a nota correspondente. "
                  f"Pagamento recorrente a PJ sem nota — e no CPF em vez do CNPJ — é o que a "
                  f"fiscalização reclassifica como vínculo, com INSS, FGTS e verbas retroativos.")
    return titulo, corpo


register(Regra(
    nome="pj_sem_nota_fiscal", familia="financeiro", severidade="atencao",
    roles_destino=("admin",),  # LGPD: financeiro SÓ diretoria
    action_url="/redesign/financeiro?t=g-pagar",
    detectar=_detectar_pj_sem_nota, template=_tpl_pj_sem_nota,
))


# ═══════════════════════ COMERCIAL — o funil que para sozinho ═══════════════════════
# Medido em 27/08/2026, quando o Jordan perguntou o que faltava para o Bartolo ser
# assessor comercial e não só ferramenta:
#
#     propostas em RASCUNHO, nunca enviadas   22 · R$ 431.880 · média 46 dias
#     propostas ENVIADAS sem resposta         10 · R$ 370.600 · média 64 dias
#     leads NOVOS sem contato                 37 ·              média 39 dias (máx 74)
#     deals empilhados em "proposta"          46 · R$ 596.881 · parados há 24 dias
#
# R$ 802.480 dormindo. O CRM já sabia disso — 26 leituras respondiam a pergunta. O que
# faltava é que NINGUÉM PERGUNTA "tem proposta parada?" no dia em que está sufocado.
# Por isso o lugar disto é o proativo (que procura o Jordan às 07:00) e não mais uma tool.
#
# ⚠️ CORTES: são de PACIÊNCIA COMERCIAL, não de estatística, e por isso ficam explícitos.
# 7 dias para rascunho porque proposta que o vendedor abriu e não mandou em uma semana ele
# esqueceu. 10 para enviada sem resposta porque abaixo disso é o cliente pensando, acima é
# você deixando morrer. 5 para lead novo porque lead esfria rápido e o mais velho aqui tem
# 74 dias. Se virarem sino que toca todo dia, o número está errado — não a regra.

# ⚠️ `- cast(:d AS integer)` e não `- :d`: bind sem tipo faz o Postgres ver
# "date <= integer" e recusar. Mesma família do `::` que mordeu 3x hoje.
_DIAS_RASCUNHO = 7
_DIAS_SEM_RESPOSTA = 10
_DIAS_LEAD_FRIO = 5

#: Quem cuida de venda.
#: ⚠️ `admin` está aqui porque o Jordan é o comercial desta casa — mas admin nesta casa
#: são CINCO contas, incluindo uma desativada e um robô. Medido em 27/08/2026: estas três
#: regras geraram 390 notificações e UMA foi lida. O conserto de fundo está em
#: `entrega.resolver_usuarios_por_roles` (contas de serviço fora), porque toda regra passa
#: por lá. Se o volume continuar alto, o próximo passo é agrupar por CLIENTE em vez de uma
#: notificação por proposta — 20 propostas do mesmo cliente são UM assunto.
_ROLES_COMERCIAL = ("admin", "gerente_comercial", "comercial")


async def _detectar_proposta_parada(db: AsyncSession) -> list[Achado]:
    # UMA linha por PROPOSTA, não um resumo: o digest lista títulos, e "22 propostas
    # paradas" não diz QUAL abrir. O correlation_id carrega o número para o achado
    # sobreviver ao dia sem duplicar.
    rows = (await db.execute(text(
        "SELECT id::text AS id, number, coalesce(client_name, 'sem cliente') AS cliente, "
        "       coalesce(total, 0) AS total, "
        "       ((now() AT TIME ZONE 'America/Manaus')::date - created_at::date) AS dias "
        "FROM proposals "
        "WHERE status::text = 'draft' "
        "  AND created_at::date <= (now() AT TIME ZONE 'America/Manaus')::date - cast(:d AS integer) "
        "ORDER BY total DESC NULLS LAST"), {"d": _DIAS_RASCUNHO})).mappings().all()
    return [Achado(
        correlation_id=f"proposta_rascunho:{r['number'] or r['id']}",
        dados={"proposta_id": r["id"], "numero": r["number"], "cliente": r["cliente"],
               "total": float(r["total"] or 0), "dias": int(r["dias"]),
               # Dinheiro parado há mais de um mês deixa de ser lembrete e vira alerta.
               "severidade": "critico" if int(r["dias"]) >= 30 else "atencao"},
    ) for r in rows]


def _tpl_proposta_parada(d: dict) -> tuple[str, str]:
    return (
        f"Proposta {d['numero']} parada em rascunho há {d['dias']} dias",
        f"A proposta {d['numero']} para {d['cliente']} "
        f"({_brl_regra(d['total'])}) está em RASCUNHO há {d['dias']} dia(s) e nunca foi "
        f"enviada. Enviar ou arquivar — parada ela não vira nada.",
    )


async def _detectar_proposta_sem_resposta(db: AsyncSession) -> list[Achado]:
    rows = (await db.execute(text(
        "SELECT id::text AS id, number, coalesce(client_name, 'sem cliente') AS cliente, "
        "       coalesce(total, 0) AS total, "
        "       ((now() AT TIME ZONE 'America/Manaus')::date - created_at::date) AS dias "
        "FROM proposals "
        "WHERE status::text = 'sent' "
        "  AND created_at::date <= (now() AT TIME ZONE 'America/Manaus')::date - cast(:d AS integer) "
        "ORDER BY total DESC NULLS LAST"), {"d": _DIAS_SEM_RESPOSTA})).mappings().all()
    return [Achado(
        correlation_id=f"proposta_sem_resposta:{r['number'] or r['id']}",
        dados={"proposta_id": r["id"], "numero": r["number"], "cliente": r["cliente"],
               "total": float(r["total"] or 0), "dias": int(r["dias"]),
               "severidade": "critico" if int(r["dias"]) >= 45 else "atencao"},
    ) for r in rows]


def _tpl_proposta_sem_resposta(d: dict) -> tuple[str, str]:
    return (
        f"Proposta {d['numero']} sem resposta há {d['dias']} dias",
        f"{d['cliente']} recebeu a proposta {d['numero']} "
        f"({_brl_regra(d['total'])}) há {d['dias']} dia(s) e não respondeu. "
        f"Fazer follow-up ou marcar como perdida — silêncio não é resposta.",
    )


async def _detectar_lead_sem_contato(db: AsyncSession) -> list[Achado]:
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(name, 'sem nome') AS nome, "
        "       coalesce(company, '') AS empresa, "
        "       ((now() AT TIME ZONE 'America/Manaus')::date - created_at::date) AS dias "
        "FROM leads "
        "WHERE status::text = 'new' "
        "  AND created_at::date <= (now() AT TIME ZONE 'America/Manaus')::date - cast(:d AS integer) "
        "ORDER BY created_at"), {"d": _DIAS_LEAD_FRIO})).mappings().all()
    return [Achado(
        correlation_id=f"lead_sem_contato:{r['id']}",
        dados={"lead_id": r["id"], "nome": r["nome"], "empresa": r["empresa"],
               "dias": int(r["dias"]),
               "severidade": "critico" if int(r["dias"]) >= 30 else "atencao"},
    ) for r in rows]


def _tpl_lead_sem_contato(d: dict) -> tuple[str, str]:
    quem = f"{d['nome']}" + (f" ({d['empresa']})" if d["empresa"] else "")
    return (
        f"Lead sem contato há {d['dias']} dias: {d['nome']}",
        f"O lead {quem} entrou há {d['dias']} dia(s) e continua como NOVO — ninguém "
        f"falou com ele. Contatar ou descartar.",
    )


def _brl_regra(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


register(Regra(
    nome="proposta_parada_rascunho", familia="comercial", severidade="atencao",
    roles_destino=_ROLES_COMERCIAL,
    action_url="/modulos/comercial/propostas",
    detectar=_detectar_proposta_parada, template=_tpl_proposta_parada,
))

register(Regra(
    nome="proposta_sem_resposta", familia="comercial", severidade="atencao",
    roles_destino=_ROLES_COMERCIAL,
    action_url="/modulos/comercial/propostas",
    detectar=_detectar_proposta_sem_resposta, template=_tpl_proposta_sem_resposta,
))

register(Regra(
    nome="lead_sem_contato", familia="comercial", severidade="atencao",
    roles_destino=_ROLES_COMERCIAL,
    action_url="/modulos/comercial/leads",
    detectar=_detectar_lead_sem_contato, template=_tpl_lead_sem_contato,
))
