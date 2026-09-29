"""Quem entra no kit de AGOSTO, por condomínio. READ-ONLY — não escreve nada.

Decisões do Jordan em 28/09/2026:
  · "faz os kits individual por condomínio"
  · "o kit de setembro com o mês de competência sendo agosto"
  · "a quantidade de funcionários que temos hoje é de 53"
  · quem trabalhou em agosto entra no kit de agosto, mesmo não estando mais na casa

## Três coisas que a medição revelou e que este script resolve

1. **`employees.status` não serve de população.** Diz 66 ativos e **nenhum tem data de
   demissão** — 13 saídas nunca foram registradas. Os 53 do Jordan saem de
   `employee_alocacoes` (alocação vigente), que ele cura à mão: dá exatamente 53.

2. **Conecta Village é posto da PRÓPRIA CONECTAMAIS ELETRONICA, não de cliente.** Doze
   pessoas trabalhavam lá (portaria fixa, ronda, jardinagem, serviços gerais, manutenção) e a
   operação encerrou em 31/08: **zero turnos em setembro** nos 6 postos. Elas têm documento de
   agosto, mas **não pertencem ao kit de condomínio nenhum** — é por isso que fazer o kit por
   condomínio, como o Jordan pediu, já as exclui sozinho.

3. **Dois vocabulários para o mesmo condomínio.** `employee_alocacoes` → `condominios.nome`
   usa nome curto («IDEAL FLORES»); `shifts.post_id` → `posts.name` usa o longo («Condomínio
   Ideal Flores da Cidade»). Sem canonizar, o mesmo prédio rende dois kits.

⭐ E a população usa **BATIDA, não escala**: escala é plano, batida é fato, e o kit é prova.
Medido: por escala entrariam 5 pessoas extras; por batida, 3. As outras 2 tinham turno lançado
em agosto e nenhuma batida — não há o que documentar.
"""

import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

COMP_INI, COMP_FIM = "2026-08-01", "2026-09-01"
#: Postos da própria empresa. O kit é do CLIENTE — o que é nosso não vai nele.
CASA = "CONECTAMAIS ELETRONICA LTDA"


def canon(nome: str) -> str:
    """«Condomínio Ideal Flores da Cidade» e «IDEAL FLORES» viram a mesma chave.

    Tira acento, caixa e as palavras de enfeite que só um dos dois vocabulários usa. NÃO
    inventa correspondência: o que não casar sai com o nome original e aparece separado no
    relatório, para um humano olhar. Casar por aproximação silenciosa é como dois clientes
    passam a dividir um PDF.
    """
    s = unicodedata.normalize("NFKD", nome or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"\b(CONDOMINIO|RESIDENCIAL|COND|EDIFICIO|VILLAGE|DA|DE|DO|DOS|DAS|CIDADE)\b", " ", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    # «VILLA PASSAROS» vs «VILLA DOS PASSAROS» já colapsam pela remoção de DOS.
    return re.sub(r"\s+", " ", s)


def main() -> None:
    with get_sync_db() as db:
        # A — os 53: alocação vigente, curada pelo Jordan
        atual = db.execute(
            text(
                "SELECT a.employee_id::text AS eid, e.nome AS pessoa, "
                "       coalesce(cd.name, cd2.nome, '(condominio nao resolvido)') AS cond "
                "  FROM employee_alocacoes a "
                "  JOIN employees e ON e.id = a.employee_id "
                "  LEFT JOIN condominiums cd ON cd.id = a.condominio_id "
                "  LEFT JOIN condominios  cd2 ON cd2.id = a.condominio_id "
                " WHERE coalesce(a.ativo,false) = true AND a.data_inicio <= current_date "
                "   AND (a.data_fim IS NULL OR a.data_fim >= current_date)"
            )
        ).mappings().all()

        # B — quem BATEU em agosto num posto de CLIENTE e não está mais alocado.
        #     Batida, não escala: o kit prova o que aconteceu.
        extras = db.execute(
            text(
                "SELECT DISTINCT p.employee_id::text AS eid, e.nome AS pessoa, po.name AS cond, "
                "       count(*) OVER (PARTITION BY p.employee_id) AS batidas "
                "  FROM gp_clock_punches p "
                "  JOIN employees e ON e.id = p.employee_id "
                "  JOIN shifts s ON s.employee_id = p.employee_id AND s.shift_date = p.punch_timestamp::date "
                "  JOIN posts po ON po.id = s.post_id "
                "  JOIN clients c ON c.id = po.client_id "
                " WHERE p.punch_timestamp >= :ini AND p.punch_timestamp < :fim "
                "   AND c.name <> :casa "
                "   AND NOT EXISTS (SELECT 1 FROM employee_alocacoes a WHERE a.employee_id = p.employee_id "
                "         AND coalesce(a.ativo,false) = true AND a.data_inicio <= current_date "
                "         AND (a.data_fim IS NULL OR a.data_fim >= current_date))"
            ),
            {"ini": COMP_INI, "fim": COMP_FIM, "casa": CASA},
        ).mappings().all()

        # C — quem bateu em agosto SÓ em posto da própria casa: tem documento, não tem kit.
        internos = db.execute(
            text(
                "SELECT DISTINCT e.nome FROM gp_clock_punches p "
                "  JOIN employees e ON e.id = p.employee_id "
                "  JOIN shifts s ON s.employee_id = p.employee_id AND s.shift_date = p.punch_timestamp::date "
                "  JOIN posts po ON po.id = s.post_id JOIN clients c ON c.id = po.client_id "
                " WHERE p.punch_timestamp >= :ini AND p.punch_timestamp < :fim AND c.name = :casa "
                "   AND NOT EXISTS (SELECT 1 FROM employee_alocacoes a WHERE a.employee_id = p.employee_id "
                "         AND coalesce(a.ativo,false) = true AND a.data_inicio <= current_date "
                "         AND (a.data_fim IS NULL OR a.data_fim >= current_date)) "
                " ORDER BY 1"
            ),
            {"ini": COMP_INI, "fim": COMP_FIM, "casa": CASA},
        ).scalars().all()

    por_cond: dict[str, dict[str, str]] = {}
    rotulo: dict[str, str] = {}
    for r in atual:
        k = canon(r["cond"])
        rotulo.setdefault(k, r["cond"])
        por_cond.setdefault(k, {})[r["eid"]] = r["pessoa"]
    novos: list[str] = []
    for r in extras:
        k = canon(r["cond"])
        if k not in por_cond:
            # condomínio que só aparece pela escala de agosto — não casou com nenhum atual
            rotulo.setdefault(k, r["cond"])
        por_cond.setdefault(k, {})
        if r["eid"] not in por_cond[k]:
            por_cond[k][r["eid"]] = r["pessoa"]
            novos.append(f"{r['pessoa']} → {rotulo[k]}")

    total = len({e for v in por_cond.values() for e in v})
    print(f"KIT DE AGOSTO · {len(por_cond)} condomínio(s) · {total} pessoa(s)\n")
    for k in sorted(por_cond, key=lambda x: (-len(por_cond[x]), x)):
        print(f"  {rotulo[k]:<34} {len(por_cond[k]):>3} pessoa(s)")
    print(f"\nEntraram por terem TRABALHADO em agosto sem alocação hoje ({len(novos)}):")
    for n in sorted(novos):
        print(f"  + {n}")
    print(f"\nFORA de todo kit de cliente — só trabalharam em posto NOSSO ({len(internos)}):")
    for n in internos:
        print(f"  · {n}")
    print("\n⚠️ Conferir com o Jordan antes de montar: o kit é documento do cliente.")


if __name__ == "__main__":
    main()
