#!/usr/bin/env python3
"""Task agendada que ENGOLE a própria falha: `except Exception` que loga e devolve normal.

O caso que motivou (07/09/2026): `financial.fechar_razao_auto` falhava nas duas empresas todo
dia desde 11/08 e a task ficava SUCCESS — `fechar_grupo` capturava a exceção por empresa,
gravava `{"ok": False}` no dict e devolvia; a task não olhava o dict. 27 dias sem razão, sino
mudo, `task_falha` (que só vê exceção) sem nada para avisar. Um beat que não pode falhar não
pode ser vigiado.

REGRA (AST, sem executar nada): função decorada com `@app.task`/`@shared_task`/`@celery.task`
cujo corpo tem um `except Exception`/`except BaseException`/`except:` que NÃO termina em
`raise`, `self.retry(...)` ou `sys.exit` — ou seja, absorve e segue — é acusada. Handler que só
loga e devolve é exatamente o "sucesso vazio" do beat.

LIMITES: não avalia `except SomethingEspecífico` (recuperação legítima); não vê falha escondida
em função chamada (só o corpo da task); "engolir" dentro de um `for` por item pode ser desenho
(isolar um CNPJ do outro) — por isso é PISTA com linha de base, não gate.

    python3 backend/scripts/qa/checar_beat_engole_falha.py            # host, segundos
    python3 backend/scripts/qa/checar_beat_engole_falha.py --self-check
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BROAD = {"Exception", "BaseException"}


def _e_task(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in fn.decorator_list:
        alvo = d.func if isinstance(d, ast.Call) else d
        nome = ast.unparse(alvo)
        if nome.endswith(".task") or nome == "shared_task" or nome.endswith("shared_task"):
            return True
    return False


def _termina_relancando(handler: ast.ExceptHandler) -> bool:
    """Último statement do handler relança, retenta ou sai — ou o handler está dentro de um
    laço e continua (isolamento por item, desenho aceito)."""
    if not handler.body:
        return False
    ult = handler.body[-1]
    if isinstance(ult, ast.Raise):
        return True
    if isinstance(ult, ast.Expr) and isinstance(ult.value, ast.Call):
        s = ast.unparse(ult.value.func)
        if s.endswith(".retry") or s in ("sys.exit", "exit"):
            return True
    if isinstance(ult, ast.Continue):
        return True
    # `return self.retry(...)` / `raise self.retry(...)`
    if isinstance(ult, ast.Return) and isinstance(ult.value, ast.Call) and ast.unparse(ult.value.func).endswith(".retry"):
        return True
    return False


def _handlers_amplos(fn: ast.AST):
    for node in ast.walk(fn):
        if isinstance(node, ast.Try):
            for h in node.handlers:
                if h.type is None:
                    yield h, "except:"
                elif isinstance(h.type, ast.Name) and h.type.id in BROAD:
                    yield h, f"except {h.type.id}"
                elif isinstance(h.type, ast.Tuple) and any(isinstance(e, ast.Name) and e.id in BROAD for e in h.type.elts):
                    yield h, "except (…Exception…)"


def varrer(raiz: Path) -> list[dict]:
    achados = []
    for arq in sorted(raiz.glob("modules/**/*.py")):
        if "__pycache__" in arq.parts or "/tests/" in str(arq):
            continue
        try:
            tree = ast.parse(arq.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and _e_task(fn):
                for h, rot in _handlers_amplos(fn):
                    if not _termina_relancando(h):
                        achados.append({"arquivo": str(arq.relative_to(raiz)), "task": fn.name, "linha": h.lineno, "como": rot})
    return achados


def self_check() -> int:
    src = '''
@app.task(name="x.engole")
def engole(self):
    try:
        faz()
    except Exception as e:
        logger.error(e)
        return {"ok": False}

@app.task(name="x.relanca")
def relanca(self):
    try:
        faz()
    except Exception as exc:
        raise self.retry(exc=exc)

@app.task(name="x.isola")
def isola(self):
    for e in empresas:
        try:
            faz(e)
        except Exception:
            logger.warning("segue")
            continue
'''
    tree = ast.parse(src)
    nomes = []
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and _e_task(fn):
            for h, _ in _handlers_amplos(fn):
                if not _termina_relancando(h):
                    nomes.append(fn.name)
    ok = nomes == ["engole"]
    print("self-check:", "OK" if ok else f"FALHOU (acusou {nomes})")
    return 0 if ok else 1


def main() -> int:
    if "--self-check" in sys.argv:
        return self_check()
    achados = varrer(RAIZ)
    por_arq: dict[str, list] = {}
    for a in achados:
        por_arq.setdefault(a["arquivo"], []).append(a)
    for arq, lst in sorted(por_arq.items()):
        print(f"  {arq}")
        for a in lst[:6]:
            print(f"     {a['task']}():{a['linha']}  {a['como']} — loga e segue")
        if len(lst) > 6:
            print(f"     … +{len(lst) - 6}")
    print(f"\nTOTAL: {len(achados)} task(s) que engolem falha")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
