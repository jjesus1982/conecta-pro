"""Quem RECEBEU × quem DEVIA receber — conferência do PIX contra o que o banco devolve.

Origem: 16/09/2026. O Jordan perguntou se o Conecta PRO faz o que o app do banco faz — digitar
a chave e ver o nome do titular antes de confirmar. Não fazia. Pior: existia um
`InterAdapter.validate_pix_key` que aponta para `/pix/v2/dict/key`, endpoint que o Inter
responde 404, com o erro engolido pelo `except` — devolvia None para toda chave, inclusive a
nossa. Treze caminhos de consulta DICT testados contra a API real: nenhum existe no Banking do
Inter.

O que existe, medido com R$ 0,01 enviados para a chave do próprio Jordan e autorizados por ele:

    envio ............... status PROCESSADO
    1ª consulta ......... status ENVIADO · recebedor.nome VAZIO
    2ª consulta (3s) .... status PAGO    · recebedor.nome 'JORDAN SANTOS DE JESUS'
                                          · recebedor.cpfCnpj '***681522**'  (CPF 730.681522-91)

Duas conclusões que mudam o desenho:

1. O nome SÓ vem depois de PAGO. Isto confirma para onde o dinheiro foi; não impede que vá para
   o lugar errado. Quem quiser prevenir usa o centavo de prova — `provar_chaves_por_centavo`.
2. A credencial aprova sozinha: TRANSACAO_CRIADA → TRANSACAO_APROVADA → PIX_ENVIADO → PIX_PAGO
   em 3 segundos, sem passar por aprovação no app.

O documento vem MASCARADO (`***681522**`): os 6 dígitos do meio, posições 4 a 9. É o que dá para
conferir, e já é forte — nome igual e 6 dígitos iguais não acontece por acaso.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

#: Posições do CPF que o Inter deixa visíveis em `***681522**`.
_FATIA_CPF = slice(3, 9)


def _texto(s: Any) -> str:
    """Sem acento, sem pontuação, caixa alta, espaço único — para comparar nome de gente."""
    t = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", t)).strip()


def _digitos(s: Any) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def documento_bate(mascarado: str, documento_nosso: str) -> bool | None:
    """Os 6 dígitos que o banco mostra conferem com o nosso CPF?

    None quando não dá para decidir (sem documento nosso, ou máscara em formato inesperado) —
    que é diferente de 'não bate'. Confundir os dois transforma dado faltando em acusação.
    """
    vis = _digitos(mascarado)
    nosso = _digitos(documento_nosso)
    if not vis or not nosso:
        return None
    if len(nosso) == 11 and len(vis) == 6:
        return nosso[_FATIA_CPF] == vis
    if len(nosso) == len(vis):  # veio inteiro (CNPJ costuma vir assim)
        return nosso == vis
    return None


def nome_bate(nome_banco: str, nome_nosso: str) -> bool | None:
    """Nome do titular × nome do cadastro, tolerando abreviação.

    Não exige igualdade literal: 'Ramon Araújo' no cadastro e 'RAMON DOS SANTOS ARAUJO' no banco
    são a mesma pessoa. A regra é que TODOS os pedaços do nome menor apareçam no maior, e que o
    primeiro nome seja o mesmo — 'MARIA SILVA' e 'MARIA SOUZA' não passam.
    """
    b, n = _texto(nome_banco), _texto(nome_nosso)
    if not b or not n:
        return None
    if b == n:
        return True
    tb, tn = b.split(), n.split()
    if tb[0] != tn[0]:
        return False
    menor, maior = (tb, tn) if len(tb) <= len(tn) else (tn, tb)
    return all(t in maior for t in menor)


def conferir(*, nome_banco: str, documento_banco: str, nome_nosso: str, documento_nosso: str) -> dict:
    """Veredito de um pagamento. `ok` só é True quando nada desmente.

    Estados:
        confere        — nome e documento batem (ou o que dá para conferir bateu)
        DIVERGE        — o banco diz outro nome ou outro documento. Dinheiro foi para outro.
        nao_confirmado — o banco ainda não devolveu o recebedor (status anterior a PAGO)
    """
    if not (nome_banco or documento_banco):
        return {
            "ok": None,
            "veredito": "nao_confirmado",
            "detalhe": "o banco ainda não devolveu o recebedor (consulte de novo após PAGO)",
        }

    vn = nome_bate(nome_banco, nome_nosso)
    vd = documento_bate(documento_banco, documento_nosso)
    ruins = []
    if vn is False:
        ruins.append(f"nome: banco diz '{nome_banco}', cadastro diz '{nome_nosso}'")
    if vd is False:
        ruins.append(f"documento: banco mostra '{documento_banco}', cadastro tem '{documento_nosso}'")
    if ruins:
        return {"ok": False, "veredito": "DIVERGE", "detalhe": " · ".join(ruins)}

    # Nada desmentiu. Diz o que foi de fato conferido, para ninguém confundir
    # 'conferi e bateu' com 'não tinha o que conferir'.
    conferido = [r for r, v in (("nome", vn), ("documento", vd)) if v is True]
    return {
        "ok": True,
        "veredito": "confere",
        "detalhe": ("conferido por " + " e ".join(conferido))
        if conferido
        else "o banco respondeu, mas não havia nome nem documento nosso para comparar",
    }


def demo() -> None:
    """Auto-checagem: roda com `python3 conferencia_pix.py`."""
    # o caso real medido em 16/09/2026
    r = conferir(
        nome_banco="JORDAN SANTOS DE JESUS",
        documento_banco="***681522**",
        nome_nosso="Jordan Santos de Jesus",
        documento_nosso="73068152291",
    )
    assert r["ok"] is True, r

    # chave de OUTRA pessoa: nome diferente com documento que bate por acaso não passa
    r = conferir(
        nome_banco="MARIA SOUZA LIMA",
        documento_banco="***681522**",
        nome_nosso="Jordan Santos de Jesus",
        documento_nosso="73068152291",
    )
    assert r["ok"] is False and "nome" in r["detalhe"], r

    # mesmo nome, documento de outro: também não passa
    r = conferir(
        nome_banco="JORDAN SANTOS DE JESUS",
        documento_banco="***999999**",
        nome_nosso="Jordan Santos de Jesus",
        documento_nosso="73068152291",
    )
    assert r["ok"] is False and "documento" in r["detalhe"], r

    # abreviação no cadastro é a mesma pessoa
    assert nome_bate("RAMON DOS SANTOS ARAUJO", "Ramon Araújo") is True
    assert nome_bate("MARIA SILVA", "MARIA SOUZA") is False

    # ainda não pago: não é divergência, é ausência de resposta
    r = conferir(nome_banco="", documento_banco="", nome_nosso="Fulano", documento_nosso="123")
    assert r["ok"] is None and r["veredito"] == "nao_confirmado", r

    # sem documento nosso não vira acusação
    assert documento_bate("***681522**", "") is None
    assert documento_bate("***681522**", "73068152291") is True
    assert documento_bate("***999999**", "73068152291") is False

    print("conferencia_pix: 9 checagens passaram")


if __name__ == "__main__":
    demo()
