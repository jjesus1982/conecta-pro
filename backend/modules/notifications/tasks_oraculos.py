"""Os 59 oráculos rodam sozinhos todo dia; falha vira alerta no sino.

Um oráculo compara o que a tela MOSTRA com o que o banco TEM. Existiam 59, rodados à mão —
o que significa que só denunciavam divergência quando alguém lembrava de rodá-los. Em
11/08/2026, sete estavam vermelhos e ninguém sabia; nenhum era defeito de produto: eram
testes presos a e-mail de gente que saiu, a tools renomeadas e a telas que mudaram de forma
de propósito. Teste que ninguém roda apodrece em silêncio e depois se confunde com bug.

Não se escreveu notificação nova. `modules.notifications.task_falha` já captura
`task_failure` do Celery e grava UM alerta por tarefa por dia no sino, com chave de
idempotência no banco. Então esta tarefa apenas ESTOURA quando algum oráculo fica vermelho,
carregando os nomes na mensagem — o resto do caminho já existia e já é deduplicado.
Verde = silêncio absoluto; o sino só toca quando há o que fazer.

Subprocess, não import: cada oráculo é um script com `asyncio.run(main())` e `SystemExit`,
alguns mexem no registry global de tools. Rodar no processo do worker deixaria um
contaminando o outro; e é exatamente assim que eles são invocados à mão.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)

_DIR = Path(os.getenv("ORQ_DIR", "/app/scripts/orq"))

#: Teto por oráculo. O mais lento (RBAC, 8 sub-oráculos) leva ~1min; 5 é folga com margem.
_TIMEOUT_ORACULO_S = 300

#: Teto do lote. A varredura completa leva ~15min; 45 cobre uma base bem maior sem que a
#: tarefa fique presa a noite inteira segurando um worker.
_TIMEOUT_LOTE_S = 45 * 60


class OraculosVermelhos(Exception):
    """Levantada para que `task_falha` publique no sino. A mensagem É o alerta."""


def _oraculos() -> list[Path]:
    return sorted(p for p in _DIR.glob("*.py") if not p.name.startswith("_"))


# Os limites da fila `gov.batch` são 300s/600s. A varredura leva ~15min: a primeira execução
# real (11/08 12:14) foi morta a SIGKILL aos 10min — e morte por sinal não dispara
# `task_failure`, então a tarefa que existe para quebrar o silêncio morria em silêncio. Os
# limites vão no decorator, que vence o padrão da fila, com folga sobre o teto do lote.
@shared_task(name="orq.oraculos_diarios",
             soft_time_limit=_TIMEOUT_LOTE_S + 300, time_limit=_TIMEOUT_LOTE_S + 600)
def rodar_oraculos_diarios() -> dict:
    """Roda todos os oráculos. Devolve o resumo; estoura se algum falhar."""
    arquivos = _oraculos()
    if not arquivos:
        raise OraculosVermelhos(f"nenhum oráculo encontrado em {_DIR} — a varredura virou casca")

    env = {**os.environ, "PYTHONPATH": "/app"}
    limite = time.monotonic() + _TIMEOUT_LOTE_S
    verdes: list[str] = []
    vermelhos: list[tuple[str, str]] = []

    try:
        for arq in arquivos:
            if time.monotonic() > limite:
                continue  # sobra vira "não rodado" abaixo — lote estourado não é sucesso parcial
            ok, motivo = _rodar(arq, env)
            if not ok:
                # Segunda chance. Duas varreduras manuais de 11/08 vieram com 38 e 17 "falhas"
                # que eram outra sessão recriando o container no meio — a conexão morre e tudo
                # dali em diante estoura junto. Alerta falso ensina a ignorar o sino, que é pior
                # que não ter alerta. Defeito de verdade falha nas duas.
                time.sleep(5)
                ok, motivo = _rodar(arq, env)
            (verdes.append(arq.name) if ok else vermelhos.append((arq.name, motivo)))
    except SoftTimeLimitExceeded:
        # Pedido de parada gracioso: para de rodar, mas AINDA reporta. Sem isto o hard limit
        # mata o processo e ninguém fica sabendo de nada.
        logger.warning("[oraculos] limite gracioso atingido — reportando o que deu tempo")

    feitos = set(verdes) | {n for n, _ in vermelhos}
    nao_rodados = [a.name for a in arquivos if a.name not in feitos]

    resumo = {"total": len(arquivos), "verdes": len(verdes), "vermelhos": len(vermelhos),
              "nao_rodados": len(nao_rodados),
              "falhas": [{"oraculo": n, "motivo": m} for n, m in vermelhos]}
    logger.info("[oraculos] %s verdes, %s vermelhos, %s não rodados",
                len(verdes), len(vermelhos), len(nao_rodados))

    if vermelhos or nao_rodados:
        raise OraculosVermelhos(_mensagem(len(arquivos), vermelhos, nao_rodados))
    return resumo


def _rodar(arq: Path, env: dict) -> tuple[bool, str]:
    """Roda um oráculo. Devolve (passou, motivo) — nunca levanta."""
    try:
        r = subprocess.run([sys.executable, str(arq)], env=env, capture_output=True,
                           text=True, timeout=_TIMEOUT_ORACULO_S)
        if r.returncode == 0:
            return True, ""
        return False, _motivo((r.stdout or "") + (r.stderr or ""))
    except subprocess.TimeoutExpired:
        return False, f"não terminou em {_TIMEOUT_ORACULO_S}s"
    except SoftTimeLimitExceeded:
        # NÃO engolir: `SoftTimeLimitExceeded` herda de Exception, então o `except` abaixo a
        # capturaria e a varredura ignoraria o pedido de parada — marcando como vermelho todo
        # oráculo restante até o hard limit matar o processo. Alerta catastrófico e falso.
        raise
    except Exception as exc:  # noqa: BLE001 — um oráculo quebrado não derruba a varredura
        return False, f"{type(exc).__name__}: {exc}"


def _motivo(saida: str) -> str:
    """Última linha útil da saída — quase sempre a mensagem do assert."""
    linhas = [ln.strip() for ln in saida.splitlines() if ln.strip()]
    for ln in reversed(linhas):
        if "Error" in ln or "assert" in ln.lower() or "FAIL" in ln:
            return ln[:160]
    return (linhas[-1][:160] if linhas else "sem saída")


def _mensagem(total: int, vermelhos: list[tuple[str, str]], nao_rodados: list[str]) -> str:
    """A mensagem vira o corpo do alerta no sino — cabe pouco, então diz o essencial.

    `task_falha` corta o erro em 400 caracteres. Por isso: contagem primeiro (que sempre
    cabe), depois os nomes, e o aviso explícito de quantos ficaram de fora do texto — um
    corte silencioso aqui esconderia justamente o oráculo que ninguém viu.
    """
    partes = [f"{len(vermelhos)} de {total} oráculos vermelhos."]
    if nao_rodados:
        partes.append(f"{len(nao_rodados)} não rodaram (lote estourou o tempo).")
    mostrados = vermelhos[:6]
    partes += [f"{n.removeprefix('test_').removesuffix('.py')}: {m}" for n, m in mostrados]
    if len(vermelhos) > len(mostrados):
        partes.append(f"(+{len(vermelhos) - len(mostrados)} não listados — ver log do worker)")
    return " ".join(partes)


if __name__ == "__main__":
    # Self-check sem banco: a mensagem tem que caber no sino e nunca esconder corte.
    msg = _mensagem(59, [(f"test_x{i}.py", "AssertionError: algo") for i in range(9)], ["test_y.py"])
    assert msg.startswith("9 de 59 oráculos vermelhos."), msg
    assert "não rodaram" in msg and "+3 não listados" in msg, msg
    assert _motivo("linha 1\nAssertionError: tela vazia\n") == "AssertionError: tela vazia"
    assert _motivo("") == "sem saída"
    assert _mensagem(59, [], []) == "0 de 59 oráculos vermelhos."
    print("self-check OK\n" + msg)
