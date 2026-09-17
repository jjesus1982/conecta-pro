"""Responde sem LLM o que não precisa de LLM — e recusa decidir quando há dúvida.

Origem: 17/09/2026. Hoje TODA mensagem que chega vai para o modelo, inclusive "obrigado" e
"👍". Medido sobre 60 dias de conversa real desta casa, as mensagens curtas mais frequentes:

    sim 12 · ok 11 · tá bom 3 · bom dia 3 · 🫡 3 · obrigado 3 · olá 2 · obrigada 2 · 👍🏻 2

O ganho de dinheiro é irrisório (o José Luís inteiro custou US$ 0,27 em 30 dias). O que se
ganha é outra coisa, e vale mais:

  · LATÊNCIA — hoje um "obrigado" espera o modelo pensar, com até 5 rodadas de ferramenta.
  · PREVISIBILIDADE — a mesma despedida sempre recebe a mesma resposta.
  · O LOOP — resposta curta e fixa não alimenta eco com outro robô do jeito que uma resposta
    gerada alimenta. Some com a guarda de turnos, é o que protege o número.

## A regra é conservadora de propósito

Só encerramento: agradecimento e emoji de positivo. `sim`, `ok` e `tá bom` — os DOIS mais
frequentes da lista — ficam FORA, e esse é o ponto mais importante deste arquivo: eles quase
sempre respondem a uma pergunta nossa ("quer que eu agende?" → "sim"). Responder "de nada" ali
quebraria a conversa no pior momento possível. Na dúvida, o modelo decide.

E mesmo o agradecimento só é atendido quando a NOSSA última mensagem não terminou em pergunta:
"te ajudo em mais alguma coisa?" → "obrigado" ainda é conversa viva.
"""

from __future__ import annotations

import re
import unicodedata

#: Encerramentos. Lista FECHADA e curta: cada item aqui é uma resposta que o modelo deixa de
#: dar, então entra só o que não tem outra leitura possível.
_AGRADECE = {
    "obrigado",
    "obrigada",
    "obg",
    "vlw",
    "valeu",
    "agradecido",
    "agradecida",
    "muito obrigado",
    "muito obrigada",
    "obrigado!",
    "obrigada!",
    "grato",
    "grata",
    "tmj",
    "show",
    "perfeito",
    "otimo",
    "excelente",
}

#: Emoji de positivo/encerramento, sem texto junto.
_EMOJI_OK = {"👍", "👍🏻", "👍🏼", "👍🏽", "👏", "🙏", "🫡", "✅", "😊", "❤️", "💙"}

#: Resposta única. Curta de propósito: encerramento não é lugar de puxar assunto — puxar
#: assunto aqui é o que gera o turno seguinte e mantém o eco vivo.
RESPOSTA_AGRADECIMENTO = "Imagina! 😊 Qualquer coisa é só me chamar. 💙"


def _limpo(texto: str) -> str:
    t = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[.!,;]+", "", t)).strip().lower()


def _so_emoji(texto: str) -> bool:
    """Só emoji, nada de texto — e todos da lista de positivo."""
    bruto = str(texto or "").strip()
    if not bruto or len(bruto) > 12:
        return False
    restante = bruto
    for e in _EMOJI_OK:
        restante = restante.replace(e, "")
    return restante.strip() == ""


def resposta_pronta(texto: str, ultima_saida: str | None = None) -> str | None:
    """A resposta que dispensa o modelo, ou None quando ele deve decidir.

    `ultima_saida` é a última coisa que NÓS dissemos. Se terminou em pergunta, devolve None
    mesmo para um agradecimento: a conversa está viva e quem tem de responder é o modelo.
    """
    if (ultima_saida or "").strip().endswith("?"):
        return None
    if _so_emoji(texto):
        return RESPOSTA_AGRADECIMENTO
    return RESPOSTA_AGRADECIMENTO if _limpo(texto) in _AGRADECE else None


def demo() -> None:
    """Auto-checagem: `python3 roteador.py`."""
    # encerra: o modelo não precisa entrar
    for t in ("Obrigado", "obrigada!", "vlw", "👍", "🫡", "Muito obrigado.", "Perfeito"):
        assert resposta_pronta(t) == RESPOSTA_AGRADECIMENTO, t

    # NÃO encerra: são respostas a pergunta, e o modelo decide
    for t in ("sim", "ok", "tá bom", "positivo", "pode ser"):
        assert resposta_pronta(t) is None, t

    # conversa viva: pergunta nossa pendente segura até o agradecimento
    assert resposta_pronta("obrigado", "Te ajudo em mais alguma coisa?") is None

    # nada que seja pedido de verdade passa
    for t in (
        "obrigado, mas preciso do meu holerite",
        "bom dia, não consegui bater o ponto",
        "👍 mas o pagamento não caiu",
        "quero falar com o humano",
    ):
        assert resposta_pronta(t) is None, t

    assert resposta_pronta("") is None
    assert resposta_pronta(None) is None
    print("roteador: 20 checagens passaram")


if __name__ == "__main__":
    demo()
