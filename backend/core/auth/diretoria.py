"""Quem é a DIRETORIA da Conecta Mais — fonte única.

Existia espalhado: `CONSULTOR_EXECUTIVO_EMAILS` em ai/consultores, `EMITENTES` no
contract_wizard, `FISCAL_OWNERS_EMAILS` em guias_drive, e uma tupla literal dentro do
payment_controller. Quatro listas com a MESMA intenção — e a do payment_controller tinha
só o Jordan, então a Pyetra levava 403 no log de auditoria de pagamentos enquanto passava
nas outras três. Lista duplicada é lista que diverge.

Decisão do Jordan em 14/09/2026: *"o perfil da Andrya Pyetra Souza de Jesus, login
pjesus@conectamais.pro, precisa ter o mesmo perfil full que eu tenho, todos os recursos e
funções devem ser liberados pra ela"*.

⚠️ Esta lista NÃO é "quem é admin". Admin passa nos gates de módulo por `role='admin'`
(ver `require_permission`). Isto aqui é a camada acima: o que é restrito à DIRETORIA e
onde nem outro admin entra — Consultor CEO, aprovação de pagamento, log de auditoria
financeira. Entrar aqui é decisão do dono, uma pessoa por vez.
"""
from __future__ import annotations

#: E-mails da diretoria. `jordansjesus@gmail.com` é o login alternativo do Jordan e já
#: estava reconhecido no payment_controller — fica.
DIRETORIA: frozenset[str] = frozenset(
    {
        "jjesus@conectamais.pro",
        "jordansjesus@gmail.com",
        "pjesus@conectamais.pro",
    }
)


def e_diretoria(email: str | None) -> bool:
    """True se o e-mail é da diretoria. Tolera None, espaço e caixa alta."""
    return (email or "").strip().lower() in DIRETORIA
