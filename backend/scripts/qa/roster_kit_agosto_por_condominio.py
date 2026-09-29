"""Quem entra no kit de AGOSTO, por condomínio. READ-ONLY — não escreve nada.

Decisões do Jordan em 28/09/2026:
  · "faz os kits individual por condomínio"
  · "o kit de setembro com o mês de competência sendo agosto"
  · "green hills iniciamos lá dia 1 de setembro" → **fora do kit de agosto**, entra em outubro
  · "rilem e mauricio hoje estão no green hills" → em AGOSTO estavam em Prime Arena e Mirante

## A âncora é o posto gravado NA BATIDA. Três fontes foram descartadas, cada uma por medição

1. **`employee_alocacoes` não serve como histórico.** Diz onde a pessoa está HOJE. Medido: a
   alocação do RILEM ao GREEN HILLS traz `data_inicio = 2026-01-01` e a do MAURICIO
   `2026-03-01` — num condomínio que **começou em 01/09**. ⭐ As datas são ficção; usá-las
   importa o condomínio de hoje para dentro de agosto.

2. **`shifts` perde gente em silêncio.** Descobrir o condomínio atravessando a escala deixa de
   fora quem bateu sem turno lançado: medido, 4 pessoas com **84, 57, 49 e 33 batidas** em
   agosto e nenhum turno. Elas sairiam caladas do kit do cliente.

3. **`employees.status` não serve como população.** Diz 66 ativos e **nenhum tem data de
   demissão** — 13 saídas nunca foram registradas.

Sobra `gp_clock_punches.posto_id`, gravado no momento do fato: resolve **60 de 63** pessoas que
bateram em agosto. As 3 restantes não têm posto em NENHUMA batida, e para elas a única fonte
legítima é o Jordan — está em `RESOLVIDO_PELO_JORDAN`, com data. Adivinhar pela alocação
repetiria o erro do Green Hills.

⚠️ `Conecta Village` é posto da PRÓPRIA CONECTAMAIS ELETRONICA. Doze pessoas trabalhavam lá e a
operação encerrou em 31/08 (zero turnos em setembro nos 6 postos). Têm documento de agosto e
**não pertencem a kit de cliente nenhum** — pedir o kit por condomínio já as exclui sozinho.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

COMP_INI, COMP_FIM = "2026-08-01", "2026-09-01"
#: Postos da própria empresa. O kit é documento do CLIENTE — o que é nosso não entra.
CASA = "CONECTAMAIS ELETRONICA LTDA"

#: Quem bateu em agosto e NÃO tem posto em nenhuma batida. Resolvido pelo Jordan em 28/09/2026,
#: perguntado nominalmente. É a única fonte aceitável: o dado não sabe, e a alocação MENTE
#: (provado no Green Hills). Chave = nome exato em `employees.nome`.
RESOLVIDO_PELO_JORDAN: dict[str, str] = {
    "KELLY PATRICIA DA SILVA DE SOUZA": "Condomínio Ideal Flores da Cidade",
    # "keyson foi demitido em agosto" — em agosto tinha 48 turnos no Prime Arena
    "KEYSON DA SILVA PINTO": "Condomínio Prime Arena",
    # "eidy estava de férias" — férias APROVADAS de 07/08 a 05/09, registradas no sistema;
    # trabalhou de 01 a 06/08. "estava no villa dei fiori"
    "EIDY CULIER DE CASTRO": "Condomínio Villa Dei Fiori",
}


def roster_por_condominio(db) -> tuple[dict[str, set[str]], dict[str, str]]:
    """`({condomínio: {employee_id}}, {employee_id: nome})` — a FONTE ÚNICA do roster.

    Existe como função, e não só dentro do `main`, porque `reconciliar_kit_agosto.py` precisa
    exatamente desta lista. Duas cópias da regra divergem na primeira mudança — e esta regra já
    mudou três vezes hoje (alocação → escala → posto da batida), cada uma por uma correção do
    Jordan. Uma cópia só não tem como ficar atrás.
    """
    por_cond: dict[str, set[str]] = {}
    nomes: dict[str, str] = {}
    for r in db.execute(
        text(
            "SELECT DISTINCT p.employee_id::text AS eid, e.nome, po.name AS cond "
            "  FROM gp_clock_punches p "
            "  JOIN employees e ON e.id = p.employee_id "
            "  JOIN posts po ON po.id::text = p.posto_id "
            "  JOIN clients c ON c.id = po.client_id "
            " WHERE p.punch_timestamp >= :i AND p.punch_timestamp < :f AND c.name <> :casa"
        ),
        {"i": COMP_INI, "f": COMP_FIM, "casa": CASA},
    ).mappings():
        por_cond.setdefault(r["cond"], set()).add(r["eid"])
        nomes[r["eid"]] = r["nome"]
    for nome, cond in RESOLVIDO_PELO_JORDAN.items():
        eid = db.execute(text("SELECT id::text FROM employees WHERE nome = :n"), {"n": nome}).scalar()
        assert eid, f"«{nome}» não existe em employees — confira o nome antes de montar o kit"
        por_cond.setdefault(cond, set()).add(eid)
        nomes[eid] = nome
    return por_cond, nomes


def main() -> None:
    with get_sync_db() as db:
        # A + B — uma fonte só, compartilhada com `reconciliar_kit_agosto.py`.
        por_cond, nomes = roster_por_condominio(db)

        # C — quem bateu em agosto e continua sem condomínio: aparece, nunca desaparece.
        todos_ago = {
            r[0]: r[1]
            for r in db.execute(
                text(
                    "SELECT DISTINCT p.employee_id::text, e.nome FROM gp_clock_punches p "
                    "  JOIN employees e ON e.id = p.employee_id "
                    " WHERE p.punch_timestamp >= :i AND p.punch_timestamp < :f"
                ),
                {"i": COMP_INI, "f": COMP_FIM},
            ).all()
        }
        na_casa = {
            r[0]
            for r in db.execute(
                text(
                    "SELECT DISTINCT p.employee_id::text FROM gp_clock_punches p "
                    "  JOIN posts po ON po.id::text = p.posto_id JOIN clients c ON c.id = po.client_id "
                    " WHERE p.punch_timestamp >= :i AND p.punch_timestamp < :f AND c.name = :casa"
                ),
                {"i": COMP_INI, "f": COMP_FIM, "casa": CASA},
            ).all()
        }
        colocados = {e for v in por_cond.values() for e in v}
        orfaos = {e: n for e, n in todos_ago.items() if e not in colocados and e not in na_casa}

        # D — quanto de agosto é MEDIÇÃO. O espelho só conta as fontes medidas; o Tangerino
        #     traz a GRADE da escala (65% em hora cheia em agosto) e o `web`, 4 horários
        #     distintos para 414 batidas. Isto não é defeito: é dia que nunca foi medido.
        med = db.execute(
            text(
                "SELECT count(*) AS total, "
                "  count(*) FILTER (WHERE lower(coalesce(device_type,'')) IN "
                "    ('mobile','contingencia','facial','biometria','app','relogio')) AS medida "
                "  FROM gp_clock_punches WHERE punch_timestamp >= :i AND punch_timestamp < :f"
            ),
            {"i": COMP_INI, "f": COMP_FIM},
        ).mappings().first()

    total = len({e for v in por_cond.values() for e in v})
    print(f"KIT DE AGOSTO · {len(por_cond)} condomínio(s) · {total} pessoa(s)\n")
    for cond in sorted(por_cond, key=lambda x: (-len(por_cond[x]), x)):
        print(f"  {cond:<36} {len(por_cond[cond]):>3}")
    print(f"\nResolvidos pelo Jordan (o dado não tinha posto): {len(RESOLVIDO_PELO_JORDAN)}")
    for n, c in RESOLVIDO_PELO_JORDAN.items():
        print(f"  + {n} → {c}")
    print(f"\nFora de kit de cliente — só bateram em posto NOSSO: {len(na_casa)}")
    if orfaos:
        print(f"\n⚠️ SEM CONDOMÍNIO, precisam do Jordan ({len(orfaos)}):")
        for n in sorted(orfaos.values()):
            print(f"  ? {n}")
    else:
        print("\nOK ninguém ficou sem condomínio.")
    pct = 100.0 * (med["medida"] or 0) / (med["total"] or 1)
    print(f"\n⚠️ AGOSTO: {med['medida']} de {med['total']} batidas são MEDIÇÃO ({pct:.0f}%). "
          f"O resto é grade de escala (Tangerino/web) e o espelho não conta — a folha de ponto "
          f"do kit vai mostrar só os dias efetivamente medidos.")


if __name__ == "__main__":
    main()
