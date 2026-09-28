"""Oráculo — o default do formulário não pode ser recusado pelo validador (DGX U5, entrega de benefício).

REGRA QUE AFIRMA (não é fotografia de nenhuma entrega):
  Preencher só os campos que o formulário MARCA como obrigatórios (`*`) e deixar todo o resto
  exatamente como a tela entrega (o `value` que o próprio builder manda, ou vazio) TEM QUE SER
  ACEITO pelo endpoint que o próprio formulário declara em `submit.endpoint`.

Por que existe: esta casa já perdeu três capacidades inteiras por isso — a tela de CND oferecia
`caixa` e o endpoint só aceitava `certidao_negativa_fgts` (400 em 100% dos envios). Aqui o caso era
mais silencioso: `beneficio-entrega-nova` nascia com `apuracao_modo = "apontamento"` por default, e
esse modo EXIGE `apuracao_inicio`/`apuracao_fim` — dois campos que o form mandava vazios e cujo
label não tinha `*`. Quem abrisse a tela, preenchesse os quatro campos com asterisco e clicasse
«Criar entrega» levava 422 e nenhuma entrega nascia. Medido em 28/09/2026: 422 em 100% dos envios
do caminho feliz; `beneficio_entregas` com 0 linhas.

O oráculo lê o formulário de onde o FRONT lê (o payload de `/redesign/data/departamento-pessoal`),
não do código — então ele pega qualquer campo NOVO que alguém acrescente com default que o
validador recusa, e qualquer opção de `select` que o endpoint não aceite.

Irmã de caminho feliz (senão um 422 esperado passaria como "validou"): o MESMO payload com
`referencia = 13/2026` tem que ser RECUSADO. Um endpoint que aceita os dois não está validando.

Limpeza: a entrega criada é apagada por `observacao` e a ausência é provada por leitura no banco.

Roda no HOST:  QA_SENHA=... python3 backend/scripts/orq/test_oraculo_u5_form_default_aceito.py
Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import calendar
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

API = os.environ.get("QA_API", "http://127.0.0.1:8080")
USUARIO = os.environ.get("QA_USER", "jjesus@conectamais.pro")
SENHA = os.environ.get("QA_SENHA", "JsJ618908@#%")
DOCKER = os.environ.get("QA_DOCKER", "/usr/bin/docker")
PG = os.environ.get("QA_PG", "conecta-pro-postgres")

MODULO = "departamento-pessoal"
TELA = "beneficio-entrega-nova"
FIX = "FIXTURE ORACULO U5 FORM"


def _sql(q: str) -> str:
    r = subprocess.run(  # noqa: S603
        [DOCKER, "exec", PG, "psql", "-U", "postgres", "-d", "conecta_pro", "-t", "-A", "-c", q],
        capture_output=True,
        timeout=120,
        check=False,
    )
    return r.stdout.decode("utf8", "ignore").strip()


def _token() -> str | None:
    dados = urllib.parse.urlencode({"username": USUARIO, "password": SENHA}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login", data=dados, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310  # nosec B310 - QA local
            return json.load(r).get("access_token")
    except Exception as e:  # noqa: BLE001
        print(f"login falhou: {e}")
        return None


def _get(path: str, tok: str) -> dict:
    req = urllib.request.Request(f"{API}{path}", headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310  # nosec B310 - QA local
        return json.load(r)


def _post(path: str, tok: str, body: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310  # nosec B310 - QA local
            return r.status, r.read().decode("utf8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf8", "ignore")


def _achar_tela(payload: dict, tela: str) -> dict | None:
    """A tela pode estar solta em `screens` ou dentro das abas de um grupo (montar_grupos stuba a solta)."""
    sc = payload.get("screens") or {}
    for nome, scr in sc.items():
        if nome == tela and isinstance(scr, dict) and scr.get("fields"):
            return scr
        for tab in (scr or {}).get("tabs", []) if isinstance(scr, dict) else []:
            if isinstance(tab, dict) and tab.get("id") == tela and isinstance(tab.get("screen"), dict):
                return tab["screen"]
    return None


def _preencher(campos: list[dict]) -> tuple[dict, list[str]]:
    """O payload que o front manda: default do campo para todo mundo; os `*` sem default, preenchidos
    com o mínimo plausível POR TIPO (é o que a pessoa faz). Nada de valor esperto: se o form não
    consegue ser preenchido com o óbvio, é ele que está errado."""
    hoje = date.today()
    ant_y, ant_m = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    prim = date(ant_y, ant_m, 1)
    ult = date(ant_y, ant_m, calendar.monthrange(ant_y, ant_m)[1])
    body: dict = {}
    faltas: list[str] = []
    for f in campos:
        k, lbl, tp = f.get("key"), str(f.get("label") or ""), str(f.get("type") or "text")
        if not k:
            continue
        val = f.get("value")
        if val not in (None, ""):
            body[k] = str(val)
            continue
        if not lbl.rstrip().endswith("*"):
            body[k] = ""  # intocado, é o que o navegador manda
            continue
        if tp == "select":
            op = next((o for o in (f.get("options") or []) if str(o.get("value") or "")), None)
            if not op:
                faltas.append(f"campo obrigatório «{lbl}» é select SEM NENHUMA opção — nada pode ser criado por esta tela")
                body[k] = ""
            else:
                body[k] = str(op["value"])
        elif tp == "date":
            body[k] = (prim if "inicio" in k else ult).isoformat()
        elif tp == "number":
            body[k] = "1"
        else:
            ph = str(f.get("ph") or "")
            body[k] = ph if (len(ph) == 7 and ph[2] == "/") else f"{ant_m:02d}/{ant_y}"
    return body, faltas


def main() -> int:
    falhas: list[str] = []
    # ⚠️ 28/09/2026 — este oráculo mede o formulário de FORA (docker exec para psql e para assinar
    # o token), então só roda no HOST. A varredura diária (`tasks_oraculos._oraculos`) globa
    # `test_*.py` DENTRO do contêiner, onde não existe /usr/bin/docker: sem esta saída o oráculo
    # virava VERMELHO todo dia por FileNotFoundError, e vermelho crônico é exatamente o que fez
    # ninguém agir sobre `test_oraculo_sku_unico` desde 12/09. 3 = BLOQUEADO (nem verde nem
    # vermelho) na convenção da casa.
    if not os.path.exists(DOCKER):
        print(f"BLOQUEADO: {DOCKER} não existe — este oráculo mede de fora e só roda no host")
        return 3
    tok = _token()
    if not tok:
        print("FALHOU: sem token — não dá para medir o formulário pelo caminho do front")
        print("TOTAL u5 form default aceito: 1")
        return 1

    payload = _get(f"/api/v1/redesign/data/{MODULO}", tok)
    tela = _achar_tela(payload, TELA)
    if not tela:
        print(f"FALHOU: tela {TELA} não chega no payload de /redesign/data/{MODULO} — builder sem porta")
        print("TOTAL u5 form default aceito: 1")
        return 1
    endpoint = ((tela.get("submit") or {}).get("endpoint") or "").strip()
    if not endpoint:
        print(f"FALHOU: {TELA} não declara submit.endpoint — o botão não tem para onde ir")
        print("TOTAL u5 form default aceito: 1")
        return 1

    body, faltas = _preencher(tela.get("fields") or [])
    falhas += faltas
    if "observacao" in body:
        body["observacao"] = FIX
    obrig = [str(f.get("label")) for f in tela["fields"] if str(f.get("label") or "").rstrip().endswith("*")]
    print(f"{TELA} → {endpoint}")
    print(f"obrigatórios ({len(obrig)}): {', '.join(obrig)}")
    print(f"payload do caminho feliz: {json.dumps(body, ensure_ascii=False)}")

    criado = None
    try:
        st, txt = _post(endpoint, tok, body)
        print(f"caminho feliz → HTTP {st}: {txt[:300]}")
        if st >= 300:
            falhas.append(
                f"o default da própria tela é recusado: HTTP {st} em {endpoint} — {txt[:200]}"
            )
        else:
            criado = (json.loads(txt) or {}).get("id")

        # irmã da recusa: se o inválido também passa, o 200 acima não prova validação
        ruim = dict(body)
        chave_ref = next((k for k in body if "referencia" in k), None)
        if chave_ref:
            ruim[chave_ref] = "13/2026"
            st2, txt2 = _post(endpoint, tok, ruim)
            print(f"controle (referência 13/2026) → HTTP {st2}: {txt2[:160]}")
            if st2 < 300:
                falhas.append("referência 13/2026 foi ACEITA — o endpoint não está validando, o verde acima não vale")
                for rid in [(json.loads(txt2) or {}).get("id")]:
                    if rid:
                        _sql(f"DELETE FROM beneficio_entregas WHERE id = {int(rid)}")
    finally:
        _sql(f"DELETE FROM beneficio_entregas WHERE observacao = '{FIX}'")
        if criado:
            _sql(f"DELETE FROM beneficio_entregas WHERE id = {int(criado)}")
        sobra = _sql(f"SELECT count(*) FROM beneficio_entregas WHERE observacao = '{FIX}'")
        itens = _sql(
            "SELECT count(*) FROM beneficio_entrega_itens i WHERE NOT EXISTS "
            "(SELECT 1 FROM beneficio_entregas e WHERE e.id = i.entrega_id)"
        )
        print(f"limpeza: fixtures restantes {sobra} · itens órfãos {itens}")
        if sobra not in ("0", ""):
            falhas.append(f"{sobra} fixture(s) do oráculo sobraram em beneficio_entregas")

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL u5 form default aceito: {len(falhas)}")
    if not falhas:
        print("OK o formulário de entrega de benefício pode ser enviado como a tela o entrega — e o inválido é recusado")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
