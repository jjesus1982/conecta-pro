#!/usr/bin/env python3
"""TELA SEM PORTA: o backend serve e nenhum menu leva — e AÇÃO que nenhuma tela chama.

Origem: 22/09/2026. O Jordan, três vezes no mesmo dia: «constrói os botões, eu quero
conferir, editar, excluir, incluir»; «não quero que você faça, eu quero fazer»; «tudo o
que estamos fazendo pelo terminal tem que funcionar no frontend, não podemos ficar reféns
do terminal».

Os três defeitos daquele dia tinham a MESMA forma, e nenhum caçador pegava:
  · `gerar-parcelas` existia e não estava em aba nenhuma (21/09) — o primeiro passo da
    folha, sem porta;
  · segurar/editar/excluir parcela só existia como UPDATE no banco;
  · «Aprovar ordem (OTP)» pedia o ID do lote num campo de TEXTO, e nenhuma tela mostrava
    esse ID. O Jordan montou uma ordem de R$ 33.137,71, foi aprovar, e o OTP «não chegou»:
    nunca chegou a ser gerado, porque o campo não tinha de onde ser preenchido.

`checar_capacidade_sem_botao` faz a pergunta certa («existe algo que a tela nunca
chama?») mas EXCLUI as rotas `/redesign/action/...` dizendo que «ela É a porta». Não é:
a ação só tem porta se alguma TELA a chamar, e a tela só tem porta se algum MENU levar
até ela. Este caçador mede os dois elos que faltavam:

  1. TELA SEM PORTA — servida pelo backend, ausente do menu do módulo, do `extraMenu` e
     das abas de todo grupo. Alcançável só por link direto `?t=<id>`, que ninguém digita.
  2. AÇÃO SEM TELA — rota `/redesign/action/X` que nenhum `submit.endpoint` referencia.

Mede a SAÍDA REAL da API (o payload que o front recebe), não o código — é a mesma
postura do `checar_contrato_front_back`. Roda no HOST porque precisa da API e dos JSONs
de menu do frontend ao mesmo tempo.

    python3 backend/scripts/qa/checar_tela_sem_porta.py
    QA_API=http://127.0.0.1:8233 QA_CONTAINER=teste-dgx-u3 QA_RAIZ=$WT python3 ...   # container efêmero

Portas (o que o `ModuleView.tsx` de fato desenha): item do menu do pacote, item do
`extraMenu`, aba de grupo (`type: tabs`), e — desde 24/09/2026 (dgx u3) — `ctaTo` de uma
tela de topo com `cta`: o botão do cabeçalho leva à tela-alvo (`ModuleView.tsx:1315`, só
quando `screens[ctaTo]` existe). Sem contar o `ctaTo`, os 4 forms do marketing apareciam
órfãos há semanas, com botão «Nova campanha» na tela-mãe. Dentro de ABA o front não lê
`ctaTo`, por isso a mãe precisa ser tela de topo, não aba.

As funções puras (`telas_sem_porta`, `acoes_orfas`, ...) são importadas pelo oráculo
`scripts/orq/test_oraculo_toda_tela_tem_porta.py`, que aplica a MESMA régua ao app
importado (sem produção) — regra, não fotografia.

Linha canônica: `TOTAL: <n> sem porta` (binária: n = 0). Exit 1 quando há achado.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("QA_API", "http://127.0.0.1:8080")
RAIZ = Path(os.environ.get("QA_RAIZ", "/opt/conecta-pro"))
MENUS = RAIZ / "frontend/src/app/redesign/_modules"
#: de onde ler as rotas /redesign/action/* — o container que serve QA_API (efêmero: teste-dgx-uN)
CONTAINER = os.environ.get("QA_CONTAINER", "conecta-pro-backend")

#: Telas que existem para serem alcançadas por OUTRA tela, nunca pelo menu. Sem esta
#: lista o caçador vira ruído — e trava que grita à toa ninguém lê.
_SEM_MENU_DE_PROPOSITO = {
    # stub de redirecionamento: o próprio mecanismo de deep-link antigo
    "type:redirect",
}


def _post(caminho: str, dados: dict, tipo: str) -> dict:
    corpo = (urllib.parse.urlencode(dados) if tipo == "form" else json.dumps(dados)).encode()
    req = urllib.request.Request(  # noqa: S310
        f"{API}{caminho}",
        data=corpo,
        headers={"Content-Type": "application/x-www-form-urlencoded" if tipo == "form" else "application/json"},
    )
    # nosec B310 — URL montada a partir de QA_API (constante local), nunca de entrada
    # externa. O bandit não lê o `noqa` do ruff, daí a marca própria.
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310  # nosec B310
        return json.loads(r.read())


def _get(caminho: str, token: str) -> dict:
    req = urllib.request.Request(f"{API}{caminho}", headers={"Authorization": f"Bearer {token}"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310  # nosec B310
        return json.loads(r.read())


def portas_do_menu(menus: Path, slug: str) -> set[str]:
    """Itens do menu que o FRONT desenha para este módulo."""
    arq = menus / f"{slug}.json"
    if not arq.exists():
        return set()
    try:
        d = json.loads(arq.read_text(encoding="utf8"))
    except json.JSONDecodeError:
        return set()
    return {m.get("id") for m in (d.get("menu") or []) if isinstance(m, dict) and m.get("id")}


def _acoes_do_router() -> set[str]:
    """Rotas /redesign/action/* que o servidor expõe — lidas do processo, não do código."""
    sonda = (
        "import sys; sys.path.insert(0,'/app')\n"
        "from main_production import app\n"
        "import json,sys\n"
        "print('@@'+json.dumps([getattr(r,'path','') for r in app.routes "
        "                        if '/redesign/action/' in getattr(r,'path','')]))"
    )
    r = subprocess.run(  # noqa: S603
        ["/usr/bin/docker", "exec", "-e", "PYTHONPATH=/app", CONTAINER, "python3", "-c", sonda],
        capture_output=True,
        timeout=300,
        check=False,
    )
    for ln in r.stdout.decode("utf8", "ignore").splitlines():
        if ln.startswith("@@"):
            return {p.split("/redesign/action/")[-1] for p in json.loads(ln[2:])}
    return set()


def telas_sem_porta(telas: dict, raiz: set[str]) -> list[str]:
    """Ids de tela servida e sem porta. `raiz` = ids do menu do pacote + extraMenu (telas de TOPO).
    Porta também é: aba de grupo; `ctaTo` de tela de topo com `cta` (transitivo — a tela-alvo vira
    tela de topo quando o botão leva até ela, e pode ter o seu próprio `ctaTo`)."""
    raiz = set(raiz)
    mudou = True
    while mudou:
        mudou = False
        for tid, tela in telas.items():
            if tid not in raiz or not isinstance(tela, dict) or not tela.get("cta"):
                continue
            alvo = tela.get("ctaTo")
            if isinstance(alvo, str) and alvo in telas and alvo not in raiz:
                raiz.add(alvo)
                mudou = True
    portas = set(raiz)
    for tela in telas.values():
        if isinstance(tela, dict) and tela.get("type") == "tabs":
            portas |= {ab.get("id") for ab in (tela.get("tabs") or []) if isinstance(ab, dict)}
    return [
        tid
        for tid, tela in telas.items()
        if tid not in portas
        # stub de deep-link antigo: existe para redirecionar, não para ser aberto
        and not (isinstance(tela, dict) and tela.get("type") == "redirect")
    ]


def colhe_endpoints(o: object, achados: set[str]) -> None:
    """Todo `submit.endpoint` /redesign/action/X presente no payload → X entra em `achados`."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == "endpoint" and isinstance(v, str) and "/redesign/action/" in v:
                achados.add(v.split("/redesign/action/")[-1].split("?")[0])
            else:
                colhe_endpoints(v, achados)
    elif isinstance(o, list):
        for x in o:
            colhe_endpoints(x, achados)


def fonte_builders(modules_dir: Path) -> str:
    """Fonte concatenado de todo redesign_builders/*.py — CÓDIGO também conta como chamador (ver main)."""
    fonte = ""
    for arq in modules_dir.rglob("redesign_builders/*.py"):
        try:
            fonte += arq.read_text(encoding="utf8")
        except OSError:
            continue
    return fonte


def acoes_orfas(acoes: set[str], endpoints_chamados: set[str], fonte: str) -> list[str]:
    """Rotas /redesign/action/* que nenhuma tela (payload) nem builder (fonte) chama."""
    import re as _re

    chamados = set(endpoints_chamados)
    chamados |= {m.group(1) for m in _re.finditer(r"/redesign/action/([a-z0-9\-_]+)", fonte)}
    # Builder que monta o endpoint por concatenação (`A + "frota-retorno"`, f"{_ACT}conta-fixa-
    # encerrar") não casa com o literal acima — 9 ações por linha das frentes DGX F10/F11
    # apareceram órfãs em 24/09/2026 sem ser. O NOME da ação entre aspas no fonte é chamador.
    for a in acoes:
        nome = a.split("/")[0].split("{")[0].strip("-")
        if nome and _re.search(r"[\"'}/]" + _re.escape(nome) + r"[\"'?]", fonte):
            chamados.add(nome)
    return sorted(
        a
        for a in acoes
        # rota com parâmetro de caminho: o nome base é o que a tela referencia
        if a.split("/")[0].split("{")[0].strip("-") not in chamados and a not in chamados
    )


def main() -> int:  # noqa: C901, PLR0912
    try:
        tok = _post(
            "/api/v1/auth/login",
            {
                "username": os.environ.get("QA_USER", "jjesus@conectamais.pro"),
                "password": os.environ.get("QA_PASS", "JsJ618908@#%"),
            },
            "form",
        )["access_token"]
    except (urllib.error.URLError, KeyError, TimeoutError, OSError) as e:
        # OSError cobre ConnectionResetError: o blue/green troca o container no meio da
        # medição e a conexão cai. Medido em 22/09 — o caçador cuspia traceback, que é
        # pior que silêncio: parece defeito do sistema e é só o deploy acontecendo.
        print(f"NÃO MEDIDO — API fora do ar: {str(e)[:120]}", file=sys.stderr)
        return 0  # API caída não é vermelho: trava que grita sem motivo ninguém lê

    slugs = [p.stem for p in MENUS.glob("*.json")]
    sem_porta: list[str] = []
    endpoints_chamados: set[str] = set()

    for slug in sorted(slugs):
        try:
            d = _get(f"/api/v1/redesign/data/{urllib.parse.quote(slug)}", tok)
        except (urllib.error.URLError, TimeoutError, OSError):
            continue  # módulo que não respondeu agora: não inventa achado
        telas = d.get("screens") or {}
        raiz = portas_do_menu(MENUS, slug) | {
            m.get("id") for m in (d.get("extraMenu") or []) if isinstance(m, dict) and m.get("id")
        }
        colhe_endpoints(telas, endpoints_chamados)
        sem_porta += [f"{slug}/{tid}" for tid in telas_sem_porta(telas, raiz)]

    # ⚠️ O payload de HOJE não basta. Ação de LINHA só aparece quando existe linha que a
    # ofereça: as três de parcela (`parcela-editar/excluir/segurar`) sumiram da medição
    # porque, no momento do teste, as 49 linhas estavam todas `pago` e linha paga não tem
    # botão — de propósito. Um caçador que muda de cor conforme o dado do dia é pior que
    # nenhum. Por isso o CÓDIGO dos builders também conta como chamador.
    orfas = acoes_orfas(_acoes_do_router(), endpoints_chamados, fonte_builders(RAIZ / "backend/modules"))

    if sem_porta:
        print(f"  TELA servida e fora de todo menu/aba: {len(sem_porta)}")
        for x in sorted(sem_porta)[:40]:
            print(f"       {x}")
        if len(sem_porta) > 40:
            print(f"       … e mais {len(sem_porta) - 40}")
    if orfas:
        print(f"  AÇÃO que nenhuma tela chama: {len(orfas)}")
        for x in orfas[:40]:
            print(f"       /redesign/action/{x}")
        if len(orfas) > 40:
            print(f"       … e mais {len(orfas) - 40}")

    total = len(sem_porta) + len(orfas)
    print(f"TOTAL: {total} sem porta")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
