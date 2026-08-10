"""Carrega a planilha conferida pelo Jordan no cadastro. DRY-RUN por padrão.

  python3 ponto_planilha_carregar.py          -> só mostra o diff, não grava
  python3 ponto_planilha_carregar.py --gravar -> aplica

O que entra (tem destino no cadastro):
  • recebe_intrajornada  <- coluna "RECEBE INTRAJORNADA?"  (SIM/Não)
  • escala_padrao        <- coluna "Escala"                 (12x36 / 44h)
  • turno_padrao         <- coluna "Turno"                  (diurno / noturno)

O que NÃO entra e por quê:
  • horário de entrada/saída — não existe campo. `jornada_trabalho` parece candidato mas é
    lido pelo `my_cct_controller` para achar a regra da CCT ("12x36"); gravar "07:00-19:00"
    ali quebraria a consulta da convenção. Precisa de coluna nova, que é o que o alarme de
    ponto vai exigir de qualquer forma.
  • Rondante — `adicional_ronda_percentual` é PERCENTUAL, não sim/não, e mexe em pagamento.
    Não invento o número.

`recebe_intrajornada` alimenta a folha: por isso o diff sai antes e o --gravar é explícito.
"""
from __future__ import annotations

import os
import sys

import openpyxl
from sqlalchemy import create_engine, text

PLANILHA = "/tmp/ponto_intrajornada_completa.xlsx"
GRAVAR = "--gravar" in sys.argv

#: normalização do que o Jordan digitou (ele escreveu "sim", "Sim", "Não", "NÃO"…)
def _sim(v) -> bool | None:
    s = str(v or "").strip().lower()
    if s.startswith("sim"):
        return True
    if s.startswith(("nao", "não")):
        return False
    return None


def _esc(v) -> str | None:
    s = str(v or "").strip().lower().replace(" ", "")
    if "12x3" in s:          # pega 12x36 e o typo 12x37
        return "12x36"
    if "44" in s:
        return "44h"
    return None


def _turno(v) -> str | None:
    s = str(v or "").strip().lower()
    if s.startswith("not"):
        return "noturno"
    if s.startswith(("diu", "dir")):   # "diruno" é typo de diurno
        return "diurno"
    return None


def main() -> None:
    db = create_engine(os.environ["DATABASE_URL"].replace("+asyncpg", "")).connect()
    ws = openpyxl.load_workbook(PLANILHA).active

    mudancas: list[tuple] = []
    nao_achei: list[str] = []

    for r in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
        nome = r[0]
        if not nome or not str(nome).strip():
            continue
        novo = {"recebe_intrajornada": _sim(r[15]),
                "escala_padrao": _esc(r[4]),
                "turno_padrao": _turno(r[5])}
        if all(v is None for v in novo.values()):
            continue

        atual = db.execute(text(
            "SELECT id::text, recebe_intrajornada, escala_padrao, turno_padrao "
            "FROM employees WHERE nome = :n AND status = 'ativo'"), {"n": nome}).mappings().first()
        if not atual:
            nao_achei.append(str(nome))
            continue

        for campo, val in novo.items():
            if val is None:
                continue
            # comparação direta: `atual or None` transformava False em None e fazia
            # toda linha já correta aparecer como "False -> False" no diff
            de = atual[campo]
            if isinstance(val, bool):
                de = bool(de) if de is not None else None
            if de != val:
                mudancas.append((atual["id"], str(nome), campo, de, val))

    print(f"  {len(mudancas)} alteração(ões) em {len({m[0] for m in mudancas})} colaborador(es)")
    if nao_achei:
        print(f"  NÃO ENCONTRADOS no cadastro ativo ({len(nao_achei)}): {nao_achei}")
    print()
    por_campo: dict[str, int] = {}
    for _id, nome, campo, de, para in mudancas:
        por_campo[campo] = por_campo.get(campo, 0) + 1
        print(f"    {nome[:30]:<32} {campo:<22} {str(de):<10} -> {para}")
    print()
    print("  por campo:", por_campo)

    if not GRAVAR:
        print()
        print("  DRY-RUN — nada foi gravado. Rode com --gravar para aplicar.")
        return

    for _id, _nome, campo, _de, para in mudancas:
        db.execute(text(f"UPDATE employees SET {campo} = :v, updated_at = now() WHERE id::text = :i"),
                   {"v": para, "i": _id})
    db.commit()
    print()
    print(f"  GRAVADO: {len(mudancas)} alterações.")


if __name__ == "__main__":
    main()
