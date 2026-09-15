#!/usr/bin/env python3
"""Chave do contrato que o backend EMITE e o frontend publicado NÃO SABE LER.

Origem: 15/09/2026, vídeo `errodp.mp4`. A Pyetra clicou em Departamento Pessoal e caiu numa
tela preta — «Algo deu errado». Clicou em Ponto & Jornada: a mesma tela preta. O backend
respondia 200 nos dois casos; o erro era no navegador dela.

A causa foi minha. O bake do backend às 00:47 daquele dia publicou o achatamento do payload:
as telas pararam de repetir o array `fields` em cada linha e passaram a emitir `fieldsRef`
(um ponteiro) e `verDaLinha` (um marcador). O frontend que resolve essas duas chaves ficou
COMPILADO NO HOST e nunca foi publicado. Medido depois do fato:

    payload de departamento-pessoal ....... 1.632 `fieldsRef` · 3.799 `verDaLinha`
    bundle que estava no ar ...............     0 ocorrências de qualquer uma das duas

O front recebia um ponteiro onde esperava a lista, e morria. As 29 telas de módulo estavam
nessa condição — a Pyetra só reportou as duas que tentou abrir.

Nada mediu isso. O deploy do frontend confere BUILD_ID e HTTP 200; o do backend confere drift
de worker. Nenhum dos dois olha para o CONTRATO entre os dois lados. Esta trava olha.

## Como mede

Chave ESTRUTURAL = aparece em pelo menos `MIN_MODULOS` dos módulos consultados. É o que separa
o vocabulário do contrato (`cells`, `actions`, `fieldsRef`) do nome de um campo de formulário
qualquer, que aparece num módulo só. Cada chave estrutural precisa existir como string literal
dentro do bundle publicado — Terser não renomeia acesso a propriedade, então `linha.fieldsRef`
sobrevive à minificação. Não existe lá = o frontend no ar não tem como ler.

Provada contra o código anterior, com o bundle antigo que o próprio deploy arquiva:

    bundle publicado agora ......... 1 ausente: wired
    bundle antigo (o da Pyetra) .... 3 ausentes: fieldsRef · verDaLinha · wired

## O que ela NÃO faz

Não afirma que a tela funciona. Afirma que o front tem a palavra. Uma chave presente e mal
lida continua passando — para isso existe a varredura de navegador.

    python3 backend/scripts/qa/checar_contrato_front_back.py

Roda no HOST: precisa falar com os dois containers. Linha canônica:
`TOTAL: <n> chave(s) do contrato que o front não sabe ler`. Exit 1 quando há achado.
"""

from __future__ import annotations

import collections
import json
import os
import subprocess
import sys

#: Chave presente em menos módulos que isso é nome de dado, não vocabulário de contrato.
MIN_MODULOS = 4

#: Módulos consultados. Os mais pesados e mais diferentes entre si — cobrem tabela, formulário,
#: abas e redirect sem pagar os 34.
MODULOS = (
    "departamento-pessoal",
    "financeiro",
    "crm",
    "operacional",
    "rh",
    "gestao-de-pessoas",
    "fiscal",
    "documentos",
)

#: Emitidas pelo backend e que o frontend nunca leu — não são quebra, são peso. Declaradas
#: aqui com o motivo, para que uma chave NOVA ausente toque o sino em vez de se perder no meio.
IGNORADAS = {
    # `list(screens.keys())` devolvida ao lado do próprio `screens`. Nenhuma linha do frontend
    # a lê (medido: ausente do bundle nas duas versões). Em DP são 80 nomes de tela repetidos.
    "wired": "eco de screens.keys(); nenhuma linha do front lê",
}

#: PRODUÇÃO (8080), não o staging da 8081 que os outros caçadores HTTP usam: a pergunta aqui
#: é o que está NO AR de um lado contra o que está NO AR do outro. Medir o staging contra o
#: bundle publicado compararia duas coisas que nunca se encontram.
API = os.environ.get("QA_API", "http://127.0.0.1:8080")
USUARIO = os.environ.get("QA_USER", "jjesus@conectamais.pro")
SENHA = os.environ.get("QA_SENHA", "JsJ618908@#%")
FRONT = os.environ.get("QA_FRONT_CONTAINER", "conecta-pro-frontend")

#: Caminho absoluto de propósito: `docker` solto depende do PATH de quem chama, e este
#: caçador roda tanto por cron quanto pelo fim do deploy.
DOCKER = os.environ.get("QA_DOCKER", "/usr/bin/docker")


def _token() -> str | None:
    import urllib.parse
    import urllib.request

    dados = urllib.parse.urlencode({"username": USUARIO, "password": SENHA}).encode()
    req = urllib.request.Request(
        f"{API}/api/v1/auth/login",
        data=dados,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310  # nosec B310 - QA_API local
            return json.load(r).get("access_token")
    except Exception as e:  # noqa: BLE001
        print(f"   login falhou: {e}")
        return None


def _chaves(obj, destino: set) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            destino.add(k)
            _chaves(v, destino)
    elif isinstance(obj, list):
        for v in obj:
            _chaves(v, destino)


def main() -> int:
    if not SENHA:
        print("RECUSO: defina QA_SENHA")
        return 2
    tok = _token()
    if not tok:
        return 2

    import urllib.request

    por_modulo: dict[str, set] = {}
    for slug in MODULOS:
        req = urllib.request.Request(f"{API}/api/v1/redesign/data/{slug}", headers={"Authorization": f"Bearer {tok}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310  # nosec B310 - QA_API local
                dados = json.load(r)
        except Exception as e:  # noqa: BLE001
            print(f"   {slug}: não respondeu ({e})")
            continue
        ks: set = set()
        _chaves(dados, ks)
        por_modulo[slug] = ks

    if len(por_modulo) < MIN_MODULOS:
        print(f"RECUSO: só {len(por_modulo)} módulo(s) responderam — medir com isso seria verde cego")
        return 2

    quantos = collections.Counter()
    for ks in por_modulo.values():
        for k in ks:
            quantos[k] += 1
    estruturais = sorted(k for k, n in quantos.items() if n >= MIN_MODULOS)

    # O bundle PUBLICADO, lido de dentro do container — não o `.next/` do host, que é a fonte
    # de build e pode estar adiantado. Foi exatamente essa diferença que derrubou a tela dela.
    try:
        bundle = subprocess.run(  # noqa: S603
            [
                DOCKER,
                "exec",
                FRONT,
                "sh",
                "-c",
                "cat /app/.next/static/chunks/*.js /app/.next/static/chunks/**/*.js 2>/dev/null",
            ],
            capture_output=True,
            timeout=300,
            check=False,
        ).stdout.decode("utf8", "ignore")
    except Exception as e:  # noqa: BLE001
        print(f"RECUSO: não consegui ler o bundle de {FRONT}: {e}")
        return 2
    if len(bundle) < 1_000_000:
        print(f"RECUSO: bundle veio com {len(bundle)} bytes — container errado ou build ausente")
        return 2

    ausentes = [k for k in estruturais if k not in bundle]
    quebra = [k for k in ausentes if k not in IGNORADAS]
    peso = [k for k in ausentes if k in IGNORADAS]

    print(f"   {len(por_modulo)} módulo(s) · {len(estruturais)} chave(s) estrutural(is) do contrato")
    print(f"   bundle publicado em {FRONT}: {len(bundle):,} bytes")
    for k in quebra:
        onde = [m for m, ks in por_modulo.items() if k in ks]
        print(f"   QUEBRA  '{k}' — emitida em {len(onde)} módulo(s), ausente do bundle: {', '.join(onde[:4])}")
    for k in peso:
        print(f"   (peso   '{k}' — {IGNORADAS[k]})")

    print(f"\nTOTAL: {len(quebra)} chave(s) do contrato que o front não sabe ler")
    return 1 if quebra else 0


if __name__ == "__main__":
    sys.exit(main())
