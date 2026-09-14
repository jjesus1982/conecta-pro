#!/usr/bin/env python3
"""Jordan e Pyetra têm o MESMO acesso — em todos os portões, dos dois lados.

Origem (14/09/2026): o Jordan pediu *"o perfil da Andrya Pyetra Souza de Jesus, login
pjesus@conectamais.pro, precisa ter o mesmo perfil full que eu tenho"*. Fui medir e os
dois já eram `role='admin'` com `permissions={all}` — idênticos na tabela. A diferença
estava em LISTAS DE E-MAIL espalhadas pelo código, quatro delas com a mesma intenção:

    ai/consultores/permissions.CONSULTOR_EXECUTIVO_EMAILS   Jordan + Pyetra   ✓
    crm/services/contract_wizard.EMITENTES                  Jordan + Pyetra   ✓
    fiscal_contabil/.../guias_drive.FISCAL_OWNERS_EMAILS    Jordan + Pyetra   ✓
    inter/payment_controller  (tupla literal no handler)    SÓ Jordan         ✗

A quarta ficou para trás e ninguém viu: a Pyetra levava 403 no log de auditoria de
pagamentos. No front era pior — o botão «Aprovar» de pagamento preparado não existia para
ela, e a tela dizia «Aguardando Jordan».

Lista duplicada é lista que diverge. Agora a fonte é `core/auth/diretoria.py` e este
oráculo afirma a REGRA: quem está na diretoria passa nos mesmos lugares, e quem não está
não passa em nenhum. Vale nos DOIS sentidos — um gate que aceita todo mundo reprova aqui
igual a um que barra a Pyetra.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/orq/test_diretoria_paridade.py

Linha canônica: `TOTAL: <n> divergência(s) de acesso da diretoria`. Exit 1 se houver.
"""
from __future__ import annotations

import asyncio
import sys

JORDAN = "jjesus@conectamais.pro"
PYETRA = "pjesus@conectamais.pro"
#: Ninguém. Serve para provar que o portão ainda é portão.
ESTRANHO = "ninguem@exemplo-invalido.test"


async def main() -> int:
    from core.auth.diretoria import DIRETORIA, e_diretoria  # noqa: PLC0415

    falhas: list[str] = []

    # 1. A fonte única reconhece os dois — e recusa quem não é.
    for quem, email in (("Jordan", JORDAN), ("Pyetra", PYETRA)):
        if not e_diretoria(email):
            falhas.append(f"{quem} ({email}) não é reconhecido como diretoria")
    if e_diretoria(ESTRANHO):
        falhas.append("um e-mail qualquer passou como diretoria — o portão deixou de ser portão")
    # tolerância a caixa e espaço (o JWT nem sempre vem normalizado)
    if not e_diretoria(f"  {PYETRA.upper()}  "):
        falhas.append("e_diretoria não tolera caixa alta/espaço — o login vem assim do JWT")

    # 2. Todas as listas de e-mail que significam "diretoria" contêm os DOIS.
    listas: list[tuple[str, set[str]]] = []
    try:
        from modules.ai.consultores.permissions import (  # noqa: PLC0415
            CONSULTOR_EXECUTIVO_EMAILS,
            _MCP_ALLOWED,
        )

        listas += [("CONSULTOR_EXECUTIVO_EMAILS", set(CONSULTOR_EXECUTIVO_EMAILS)),
                   ("_MCP_ALLOWED", set(_MCP_ALLOWED))]
    except Exception as e:  # noqa: BLE001
        falhas.append(f"permissions dos consultores não importa: {type(e).__name__}: {e}")
    try:
        from modules.crm.services.contract_wizard import EMITENTES  # noqa: PLC0415

        listas.append(("EMITENTES (contrato)", set(EMITENTES)))
    except Exception as e:  # noqa: BLE001
        falhas.append(f"EMITENTES não importa: {type(e).__name__}: {e}")
    try:
        from modules.fiscal_contabil.obrigacoes.guias_drive_service import (  # noqa: PLC0415
            FISCAL_OWNERS_EMAILS,
        )

        listas.append(("FISCAL_OWNERS_EMAILS", set(FISCAL_OWNERS_EMAILS)))
    except Exception as e:  # noqa: BLE001
        falhas.append(f"FISCAL_OWNERS_EMAILS não importa: {type(e).__name__}: {e}")

    for nome, conjunto in listas:
        for quem, email in (("Jordan", JORDAN), ("Pyetra", PYETRA)):
            if email not in conjunto:
                falhas.append(f"{nome}: {quem} está de fora — acesso desigual")

    # 3. O gate do log de auditoria de pagamentos: os dois entram, o estranho não.
    #    É o handler DE VERDADE, não uma cópia da regra.
    try:
        from fastapi import HTTPException  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
        from modules.integrations.inter.payment_controller import (  # noqa: PLC0415
            audit_log_global,
        )

        class _U:
            def __init__(self, email: str) -> None:
                self.email = email

        async with async_session_factory() as db:
            for quem, email, deve_passar in (
                ("Jordan", JORDAN, True),
                ("Pyetra", PYETRA, True),
                ("estranho", ESTRANHO, False),
            ):
                try:
                    await audit_log_global(limit=1, offset=0, db=db, current_user=_U(email))
                    passou = True
                except HTTPException as exc:
                    passou = exc.status_code != 403
                except Exception:  # noqa: BLE001 — erro de consulta não é erro de permissão
                    passou = True
                if passou != deve_passar:
                    falhas.append(
                        f"audit de pagamentos: {quem} "
                        + ("foi BARRADO e deveria entrar" if deve_passar else "ENTROU e não deveria")
                    )
    except Exception as e:  # noqa: BLE001
        falhas.append(f"não consegui exercitar o gate do audit: {type(e).__name__}: {e}")

    # 4. E na TABELA: mesmo papel, mesmas permissões, os dois ativos.
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415

        async with async_session_factory() as db:
            linhas = {
                r[0]: (r[1], tuple(r[2] or ()), r[3])
                for r in (
                    await db.execute(
                        text(
                            "SELECT email, role, permissions, is_active FROM users "
                            "WHERE email IN (:j, :p)"
                        ),
                        {"j": JORDAN, "p": PYETRA},
                    )
                ).all()
            }
        for email in (JORDAN, PYETRA):
            if email not in linhas:
                falhas.append(f"{email} não existe na tabela users")
        if JORDAN in linhas and PYETRA in linhas and linhas[JORDAN] != linhas[PYETRA]:
            falhas.append(
                f"users: Jordan {linhas[JORDAN]} × Pyetra {linhas[PYETRA]} — papel/permissão/ativo diferentes"
            )
    except Exception as e:  # noqa: BLE001
        falhas.append(f"não consegui ler a tabela users: {type(e).__name__}: {e}")

    for f in falhas:
        print(f"   ✗ {f}")
    if not falhas:
        print(f"   ✓ diretoria = {sorted(DIRETORIA)}")
        print(f"   ✓ {len(listas)} lista(s) de acesso com os dois · gate do audit exercitado · users idênticos")
    print(f"\nTOTAL: {len(falhas)} divergência(s) de acesso da diretoria")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
