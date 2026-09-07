#!/usr/bin/env python3
"""O código diz o que a VERDADE DE DOMÍNIO diz — e a verdade ainda vale?

"Erro de domínio não tem trava possível" (ARSENAL §6): alíquota errada com fonte certa
passa em todos os portões. Esta trava não sabe a lei — sabe conferir. Um humano escreve a
verdade UMA vez em `verdades_dominio.py` (valor, fonte, vigência); aqui se confere:

  1. cada constante citada tem no código EXATAMENTE os números da verdade (AST, não regex);
  2. a mesma verdade em dois arquivos tem o mesmo valor — o caso de 06/09/2026:
     `FAIXAS_INSS_2026` com a tabela de 2026 num arquivo e a de 2024 no outro;
  3. a vigência não venceu — tabela anual vence em 31/12 e ninguém lembra em janeiro;
  4. verdade ancorada no BANCO (piso da CCT) bate com o que o banco tem hoje.

    python3 backend/scripts/qa/checar_dominio.py      (host; o banco é consultado via docker)

Linha canônica: `TOTAL: <n> divergência(s) de domínio`. Exit 1 se houver.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

RAIZ = Path("/opt/conecta-pro/backend")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verdades_dominio import VERDADES  # noqa: E402


def _numeros(node: ast.AST) -> list[Decimal]:
    """Todos os números do valor atribuído, na ordem: Decimal("x"), 1.5, "2.0" dentro de Decimal()."""
    out: list[Decimal] = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, int | float) and not isinstance(n.value, bool):
            out.append(Decimal(str(n.value)))
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            try:
                out.append(Decimal(n.value))
            except InvalidOperation:
                pass
    return out


def _constante(arquivo: Path, nome: str) -> list[Decimal] | None:
    try:
        tree = ast.parse(arquivo.read_text(errors="replace"))
    except (OSError, SyntaxError):
        return None
    for n in ast.walk(tree):
        alvo = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            alvo = n.targets[0].id
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            alvo = n.target.id
        if alvo == nome and n.value is not None:
            return _numeros(n.value)
    return None


def _banco(sql: str) -> Decimal | None:
    r = subprocess.run(["docker", "exec", "conecta-pro-backend", "python3", "-c",
                        "import sys; from core.database.session import SyncSessionLocal; from sqlalchemy import text; "
                        "db=SyncSessionLocal(); print('V=', db.execute(text(sys.argv[1])).scalar())", sql],
                       capture_output=True, text=True, timeout=120)
    for ln in r.stdout.splitlines():
        if ln.startswith("V="):
            try:
                return Decimal(ln[2:].strip())
            except InvalidOperation:
                return None
    return None


def main() -> int:
    hoje = date.today()
    achados: list[str] = []
    for v in VERDADES:
        esperado = [Decimal(x) for x in v["valores"]]
        if date.fromisoformat(v["vigente_ate"]) < hoje:
            achados.append(f"{v['chave']}: verdade VENCIDA em {v['vigente_ate']} — renove a fonte ({v['fonte']})")
        vistos: dict[str, list[Decimal] | None] = {}
        for arq, nome in v["onde"]:
            nums = _constante(RAIZ / arq, nome)
            vistos[f"{arq}:{nome}"] = nums
            if nums is None:
                achados.append(f"{v['chave']}: {arq} não tem a constante {nome} (renomeada? apagada?)")
            elif nums != esperado:
                achados.append(f"{v['chave']}: {arq}:{nome} = {[str(x) for x in nums]} ≠ verdade "
                               f"{v['valores']} ({v['fonte']})")
        distintos = {tuple(n) for n in vistos.values() if n is not None}
        if len(distintos) > 1:
            achados.append(f"{v['chave']}: a MESMA verdade tem {len(distintos)} valores diferentes em "
                           f"{[k for k, n in vistos.items() if n is not None]}")
        if v.get("banco"):
            real = _banco(v["banco"])
            if real is None:
                achados.append(f"{v['chave']}: banco não respondeu — NÃO VERIFICADO")
            elif real != esperado[0]:
                achados.append(f"{v['chave']}: banco diz {real}, verdade/código dizem {esperado[0]} — "
                               f"o fallback codificado envelheceu")
        print(f"  {'x' if any(a.startswith(v['chave']) for a in achados) else 'ok'} {v['chave']}  "
              f"({len(v['onde'])} lugar(es), vigente até {v['vigente_ate']})")
    print()
    for a in achados:
        print(f"   {a}")
    print(f"\nTOTAL: {len(achados)} divergência(s) de domínio")
    return 1 if achados else 0


if __name__ == "__main__":
    raise SystemExit(main())
