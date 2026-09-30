#!/usr/bin/env python3
"""Oráculo: o `request_id` que volta no erro TEM de achar a linha na trilha.

O QUE ACONTECEU (BUG-09, 30/09/2026)
O conector MCP manda `X-Request-ID` em toda chamada, com um comentário no código dizendo
que é «para `consultar_auditoria(request_id=...)` ter o que achar». Do lado do servidor:

  · ninguém lia o cabeçalho
  · `crm_audit_log` não tinha a coluna
  · `GET /crm/audit` ACEITAVA o parâmetro `request_id` e NÃO o usava no WHERE —
    devolvia a trilha inteira com HTTP 200

Resultado: o Jordan recebia «{"codigo":"ERRO_INTERNO","mensagem":"Internal Server Error"}»
com um `req_28235eb2338d9573`, e não havia NADA com esse número deste lado. Seis 500 do
`criar_proposta` em 30/09 morreram assim.

O DEFEITO MAIS CARO AQUI NÃO É A COLUNA QUE FALTAVA — é o parâmetro aceito e ignorado.
Uma rota que recusa `request_id` faz alguém investigar em 5 minutos. Uma rota que o aceita
e devolve 200 com a lista inteira faz todo mundo acreditar que a correlação funciona.

A REGRA AFIRMADA, ponta a ponta:
  1. resposta de erro carrega um `request_id`
  2. esse mesmo id está na trilha
  3. filtrar por ele devolve MENOS linhas do que não filtrar (senão o filtro é decorativo)
  4. um id que não existe devolve ZERO (senão o filtro é decorativo de outro jeito)
"""

import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

import httpx  # noqa: E402

BASE = "http://127.0.0.1:8080/api/v1"


async def _token() -> str | None:
    """Assina o JWT em processo. Não faz login: o rate limit de auth é 5/min, e senha
    literal em arquivo do repositório é achado do `detect-secrets` — com razão."""
    from sqlalchemy import text

    from core.auth.jwt import create_access_token
    from core.database import async_session_factory

    async with async_session_factory() as db:
        uid = (
            await db.execute(text("SELECT id::text FROM users WHERE email='jjesus@conectamais.pro' LIMIT 1"))
        ).scalar()
    return create_access_token(subject=uid) if uid else None


async def main() -> int:
    falhas: list[str] = []
    async with httpx.AsyncClient(timeout=30) as c:
        token = await _token()
        if not token:
            print("FALHOU: sem token — o oráculo não tem como provar")
            return 1
        h = {"Authorization": f"Bearer {token}"}

        rid = f"orq_{uuid.uuid4().hex[:16]}"
        # Uma escrita que RECUSA de propósito: precisa ser auditada e carimbada, e recusar
        # não pode sujar a base.
        await c.post(
            f"{BASE}/crm/oportunidades/do-cliente",
            headers={**h, "X-Request-ID": rid},
            json={"cliente": "CLIENTE-QUE-NAO-EXISTE-ORACULO", "titulo": "x"},
        )
        await asyncio.sleep(3)

        filtrado = (await c.get(f"{BASE}/crm/audit", headers=h, params={"request_id": rid})).json()
        inteiro = (await c.get(f"{BASE}/crm/audit", headers=h, params={"limite": 50})).json()
        inexistente = (
            await c.get(f"{BASE}/crm/audit", headers=h, params={"request_id": f"nao_existe_{uuid.uuid4().hex}"})
        ).json()

        if filtrado.get("total", 0) < 1:
            falhas.append(f"a chamada carimbada com {rid} não apareceu na trilha")
        else:
            print(f"ok    a chamada com request_id aparece na trilha ({filtrado['total']})")

        if filtrado.get("total", 0) >= inteiro.get("total", 0):
            falhas.append(
                f"filtrar por request_id devolveu {filtrado.get('total')} e sem "
                f"filtro {inteiro.get('total')} — o filtro é decorativo"
            )
        else:
            print(f"ok    filtrar reduz: {filtrado['total']} × {inteiro['total']} sem filtro")

        if inexistente.get("total", 0) != 0:
            falhas.append(
                f"request_id inexistente devolveu {inexistente.get('total')} linha(s) — o filtro não está no WHERE"
            )
        else:
            print("ok    request_id inexistente devolve ZERO")

        ev = (filtrado.get("eventos") or [{}])[0]
        if ev.get("request_id") != rid:
            falhas.append(f"a linha veio sem o request_id de volta: {ev.get('request_id')!r}")
        else:
            print("ok    a linha devolve o request_id, para conferir sem adivinhar")

        # 4) o cabeçalho volta SEMPRE, inclusive quando quem chamou não mandou nenhum:
        # é o que permite ao dono citar um número mesmo vindo do navegador.
        resp = await c.get(f"{BASE.rsplit('/api', 1)[0]}/health")
        if not resp.headers.get("x-request-id"):
            falhas.append("resposta sem cabeçalho X-Request-ID — quem não manda id fica sem um")
        else:
            print(f"ok    resposta carrega X-Request-ID mesmo sem pedir ({resp.headers['x-request-id'][:14]}…)")

    print()
    if falhas:
        print(f"VEREDITO: {len(falhas)} falha(s)")
        for f in falhas:
            print("  -", f)
        return 1
    print("VEREDITO: o número no erro acha a linha na trilha, e o filtro filtra de verdade")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
