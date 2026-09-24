"""DGX AA4 — a conciliação da NFS-e rodando sozinha, depois da sincronia do ADN.

Por que agendada, e por que DEPOIS
-----------------------------------
A sincronia por NSU (`financial.sincronizar_nfse_nacional`, 04:30) é o caminho largo: ela
traz o que o ADN distribui. A conciliação é o caminho estreito: ela pergunta pelos números
que a régua diz que faltam. Rodar antes do ADN faria a conciliação perguntar ao fisco por
notas que a sincronia ia trazer de graça meia hora depois — requisição gasta à toa contra
um endpoint com limite por segundo.

Por que 40 números por rodada e não todos
------------------------------------------
O sefin limita requisições. A fila é durável (`nfse_conciliacao`) e o estado de cada número
fica gravado: uma rodada que para no meio não perde nada, e a de amanhã continua de onde
esta parou. Atravessar a fila devagar é melhor que levar 429 e não saber quais números
ficaram sem resposta.

O que esta task NÃO faz
-----------------------
**Não emite nota.** Nenhuma. O caminho de emissão (`nfse_emissao.emitir`) não é chamado
aqui, nem direta nem indiretamente — emissão exige clique humano, por desenho da frente.
Esta task só faz GET no fisco e INSERT/UPDATE no banco local.
"""

import logging

from celery_app import app

logger = logging.getLogger(__name__)

#: Quantos números de DPS perguntar por rodada. Ver docstring.
LOTE_POR_RODADA = 40


@app.task(
    name="fiscal.conciliar_nfse_com_fisco",
    bind=True,
    max_retries=2,
    default_retry_delay=900,
)
def conciliar_nfse_task(self, limite: int = LOTE_POR_RODADA):
    """Semeia as pendências e pergunta ao fisco sobre `limite` números de DPS."""
    import asyncio

    async def _rodar() -> dict:
        from core.database import async_session_factory
        from modules.fiscal.services import nfse_conciliacao as cc

        async with async_session_factory() as db:
            semeado = await cc.semear(db)
            r = await cc.conciliar(db, limite=limite, quem="agendador")
            return {**semeado, **r}

    try:
        r = asyncio.run(_rodar())
        logger.info(
            "NFS-e conciliação: %s consultadas, %s recuperadas (R$ %s), %s negadas pelo fisco, %s erros",
            r.get("consultadas"),
            r.get("recuperadas"),
            r.get("dinheiro_recuperado"),
            r.get("fisco_disse_que_nao_existe"),
            r.get("erros"),
        )
        return r
    except Exception as exc:  # noqa: BLE001
        logger.error("NFS-e conciliação falhou: %s", exc)
        raise self.retry(exc=exc) from exc
