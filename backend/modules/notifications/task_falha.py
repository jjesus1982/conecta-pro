"""Falha de tarefa agendada vira alerta no sino — uma por tarefa por dia.

Em julho/2026 a tarefa `financial.fechar_razao_auto` estourou TODOS OS DIAS e o
único rastro foi o log do container. O razão parou em 63 lançamentos contra 181
de junho e ninguém soube por semanas. O sinal existia; faltava onde olhar.

Medido em 2026-08-10, antes de escrever isto:
  • `celery-task-meta-*` no Redis: **0 chaves** — o Celery não guarda resultado;
  • `scheduler_executions`, `scheduler_execution_logs`, `execution_logs`: **0 linhas**;
  • 88 tarefas agendadas, nenhum registro consultável de execução.

Não se criou tabela: o sino (`communication_notifications`) já tem índice único
parcial em (user_id, extra_data->>'idempotency_key'), então a deduplicação é
atômica no banco. A chave é `task_falha:<tarefa>:<dia>` — uma tarefa que estoura
de 5 em 5 minutos gera UM alerta no dia, não 288.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from celery.signals import task_failure, task_postrun
from sqlalchemy import text

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Manaus")

# Conta de serviço não lê sino. Robô recebendo alerta é ruído que treina gente
# a ignorar o sino.
_SQL_DESTINATARIOS = """
    SELECT id::text FROM users
    WHERE lower(coalesce(role, '')) = 'admin'
      AND coalesce(is_active, true) = true
      AND lower(coalesce(email, '')) NOT LIKE 'mcp-service%'
"""

_SQL_SINO = """
    INSERT INTO communication_notifications
        (id, tenant_id, user_id, title, body, type, reference_type,
         action_url, extra_data, is_active, sent_at, created_at)
    VALUES (gen_random_uuid(), :uid, :uid, :title, :body, 'alerta', 'task_falha',
            '/redesign', CAST(:extra AS jsonb), true, NOW(), NOW())
    ON CONFLICT DO NOTHING
"""


@task_postrun.connect
def registrar_sucesso_vazio_no_sino(sender=None, retval=None, state=None, **_kwargs) -> None:
    """Task que NÃO estoura mas devolve `{"ok": False}` / `{"erro": …}` é falha disfarçada de
    sucesso: o fechamento do razão ficou 27 dias assim (11/08 → 07/09/2026) e este módulo,
    que só ouve `task_failure`, não tinha o que avisar. 55 tasks engolem a própria exceção
    (`checar_beat_engole_falha`); aqui o resultado delas vira aviso, sem mudar cada uma."""
    try:
        if not isinstance(retval, dict):
            return
        erro = None
        if retval.get("ok") is False:
            erro = "devolveu ok=False: " + str({k: v for k, v in retval.items() if k in ("erro", "error", "msg", "mensagem", "detalhe")} or retval)[:300]
        elif retval.get("erro") or retval.get("error"):
            erro = "devolveu erro: " + str(retval.get("erro") or retval.get("error"))[:300]
        if not erro:
            return
        nome = getattr(sender, "name", None) or str(sender)
        _avisar(nome, erro, titulo=f"Tarefa agendada devolveu falha: {nome}")
    except Exception as exc:  # noqa: BLE001 — nunca derrubar a tarefa por causa do aviso
        logger.warning("[task_falha] não consegui registrar o sucesso vazio no sino: %s", exc)


@task_failure.connect
def registrar_falha_no_sino(sender=None, exception=None, einfo=None, **_kwargs) -> None:
    """Grava UM alerta por tarefa por dia quando uma tarefa Celery estoura.

    Envolvido em try/except de propósito: um manipulador de falha que falha é
    pior que nenhum — derrubaria a própria tarefa que já estava com problema.
    """
    try:
        nome = getattr(sender, "name", None) or str(sender)
        erro = f"{type(exception).__name__}: {exception}"[:400]
        _avisar(nome, erro)
    except Exception as exc:  # noqa: BLE001 — nunca derrubar a tarefa por causa do aviso
        logger.warning("[task_falha] não consegui registrar a falha no sino: %s", exc)


def _avisar(nome: str, erro: str, titulo: str | None = None) -> None:
    """Um aviso por (tarefa, dia) no sino dos admins — mesmo molde para exceção e sucesso vazio."""
    try:
        dia = datetime.now(_TZ).strftime("%Y-%m-%d")

        # Importado aqui dentro: no import do módulo o app ainda está subindo.
        from core.database.session import SyncSessionLocal

        with SyncSessionLocal() as db:
            destinatarios = [r[0] for r in db.execute(text(_SQL_DESTINATARIOS)).fetchall()]
            if not destinatarios:
                logger.warning("[task_falha] %s estourou e não há admin ativo para avisar", nome)
                return
            extra = json.dumps({
                "idempotency_key": f"task_falha:{nome}:{dia}",
                "origem": "task_falha", "familia": "sistema",
                "severidade": "critico", "tarefa": nome, "erro": erro,
            })
            title = titulo or f"Tarefa agendada falhou: {nome}"
            body = (
                f"A tarefa {nome} estourou hoje ({dia}).\n\n{erro}\n\n"
                f"Se ela roda todo dia, pode estar falhando em silêncio há mais tempo — "
                f"foi assim que o fechamento contábil parou em julho/2026 e só se "
                f"descobriu semanas depois. Conferir o log do worker."
            )
            for uid in destinatarios:
                db.execute(text(_SQL_SINO), {"uid": uid, "title": title,
                                             "body": body, "extra": extra})
            db.commit()
    except Exception as exc:  # noqa: BLE001 — nunca derrubar a tarefa por causa do aviso
        logger.warning("[task_falha] não consegui registrar a falha no sino: %s", exc)
