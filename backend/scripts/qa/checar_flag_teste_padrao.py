#!/usr/bin/env python3
"""Caçador: flag que marca dado como DESCARTÁVEL nunca nasce ligada.

O QUE ACONTECEU (30/09/2026)
`mcp-server/server.py::_gerar_doc` tinha `teste: bool = True` na assinatura, e nenhum
dos 5 chamadores passava outro valor. Todo orçamento, recibo, aditivo, atestado e ordem
de serviço gerado pelo Cowork nascia carimbado como lixo de teste.

`expurgar_documentos_teste` arquiva exatamente por essa flag. 174 documentos comerciais
REAIS ficaram na mira — Villa Toscana, Villa-Lobos, Michelangelo, Prime Arena, Estilo
Golf, Green Hills e 6 versões da PROP-2026-00114. A prévia do expurgo mostrava só a
contagem, «225 documentos de teste», que qualquer um confirma sem hesitar.

POR QUE ESTA TRAVA E NÃO UM TESTE DE UNIDADE
O defeito não estava em nenhuma linha executada errado: cada função fazia o que a
assinatura mandava. Estava no PADRÃO da assinatura — e padrão não aparece em traceback,
não quebra teste e não acende log. Só se vê lendo, e ninguém leu por 3 meses.

A REGRA AFIRMADA
Parâmetro que marca um registro como descartável (`teste`, `fixture`, `dry_run`
invertido, `sandbox`) tem padrão FALSO. Quem quer descartável diz que quer.
Uma exceção legítima se declara aqui, nomeada, com o motivo.
"""

import ast
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[3]

#: Nomes de parâmetro que carimbam um registro como descartável.
SUSPEITOS = {"teste", "is_teste", "fixture", "is_fixture", "descartavel", "sandbox"}

#: Exceções declaradas — nome do arquivo::função. Vazio de propósito: hoje não há
#: nenhuma legítima, e deixar a lista vazia é o que torna a trava honesta.
PERDOADOS: set[str] = set()

#: Onde varrer. O `mcp-server/` entra porque foi lá que o defeito morou, e ele estava
#: fora de toda varredura anterior — a de 30/09 chegou a afirmar, por escrito e errado,
#: que «não está neste repositório».
PASTAS = ("backend/modules", "backend/scripts", "mcp-server")


def achados() -> list[str]:
    fora = []
    for pasta in PASTAS:
        base = RAIZ / pasta
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            if "__pycache__" in py.parts or "/tests/" in str(py):
                continue
            try:
                arvore = ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for no in ast.walk(arvore):
                if not isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                args = no.args
                # posicionais com default + keyword-only com default
                pares = list(zip(args.args[len(args.args) - len(args.defaults) :], args.defaults, strict=False))
                pares += [(a, d) for a, d in zip(args.kwonlyargs, args.kw_defaults, strict=False) if d]
                for arg, padrao in pares:
                    if arg.arg not in SUSPEITOS:
                        continue
                    if not (isinstance(padrao, ast.Constant) and padrao.value is True):
                        continue
                    chave = f"{py.name}::{no.name}"
                    if chave in PERDOADOS:
                        continue
                    fora.append(f"{py.relative_to(RAIZ)}:{no.lineno} {no.name}({arg.arg}=True)")
    return sorted(fora)


def main() -> int:
    fora = achados()
    for linha in fora:
        print("FLAG LIGADA NO PADRÃO:", linha)
    print(f"\n{len(fora)} assinatura(s) marcando registro como descartável por padrão")
    if fora:
        print("Um documento de cliente nasce descartável e entra na mira do expurgo.")
        return 1
    print("VEREDITO: nenhuma flag de descarte nasce ligada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
