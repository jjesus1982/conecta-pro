#!/usr/bin/env python3
"""Trava: no modo bearer, conector SEM token (ou com token curto) não sobe.

Por que existe: a checagem de `_BearerASGI.__call__` era condicionada a `and self.token`.
Com `MCP_AUTH_TOKEN` vazio ou ausente o `if` inteiro era saltado e o conector respondia 200
a qualquer requisição, com todo o catálogo de ferramentas do ERP atrás — enquanto o modo google já
recusava subir sem allowlist. Assimetria: um modo falhava fechado, o outro falhava aberto.

As duas primeiras provas rodam em SUBPROCESSO de propósito: a guarda é no import de
`server`, e é exatamente isso que se quer provar — que o processo morre antes de servir, em
vez de subir desarmado. As duas últimas dirigem o middleware com scope ASGI cru para provar
que a checagem acontece sempre, e que `/healthz` continua aberto para o healthcheck do
compose.

    python test_bearer_fail_closed.py
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess
import sys

os.environ.setdefault("MCP_AUTH_TOKEN", "t" * 64)  # o import de `server` é fail-closed sem token

AQUI = pathlib.Path(__file__).parent
TOKEN_OK = "t" * 64


def _importa_server(token: str | None) -> subprocess.CompletedProcess:
    """Sobe `import server` num processo limpo com este MCP_AUTH_TOKEN.

    O env é sobrescrito explicitamente: rodando por `docker exec` o container já traz o
    token de verdade do env_file, e herdá-lo faria o teste passar sem testar nada.
    """
    env = {**os.environ, "AUTH_MODE": "bearer"}
    if token is None:
        env.pop("MCP_AUTH_TOKEN", None)
    else:
        env["MCP_AUTH_TOKEN"] = token
    return subprocess.run(
        [sys.executable, "-c", "import server"],
        cwd=AQUI, env=env, capture_output=True, text=True, timeout=180, check=False)


def test_token_vazio_nao_sobe() -> None:
    for rotulo, token in (("vazio", ""), ("ausente", None)):
        r = _importa_server(token)
        assert r.returncode != 0, (
            f"com MCP_AUTH_TOKEN {rotulo} o `import server` RETORNOU 0 — o conector subiria "
            f"sem autenticação nenhuma, com todo o catálogo de ferramentas do ERP expostas.")
        assert "MCP_AUTH_TOKEN" in r.stderr, (
            f"falhou com MCP_AUTH_TOKEN {rotulo}, mas o erro não nomeia a variável a "
            f"configurar:\n{r.stderr[-600:]}")
    print("OK token vazio e token ausente abortam a inicializacao")


def test_token_curto_nao_sobe() -> None:
    r = _importa_server("t" * 63)
    assert r.returncode != 0, (
        "token de 63 chars subiu — o mínimo da casa é 64 (`secrets.token_hex(32)`), e "
        "token curto em produção é rascunho que vazou.")
    r_ok = _importa_server(TOKEN_OK)
    assert r_ok.returncode == 0, (
        f"token de 64 chars NÃO subiu — a guarda está recusando token válido:\n"
        f"{r_ok.stderr[-600:]}")
    print("OK 63 chars recusado, 64 chars aceito")


def _resposta(token_enviado: bytes | None, caminho: str = "/mcp") -> int:
    """Dirige `_BearerASGI` com scope ASGI cru. Devolve o status, ou 0 se passou adiante."""
    import server as S  # noqa: PLC0415 — importado aqui para o env acima já valer

    passou: list[bool] = []

    async def app_interna(scope, receive, send):  # noqa: ANN001, ARG001
        passou.append(True)

    guarda = S._BearerASGI(app_interna, TOKEN_OK)
    enviados: list[dict] = []

    async def send(msg):  # noqa: ANN001
        enviados.append(msg)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    headers = [] if token_enviado is None else [(b"authorization", token_enviado)]
    scope = {"type": "http", "path": caminho, "headers": headers, "method": "POST"}
    asyncio.run(guarda(scope, receive, send))
    if passou:
        return 0
    return next(m["status"] for m in enviados if m["type"] == "http.response.start")


def test_checagem_acontece_sempre() -> None:
    assert _resposta(None) == 401, "requisição sem Authorization passou"
    assert _resposta(b"Bearer errado") == 401, "token errado passou"
    assert _resposta(b"Bearer " + (b"t" * 63)) == 401, "token quase certo (prefixo) passou"
    assert _resposta(b"Bearer " + TOKEN_OK.encode()) == 0, "token correto foi recusado"
    print("OK 401 sem token, com token errado e com prefixo; passa so com o token certo")


def test_healthz_continua_aberto() -> None:
    assert _resposta(None, "/healthz") == 0, (
        "/healthz passou a exigir token — o healthcheck do docker-compose.mcp.yml chama "
        "esse caminho sem cabeçalho e marcaria o container unhealthy.")
    print("OK /healthz segue aberto para o healthcheck")


def _resposta_teto(guarda, caminho: str = "/mcp") -> int:
    """Uma passada pelo `_TetoASGI`. Devolve o status, ou 0 se passou adiante."""
    passou: list[bool] = []

    async def app_interna(scope, receive, send):  # noqa: ANN001, ARG001
        passou.append(True)

    enviados: list[dict] = []

    async def send(msg):  # noqa: ANN001
        enviados.append(msg)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    guarda.app = app_interna
    scope = {"type": "http", "path": caminho, "headers": [], "method": "POST"}
    asyncio.run(guarda(scope, receive, send))
    if passou:
        return 0
    return next(m["status"] for m in enviados if m["type"] == "http.response.start")


def test_teto_entra_na_cadeia_nos_dois_modos() -> None:
    """A razão de o teto ser middleware próprio: em `AUTH_MODE=google` o `_BearerASGI` não
    entra na cadeia, e o teto morava dentro dele — o conector publicado na internet era o
    único sem limite. Esta prova é de FONTE porque as duas pernas do `if` não coexistem no
    mesmo processo: qual delas roda é decidido no import, pelo env."""
    import inspect  # noqa: PLC0415

    import server as S  # noqa: PLC0415

    fonte = inspect.getsource(S)
    assert "app = _TetoASGI(_base)" in fonte, (
        "a perna `AUTH_MODE=google` voltou a montar o app sem o teto — o conector exposto "
        "na internet ficaria o único sem limite de requisições.")
    assert "_BearerASGI(_TetoASGI(_base)" in fonte, (
        "a perna bearer perdeu o teto, ou inverteu a ordem. A auth fica POR FORA: assim só "
        "requisição autenticada consome cota e inundação anônima não tranca quem tem token.")
    print("OK o teto entra na cadeia nas duas pernas, com a auth por fora no bearer")


def test_teto_recusa_no_estouro_e_poupa_healthz() -> None:
    import server as S  # noqa: PLC0415

    rpm_real = S._RPM
    S._RPM = 3
    try:
        guarda = S._TetoASGI(None)
        assert [_resposta_teto(guarda) for _ in range(3)] == [0, 0, 0], (
            "recusou antes de estourar o teto")
        assert _resposta_teto(guarda) == 429, "a 4a chamada com teto 3 não foi recusada"
        assert _resposta_teto(guarda, "/healthz") == 0, (
            "/healthz levou 429 — o healthcheck do compose marcaria o container unhealthy "
            "por causa de tráfego que chegou em outra rota.")
    finally:
        S._RPM = rpm_real
    print("OK teto recusa na 4a com _RPM=3, e /healthz fica fora da conta")


def test_comparacao_em_tempo_constante() -> None:
    import inspect  # noqa: PLC0415

    import server as S  # noqa: PLC0415

    fonte = inspect.getsource(S._BearerASGI.__call__)
    assert "compare_digest" in fonte, (
        "a comparação do token voltou a ser `==`/`!=`: ela retorna na primeira divergência "
        "e o tempo de resposta entrega o prefixo correto, byte a byte.")
    print("OK comparacao do token em tempo constante")


if __name__ == "__main__":
    falhou = 0
    for fn in (test_token_vazio_nao_sobe, test_token_curto_nao_sobe,
               test_checagem_acontece_sempre, test_healthz_continua_aberto,
               test_comparacao_em_tempo_constante,
               test_teto_entra_na_cadeia_nos_dois_modos,
               test_teto_recusa_no_estouro_e_poupa_healthz):
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            falhou += 1
            print(f"FAIL {fn.__name__}\n  {e}")
    print("TEST test_bearer_fail_closed " + ("FAIL" if falhou else "PASS"))
    sys.exit(1 if falhou else 0)
