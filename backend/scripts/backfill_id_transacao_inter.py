"""Preenche `inter_transactions.id_transacao` com o id do próprio Inter.

Por que existe: a chave de deduplicação da origem era (data, tipo, valor, DESCRIÇÃO), e o
Inter muda o texto entre importações — a mesma transação entrava duas vezes e o saldo
divergia R$1.999,34 do que o banco informa.

⚠️ Trocar o endpoint SEM fazer isto já falhou: em 14/08/2026 o `/extrato` virou
`/extrato/completo` e o sync duplicou 47 linhas, porque o `completo` devolve a descrição
noutro formato e a descrição era a chave. A ordem certa é: primeiro dar identidade às
linhas que já existem, depois trocar a chave, só então trocar o endpoint.

⭐ O pareamento ADJUDICA as duplicatas de quebra. Para cada (data, valor, direção), o banco
tem N lançamentos e a origem tem M linhas. Emparelhando na ordem, sobra M−N sem id — e
essas são exatamente as cópias que ninguém deveria ter criado. Nada é apagado aqui: o
script só marca. Apagar linha de extrato é passo separado, com o oráculo conferindo.

Uso:
    python scripts/backfill_id_transacao_inter.py --de 2026-01-01 --ate 2026-08-23
    python scripts/backfill_id_transacao_inter.py --de ... --ate ... --aplicar
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from collections import defaultdict
from datetime import date, timedelta

sys.path[0] = str(pathlib.Path(__file__).resolve().parents[1])

from sqlalchemy import text  # noqa: E402

#: Janela por chamada. O Inter limita requisições (429 depois de poucas dezenas), então
#: pedir mês a mês gasta 8 chamadas em vez de 235.
DIAS_POR_CHAMADA = 31


async def _extrato_completo(ad, inicio: date, fim: date) -> list[dict]:
    """`/extrato/completo` — é o único que traz `idTransacao`.

    ⚠️ PAGINADO, 50 por página. A primeira versão deste script lia só a primeira e todas
    as janelas devolviam exatamente 50 — número redondo demais para ser coincidência, e
    foi o que denunciou. Se tivesse rodado com `--aplicar`, teria marcado 2.566 linhas
    REAIS como cópia, porque o resto do extrato simplesmente não foi lido.
    A resposta traz `totalPaginas`/`totalElementos`: usar isso, não confiar no tamanho.
    """
    c = await ad._get_client()
    tok = (getattr(ad, "_token", None) or getattr(ad, "access_token", None)
           or getattr(ad, "_access_token", None))
    itens: list[dict] = []
    pagina = 0
    while True:
        # O Inter devolve 429 depois de poucas dezenas de chamadas seguidas, e o backfill
        # de 8 meses precisa de ~40 páginas. Espera crescente em vez de desistir: parar no
        # meio deixaria o extrato pela metade, que é pior que demorar.
        for tentativa in range(6):
            r = await c.get("/banking/v2/extrato/completo",
                            headers={"Authorization": f"Bearer {tok}"},
                            params={"dataInicio": inicio.isoformat(), "dataFim": fim.isoformat(),
                                    "pagina": pagina, "tamanhoPagina": 50},
                            timeout=90)
            if r.status_code != 429:
                break
            espera = 20 * (tentativa + 1)
            print(f"    (429 — esperando {espera}s)", flush=True)
            await asyncio.sleep(espera)
        if r.status_code != 200:
            raise RuntimeError(f"extrato/completo {inicio}..{fim} p{pagina}: "
                               f"HTTP {r.status_code} {r.text[:120]}")
        await asyncio.sleep(1.5)   # respiro entre páginas, para não provocar o teto
        d = r.json() or {}
        itens.extend(d.get("transacoes") or [])
        total = int(d.get("totalPaginas") or 1)
        if d.get("ultimaPagina") or pagina >= total - 1:
            # Conferência explícita: se a soma não bater com o que o banco DECLARA, é
            # melhor estourar do que seguir com extrato pela metade.
            declarado = int(d.get("totalElementos") or len(itens))
            if len(itens) != declarado:
                raise RuntimeError(f"{inicio}..{fim}: li {len(itens)} de {declarado} "
                                   f"declarados pelo banco — paginação incompleta")
            return itens
        pagina += 1


async def main(inicio: date, fim: date, aplicar: bool) -> None:
    import os as _os

    from core.database.session import SyncSessionLocal
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    db = SyncSessionLocal()
    ad = InterAdapter(BankCredentials(
        client_id=_os.getenv("INTER_CLIENT_ID", ""), client_secret=_os.getenv("INTER_CLIENT_SECRET", ""),
        certificate_path=_os.getenv("INTER_CERT_PATH"), private_key_path=_os.getenv("INTER_KEY_PATH"),
        environment="production"))
    await ad.authenticate()

    # ── 1. o banco, em janelas ────────────────────────────────────────────────
    do_banco: dict[tuple, list[str]] = defaultdict(list)
    total_banco = 0
    d = inicio
    while d <= fim:
        ate = min(d + timedelta(days=DIAS_POR_CHAMADA - 1), fim)
        itens = await _extrato_completo(ad, d, ate)
        total_banco += len(itens)
        for t in itens:
            chave = (str(t.get("dataTransacao") or t.get("dataEntrada")),
                     round(float(t["valor"]), 2), str(t.get("tipoOperacao")))
            if t.get("idTransacao"):
                do_banco[chave].append(str(t["idTransacao"]))
        print(f"  banco {d}..{ate}: {len(itens)} lançamentos", flush=True)
        d = ate + timedelta(days=1)

    # ── 2. a origem ───────────────────────────────────────────────────────────
    linhas = db.execute(text("""
        SELECT id, data_lancamento, valor, tipo_operacao, id_transacao, created_at
          FROM inter_transactions
         WHERE data_lancamento BETWEEN :i AND :f
         ORDER BY data_lancamento, valor, tipo_operacao, created_at
    """), {"i": inicio, "f": fim}).mappings().all()

    da_origem: dict[tuple, list[dict]] = defaultdict(list)
    for ln in linhas:
        da_origem[(str(ln["data_lancamento"]), round(float(ln["valor"]), 2),
                   str(ln["tipo_operacao"]))].append(dict(ln))

    # ── 3. parear na ordem; o que sobrar da origem é cópia ────────────────────
    casados, sobra_origem, sobra_banco = [], [], 0
    for chave, ids in do_banco.items():
        nossas = da_origem.get(chave, [])
        for i, ln in enumerate(nossas):
            if i < len(ids):
                casados.append((ln["id"], ids[i]))
            else:
                # Mais linhas nossas que lançamentos no banco: as excedentes são as cópias
                # que a chave por descrição deixou entrar.
                sobra_origem.append(ln)
        if len(ids) > len(nossas):
            sobra_banco += len(ids) - len(nossas)

    # Grupo que só existe do nosso lado: nem o banco conhece. Também é cópia (ou lixo).
    for chave, nossas in da_origem.items():
        if chave not in do_banco:
            sobra_origem.extend(nossas)

    print(f"\n  banco: {total_banco} lançamentos | origem: {len(linhas)} linhas")
    print(f"  pareadas (ganham id): {len(casados)}")
    print(f"  sobra da ORIGEM (cópias, ficam sem id): {len(sobra_origem)}")
    print(f"  sobra do BANCO (faltam em nós): {sobra_banco}")

    if not aplicar:
        print("\n  [simulação] nada gravado. Use --aplicar para escrever os ids.")
        return

    gravados = 0
    for linha_id, id_tx in casados:
        r = db.execute(text(
            "UPDATE inter_transactions SET id_transacao = :t, updated_at = NOW() "
            "WHERE id = :i AND id_transacao IS NULL "
            # O índice único já barraria, mas conflito no meio de um laço aborta a
            # transação inteira no Postgres. Melhor não tentar do que capturar.
            "  AND NOT EXISTS (SELECT 1 FROM inter_transactions x WHERE x.id_transacao = :t)"
        ), {"t": id_tx, "i": linha_id})
        gravados += r.rowcount
    db.commit()
    print(f"\n  ids gravados: {gravados}")
    print(f"  linhas sem id (cópias a conferir): {len(sobra_origem)}")


if __name__ == "__main__":
    args = sys.argv
    de = date.fromisoformat(args[args.index("--de") + 1]) if "--de" in args else date(2026, 1, 1)
    ate = date.fromisoformat(args[args.index("--ate") + 1]) if "--ate" in args else date.today()
    asyncio.run(main(de, ate, "--aplicar" in args))
