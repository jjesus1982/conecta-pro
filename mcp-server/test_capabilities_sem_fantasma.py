"""O mapa de descoberta não pode citar ferramenta que não existe.

Validação do Cowork, 11/09/2026 (Bloco 5). `conecta_pro_capabilities(dominio="financeiro")`
devolvia no `fluxo`: `resumo_financeiro`, `listar_contas_pagar`, `listar_recebiveis` — e as
duas últimas NUNCA existiram. Auditando os seis domínios pelo mesmo critério apareceram DEZ
nomes fantasma, não dois.

⭐ POR QUE É GRAVE, e não cosmético: `capabilities` é a tool de DESCOBERTA. É por ela que um
agente decide o que fazer em seguida — ele não tem navegador, não lê o código, e o mapa é o
que ele tem. Mapa apontando para rua que não existe faz o agente tentar, falhar, e o operador
humano concluir que "o MCP não funciona". O defeito custa confiança, não uma chamada.

⚠️ Um nome com sintaxe junto — `baixar_contrato_pdf(formato='texto')` — também reprova. Lê
bem para humano e é inchamável por agente: ele tenta chamar uma ferramenta com esse nome
literal. A dica de uso vai no campo `atencao`, que é texto; o `fluxo` é lista de NOMES.

São 15 linhas de teste que impedem a classe inteira de erro.

    python test_capabilities_sem_fantasma.py
"""
from __future__ import annotations

import re

import server as S

_NOME_VALIDO = re.compile(r"^[a-z][a-z0-9_]*$")


def test_mapa_tem_dominios() -> None:
    assert len(S._MAPA) >= 5, f"o mapa encolheu para {len(S._MAPA)} domínios"
    for nome, d in S._MAPA.items():
        assert d.get("resumo"), f"{nome} sem resumo"
        assert d.get("fluxo"), f"{nome} sem fluxo — domínio sem caminho não ajuda ninguém"
    print(f"OK {len(S._MAPA)} domínios, todos com resumo e fluxo")


def test_nenhuma_tool_fantasma() -> None:
    fantasmas = []
    total = 0
    for dominio, d in S._MAPA.items():
        for tool in d["fluxo"]:
            total += 1
            if not hasattr(S, tool) or not callable(getattr(S, tool, None)):
                fantasmas.append(f"{dominio} → {tool}")
    assert not fantasmas, (
        "o mapa cita ferramentas que NÃO EXISTEM:\n    " + "\n    ".join(fantasmas)
        + "\n  Corrija o nome em `_MAPA` — o agente vai tentar chamar exatamente isto.")
    print(f"OK as {total} ferramentas do mapa existem no registry")


def test_fluxo_e_lista_de_nomes() -> None:
    """Nome com parêntese, espaço ou argumento não é nome — é instrução disfarçada."""
    ruins = []
    for dominio, d in S._MAPA.items():
        for tool in d["fluxo"]:
            if not _NOME_VALIDO.match(tool):
                ruins.append(f"{dominio} → {tool!r}")
    assert not ruins, (
        "o `fluxo` tem entradas que não são nome de ferramenta:\n    " + "\n    ".join(ruins)
        + "\n  Dica de uso vai em `atencao`; `fluxo` é lista de NOMES chamáveis.")
    print("OK todo item do fluxo é um nome chamável")


def test_tool_citada_esta_no_manifesto() -> None:
    """Existir não basta: sem etiqueta de risco ela não passa pelas paredes.

    Uma ferramenta fora do `tool_risk_manifest` é tratada como `propose` por padrão (a
    parede fecha no caso desconhecido). Citá-la no mapa como caminho normal mandaria o
    agente para uma porta que sempre recusa.
    """
    from tool_risk_manifest import TOOL_RISK

    sem_etiqueta = [f"{dom} → {t}" for dom, d in S._MAPA.items()
                    for t in d["fluxo"] if t not in TOOL_RISK]
    assert not sem_etiqueta, (
        "citadas no mapa e sem classe de risco:\n    " + "\n    ".join(sem_etiqueta))
    print("OK toda ferramenta do mapa tem classe de risco")


if __name__ == "__main__":
    for fn in (test_mapa_tem_dominios, test_nenhuma_tool_fantasma,
               test_fluxo_e_lista_de_nomes, test_tool_citada_esta_no_manifesto):
        fn()
        print(f"PASS {fn.__name__}")
    print("TEST test_capabilities_sem_fantasma PASS")
