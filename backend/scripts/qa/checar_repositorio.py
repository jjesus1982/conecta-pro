#!/usr/bin/env python3
"""Controller/service chama método que o repositório NÃO tem?

Achado no MVP de fechamento do módulo `services` (12/08/2026): 4 de 6 rotas devolviam 500, e
a causa era sempre a mesma — `AttributeError: 'ServiceRepository' object has no attribute
'get_service_catalog_stats'`. O repositório tem `get_service_stats`.

Medindo a família: **78 chamadas em 2 arquivos** da camada de serviço, mais 10 no controller.
O módulo inteiro foi escrito contra uma API de repositório que nunca existiu — nome por nome.
Não é bug de lógica: é código que nunca rodou.

DUAS travas, porque a primeira sozinha deu VERDE INCOMPLETO: depois das 78 renomeações ela
dizia "services: 0" e o dashboard executivo continuava em 500. "O método existe" não é o
contrato inteiro — existe e devolve OUTRA FORMA quebra igual. A trava 2 pega o método
anotado `-> Schema` que devolve o dict cru do repositório (só acusa quando o repositório
devolve dict literal; devolver objeto do ORM é legítimo e comum).

Isto é estático e mecânico. Roda em segundos e pega a classe inteira, em qualquer módulo.

LIMITE: casa `repo.x()`, `repository.x()`, `self.repository.x()`. Se o repositório for
guardado noutro nome, passa batido. Herança também não é resolvida — método herdado de uma
classe-base fora de `repositories/` aparece como faltando. Achado é PISTA; confira a linha.

    python3 backend/scripts/qa/checar_repositorio.py
    python3 backend/scripts/qa/checar_repositorio.py --self-check
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

RAIZ = Path(os.getenv("QA_RAIZ", "/opt/conecta-pro/backend")) / "modules"

_RE_DEF = re.compile(r"^\s+(?:async\s+)?def\s+(\w+)\s*\(", re.M)
_RE_USO = re.compile(r"\b(?:self\.)?(?:repo|repository|_repo|_repository)\.(\w+)\s*\(")


def metodos_do_repositorio(mod: Path) -> set[str]:
    """Tudo que os arquivos de repositório do módulo definem."""
    arquivos = list(mod.rglob("repositories/*.py")) + [
        p for p in mod.rglob("*repository*.py") if "repositories" not in p.parts]
    nomes: set[str] = set()
    for p in arquivos:
        nomes |= set(_RE_DEF.findall(p.read_text(errors="ignore")))
    return nomes


def achados(raiz: Path = RAIZ) -> list[dict]:
    out: list[dict] = []
    for mod in sorted(p for p in raiz.iterdir() if p.is_dir()):
        metodos = metodos_do_repositorio(mod)
        if not metodos:
            continue
        for p in sorted(mod.rglob("*.py")):
            if "repositories" in p.parts or "__pycache__" in p.parts:
                continue
            texto = p.read_text(errors="ignore")
            for m in _RE_USO.finditer(texto):
                nome = m.group(1)
                if nome in metodos:
                    continue
                # sugere o método real mais próximo — quase sempre é renomeação
                base = nome.replace("_by_id", "").replace("service_", "").replace("_config", "")
                perto = sorted(x for x in metodos if base and (base in x or x in nome))
                out.append({
                    "modulo": mod.name,
                    "arquivo": str(p.relative_to(raiz)),
                    "linha": texto[:m.start()].count("\n") + 1,
                    "chamado": nome,
                    "existe_parecido": perto[:2],
                })
    return out


#: O verde incompleto de 12/08: a trava acima disse "services: 0" enquanto o dashboard
#: executivo ainda estourava. "O método existe" não é o contrato inteiro — existe e devolve
#: OUTRA FORMA também quebra. Dois casos no mesmo módulo: get_service_catalog_stats e
#: get_order_stats anotados `-> ServiceCatalogStats`/`-> ServiceOrderStats`, devolvendo o
#: dict cru do repositório, e quem consome acessando `.total_services`.
_RE_DEF_TIPADA = re.compile(
    r"^[ \t]+(?:async +)?def +(\w+)\s*\([^)]*\)\s*->\s*([A-Z]\w+)\s*:", re.M)
_RE_RET_REPO = re.compile(r"return +(?:self\.)?(?:repo|repository|_repo|_repository)\.(\w+)\(")


def _devolve_dict(mod: Path, metodo: str) -> bool:
    """O método do repositório devolve dict literal? (então o envelope do schema falta)"""
    for p in list(mod.rglob("repositories/*.py")) + [
            x for x in mod.rglob("*repository*.py") if "repositories" not in x.parts]:
        txt = p.read_text(errors="ignore")
        for m in re.finditer(rf"^[ \t]+(?:async +)?def +{re.escape(metodo)}\s*\(", txt, re.M):
            corpo = txt[m.end():]
            fim = re.search(r"^[ \t]{0,4}(?:async +)?def ", corpo, re.M)
            if re.search(r"return +\{", corpo[:fim.start() if fim else len(corpo)]):
                return True
    return False


def contratos(raiz: Path = RAIZ) -> list[dict]:
    """Promete schema na anotação, devolve o dict do repositório sem envelopar."""
    out: list[dict] = []
    for mod in sorted(p for p in raiz.iterdir() if p.is_dir()):
        for p in sorted(mod.rglob("*.py")):
            if "repositories" in p.parts or "__pycache__" in p.parts:
                continue
            texto = p.read_text(errors="ignore")
            linhas = texto.splitlines()
            for m in _RE_DEF_TIPADA.finditer(texto):
                ini = texto[:m.start()].count("\n")
                corpo = "\n".join(linhas[ini + 1:ini + 16])
                r = _RE_RET_REPO.search(corpo)
                # devolver o objeto do ORM é legítimo e comum; só acusa dict literal
                if r and _devolve_dict(mod, r.group(1)):
                    out.append({"modulo": mod.name,
                                "arquivo": str(p.relative_to(raiz)), "linha": ini + 1,
                                "metodo": m.group(1), "promete": m.group(2),
                                "devolve": r.group(1) + "() -> dict"})
    return out


def _self_check() -> None:
    """A prova é o caso real: o controller chamando o nome que o repositório não tem."""
    import tempfile

    repo = "class R:\n    def get_service(self, i): ...\n    def list_orders(self, f): ...\n"
    ruim = "def rota(repo):\n    return repo.get_service_catalog_stats()\n"
    bom = "def rota(repo):\n    return repo.get_service(1)\n"

    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d)
        mod = raiz / "servicos"
        (mod / "repositories").mkdir(parents=True)
        (mod / "repositories" / "r.py").write_text(repo)
        (mod / "controllers").mkdir()
        (mod / "controllers" / "c.py").write_text(ruim)
        (mod / "controllers" / "ok.py").write_text(bom)
        got = achados(raiz)

    nomes = {a["chamado"] for a in got}
    assert "get_service_catalog_stats" in nomes, f"não pegou o caso real: {nomes}"
    assert "get_service" not in nomes, "acusou chamada que EXISTE no repositório"
    alvo = next(a for a in got if a["chamado"] == "get_service_catalog_stats")
    assert alvo["existe_parecido"] == ["get_service"], alvo["existe_parecido"]
    # 2a trava: o método EXISTE, mas devolve dict onde a anotação promete schema. Foi o
    # verde incompleto de 12/08 — "services: 0" com o dashboard executivo ainda em 500.
    repo2 = ("class R:\n    def get_service_stats(self):\n        return {'total': 1}\n"
             "    def get_service(self, i):\n        return self.db.q()\n")
    forma = ("class S:\n    def get_catalog_stats(self) -> CatalogStats:\n"
             "        return self.repository.get_service_stats()\n"
             "    def get_um(self, i) -> ServiceCatalog:\n"
             "        return self.repository.get_service(i)\n")
    with tempfile.TemporaryDirectory() as d:
        raiz = Path(d)
        mod = raiz / "servicos"
        (mod / "repositories").mkdir(parents=True)
        (mod / "repositories" / "r.py").write_text(repo2)
        (mod / "services").mkdir()
        (mod / "services" / "s.py").write_text(forma)
        got2 = contratos(raiz)

    assert [a["metodo"] for a in got2] == ["get_catalog_stats"], got2
    print("self-check OK — pega o método que falta, a forma errada, "
          "e ignora tanto chamada válida quanto repositório que devolve objeto do ORM")


def _relatar_formas() -> int:
    forma = contratos()
    if not forma:
        return 0
    print(f"\n{len(forma)} método(s) que PROMETEM schema e devolvem o dict do repositório:")
    for a in forma:
        print(f"   {a['arquivo']}:{a['linha']}  {a['metodo']}() -> {a['promete']}"
              f"  mas devolve {a['devolve']}")
    print("   (envelope: return Schema(**self.repository.x()))")
    return len(forma)


def main() -> int:
    itens = achados()
    if not itens:
        print("nenhuma chamada para método inexistente no repositório")
        n = _relatar_formas()
        print(f"TOTAL: {n}")   # linha canônica lida por checar_regressao.py
        return 1 if n else 0
    por_mod: dict[str, list[dict]] = {}
    for a in itens:
        por_mod.setdefault(a["modulo"], []).append(a)
    print(f"{len(itens)} chamada(s) para método que o repositório NÃO tem, "
          f"em {len(por_mod)} módulo(s):\n")
    for mod, lst in sorted(por_mod.items(), key=lambda kv: -len(kv[1])):
        nomes = sorted({a["chamado"] for a in lst})
        print(f"── {mod}: {len(lst)} chamada(s), {len(nomes)} método(s)")
        for a in lst[:4]:
            print(f"   {a['arquivo']}:{a['linha']}  {a['chamado']}()"
                  f"{'  → existe: ' + ', '.join(a['existe_parecido']) if a['existe_parecido'] else ''}")
        if len(lst) > 4:
            print(f"   (+{len(lst) - 4} não listadas)")
        print()
    print(f"TOTAL: {len(itens) + _relatar_formas()}")
    return 1


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(main())
