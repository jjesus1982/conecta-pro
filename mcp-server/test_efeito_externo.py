"""Ação cujo efeito SAI da empresa não pode existir sem parede — em nenhum modo.

Auditoria do Cowork, 11/09/2026. `enviar_link_assinatura` ESTAVA classificada `propose` no
manifesto, e mesmo assim passou por `ensaiar` — que tinha na própria descrição a promessa
"ferramenta `propose` é recusada aqui do mesmo jeito". Duas causas empilhadas:

  1. `precisa_aprovacao` era `MODO_AGENTE and classe == "propose"`, e o conector PÚBLICO
     (o Cowork do Jordan) não é modo agente;
  2. o middleware que lê a classificação nem era INSTALADO fora do modo agente — então a
     chamada direta `enviar_link_assinatura("CTR-2026-00022")` teria MANDADO O E-MAIL para
     a síndica do Maiápolis. A classificação estava certa e não havia ninguém para lê-la.

O raciocínio que criou o buraco foi meu e era quase certo: "parede mais rígida que a porta
da frente não protege nada". Vale para IDENTIDADE, onde a porta da frente é aberta de
propósito para o dono. Não vale aqui — nestas ações a porta da frente aberta É o defeito,
porque quem chama o conector público é um LLM agindo em nome do Jordan, não o Jordan
clicando um botão.

Esta trava roda no BUILD e é fail-closed: ferramenta nova com nome de verbo que sai da
empresa REPROVA até alguém decidir de que lado ela está. O custo de reprovar é um minuto de
revisão; o de liberar é um e-mail no cliente que não se desfaz.

    python test_efeito_externo.py
"""
from __future__ import annotations

import os

os.environ.pop("MCP_MODO", None)  # modo PÚBLICO de propósito: é onde o buraco estava

import gate_propose as G  # noqa: E402
from tool_risk_manifest import TOOL_RISK  # noqa: E402

# Verbos cujo efeito, por convenção desta casa, atravessa a fronteira da empresa.
VERBOS_QUE_SAEM = ("enviar_", "transmitir_", "pagar_", "assinar_", "notificar_",
                   "disparar_", "publicar_", "compartilhar_", "followup_")


def test_modo_publico() -> None:
    """Sem isto o teste passaria por estar medindo o conector errado."""
    assert not G.MODO_AGENTE, "este teste tem de rodar em modo PÚBLICO — é onde falhou"


def test_verbo_que_sai_esta_decidido() -> None:
    """Toda tool com verbo de saída está em EFEITO_EXTERNO ou na exceção COM MOTIVO."""
    pendentes = [
        n for n in sorted(TOOL_RISK)
        if any(n.startswith(v) for v in VERBOS_QUE_SAEM)
        and n not in G.EFEITO_EXTERNO
        and n not in G.NAO_SAI_DA_EMPRESA
    ]
    assert not pendentes, (
        "estas têm nome de ação que sai da empresa e ninguém decidiu: " + ", ".join(pendentes)
        + "\nAcrescente a gate_propose.EFEITO_EXTERNO (com o que sai, em português) ou a "
          "NAO_SAI_DA_EMPRESA (com a ROTA que prova que o efeito é interno).")
    print(f"OK {len(G.EFEITO_EXTERNO)} com efeito externo, "
          f"{len(G.NAO_SAI_DA_EMPRESA)} exceções revisadas")


def test_efeito_externo_barra_em_modo_publico() -> None:
    """⭐ O teste que teria pego o defeito: barrar SEM depender do modo."""
    passam = [n for n in G.EFEITO_EXTERNO if not G.precisa_aprovacao(n)]
    assert not passam, (
        f"em modo público estas passariam: {passam} — é exatamente o defeito de 11/09")
    print(f"OK as {len(G.EFEITO_EXTERNO)} barram em modo público")


def test_cada_uma_diz_o_que_sai() -> None:
    """A recusa precisa dizer o que aconteceria, não o nome de uma função.

    Um agente lendo "`enviar_nps` é classe propose" não sabe o que evitou. Lendo "sai a
    pesquisa de satisfação para os clientes", sabe — e o dono também, quando o pedido
    chegar a ele.
    """
    mudas = [n for n, txt in G.EFEITO_EXTERNO.items() if len(str(txt).strip()) < 15]
    assert not mudas, f"efeito externo sem descrição do que sai: {mudas}"
    for nome in G.EFEITO_EXTERNO:
        assert G.efeito_externo(nome), f"{nome} não devolve o que sai"
    print("OK cada uma declara, em português, o que sairia")


def test_exececao_nao_vira_gaveta() -> None:
    """Exceção precisa citar a ROTA — é o que prova que o efeito é interno."""
    sem_prova = [n for n, m in G.NAO_SAI_DA_EMPRESA.items() if "/" not in str(m)]
    assert not sem_prova, (
        f"exceção sem a rota que a justifica: {sem_prova}. "
        "'Eu olhei e é interno' não é evidência — cole a rota.")
    cruzadas = set(G.NAO_SAI_DA_EMPRESA) & set(G.EFEITO_EXTERNO)
    assert not cruzadas, f"nas duas listas ao mesmo tempo: {cruzadas}"
    print(f"OK {len(G.NAO_SAI_DA_EMPRESA)} exceções, cada uma com a rota")


def test_efeito_externo_tambem_e_propose() -> None:
    """As duas listas não podem divergir: quem sai da empresa é `propose` no manifesto.

    Se uma ficasse `write_low`, o `test_read_nao_escreve` e o manifesto contariam uma
    história e o gate outra — e a próxima pessoa acreditaria na que ler primeiro.
    """
    erradas = {n: TOOL_RISK.get(n) for n in G.EFEITO_EXTERNO
               if n in TOOL_RISK and TOOL_RISK[n] != "propose"}
    assert not erradas, f"efeito externo classificado fora de `propose`: {erradas}"
    print("OK manifesto e gate contam a mesma história")


def test_middleware_instala_no_modo_publico() -> None:
    """Classificar não adianta se o middleware não estiver no caminho.

    Era a segunda metade do defeito: `instalar()` devolvia False fora do modo agente e não
    punha nada na pilha. A parede existia no papel e não no caminho da chamada.
    """
    class FalsoMcp:
        def __init__(self) -> None:
            self.middlewares: list = []

        def add_middleware(self, m) -> None:  # noqa: ANN001
            self.middlewares.append(m)

    m = FalsoMcp()
    assert G.instalar(m) is True, "instalar() recusou em modo público — o buraco voltou"
    assert m.middlewares, "instalar() devolveu True e não instalou nada"
    print("OK o gate entra na pilha também no conector público")


if __name__ == "__main__":
    for fn in (test_modo_publico, test_verbo_que_sai_esta_decidido,
               test_efeito_externo_barra_em_modo_publico, test_cada_uma_diz_o_que_sai,
               test_exececao_nao_vira_gaveta, test_efeito_externo_tambem_e_propose,
               test_middleware_instala_no_modo_publico):
        fn()
        print(f"PASS {fn.__name__}")
    print("TEST test_efeito_externo PASS")
