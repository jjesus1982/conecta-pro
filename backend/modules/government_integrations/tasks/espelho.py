"""Task Celery que sincroniza o espelho oficial do eSocial.

🔴 POR QUE ESTE ARQUIVO NASCEU EM 25/09/2026: **ele não existia, e três coisas o chamavam.**

  · `celery_app.py:608` — beat `esocial-espelho-sync`, agendado, na fila `gov.esocial`
  · `celery_app.py:92`  — roteamento declarado para a mesma fila
  · `esocial_espelho_controller.py:50` — o botão "Sincronizar" da tela manda a task por NOME

O beat estava agendado e **nunca pôde ter rodado**: `send_task` por nome não valida que o
destino existe — o Celery aceita, enfileira, e o worker responde `NotRegistered` num log que
ninguém lê. Efeito medido: o espelho congelou em **03/07/2026**, com **1 evento S-2200** (de
1995) e **5 S-2299**. Ou seja, a fonte oficial de quem foi ADMITIDO e DEMITIDO estava vazia
enquanto a tela de "sincronizar" respondia `success: true`.

E a consequência prática apareceu hoje: quando o dono pediu para conferir o efetivo contra o
eSocial, não havia contra o que conferir. Os 4 colaboradores criados pela planilha de setembro
também não puderam ter CPF puxado de lá.

⭐ A capacidade SEMPRE EXISTIU. `services/esocial_espelho_service.py` tem a lógica inteira —
`gerar_janelas`, `sincronizar_espelho`, os INSERTs — e há **818 janelas** na fila e **267
acessos** já feitos ao governo. Faltava só o invólucro. Não é código faltando, é código
desligado, e o consumidor que faltava tinha 20 linhas.

⚠️ O QUE ESTA TASK **NÃO** FAZ: transmitir. Consulta e download são READ-ONLY no governo.
Transmitir evento gera fato jurídico e é do Jordan, nunca de um beat.

⚠️ ORÇAMENTO DO GOVERNO: 10 acessos/dia e bloqueio nos dias 1–7 do mês. O `max_acessos=8`
deixa folga para o uso manual da tela no mesmo dia — se a task gastasse os 10, o botão
"Sincronizar" pararia de funcionar sem explicação.
"""

from __future__ import annotations

import logging

from celery_app import app

logger = logging.getLogger(__name__)


@app.task(name="government_integrations.tasks.espelho.sincronizar_espelho_esocial", bind=True)
def sincronizar_espelho_esocial(  # noqa: PLR0913
    self,  # noqa: ANN001, ARG001
    tipos: list[str] | None = None,
    periodo: str | None = None,
    cpfs: list[str] | None = None,
    max_acessos: int = 8,
    max_downloads: int = 50,
) -> dict:
    """Consulta identificadores pendentes no eSocial e baixa os XMLs. READ-ONLY no governo.

    Devolve o dicionário do serviço. Falha é LOGADA com nível error e RELANÇADA: desde 07/09
    o sino ouve `task_failure` (`notifications/task_falha.py`), e é por ali que uma falha vira
    aviso. A versão anterior devolvia `{"ok": False}` — para o Celery isso é SUCESSO, e o
    `checar_beats` acusava (quando analisava): «engole a própria falha, o sino fica mudo».
    Bloqueio dos dias 1–7 e orçamento esgotado NÃO são exceção: o serviço devolve status.
    """
    import asyncio

    from modules.government_integrations.services.esocial_espelho_service import (
        sincronizar_espelho,
    )

    try:
        r = asyncio.run(
            sincronizar_espelho(
                tipos=tipos,
                periodo=periodo,
                cpfs=cpfs,
                max_acessos=max_acessos,
                max_downloads=max_downloads,
            )
        )
        logger.info("espelho eSocial sincronizado: %s", r)
        return {"ok": True, **(r if isinstance(r, dict) else {"resultado": r})}
    except Exception:
        logger.error("espelho eSocial: sincronização FALHOU", exc_info=True)
        raise
