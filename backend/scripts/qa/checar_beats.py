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

        # `c = C(...)` para saber de que classe é a variável.
        # ⚠️ SÓ VALE SE `C` FOR CLASSE. Na primeira execução isto acusou `r.get()`,
        # `result.items()` e `engine.connect()` — variáveis que vêm de FUNÇÃO (`r = apurar()`,
        # `engine = create_engine()`), onde a variável é o RETORNO, não uma instância. Eram 6
        # dos 9 achados: dois terços de ruído. Tipo de retorno de função não dá para saber
        # estaticamente, então aqui a gente cala.
        if isinstance(no, ast.Assign) and isinstance(no.value, ast.Call):
            f = no.value.func
            if isinstance(f, ast.Name) and f.id in importados and len(no.targets) == 1:
                alvo = no.targets[0]
                if isinstance(alvo, ast.Name):
                    try:
                        origem = getattr(importlib.import_module(importados[f.id]), f.id, None)
                    except Exception:  # noqa: BLE001
                        origem = None
                    if inspect.isclass(origem):
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


#: Camada 4 — a task ENGOLE a própria falha?
#:
#: Descoberto em 14/08/2026 no espelho do eSocial. A task terminava assim:
#:
#:     except Exception as exc:
#:         logger.error(...)
#:         return {"status": "erro", "erro": str(exc)}
#:
#: e para o Celery isso é uma execução BEM-SUCEDIDA. O sinal `task_failure` nunca dispara,
#: `task_falha` nunca publica no sino, e a rotina pode estar quebrada por semanas parecendo
#: saudável. Foram 37 dias sem um único acesso registrado, com o beat diário e a fila
#: consumida, e ninguém soube.
#:
#: Isto é ESTÁTICO e mecânico: procura, no corpo da task, um `except` largo cujo corpo
#: termina em `return` e não contém `raise`. Não julga o mérito — um `except` que devolve
#: valor de fallback pode ser correto. Achado é PISTA: leia a linha.
def _engole_falha(tree) -> list[tuple[str, str]]:
    achados: list[tuple[str, str]] = []
    for no in ast.walk(tree):
        if not isinstance(no, ast.ExceptHandler):
            continue
        # só o `except` LARGO interessa: `except Exception` / `except BaseException` / `except:`
        tipo = no.type
        largo = tipo is None or (isinstance(tipo, ast.Name)
                                 and tipo.id in ("Exception", "BaseException"))
        if not largo:
            continue
        corpo = list(ast.walk(ast.Module(body=no.body, type_ignores=[])))
        if any(isinstance(x, ast.Raise) for x in corpo):
            continue  # relança: a falha tem voz
        if any(isinstance(x, ast.Return) and x.value is not None for x in corpo):
            achados.append(("🟠", f"linha {no.lineno}: `except Exception` devolve valor e não "
                                 f"relança — para o Celery isto é SUCESSO, e o sino fica mudo"))
    return achados


#: Camada 5 — a rotina PRODUZIU alguma coisa?
#:
#: A pergunta que não existia em lugar nenhum do Arsenal. Temos trava para código morto
#: (`checar_repositorio`) e para número mentiroso (`cacar_fabricacao`); nenhuma para rotina
#: que roda, não falha, e não produz.
#:
#: Não dá para responder isso genericamente: só quem conhece a rotina sabe onde ela deixa
#: marca. Então é um mapa CURADO — beat → onde a produção dele aparece, e em quantos dias
#: no máximo. Curto de propósito: cada linha aqui é uma afirmação que alguém verificou.
#: Beat fora do mapa não é acusado, é apenas não coberto.
_PRODUCAO = {
    "esocial-espelho-sync": (
        "SELECT max(criado_em)::date FROM esocial_espelho_acessos", 2,
        "acesso ao governo registrado"),
    "fiscal.certidoes.sync_diario": (
        "SELECT max(updated_at)::date FROM ged_certidoes", 2,
        "certidão consultada/renovada"),
    "fiscal.calendario_obrigacoes": (
        "SELECT max(created_at)::date FROM fiscal_obligations", 40,
        "obrigação criada (mensal — a folga cobre o mês)"),
}


def _producao(agenda) -> list[str]:
    """Consulta o banco e devolve uma linha por rotina estéril."""
    from sqlalchemy import text  # noqa: PLC0415

    from core.database.session import SyncSessionLocal  # noqa: PLC0415

    from datetime import date  # noqa: PLC0415

    hoje, mudas = date.today(), []
    with SyncSessionLocal() as db:
        for apelido, (sql, limite, oque) in _PRODUCAO.items():
            if apelido not in agenda:
                continue
            try:
                ultima = db.execute(text(sql)).scalar()
            except Exception as e:  # noqa: BLE001
                mudas.append(f"{apelido}: não consegui medir — {type(e).__name__}: {e}")
                continue
            if ultima is None:
                mudas.append(f"{apelido}: NUNCA produziu ({oque})")
            elif (hoje - ultima).days > limite:
                mudas.append(f"{apelido}: última produção em {ultima} "
                             f"({(hoje - ultima).days} dias) — esperado no máximo {limite}. {oque}")
    return mudas


def main() -> int:
    app = _celery()
    agenda = app.conf.beat_schedule or {}
    registradas = set(app.tasks.keys())

    print(f"\n══ beats agendados: {len(agenda)} ══\n")
    problemas: dict[str, list[tuple[str, str]]] = {}
    engolem: dict[str, list[tuple[str, str]]] = {}
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
        engolidos = _engole_falha(tree)
        if engolidos:
            engolem[nome] = engolidos

    mudas = _producao(agenda)

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

    if engolem:
        print(f"🟠 ENGOLE A PRÓPRIA FALHA ({len(engolem)}) — quebra em silêncio, o sino não sabe\n")
        for nome, achados in sorted(engolem.items()):
            print(f"   {nome}")
            for grav, msg in achados:
                print(f"      {grav} {msg}")
        print("\n   Foi assim que o espelho do eSocial passou 37 dias sem consultar o governo,")
        print("   com o beat diário e a fila consumida. PISTA, não veredito: um `except` que")
        print("   devolve fallback pode ser correto — leia a linha antes de mexer.\n")

    if mudas:
        print(f"🔴 RODA E NÃO PRODUZ ({len(mudas)}) — verde no beat, nada no banco\n")
        for m in mudas:
            print(f"   {m}")
        print()

    total = len(sem_registro) + sum(len(v) for v in problemas.values()) + len(mudas)
    if not total and not engolem:
        print(f"✅ nenhum beat chama coisa que não existe, engole a própria falha "
              f"ou está estéril ({len(_PRODUCAO)} com produção vigiada).\n")
        return 0
    print(f"TOTAL: {total} achado(s) que quebram + {len(engolem)} que quebram CALADO")
    print("Cada um destes falha na hora agendada, todo dia, e só aparece no sino.\n")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
