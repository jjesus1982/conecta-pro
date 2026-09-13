#!/usr/bin/env python3
"""Trava: recusa sai em ENVELOPE, nunca em campo solto.

Por que existe (13/09/2026): a validação do Cowork achou `dossie_juridico` devolvendo
`{"encontrado": false, "mensagem": "..."}` — sem `ok`, sem `codigo`, sem `http`, sem `dica`
— numa das 15 tools de dado pessoal SENSÍVEL. Não era sucesso falso; era o contrato de erro
quebrado justamente onde ele precisa ser previsível.

Varrendo a família, havia SETE `return {"erro": ...}` em tools de escrita (`atualizar_cliente`,
`criar_contrato`, `atualizar_estagio_deal`, …). Todas viraram envelope.

⭐ A razão de ser uma TRAVA e não um conserto: o `carimbo` agora preenche `ok: true` em toda
resposta que não traz `ok`. Uma tool nova com `{"erro": ...}` sairia `{"ok": true, "erro": …}`
— contradição assinada pelo próprio middleware. O carimbo se defende (não estampa sobre
`erro`), e esta trava impede que o caso exista para ele se defender.

    python test_envelope_de_erro.py
"""
from __future__ import annotations

import pathlib
import re
import sys

SERVER = pathlib.Path(__file__).parent / "server.py"
# campos que uma recusa DEVE carregar para o agente poder agir
OBRIGATORIOS = ("codigo", "http", "mensagem", "dica")


def _corpos() -> dict[str, str]:
    s = SERVER.read_text()
    out: dict[str, str] = {}
    for bloco in re.split(r"\n@mcp\.tool\b", s)[1:]:
        m = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", bloco)
        if m:
            out[m.group(1)] = bloco
    return out


def test_sem_erro_em_campo_solto() -> None:
    culpadas = [n for n, c in _corpos().items()
                if re.search(r'return\s*\{\s*["\'](erro|error)["\']\s*:', c)]
    assert not culpadas, (
        f"{len(culpadas)} tool(s) devolvem erro em campo solto em vez de envelope: "
        f"{culpadas}\n  Use "
        '{"ok": False, "codigo": ..., "http": ..., "mensagem": ..., "dica": ...}.\n'
        "  Campo solto não diz ao agente o que fazer, e o carimbo não pode completar "
        "o que não existe.")
    print(f"OK nenhuma das {len(_corpos())} tools devolve erro em campo solto")


def test_recusa_literal_tem_os_quatro_campos() -> None:
    """`ok: False` escrito à mão carrega codigo/http/mensagem/dica.

    ⚠️ POR AST, NÃO POR REGEX — e a 1ª versão desta função é a prova de por quê. Ela usava
    `\{\s*"ok":\s*False\s*,(.{0,900}?)\}` e acusou 12 recusas "sem dica" que TODAS tinham
    dica: o quantificador não-guloso fecha no primeiro `}`, e o primeiro `}` costuma ser o de
    dentro de um f-string (`f"estágio inválido: {estagio!r}"`). Regex não conta chaves de
    Python.

    Se eu tivesse acreditado na minha própria trava, teria adicionado `dica` redundante em 12
    lugares corretos — que é exatamente a lição de ontem (régua de formato único fazendo
    "consertar" código certo) repetida por mim no dia seguinte, dentro da trava nova.
    """
    import ast

    fonte = SERVER.read_text()
    faltando: list[str] = []
    for no in ast.walk(ast.parse(fonte)):
        if not isinstance(no, ast.Dict):
            continue
        chaves = {k.value for k in no.keys
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        if "ok" not in chaves:
            continue
        valor_ok = next((v for k, v in zip(no.keys, no.values)
                         if isinstance(k, ast.Constant) and k.value == "ok"), None)
        if not (isinstance(valor_ok, ast.Constant) and valor_ok.value is False):
            continue
        ausentes = [c for c in OBRIGATORIOS if c not in chaves]
        if ausentes:
            faltando.append(f"linha {no.lineno}: falta {ausentes}")
    assert not faltando, (
        f"{len(faltando)} recusa(s) sem os quatro campos:\n  - "
        + "\n  - ".join(faltando[:12])
        + "\n  Recusa que informa o defeito e não a saída ensina metade.")
    print("OK toda recusa literal carrega codigo, http, mensagem e dica (por AST)")


if __name__ == "__main__":
    falhou = 0
    for fn in (test_sem_erro_em_campo_solto, test_recusa_literal_tem_os_quatro_campos):
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            falhou += 1
            print(f"FAIL {fn.__name__}\n  {e}")
    print("TEST test_envelope_de_erro " + ("FAIL" if falhou else "PASS"))
    sys.exit(1 if falhou else 0)
