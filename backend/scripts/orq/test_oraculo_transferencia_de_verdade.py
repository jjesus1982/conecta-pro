"""Oráculo — quando o José Luís DIZ que vai transferir, a conversa foi mesmo entregue (11/09/2026).

Decisão do Jordan, 11/09: *"quando disser que vai transferir pra mim, pra Pyetra, pro Gonzaga ou
pro Paiva que realmente transfira a conversa na íntegra, não apenas diga a quem está na conversa
que vai transferir, mas que transfira de fato, e cada um de acordo com sua competência"*.

Estado medido no dia em que este oráculo nasceu: das 5 conversas em que o agente disse "vou te
encaminhar", 4 tinham marcador de transferência e 1 não — a do Rilem, hoje às 15:17, um
funcionário que ouviu "já vou te encaminhar pra eles" sobre o código do ponto e ficou esperando
alguém que nunca foi avisado. Além dessa, operacional/administrativo/DP/RH nem tinham destinatário:
a "transferência" era uma atribuição a um time do Chatwoot que ninguém abre.

Quatro afirmações, e nenhuma delas é uma cópia da lista que ela vigia:

  1. Todo setor que a FERRAMENTA oferece tem dono em `transferencia.RESPONSAVEIS`. Ler o `enum`
     da tool e afirmá-lo contra o mapa é o ponto — dois vocabulários para a mesma coisa foi o que
     fez a política de assinatura passar verde estando errada (oráculo de 09/09).
  2. A competência é a que o dono falou: operacional → Gonzaga e Paiva · DP e RH → Pyetra ·
     comercial e QUALQUER setor não previsto → Jordan.
  3. Os números são os do CADASTRO. Constante que envelhece manda conversa para o número antigo de
     alguém — em 11/09 foram cinco telefones de funcionário errados no cadastro, um deles apontando
     para outra pessoa.
  4. Promessa cumprida: nenhuma conversa dos últimos 7 dias em que o agente disse "vou te
     encaminhar" está sem marcador `trf`.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import re
import sys

#: O que o dono falou, em código. Nome parcial basta — o oráculo casa por `in`.
COMPETENCIA = {
    "operacional": ["Gonzaga", "Paiva"],
    "dp": ["Pyetra"],
    "rh": ["Pyetra"],
    "comercial": ["Jordan"],
    "administrativo": ["Jordan"],
    "suporte_tecnico": ["Pedro"],
}
#: setor que ninguém previu NÃO fica órfão — "comercial e demais demandas é comigo".
NAO_PREVISTOS = ("juridico", "financeiro", "", "qualquer_coisa")

#: A mesma régua do relatório acima. `\y` é a fronteira de palavra do POSIX (o `\b` não casa).
SQL_PROMETEU = """
WITH p AS (
  SELECT chatwoot_conversation_id c, min(created_at) q FROM cwi_message_log
  WHERE direction='out' AND chatwoot_conversation_id IS NOT NULL
    AND created_at > now() - interval '7 days'
    AND content ~* '\\y(vou|irei|estou)\\s+(j[áa]\\s+)?(te\\s+|lhe\\s+)?(encaminh|transferi|passa)'
  GROUP BY 1)
SELECT p.c, to_char(p.q,'DD/MM HH24:MI'),
       (SELECT phone_canonical FROM cwi_message_log x
         WHERE x.chatwoot_conversation_id=p.c AND phone_canonical IS NOT NULL LIMIT 1)
FROM p WHERE NOT EXISTS (
  SELECT 1 FROM cwi_message_log t WHERE t.chatwoot_conversation_id=p.c AND t.direction='trf')
ORDER BY p.q
"""


def _dig(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db
    from modules.integrations.connectors.whatsapp import agent_service as ag
    from modules.integrations.connectors.whatsapp.transferencia import RESPONSAVEIS, responsaveis

    falhas: list[str] = []

    # 1) todo setor que a FERRAMENTA oferece tem dono
    enum_da_tool: list[str] = []
    for t in ag.TOOLS:
        f = t.get("function", {})
        if f.get("name") == "transferir_conversa":
            enum_da_tool = list(f["parameters"]["properties"]["setor"]["enum"])
    if not enum_da_tool:
        falhas.append("a ferramenta transferir_conversa sumiu da lista de tools — ninguém transfere nada")
    for setor in enum_da_tool:
        if setor not in RESPONSAVEIS:
            falhas.append(f"a ferramenta oferece setor '{setor}' e o mapa de competência não conhece — "
                          f"a conversa cairia no padrão sem ninguém perceber")

    # 2) a competência é a que o dono falou
    for setor, esperados in COMPETENCIA.items():
        nomes = [p["nome"] for p in responsaveis(setor)[1]]
        for quem in esperados:
            if not any(quem in n for n in nomes):
                falhas.append(f"setor '{setor}' deveria ir para {quem} e vai para {nomes}")
        if len(nomes) != len(esperados):
            falhas.append(f"setor '{setor}': esperava {len(esperados)} responsável(is) {esperados}, achei {nomes}")
    for setor in NAO_PREVISTOS:
        nomes = [p["nome"] for p in responsaveis(setor)[1]]
        if not any("Jordan" in n for n in nomes):
            falhas.append(f"setor não previsto ('{setor}') não cai no Jordan — vai para {nomes}")

    gen = get_db()
    db = await gen.__anext__()

    # 3) o número é o do cadastro
    vistos: dict[str, str] = {}
    for cfg in RESPONSAVEIS.values():
        for p in cfg["pessoas"]:
            vistos[p["nome"]] = p["whatsapp"]
    for nome, fone in vistos.items():
        # casa por TODAS as palavras do nome, não pelo sobrenome: 'Jesus' sozinho casa com o
        # Jordan e com a Pyetra, e 'Paiva'/'Rafael' com duas pessoas cada.
        tokens = [t for t in nome.split() if len(t) > 2]
        onde = " AND ".join(f"nome ILIKE :t{i}" for i in range(len(tokens)))
        par = {f"t{i}": f"%{t}%" for i, t in enumerate(tokens)}
        row = (await db.execute(text(
            "SELECT nome, regexp_replace(coalesce(nullif(celular,''),telefone,''),'[^0-9]','','g') "
            f"FROM employees WHERE {onde} AND coalesce(nullif(celular,''),telefone,'') <> '' LIMIT 2"),
            par)).fetchall()
        if not row:
            falhas.append(f"{nome}: não achei no cadastro (com telefone) — não dá para conferir o número")
            continue
        if len(row) > 1:
            falhas.append(f"{nome}: casa com {len(row)} pessoas no cadastro ({[r[0] for r in row]}) — confira à mão")
            continue
        if _dig(fone)[-8:] != row[0][1][-8:]:
            falhas.append(f"{nome}: a transferência usa …{_dig(fone)[-8:]} e o cadastro de "
                          f"{row[0][0]} diz …{row[0][1][-8:]}")

    # 4) promessa cumprida
    orfas = (await db.execute(text(SQL_PROMETEU))).fetchall()
    for c, quando, fone in orfas:
        falhas.append(f"conversa {c} ({quando}, {fone or 'sem telefone'}): o agente disse que ia "
                      f"encaminhar e NINGUÉM foi avisado — a pessoa está esperando")

    print(f"setores na ferramenta: {len(enum_da_tool)} · com dono: {len(RESPONSAVEIS)} · "
          f"pessoas: {len(vistos)} · promessas sem transferência (7d): {len(orfas)}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na transferência de conversa")
    print("OK transferência: todo setor tem dono, a competência é a do Jordan, os números são os do "
          "cadastro e toda promessa de encaminhar virou transferência")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
