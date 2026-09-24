"""Oráculo — Painel do dono: decisões pendentes com número ao vivo (DGX X5, 24/09/2026).

**Por que existe.** O painel `decisoes-do-dono` existe para tirar 51 decisões do markdown e pôr
o número de HOJE ao lado de cada uma. Três jeitos de ele mentir, e um de machucar:
  · decisão sem origem ou sem pergunta — vira lembrete vago que ninguém sabe de onde veio;
  · `numero_sql` que não roda, ou que devolve mais de um valor — a coluna «Número de hoje» passa
    a mostrar lixo com cara de número;
  · `numero_sql` que ESCREVE — uma consulta de painel que faz UPDATE é um estrago silencioso,
    em produção, no render de uma tela que o dono abre sozinho;
  · um SQL que quebra derrubando o painel inteiro — aí as outras 50 decisões somem junto.

**O que afirma:**
  1. Toda decisão semeada tem `origem` e `pergunta` (e área/impacto dentro do vocabulário).
  2. Todo `numero_sql` roda contra o banco e devolve UM escalar — ou é nulo DE PROPÓSITO
    (escolha pura), e nesse caso a tela diz «sem número, é escolha».
  3. Nenhum `numero_sql` escreve: varredura por palavra-chave (INSERT/UPDATE/DELETE/CREATE/DROP/
     ALTER/…). Contra-prova: um SQL de escrita inventado aqui TEM de ser recusado.
  4. Decidir grava autor e data e tira a linha da lista de abertas.
  5. O painel não quebra se um SQL falhar: fixture com SQL inválido → a linha aparece como
     «não medido», e o resto das linhas continua lá.

**Estado medido no nascimento (sandbox, 24/09/2026):** a tabela `dono_decisoes` não existia e o
serviço não existia → VERMELHO em tudo (ImportError).

**Como roda** (container efêmero contra o sandbox, PYTHONPATH=/app):
    python3 /app/scripts/orq/test_oraculo_x5_decisoes.py
Sai 0 = verde; 1 = vermelho. Fixtures marcadas 'FIXTURE DGX X5' são apagadas no fim.
"""

from __future__ import annotations

import asyncio
import sys

FIXTURE = "X5FIX"
FIXTURE_MARCA = "FIXTURE DGX X5"

#: SQLs de escrita que o painel NUNCA pode aceitar. A contra-prova do item 3.
ESCRITAS = (
    "UPDATE employees SET nome = 'x'",
    "DELETE FROM dono_decisoes",
    "INSERT INTO dono_decisoes (codigo) VALUES ('x')",
    "DROP TABLE dono_decisoes",
    "ALTER TABLE employees ADD COLUMN zz int",
    "CREATE TABLE zz (a int)",
    "TRUNCATE dono_decisoes",
)

#: SQLs legítimos que a varredura NÃO pode recusar (`created_at`/`updated_at` têm as palavras
#: dentro, e uma coluna chamada `deleted_at` também).
LEGITIMOS = (
    "SELECT count(*) FROM employees WHERE created_at > now() - interval '1 day'",
    "SELECT count(*) FROM employees WHERE updated_at IS NOT NULL",
)


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.operacional.services import dono_decisoes as dd

    falhas: list[str] = []
    medidas: list[tuple[str, object]] = []

    async with async_session_factory() as db:
        await dd.ensure(db)

        # ── 1) origem e pergunta em toda decisão semeada ────────────────────────────────
        linhas = await dd.listar(db, medindo=False)
        semeados = {s[0] for s in dd.SEMENTE}
        if len(linhas) < len(dd.SEMENTE):
            falhas.append(f"semente tem {len(dd.SEMENTE)} e a tabela só trouxe {len(linhas)}")
        for d in linhas:
            if d["codigo"] not in semeados:
                continue  # linha criada por gente, não é responsabilidade da semente
            if not (d["origem"] or "").strip():
                falhas.append(f"{d['codigo']}: sem origem (de qual frente veio?)")
            if len((d["pergunta"] or "").strip()) < 20:
                falhas.append(f"{d['codigo']}: pergunta vazia ou curta demais para decidir")
            if d["area"] not in dd.AREAS:
                falhas.append(f"{d['codigo']}: área «{d['area']}» fora do vocabulário")
            if d["impacto"] not in dd.IMPACTOS:
                falhas.append(f"{d['codigo']}: impacto «{d['impacto']}» fora do vocabulário")
            if d["numero_sql"] and not (d["unidade"] or "").strip():
                falhas.append(f"{d['codigo']}: tem numero_sql e não tem unidade")

        # ── 3) nenhum numero_sql escreve ────────────────────────────────────────────────
        for d in linhas:
            if d["numero_sql"] and dd.proibido(d["numero_sql"]):
                falhas.append(
                    f"{d['codigo']}: numero_sql contém {dd.proibido(d['numero_sql'])} — consulta de painel não escreve"
                )
        for sql in ESCRITAS:
            if not dd.proibido(sql):
                falhas.append(f"varredura deixou passar escrita: {sql[:40]}")
            v, erro = await dd.medir(db, sql)
            if v is not None or not erro:
                falhas.append(f"medir() executou uma escrita: {sql[:40]}")
        for sql in LEGITIMOS:
            if dd.proibido(sql):
                falhas.append(f"varredura recusou consulta legítima: {sql[:60]}")

        # ── 2) todo numero_sql roda e devolve UM escalar ────────────────────────────────
        for d in linhas:
            if not d["numero_sql"]:
                continue
            valor, erro = await dd.medir(db, d["numero_sql"])
            if erro:
                falhas.append(f"{d['codigo']}: numero_sql não rodou — {erro}")
            elif valor is None:
                falhas.append(f"{d['codigo']}: numero_sql devolveu vazio (nem zero)")
            elif isinstance(valor, (list, tuple, dict)):
                falhas.append(f"{d['codigo']}: numero_sql devolveu {type(valor).__name__}, não um escalar")
            else:
                medidas.append((d["codigo"], valor))

        # A medição é só-leitura de verdade: o SAVEPOINT é sempre desfeito. Contra-prova —
        # um SELECT dentro de uma CTE de escrita é recusado antes do banco (item 3), e um
        # SELECT puro não deixa rastro. Aqui provamos que a sessão continua utilizável.
        if (await db.execute(text("SELECT 1"))).scalar() != 1:
            falhas.append("a sessão ficou inutilizável depois das medições")

        # ── 5) SQL inválido → «não medido», e o painel continua de pé ───────────────────
        await db.execute(
            text(
                "INSERT INTO dono_decisoes (codigo, titulo, pergunta, area, origem, impacto, "
                "numero_sql, unidade) VALUES (:c, :t, :p, 'qa', :o, 'risco', "
                "'SELECT count(*) FROM tabela_que_nao_existe_x5', 'itens') "
                "ON CONFLICT (codigo) DO NOTHING"
            ),
            {
                "c": FIXTURE,
                "t": f"{FIXTURE_MARCA} — consulta quebrada de propósito",
                "p": f"{FIXTURE_MARCA}: esta linha existe para provar que um SQL ruim não derruba o painel.",
                "o": FIXTURE_MARCA,
            },
        )
        await db.commit()

        from modules.operacional.controllers.redesign_builders import _dgx_x5_decisoes as x5

        telas = await x5.telas(db)
        painel = telas.get("decisoes-do-dono") or {}
        if painel.get("title", "").endswith("FALHOU"):
            falhas.append(f"o painel caiu por causa do SQL inválido: {painel.get('sub')}")
        rows = painel.get("rows") or []
        if len(rows) < len(linhas):
            falhas.append(f"painel mostra {len(rows)} linha(s) e há {len(linhas) + 1} decisões")
        fix = [r for r in rows if FIXTURE in str(r["cells"][1].get("v", ""))]
        if not fix:
            falhas.append("a linha com SQL inválido sumiu do painel em vez de dizer «não medido»")
        elif fix[0]["cells"][3].get("v") != "não medido":
            falhas.append(f"linha com SQL inválido mostra «{fix[0]['cells'][3].get('v')}», não «não medido»")
        if not telas.get("decisao-registrar"):
            falhas.append("telas() não devolve 'decisao-registrar'")

        # a tela diz «sem número, é escolha» para quem não tem consulta
        sem_sql = {d["codigo"] for d in linhas if not d["numero_sql"]}
        if sem_sql:
            um = sorted(sem_sql)[0]
            linha = next((r for r in rows if str(r["cells"][1].get("v", "")).startswith(um)), None)
            if not linha:
                falhas.append(f"{um}: decisão sem número não aparece no painel")
            elif linha["cells"][3].get("v") != "sem número, é escolha":
                falhas.append(f"{um}: decisão sem consulta mostra «{linha['cells'][3].get('v')}»")

        # ── 4) decidir grava autor e data e tira da lista de abertas ────────────────────
        antes = [d["codigo"] for d in await dd.listar(db, medindo=False) if d["status"] == "aberta"]
        if FIXTURE not in antes:
            falhas.append("a fixture nasceu fora de «aberta»")
        await dd.decidir(db, FIXTURE, "decidido pelo oráculo", "oraculo@x5", "decidida")
        depois = {d["codigo"]: d for d in await dd.listar(db, medindo=False)}
        reg = depois.get(FIXTURE) or {}
        if reg.get("status") != "decidida":
            falhas.append(f"decidir() deixou o status em «{reg.get('status')}»")
        if reg.get("decidida_por") != "oraculo@x5":
            falhas.append(f"decidir() não gravou o autor (gravou «{reg.get('decidida_por')}»)")
        if not reg.get("decidida_em"):
            falhas.append("decidir() não gravou a data")
        if reg.get("decisao") != "decidido pelo oráculo":
            falhas.append("decidir() não gravou o texto da decisão")
        if FIXTURE in [d["codigo"] for d in depois.values() if d["status"] == "aberta"]:
            falhas.append("decidir() não tirou a linha da lista de abertas")
        try:
            await dd.decidir(db, FIXTURE, "", "oraculo@x5", "decidida")
            falhas.append("decidir() aceitou decisão em branco")
        except dd.DecisaoErro:
            pass
        try:
            await dd.decidir(db, "NAOEXISTE", "x", "oraculo@x5", "decidida")
            falhas.append("decidir() aceitou código inexistente")
        except dd.DecisaoErro:
            pass

        # ── limpeza das fixtures ────────────────────────────────────────────────────────
        await db.execute(text("DELETE FROM dono_decisoes WHERE origem = :m"), {"m": FIXTURE_MARCA})
        await db.commit()
        sobrou = (
            await db.execute(text("SELECT count(*) FROM dono_decisoes WHERE origem = :m"), {"m": FIXTURE_MARCA})
        ).scalar()
        if sobrou:
            falhas.append(f"{sobrou} fixture(s) '{FIXTURE_MARCA}' ficaram no banco")

    print(
        f"decisões semeadas: {len(dd.SEMENTE)} · com número: {len(medidas)} · sem número (escolha): "
        f"{len(dd.SEMENTE) - len([s for s in dd.SEMENTE if s[6]])}"
    )
    for codigo, valor in medidas:
        print(f"  · {codigo}: {valor}")
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL desvios no painel de decisões: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no painel do dono")
    print(
        "OK painel do dono: origem e pergunta em todas, todo numero_sql mede um escalar, "
        "nenhum escreve, decidir grava autor e data, SQL ruim vira «não medido»"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
