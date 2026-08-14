#!/usr/bin/env python3
"""A tarefa agendada IMPORTA o que ela CHAMA?

Achado no fechamento do GEDEON (14/08/2026): três agentes estavam mortos desde 11/08 e as
oito travas do Arsenal deram VERDE. `kronos.verificacao_diaria` (06:00),
`themis.verificacao_assinaturas` (4/4h), `fiscal.verificar_certidoes` (07:00) e
`verificar_kits_completos` falharam 12× cada, todo dia, por três dias.

    ImportError: cannot import name 'KronosAgent' from 'modules.gedeon.agents.kronos'

**O vigia de vencimento de certidão e ASO ficou cego e ninguém soube.** O sino publicou as 48
falhas; ninguém leu. É a família de `checar_repositorio` — código escrito contra uma API que
não existe — só que agendado, então ele falha às 06:00 sem plateia.

E o diagnóstico do nome da classe é só a PRIMEIRA camada. Medido no mesmo dia, renomear
resolveria UM dos três:

    KronosAgent.executar_verificacao_completa()  → a classe é Kronos e o método é
                                                   executar_verificacao_diaria()
    ThemisAgent.verificar_e_alertar()            → a classe é Themis e o método EXIGE db
    AtlasAgent.sync_onvio(db, mes)               → não existe método nenhum na classe

Trocar só o nome da classe trocaria `ImportError` por `AttributeError` em dois deles — e o
beat continuaria vermelho, agora com uma mensagem diferente. Por isso esta trava tem TRÊS
camadas, e cada uma pega o que a anterior deixa passar:

    1. o beat aponta para uma task REGISTRADA?
    2. os `from X import Y` dentro da task resolvem?
    3. o método chamado no objeto EXISTE e aceita os argumentos passados?

Estático e mecânico: não executa nada, não toca no banco, roda em segundos. Teria pego no
primeiro dia — inclusive as 3 de `bidding`, que falham desde a mesma data e não estavam no
diagnóstico de ninguém.

LIMITES, e são reais. Só enxerga o que está escrito na cara: `from M import C` seguido de
`c = C(...)` e `c.metodo(...)`, no corpo da própria task. Fábrica, injeção de dependência,
`getattr` dinâmico e método herdado de fora do módulo passam batido. Achado é PISTA — leia a
linha antes de mexer. E o silêncio daqui NÃO quer dizer que a task funciona: quer dizer que
ela não tem ESTE defeito.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/checar_beats.py
"""
from __future__ import annotations

import ast
import importlib
import inspect
import sys

sys.path.insert(0, "/app")


def _celery():
    m = importlib.import_module("celery_app")
    for nome in ("app", "celery_app", "celery"):
        obj = getattr(m, nome, None)
        if obj is not None and hasattr(obj, "conf"):
            # ⚠️ SEM ISTO A TRAVA MENTE, e mentiu na primeira execução: acusou 89 de 89 beats
            # como "task não registrada". O Celery registra a task quando o MÓDULO dela é
            # importado, e o worker faz isso pelo `include=[...]` no boot. Um processo que só
            # faz `import celery_app` fica com `app.tasks` contendo apenas as embutidas —
            # então tudo parece órfão. Estava medindo o arreio, não o código.
            # Falso positivo mata a confiança mais rápido que achado nenhum.
            obj.loader.import_default_modules()
            return obj
    raise SystemExit("não achei o objeto Celery em celery_app.py")


def _corpo(func):
    """AST da função, já desindentado — `inspect.getsource` traz o recuo do decorator."""
    try:
        src = inspect.getsource(func)
    except (OSError, TypeError):
        return None
    linhas = src.splitlines()
    recuo = len(linhas[0]) - len(linhas[0].lstrip())
    return ast.parse("\n".join(ln[recuo:] if len(ln) > recuo else ln.lstrip() for ln in linhas))


def _aceita(func, n_pos: int) -> tuple[bool, str]:
    """A função aceita `n_pos` argumentos posicionais? (sem contar self)"""
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return True, ""
    params = [
        p for p in sig.parameters.values()
        if p.name != "self" and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if any(p.kind == p.VAR_POSITIONAL for p in sig.parameters.values()):
        return True, ""
    obrigatorios = [p.name for p in params if p.default is inspect.Parameter.empty]
    if n_pos < len(obrigatorios):
        return False, f"exige {obrigatorios}, a chamada passa {n_pos}"
    if n_pos > len(params):
        return False, f"aceita {len(params)} posicional(is), a chamada passa {n_pos}"
    return True, ""


def _analisar(tree) -> list[tuple[str, str]]:
    """(gravidade, mensagem) para cada defeito estático encontrado no corpo da task."""
    achados: list[tuple[str, str]] = []
    importados: dict[str, str] = {}   # nome local -> módulo de origem
    instancias: dict[str, str] = {}   # variável -> nome local da classe

    for no in ast.walk(tree):
        # camada 2 — `from M import C` resolve?
        if isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            for alias in no.names:
                local = alias.asname or alias.name
                try:
                    mod = importlib.import_module(no.module)
                except Exception as e:  # noqa: BLE001 — qualquer falha de import é achado
                    achados.append(("🔴", f"linha {no.lineno}: `import {no.module}` "
                                          f"quebrou — {type(e).__name__}: {e}"))
                    continue
                if not hasattr(mod, alias.name):
                    exporta = [n for n in dir(mod) if n[:1].isupper() and not n.startswith("_")]
                    palpite = [n for n in exporta if n.lower() in alias.name.lower()
                               or alias.name.lower().startswith(n.lower())]
                    achados.append((
                        "🔴",
                        f"linha {no.lineno}: `from {no.module} import {alias.name}` — "
                        f"NÃO EXISTE." + (f" Você quis dizer {palpite[0]}?" if palpite else
                                          f" O módulo exporta: {', '.join(exporta[:6])}")))
                    continue
                importados[local] = no.module

        # `c = C(...)` para saber de que classe é a variável
        if isinstance(no, ast.Assign) and isinstance(no.value, ast.Call):
            f = no.value.func
            if isinstance(f, ast.Name) and f.id in importados and len(no.targets) == 1:
                alvo = no.targets[0]
                if isinstance(alvo, ast.Name):
                    instancias[alvo.id] = f.id

    # camada 3 — `c.metodo(...)` existe e aceita os argumentos?
    for no in ast.walk(tree):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)):
            continue
        alvo = no.func.value
        if not (isinstance(alvo, ast.Name) and alvo.id in instancias):
            continue
        classe_local = instancias[alvo.id]
        mod = importlib.import_module(importados[classe_local])
        classe = getattr(mod, classe_local, None)
        if classe is None:
            continue
        metodo = getattr(classe, no.func.attr, None)
        if metodo is None:
            tem = [n for n, _ in inspect.getmembers(classe, inspect.isfunction)
                   if not n.startswith("_")]
            achados.append(("🔴", f"linha {no.lineno}: `{alvo.id}.{no.func.attr}()` — o método "
                                 f"NÃO EXISTE em {classe.__name__}. Tem: {', '.join(tem[:5])}"))
            continue
        ok, porque = _aceita(metodo, len(no.args))
        if not ok:
            achados.append(("🟠", f"linha {no.lineno}: `{alvo.id}.{no.func.attr}()` — {porque}"))
    return achados


def main() -> int:
    app = _celery()
    agenda = app.conf.beat_schedule or {}
    registradas = set(app.tasks.keys())

    print(f"\n══ beats agendados: {len(agenda)} ══\n")
    problemas: dict[str, list[tuple[str, str]]] = {}
    sem_registro: list[tuple[str, str]] = []

    for apelido, cfg in sorted(agenda.items()):
        nome = cfg.get("task", "")
        if nome not in registradas:
            # camada 1 — o beat dispara um nome que ninguém registrou: falha silenciosa,
            # o worker recusa a mensagem e o agendamento vira enfeite.
            sem_registro.append((apelido, nome))
            continue
        tree = _corpo(app.tasks[nome].run)
        if tree is None:
            continue
        achados = _analisar(tree)
        if achados:
            problemas[nome] = achados

    if sem_registro:
        print(f"🔴 BEAT SEM TASK REGISTRADA ({len(sem_registro)}) — agendado e nunca executa\n")
        for apelido, nome in sem_registro:
            print(f"   {apelido}\n      task '{nome}' não está em app.tasks")
        print()

    if problemas:
        print(f"🔴 TASK QUE CHAMA O QUE NÃO EXISTE ({len(problemas)})\n")
        for nome, achados in sorted(problemas.items()):
            print(f"   {nome}")
            for grav, msg in achados:
                print(f"      {grav} {msg}")
            print()

    total = len(sem_registro) + sum(len(v) for v in problemas.values())
    if not total:
        print("✅ nenhum beat chama coisa que não existe.\n")
        return 0
    print(f"TOTAL: {total} achado(s) em {len(problemas) + len(sem_registro)} beat(s)")
    print("Cada um destes falha na hora agendada, todo dia, e só aparece no sino.\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
