#!/usr/bin/env python3
"""Trava: parâmetro AUSENTE não pode apagar campo de cadastro.

Por que existe (18/09/2026): na rodada R5 eu cheguei a trocar os defaults de
`atualizar_cliente` de `None` para `""`. O corpo da tool monta o payload com
`if nome is not None: payload["name"] = nome` — e `""` **não é** `None`. Com esse default,
`atualizar_cliente(cnpj_ou_id=X, cidade="Y")` passaria a enviar `name=""`, `email=""` e
`phone=""` junto, APAGANDO nome, e-mail e telefone de um cliente de produção.

A asserção do meu script falhou antes de gravar e o apagador nunca existiu. Foi sorte, não
processo — e o Cowork pediu uma trava nomeada exatamente porque nada estrutural impedia a
volta (R6-9).

⭐ A régua mede por AST a combinação PERIGOSA, não o texto: default string vazia num parâmetro
cujo uso é guardado por `is not None`. Qualquer uma das duas isolada é legítima; juntas
apagam dado. É a diferença entre "campo omitido" e "campo apagado de propósito", e a tool
precisa das duas coisas.

    python test_defaults_nao_apagam.py
"""
from __future__ import annotations

import ast
import pathlib
import sys

SERVER = pathlib.Path(__file__).parent / "server.py"

# Tools que escrevem em CADASTRO e onde ausente ≠ limpar. Lista explícita: a régua não deve
# adivinhar qual escrita é destrutiva.
TOOLS_DE_CADASTRO = (
    "atualizar_cliente", "atualizar_contrato", "atualizar_proposta",
    "definir_representante_cliente", "atualizar_modelo_contrato",
)


def _funcao(arvore, nome: str):
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == nome:
            return no
    return None


def test_default_vazio_com_guarda_is_not_none() -> None:
    arvore = ast.parse(SERVER.read_text())
    culpadas: list[str] = []
    for nome in TOOLS_DE_CADASTRO:
        fn = _funcao(arvore, nome)
        if fn is None:
            continue
        # parâmetros com default string vazia
        args = fn.args.args + fn.args.kwonlyargs
        defaults = ([None] * (len(fn.args.args) - len(fn.args.defaults))
                    + list(fn.args.defaults) + list(fn.args.kw_defaults))
        vazios = {a.arg for a, d in zip(args, defaults)
                  if isinstance(d, ast.Constant) and d.value == ""}
        if not vazios:
            continue
        # …e que sejam usados atrás de `is not None`
        guardados = set()
        for no in ast.walk(fn):
            if (isinstance(no, ast.Compare) and len(no.ops) == 1
                    and isinstance(no.ops[0], ast.IsNot)
                    and isinstance(no.comparators[0], ast.Constant)
                    and no.comparators[0].value is None
                    and isinstance(no.left, ast.Name)):
                guardados.add(no.left.id)
        perigosos = sorted(vazios & guardados)
        if perigosos:
            culpadas.append(f"{nome}: {perigosos}")
    assert not culpadas, (
        "default `\"\"` em parâmetro guardado por `is not None` — chamada SEM o campo vai "
        "enviar vazio e APAGAR o dado:\n  - " + "\n  - ".join(culpadas)
        + "\n  Use `None` como default (ausente não toca) e deixe `\"\"` significar "
          "'limpar de propósito'.")
    print(f"OK nenhuma das {len(TOOLS_DE_CADASTRO)} tools de cadastro tem default que apaga")


def test_atualizar_cliente_usa_none() -> None:
    """Âncora explícita na tool onde isto quase aconteceu."""
    fn = _funcao(ast.parse(SERVER.read_text()), "atualizar_cliente")
    assert fn is not None, "atualizar_cliente desapareceu"
    args = [a.arg for a in fn.args.args]
    defaults = ([None] * (len(args) - len(fn.args.defaults))) + list(fn.args.defaults)
    errados = [a for a, d in zip(args, defaults)
               if isinstance(d, ast.Constant) and d.value == ""]
    assert not errados, (
        f"estes parâmetros de `atualizar_cliente` voltaram a ter default `\"\"`: {errados}. "
        f"Com a guarda `is not None`, uma chamada que só muda a cidade apagaria os outros.")
    assert len(args) >= 11, (
        f"`atualizar_cliente` tem {len(args)} parâmetros — o endereço completo (rua, numero, "
        f"bairro, cep, uf, complemento) foi removido? Ele é o que permite preparar um cliente "
        f"para emissão de contrato.")
    print(f"OK atualizar_cliente: {len(args)} parâmetros, nenhum com default que apaga")


if __name__ == "__main__":
    falhou = 0
    for fn_ in (test_default_vazio_com_guarda_is_not_none, test_atualizar_cliente_usa_none):
        try:
            fn_()
            print(f"PASS {fn_.__name__}")
        except AssertionError as e:
            falhou += 1
            print(f"FAIL {fn_.__name__}\n  {e}")
    print("TEST test_defaults_nao_apagam " + ("FAIL" if falhou else "PASS"))
    sys.exit(1 if falhou else 0)
