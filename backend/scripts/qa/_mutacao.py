#!/usr/bin/env python3
"""Arcabouço para script que ALTERA dado de produção. Ensaio primeiro, sempre.

Em 12/08/2026, dois scripts meus mexeram no banco de produção no mesmo dia:

  reclassificação   TINHA ensaio. Rodei, li os 194, vi o que ia mudar, apliquei. Acertou.
  limpeza de CND    NÃO tinha. `DELETE ... WHERE notes LIKE '%indeterminado%'` — o filtro
                    pegou junto a Certidão Trabalhista da Patrimonial, legítima e anterior
                    a mim. Só descobri porque fui conferir o total depois.

A diferença entre acertar e apagar dado alheio foi ter olhado a lista antes. Isto torna
"olhar antes" obrigatório em vez de virtuoso.

Uso:

    from _mutacao import Mutacao

    m = Mutacao("limpar apontamentos de teste", teto=20)
    alvos = [(r[0], f"{r[1]} — {r[2]}") for r in await db.execute(...)]
    if not m.confirmar(alvos):
        return                      # ensaio: mostrou e saiu
    ...aplica...
    m.feito(len(alvos))

Regras:
  • ensaio é o padrão; `--aplicar` é explícito;
  • acima do teto, exige `--forcar` — mutação em massa não acontece por acidente;
  • lista vazia nunca aplica: filtro que não casa nada quase sempre é filtro errado.
"""
from __future__ import annotations

import sys


class Mutacao:
    """Portão entre um script e o banco de produção."""

    def __init__(self, descricao: str, teto: int = 50, argv: list[str] | None = None) -> None:
        self.descricao = descricao
        self.teto = teto
        argv = sys.argv if argv is None else argv
        self.aplicar = "--aplicar" in argv
        self.forcar = "--forcar" in argv

    def confirmar(self, alvos: list) -> bool:
        """Mostra o que será tocado e devolve se pode aplicar.

        `alvos` é uma lista de qualquer coisa imprimível — de preferência (id, descrição),
        para o ensaio ser LEGÍVEL. Contagem sozinha não deixa ninguém notar que a certidão
        da Patrimonial entrou na lista por engano.
        """
        n = len(alvos)
        print(f"\n── {self.descricao} — {n} registro(s) ──")
        for a in alvos[:30]:
            print(f"   {a}")
        if n > 30:
            print(f"   (+{n - 30} não listados — {n} no total)")

        if n == 0:
            print("\nNada a fazer. Filtro que não casa nada quase sempre é filtro errado — "
                  "confira antes de concluir que já está limpo.")
            return False

        if not self.aplicar:
            print(f"\nENSAIO. Nada foi gravado. Confira a lista ACIMA linha a linha; foi assim "
                  f"que uma certidão legítima entrou num DELETE em 12/08.\n"
                  f"Para aplicar: --aplicar" + (f" --forcar  (são {n}, acima do teto de "
                                                f"{self.teto})" if n > self.teto else ""))
            return False

        if n > self.teto and not self.forcar:
            print(f"\nRECUSADO: {n} registros passam do teto de {self.teto}. Mutação em massa "
                  f"não acontece por acidente. Se é isso mesmo, repita com --forcar.")
            return False

        print(f"\nAPLICANDO em {n} registro(s)…")
        return True

    def feito(self, n: int) -> None:
        print(f"OK {self.descricao}: {n} registro(s) alterado(s).")


def _self_check() -> None:
    """As provas são os dois casos reais: o ensaio que salvou e o DELETE que não teve."""
    alvos = [(i, f"registro {i}") for i in range(5)]

    assert Mutacao("t", argv=[]).confirmar(alvos) is False, "sem --aplicar tem que ser ensaio"
    assert Mutacao("t", argv=["--aplicar"]).confirmar(alvos) is True, "com --aplicar deve aplicar"
    assert Mutacao("t", argv=["--aplicar"]).confirmar([]) is False, "lista vazia nunca aplica"

    muitos = [(i, "x") for i in range(200)]
    assert Mutacao("t", teto=50, argv=["--aplicar"]).confirmar(muitos) is False, \
        "acima do teto exige --forcar"
    assert Mutacao("t", teto=50, argv=["--aplicar", "--forcar"]).confirmar(muitos) is True, \
        "--forcar libera o teto"

    # O caso de 12/08: o DELETE pegou 4 onde deveriam ser 3. Com teto baixo e ensaio, a lista
    # aparece antes — e a linha a mais salta aos olhos.
    reais = [("99f92468", "[Eliziel] INSS divergente — teste"),
             ("c917da0a", "[Eliziel] INSS divergente — teste"),
             ("2c2abe79", "[Eliziel] INSS divergente — teste"),
             ("aa11bb22", "Certidão Negativa Trabalhista — Patrimonial")]
    assert Mutacao("limpar teste", teto=10, argv=[]).confirmar(reais) is False
    print("self-check OK — ensaio por padrão, vazio nunca aplica, teto exige --forcar")


if __name__ == "__main__":
    _self_check()
