"""Normalização de telefone brasileiro: E.164 (+55DDDNUMERO) e forma canônica (matching).

- canonical_br: dígitos DDD+número SEM o DDI 55 — igual ao que o webhook grava em
  cwi_message_log.phone_canonical e ao que costuma estar em leads.phone (matching).
- to_e164_br: +55DDDNUMERO, validando 10 (fixo) ou 11 (celular) dígitos nacionais — para
  armazenar em clients.whatsapp e disparar o envio. Retorna None se claramente inválido.
"""

from __future__ import annotations

import re

_NON_DIGIT = re.compile(r"\D")


def only_digits(raw: object) -> str:
    return _NON_DIGIT.sub("", str(raw or ""))


def canonical_br(raw: object) -> str | None:
    """DDD+número sem DDI 55 (ex.: '92991234567'). Só dígitos, máx 20 chars, ou None."""
    d = only_digits(raw)
    if not d:
        return None
    if d.startswith("55") and len(d) > 11:
        d = d[2:]
    return d[:20] or None


def to_e164_br(raw: object) -> str | None:
    """+55DDDNUMERO. Valida 10 (fixo) ou 11 (celular) dígitos nacionais. None se inválido."""
    c = canonical_br(raw)
    if not c:
        return None
    if len(c) < 10 or len(c) > 11:
        return None
    return f"+55{c}"


def display_br(raw: object) -> str | None:
    """Formata para exibição: +55 (92) 9 9123-4567 (best-effort)."""
    c = canonical_br(raw)
    if not c or len(c) < 10:
        return to_e164_br(raw)
    ddd, rest = c[:2], c[2:]
    if len(rest) == 9:
        return f"+55 ({ddd}) {rest[0]} {rest[1:5]}-{rest[5:]}"
    return f"+55 ({ddd}) {rest[:4]}-{rest[4:]}"
