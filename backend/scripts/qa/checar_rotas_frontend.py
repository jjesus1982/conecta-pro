#!/usr/bin/env python3
"""O frontend chama rota que o backend NÃO tem?

Espelho do `checar_repositorio.py`, e nasceu do mesmo MVP. Fechando `services` (12/08/2026)
achei `frontend/src/lib/api/services/services/slaService.ts` chamando `/api/v1/services/sla`
nove vezes — as rotas reais são `/api/v1/services/sla-configs`. **9 de 9 inexistentes.**

É a mesma doença do backend (código escrito contra uma API que nunca existiu), do outro lado
da parede. E ninguém a via: a trava do repositório só olha Python, os oráculos só olham
telas do redesign, e o cliente gerado do OpenAPI espelha o backend por construção — então
a impressão é de cobertura.

Medido no sistema inteiro na estreia: **723 chamadas inexistentes em 206 arquivos**, das
quais 77 em arquivos que ninguém importa (código órfão). Amostra de 12 conferida por HTTP
real: 12 de 12 devolveram 404.

LIMITES, porque número grande sem limite vira mentira:
- `types/generated/` fica de fora: é cliente gerado do OpenAPI, espelha o backend.
- rota montada com template complexo (`${base}${path}`) não é avaliada — subestima.
- "alcançável" = a partir de `app/**`, andando imports. Casa por NOME de arquivo, então
  homônimos em pastas diferentes inflam o alcance. Erra para MAIS, nunca para menos.
- **string que é PREFIXO de rota montada é tratada como constante de base e NÃO acusa.**
  Isso troca falso positivo por risco de falso negativo: se uma tela chamar a coleção base
  (`GET /api/v1/x/tasks`) e só `/api/v1/x/tasks/{id}` estiver montada, a trava cala. Aceito
  de propósito — acusei duas bases no financeiro e o T1 provou por HTTP que as telas
  funcionavam; falso positivo em trava nova custa a confiança inteira.
- achado é PISTA. Confirme por HTTP antes de agir (`curl` com token; 404 = não existe).

    python3 backend/scripts/qa/checar_rotas_frontend.py
    python3 backend/scripts/qa/checar_rotas_frontend.py --self-check
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

FRONT = Path(os.getenv("QA_FRONT", "/opt/conecta-pro/frontend/src"))

_RE_ROTA = re.compile(r"""[`'"](/api/v1/[^`'"]*)[`'"]""")
_RE_IMPORT = "from ['\"][^'\"]*(?:/|\\./){nome}['\"]"


def rotas_do_backend() -> list[str]:
    """Pergunta ao app de PRODUÇÃO quais rotas existem. Nunca inventa a lista."""
    r = subprocess.run(
        ["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend", "python3", "-c",
         "from main_production import app; import json;"
         " print(json.dumps(sorted({r.path for r in app.routes})))"],
        capture_output=True, text=True)
    for linha in reversed(r.stdout.splitlines()):
        if linha.startswith("["):
            return json.loads(linha)
    raise SystemExit("não consegui ler as rotas do backend — container de pé?")


def achados(front: Path = FRONT, rotas: list[str] | None = None) -> dict[str, list[str]]:
    # Normaliza a barra final DOS DOIS LADOS. A 1a versão tirava a barra só do frontend, e
    # rota registrada como `/operacional/employees/` deixava de casar: 3 dos 14 primeiros
    # achados devolviam 200 no curl. Falso positivo mata a confiança na trava mais rápido
    # que achado nenhum.
    cruas = [r.rstrip("/") or "/" for r in (rotas if rotas is not None else rotas_do_backend())]
    pads = [re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", r) + "$") for r in cruas]
    fora: dict[str, list[str]] = {}
    for f in sorted(front.rglob("*.ts*")):
        if "types/generated" in str(f):
            continue
        ruins = []
        for a in sorted(set(_RE_ROTA.findall(f.read_text(errors="ignore")))):
            alvo = re.sub(r"\$\{[^}]+\}", "1", a).split("?")[0].rstrip("/")
            if "${" in alvo:          # template que sobrou: não dá para avaliar
                continue
            if any(p.match(alvo) for p in pads):
                continue
            # CONSTANTE DE BASE não é chamada. `const API = '/api/v1/financeiro/inter'` com
            # 40 rotas montadas embaixo é o prefixo que o código concatena, não um endpoint.
            # Acusei duas assim no financeiro e o T1 provou por HTTP que as telas funcionam:
            # /banking/payment tem 5 rotas abaixo, /financeiro/inter tem 40.
            if any(r.startswith(alvo + "/") for r in cruas):
                continue
            ruins.append(a)
        if ruins:
            fora[str(f.relative_to(front))] = ruins
    return fora


def alcancaveis(front: Path) -> set[str]:
    """Arquivos que uma PÁGINA alcança, andando os imports a partir de `app/**`.

    A primeira versão perguntava só "alguém importa este arquivo?" e classificou 185 de 205
    como alcançáveis. Falso: `employeePortalService`, `timeTrackingService` e os outros
    campeões da lista não são usados por página nenhuma — são resíduo da reorganização
    35→9 módulos, quando `/api/v1/hr` virou `/api/v1/people-management` (hoje o backend não
    monta UMA rota /hr). Corrente de órfãos que se importam entre si parecia viva.

    Número alarmista é tão inútil quanto número escondido: 721 chamadas quebradas assusta e
    não diz o que consertar; o que uma tela alcança, sim.
    """
    textos = {f: f.read_text(errors="ignore") for f in front.rglob("*.ts*")}
    por_stem: dict[str, list[Path]] = {}
    for f in textos:
        por_stem.setdefault(f.stem, []).append(f)

    fila = [f for f in textos if f.parts[len(front.parts):][:1] == ("app",)]
    visto: set[Path] = set(fila)
    while fila:
        atual = fila.pop()
        for alvo in re.findall(r"""from\s+['"]([^'"]+)['"]""", textos.get(atual, "")):
            for cand in por_stem.get(Path(alvo).stem, []):
                if cand not in visto:
                    visto.add(cand)
                    fila.append(cand)
    return {str(f.relative_to(front)) for f in visto}


def _self_check() -> None:
    """A prova é o caso real: slaService chamando /services/sla onde existe /sla-configs."""
    import tempfile

    rotas = ["/api/v1/services/sla-configs", "/api/v1/services/sla-configs/{sla_id}",
             "/api/v1/services/catalog"]
    ruim = ("export const listar = () => api.get('/api/v1/services/sla');\n"
            "export const um = (id) => api.get(`/api/v1/services/sla/${id}`);\n")
    bom = ("export const cat = () => api.get('/api/v1/services/catalog');\n"
           "const BASE = '/api/v1/services/sla-configs';\n")   # base: 1 rota abaixo dela
    gerado = "export const x = () => api.get('/api/v1/services/sla');\n"

    with tempfile.TemporaryDirectory() as d:
        front = Path(d)
        (front / "lib").mkdir()
        (front / "lib" / "slaService.ts").write_text(ruim)
        (front / "lib" / "catalogService.ts").write_text(bom)
        (front / "types" / "generated").mkdir(parents=True)
        (front / "types" / "generated" / "g.ts").write_text(gerado)
        (front / "app").mkdir()
        (front / "app" / "page.tsx").write_text(
            "import {cat} from '../lib/catalogService';\nexport default () => cat();\n")
        got = achados(front, rotas)
        orf = {f for f in got if f not in alcancaveis(front)}

    assert list(got) == ["lib/slaService.ts"], f"pegou o arquivo errado: {list(got)}"
    assert len(got["lib/slaService.ts"]) == 2, got
    assert "types/generated/g.ts" not in got, "acusou o cliente gerado do OpenAPI"
    assert orf == {"lib/slaService.ts"}, f"alcance mal medido: {orf}"
    print("self-check OK — pega a rota fantasma, ignora o cliente gerado e a rota válida, "
          "e separa órfão de alcançável")


def main() -> int:
    fora = achados()
    n = sum(len(v) for v in fora.values())
    if not fora:
        print("nenhuma chamada do frontend para rota inexistente")
        print("TOTAL: 0")
        return 0
    vivos = alcancaveis(FRONT)
    orf = {f for f in fora if f not in vivos}
    n_orf = sum(len(fora[f]) for f in orf)
    print(f"{n} chamada(s) do frontend para rota que o backend NÃO tem, "
          f"em {len(fora)} arquivo(s):")
    print(f"  fora de alcance de tela: {len(orf)} arquivo(s), {n_orf} chamada(s)")
    print(f"  alcançáveis:              {len(fora) - len(orf)} arquivo(s), {n - n_orf} chamada(s)\n")
    for f, lst in sorted(((f, v) for f, v in fora.items() if f not in orf),
                         key=lambda kv: -len(kv[1]))[:10]:
        print(f"  {len(lst):>3}  {f}")
        for a in lst[:2]:
            print(f"        x {a}")
    print(f"\nTOTAL: {n}")   # linha canônica lida por checar_regressao.py
    return 1


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    raise SystemExit(main())
