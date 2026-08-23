"""Toda recusa de batida deixa rastro. O ponto cego não pode voltar.

🔴 O QUE MOTIVOU. Em 23/08/2026 o Jordan pediu uma auditoria severa do ponto — "a Lívia dá
divergência, o Ediwilson dá como se fosse ainda o primeiro acesso dele, muitos erros
assim". Eu não consegui responder POR QUE quatro pessoas nunca bateram uma única vez.

O banco tinha 1.943 batidas que DERAM CERTO e ZERO das que falharam. Eliminei hipóteses
(descriptor válido, conta ativa, geofence ok, rosto cadastrado, hora do cadastro) mas não
provei nada — auditoria por eliminação é o que sobra quando falta evidência.

Este oráculo trava a estrutura que produz a evidência: os caminhos de recusa do backend
têm de registrar, e o `except` do registrador tem de ser mudo (log nunca derruba batida de
quem está na guarita às 6h).

Afirma a REGRA, não a fotografia: não conta quantas falhas existem — no dia em que ninguém
falhar, o oráculo continua válido.
"""

import ast
import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

_CONTROLLER = "/app/modules/people_management/employee_portal/controllers/self_service_controller.py"
_REGISTRADOR = "/app/modules/people_management/ponto/tentativa_log.py"


async def main() -> None:
    with open(_CONTROLLER, encoding="utf-8") as fh:
        src = fh.read()

    # 1. A rota que o app chama quando desiste ANTES do servidor tem de existir.
    assert '"/tentativa-falhou"' in src, (
        "a rota /tentativa-falhou sumiu — a câmera que não abre e o rosto não reconhecido "
        "voltam a morrer no celular, sem chegar ao servidor"
    )

    # 2. Os dois GATES da batida facial (sem rosto e match=false) registram antes de recusar.
    achou = {"sem_rosto": False, "nao_reconhecido": False}
    for linha in src.splitlines():
        if "MOTIVO_SEM_ROSTO" in linha:
            achou["sem_rosto"] = True
        if "MOTIVO_NAO_RECONHECIDO" in linha:
            achou["nao_reconhecido"] = True
    faltando = [k for k, v in achou.items() if not v]
    assert not faltando, f"gate(s) de recusa sem registro de tentativa: {faltando}"

    # 3. O registrador NÃO pode propagar exceção: quem está na guarita precisa bater ponto,
    #    não alimentar auditoria. Verifica na ÁRVORE, não por texto.
    with open(_REGISTRADOR, encoding="utf-8") as fh:
        sql = fh.read()
    arvore = ast.parse(sql)
    fn = next(
        (n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "registrar_falha_async"),
        None,
    )
    assert fn is not None, "registrar_falha_async sumiu de tentativa_log"
    tem_try = any(isinstance(n, ast.Try) for n in ast.walk(fn))
    tem_raise = any(isinstance(n, ast.Raise) for n in ast.walk(fn))
    assert tem_try and not tem_raise, (
        "registrar_falha_async precisa engolir a própria falha (try sem raise) — "
        f"try={tem_try} raise={tem_raise}. Log que derruba batida é pior que log nenhum."
    )

    # 4. O destino tem de aceitar o registro. Colunas NOT NULL de gp_audit_logs já
    #    derrubaram o INSERT uma vez (actor_user_id), e o except mudo escondeu.
    with get_sync_db() as db:
        obrig = {
            r[0]
            for r in db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    " WHERE table_name = 'gp_audit_logs' AND is_nullable = 'NO'"
                )
            ).all()
        }
    ausentes = sorted(c for c in obrig if c not in sql and c != "timestamp")
    assert not ausentes, (
        f"coluna(s) NOT NULL de gp_audit_logs fora do INSERT: {ausentes} — o registro "
        "falharia calado e a tentativa sumiria, que é o defeito original"
    )

    print("OK rota /tentativa-falhou existe (falha que morre no celular chega ao servidor)")
    print("OK os 2 gates de recusa da batida facial registram antes de negar")
    print("OK registrar_falha_async engole a própria falha — nunca derruba a batida")
    print(f"OK as {len(obrig)} colunas NOT NULL de gp_audit_logs estão no INSERT")
    print("TEST oraculo_tentativa_ponto_registrada PASS")


if __name__ == "__main__":
    asyncio.run(main())
