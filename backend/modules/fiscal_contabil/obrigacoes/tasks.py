"""Tasks Celery — Fiscal/Obrigações (puxador de guias do Drive)."""

from __future__ import annotations

import logging

from celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="fiscal.sync_guias_drive", queue="gov.batch")
def task_sync_guias_drive() -> dict:
    """Puxa o pacote mensal de guias (Portte/Onvio) da pasta do Drive.

    Roda 2×/dia via beat; idempotente (file_id registrado em observacoes).
    """
    from modules.fiscal_contabil.obrigacoes.guias_drive_service import sync_guias_drive, sync_guias_onvio

    rel = sync_guias_drive()
    # Enquanto o Onvio (da Portte) existir, os PDFs que ele já baixou também viram obrigação.
    try:
        rel["onvio"] = sync_guias_onvio()
    except Exception as exc:  # noqa: BLE001
        logger.warning("sync_guias_onvio falhou (o Drive já foi processado): %s", exc)
    # Depois das guias, o extrato: obrigação com valor e débito exato na janela = cumprida.
    # Porta própria: a pasta de entrada não depende de Drive nem de Onvio (os dois são da
    # contabilidade e fecham quando ela sair). Roda DEPOIS das outras duas de propósito —
    # documento que já entrou por lá não é reprocessado, e o que só existe aqui entra igual.
    try:
        from modules.fiscal_contabil.obrigacoes.guias_drive_service import sync_guias_pasta

        rel["pasta_entrada"] = sync_guias_pasta()
    except Exception as exc:  # noqa: BLE001
        logger.warning("sync_guias_pasta falhou (Drive e Onvio já foram processados): %s", exc)

    try:
        from modules.fiscal_contabil.obrigacoes.guias_drive_service import parear_obrigacoes_com_extrato

        rel["pareamento"] = parear_obrigacoes_com_extrato()
    except Exception as exc:  # noqa: BLE001
        logger.warning("parear_obrigacoes_com_extrato falhou (guias já gravadas): %s", exc)
    logger.info(
        "fiscal.sync_guias_drive: ok=%s baixados=%s guias=%s anexos=%s ja=%s",
        rel.get("ok"),
        rel.get("baixados"),
        len(rel.get("guias", [])),
        len(rel.get("anexos", [])),
        rel.get("ja_processados"),
    )

    # Recibo que chega pelo ONVIO também dá baixa. Vai junto daqui, e não num beat novo,
    # porque é a mesma pergunta ("o que já foi entregue?") e esta tarefa já roda 2×/dia no
    # horário certo. Medido em 15/08/2026: a DCTFWeb de 07/2026 estava transmitida desde
    # 11/08, com recibo e saldo R$0,00, e as três acessórias apareciam pendentes vencendo
    # naquele dia — a regra de baixa existia, só ninguém a chamava por este caminho.
    from modules.fiscal_contabil.obrigacoes.baixa_por_recibo_onvio import baixar

    rel["baixa_onvio"] = baixar()
    logger.info(
        "fiscal.sync_guias_drive: baixa por recibo do Onvio — %s competência(s)",
        len(rel["baixa_onvio"].get("baixadas", [])),
    )

    # Parcelamento do acervo Onvio, pelo mesmo motivo e no mesmo lugar. Medido em 18/08/2026:
    # a casa paga SEIS acordos mensais e o sistema conhecia dois — os quatro invisíveis somam
    # ≈ R$ 6.207/mês, e parcela perdida não gera multa, RESCINDE o acordo.
    from modules.fiscal_contabil.obrigacoes.parcelamentos_onvio import sincronizar

    rel["parcelamentos_onvio"] = sincronizar()
    logger.info(
        "fiscal.sync_guias_drive: parcelamentos do Onvio — %s federal(is), %s municipal(is)",
        len(rel["parcelamentos_onvio"].get("federais", [])),
        len(rel["parcelamentos_onvio"].get("municipais", [])),
    )
    return rel


@app.task(name="fiscal.calendario_obrigacoes", queue="gov.batch")
def task_calendario_obrigacoes() -> dict:
    """Garante que cada competência FECHADA tenha suas obrigações recorrentes cadastradas.

    Existe porque o calendário dependia do PDF da guia chegar no Drive: as guias pararam em
    dez/2025 e o calendário parou junto — competências 04, 05 e 07/2026 simplesmente não
    existiam, e em 11/08 havia UMA obrigação vencendo nos 30 dias seguintes no sistema
    inteiro, com a competência de julho vencendo em nove dias.

    Obrigação existe por lei, não porque o documento chegou. Roda mensal; é idempotente,
    então rodar de novo não duplica.
    """
    import asyncio
    from datetime import date

    from core.database import async_session_factory
    from modules.fiscal_contabil.obrigacoes.calendario_service import garantir_ate_hoje

    async def _run():
        async with async_session_factory() as db:
            return await garantir_ate_hoje(db, date.today(), meses_atras=3, aplicar=True)

    # ⚠️ SEM `except` largo aqui. Devolver `{"erro": ...}` faz o Celery ver SUCESSO: o sinal
    # `task_failure` não dispara, `task_falha` não publica no sino, e a rotina fica quebrada
    # em silêncio. Foi assim que o espelho do eSocial passou 37 dias sem consultar o governo,
    # com beat diário e fila consumida. "Falha aqui não pode derrubar o worker" não se
    # sustenta: o worker sobrevive a task que estoura — quem não sobrevive é o alarme.
    r = asyncio.run(_run())
    logger.info("[calendario_obrigacoes] %s criada(s)", r.get("total"))
    return r
