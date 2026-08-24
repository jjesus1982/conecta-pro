#!/usr/bin/env python3
"""Critério de aceite EXECUTÁVEL do Bartolo — o agente que OPERA o Conecta PRO.

Sai 0 só quando as 8 condições da ordem T4 passam. Enquanto sair vermelho, não fechou.

As 8, como foram escritas na ordem:

    1. roteamento   0 tool que toca dado pessoal/dinheiro roteada pelo Hermes
    2. identidade   0 execução de tool sensível com a conta de serviço
    3. serviço      a conta de serviço do MCP NÃO é jjesus; escopo mínimo declarado
    4. autoconhec.  "o que você sabe fazer" vem do tool_registry, não de texto fixo
    5. beats        checar_beats sem achados
    6. LLM          0 falha recorrente em llm_usage nas últimas 24h
    7. travas       repositorio · vocabulario · rotas_frontend == 0 em ai/
    8. oráculos     os test_tools_* e test_u2_* verdes
    9. caso de uso  um usuário COMUM pergunta pelo próprio dado, pelo caminho real, e RECEBE

⚠️ As condições 1 e 2 medem coisas DIFERENTES e é fácil confundi-las. A 1 pergunta *o que
chega* ao agente (catálogo); a 2 pergunta *como ele age* (identidade). Um agente pode receber
só tool inofensiva e ainda assim agir como o dono do sistema — F1 fecha a primeira, F2 a
segunda. Este gate nasce com a 2 VERMELHA de propósito: a F2 não foi construída, e um gate
que só mede o que já está pronto é enfeite.

Uso (rode do HOST — ele delega ao container o que depende do banco):
    python3 backend/scripts/qa/fechado_bartolo.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

RAIZ = "/opt/conecta-pro"
MCP = os.path.join(RAIZ, "mcp-server")
NO_CONTAINER = os.path.isdir("/app/modules") and not os.path.isdir(
    os.path.join(RAIZ, "backend/scripts/qa"))

#: Conector que o AGENTE usa. O público (`conecta-pro-mcp`) é o Cowork do Jordan, onde a
#: pessoa lê e decide na hora — medir a parede lá seria medir a régua errada.
CONECTOR_AGENTE = "conecta-pro-mcp-internal"

#: Grupos do `tool_scopes` cujo conteúdo é DADO PESSOAL (LGPD): holerite, ponto, ASO,
#: dependentes. Nenhum deles pode estar no escopo do agente enquanto a F2 não propagar a
#: identidade de quem pergunta — sem isso o agente leria a folha alheia com a conta de serviço.
GRUPOS_PESSOAIS = {"dp", "rh"}


#: Prefixo que uma condição usa para dizer "não consegui medir" — diferente de "reprovou".
#: Sem essa distinção, medição atropelada (deploy no meio da corrida, backend aquecendo) lê
#: exatamente igual a parede quebrada, e quem lê o placar não sabe qual dos dois aconteceu.
#: NÃO VERIFICADO continua NÃO PASSANDO — fail-closed —, só para de mentir sobre a causa.
NAO_MEDIDO = "!nao-medido!"


def _ok(cond: bool, titulo: str, detalhe: str = "") -> bool:
    if detalhe.startswith(NAO_MEDIDO):
        print(f"  ⚠️  {titulo} — NÃO VERIFICADO: {detalhe[len(NAO_MEDIDO):]}")
        return False
    print(f"  {'✅' if cond else '❌'} {titulo}" + (f" — {detalhe}" if detalhe else ""))
    return cond


def _docker(*args: str, timeout: int = 900) -> str:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")


def _docker_json(*args: str, timeout: int = 420, marcador: str = "J"):
    """Roda no container e extrai o bloco marcado, com UMA repetição.

    Importar o app leva ~40-75s e logo depois de um bake o backend ainda está aquecendo: a
    primeira tentativa estoura e a condição reprovaria por motivo errado. Devolve None quando
    as duas tentativas falham — aí é NÃO VERIFICADO, nunca "reprovou".
    """
    for _tentativa in (1, 2):
        try:
            saida = _docker(*args, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        m = re.search(f"<<{marcador}>>(.*?)<<{marcador}>>", saida, re.S)
        if m:
            return json.loads(m.group(1))
    return None


def _env_do(container: str, chave: str) -> str:
    bruto = _docker("inspect", container, "--format", "{{json .Config.Env}}", timeout=60).strip()
    try:
        env = dict(e.split("=", 1) for e in json.loads(bruto) if "=" in e)
    except Exception:  # noqa: BLE001
        return ""
    return env.get(chave, "")


# ── 1 · roteamento ────────────────────────────────────────────────────────────────────
def _c1_roteamento() -> tuple[bool, str]:
    """O que o agente RECEBE. Dois fatos, nenhuma heurística de nome.

    (a) nenhum grupo de dado pessoal no escopo servido;
    (b) toda tool servida que EXECUTA (read/write_low) não é uma das consequentes — as
        consequentes são `propose` e a parede F1 as barra.
    """
    sys.path.insert(0, MCP)
    try:
        from gate_propose import CONSEQUENCIAS, classe_de  # noqa: PLC0415
        from tool_scopes import escopos_da_tool  # noqa: PLC0415
        from tool_risk_manifest import TOOL_RISK  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        return False, f"não consegui ler o manifesto/escopos: {e}"

    escopo = {g.strip() for g in (_env_do(CONECTOR_AGENTE, "MCP_ESCOPO") or "").split(",")
              if g.strip()}
    if not escopo:
        return False, (f"{CONECTOR_AGENTE} sem MCP_ESCOPO — sem escopo declarado o agente "
                       f"recebe o catálogo inteiro")

    pessoais = sorted(escopo & GRUPOS_PESSOAIS)
    servidas = [t for t in TOOL_RISK if escopos_da_tool(t) in escopo]
    executam = [t for t in servidas if classe_de(t) in ("read", "write_low")]
    consequentes = sorted(t for t in executam if t in CONSEQUENCIAS)

    if pessoais:
        return False, f"grupo(s) de dado pessoal no escopo do agente: {pessoais}"
    if consequentes:
        return False, f"tool consequente EXECUTÁVEL pelo agente: {consequentes[:6]}"
    return True, (f"{len(servidas)} servidas, {len(executam)} executáveis, 0 consequente; "
                  f"escopo={sorted(escopo)}")


# ── 2 · identidade (F2) ───────────────────────────────────────────────────────────────
def _c2_identidade() -> tuple[bool, str]:
    """Como o agente AGE. Não basta o mecanismo existir: ele tem de RECUSAR.

    Duas medições, porque uma só engana. O oráculo prova a régua (o que conta como sensível);
    a sonda ao vivo prova o comportamento — chama uma tool sensível SEM identidade contra o
    conector que está no ar e exige recusa. Marcador no fonte não serve: a primeira versão
    desta condição procurava um nome de variável em `server.py`, e nome de variável não
    recusa nada.
    """
    r = subprocess.run(["docker", "exec", CONECTOR_AGENTE, "python3", "/app/test_identidade.py"],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        ruins = [ln for ln in r.stdout.splitlines() if ln.startswith("FAIL")]
        return False, f"oráculo de identidade reprovou: {ruins[:3]}"

    sonda = """
import asyncio, os
async def main():
    from fastmcp import Client
    from fastmcp.client.transports import StreamableHttpTransport
    h = {"Authorization": "Bearer " + os.environ["MCP_AUTH_TOKEN"]}
    try:
        async with Client(StreamableHttpTransport(
                "http://localhost:8788/mcp", headers=h)) as c:
            await c.call_tool("resumo_financeiro", {})
        print("<<R>>EXECUTOU<<R>>")
    except Exception as e:
        print("<<R>>" + ("RECUSOU" if "identidade" in str(e) else "OUTRO:" + str(e)[:70]) + "<<R>>")
asyncio.run(main())
"""
    saida = _docker("exec", CONECTOR_AGENTE, "python3", "-c", sonda, timeout=300)
    m = re.search(r"<<R>>(.*?)<<R>>", saida, re.S)
    if not m:
        return False, "a sonda ao vivo não respondeu — condição NÃO verificada"
    veredito = m.group(1).strip()
    if veredito != "RECUSOU":
        return False, f"tool sensível SEM identidade -> {veredito}"
    return True, "oráculo 6/6 e a sonda ao vivo recusou tool sensível sem identidade"


# ── 3 · conta de serviço ──────────────────────────────────────────────────────────────
def _c3_conta_de_servico() -> tuple[bool, str]:
    usuario = _env_do(CONECTOR_AGENTE, "ERP_USER")
    escopo = _env_do(CONECTOR_AGENTE, "MCP_ESCOPO")
    if not usuario:
        return False, f"{CONECTOR_AGENTE} sem ERP_USER declarado"
    if usuario.split("@")[0].lower() in ("jjesus", "pjesus"):
        return False, (f"o agente age como {usuario} — a conta de uma PESSOA. O que ele fizer "
                       f"fica no nome dela na auditoria")
    if not escopo:
        return False, f"conta {usuario} sem escopo mínimo declarado (MCP_ESCOPO vazio)"
    return True, f"{usuario}, escopo mínimo declarado ({escopo})"


# ── 4 · autoconhecimento ──────────────────────────────────────────────────────────────
def _c4_autoconhecimento() -> tuple[bool, str]:
    """Tem de vir do registro. Lista escrita à mão é a mesma casca com nome novo."""
    d = _docker_json("exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend", "python3", "-c",
                    "import asyncio, json;"
                    "import modules.ai.conversation.controllers.consultor_escopado_controller as c;"
                    "from modules.ai.conversation.services.orquestrador.tool_registry import get_tool;"
                    "from modules.ai.conversation.services.orquestrador.read_dispatcher import _READ_OPS;"
                    "t = get_tool('o_que_voce_faz');"
                    "print('<<J>>' + json.dumps({'existe': t is not None,"
                    " 'modulos_registrados': sorted(_READ_OPS)}) + '<<J>>')",
                    timeout=420)
    if d is None:
        return False, NAO_MEDIDO + "não consegui interrogar o registro no container (2 tentativas)"
    if not d["existe"]:
        return False, "tool `o_que_voce_faz` NÃO registrada"

    # a fonte não pode carregar o catálogo escrito à mão: tem de derivar dos dispatchers
    fonte = os.path.join(
        RAIZ, "backend/modules/ai/conversation/services/orquestrador/tools_autoconhecimento.py")
    if not os.path.exists(fonte):
        return False, "tools_autoconhecimento.py ausente"
    s = open(fonte, encoding="utf-8").read()
    if "_READ_OPS" not in s or "_ACOES" not in s:
        return False, "a tool não lê os dispatchers — está descrevendo de texto fixo"
    return True, f"deriva de _READ_OPS/_ACOES ({len(d['modulos_registrados'])} módulos vivos)"


# ── 5 · beats ─────────────────────────────────────────────────────────────────────────
def _c5_beats() -> tuple[bool, str]:
    saida = _docker("exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                    "python3", "/app/scripts/qa/checar_beats.py", timeout=600)
    if "No such file" in saida:
        return False, "checar_beats.py não está na imagem"
    achados = [ln for ln in saida.splitlines() if ln.strip().startswith(("x ", "- ", "❌"))]
    return not achados, (f"{len(achados)} achado(s)" if achados else "sem achados")


# ── 6 · LLM ───────────────────────────────────────────────────────────────────────────
def _c6_llm() -> tuple[bool, str]:
    """Falha RECORRENTE, não falha isolada: 1.110 erros 401 em 3h passaram despercebidos hoje
    justamente porque ninguém agregava. Recorrente = mesma origem+erro 3+ vezes em 24h."""
    snippet = '''
import json
from sqlalchemy import text
from core.database.session import SyncSessionLocal
SQL = """
    SELECT origem, left(coalesce(erro, ''), 60) AS e, count(*) AS n,
           max(criado_em) AS ultimo
    FROM llm_usage
    WHERE ok = false AND criado_em > now() - interval '24 hours'
    GROUP BY 1, 2 HAVING count(*) >= 3 ORDER BY 3 DESC LIMIT 8
"""
with SyncSessionLocal() as s:
    r = s.execute(text(SQL)).fetchall()
print("<<J>>" + json.dumps([[x[0], x[1], int(x[2]), str(x[3])] for x in r]) + "<<J>>")
'''
    linhas = _docker_json("exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                          "python3", "-c", snippet, timeout=300)
    if linhas is None:
        return False, NAO_MEDIDO + "não consegui ler llm_usage (2 tentativas)"
    if linhas:
        pior = linhas[0]
        # O ÚLTIMO é o que separa "sangrando agora" de "já parou e a janela ainda lembra".
        # Sem essa data, um gate vermelho por defeito já corrigido vira sino que ninguém escuta.
        return False, (f"{len(linhas)} recorrente(s); pior: {pior[0]} ×{pior[2]} ({pior[1]}) "
                       f"— último em {pior[3][:16]}")
    return True, "nenhuma falha recorrente"


# ── 7 · travas, filtradas ao território do agente ─────────────────────────────────────
def _c7_travas() -> tuple[bool, str]:
    partes: list[str] = []

    r = subprocess.run([sys.executable, f"{RAIZ}/backend/scripts/qa/checar_repositorio.py"],
                       capture_output=True, text=True, timeout=900, cwd=RAIZ)
    m = re.search(r"──\s*ai:\s*(\d+)\s*chamada", r.stdout + r.stderr)
    n_repo = int(m.group(1)) if m else 0
    partes.append(f"repositorio={n_repo}")

    voc = _docker("exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                  "python3", "/app/scripts/qa/checar_vocabulario.py", timeout=900)
    n_voc = sum(1 for ln in voc.splitlines()
                if "[CRITICO]" in ln and ("/ai/" in ln or "modules/ai" in ln))
    partes.append(f"vocabulario={n_voc}")

    r = subprocess.run([sys.executable, f"{RAIZ}/backend/scripts/qa/checar_rotas_frontend.py"],
                       capture_output=True, text=True, timeout=900, cwd=RAIZ)
    n_rot = sum(1 for ln in (r.stdout + r.stderr).splitlines()
                if "/ai/" in ln and ln.strip().startswith(("x", "-", "❌")))
    partes.append(f"rotas_frontend={n_rot}")

    total = n_repo + n_voc + n_rot
    return total == 0, " · ".join(partes)


# ── 8 · oráculos do orquestrador ──────────────────────────────────────────────────────
def _c8_oraculos() -> tuple[bool, str]:
    lista = _docker("exec", "conecta-pro-backend", "sh", "-c",
                    "ls /app/scripts/orq/test_tools_*.py /app/scripts/orq/test_u2_*.py "
                    "2>/dev/null", timeout=120).split()
    lista = [x for x in lista if x.endswith(".py")]
    if not lista:
        return False, "nenhum test_tools_*/test_u2_* na imagem"
    falharam: list[str] = []
    for caminho in lista:
        r = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                            "python3", caminho], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            falharam.append(os.path.basename(caminho))
    return not falharam, (f"{len(lista) - len(falharam)}/{len(lista)} verdes"
                          + (f"; falhou: {falharam[:5]}" if falharam else ""))


# ── 9 · caso de uso ───────────────────────────────────────────────────────────────────
def _c9_caso_de_uso() -> tuple[bool, str]:
    """As 8 anteriores medem PAREDE e DRIFT. Nenhuma mede se alguém consegue USAR o Bartolo.

    O gate poderia dar 8/8 com o agente servindo 4 ferramentas e o caso de uso principal
    quebrado — é a família do `fechado_operacional`, que deu 7/7 escondendo assinatura numa
    rota 404. Provar que o porteiro é BARRADO no que não é dele prova a parede; provar que ele
    RECEBE o que é dele prova o produto. Só o negativo estava provado.
    """
    r = subprocess.run(["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
                        "python3", "/app/scripts/orq/test_caso_de_uso_porteiro.py"],
                       capture_output=True, text=True, timeout=600)
    linhas = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    veredito = next((ln for ln in linhas if ln.startswith(("PASS", "FAIL"))), "sem veredito")
    recebeu = next((ln for ln in linhas if ln.startswith("no banco")), "")
    return r.returncode == 0, (veredito[:150] + (f" · {recebeu[:60]}" if recebeu else ""))


CONDICOES = [
    ("1 · roteamento: 0 tool pessoal/consequente executável pelo agente", _c1_roteamento),
    ("2 · identidade: agente NÃO age com a conta de serviço em tool sensível", _c2_identidade),
    ("3 · serviço: conta própria, não a de uma pessoa, com escopo mínimo", _c3_conta_de_servico),
    ("4 · autoconhecimento: vem do tool_registry, não de texto fixo", _c4_autoconhecimento),
    ("5 · beats: checar_beats sem achados", _c5_beats),
    ("6 · LLM: 0 falha recorrente em llm_usage (24h)", _c6_llm),
    ("7 · travas: repositorio · vocabulario · rotas_frontend == 0 em ai/", _c7_travas),
    ("8 · oráculos: test_tools_* e test_u2_* verdes", _c8_oraculos),
    ("9 · caso de uso: usuário COMUM pergunta pelo próprio dado e RECEBE", _c9_caso_de_uso),
]


def main() -> int:
    if NO_CONTAINER:
        print("⚠️  rode do HOST: este gate precisa de docker/git e delega o banco ao container")
        return 2
    print("FECHADO_BARTOLO — critério de aceite executável (ordem T4)\n")
    res: list[bool] = []
    for titulo, fn in CONDICOES:
        try:
            ok, det = fn()
        except Exception as e:  # noqa: BLE001
            # Condição que morre calada conta como REPROVADA: um gate que engole exceção
            # devolve verde por ausência de medição, que é o pior verde que existe.
            ok, det = False, f"a checagem estourou ({type(e).__name__}: {str(e)[:110]})"
        res.append(_ok(ok, titulo, det))

    print(f"\n{sum(res)}/{len(res)} condições")
    if not all(res):
        print("NÃO FECHOU — o que está vermelho é trabalho, não observação.")
        return 1
    print("FECHADO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
