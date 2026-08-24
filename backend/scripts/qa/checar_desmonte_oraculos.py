#!/usr/bin/env python3
"""Trava: oráculo que ESCREVE em produção limpa na ENTRADA e na saída, por PREFIXO.

Medido em 24/08/2026, antes de qualquer conserto: **11 registros de teste vivos em produção**,
em 6 tabelas e 5 datas diferentes — ou seja, cinco execuções distintas deixaram resíduo.

    occurrences.title                    'TESTE E2E auto-posto — ignorar'          07/07
    occurrences.description              '...(será cancelada na limpeza).'         09/07
    billing_rules.name                   'E2E_TESTE editada'                       05/07
    communication_announcements.titulo   '[QA E2E] Teste de criação — pode excluir' 09/08
    financial_custos_recorrentes.descricao 'E2E_TESTE_CUSTO'                       05/07
    training_courses.name                'Curso de Teste E2E - RH'                 05/04

⭐ O achado está na segunda linha: alguém ESCREVEU "será cancelada na limpeza" em 09/07 e o
registro está lá 46 dias depois. A limpeza estava planejada — e não rodou. Isso é a prova de
que `finally` é NECESSÁRIO e NÃO SUFICIENTE: execução morta por sinal (OOM, timeout, deploy no
meio) não roda `finally` nenhum.

Daí a regra em três partes:

  saída (`finally`)  — o caso normal;
  ENTRADA            — apaga o que ficou da vez em que não houve saída;
  por PREFIXO        — nunca pela lista de ids da execução. A que morreu não deixou a lista
                       dela; limpar por id só limpa o próprio lixo, e o órfão é justamente o
                       que sobra. É o defeito exato acima.

E o prefixo é FIXO, não gerado: além de casar com o que já está abandonado, `ZZ` ordena no fim
de qualquer listagem — o que escapar aparece agrupado no rodapé em vez de escondido no meio do
dado real. Hoje os prefixos são cinco (`TESTE_5`, `TESTE_APROVA__`, `ZZQX_`, `TESTE_CENTRAL__`,
`E2E`), e prefixo que varia não casa com órfão de ontem.

    python3 backend/scripts/qa/checar_desmonte_oraculos.py
"""
from __future__ import annotations

import pathlib
import re

ORQ = pathlib.Path("/opt/conecta-pro/backend/scripts/orq")

ESCRITA = re.compile(
    r"INSERT\s+INTO|UPDATE\s+[a-z_]+\s+SET|DELETE\s+FROM|"
    r"\.(post|put|patch|delete)\s*\(", re.I)

#: O prefixo da casa. Fixo, maiúsculo, ordenando no fim das listagens.
PREFIXO = "ZZ"

#: Marca de limpeza NA ENTRADA: apaga por prefixo ANTES de começar.
ENTRADA = re.compile(
    r"(limpar_orfaos|desmontar_entrada|_limpar_previo|"
    r"DELETE\s+FROM\s+\w+\s+WHERE[^\n]*LIKE\s*[:'\"]?\s*'?ZZ)", re.I)

#: Só leem: não têm o problema, e inventar desmonte neles é trabalho fabricado.
def _escreve(txt: str) -> bool:
    return bool(ESCRITA.search(txt))


def main() -> int:
    if not ORQ.is_dir():
        print(f"  {ORQ} não existe — rode do host")
        return 1

    escrevem, sem_saida, sem_entrada, prefixo_errado, sem_marca = [], [], [], [], []
    for f in sorted(ORQ.glob("*.py")):
        if f.name.startswith("_"):
            continue
        txt = f.read_text(errors="replace")
        if not _escreve(txt):
            continue
        escrevem.append(f.name)
        if "finally:" not in txt:
            sem_saida.append(f.name)
        if not ENTRADA.search(txt):
            sem_entrada.append(f.name)
        # SEM exigir aspas coladas: os prefixos aparecem dentro de f-string e concatenação.
        # A primeira versão exigia a aspa e devolveu "0 fora do padrão" — verde por não ter
        # medido, que é o pior verde que existe.
        marcas = set(re.findall(r"\b(TESTE_[A-Z0-9_]+|E2E[A-Z0-9_]*|ZZ[A-Z0-9_]+)", txt))
        if not marcas:
            # Pior que prefixo errado: escreve SEM marca nenhuma. O resíduo dele fica
            # indistinguível de dado real — foi o que custou separar teste de lead à mão.
            sem_marca.append(f.name)
        elif not any(m.startswith(PREFIXO) for m in marcas):
            prefixo_errado.append(f"{f.name} usa {sorted(marcas)[:3]}")

    print(f"  {len(escrevem)} oráculo(s) escrevem em produção "
          f"(de {len(list(ORQ.glob('*.py')))} no total)")
    print(f"  sem limpeza de SAÍDA (finally): {len(sem_saida)}")
    print(f"  sem limpeza de ENTRADA (por prefixo): {len(sem_entrada)}")
    print(f"  com prefixo fora do padrão {PREFIXO!r}: {len(prefixo_errado)}")
    print(f"  SEM marca de teste nenhuma (resíduo vira dado real): {len(sem_marca)}")
    for n in sem_marca:
        print(f"    - {n}")

    if sem_entrada:
        print("\n  ── sem desmonte de ENTRADA (o órfão de execução morta fica) ──")
        for n in sem_entrada[:20]:
            print(f"    - {n}")
        if len(sem_entrada) > 20:
            print(f"    … +{len(sem_entrada) - 20}")

    if sem_entrada or sem_saida or sem_marca:
        print(f"\n{len(sem_entrada)} sem entrada e {len(sem_saida)} sem saída. Execução morta "
              f"por sinal não roda `finally`: sem a limpeza de ENTRADA, por PREFIXO, o resíduo "
              f"fica. Medido hoje: 11 registros de teste vivos em produção, o mais antigo de "
              f"05/04 e um deles escrito com a frase 'será cancelada na limpeza'.")
        return 1
    print("\n  confere: todo oráculo que escreve limpa na entrada e na saída")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
