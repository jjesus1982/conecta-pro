"""Recalcula o espelho de ponto do mês corrente, todo dia — para o DP conferir ontem, não 14/09.

🔴 POR QUE EXISTE (28/09/2026). A Pyetra vai passar a conferir ponto pela tela de apropriação de
horas. Fui medir o que ela veria e achei o mês **congelado**:

  · 55 espelhos de 09/2026, **51 deles com `last_calculated_at` em 14/09**
  · última batida da casa: 28/09 09:01
  · ou seja: ela abriria a tela e veria duas semanas de trabalho faltando

⭐ E o motivo não é bug de cálculo — é **rotina que não existe**. `calcular_espelho` só roda
quando alguém fecha o mês (`fechar_mes`), quando o funcionário abre o Meu Espaço
(`self_service_controller.py:1556`), na geração de documentos (`gerar_docs_mes_service.py:87`)
ou em `punch_controller.py:413` — e **este último só quando não existe linha ainda**. Nenhum
beat. O espelho de quem não abriu o portal envelhece até alguém precisar dele no fim do mês.

É a terceira causa conhecida de rotina parada nesta casa: produtor sem consumidor, fila sem
beat, motor sem gatilho. A dívida quase nunca é código faltando.

## As travas, e por que cada uma existe

**`fechar=False` — NÃO É DETALHE.** `fechar_mes` tem `fechar=True` no padrão da assinatura, e
com ele o espelho **sem anomalia vira `status='fechado'` definitivo**, com `closed_at` e
`closed_by`. Um beat diário com o padrão fecharia o mês da casa inteira sozinho, todo dia, sem
ninguém conferir. Fechamento é ato humano; este beat só **calcula**.

**Só o mês corrente.** Recalcular meses passados mexeria em base de folha já paga.

**Mês fechado/assinado é pulado pelo próprio motor** — `espelho_service.py:552-558` recusa
mesmo com `force=True`, porque o hash do PDF assinado deixaria de corresponder aos dados.
⚠️ Esta rotina **jamais** chama `reopen_time_sheet`: reabrir invalida homologação e assinatura.

**Fila `gov.batch`.** Tem consumidor comprovado (64 tarefas roteadas nela). ⚠️ NUNCA a fila
`ged` — ela tem produtor e **nenhum consumidor**, e mensagem entra lá para nunca sair.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from celery import shared_task

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Manaus")


@shared_task(name="ponto.recalcular_espelhos_mes_corrente")
def recalcular_espelhos_mes_corrente() -> dict[str, Any]:
    """Calcula (nunca fecha) o espelho de todos que bateram ponto no mês corrente."""
    from core.database.session import SyncSessionLocal
    from modules.people_management.hr.services.espelho_service import fechar_mes

    from sqlalchemy import text

    hoje = datetime.now(TZ).date()
    db = SyncSessionLocal()
    try:
        r = fechar_mes(db, hoje.month, hoje.year, fechar=False, force=True)

        # 🔴 COMMIT EXPLÍCITO — a primeira versão desta task NÃO tinha, e foi o defeito exato
        # que ela existe para combater. `espelho_service` só faz `db.flush()` (`:873`, `:1067`);
        # quem chama é que commita. Sem esta linha a task rodava, imprimia "47 processados" e
        # **o banco não mudava**: os 51 espelhos seguiam parados em 14/09 e o log dizia sucesso.
        db.commit()

        res = r.get("resumo") or {}
        processados = int(res.get("total_processados") or 0)
        com_anomalia = int(res.get("com_anomalia") or 0)
        erros = r.get("erros") or []

        # ⭐ PROVA POR LEITURA POSTERIOR, dentro da própria rotina. Contar o que a função
        # devolveu mede o que ela ACHA que fez; contar a coluna mede o que ficou gravado. Na
        # primeira versão os dois números discordavam e só o segundo estava certo.
        gravados = db.execute(text(
            "SELECT count(*) FROM time_sheets "
            " WHERE reference_month = :m AND reference_year = :a "
            "   AND last_calculated_at::date = CURRENT_DATE"),
            {"m": hoje.month, "a": hoje.year}).scalar() or 0

        logger.info(
            "espelho %02d/%s: %s processado(s) · %s com anomalia aberta · %s erro(s) · "
            "%s com carimbo de hoje no banco",
            hoje.month, hoje.year, processados, com_anomalia, len(erros), gravados,
        )
        if processados and not gravados:
            # Estado impossível que JÁ ACONTECEU: função diz que processou e nada foi gravado.
            logger.error("espelho: %s processado(s) e ZERO gravado(s) — recálculo não persistiu",
                         processados)

        # ⚠️ Erro por pessoa não derruba o lote (o motor isola em `erros`), mas tem de aparecer:
        # lote que falha calado é pior que lote que não roda, porque parece verde.
        for e in erros[:5]:
            logger.error("espelho: %s falhou — %s", e.get("employee_id"), str(e.get("erro"))[:160])

        return {"mes": hoje.month, "ano": hoje.year, "processados": processados,
                "com_anomalia": com_anomalia, "erros": len(erros), "gravados_hoje": int(gravados)}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.error("espelho: recálculo do mês corrente falhou — %s", exc, exc_info=True)
        raise
    finally:
        db.close()
