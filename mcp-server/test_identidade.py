#!/usr/bin/env python3
"""Trava F2: tool sensível NÃO executa com a conta de serviço.

Por que existe: até 23/08/2026 toda chamada do conector do agente ia ao ERP com o JWT de
`mcp-service@`. O RBAC funcionava e respondia sobre o usuário errado — um porteiro perguntando
"quantas horas eu fiz" era atendido com os poderes da conta de serviço, e a auditoria gravava
`mcp-service`, não ele.

A régua: sensível é o DEFAULT. Escrita sempre; leitura salvo liberação escrita, uma a uma,
com o motivo. Nem nome (o manifesto errou 54 vezes assim) nem GRUPO DE ASSUNTO — a primeira
versão desta parede usou grupo e `resumo_financeiro` devolveu o MRR sem identidade nenhuma,
porque a rota dela é `/crm/financeiro` e o grupo é "comercial".

Os quatro testes cobrem os quatro jeitos de furar isto:
  1. a classificação afrouxar no caso desconhecido;
  2. uma escrita ser tratada como leitura inofensiva;
  3. o middleware deixar passar quando não veio identidade;
  4. o cliente HTTP montar o cabeçalho por fora de `_cabecalho` e escapar da regra.

O 4º é o que a experiência desta casa manda testar: a regra certa num lugar só, e uma segunda
via que ninguém lembrou de fechar.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gate_propose import classe_de  # noqa: E402
from identidade import (  # noqa: E402
    CABECALHO, SEM_DADO_DE_TERCEIRO, ExigeIdentidade, sensivel,
)
from tool_risk_manifest import TOOL_RISK  # noqa: E402

SERVER = pathlib.Path(__file__).parent / "server.py"


def test_desconhecida_e_sensivel() -> None:
    """Tool que ninguém classificou tem de contar como sensível — fail-closed."""
    assert sensivel("tool_que_nunca_existiu_xyz"), (
        "tool desconhecida passou como não-sensível: no caso desconhecido a parede tem de "
        "fechar, senão toda tool nova nasce liberada")


def test_toda_escrita_e_sensivel() -> None:
    frouxas = sorted(t for t in TOOL_RISK if classe_de(t) != "read" and not sensivel(t))
    assert not frouxas, f"tools que ESCREVEM e passaram como não-sensíveis: {frouxas[:10]}"


def test_leitura_e_sensivel_por_padrao() -> None:
    """Ler é sensível salvo liberação escrita — e a liberação não pode virar gaveta.

    Regressão que originou: a régua anterior deduzia sensibilidade do GRUPO DE ASSUNTO, e
    `resumo_financeiro` devolveu o MRR da empresa sem identidade nenhuma porque a rota é
    `/crm/financeiro` e o grupo dela é "comercial". Assunto não é risco.
    """
    liberadas = set(SEM_DADO_DE_TERCEIRO)
    frouxas = sorted(t for t in TOOL_RISK
                     if classe_de(t) == "read" and t not in liberadas and not sensivel(t))
    assert not frouxas, f"leitura tratada como inofensiva sem liberação escrita: {frouxas[:10]}"

    # o caso concreto que furou
    assert sensivel("resumo_financeiro"), (
        "resumo_financeiro devolve MRR e recebíveis — não pode executar sem identidade só "
        "porque o grupo de assunto dela é 'comercial'")

    fantasmas = sorted(t for t in liberadas if t not in TOOL_RISK)
    assert not fantasmas, f"liberação para tool inexistente (gaveta): {fantasmas}"


def test_middleware_barra_sem_identidade() -> None:
    """O comportamento, não só a classificação: sem cabeçalho, a sensível não roda."""
    from fastmcp.exceptions import ToolError

    class _Msg:
        def __init__(self, nome): self.name, self.arguments = nome, {}

    class _Ctx:
        def __init__(self, nome): self.message = _Msg(nome)

    executou: list[str] = []

    async def _segue(ctx):
        executou.append(ctx.message.name)
        return "executou"

    sensiveis = [t for t in TOOL_RISK if sensivel(t)][:3]
    inocentes = [t for t in TOOL_RISK if not sensivel(t)][:3]
    assert sensiveis and inocentes, "manifesto não tem os dois lados — teste não separa nada"

    async def _rodar():
        mw, barradas, passadas = ExigeIdentidade(), [], []
        for nome in sensiveis:
            try:
                await mw.on_call_tool(_Ctx(nome), _segue)
                passadas.append(nome)
            except ToolError:
                barradas.append(nome)
        for nome in inocentes:
            await mw.on_call_tool(_Ctx(nome), _segue)
        return barradas, passadas

    barradas, passadas = asyncio.run(_rodar())
    assert not passadas, f"tool SENSÍVEL executou sem identidade: {passadas}"
    assert len(barradas) == len(sensiveis), "nem toda sensível foi barrada"
    assert executou == inocentes, (
        f"as não-sensíveis deveriam seguir normalmente; executaram {executou}")


def test_cliente_erp_nao_tem_segunda_via() -> None:
    """Toda chamada do `_Erp` passa por `_cabecalho`. Cabeçalho montado inline é a segunda
    via por onde a conta de serviço voltaria a agir sem ninguém perceber."""
    fonte = SERVER.read_text()
    inicio = fonte.index("class _Erp:")
    corpo = fonte[inicio:fonte.index("\nerp = _Erp()")]
    # o próprio `_login` monta a sua requisição (é ele quem obtém o token de serviço)
    corpo = re.sub(r"async def _login.*?(?=\n    async def )", "", corpo, flags=re.S)

    chamadas = re.findall(r"await client\.(?:request|get|post)\((.*?)\)\n", corpo, re.S)
    sem_variavel = [c for c in chamadas if "headers=headers" not in c]
    assert not sem_variavel, (
        f"{len(sem_variavel)} chamada(s) do _Erp montam o cabeçalho por fora de `_cabecalho` "
        f"— é por aí que a conta de serviço volta a agir no lugar do usuário:\n  "
        + "\n  ".join(c.replace("\n", " ")[:110] for c in sem_variavel[:4]))


def test_cabecalho_e_um_token_nao_um_nome() -> None:
    """O canal tem de ser prova assinada, não afirmação do chamador."""
    assert CABECALHO == "x-usuario-token", (
        "o canal de identidade mudou de nome; se virou um `x-usuario: email`, é forjável por "
        "quem tiver o bearer do conector — a mesma classe do confirmar='ACEITAR'")


if __name__ == "__main__":
    falhas = 0
    for fn in (test_desconhecida_e_sensivel, test_toda_escrita_e_sensivel,
               test_leitura_e_sensivel_por_padrao, test_middleware_barra_sem_identidade,
               test_cliente_erp_nao_tem_segunda_via, test_cabecalho_e_um_token_nao_um_nome):
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            falhas += 1
            print(f"FAIL {fn.__name__}\n  {e}")
    raise SystemExit(1 if falhas else 0)
