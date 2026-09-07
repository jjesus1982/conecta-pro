"""
Tasks Celery — SST: alertas automáticos de Saúde Ocupacional.

Executa via Celery Beat:
- verificar_asos_vencendo: diariamente às 07:00 — alerta ASOs próximos do vencimento
- verificar_epis_vencendo: diariamente às 07:30 — alerta EPIs com validade próxima
- verificar_exames_pendentes: diariamente às 08:00 — exames não agendados há > 30 dias
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="sst.verificar_asos_vencendo")
def verificar_asos_vencendo(dias_antecedencia: int = 30) -> str:
    """
    Verifica ASOs próximos do vencimento e loga alertas.

    Verifica dois horizontes:
    - Crítico: vencendo em até 7 dias
    - Atenção: vencendo em até 30 dias (ou dias_antecedencia)

    Returns:
        Resumo do processamento.
    """
    from sqlalchemy import text

    from core.database.session import get_sync_db

    hoje = date.today()
    limite_atencao = hoje + timedelta(days=dias_antecedencia)
    limite_critico = hoje + timedelta(days=7)  # noqa: F841

    try:
        with get_sync_db() as db:
            # ASOs vencendo (consulta direta para evitar dependência circular)
            result = db.execute(
                text(
                    """
                    -- 07/09/2026: lia `health_asos` (família morta: a tabela nem existe) e
                    -- engolia a exceção — nunca alertou. Os ASOs vivos estão em `gp_asos`
                    -- (data_validade). Medido no dia: de 53 ativos, 25 com o ASO mais
                    -- recente VENCIDO e 21 sem ASO nenhum; a janela antiga (só "vencendo")
                    -- nunca alertaria vencido — agora o vencido é crítico.
                    SELECT
                        a.id,
                        a.aso_id AS exame_id,
                        coalesce(a.aso_id::text, a.id::text) AS numero_aso,
                        CASE WHEN a.apto THEN 'apto' ELSE coalesce(a.status, 'n/d') END AS resultado,
                        a.data_validade AS data_vencimento,
                        a.data_validade - :hoje AS dias_restantes,
                        a.employee_id AS funcionario_id,
                        coalesce(e.cargo, '') AS funcao,
                        '' AS setor
                    FROM gp_asos a
                    JOIN employees e ON e.id = a.employee_id AND e.status = 'ativo'
                    WHERE a.data_validade IS NOT NULL
                      AND a.data_validade <= :limite_atencao
                      AND a.data_validade = (SELECT max(x.data_validade) FROM gp_asos x WHERE x.employee_id = a.employee_id)
                    ORDER BY a.data_validade ASC
                    """
                ),
                {
                    "hoje": hoje,
                    "limite_atencao": limite_atencao,
                },
            )
            asos = result.fetchall()

            criticos = [a for a in asos if a.dias_restantes <= 7]
            atencao = [a for a in asos if a.dias_restantes > 7]

            for aso in criticos:
                logger.warning(
                    "🔴 ASO CRÍTICO vencendo em %s dias: aso=%s funcionario=%s funcao=%s setor=%s vencimento=%s",
                    aso.dias_restantes,
                    aso.numero_aso,
                    aso.funcionario_id,
                    aso.funcao,
                    aso.setor,
                    aso.data_vencimento,
                )

            for aso in atencao:
                logger.info(
                    "🟡 ASO vencendo em %s dias: aso=%s funcionario=%s funcao=%s vencimento=%s",
                    aso.dias_restantes,
                    aso.numero_aso,
                    aso.funcionario_id,
                    aso.funcao,
                    aso.data_vencimento,
                )

            # Publicar evento de alerta para cada ASO crítico
            if criticos:
                _publicar_alertas_aso(criticos)

            resumo = (
                f"{len(asos)} ASOs vencendo nos próximos {dias_antecedencia} dias "
                f"({len(criticos)} críticos, {len(atencao)} atenção)"
            )
            logger.info("verificar_asos_vencendo concluído: %s", resumo)
            return resumo

    except Exception as exc:
        logger.error("Erro em verificar_asos_vencendo: %s", exc)
        return f"Erro: {exc}"


def _publicar_alertas_aso(asos: list) -> None:
    """Publica eventos de alerta para ASOs críticos no message bus."""
    try:
        import asyncio

        from infrastructure.message_bus.bus import MessagePriority
        from infrastructure.message_bus.events import Event, EventType, publish_event

        for aso in asos:
            event = Event(
                type=EventType.EXAME_AGENDADO,  # Reutiliza tipo existente como alerta
                source="health_occupational.sst_tasks",
                data={
                    "alerta_tipo": "aso_vencendo",
                    "aso_id": str(aso.id),
                    "numero_aso": aso.numero_aso,
                    "funcionario_id": str(aso.funcionario_id),
                    "dias_restantes": int(aso.dias_restantes),
                    "data_vencimento": str(aso.data_vencimento),
                    "funcao": aso.funcao,
                    "setor": aso.setor,
                },
                metadata={"alerta": True, "prioridade": "critico"},
            )
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(publish_event(event, priority=MessagePriority.HIGH))
                else:
                    asyncio.run(publish_event(event, priority=MessagePriority.HIGH))
            except RuntimeError:
                asyncio.run(publish_event(event, priority=MessagePriority.HIGH))

    except Exception as exc:
        logger.warning("Falha ao publicar alertas ASO: %s", exc)


@app.task(name="sst.verificar_epis_vencendo")
def verificar_epis_vencendo(dias_antecedencia: int = 30) -> str:
    """
    Verifica EPIs com validade próxima (na ficha do funcionário).

    Alertas:
    - Crítico: vencendo em até 7 dias
    - Atenção: vencendo em até 30 dias

    Returns:
        Resumo do processamento.
    """
    from sqlalchemy import text

    from core.database.session import get_sync_db

    hoje = date.today()
    limite_atencao = hoje + timedelta(days=dias_antecedencia)

    try:
        with get_sync_db() as db:
            result = db.execute(
                text(
                    """
                    SELECT
                        ed.id,
                        ed.epi_id,
                        ed.funcionario_id,
                        ed.data_validade,
                        ed.data_validade - :hoje AS dias_restantes,
                        ed.motivo,
                        ed.quantidade,
                        ec.nome AS epi_nome,
                        ec.ca_number,
                        ec.categoria
                    FROM health_epi_deliveries ed
                    JOIN health_epi_catalog ec ON ec.id = ed.epi_id
                    WHERE ed.devolvido = FALSE
                      AND ed.data_validade IS NOT NULL
                      AND ed.data_validade <= :limite_atencao
                      AND ed.data_validade >= :hoje
                    ORDER BY ed.data_validade ASC
                    """
                ),
                {
                    "hoje": hoje,
                    "limite_atencao": limite_atencao,
                },
            )
            epis = result.fetchall()

            criticos = [e for e in epis if e.dias_restantes <= 7]
            atencao = [e for e in epis if e.dias_restantes > 7]

            for epi in criticos:
                logger.warning(
                    "🔴 EPI CRÍTICO vencendo em %s dias: epi=%s ca=%s funcionario=%s vencimento=%s",
                    epi.dias_restantes,
                    epi.epi_nome,
                    epi.ca_number,
                    epi.funcionario_id,
                    epi.data_validade,
                )

            for epi in atencao:
                logger.info(
                    "🟡 EPI vencendo em %s dias: epi=%s funcionario=%s",
                    epi.dias_restantes,
                    epi.epi_nome,
                    epi.funcionario_id,
                )

            resumo = (
                f"{len(epis)} EPIs vencendo nos próximos {dias_antecedencia} dias "
                f"({len(criticos)} críticos, {len(atencao)} atenção)"
            )
            logger.info("verificar_epis_vencendo concluído: %s", resumo)
            return resumo

    except Exception as exc:
        logger.error("Erro em verificar_epis_vencendo: %s", exc)
        return f"Erro: {exc}"


@app.task(name="sst.verificar_exames_pendentes")
def verificar_exames_pendentes(dias_sem_exame: int = 365) -> str:
    """
    Verifica funcionários com exames periódicos vencidos ou nunca realizados.

    Busca exames periódicos com mais de `dias_sem_exame` dias sem renovação.

    Returns:
        Resumo do processamento.
    """
    from sqlalchemy import text

    from core.database.session import get_sync_db

    hoje = date.today()
    limite = hoje - timedelta(days=dias_sem_exame)

    try:
        with get_sync_db() as db:
            result = db.execute(
                text(
                    """
                    SELECT
                        me.funcionario_id,
                        me.funcao,
                        me.setor,
                        MAX(me.data_realizacao) AS ultimo_exame,
                        :hoje - MAX(me.data_realizacao) AS dias_sem_exame
                    FROM health_medical_exams me
                    WHERE me.tipo_exame = 'periodico'
                      AND me.status = 'realizado'
                    GROUP BY me.funcionario_id, me.funcao, me.setor
                    HAVING MAX(me.data_realizacao) < :limite
                    ORDER BY ultimo_exame ASC
                    """
                ),
                {"hoje": hoje, "limite": limite},
            )
            pendentes = result.fetchall()

            for p in pendentes:
                logger.warning(
                    "⚠️ Exame periódico vencido: funcionario=%s funcao=%s setor=%s último_exame=%s (%s dias atrás)",
                    p.funcionario_id,
                    p.funcao,
                    p.setor,
                    p.ultimo_exame,
                    p.dias_sem_exame,
                )

            resumo = f"{len(pendentes)} funcionários com exame periódico vencido (>{dias_sem_exame} dias)"
            logger.info("verificar_exames_pendentes concluído: %s", resumo)
            return resumo

    except Exception as exc:
        logger.error("Erro em verificar_exames_pendentes: %s", exc)
        return f"Erro: {exc}"
