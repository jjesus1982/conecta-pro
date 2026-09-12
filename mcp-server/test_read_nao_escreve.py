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
    # 11/09/2026 · Bloco 1. O corpo leva a LISTA de itens com custo e natureza, que não
    # cabe em query string. A rota resolve a margem de cada linha e devolve a memória de
    # cálculo — não há INSERT nem UPDATE em nenhum caminho dela. Revisado lendo a função.
    "orcamento_por_natureza": "POST /crm/pricing/orcamento-por-natureza — calcula, não grava",
    "simular_fechamento": "POST /crm/simular-fechamento — simulação",
    "briefing_contrato_novo": "POST /crm/contracts/briefing — diagnóstico do que falta",

    # 11/09/2026 · item 2.1. As ferramentas de documento passaram a extrair o TEXTO do que
    # geraram, para o agente conferir sem abrir binário. O corpo leva o arquivo em base64,
    # que não cabe em query string. `POST /crm/docs/extrair-texto` grava num temporário e o
    # apaga no `finally` — não toca banco nem deixa arquivo. Revisado lendo a rota.
    "baixar_proposta_pdf": "POST /crm/docs/extrair-texto — extrai texto, não persiste",
    "baixar_holerite_pdf": "POST /crm/docs/extrair-texto — idem",
    "baixar_recibo_vt_vr_pdf": "POST /crm/docs/extrair-texto — idem",
    "baixar_comprovante_pagamento_pdf": "POST /crm/docs/extrair-texto — idem",
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


# ⭐ 12/09/2026 — TERCEIRA CATEGORIA, medida em vez de assumida.
# Ao seguir a delegação, as 8 `consultor_*` apareceram: chamam `_consultar`, que faz
# POST /consultores/mcp/{origem}/consultar. A tentação era jogá-las em POST_DE_CONSULTA por
# semelhança com `cfo_perguntar`. Fui ler a rota: ela faz
# `INSERT INTO {tabela} (area, pergunta, resposta, ...)` e `commit()` — `_persistir_consulta`.
# Ela PERSISTE.
#
# E isso revelou um entry ERRADO que já estava na lista: `baixar_espelho_ponto_pdf` declarava
# esta mesma rota como "consulta que devolve PDF", afirmando o que o contrato de
# POST_DE_CONSULTA exige — "NÃO persiste". Era falso desde que foi escrito. Movido para cá.
#
# A distinção que importa para o agente: estas gravam a TRILHA da própria pergunta, não dado
# de negócio. Nenhuma proposta, folha, contrato ou pagamento muda. Manter `read` é correto —
# mas com o fato registrado, não com um motivo que diz o contrário do que a rota faz.
POST_QUE_REGISTRA_A_PROPRIA_CONSULTA: dict[str, str] = {
    n: ("POST /consultores/mcp/{origem}/consultar — INSERT da própria pergunta/resposta na "
        "tabela de consultas (trilha). Não muda dado de negócio.")
    for n in ("consultor_ceo", "consultor_cfo", "consultor_comercial", "consultor_dp",
              "consultor_fiscal", "consultor_ged", "consultor_juridico",
              "consultor_operacional", "baixar_espelho_ponto_pdf")
}

# ⚠️ 12/09/2026 — A MESMA PORTA, TERCEIRA VEZ: agora é DELEGAÇÃO.
# A varredura paramétrica achou `gerar_aditivo_pdf`, `gerar_atestado_pdf` e
# `gerar_ordem_servico_pdf` etiquetadas `read` — e o docstring de cada uma diz, com estas
# palavras, "⚠️ ESCREVE no Conecta PRO — não é consulta". O corpo delas não tem verbo
# nenhum: tem `_gerar_doc(...)`, e é o HELPER que faz `erp.post(...?salvar=true)`.
#
# Duas vezes esta trava mediu "o jeito de escrever que o autor tinha na cabeça" (primeiro só
# `erp.post`, depois sem o `erp.request` genérico) e as duas vezes o comentário acima anotou
# a lição sem consertar a causa: ela olhava o TEXTO DO CORPO da tool. Tool que delega escapa
# de qualquer regex de corpo, por mais completa que a lista de verbos fique.
#
# Agora a régua fecha a porta em vez de tapá-la: monta o conjunto dos HELPERS que escrevem e
# propaga TRANSITIVAMENTE. Helper novo que escreva contamina quem o chamar, sem ninguém
# precisar lembrar de atualizar lista.
_DEF_HELPER = re.compile(r"^(?:async\s+)?def\s+(_\w+)\s*\(", re.M)


def _helpers_que_escrevem(fonte: str) -> dict[str, str]:
    """Helpers `_x` cujo corpo escreve — direto ou chamando outro helper que escreve."""
    corpos: dict[str, str] = {}
    # um helper vai do seu `def` até o próximo `def` de coluna zero
    pedacos = re.split(r"\n(?=(?:async )?def )", fonte)
    for pedaco in pedacos:
        m = _DEF_HELPER.match(pedaco)
        if m:
            corpos[m.group(1)] = pedaco

    escrevem = {n: "escreve direto" for n, c in corpos.items()
                if ESCRITA_HTTP.search(c) or ESCRITA_SQL.search(c)}
    # ponto fixo: propaga até não mudar mais
    mudou = True
    while mudou:
        mudou = False
        for nome, corpo in corpos.items():
            if nome in escrevem:
                continue
            for alvo in escrevem:
                if re.search(rf"\b{re.escape(alvo)}\s*\(", corpo):
                    escrevem[nome] = f"chama {alvo} ({escrevem[alvo]})"
                    mudou = True
                    break
    return escrevem


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
    delegam = _helpers_que_escrevem(SERVER.read_text())
    culpadas: list[str] = []
    for nome, classe in sorted(TOOL_RISK.items()):
        if classe != "read" or nome in POST_DE_CONSULTA:
            continue
        if nome in POST_QUE_REGISTRA_A_PROPRIA_CONSULTA:
            continue
        c = corpos.get(nome, "")
        http = ESCRITA_HTTP.search(c)
        sql = ESCRITA_SQL.search(c)
        # ⭐ delegação: o corpo pode não ter verbo e ainda assim escrever, chamando helper
        if not (http or sql):
            for helper, por_que in delegam.items():
                if re.search(rf"\b{re.escape(helper)}\s*\(", c):
                    culpadas.append(f"{nome} ESCREVE via {helper} — {por_que}")
                    break
            continue
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
    # ⭐ as DUAS listas de dispensa, não só a que eu lembrei de criar primeiro. Guarda que
    # cobre uma gaveta e ignora a outra é a própria falha que este arquivo documenta.
    for rotulo, lista in (("POST_DE_CONSULTA", POST_DE_CONSULTA),
                          ("POST_QUE_REGISTRA_A_PROPRIA_CONSULTA",
                           POST_QUE_REGISTRA_A_PROPRIA_CONSULTA)):
        fantasmas = sorted(n for n in lista if n not in corpos)
        assert not fantasmas, f"{rotulo} lista tool inexistente: {fantasmas}"
        sem_motivo = sorted(n for n, m in lista.items() if len((m or "").strip()) < 20)
        assert not sem_motivo, (
            f"{rotulo}: dispensa sem motivo escrito é gaveta — {sem_motivo}")
    sobrepostas = sorted(set(POST_DE_CONSULTA) & set(POST_QUE_REGISTRA_A_PROPRIA_CONSULTA))
    assert not sobrepostas, (
        f"nas duas listas, com contratos OPOSTOS (persiste × não persiste): {sobrepostas}")


def test_excecao_so_para_read() -> None:
    """Só faz sentido dispensar quem se diz leitura."""
    erradas = sorted(n for n in (*POST_DE_CONSULTA, *POST_QUE_REGISTRA_A_PROPRIA_CONSULTA)
                     if TOOL_RISK.get(n) not in (None, "read"))
    assert not erradas, (
        f"estas estão numa lista de dispensa mas NÃO são 'read' — tire: {erradas}")


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
