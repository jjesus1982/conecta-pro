#!/usr/bin/env python3
"""Diarista que trabalhou e não tem como receber — e nome fora do padrão da lista.

Origem: 15/09/2026. O Jordan abriu a lista de pagamento de agosto e disse que estava «fora do
padrão». O timbrado, o cabeçalho e o rodapé eram os mesmos de julho — a quebra estava no dado:
a linha 16 saía «Ivanildo Alves Bonates» no meio de 28 nomes em CAIXA ALTA. Sete dos 64
diaristas tinham entrado assim, todos nos cadastros mais recentes: `criar_diarista` fazia
`.strip()` e gravava a caixa como a pessoa digitou.

Isso é cosmético. O que este caçador vigia junto NÃO é: diarista com diária lançada no mês e
sem CPF ou sem chave PIX. Esse não entra no lote — some da lista de pagamento sem nada apitar,
e quem trabalhou fica sem receber. Hoje são 0 de 29, e a intenção é que continue assim.

    python3 backend/scripts/qa/checar_diarista_impagavel.py

Linha canônica: `TOTAL: <n> diarista(s) com problema`. Exit 1 quando há achado.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date

PG = os.environ.get("QA_PG_CONTAINER", "conecta-pro-postgres")
DOCKER = os.environ.get("QA_DOCKER", "/usr/bin/docker")

#: Janela conferida: o mês anterior fechado — o mesmo período que a lista de pagamento usa.
#: Cobrar PIX de quem ainda vai trabalhar este mês seria sino tocando antes da hora.
_HOJE = date.today()
_FIM = _HOJE.replace(day=1) - __import__("datetime").timedelta(days=1)
_INI = _FIM.replace(day=1)


def _sql(q: str) -> list[list[str]]:
    r = subprocess.run(  # noqa: S603
        [DOCKER, "exec", PG, "psql", "-U", "postgres", "-d", "conecta_pro", "-t", "-A", "-F|", "-c", q],
        capture_output=True,
        timeout=120,
        check=False,
    )
    saida = r.stdout.decode("utf8", "ignore").strip()
    return [ln.split("|") for ln in saida.splitlines() if ln.strip()]


def main() -> int:
    impagaveis = _sql(
        "SELECT d.nome, count(*), coalesce(nullif(d.cpf,''),'SEM CPF'), "
        "       coalesce(nullif(d.pix,''),'SEM PIX') "
        "  FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id = l.diarista_id "
        f" WHERE l.status='lancado' AND l.data BETWEEN '{_INI}' AND '{_FIM}' "
        "   AND (coalesce(d.cpf,'')='' OR coalesce(d.pix,'')='') "
        " GROUP BY d.nome, d.cpf, d.pix ORDER BY d.nome;"
    )
    fora_padrao = _sql(
        "SELECT id, nome FROM diaria_diaristas "
        r"WHERE nome <> upper(regexp_replace(btrim(nome), '\s+', ' ', 'g')) ORDER BY nome;"
    )

    print(f"   período conferido: {_INI:%d/%m/%Y} a {_FIM:%d/%m/%Y} (o da lista de pagamento)")
    for nome, qtd, cpf, pix in impagaveis:
        print(f"   IMPAGÁVEL  {nome} — {qtd} diária(s) no mês · cpf={cpf} · pix={pix}")
    for _id, nome in fora_padrao:
        print(f"   fora do padrão da lista  id={_id}  '{nome}' (a lista imprime em CAIXA ALTA)")

    achados = len(impagaveis) + len(fora_padrao)
    print(f"\nTOTAL: {achados} diarista(s) com problema")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
