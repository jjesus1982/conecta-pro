#!/usr/bin/env python3
"""O conector MCP serve o que ele DIZ que serve? — medido pela rota, não pelo log.

🔴 O que originou (11/09/2026). O filtro de escopo chamava `mcp.remove_tool(nome)` dentro de
um `except Exception: pass` e imprimia quantas ferramentas "sobraram" por ARITMÉTICA. Só que
`remove_tool` não existe no fastmcp 4.0.3 — é API da 3.4. Toda chamada levantava
AttributeError, o except engolia, e o conector do kit anunciava

    [mcp] escopo=ged,fiscal · servindo 42 de 254 ferramentas

enquanto o `tools/list` dele devolvia **266**, com `fechar_folha`, `criar_lead` e as
ferramentas de dinheiro à vista do agente. A proteção declarada daquele conector, no próprio
docker-compose, era "quem o protege é o ESCOPO".

Por isso esta trava NÃO lê o log nem o código: ela abre uma sessão MCP em cada conector e
pergunta `tools/list`, que é o que o agente do outro lado enxerga. Log é o que o programa
diz de si; a rota é o que ele faz.

Confere três coisas por conector:
  1. o número servido bate com o escopo declarado em `tool_scopes`;
  2. nenhuma ferramenta FORA do escopo aparece na lista;
  3. as ferramentas proibidas de cada conector continuam ausentes (lista abaixo, explícita).

    python3 backend/scripts/qa/checar_escopo_mcp.py

Linha canônica: `TOTAL conectores servindo fora do escopo: N` (binária: N = 0).
"""
from __future__ import annotations

import json
import subprocess
import sys

#: Os conectores escopados. O do Cowork (`conecta-pro-mcp`) fica fora de propósito: serve o
#: catálogo inteiro para o Jordan autenticado por Google, e isso é decisão, não defeito.
CONECTORES = ("conecta-pro-mcp-pessoas", "conecta-pro-mcp-ged", "conecta-pro-mcp-internal")

#: O que um conector de IDENTIDADE PRÓPRIA nunca pode servir. Ali a parede de identidade está
#: desligada por desenho (o agente tem nome próprio e não repassa JWT humano), então quem
#: segura é só o escopo + o gate de aprovação — e estas não devem nem aparecer na lista.
#: Fecham o mês, calculam ou pagam dinheiro, ou mexem na vida contratual de alguém.
#:
#: ⚠️ Num conector de identidade REPASSADA a régua é outra e continua valendo: lá estas
#: ferramentas existem e são barradas por chamada (sem `x-usuario-token`, tool sensível não
#: executa). Aplicar a mesma lista aos dois seria confundir duas defesas diferentes — foi o
#: que esta trava fez na primeira versão, e ela acusou `propor_pagamento` no conector interno
#: como se fosse buraco, quando ali a parede é a identidade.
PROIBIDAS_EM_IDENTIDADE_PROPRIA = (
    "fechar_folha", "calcular_folha_todos", "exportar_folha_dominio",
    "calcular_verbas_rescisorias", "fechar_mes_ponto", "concluir_admissao",
    "propor_pagamento", "listar_beneficiarios_pix", "aceitar_proposta",
    "enviar_proposta", "criar_contrato", "assinar_contrato_empresa")

_PROVA = r'''
import json, os, urllib.request
B = os.environ["MCP_AUTH_TOKEN"]; URL = "http://127.0.0.1:8788/mcp"
sid = None
def call(p):
    global sid
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
         "Authorization": "Bearer " + B}
    if sid: h["Mcp-Session-Id"] = sid
    r = urllib.request.urlopen(urllib.request.Request(URL, data=json.dumps(p).encode(), headers=h), timeout=60)
    sid = r.headers.get("Mcp-Session-Id") or sid
    t = r.read().decode()
    for l in t.splitlines():
        if l.startswith("data: "): return json.loads(l[6:])
    return json.loads(t) if t.strip() else {}
call({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"trava","version":"1"}}})
urllib.request.urlopen(urllib.request.Request(URL, data=json.dumps({"jsonrpc":"2.0","method":"notifications/initialized"}).encode(),
    headers={"Content-Type":"application/json","Accept":"application/json, text/event-stream","Authorization":"Bearer "+B,"Mcp-Session-Id":sid}), timeout=30)
r = call({"jsonrpc":"2.0","id":2,"method":"tools/list"})
servidas = sorted(t["name"] for t in r["result"]["tools"])
# ⭐ BATER NA PORTA, não só olhar a lista. `remove_tool`, mesmo quando funcionava, só sumia
# com a ferramenta da LISTAGEM — quem soubesse o nome ainda chamava. O middleware promete
# recusar a CHAMADA, e esse ramo nunca tinha rodado: promessa, não parede.
# A batida é de LEITURA e fora do escopo de propósito: se um dia a parede falhar, o pior que
# acontece é uma consulta a mais — nunca uma escrita.
alvo = os.environ.get("BATIDA", "")
recusou = None
if alvo:
    rr = call({"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":alvo,"arguments":{}}})
    res = rr.get("result") or {}
    txt = "".join(str(c.get("text") or "") for c in (res.get("content") or []))
    recusou = bool(res.get("isError")) and "fora do escopo" in txt
print(json.dumps({"servidas": servidas, "batida": alvo, "recusou": recusou}))
'''


def _imagem_do_conector(container: str) -> str:
    """Data de criação da IMAGEM que este container roda — o terceiro dado.

    Ideia da sessão t6, depois de um drift check dar 4/4 ✅ com os quatro containers na imagem
    ANTERIOR (a build tinha falhado e a tag não se moveu): eles concordavam entre si e nenhum
    tinha o código novo. Igualdade responde "todos iguais?"; só a data responde "todos atuais?".
    """
    img = subprocess.run(  # noqa: S603
        ["/usr/bin/docker", "inspect", container, "--format", "{{.Image}}"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    if not img:
        return "?"
    criada = subprocess.run(  # noqa: S603
        ["/usr/bin/docker", "inspect", img, "--format", "{{.Created}}"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    return (criada[:16].replace("T", " ") or "?")


def _env_do_conector(container: str) -> dict[str, str]:
    """MCP_ESCOPO/MCP_MODO/MCP_IDENTIDADE do container que está NO AR — medido, não suposto.

    Ler do docker-compose diria o que deveria estar rodando; `docker inspect` diz o que está.
    """
    out = subprocess.run(  # noqa: S603
        ["/usr/bin/docker", "inspect", container, "--format", "{{json .Config.Env}}"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    env: dict[str, str] = {}
    for item in json.loads(out or "[]"):
        chave, _, valor = str(item).partition("=")
        if chave.startswith("MCP_"):
            env[chave] = valor
    return env


#: A ferramenta de LEITURA que vamos tentar chamar em cada conector, escolhida por estar
#: FORA do escopo dele. Leitura de propósito: a trava não pode ser a coisa que quebra o que
#: ela vigia. Se a parede cair, o custo é uma consulta; nunca uma escrita.
BATIDA_FORA_DO_ESCOPO = {
    "conecta-pro-mcp-pessoas": "listar_clientes",     # comercial
    "conecta-pro-mcp-ged": "ponto_dashboard",         # pessoas/dp
    "conecta-pro-mcp-internal": "espelho_ponto",      # dp
}


def _tools_do_conector(container: str) -> list[str] | None:
    bearer = subprocess.run(  # noqa: S603
        ["/usr/bin/docker", "exec", container, "sh", "-c", "echo $MCP_AUTH_TOKEN"],
        capture_output=True, text=True, timeout=60).stdout.strip()
    if not bearer:
        return None
    r = subprocess.run(  # noqa: S603
        ["/usr/bin/docker", "exec", "-e", f"MCP_AUTH_TOKEN={bearer}",
         "-e", f"BATIDA={BATIDA_FORA_DO_ESCOPO.get(container, '')}", "-i", container, "python3", "-"],
        input=_PROVA, capture_output=True, text=True, timeout=120)
    linha = next((l for l in r.stdout.splitlines() if l.startswith("{")), "")
    if not linha:
        print(f"  {container}: não consegui perguntar tools/list — {(r.stderr or '').strip()[:160]}")
        return None
    return json.loads(linha)


def main() -> int:
    sys.path.insert(0, "/opt/conecta-pro/mcp-server")
    from tool_scopes import tools_do_escopo

    falhas = 0
    for container in CONECTORES:
        env = _env_do_conector(container)
        escopo = env.get("MCP_ESCOPO", "")
        propria = env.get("MCP_IDENTIDADE", "").lower() == "propria"
        if not escopo:
            print(f"  {container}: SEM MCP_ESCOPO — serve o catálogo inteiro")
            falhas += 1
            continue
        # identidade própria sem o gate de aprovação é a combinação que o `identidade.py`
        # recusa no boot; se um dia alguém contornar por outro caminho, acusa aqui também.
        if propria and env.get("MCP_MODO", "").lower() != "agente":
            print(f"  {container}: 🔴 identidade PRÓPRIA e MCP_MODO != agente — agiria sem humano")
            falhas += 1
        medida = _tools_do_conector(container)
        if medida is None:
            falhas += 1
            continue
        servidas, batida, recusou = medida["servidas"], medida["batida"], medida["recusou"]
        if batida and recusou is not True:
            print(f"      🔴 chamei `{batida}` pelo NOME (fora do escopo) e a parede NÃO recusou")
            falhas += 1
        permitidas = tools_do_escopo(escopo) or set()
        fora = sorted(set(servidas) - set(permitidas))
        # ⭐ A OUTRA DIREÇÃO, que esta trava não olhava (11/09/2026, apontado pela sessão t6).
        # Eu só media "serve algo que NÃO devia" — o buraco de segurança. Mas "serve MENOS do
        # que declara" tem a mesma família e passava calado: o `tools/list` é lido do processo
        # VIVO e o escopo vem do repositório, então uma imagem parada faz o conector servir a
        # lista velha enquanto a declaração já mudou, e a minha conta dava fora=0.
        # É o caso que pegou a t6 hoje: uma build falhou, os quatro containers seguiram na
        # imagem anterior e o drift check deu 4/4 ✅ — **concordância não é atualidade**.
        # Nome que está no escopo e não é servido é uma das duas coisas, e as duas importam:
        # imagem atrasada, ou ferramenta declarada que não existe em server.py.
        faltando = sorted(set(permitidas) - set(servidas))
        proibidas = [t for t in PROIBIDAS_EM_IDENTIDADE_PROPRIA if t in servidas] if propria else []
        # TRÊS estados, não dois — e o terceiro é o que precisa aparecer escrito. Um conector
        # sem `MCP_MODO=agente` não tem parede NENHUMA: nem exigência de identidade, nem gate
        # de aprovação. É o caso do conector do kit, e é DECISÃO (o Hermes monta kit sozinho,
        # ordem do Jordan em 10/09) — mas decisão que some se ninguém a exibir.
        agente = env.get("MCP_MODO", "").lower() == "agente"
        parede = ("identidade PRÓPRIA + gate" if (propria and agente)
                  else "identidade repassada + gate" if agente
                  else "⚠️ SEM PAREDE (sem exigência de identidade e sem gate de aprovação)")
        print(f"  {container}: {len(servidas)} servidas · escopo `{escopo}` "
              f"({len(permitidas)} previstas) · imagem de {_imagem_do_conector(container)} · {parede}"
              + (f" · chamada de `{batida}` recusada" if recusou else ""))
        for t in fora[:12]:
            print(f"      FORA DO ESCOPO: {t}")
        if len(fora) > 12:
            print(f"      (+{len(fora) - 12} não listadas)")
        for t in faltando[:12]:
            print(f"      DECLARADA E NÃO SERVIDA: {t}  — imagem atrasada, ou nome que não "
                  f"existe em server.py")
        if len(faltando) > 12:
            print(f"      (+{len(faltando) - 12} não listadas)")
        for t in proibidas:
            print(f"      🔴 PROIBIDA e servida: {t}")
        if fora or proibidas or faltando:
            falhas += 1

    print(f"TOTAL conectores servindo fora do escopo: {falhas}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
