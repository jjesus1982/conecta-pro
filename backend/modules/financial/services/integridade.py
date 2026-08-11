"""Vocabulário de direção do extrato e impressão digital canônica de transação.

Nasceu de dois defeitos silenciosos reais (2026-08-09/10):
  • a Cora gravava `abs(amount)`: 112 saídas (R$129.817,61) viraram entrada;
  • CSV e API importaram o MESMO PIX com chaves diferentes: 880 linhas em dobro.

Ambos passaram porque nada no banco de dados os impedia.
"""

from __future__ import annotations

import re

# As DUAS grafias convivem na base (herança de importadores diferentes).
# Deixar uma de fora reabre o buraco.
TIPOS_ENTRADA: frozenset[str] = frozenset(
    {"credit", "credito", "pix_recebido", "boleto_recebido"}
)
TIPOS_SAIDA: frozenset[str] = frozenset(
    {"debit", "debito", "pix_enviado", "boleto_pago", "saque", "ted"}
)

_RE_CONTRAPARTE = re.compile(r"CP :[0-9]+-")
_RE_NAO_ALFANUM = re.compile(r"[^A-Z0-9 ]")
_RE_ESPACOS = re.compile(r" +")


def direcao_esperada(transaction_type: str | None) -> str | None:
    """'saida' | 'entrada' | None. None = tipo DESCONHECIDO.

    Fail-closed de propósito: um tipo novo não ganha direção por chute. Quem
    adicionar um tipo declara o sinal dele — no vocabulário e na constraint.
    """
    t = (transaction_type or "").strip().lower()
    if t in TIPOS_ENTRADA:
        return "entrada"
    if t in TIPOS_SAIDA:
        return "saida"
    return None


def descricao_canonica(descricao: str | None) -> str:
    """Normaliza a descrição para comparação entre importadores.

    O mesmo PIX chega como `PIX ENVIADO - Cp :60701190-FULANO` pela API e como
    `Pix enviado: "Cp :00000000-FULANO` pelo CSV — mesmo fato, texto diferente,
    e o código da contraparte vem MASCARADO de formas distintas.

    Espelha a expressão do índice único `uq_bank_tx_impressao_digital`. Mudar um
    sem o outro deixa Python e banco discordando — que é como o defeito nasce.
    """
    s = (descricao or "").replace("\n", " ").upper()
    s = _RE_CONTRAPARTE.sub("", s)
    s = _RE_NAO_ALFANUM.sub(" ", s)
    return _RE_ESPACOS.sub(" ", s).strip()
