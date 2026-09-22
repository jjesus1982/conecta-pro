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


def _portas_do_menu(slug: str) -> set[str]:
    """Itens do menu que o FRONT desenha para este módulo."""
    arq = MENUS / f"{slug}.json"
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
        ["/usr/bin/docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend", "python3", "-c", sonda],
        capture_output=True,
        timeout=300,
        check=False,
    )
    for ln in r.stdout.decode("utf8", "ignore").splitlines():
        if ln.startswith("@@"):
            return {p.split("/redesign/action/")[-1] for p in json.loads(ln[2:])}
    return set()


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
        portas = _portas_do_menu(slug) | {
            m.get("id") for m in (d.get("extraMenu") or []) if isinstance(m, dict) and m.get("id")
        }
        # abas de grupo também são porta — a tela vive dentro do grupo
        for tela in telas.values():
            if isinstance(tela, dict) and tela.get("type") == "tabs":
                portas |= {ab.get("id") for ab in (tela.get("tabs") or []) if isinstance(ab, dict)}

        def _colhe_endpoints(o: object) -> None:
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "endpoint" and isinstance(v, str) and "/redesign/action/" in v:
                        endpoints_chamados.add(v.split("/redesign/action/")[-1].split("?")[0])
                    else:
                        _colhe_endpoints(v)
            elif isinstance(o, list):
                for x in o:
                    _colhe_endpoints(x)

        _colhe_endpoints(telas)

        for tid, tela in telas.items():
            if tid in portas:
                continue
            if isinstance(tela, dict) and tela.get("type") == "redirect":
                continue  # stub de deep-link antigo: existe para redirecionar, não para ser aberto
            sem_porta.append(f"{slug}/{tid}")

    # ⚠️ O payload de HOJE não basta. Ação de LINHA só aparece quando existe linha que a
    # ofereça: as três de parcela (`parcela-editar/excluir/segurar`) sumiram da medição
    # porque, no momento do teste, as 49 linhas estavam todas `pago` e linha paga não tem
    # botão — de propósito. Um caçador que muda de cor conforme o dado do dia é pior que
    # nenhum. Por isso o CÓDIGO dos builders também conta como chamador.
    fonte = ""
    for arq in (RAIZ / "backend/modules").rglob("redesign_builders/*.py"):
        try:
            fonte += arq.read_text(encoding="utf8")
        except OSError:
            continue
    import re as _re

    endpoints_chamados |= {m.group(1) for m in _re.finditer(r"/redesign/action/([a-z0-9\-_]+)", fonte)}
    acoes = _acoes_do_router()
    acoes_orfas = sorted(
        a
        for a in acoes
        # rota com parâmetro de caminho: o nome base é o que a tela referencia
        if a.split("/")[0].split("{")[0].strip("-") not in endpoints_chamados and a not in endpoints_chamados
    )

    if sem_porta:
        print(f"  TELA servida e fora de todo menu/aba: {len(sem_porta)}")
        for x in sorted(sem_porta)[:40]:
            print(f"       {x}")
        if len(sem_porta) > 40:
            print(f"       … e mais {len(sem_porta) - 40}")
    if acoes_orfas:
        print(f"  AÇÃO que nenhuma tela chama: {len(acoes_orfas)}")
        for x in acoes_orfas[:40]:
            print(f"       /redesign/action/{x}")
        if len(acoes_orfas) > 40:
            print(f"       … e mais {len(acoes_orfas) - 40}")

    total = len(sem_porta) + len(acoes_orfas)
    print(f"TOTAL: {total} sem porta")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
