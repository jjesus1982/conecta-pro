#!/usr/bin/env python3
"""Controller/service chama método que o repositório NÃO tem?

Achado no MVP de fechamento do módulo `services` (12/08/2026): 4 de 6 rotas devolviam 500, e
a causa era sempre a mesma — `AttributeError: 'ServiceRepository' object has no attribute
'get_service_catalog_stats'`. O repositório tem `get_service_stats`.

Medindo a família: **78 chamadas em 2 arquivos** da camada de serviço, mais 10 no controller.
O módulo inteiro foi escrito contra uma API de repositório que nunca existiu — nome por nome.
Não é bug de lógica: é código que nunca rodou.

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
    print("self-check OK — pega o caso real e ignora chamada válida")


def main() -> int:
    itens = achados()
    if not itens:
        print("nenhuma chamada para método inexistente no repositório")
        return 0
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
    return 1


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(main())
