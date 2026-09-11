#!/usr/bin/env python3
"""Trava: quem é `read` no manifesto PROVA que não escreve.

Por que existe (23/08/2026): o `tool_risk_manifest` classificava como leitura ferramentas
que enviam WhatsApp ao cliente, excluem documento, fecham folha e aprovam férias. O teste
que existia validava que a CLASSE era válida — nunca que ela correspondia ao que a função
faz. Verde 4/4 com oito etiquetas mentindo.

A régua aqui é FATO, não texto: verbo HTTP no corpo da tool e SQL de escrita. Docstring com
"envia" é heurística; `erp.post(...)` é prova.

⚠️ A régua tem falso positivo conhecido e por isso NÃO decide sozinha: há rotas que usam
POST para CONSULTAR (o consultor recebe a pergunta no corpo; o simulador recebe os
parâmetros). Essas ficam em `POST_DE_CONSULTA`, uma por linha, com o motivo — cada entrada
é uma decisão HUMANA registrada, não uma exceção genérica. Tool nova que use POST e se diga
`read` REPROVA até alguém decidir de que lado ela está.

É fail-closed de propósito: o custo de reprovar uma leitura é um minuto de revisão; o de
aprovar uma escrita é o agente fechando folha sozinho.
"""
from __future__ import annotations

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from tool_risk_manifest import TOOL_RISK  # noqa: E402

SERVER = pathlib.Path(__file__).parent / "server.py"

# POST que CONSULTA — revisado à mão em 23/08/2026, um a um, pela rota que cada uma chama.
# Entrar aqui é afirmar: "esta rota recebe parâmetro no corpo e NÃO persiste".
POST_DE_CONSULTA: dict[str, str] = {
    "cfo_perguntar": "POST /financial/cfo/perguntar — pergunta no corpo, resposta do LLM",
    "consultar_juridico": "POST /juridico/consultor/perguntar — idem",
    "consultar_viabilidade_contratacao": "POST /consultores/mcp/executivo/viabilidade — cálculo",
    "simular_preco": "POST /crm/pricing/simular — simulação, não persiste",
    "simular_fechamento": "POST /crm/simular-fechamento — simulação",
    "briefing_contrato_novo": "POST /crm/contracts/briefing — diagnóstico do que falta",
    "baixar_espelho_ponto_pdf": "POST /consultores/mcp/{origem}/consultar — consulta que devolve PDF",
    # 11/09/2026: o corpo leva o TEXTO do modelo, que não cabe em query string. A rota
    # monta o contexto de um contrato e compara com as {{vars}} do corpo — é o ENSAIO antes
    # de cadastrar, e não grava linha nenhuma. Conferido na rota: só SELECT e montar_contexto.
    "validar_modelo_contrato": "POST /crm/contracts/validar-modelo — confere as variáveis "
                               "do corpo contra o contexto real; não persiste",
}

# ⚠️ 11/09/2026 — A REGEX TINHA UMA PORTA DOS FUNDOS, e ela custou 13 etiquetas.
# Só casava `erp.post(...)`. O conector tem DUAS portas para o ERP: os atalhos
# (`erp.post`, `erp.delete`) e o genérico `erp.request("PUT", rota, ...)` — e é pelo
# genérico que passam TODAS as 13 tools que estavam etiquetadas `read` fazendo PUT, PATCH
# ou DELETE, entre elas `revisar_justificativa_ponto` (decide falta de gente, entra na
# folha), `definir_parametros_precificacao` (muda o parâmetro de todo preço cotado) e
# `excluir_campanha` (`DELETE FROM` sem soft).
#
# A lição, que vale além daqui: este teste nasceu em 23/08 dizendo *"a régua aqui é FATO,
# não texto"* — e a régua media UM jeito de escrever, não o fato. Verde por 19 dias com 13
# etiquetas mentindo, pelo mesmo motivo que o teste anterior a ele: conferia a forma que o
# autor tinha na cabeça, não todas as formas que o código usa.
ESCRITA_HTTP = re.compile(
    r"""erp\.(post|put|patch|delete)\s*\(|erp\.request\(\s*\n?\s*["'](POST|PUT|PATCH|DELETE)["']""",
    re.I,
)
ESCRITA_SQL = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.I)


def _corpos() -> dict[str, str]:
    s = SERVER.read_text()
    out: dict[str, str] = {}
    for bloco in re.split(r"\n@mcp\.tool\b", s)[1:]:
        m = re.search(r"(?:async\s+)?def\s+(\w+)\s*\(", bloco)
        if m:
            out[m.group(1)] = bloco
    return out


def test_read_nao_escreve() -> None:
    corpos = _corpos()
    culpadas: list[str] = []
    for nome, classe in sorted(TOOL_RISK.items()):
        if classe != "read" or nome in POST_DE_CONSULTA:
            continue
        c = corpos.get(nome, "")
        http = ESCRITA_HTTP.search(c)
        sql = ESCRITA_SQL.search(c)
        if http or sql:
            # pula o primeiro argumento do `erp.request("PUT", ...)` — senão a "rota"
            # exibida vira o próprio verbo ("usa DELETE em DELETE"), que não ajuda ninguém
            rota = re.search(r'erp\.request\(\s*\n?\s*["\']\w+["\'],\s*\n?\s*f?["\']([^"\']+)'
                             r'|erp\.\w+\(\s*f?["\']([^"\']+)', c)
            # o verbo pode vir do atalho (grupo 1) ou do `erp.request("PUT", ...)` (grupo 2)
            verbo = (http.group(1) or http.group(2)) if http else sql.group(1)
            culpadas.append(
                f"{nome} usa {verbo.upper()}"
                + (f" em {(rota.group(1) or rota.group(2))[:44]}" if rota else ""))
    assert not culpadas, (
        f"{len(culpadas)} tool(s) classificadas 'read' que ESCREVEM. Reclassifique "
        f"(write_low/propose) ou, se a rota apenas consulta, registre em POST_DE_CONSULTA "
        f"com o motivo:\n  - " + "\n  - ".join(culpadas[:12]))


def test_excecao_nao_vira_gaveta() -> None:
    """Exceção sem tool correspondente é lixo que esconde o próximo erro."""
    corpos = _corpos()
    fantasmas = sorted(n for n in POST_DE_CONSULTA if n not in corpos)
    assert not fantasmas, f"POST_DE_CONSULTA lista tool inexistente: {fantasmas}"


def test_excecao_so_para_read() -> None:
    """Só faz sentido dispensar quem se diz leitura."""
    erradas = sorted(n for n in POST_DE_CONSULTA
                     if TOOL_RISK.get(n) not in (None, "read"))
    assert not erradas, (
        f"estas estão em POST_DE_CONSULTA mas NÃO são 'read' — tire da lista: {erradas}")


if __name__ == "__main__":
    falhas = 0
    for fn in (test_read_nao_escreve, test_excecao_nao_vira_gaveta, test_excecao_so_para_read):
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            falhas += 1
            print(f"FAIL {fn.__name__}\n  {e}")
    raise SystemExit(1 if falhas else 0)
