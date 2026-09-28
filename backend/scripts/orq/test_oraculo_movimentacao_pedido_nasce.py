"""Oráculo — o pedido de movimentação NASCE pela tela, e quem pede não aprova (28/09/2026).

REGRA QUE AFIRMA (duas, nenhuma é fotografia de entrega):
  R1. Preencher no formulário `movimentacao-nova` SÓ os campos que ele mesmo marca com `*`, e
      deixar todo o resto exatamente como a tela entrega, TEM QUE nascer um pedido `pendente` em
      `op_movimentacao_pedidos` — sem tocar em `employee_alocacoes`.
  R2. Quem PEDIU não pode APROVAR o próprio pedido (403). Outra pessoa do DP passa dessa trava.

Por que existe. `op_movimentacao_pedidos` tinha 0 linhas e `employee_alocacoes` tinha 0 linhas
escritas pelo app (`created_by IS NOT NULL` = 0) — a capacidade inteira estava viva e inalcançada,
por DOIS motivos que só aparecem chamando o endpoint de verdade:
  · `condominio_id` e `funcao` não tinham `*` no form, e `_checar_entrada` os exige → 400
    «Colaborador, condomínio e função são obrigatórios» em 100% do caminho feliz (medido por curl
    em 28/09/2026). É o mesmo defeito que já matou a tela de CND (`caixa` × `certidao_negativa_fgts`).
  · o default de `pedir_aprovacao` era "" ("Automático"), e «automático» se decidia por
    `e_dp` = tem `module:dp`. Dos 78 usuários ativos, TODOS os que alcançam o módulo Operacional
    têm `module:dp` — inclusive o Orlailson (gerente_operacional), que é quem PEDE. O ramo
    `pedir()` era inalcançável no default: alocava direto, sem pedido e sem aprovação.
E a trava de papel não era parede: com `module:dp`, o próprio solicitante aprovava o que pediu.

O oráculo lê o formulário de onde o FRONT lê (o payload de `/redesign/data/operacional`), não do
código — então pega qualquer campo NOVO que alguém acrescente com default que o validador recusa,
e pega o dia em que alguém devolver o default de `pedir_aprovacao` para "alocar direto".

Não escreve em `employee_alocacoes` NUNCA: a fixture é um colaborador que JÁ tem a alocação ativa
idêntica, então `aprovar()` só pode chegar a 409 («já existe alocação ativa igual») — o que é
justamente a irmã de caminho feliz da R2 (passou a trava de identidade e parou noutra). A contagem
de `employee_alocacoes` é conferida antes e depois. O pedido criado é apagado e a ausência é
provada por leitura.

Estado medido no nascimento (produção, 28/09/2026): R1 vermelha (400 em 100% dos envios),
R2 vermelha (`aprovar` não olhava `pedido_por`).

Roda no HOST:  python3 backend/scripts/orq/test_oraculo_movimentacao_pedido_nasce.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("QA_API", "http://127.0.0.1:8080")
DOCKER = os.environ.get("QA_DOCKER", "/usr/bin/docker")
PG = os.environ.get("QA_PG", "conecta-pro-postgres")
BACKEND = os.environ.get("QA_BACKEND", "conecta-pro-backend")

MODULO = "operacional"
TELA = "movimentacao-nova"
FIX = "FIXTURE ORACULO MOV PEDIDO"
PEDE = "jjesus@conectamais.pro"  # quem pede (admin, tem module:dp — era exatamente o furo)
APROVA = "pjesus@conectamais.pro"  # outra pessoa do DP

SQL_FIXTURE = (
    "SELECT a.employee_id::text, a.condominio_id::text, coalesce(a.posto_id::text,''), a.funcao "
    "FROM employee_alocacoes a JOIN employees e ON e.id = a.employee_id "
    "WHERE a.ativo AND a.posto_id IS NOT NULL ORDER BY e.nome LIMIT 1"
)
SQL_N_ALOC = "SELECT count(*) FROM employee_alocacoes"
SQL_N_PEDIDO = "SELECT count(*) FROM op_movimentacao_pedidos WHERE observacao LIKE '" + FIX + "%'"
SQL_STATUS = "SELECT status FROM op_movimentacao_pedidos WHERE observacao LIKE '" + FIX + "%'"
SQL_LIMPA = "DELETE FROM op_movimentacao_pedidos WHERE observacao LIKE '" + FIX + "%'"


def _sql(q: str) -> str:
    r = subprocess.run(  # noqa: S603
        [DOCKER, "exec", PG, "psql", "-U", "postgres", "-d", "conecta_pro", "-t", "-A", "-F", "|", "-c", q],
        capture_output=True,
        timeout=120,
        check=False,
    )
    return r.stdout.decode("utf8", "ignore").strip()


def _token(email: str) -> str | None:
    """Assina o token no próprio backend: o oráculo afirma o formulário e a trava, não a senha."""
    code = (
        "import asyncio;from sqlalchemy import text;from core.database import async_session_factory;"
        "from core.auth.jwt import create_access_token\n"
        "async def m():\n"
        " async with async_session_factory() as d:\n"
        f"  u=(await d.execute(text(\"SELECT id::text FROM users WHERE email='{email}'\"))).scalar()\n"
        "  print(create_access_token(u) if u else '')\n"
        "asyncio.run(m())"
    )
    r = subprocess.run(  # noqa: S603
        [DOCKER, "exec", "-e", "PYTHONPATH=/app", BACKEND, "python", "-c", code],
        capture_output=True,
        timeout=180,
        check=False,
    )
    for ln in reversed(r.stdout.decode("utf8", "ignore").strip().splitlines()):
        if ln.count(".") == 2 and ln.startswith("ey"):
            return ln.strip()
    return None


def _get(path: str, tok: str) -> dict:
    req = urllib.request.Request(f"{API}{path}", headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310  # nosec B310 - QA local
        return json.load(r)


def _post(path: str, tok: str, body: dict) -> tuple[int, str]:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:  # noqa: S310  # nosec B310 - QA local
            return r.status, r.read().decode("utf8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf8", "ignore")


def _achar_tela(payload: dict, tela: str) -> dict | None:
    """A tela pode estar solta em `screens` ou ser aba de um grupo (`montar_grupos` stuba a solta)."""
    sc = payload.get("screens") or {}
    for nome, scr in sc.items():
        if nome == tela and isinstance(scr, dict) and scr.get("fields"):
            return scr
        for tab in (scr or {}).get("tabs", []) if isinstance(scr, dict) else []:
            if isinstance(tab, dict) and tab.get("id") == tela and isinstance(tab.get("screen"), dict):
                return tab["screen"]
    return None


def _preencher(campos: list[dict], fixture: dict) -> tuple[dict, list[str]]:
    """O payload que o front manda: default do campo para TODO mundo; os `*` sem default, com o
    mínimo plausível (o valor da fixture quando o campo é uma escolha de cadastro, senão a primeira
    opção). Nada de valor esperto: se o form não pode ser preenchido com o óbvio, é ele que erra."""
    body, marcados = {}, []
    for f in campos:
        k, tipo = f.get("key"), f.get("type")
        v = f.get("value") or ""
        if str(f.get("label", "")).rstrip().rstrip(" —").endswith("*") or "*" in str(f.get("label", "")):
            marcados.append(k)
            if not v:
                if k in fixture:
                    v = fixture[k]
                elif tipo == "select":
                    v = next((o.get("value") for o in f.get("options", []) if o.get("value")), "")
                elif tipo == "date":
                    v = fixture.get("_hoje", "")
                else:
                    v = "teste"
        body[k] = v
    return body, marcados


def main() -> int:
    falhas: list[str] = []
    # ⚠️ 28/09/2026 — mede de FORA (docker exec para psql e para assinar token), só roda no host.
    # A varredura diária globa `test_*.py` dentro do contêiner, onde não há /usr/bin/docker; sem
    # esta saída o oráculo viraria VERMELHO crônico por FileNotFoundError. 3 = BLOQUEADO.
    if not os.path.exists(DOCKER):
        print(f"BLOQUEADO: {DOCKER} não existe — este oráculo mede de fora e só roda no host")
        return 3

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    tok_pede, tok_aprova = _token(PEDE), _token(APROVA)
    if not tok_pede or not tok_aprova:
        print(f"  ✗ (R1,R2) não consegui token de {PEDE} / {APROVA}")
        print("TOTAL falhas movimentação pedido nasce: 1")
        return 1

    linha = _sql(SQL_FIXTURE)
    if linha.count("|") != 3:
        print("  ✗ (R1,R2) fixture impossível: nenhuma alocação ativa com posto para usar de âncora")
        print("TOTAL falhas movimentação pedido nasce: 1")
        return 1
    emp, cond, posto, funcao = linha.split("|")
    fixture = {"employee_id": emp, "condominio_id": cond, "posto_id": posto, "funcao": funcao}

    _sql(SQL_LIMPA)
    n_aloc_antes = _sql(SQL_N_ALOC)
    try:
        tela = _achar_tela(_get(f"/api/v1/redesign/data/{MODULO}", tok_pede), TELA)
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ (R1) não consegui ler /redesign/data/{MODULO}: {type(exc).__name__}: {exc}")
        print("TOTAL falhas movimentação pedido nasce: 1")
        return 1
    if not tela or not tela.get("submit", {}).get("endpoint"):
        ok(False, f"(R1) a tela `{TELA}` não chega no payload de `{MODULO}` com submit — ninguém consegue pedir")
        print(f"TOTAL falhas movimentação pedido nasce: {len(falhas)}")
        return 1

    fixture["_hoje"] = next((f.get("value") for f in tela["fields"] if f.get("type") == "date" and f.get("value")), "")
    body, marcados = _preencher(tela["fields"], fixture)
    body["observacao"] = FIX + " — apagado pelo próprio oráculo"
    endpoint = tela["submit"]["endpoint"]
    print(f"  · form declara obrigatórios: {', '.join(marcados)}")
    print(f"  · POST {endpoint}")

    try:
        # ── R1: o caminho feliz do formulário nasce pendente, sem mexer na alocação ──
        status, corpo = _post(endpoint, tok_pede, body)
        ok(
            status == 200,
            f"(R1) só os campos `*` do form são ACEITOS pelo endpoint que ele declara — HTTP {status} {corpo[:200]}",
        )
        pid = (json.loads(corpo).get("id") or "") if status == 200 else ""
        ok(
            status == 200 and json.loads(corpo).get("status") == "pendente",
            f"(R1) o default do form gera PEDIDO pendente (não aloca direto) — corpo {corpo[:160]}",
        )
        ok(
            _sql(SQL_STATUS) == "pendente",
            f"(R1) o banco confirma `pendente` em op_movimentacao_pedidos (leitura posterior) — lido {_sql(SQL_STATUS)!r}",
        )
        ok(
            _sql(SQL_N_ALOC) == n_aloc_antes,
            f"(R1) `pedir` não tocou em employee_alocacoes — antes {n_aloc_antes}, depois {_sql(SQL_N_ALOC)}",
        )
        if not pid:
            print(f"TOTAL falhas movimentação pedido nasce: {len(falhas)}")
            return 1

        # ── R2: quem pediu não aprova; outra pessoa do DP passa dessa trava ──
        # Pedido PRÓPRIO para esta regra, com `posto_id` preenchido (o form deixa o posto
        # opcional, e sem ele `alocar` não reconhece a duplicata e ALOCA DE VERDADE — foi o que
        # a primeira versão deste oráculo fez, escrevendo em employee_alocacoes). Com posto igual
        # ao da alocação ativa, `alocar` para em 409 ANTES de qualquer UPDATE/INSERT: a aprovação
        # por outra pessoa prova que passou da trava de identidade sem mover ninguém de posto.
        body2 = dict(body)
        body2["posto_id"] = fixture["posto_id"]
        st2, c2 = _post(endpoint, tok_pede, body2)
        pid2 = (json.loads(c2).get("id") or "") if st2 == 200 else ""
        if not pid2:
            ok(False, f"(R2) não consegui criar o pedido âncora (posto igual ao atual) — HTTP {st2} {c2[:180]}")
            print(f"TOTAL falhas movimentação pedido nasce: {len(falhas)}")
            return 1
        st_self, c_self = _post(f"/api/v1/redesign/action/movimentacao-aprovar?pedido_id={pid2}", tok_pede, {})
        ok(st_self == 403, f"(R2) quem PEDIU não aprova o próprio pedido — HTTP {st_self} {c_self[:180]}")
        st_out, c_out = _post(f"/api/v1/redesign/action/movimentacao-aprovar?pedido_id={pid2}", tok_aprova, {})
        ok(
            st_out == 409,
            f"(R2, irmã de caminho feliz) OUTRA pessoa do DP passa da trava de identidade e só para na "
            f"duplicata — esperado 409, veio HTTP {st_out} {c_out[:180]}",
        )
        ok(
            _sql(SQL_N_ALOC) == n_aloc_antes,
            f"(R2) nenhuma das duas tentativas escreveu em employee_alocacoes — "
            f"antes {n_aloc_antes}, depois {_sql(SQL_N_ALOC)}",
        )
        ok(
            _sql(SQL_STATUS) == "pendente\npendente",
            f"(R2) os dois pedidos seguem PENDENTES (nada foi decidido) — lido {_sql(SQL_STATUS)!r}",
        )
    finally:
        _sql(SQL_LIMPA)
        restou = _sql(SQL_N_PEDIDO)
        ok(restou == "0", f"(limpeza) a fixture saiu do banco, provado por leitura — restaram {restou!r}")

    print(f"TOTAL falhas movimentação pedido nasce: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
