#!/usr/bin/env python3
"""Ação IRREVERSÍVEL para fora executada ANTES de gravar o registro.

Caso real (cotação, 31/08/2026, commit 0b57d96c4 "grava ANTES de enviar"): a mensagem saía
por WhatsApp e só depois o pedido era gravado; quando a gravação falhava, o fornecedor
tinha recebido um pedido que não existia em lugar nenhum. A regra da casa desde então:
**o registro nasce antes do disparo**. Nada a vigiava.

Medição por ESTRUTURA (AST), não por regex sobre texto: dentro de UMA função, a primeira
chamada de saída (WhatsApp, e-mail, aviso ao dono) acontece em linha anterior à primeira
CRIAÇÃO de registro (add/create/save, ou `execute` com INSERT)? Marcar `enviado=true`
depois do envio é a ordem certa e não conta.
Função que só envia ou só grava não entra. Ainda assim é FORMA, e forma erra nos dois
sentidos — por isso cada achado foi conferido um a um antes de virar base, e a base só
acusa o que ENTRAR (ver `checar_regressao`).

    python3 backend/scripts/qa/checar_irreversivel.py   (host)

Linha canônica: `TOTAL: <n> função(ões) que disparam antes de gravar`. Exit 1 se houver.
"""
from __future__ import annotations

import ast
import pathlib

RAIZ = pathlib.Path("/opt/conecta-pro/backend/modules")
SAIDA = {"send_message", "send_text_message", "send_text_with_pdf", "send_email",
         "notify_owner", "send_whatsapp", "enviar_whatsapp", "send_sms"}
#: Só CRIAÇÃO. Conferido um a um em 06/09/2026: os 6 primeiros achados eram todos
#: `UPDATE … enviado=true` DEPOIS do envio — que é a ordem certa para uma marcação (marcar
#: antes perderia o lembrete se o envio falhasse). O defeito da cotação era outro: o
#: registro NASCIA depois do disparo. É isso que se vigia.
PERSISTE = {"add", "add_all", "create", "save", "criar", "gravar", "insert"}
SQL = ("INSERT",)


def _nome(call: ast.Call) -> str:
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def _persiste(call: ast.Call) -> bool:
    n = _nome(call)
    if n in PERSISTE:
        return True
    if n == "execute" and call.args:
        a = call.args[0]
        txt = a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else ""
        if isinstance(a, ast.Call) and a.args and isinstance(a.args[0], ast.Constant):
            txt = str(a.args[0].value)
        return any(k in txt.upper()[:40] for k in SQL)
    return False


def _chamadas_proprias(fn: ast.AST) -> list[ast.Call]:
    """Calls no corpo de `fn`, sem descer em def/async def aninhados."""
    out: list[ast.Call] = []
    fila = list(ast.iter_child_nodes(fn))
    while fila:
        n = fila.pop()
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(n, ast.Call):
            out.append(n)
        fila.extend(ast.iter_child_nodes(n))
    return out


def main() -> int:
    achados = []
    for arq in sorted(RAIZ.rglob("*.py")):
        if "test" in arq.name or "__pycache__" in str(arq):
            continue
        try:
            tree = ast.parse(arq.read_text(errors="replace"))
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            # só o corpo DESTA função: função aninhada é contada por ela mesma (sem isto
            # `crm/tasks.py` saía duas vezes — a externa e a `_inner`)
            chamadas = _chamadas_proprias(fn)
            saida = [c for c in chamadas if _nome(c) in SAIDA]
            grava = [c for c in chamadas if _persiste(c)]
            if not saida or not grava:
                continue
            s, g = min(saida, key=lambda c: c.lineno), min(grava, key=lambda c: c.lineno)
            if s.lineno < g.lineno:
                achados.append((str(arq.relative_to(RAIZ)), fn.name, _nome(s), s.lineno, _nome(g), g.lineno))
    for arq, fn, ns, ls, ng, lg in achados:
        print(f"   {arq}:{ls}  {fn}()  {ns}() na linha {ls} antes de {ng}() na {lg}")
    print(f"\nTOTAL: {len(achados)} função(ões) que disparam antes de gravar")
    return 1 if achados else 0


if __name__ == "__main__":
    raise SystemExit(main())
