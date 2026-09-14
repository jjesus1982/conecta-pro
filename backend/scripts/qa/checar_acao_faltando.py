#!/usr/bin/env python3
"""Tela que LISTA e não deixa MEXER — o mapa do que obriga o dono a ir ao terminal.

Origem (13/09/2026, pedido do Jordan): «percebi vários botões, funções e recursos que
deveriam ter para incluir, baixar, excluir, adicionar etc, isso em todos os módulos,
tanto que todas as vezes tive que recorrer ao terminal». O caso que abriu a conversa foi
CLIENTE: dá para criar contato, proposta, contrato, comissão, produto e condomínio — e
não dá para criar um cliente. Um cliente novo nunca vira proposta sem `psql`.

O caçador varre os 13 módulos pela MESMA porta que a tela usa
(`GET /api/v1/redesign/data/<slug>`), resolve as abas e classifica cada tela de lista:

  • SEM CRIAR  — a lista existe, mas não há nenhum formulário no módulo que grave nessa
                 entidade. É o caso do cliente: só leitura, para sempre.
  • SEM MEXER  — a lista existe e as linhas não têm ação nenhuma (nem ver, nem editar,
                 nem excluir). Quem precisa corrigir uma linha vai ao banco.

O que NÃO é achado, de propósito: painel de indicador, extrato de origem externa (banco,
fisco, governo) e tela que já declara `cta: "—"` porque a entidade nasce de outro fluxo.
Acusar essas seria sino tocando todo dia — e sino que toca sempre ninguém lê.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/qa/checar_acao_faltando.py            # resumo
    ... checar_acao_faltando.py --detalhe                          # lista tela a tela

Linha canônica: `TOTAL: <n> tela(s) de lista sem ação`. Exit 1 quando há achado.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

#: Os 13 módulos do ERP, pelos slugs que a tela usa.
MODULOS = [
    "operacional", "dp", "rh", "ponto", "financeiro", "fiscal-contabil", "ged",
    "inteligencia", "negocios", "saude-ocupacional", "portais", "equipamentos",
    "administrativo", "portal-do-funcionario",
]

#: Lista que é PAINEL ou ESPELHO de fonte externa: ninguém cria linha ali pela tela, e
#: exigir "Adicionar" seria pedir para fabricar dado que vem de fora.
PADRAO_SO_LEITURA = re.compile(
    r"extrato|saldo|painel|dashboard|visao|visão|indicador|kpi|resumo|ranking|"
    r"historico|histórico|auditoria|log|espelho|conciliac|conciliaç|"
    r"recebidos|arrecad|obrigac|obrigaç|certid|debito|débito|ecac|sefaz|esocial|"
    r"calendario|calendário|alerta|pendencia|pendência|fila|monitor|mapa-de-|"
    r"cobertura|previsao|previsão|forecast|margem|rentabilidade|runway",
    re.I,
)

#: Verbo de gravação no endpoint de um formulário → a que entidade ele pertence.
def _entidade(texto: str) -> set[str]:
    """Palavras significativas de um id/endpoint, para casar lista com formulário."""
    bruto = re.split(r"[^a-zà-ú0-9]+", (texto or "").lower())
    ruido = {
        "", "api", "v1", "redesign", "action", "data", "novo", "nova", "criar", "cadastrar",
        "editar", "excluir", "registrar", "lancar", "lançar", "adicionar", "incluir", "de",
        "do", "da", "por", "em", "no", "na", "com", "sem", "id", "operacional", "modulos",
    }
    return {p.rstrip("s") for p in bruto if p not in ruido and len(p) > 3}


#: Durante um blue/green o tráfego alterna entre 8080 e 8081. Fixar uma porta faz o
#: caçador falhar por 15 minutos a cada deploy — e falha intermitente vira ruído ignorado.
PORTAS = (8080, 8081)
_base: list[str] = []


async def _api(caminho: str, token: str | None = None, dados: dict | None = None):
    import httpx  # noqa: PLC0415

    ultimo: Exception | None = None
    for base in (_base or [f"http://127.0.0.1:{p}" for p in PORTAS]):
        try:
            async with httpx.AsyncClient(timeout=120) as c:
                if dados is not None:
                    r = await c.post(
                        base + caminho, data=dados,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                else:
                    r = await c.get(base + caminho, headers={"Authorization": f"Bearer {token}"})
                r.raise_for_status()
                if not _base:
                    _base.append(base)
                return r.json()
        except Exception as e:  # noqa: BLE001
            ultimo = e
    raise ultimo  # type: ignore[misc]


async def _screens(slug: str, token: str) -> dict:
    return (await _api(f"/api/v1/redesign/data/{slug}", token)).get("screens") or {}


def _achatar(screens: dict) -> dict[str, dict]:
    """Resolve `tabs` e devolve {id: tela} com todas as telas reais do módulo."""
    plano: dict[str, dict] = {}
    for k, v in screens.items():
        if not isinstance(v, dict):
            continue
        if v.get("type") == "tabs":
            for aba in v.get("tabs") or []:
                tela = aba.get("screen")
                if isinstance(tela, dict):
                    plano[aba.get("id") or f"{k}:{len(plano)}"] = tela
        elif v.get("type") != "redirect":
            plano[k] = v
    return plano


async def _token() -> str:
    u = os.getenv("QA_USER", "jjesus@conectamais.pro")
    p = os.getenv("QA_PASS", "")
    if not p:
        raise SystemExit("RECUSO: defina QA_PASS — o caçador não carrega senha no código")
    return (await _api("/api/v1/auth/login", dados={"username": u, "password": p}))["access_token"]


async def main() -> int:
    detalhe = "--detalhe" in sys.argv
    token = await _token()

    sem_criar: list[tuple[str, str, str]] = []
    sem_mexer: list[tuple[str, str, str]] = []
    total_listas = 0

    for slug in MODULOS:
        try:
            plano = _achatar(await _screens(slug, token))
        except Exception as e:  # noqa: BLE001
            print(f"   ! {slug}: não respondeu — {type(e).__name__}: {e}")
            continue

        # Tudo que GRAVA neste módulo: id do formulário + endpoint de submit.
        grava: set[str] = set()
        for k, v in plano.items():
            sub = v.get("submit") or {}
            if v.get("type") == "form" or sub.get("endpoint"):
                grava |= _entidade(k) | _entidade(sub.get("endpoint", ""))
            for linha in v.get("rows") or []:
                for a in (linha or {}).get("actions") or []:
                    grava |= _entidade((a or {}).get("endpoint", ""))

        for k, v in plano.items():
            if v.get("type") != "table":
                continue
            titulo = v.get("title") or k
            if PADRAO_SO_LEITURA.search(k) or PADRAO_SO_LEITURA.search(titulo):
                continue
            total_listas += 1
            linhas = v.get("rows") or []
            tem_acao = any((linha or {}).get("actions") or (linha or {}).get("edit") for linha in linhas)
            if linhas and not tem_acao:
                sem_mexer.append((slug, k, titulo))
            if not (_entidade(k) & grava):
                sem_criar.append((slug, k, titulo))

    if detalhe:
        print("=== LISTA SEM COMO CRIAR ===")
        for slug, k, titulo in sem_criar:
            print(f"   {slug:<20} {k:<34} {titulo}")
        print("\n=== LISTA SEM AÇÃO NA LINHA (ver/editar/excluir) ===")
        for slug, k, titulo in sem_mexer:
            print(f"   {slug:<20} {k:<34} {titulo}")
        print()

    por_modulo: dict[str, int] = {}
    for slug, _, _ in sem_criar + sem_mexer:
        por_modulo[slug] = por_modulo.get(slug, 0) + 1
    for slug, n in sorted(por_modulo.items(), key=lambda x: -x[1]):
        print(f"   {n:3}  {slug}")

    print(f"\n   {total_listas} lista(s) examinada(s) · "
          f"{len(sem_criar)} sem como criar · {len(sem_mexer)} sem ação na linha")
    total = len(sem_criar) + len(sem_mexer)
    print(f"\nTOTAL: {total} tela(s) de lista sem ação")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
