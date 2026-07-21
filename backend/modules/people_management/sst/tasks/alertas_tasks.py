"""Alertas SST no sistema de notificações INTERNO (sino do Conecta PRO).

Task Celery `sst.alertas_diarios` (beat diário 08:00 America/Manaus) — gera
notificações internas para os usuários ADMIN via notification_queue
(channel_type='push'), o MESMO caminho que o sino do frontend lê em
GET /api/v1/notifications/push. NADA de Telegram.

Alertas (todos por FATO no banco — nunca fabricados):
1. ASOs vencendo em 30 dias (agrupado: "X ASOs vencem em 30d") — diário
2. ASOs JÁ vencidas — resumo SEMANAL (só segunda-feira; anti-spam)
3. CATs com esocial_status em nao_transmitida/erro há mais de 4h
   (prazo legal S-2210 = 1 dia útil!) — diário
4. Fichas de EPI pendentes de assinatura há 7+ dias — diário
5. ESTEIRA PCMSO PREVENTIVA: funcionários com ASO vencendo em ≤45 dias e SEM
   agendamento futuro em gp_asos (agrupado) — diário

Dedupe: por correlation_id (chave estável por tipo de alerta). Se já existe
notificação NÃO-LIDA igual (mesmo título/corpo) para o usuário, não recria;
se os números mudaram, ATUALIZA a existente em vez de empilhar outra.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from uuid import UUID, uuid4

from celery_app import app

logger = logging.getLogger(__name__)

# Mesmo tenant do fallback de get_tenant_id do controller de notificações
# (users não tem coluna tenant_id — o sino sempre consulta este tenant)
_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


def _upsert_notificacao(db, user_id, correlation_id: str, titulo: str, corpo: str,
                        action_url: str | None, prioridade) -> str:
    """Cria (ou atualiza) UMA notificação interna não-lida por chave/usuário.

    Retorna: 'criada' | 'atualizada' | 'igual' (dedupe — nada feito).
    """
    from modules.notifications.models import NotificationQueue, QueueStatus

    content_data = {"action_url": action_url, "custom_data": {"origem": "sst.alertas_diarios"}}

    # Busca a linha ÚNICA por (tenant,user,correlation) — SEM filtrar opened.
    # O índice único uq_notification_correlation (tenant_id,correlation_id,user_id)
    # garante no máx. 1 linha; filtrar opened=False fazia o db.add abaixo colidir
    # quando o admin já tinha LIDO o alerta (regressão da Fase 0 — auditoria 2026-07-21).
    existente = (
        db.query(NotificationQueue)
        .filter(
            NotificationQueue.tenant_id == _TENANT_ID,
            NotificationQueue.user_id == user_id,
            NotificationQueue.channel_type == "push",
            NotificationQueue.correlation_id == correlation_id,
        )
        .order_by(NotificationQueue.created_at.desc())
        .first()
    )
    if existente is not None:
        if existente.opened is False and existente.subject == titulo and existente.body == corpo:
            return "igual"  # não-lida idêntica → anti-spam
        # Atualiza (e RE-ALERTA: volta para não-lida) — nunca insere duplicata.
        existente.subject = titulo
        existente.body = corpo
        existente.content_data = content_data
        existente.created_at = datetime.utcnow()
        existente.opened = False
        return "atualizada"

    db.add(
        NotificationQueue(
            tenant_id=_TENANT_ID,
            notification_id=f"sst-{uuid4().hex[:20]}",
            correlation_id=correlation_id,
            user_id=user_id,
            recipient_type="user",
            recipient_address="push",
            channel_type="push",
            subject=titulo,
            body=corpo,
            content_data=content_data,
            # DELIVERED: notificação interna do sino — nenhum worker de envio
            # deve tentar despachá-la para dispositivo/e-mail
            status=QueueStatus.DELIVERED,
            priority=prioridade,
            trigger_type="scheduled",
            category="sst",
            opened=False,
        )
    )
    return "criada"


def _coletar_alertas(db, incluir_semanais: bool) -> list[dict]:
    """Consulta os FATOS no banco e monta a lista de alertas (sem criar nada)."""
    from sqlalchemy import text

    from modules.notifications.models import QueuePriority

    alertas: list[dict] = []

    # 1. ASOs vencendo nos próximos 30 dias (agrupado) — diário
    vencendo = db.execute(
        text(
            "SELECT count(*) AS regs, count(DISTINCT employee_id) AS funcs "
            "FROM gp_asos WHERE data_validade IS NOT NULL "
            "AND data_validade >= CURRENT_DATE "
            "AND data_validade <= CURRENT_DATE + INTERVAL '30 days'"
        )
    ).mappings().first()
    if vencendo and vencendo["regs"]:
        alertas.append(
            {
                "chave": "sst:asos_vencendo_30d",
                "titulo": f"SST: {vencendo['regs']} ASO(s) vencem em 30 dias",
                "corpo": (
                    f"{vencendo['regs']} ASO(s) de {vencendo['funcs']} funcionário(s) vencem nos "
                    "próximos 30 dias. Agende os exames periódicos (NR-7) para manter o PCMSO em dia."
                ),
                "action_url": "/modulos/gestao-pessoas/saude-ocupacional/exames",
                "prioridade": QueuePriority.NORMAL,
            }
        )

    # 2. ASOs JÁ vencidas — resumo SEMANAL (segunda-feira), anti-spam
    if incluir_semanais:
        vencidas = db.execute(
            text(
                "SELECT count(*) AS regs, count(DISTINCT employee_id) AS funcs "
                "FROM gp_asos WHERE data_validade IS NOT NULL AND data_validade < CURRENT_DATE"
            )
        ).mappings().first()
        if vencidas and vencidas["regs"]:
            alertas.append(
                {
                    "chave": "sst:asos_vencidas_semanal",
                    "titulo": f"SST (semanal): {vencidas['regs']} ASO(s) vencida(s)",
                    "corpo": (
                        f"Resumo semanal: {vencidas['regs']} registro(s) de ASO vencido(s), "
                        f"{vencidas['funcs']} funcionário(s) afetado(s). Use o plano de "
                        "regularização para agendar em lote."
                    ),
                    "action_url": "/modulos/gestao-pessoas/saude-ocupacional/compliance-nr1",
                    "prioridade": QueuePriority.NORMAL,
                }
            )

    # 3. CATs não transmitidas/erro no eSocial há mais de 4h — prazo legal 1 dia útil
    cats = db.execute(
        text(
            "SELECT count(*) AS n, min(created_at) AS mais_antiga FROM gp_cats "
            "WHERE esocial_status IN ('nao_transmitida', 'erro') "
            "AND created_at < now() - INTERVAL '4 hours'"
        )
    ).mappings().first()
    if cats and cats["n"]:
        alertas.append(
            {
                "chave": "sst:cats_esocial_pendentes",
                "titulo": f"URGENTE SST: {cats['n']} CAT(s) sem transmissão ao eSocial",
                "corpo": (
                    f"{cats['n']} CAT(s) com eSocial em 'nao_transmitida'/'erro' há mais de 4h "
                    f"(mais antiga: {cats['mais_antiga']:%d/%m/%Y %H:%M}). PRAZO LEGAL do "
                    "S-2210 é 1 DIA ÚTIL após o acidente — transmita agora."
                ),
                "action_url": "/modulos/gestao-pessoas/saude-ocupacional",
                "prioridade": QueuePriority.CRITICAL,
            }
        )

    # 4. Fichas de EPI pendentes de assinatura há 7+ dias
    fichas = db.execute(
        text(
            "SELECT count(*) AS n FROM sst_fichas_epi "
            "WHERE status = 'pendente_assinatura' "
            "AND created_at < now() - INTERVAL '7 days'"
        )
    ).mappings().first()
    if fichas and fichas["n"]:
        alertas.append(
            {
                "chave": "sst:fichas_epi_pendentes_7d",
                "titulo": f"SST: {fichas['n']} ficha(s) de EPI sem assinatura há 7+ dias",
                "corpo": (
                    f"{fichas['n']} ficha(s) de EPI aguardam assinatura do funcionário há mais "
                    "de 7 dias (NR-6). Cobre a assinatura digital pelo Portal do Funcionário."
                ),
                "action_url": "/modulos/gestao-pessoas/saude-ocupacional/epis",
                "prioridade": QueuePriority.HIGH,
            }
        )

    # 5. ESTEIRA PCMSO PREVENTIVA: funcionários ATIVOS cujo último ASO vence em
    #    ≤45 dias e que NÃO têm nenhum agendamento futuro em gp_asos — o alvo é
    #    agendar ANTES de vencer ("nunca mais 88 ASOs vencidos"). Fato no banco:
    #    último data_validade por funcionário + ausência de status='agendado' futuro.
    preventivo = db.execute(
        text(
            """
            WITH ultimo AS (
                SELECT DISTINCT ON (a.employee_id) a.employee_id, a.data_validade
                FROM gp_asos a
                WHERE a.data_validade IS NOT NULL
                ORDER BY a.employee_id, a.data_validade DESC
            )
            SELECT count(*) AS funcs, min(u.data_validade) AS primeiro_vencimento
            FROM ultimo u
            JOIN employees e ON e.id = u.employee_id AND e.status = 'ativo'
            WHERE u.data_validade >= CURRENT_DATE
              AND u.data_validade <= CURRENT_DATE + INTERVAL '45 days'
              AND NOT EXISTS (
                  SELECT 1 FROM gp_asos g
                  WHERE g.employee_id = u.employee_id
                    AND g.status = 'agendado'
                    AND g.data_agendamento >= CURRENT_DATE
              )
            """
        )
    ).mappings().first()
    if preventivo and preventivo["funcs"]:
        alertas.append(
            {
                "chave": "sst:esteira_pcmso_45d_sem_agendamento",
                "titulo": (
                    f"PCMSO preventivo: {preventivo['funcs']} funcionário(s) "
                    "precisam agendar exame periódico (45d)"
                ),
                "corpo": (
                    f"{preventivo['funcs']} funcionário(s) ativo(s) têm ASO vencendo em até "
                    f"45 dias (primeiro vencimento: {preventivo['primeiro_vencimento']:%d/%m/%Y}) "
                    "e NENHUM exame agendado. Agende pela Esteira Preventiva antes de vencer "
                    "(NR-7 — exame periódico anual)."
                ),
                "action_url": "/modulos/gestao-pessoas/saude-ocupacional/exames",
                "prioridade": QueuePriority.HIGH,
            }
        )

    # 6. Calendário Legal SST — PCMSO/LTCAT/CAs de EPI/treinamentos NR ≤30d
    alertas.extend(_alertas_calendario_legal(db))

    return alertas


def _alertas_calendario_legal(db) -> list[dict]:
    """Itens LEGAIS do calendário SST vencidos ou vencendo em ≤30 dias.

    Cobre o que os alertas existentes NÃO cobrem: PCMSO (vigência), LTCAT
    (validade), CAs dos EPIs do CATÁLOGO (health_epi_catalog.ca_validade) e
    treinamentos NR (sst_treinamentos). ASOs e fichas de EPI já têm alertas
    próprios — não duplicar. Fatos do banco, nunca fabricados. Dedupe padrão
    via chave estável (correlation_id) como os demais alertas.
    """
    from sqlalchemy import text

    from modules.notifications.models import QueuePriority

    try:
        row = db.execute(
            text(
                "SELECT "
                "(SELECT count(*) FROM sst_pcmso WHERE vigencia_fim <= CURRENT_DATE + 30) AS pcmso, "
                "(SELECT count(*) FROM sst_pcmso WHERE vigencia_fim < CURRENT_DATE) AS pcmso_venc, "
                "(SELECT count(*) FROM sst_ltcat WHERE validade_fim IS NOT NULL "
                "   AND validade_fim <= CURRENT_DATE + 30) AS ltcat, "
                "(SELECT count(*) FROM sst_ltcat WHERE validade_fim IS NOT NULL "
                "   AND validade_fim < CURRENT_DATE) AS ltcat_venc, "
                "(SELECT count(*) FROM health_epi_catalog WHERE ativo = true "
                "   AND ca_validade IS NOT NULL AND ca_validade <= CURRENT_DATE + 30) AS cas, "
                "(SELECT count(*) FROM health_epi_catalog WHERE ativo = true "
                "   AND ca_validade IS NOT NULL AND ca_validade < CURRENT_DATE) AS cas_venc, "
                "(SELECT count(*) FROM sst_treinamentos "
                "   WHERE vencimento <= CURRENT_DATE + 30) AS trein, "
                "(SELECT count(*) FROM sst_treinamentos "
                "   WHERE vencimento < CURRENT_DATE) AS trein_venc"
            )
        ).mappings().first()
    except Exception as exc:
        logger.error("_alertas_calendario_legal: falha ao consultar o banco: %s", exc)
        return []

    if not row:
        return []

    partes: list[str] = []
    tem_vencido = False
    if row["pcmso"]:
        partes.append(f"{row['pcmso']} PCMSO")
        tem_vencido = tem_vencido or bool(row["pcmso_venc"])
    if row["ltcat"]:
        partes.append(f"{row['ltcat']} LTCAT")
        tem_vencido = tem_vencido or bool(row["ltcat_venc"])
    if row["cas"]:
        partes.append(f"{row['cas']} CA(s) de EPI do catálogo")
        tem_vencido = tem_vencido or bool(row["cas_venc"])
    if row["trein"]:
        partes.append(f"{row['trein']} treinamento(s) NR")
        tem_vencido = tem_vencido or bool(row["trein_venc"])

    if not partes:
        return []

    total = (row["pcmso"] or 0) + (row["ltcat"] or 0) + (row["cas"] or 0) + (row["trein"] or 0)
    return [
        {
            "chave": "sst:calendario_legal_30d",
            "titulo": f"SST: {total} item(ns) do Calendário Legal vencendo em 30 dias",
            "corpo": (
                "Itens legais SST vencidos ou vencendo em 30 dias: "
                + "; ".join(partes)
                + ". Veja o Calendário Legal para a lista completa com ações sugeridas."
            ),
            "action_url": "/modulos/gestao-pessoas/saude-ocupacional/calendario-legal",
            "prioridade": QueuePriority.CRITICAL if tem_vencido else QueuePriority.HIGH,
        }
    ]


# user_id da Márcia (MB Consultoria — perfil SST). Notificação vai para o sino
# INTERNO dela pelo MESMO caminho dos alertas admin (notification_queue push).
_MARCIA_USER_ID = UUID("d4e309e9-026c-4c81-94a9-8c2ba9e4f80e")


def _coletar_regularizacao(db) -> dict:
    """Fatos do banco para a notificação de regularização (nunca fabricados).

    Retorna contagens reais + os 2 descalços mais antigos (para a prioridade).
    """
    from sqlalchemy import text

    descalcos = db.execute(
        text(
            """
            SELECT e.nome, (CURRENT_DATE - e.data_admissao) AS dias
            FROM employees e
            WHERE e.status = 'ativo'
              AND e.data_admissao IS NOT NULL
              AND e.data_admissao >= DATE '2026-01-01'
              AND NOT EXISTS (
                  SELECT 1 FROM gp_asos a
                  WHERE a.employee_id = e.id AND a.status = 'realizado'
                    AND (a.data_validade IS NULL OR a.data_validade >= CURRENT_DATE)
              )
            ORDER BY e.data_admissao ASC, e.nome
            """
        )
    ).mappings().all()

    vencidos = db.execute(
        text(
            """
            WITH ultimo AS (
                SELECT DISTINCT ON (a.employee_id) a.employee_id, a.data_validade
                FROM gp_asos a WHERE a.data_validade IS NOT NULL
                ORDER BY a.employee_id, a.data_validade DESC
            )
            SELECT count(*) AS n
            FROM ultimo u JOIN employees e ON e.id = u.employee_id AND e.status = 'ativo'
            WHERE u.data_validade < CURRENT_DATE
            """
        )
    ).scalar() or 0

    return {"descalcos": [dict(r) for r in descalcos], "aso_vencidos": int(vencidos)}


@app.task(name="sst.notificar_regularizacao_marcia")
def notificar_regularizacao_marcia() -> str:
    """Notifica a Márcia (SST) sobre os funcionários a regularizar (descalços).

    UMA notificação interna no sino dela, com dedupe por correlation_id
    (atualiza se os números mudarem, nunca empilha). À prova de falha: qualquer
    erro é logado e a task retorna a mensagem, sem derrubar o beat.
    """
    from core.database.session import get_sync_db
    from modules.notifications.models import QueuePriority

    try:
        with get_sync_db() as db:
            fatos = _coletar_regularizacao(db)
            descalcos = fatos["descalcos"]
            n = len(descalcos)
            if n == 0:
                logger.info("sst.notificar_regularizacao_marcia: 0 descalços — nada a notificar")
                return "0 descalços — nenhuma notificação criada"

            top = descalcos[:2]
            prioridade = " e ".join(
                f"{d['nome'].split()[0].title()} (adm. jan, {d['dias']}d)"
                if d["dias"] and d["dias"] > 150
                else f"{d['nome'].split()[0].title()} ({d['dias']}d)"
                for d in top
            )
            titulo = f"SST: {n} funcionários a regularizar (ASO/EPI/treinamento)"
            corpo = (
                f"A auditoria SST apontou {n} funcionário(s) ativo(s) sem ASO admissional, "
                f"sem entrega de EPI assinada e sem treinamento NR — os \"descalços\" da onda "
                f"de admissões 2026. Prioridade: {prioridade}. Também há "
                f"{fatos['aso_vencidos']} ASO(s) vencido(s) para renovação. Abra o Painel de "
                f"Regularização para carregar ASO retroativo, gerar ficha de EPI e registrar os "
                f"treinamentos — a barra avança conforme você executa."
            )
            resultado = _upsert_notificacao(
                db,
                user_id=_MARCIA_USER_ID,
                correlation_id="sst:regularizacao_descalcos",
                titulo=titulo,
                corpo=corpo,
                action_url="/modulos/gestao-pessoas/saude-ocupacional/regularizacao",
                prioridade=QueuePriority.HIGH,
            )
            db.commit()
            resumo = f"Notificação '{resultado}' para a Márcia ({n} descalços)"
            logger.info("sst.notificar_regularizacao_marcia: %s", resumo)
            return resumo
    except Exception as exc:
        logger.error("Erro em sst.notificar_regularizacao_marcia: %s", exc)
        return f"Erro: {exc}"


@app.task(name="sst.alertas_diarios")
def alertas_diarios(forcar_semanais: bool = False) -> str:
    """Gera os alertas SST do dia no sino interno dos usuários ADMIN.

    forcar_semanais=True inclui o resumo semanal de ASOs vencidas mesmo fora
    de segunda-feira (para teste manual/prova).
    """
    from sqlalchemy import text

    from core.database.session import get_sync_db

    incluir_semanais = forcar_semanais or date.today().weekday() == 0  # segunda-feira

    try:
        with get_sync_db() as db:
            admins = db.execute(
                text("SELECT id, email FROM users WHERE role = 'admin' AND is_active = true")
            ).mappings().all()
            if not admins:
                return "Nenhum usuário admin ativo — nada a notificar"

            alertas = _coletar_alertas(db, incluir_semanais)
            if not alertas:
                logger.info("sst.alertas_diarios: nenhum alerta hoje (banco sem pendências)")
                return "0 alertas (sem pendências SST no banco)"

            criadas = atualizadas = iguais = 0
            for alerta in alertas:
                for adm in admins:
                    resultado = _upsert_notificacao(
                        db,
                        user_id=adm["id"],
                        correlation_id=alerta["chave"],
                        titulo=alerta["titulo"],
                        corpo=alerta["corpo"],
                        action_url=alerta["action_url"],
                        prioridade=alerta["prioridade"],
                    )
                    if resultado == "criada":
                        criadas += 1
                    elif resultado == "atualizada":
                        atualizadas += 1
                    else:
                        iguais += 1
            db.commit()

            resumo = (
                f"{len(alertas)} alerta(s) SST × {len(admins)} admin(s): "
                f"{criadas} criada(s), {atualizadas} atualizada(s), {iguais} dedupe (não-lidas iguais)"
            )
            logger.info("sst.alertas_diarios concluído: %s", resumo)
            return resumo

    except Exception as exc:
        logger.error("Erro em sst.alertas_diarios: %s", exc)
        return f"Erro: {exc}"
