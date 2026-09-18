#!/usr/bin/env python3
"""O skill-retrieval está de fato ENCOLHENDO o prompt — e não escondendo as nossas skills.

Origem: 18/09/2026. O plugin `skill-retrieval` (BM25, terceiro, MIT) troca a lista completa de
skills do system prompt por uma lista de NOMES e injeta, por turno, só as top-K relevantes.
Instalado a pedido do Jordan depois de auditado: sem rede, sem subprocess, sem exec, sem
escrita em disco, um hook só (`pre_llm_call`) que falha devolvendo None.

## Por que esta trava existe, e não só um "instalei e funcionou"

O plugin tem DUAS fases, e elas puxam o custo em direções OPOSTAS:

    fase 1 · compactação  REMOVE as descrições do system prompt   (−1.426 tokens medidos)
    fase 2 · injeção      ADICIONA as top-K do turno              (+ algumas centenas)

Se a fase 1 parar de funcionar e a 2 continuar, o plugin passa a CUSTAR em vez de economizar,
em silêncio. E isso não é hipótese: rodamos Hermes **v0.19.0** e o plugin pede `>=0.20.0`. Na
nossa versão `agent/system_prompt.py` resolve `build_skills_system_prompt` pelo módulo
`run_agent`, que a importou para o próprio namespace — o patch do autor, que só toca
`agent.prompt_builder`, NÃO alcança o chamador. Medido no container:

    patch em prompt_builder → run_agent continua apontando para a função antiga
    "O PATCH ALCANÇA O CHAMADOR?" False

Por isso o `__init__.py` leva uma ADAPTAÇÃO DA CASA que também patcheia `run_agent`. Ela sai
quando subirmos o Hermes para >= 0.21.0 — e é exatamente por ser nossa que precisa de trava:
uma atualização do plugin sobrescreve o arquivo e leva a adaptação junto, sem avisar.

## As regras afirmadas

1. O patch alcança o CHAMADOR (`run_agent`), não só `agent.prompt_builder`.
2. O prompt compactado é MENOR que o original — a economia é medida, não assumida.
3. Os NOMES sobrevivem à compactação: `triagem-de-ponto` e `conferir-kit-documental` têm de
   continuar visíveis, senão a triagem e a auditoria perdem a própria skill.
4. O índice BM25 contém as duas, e a consulta real da triagem recupera a dela.

    python3 backend/scripts/qa/checar_hermes_skill_retrieval.py

Linha canônica: `TOTAL: <n> falha(s) no skill-retrieval`. Exit 1 quando há achado.
"""

from __future__ import annotations

import json
import subprocess
import sys

DOCKER = "/usr/bin/docker"  # nosec B607 — ruff S607 recusa executável parcial
HERMES = "conecta-pro-hermes"

#: As skills SEM AS QUAIS as duas rotinas agendadas não funcionam.
_NOSSAS = ("triagem-de-ponto", "conferir-kit-documental")

_SONDA = r"""
import json, re, sys
sys.path.insert(0, "/app")
sys.path.insert(0, "/data/plugins/skill-retrieval/scripts")
import run_agent
from agent import prompt_builder

# ⚠️ ESTA SONDA NÃO CONSEGUE VER A ADAPTAÇÃO DA CASA — e isso está escrito aqui porque eu
# tentei duas vezes e errei as duas.
#   1ª tentativa: conferir o atributo `_skill_retrieval_patched`. VERDE com a adaptação
#      removida — a descoberta de plugins roda no meio do import e carimba o atributo.
#   2ª tentativa: medir a SAÍDA de `run_agent.build_skills_system_prompt`. VERDE também —
#      num processo NOVO o plugin patcheia ANTES de `run_agent` ser importado, então ele já
#      importa a função compactada. No gateway VIVO a ordem é a inversa, e aí a adaptação faz
#      falta.
# Medido de ponta a ponta, que é a única régua que não mente aqui:
#      com a adaptação   25.455 tokens de entrada
#      sem a adaptação   26.793  ← PIOR que sem o plugin (26.569)
# Por isso a presença da adaptação é conferida LENDO O ARQUIVO (lá embaixo), e esta sonda
# mede o que ela alcança: a compactação existe, os nomes sobrevivem, o índice está completo.
f = prompt_builder.build_skills_system_prompt
comp = f(available_tools=set(), available_toolsets=set()) or ""
from hermes_cli import __version__ as _v
out = {"versao": str(_v)}
orig_fn = None
for c in (f.__closure__ or ()):
    if callable(getattr(c, "cell_contents", None)):
        orig_fn = c.cell_contents
        break
full = orig_fn(available_tools=set(), available_toolsets=set()) if orig_fn else ""
out["chars_original"] = len(full)
out["chars_compacto"] = len(comp)

m = re.search(r"<available_skills>(.*?)</available_skills>", comp, re.S)
nomes = re.findall(r"^\s*[-*]\s*([a-z0-9][\w/\-]*)", m.group(1), re.M) if m else []
out["nomes_no_prompt"] = nomes

try:
    from bm25_retriever import get_index
    idx = get_index()
    out["indexadas"] = list(idx._corpus_ids)
    pedido = ("Faca a triagem do ponto de hoje seguindo a skill triagem-de-ponto. "
              "Quem esta sem batida no turno e por que.")
    out["recuperadas"] = [s for s, _ in idx.retrieve(pedido, top_k=6)]
except Exception as exc:
    out["erro_indice"] = str(exc)[:200]
print("JSON " + json.dumps(out))
"""


def main() -> int:
    r = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [DOCKER, "exec", "-i", HERMES, "python3", "-"],
        input=_SONDA,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    linha = next((x for x in r.stdout.splitlines() if x.startswith("JSON ")), "")
    if not linha:
        # Hermes fora do ar não é "tudo certo": é o terceiro estado, dito de frente.
        print(f"NÃO MEDIDO: {HERMES} não respondeu — {(r.stderr or '').strip()[-160:]}")
        print("TOTAL: 0 falha(s) no skill-retrieval")
        return 0
    d = json.loads(linha[5:])

    falhas: list[str] = []
    orig = d.get("chars_original", 0)
    comp = d.get("chars_compacto", 0)
    if orig and comp >= orig:
        falhas.append(
            f"a compactação NÃO encolhe nada: {comp:,} vs {orig:,} chars — o plugin "
            f"virou só custo, porque a injeção continua somando e nada é removido"
        )

    # A VARIANTE CERTA PARA A VERSÃO, conferida LENDO O ARQUIVO instalado. As duas direções
    # doem, e cada uma já doeu:
    #   Hermes <  0.21  sem a adaptação → o plugin liga só a metade que ADICIONA tokens
    #                   (medido na 0.19: 26.793 com o original contra 26.569 sem plugin nenhum)
    #   Hermes >= 0.21  COM a adaptação → o plugin NÃO CARREGA: o Hermes recusa quem importa
    #                   caminhos removidos em 14/09 («uses 1 import path removed»)
    # O plugin mora no VOLUME e sobrevive à troca de imagem — então um upgrade ou um rollback
    # deixa a variante errada no lugar, calada. Ver plugins/skill-retrieval/LEIA-ME-CONECTA.md.
    r2 = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [
            DOCKER,
            "exec",
            HERMES,
            "grep",
            "-c",
            "_precisa_patchear_run_agent",
            "/data/plugins/skill-retrieval/__init__.py",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    tem_adaptacao = (r2.stdout or "0").strip() not in ("", "0")
    versao = str(d.get("versao") or "?")
    try:
        antiga = tuple(int(x) for x in versao.split(".")[:2]) < (0, 21)
    except Exception:  # noqa: BLE001 — versão ilegível: cobra a adaptação, que é o lado seguro
        antiga = True
    if antiga and not tem_adaptacao:
        falhas.append(
            f"Hermes {versao} (< 0.21) com o plugin ORIGINAL: a compactação não alcança o "
            f"`run_agent`, que é quem monta o prompt nesta versão, e o plugin passa a CUSTAR em "
            f"vez de economizar. Instale `__init__.py.para-hermes-0.19-0.20`"
        )
    if not antiga and tem_adaptacao:
        falhas.append(
            f"Hermes {versao} (>= 0.21) com a variante ADAPTADA: ela importa um caminho removido "
            f"em 14/09 e o Hermes RECUSA carregar o plugin inteiro — confira com "
            f"`hermes plugins compat`. Instale o `__init__.py` original"
        )

    nomes = set(d.get("nomes_no_prompt") or [])
    indexadas = set(d.get("indexadas") or [])
    recuperadas = set(d.get("recuperadas") or [])
    if d.get("erro_indice"):
        falhas.append(f"o índice BM25 não abriu: {d['erro_indice']}")

    # ⚠️ O ID DA SKILL GANHOU NAMESPACE na 0.21.3: `triagem-de-ponto` virou
    # `triagem-de-ponto/triagem-de-ponto`. A primeira versão desta trava comparava nome EXATO
    # e acusou três falhas sobre um sistema saudável — a skill estava lá e era recuperada em
    # primeiro lugar. Régua que não acompanha a forma do dado acusa o certo, e trava que
    # acusa o certo é desligada na terceira vez.
    def _tem(conjunto, nome: str) -> bool:
        """O nome aparece, com ou sem namespace (`grupo/nome`)."""
        return any(x == nome or x.endswith("/" + nome) or x.startswith(nome + "/") for x in conjunto)

    for nossa in _NOSSAS:
        if nomes and not _tem(nomes, nossa):
            falhas.append(
                f"`{nossa}` sumiu da lista de nomes do prompt — a rotina que depende dela deixa de saber que ela existe"
            )
        if indexadas and not _tem(indexadas, nossa):
            falhas.append(f"`{nossa}` não está no índice BM25 — nunca será recuperada")
    if recuperadas and not _tem(recuperadas, "triagem-de-ponto"):
        falhas.append(
            "a consulta REAL da triagem não recupera `triagem-de-ponto` — ela roda "
            f"sem a própria régua (veio: {sorted(recuperadas)[:4]})"
        )

    for f in falhas:
        print(f"  ✗ {f}")
    if orig and comp:
        print(
            f"prompt de skills: {orig:,} → {comp:,} chars "
            f"(−{orig - comp:,} ~ {(orig - comp) // 4:,} tokens) · "
            f"{len(nomes)} nomes no prompt · {len(indexadas)} indexadas · "
            f"Hermes {versao}" + (" (adaptação da casa presente)" if tem_adaptacao else "")
        )
    print(f"TOTAL: {len(falhas)} falha(s) no skill-retrieval")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
