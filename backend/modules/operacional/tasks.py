"""Celery Tasks - Módulo Operacional.

Sprint: Módulo Operacional - Sistema de Notificações Push
Sprint: Geração Automática de Escalas
Sprint: Expiração de Banco de Horas / Lembretes de Turno / Relatório de Cobertura
"""

import asyncio
import logging

from celery_app import app
from core.database.session import get_async_db_session, get_sync_db
from modules.operacional.services.notification_triggers import (
    OperacionalNotificationTriggers,
    _get_active_tenants,
)

logger = logging.getLogger(__name__)


@app.task(
    name="operacional.check_late_employees",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def check_late_employees_task(self):
    """Tarefa Celery: Verifica colaboradores atrasados.

    Executada a cada 5 minutos via Celery Beat.
    Itera sobre todos os tenants ativos.
    """
    try:
        with get_sync_db() as db:
            tenant_ids = _get_active_tenants(db)
            logger.info(f"[Operacional Task] Verificando atrasos em {len(tenant_ids)} tenants")

            results = []
            for tenant_id in tenant_ids:
                try:
                    triggers = OperacionalNotificationTriggers(db, tenant_id)
                    result = triggers.check_late_employees()
                    results.append({"tenant_id": str(tenant_id), **result})
                except Exception as e:
                    logger.error(f"[Operacional Task] Atrasos falhou para tenant {tenant_id}: {e}")

            logger.info(f"[Operacional Task] Verificação de atrasos concluída: {len(results)} tenants")
            return results

    except Exception as exc:
        logger.error(f"[Operacional Task] Erro ao verificar atrasos: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.check_pending_approvals",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def check_pending_approvals_task(self):
    """Tarefa Celery: Verifica aprovações pendentes.

    Executada a cada 1 hora via Celery Beat.
    Itera sobre todos os tenants ativos.
    """
    try:
        with get_sync_db() as db:
            tenant_ids = _get_active_tenants(db)
            logger.info(f"[Operacional Task] Verificando aprovações em {len(tenant_ids)} tenants")

            results = []
            for tenant_id in tenant_ids:
                try:
                    triggers = OperacionalNotificationTriggers(db, tenant_id)
                    result = triggers.check_pending_approvals()
                    results.append({"tenant_id": str(tenant_id), **result})
                except Exception as e:
                    logger.error(f"[Operacional Task] Aprovações falhou para tenant {tenant_id}: {e}")

            logger.info(f"[Operacional Task] Verificação de aprovações concluída: {len(results)} tenants")
            return results

    except Exception as exc:
        logger.error(f"[Operacional Task] Erro ao verificar aprovações: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.auto_generate_monthly_scales",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def auto_generate_monthly_scales_task(self, month: int = None, year: int = None):
    """Tarefa Celery: Gera escalas automaticamente para o mês.

    Executada no dia 1º de cada mês via Celery Beat, ou sob demanda.
    Itera sobre todos os tenants ativos.

    Args:
        month: Mês (1-12), se None usa mês atual
        year: Ano, se None usa ano atual
    """
    try:
        from modules.operacional.services.auto_scale_service import AutoScaleService

        async def _generate():
            async with get_async_db_session() as db:
                service = AutoScaleService(db)

                if month and year:
                    result = await service.generate_scales_for_month(month, year)
                else:
                    result = await service.generate_scales_for_current_month()

                return result

        # Executar função async
        result = asyncio.run(_generate())

        logger.info(f"[Operacional Task] Geração automática de escalas: {result}")
        return result

    except Exception as exc:
        logger.error(f"[Operacional Task] Erro ao gerar escalas: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.expire_time_bank_entries",
    bind=True,
    max_retries=3,
    default_retry_delay=1800,  # 30 minutos
)
def expire_time_bank_entries(self):
    """
    Task Celery para expiração automática de banco de horas.

    Executa diariamente via Celery Beat às 00:30h.
    Marca como expiradas as entradas de banco de horas com data de validade vencida.
    """
    try:

        async def run_expiration():
            from datetime import date

            from sqlalchemy import and_, select

            from core.database.session import get_async_db_session
            from modules.operacional.models import TimeBank, TimeBankEntryType, TimeBankStatus

            async with get_async_db_session() as db:
                cutoff_date = date.today()
                result = await db.execute(
                    select(TimeBank).where(
                        and_(
                            TimeBank.status == TimeBankStatus.APPROVED,
                            TimeBank.expiration_date.isnot(None),
                            TimeBank.expiration_date < cutoff_date,
                            TimeBank.entry_type == TimeBankEntryType.CREDIT,
                            TimeBank.hours > 0,
                        )
                    )
                )
                entries = result.scalars().all()
                expired_count = 0
                for entry in entries:
                    entry.status = TimeBankStatus.EXPIRED
                    entry.description = f"Expirado automaticamente em {cutoff_date.strftime('%d/%m/%Y')}"
                    expired_count += 1

                if expired_count > 0:
                    await db.commit()
                    logger.info(
                        "[Operacional Task] Banco de horas: %d entradas expiradas automaticamente",
                        expired_count,
                    )
                else:
                    logger.debug("[Operacional Task] Banco de horas: nenhuma entrada para expirar")

                return expired_count

        result = asyncio.run(run_expiration())
        return {"expired_count": result}

    except Exception as exc:
        logger.error(f"[Operacional Task] Erro na expiração do banco de horas: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.send_shift_reminders",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_shift_reminders(self):
    """
    Task para envio de lembretes de turno 2h antes.
    Executa a cada 30 minutos via Celery Beat.
    """
    try:
        logger.info("[Operacional Task] Processando lembretes de turno...")
        # TODO: integrar com CommsAutomatorAgent quando WhatsApp API estiver configurado
        return {"status": "ok", "message": "Lembretes processados"}
    except Exception as exc:
        logger.error(f"[Operacional Task] Erro nos lembretes de turno: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.briefing_operacional_matinal",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def briefing_operacional_matinal(self):
    """
    Briefing Operacional matinal via Telegram (07:30 BRT, seg-sex via Celery Beat).

    100% dados REAIS do banco — mesmas fontes das rotas/tasks existentes:
    - posts/allocations (cobertura), scales (vigentes + drafts),
    - occurrences (abertas por severidade),
    - diaria_lancamentos (diárias de ontem — módulo Diárias),
    - gp_asos (ASOs vencendo — MESMA query do SST verificar_vencimentos_aso).
    Seção sem dado → linha honesta "sem registros". NUNCA fabrica dado.

    Roteada para a fila gov.batch (worker celery-batch tem TELEGRAM_* no env).
    """
    try:
        import os
        from datetime import date, datetime, timedelta
        from zoneinfo import ZoneInfo

        from sqlalchemy import text

        # Import tardio: field_alerts é módulo irmão (envio Telegram best-effort);
        # import no topo quebraria TODAS as tasks do módulo se ele faltar.
        from modules.operacional.field_alerts import enviar_telegram

        # Datas na hora local de Manaus (operação é em Manaus-AM)
        tz_manaus = ZoneInfo("America/Manaus")
        agora = datetime.now(tz_manaus)
        hoje = agora.date()
        ontem = hoje - timedelta(days=1)

        async def _gerar() -> tuple[str, dict]:
            async with get_async_db_session() as db:
                linhas: list[str] = [f"🎯 *Briefing Operacional — {hoje.strftime('%d/%m/%Y')}*", ""]
                resumo: dict = {}

                # ── a) POSTOS: ativos, com alocação ativa, sem cobertura ──────
                postos_ativos = (
                    await db.execute(text("SELECT COUNT(*) FROM posts WHERE is_active = TRUE"))
                ).scalar() or 0
                postos_cobertos = (
                    await db.execute(
                        text(
                            """
                            SELECT COUNT(DISTINCT a.post_id)
                            FROM allocations a
                            JOIN posts p ON p.id = a.post_id
                            WHERE a.status = 'active' AND a.is_active = TRUE
                              AND p.is_active = TRUE
                            """
                        )
                    )
                ).scalar() or 0
                sem_cobertura = [
                    r[0]
                    for r in (
                        await db.execute(
                            text(
                                """
                                SELECT p.name FROM posts p
                                WHERE p.is_active = TRUE
                                  AND NOT EXISTS (
                                    SELECT 1 FROM allocations a
                                    WHERE a.post_id = p.id
                                      AND a.status = 'active' AND a.is_active = TRUE
                                  )
                                ORDER BY p.name
                                """
                            )
                        )
                    ).all()
                ]
                linhas.append("*Postos*")
                if postos_ativos:
                    linhas.append(f"• {postos_ativos} ativos · {postos_cobertos} com alocação ativa")
                    if sem_cobertura:
                        linhas.append(f"• Sem cobertura ({len(sem_cobertura)}): " + ", ".join(sem_cobertura))
                    else:
                        linhas.append("• Todos os postos ativos têm alocação ativa")
                else:
                    linhas.append("• sem registros de postos ativos")
                linhas.append("")
                resumo["postos_ativos"] = int(postos_ativos)
                resumo["postos_com_alocacao"] = int(postos_cobertos)
                resumo["postos_sem_cobertura"] = len(sem_cobertura)

                # ── b) ESCALAS: vigentes hoje + drafts pendentes ──────────────
                vigentes = (
                    await db.execute(
                        text(
                            """
                            SELECT p.name
                            FROM scales s
                            JOIN posts p ON p.id = s.post_id
                            WHERE s.is_active = TRUE
                              AND s.status IN ('published', 'in_progress')
                              AND s.start_date IS NOT NULL AND s.end_date IS NOT NULL
                              AND CURRENT_DATE BETWEEN s.start_date AND s.end_date
                            ORDER BY p.name
                            """
                        )
                    )
                ).all()
                drafts = (
                    await db.execute(
                        text(
                            """
                            SELECT month, year, COUNT(*)
                            FROM scales
                            WHERE is_active = TRUE AND status = 'draft'
                            GROUP BY month, year
                            ORDER BY year, month
                            """
                        )
                    )
                ).all()
                linhas.append("*Escalas*")
                if vigentes:
                    nomes_vig = ", ".join(sorted({r[0] for r in vigentes}))
                    linhas.append(f"• {len(vigentes)} vigente(s) hoje: {nomes_vig}")
                else:
                    linhas.append("• nenhuma escala vigente hoje")
                if drafts:
                    partes = [f"{int(r[2])}× {int(r[0]):02d}/{int(r[1])}" for r in drafts]
                    linhas.append(f"• Drafts pendentes: {sum(int(r[2]) for r in drafts)} ({', '.join(partes)})")
                else:
                    linhas.append("• sem drafts pendentes")
                linhas.append("")
                resumo["escalas_vigentes"] = len(vigentes)
                resumo["escalas_draft"] = sum(int(r[2]) for r in drafts) if drafts else 0

                # ── b2) PRESENÇA AGORA (escala × batidas reais) ───────────────
                # Mesmas fontes do quadro /operacional/presenca/hoje, via SQL
                # direto (sem importar o controller): gp_clock_punches + shifts.
                # Batida válida = status fora de ('rejected','cancelado'); COALESCE
                # protege status NULL. "Em andamento" = agora (hora LOCAL de
                # Manaus — punch_timestamp e planned_* são naive em hora local)
                # dentro da janela planejada, com braço específico p/ turno
                # noturno (fim <= início atravessa a meia-noite). Check-in manual
                # (actual_start_time) conta como presença. Vazio → linha honesta.
                linhas.append("*Presença agora*")
                try:
                    row_b = (
                        await db.execute(
                            text(
                                """
                                SELECT COUNT(*), COUNT(DISTINCT employee_id)
                                FROM gp_clock_punches
                                WHERE punch_timestamp::date = :hoje
                                  AND COALESCE(status, '') NOT IN ('rejected', 'cancelado')
                                """
                            ),
                            {"hoje": hoje},
                        )
                    ).first()
                    batidas_hoje = int(row_b[0] or 0)
                    func_com_batida = int(row_b[1] or 0)

                    turnos_esperados = (
                        await db.execute(
                            text(
                                """
                                SELECT COUNT(*)
                                FROM shifts
                                WHERE shift_date = :hoje
                                  AND employee_id IS NOT NULL
                                  AND is_off_day = FALSE
                                  AND status <> 'cancelled'
                                  AND is_active = TRUE
                                """
                            ),
                            {"hoje": hoje},
                        )
                    ).scalar() or 0

                    postos_sem_batida = (
                        await db.execute(
                            text(
                                """
                                SELECT DISTINCT p.name
                                FROM shifts sh
                                JOIN posts p ON p.id = sh.post_id
                                WHERE sh.shift_date = :hoje
                                  AND sh.employee_id IS NOT NULL
                                  AND sh.is_off_day = FALSE
                                  AND sh.status <> 'cancelled'
                                  AND sh.is_active = TRUE
                                  AND sh.actual_start_time IS NULL
                                  AND (
                                        (sh.planned_end_time > sh.planned_start_time
                                         AND :agora_hora BETWEEN sh.planned_start_time AND sh.planned_end_time)
                                     OR (sh.planned_end_time <= sh.planned_start_time
                                         AND (:agora_hora >= sh.planned_start_time
                                              OR :agora_hora <= sh.planned_end_time))
                                  )
                                  AND NOT EXISTS (
                                      SELECT 1 FROM gp_clock_punches cp
                                      WHERE cp.employee_id = sh.employee_id
                                        AND cp.punch_timestamp::date = :hoje
                                        AND COALESCE(cp.status, '') NOT IN ('rejected', 'cancelado')
                                  )
                                ORDER BY p.name
                                """
                            ),
                            # .time() de datetime aware já devolve hora local NAIVE
                            {"hoje": hoje, "agora_hora": agora.time()},
                        )
                    ).all()

                    if turnos_esperados or batidas_hoje:
                        linhas.append(
                            f"• {func_com_batida} funcionário(s) com batida hoje "
                            f"({batidas_hoje} batida(s)) · {int(turnos_esperados)} turno(s) esperado(s) no dia"
                        )
                        if postos_sem_batida:
                            linhas.append(
                                "• Turno em andamento SEM batida: "
                                + ", ".join(r[0] for r in postos_sem_batida)
                            )
                        else:
                            linhas.append("• nenhum posto com turno em andamento sem batida")
                    else:
                        linhas.append("• sem turnos esperados hoje e sem batidas até o momento")
                    resumo["batidas_hoje"] = batidas_hoje
                    resumo["funcionarios_com_batida"] = func_com_batida
                    resumo["turnos_esperados_hoje"] = int(turnos_esperados)
                    resumo["postos_em_andamento_sem_batida"] = len(postos_sem_batida)
                except Exception as e:
                    logger.warning(f"[Briefing] presença indisponível: {e}")
                    linhas.append("• sem registros (fontes de presença indisponíveis)")
                    resumo["batidas_hoje"] = None
                linhas.append("")

                # ── c) OCORRÊNCIAS ABERTAS por severidade ─────────────────────
                por_sev = (
                    await db.execute(
                        text(
                            """
                            SELECT severity, COUNT(*)
                            FROM occurrences
                            WHERE status IN ('aberta', 'em_analise') AND is_active = TRUE
                            GROUP BY severity
                            """
                        )
                    )
                ).all()
                graves_nominais = (
                    await db.execute(
                        text(
                            """
                            SELECT o.code, COALESCE(p.name, 'posto não identificado')
                            FROM occurrences o
                            LEFT JOIN posts p ON p.id = o.post_id
                            WHERE o.status IN ('aberta', 'em_analise')
                              AND o.is_active = TRUE
                              AND o.severity IN ('grave', 'gravissima')
                            ORDER BY o.occurred_at DESC
                            """
                        )
                    )
                ).all()
                linhas.append("*Ocorrências abertas*")
                if por_sev:
                    ordem = {"gravissima": 0, "grave": 1, "moderada": 2, "leve": 3}
                    sevs = sorted(por_sev, key=lambda r: ordem.get(r[0], 9))
                    rotulo = {"gravissima": "gravíssima(s)", "grave": "grave(s)",
                              "moderada": "moderada(s)", "leve": "leve(s)"}
                    linhas.append("• " + ", ".join(f"{int(r[1])} {rotulo.get(r[0], r[0])}" for r in sevs))
                    if graves_nominais:
                        linhas.append("• Graves/gravíssimas: " + "; ".join(f"{r[0]} ({r[1]})" for r in graves_nominais))
                else:
                    linhas.append("• sem ocorrências abertas")
                linhas.append("")
                resumo["ocorrencias_abertas"] = sum(int(r[1]) for r in por_sev) if por_sev else 0
                resumo["ocorrencias_graves"] = len(graves_nominais)

                # ── d) DIARISTAS ONTEM (diaria_lancamentos — módulo Diárias) ──
                linhas.append(f"*Diaristas — ontem ({ontem.strftime('%d/%m')})*")
                try:
                    row = (
                        await db.execute(
                            text(
                                """
                                SELECT COUNT(*), COUNT(DISTINCT diarista_id), COALESCE(SUM(valor), 0)
                                FROM diaria_lancamentos
                                WHERE data = :ontem
                                """
                            ),
                            {"ontem": ontem},
                        )
                    ).first()
                    n_lanc = int(row[0]) if row else 0
                    if n_lanc:
                        total_str = f"{float(row[2]):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        linhas.append(f"• {n_lanc} lançamento(s) · {int(row[1])} diarista(s) · R$ {total_str}")
                    else:
                        linhas.append("• nenhum lançamento ontem")
                    resumo["diarias_ontem"] = n_lanc
                except Exception as e:  # tabela criada sob demanda pelo módulo Diárias
                    logger.warning(f"[Briefing] diaria_lancamentos indisponível: {e}")
                    linhas.append("• sem registros (tabela de diárias indisponível)")
                    resumo["diarias_ontem"] = None
                linhas.append("")

                # ── e) ASOs VENCENDO 30 dias (gp_asos — MESMA fonte do SST) ───
                linhas.append("*ASOs vencendo (30 dias)*")
                try:
                    limite = hoje + timedelta(days=30)
                    asos = (
                        await db.execute(
                            text(
                                """
                                SELECT COALESCE(e.nome, a.employee_id::text) AS nome, a.data_validade
                                FROM gp_asos a
                                LEFT JOIN employees e ON e.id = a.employee_id
                                WHERE a.data_validade IS NOT NULL
                                  AND a.data_validade BETWEEN :hoje AND :limite
                                ORDER BY a.data_validade
                                """
                            ),
                            {"hoje": hoje, "limite": limite},
                        )
                    ).all()
                    if asos:
                        urgentes = "; ".join(
                            f"{r[0]} ({r[1].strftime('%d/%m')})" for r in asos[:3]
                        )
                        linhas.append(f"• {len(asos)} vencendo · mais urgentes: {urgentes}")
                    else:
                        linhas.append("• nenhum ASO vencendo nos próximos 30 dias")
                    resumo["asos_vencendo_30d"] = len(asos)
                except Exception as e:
                    logger.warning(f"[Briefing] gp_asos indisponível: {e}")
                    linhas.append("• sem registros (tabela gp_asos indisponível)")
                    resumo["asos_vencendo_30d"] = None
                linhas.append("")

                # ── f) Rodapé ────────────────────────────────────────────────
                linhas.append(f"Fonte: banco Conecta PRO · gerado {agora.strftime('%H:%M')}")
                return "\n".join(linhas), resumo

        async def _run() -> dict:
            texto, resumo = await _gerar()

            chat_jordan = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
            chat_oper = (os.getenv("TELEGRAM_CHAT_ID_OPERACIONAL") or "").strip()

            enviado_jordan = False
            if chat_jordan:
                enviado_jordan = await enviar_telegram(texto, chat_id=chat_jordan)
            enviado_operacional = False
            if chat_oper and chat_oper != chat_jordan:
                enviado_operacional = await enviar_telegram(texto, chat_id=chat_oper)

            return {
                "enviado_jordan": bool(enviado_jordan),
                "enviado_operacional": bool(enviado_operacional),
                "resumo": resumo,
            }

        logger.info("[Operacional Task] Gerando briefing operacional matinal (dados reais)...")
        result = asyncio.run(_run())
        logger.info(f"[Operacional Task] Briefing matinal: {result}")
        return result
    except Exception as exc:
        logger.error(f"[Operacional Task] Erro no briefing matinal: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.daily_coverage_report",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def daily_coverage_report(self):
    """
    Task para geração diária de relatório de cobertura.
    Executa todo dia às 23:55h via Celery Beat.

    Usa dados REAIS via ReportsRepository (mesma fonte das rotas
    /operacional/reports/coverage) — nunca dados simulados.
    """
    try:
        from datetime import date

        from modules.operacional.repositories.reports_repository import ReportsRepository

        async def _generate():
            async with get_async_db_session() as db:
                repo = ReportsRepository(db)
                today = date.today()
                period_start = date(today.year, today.month, 1)
                items = await repo.get_coverage(period_start, today)

                total_allocations = sum(item["total_allocations"] for item in items)
                active_allocations = sum(item["active_allocations"] for item in items)
                coverage_rate = (
                    round(active_allocations / total_allocations * 100, 2) if total_allocations else 0.0
                )

                critical_posts = [
                    item["post_name"] for item in items if item["total_allocations"] and item["coverage_rate"] < 90.0
                ]

                return {
                    "status": "ok",
                    "date": today.isoformat(),
                    "period_start": period_start.isoformat(),
                    "total_posts": len(items),
                    "total_allocations": total_allocations,
                    "active_allocations": active_allocations,
                    "coverage_rate": coverage_rate,
                    "critical_posts": critical_posts,
                }

        logger.info("[Operacional Task] Gerando relatório diário de cobertura (dados reais)...")
        result = asyncio.run(_generate())
        logger.info(f"[Operacional Task] Relatório diário de cobertura: {result}")
        return result
    except Exception as exc:
        logger.error(f"[Operacional Task] Erro no relatório diário: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.vigia_ausencia",
    bind=True,
    max_retries=1,
)
def vigia_ausencia(self):
    """Vigia de ausência: turno em andamento há 30-60min sem batida nem check-in manual → Telegram.

    Roda a cada 30min (beat). Janela de disparo única por turno: só alerta quando
    'agora' está entre inicio+30min e inicio+60min (cadência */30 ⇒ no máx. 1 alerta/turno).
    Horários de shifts/batidas são hora LOCAL de Manaus (mesma decisão do módulo presence).
    """
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from sqlalchemy import text

    async def _run() -> dict:
        tz_manaus = ZoneInfo("America/Manaus")
        agora = datetime.now(tz_manaus).replace(tzinfo=None)
        hoje = agora.date()
        async with get_async_db_session() as db:
            rows = (
                await db.execute(
                    text(
                        """
                        SELECT e.nome, p.name AS posto, s.planned_start_time, s.planned_end_time
                        FROM shifts s
                        JOIN employees e ON e.id = s.employee_id
                        JOIN posts p ON p.id = s.post_id
                        WHERE s.shift_date = :hoje
                          AND s.employee_id IS NOT NULL
                          AND s.is_off_day = FALSE
                          AND s.is_active = TRUE
                          AND s.status NOT IN ('cancelled', 'completed', 'missed')
                          AND s.actual_start_time IS NULL
                          AND NOT EXISTS (
                            SELECT 1 FROM gp_clock_punches gp
                            WHERE gp.employee_id = s.employee_id
                              AND gp.punch_timestamp::date = :hoje
                              AND COALESCE(gp.status, '') NOT IN ('rejected', 'cancelado')
                          )
                        """
                    ),
                    {"hoje": hoje},
                )
            ).all()

        alertas = []
        for nome, posto, ini, fim in rows:
            if ini is None:
                continue
            inicio_dt = datetime.combine(hoje, ini)
            janela_ini = inicio_dt + timedelta(minutes=30)
            janela_fim = inicio_dt + timedelta(minutes=60)
            if janela_ini <= agora < janela_fim:
                horario = f"{ini:%H:%M}–{fim:%H:%M}" if fim else f"{ini:%H:%M}"
                alertas.append(f"• {nome} — {posto} (turno {horario})")

        enviado = False
        if alertas:
            from modules.operacional.field_alerts import enviar_telegram  # lazy

            texto = (
                "⚠️ *Sem batida de ponto* (30min após o início do turno)\n"
                + "\n".join(alertas)
                + f"\n_Verificado às {agora:%H:%M} (Manaus) · fonte: escala × gp_clock_punches_"
            )
            enviado = await enviar_telegram(texto)
        return {"turnos_sem_presenca_na_janela": len(alertas), "enviado": enviado}

    try:
        result = asyncio.run(_run())
        logger.info(f"[Operacional Task] Vigia de ausência: {result}")
        return result
    except Exception as exc:
        logger.error(f"[Operacional Task] Erro no vigia de ausência: {exc}")
        raise self.retry(exc=exc)


@app.task(
    name="operacional.gerar_escalas_proximo_mes",
    bind=True,
    max_retries=2,
)
def gerar_escalas_proximo_mes(self):
    """Dia 25: gera em RASCUNHO as escalas do mês seguinte a partir das alocações ativas
    e avisa a gestão no Telegram para revisar e publicar. Nunca publica sozinho."""

    async def _run() -> dict:
        from datetime import date

        from modules.operacional.services.auto_scale_service import AutoScaleService

        hoje = date.today()
        mes = 1 if hoje.month == 12 else hoje.month + 1
        ano = hoje.year + 1 if hoje.month == 12 else hoje.year

        async with get_async_db_session() as db:
            service = AutoScaleService(db)
            result = await service.generate_scales_for_month(mes, ano, created_by=None)

        from modules.operacional.field_alerts import enviar_telegram  # lazy

        if result.get("scales_created", 0) > 0:
            texto = (
                f"📅 *Escalas de {mes:02d}/{ano} geradas em rascunho*\n"
                f"• {result['scales_created']} escalas · {result['shifts_created']} turnos\n"
                "Revise e publique em Operacional → Escalas (ou na Triagem)."
            )
        else:
            texto = (
                f"📅 Escalas de {mes:02d}/{ano}: nada gerado "
                f"(já existiam ou sem alocações ativas). Erros: {len(result.get('errors', []))}"
            )
        enviado = await enviar_telegram(texto)
        result["telegram_enviado"] = enviado
        return result

    try:
        result = asyncio.run(_run())
        logger.info(f"[Operacional Task] Escalas do próximo mês: {result}")
        return result
    except Exception as exc:
        logger.error(f"[Operacional Task] Erro ao gerar escalas do próximo mês: {exc}")
        raise self.retry(exc=exc)
