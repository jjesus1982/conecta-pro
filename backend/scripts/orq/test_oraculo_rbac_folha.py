#!/usr/bin/env python3
"""Nenhuma rota de dinheiro do DP é alcançável por quem não tem o módulo `dp`.

Medido em 13/08/2026: 71 rotas sob `/dp/payslips`, `/dp/payroll` e `/hr/payroll` — folha,
holerite, chave PIX e pagamento — todas com `requer_modulo('dp')`. Sem token dão 401; com
token de perfil comum (`agente`, permissão `self:portal`) dão 403; e com um `admin` de
`permissions` VAZIO também dão 403, que é o que prova que o gate olha PERMISSÃO e não papel.

Por que este oráculo existe, se o gate já está de pé: ele é montado por um LAÇO no fim de
`dp_payslips_controller.py`, que percorre `router.routes` e anexa a dependência. Rota
declarada depois daquele laço nasce SEM gate, e nada no código avisa. Um `git diff` de uma
linha pode abrir o caminho do dinheiro sem ninguém perceber.

Duas asserções, porque uma só verificaria metade:

  (A) ESTRUTURAL, sobre TODAS as 71 — inclusive as de escrita, que não podem ser chamadas:
      cada rota de dinheiro do DP carrega `requer_modulo('dp')`. A descoberta é por PADRÃO
      DE CAMINHO, não por lista congelada: rota nova entra na conta sozinha, que é
      exatamente o caso que o laço deixa passar.
  (B) DE PONTA A PONTA, só em rota de LEITURA: 401 sem token, 403 com perfil comum. A
      estrutural prova que a dependência está pendurada; só a chamada prova que ela NEGA.
      💰 Rota de escrita não entra em (B): dinheiro que sai não se testa por happy-path.

⚠️ **(A) e (B) NÃO medem a mesma coisa, e foi provando o vermelho que isso apareceu.** Com
o gate apagado do arquivo, (A) acusou 17 rotas e (B) continuou **verde**: (A) lê o código
que está no DISCO, (B) fala com o processo que está RODANDO, e o processo só carrega o
arquivo novo depois do bake. Quem rodar só (B) num deploy pendente vê o gate do código
ANTIGO e conclui que o novo está fechado. Nenhuma das duas sozinha responde a pergunta.

O usuário de (B) é resolvido por PAPEL — "um ativo, sem `all`, sem `module:dp`, que não
seja o CEO" — e nunca por e-mail. Quatro oráculos quebraram em 11/08 por hardcodar o
e-mail de alguém que saiu da empresa.

Receita:
  docker exec -e PYTHONPATH=/app conecta-pro-backend \\
    python3 /app/scripts/orq/test_oraculo_rbac_folha.py
"""
from __future__ import annotations

import asyncio
import logging
import sys

sys.path.insert(0, "/app")
logging.disable(logging.CRITICAL)  # o import do app despeja o boot inteiro no stdout

import httpx  # noqa: E402
from sqlalchemy import text  # noqa: E402

from core.auth.jwt import create_access_token  # noqa: E402
from core.database.session import async_session_factory  # noqa: E402

# O que é "caminho do dinheiro do DP". Por padrão de caminho e não por lista de rotas: uma
# rota nova sob estes prefixos entra na conta sem ninguém lembrar de cadastrá-la aqui.
MARCADORES = ("/dp/payslips", "/dp/payroll", "/hr/payroll")
MODULO = "dp"
BASE = "http://127.0.0.1:8080"
# leitura, e só leitura: é a única que pode ser chamada de verdade sem mexer em dinheiro
ROTA_LEITURA = "/api/v1/people-management/dp/payslips"


def _modulos_exigidos(rota) -> list[str]:
    """Módulos que as dependências da rota exigem, lidos do closure de `requer_modulo`."""
    achados = []
    for dep in getattr(rota, "dependencies", []) or []:
        fn = getattr(dep, "dependency", None)
        if getattr(fn, "__qualname__", "") != "requer_modulo.<locals>._verificar":
            continue
        achados += [c.cell_contents for c in (fn.__closure__ or ())
                    if isinstance(c.cell_contents, str)]
    return achados


async def main() -> int:
    falhas: list[str] = []

    from main_production import app  # noqa: PLC0415 — import caro, só quando roda

    # ── (A) estrutural ───────────────────────────────────────────────────────
    dinheiro = [r for r in app.routes
                if any(m in getattr(r, "path", "") for m in MARCADORES)]
    sem_gate = [r.path for r in dinheiro if MODULO not in _modulos_exigidos(r)]
    print(f"(A) rotas de dinheiro do DP: {len(dinheiro)} · sem gate module:{MODULO}: "
          f"{len(sem_gate)}")
    for p in sem_gate:
        print(f"    ✗ {p}")
    if sem_gate:
        falhas.append(
            f"{len(sem_gate)} rota(s) de dinheiro do DP sem `requer_modulo('{MODULO}')` — "
            f"alcançáveis por qualquer usuário autenticado"
        )
    if not dinheiro:
        falhas.append(
            "NENHUMA rota casou os marcadores de dinheiro do DP. Ou os prefixos mudaram, "
            "ou o app não montou — verde por caminho errado é o pior tipo de verde"
        )

    # ── (B) ponta a ponta, só leitura ────────────────────────────────────────
    async with async_session_factory() as db:
        comum = (await db.execute(text(
            "SELECT id::text, email FROM users "
            "WHERE is_active AND email <> 'jjesus@conectamais.pro' "
            "  AND NOT ('all' = ANY(coalesce(permissions, '{}'))) "
            "  AND NOT ('module:' || :mod = ANY(coalesce(permissions, '{}'))) "
            "ORDER BY email LIMIT 1"
        ), {"mod": MODULO})).first()

    if not comum:
        print("(B) NÃO VERIFICADO: nenhum usuário ativo sem o módulo dp para testar")
        falhas.append("(B) NÃO VERIFICADO — sem usuário comum, a chamada não prova nada")
    else:
        uid, email = comum
        token = create_access_token(uid)
        async with httpx.AsyncClient(base_url=BASE, timeout=20) as cli:
            anon = await cli.get(ROTA_LEITURA)
            logado = await cli.get(ROTA_LEITURA, headers={"Authorization": f"Bearer {token}"})
        print(f"(B) {ROTA_LEITURA}: sem token {anon.status_code} · "
              f"{email} {logado.status_code}")
        if anon.status_code != 401:
            falhas.append(f"(B) sem token devolveu {anon.status_code}, esperado 401")
        if logado.status_code != 403:
            falhas.append(
                f"(B) perfil comum ({email}) devolveu {logado.status_code}, esperado 403 — "
                f"a dependência está pendurada mas NÃO está negando"
            )

    if falhas:
        for f in falhas:
            print(f"FALHA: {f}")
        print("TEST oraculo_rbac_folha FAIL")
        return 1
    print("TEST oraculo_rbac_folha PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
