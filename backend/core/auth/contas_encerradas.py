"""E-mails ENCERRADOS — não entram e não podem ser recriados.

Origem (14/09/2026): o Jordan mandou encerrar `andryapytt08@gmail.com`, o Gmail pessoal
pelo qual a Pyetra vinha entrando — *"este e-mail sai, deixa de existir, o único cadastro
da Pyetra Jesus vai ser por meio do e-mail pjesus@conectamais.pro"*.

APAGAR A LINHA NÃO BASTA, e é por isso que este arquivo existe. O callback do Google
resolve o usuário **pelo e-mail** e, quando não encontra, CRIA:

    result = await db.execute(select(User).where(User.email == email))
    if not user:
        user = User(email=email, role="pending", is_active=True, google_id=google_id)

Ou seja: apaga-se a conta e, no primeiro clique em «entrar com Google», ela volta — como
`pending`, sem permissão, mas VOLTA, e ainda toca o sino dos admins. Conta encerrada que
ressuscita sozinha não está encerrada.

A lista vale nas DUAS portas de cadastro: `/auth/register` (senha) e `/auth/google/callback`.

⚠️ Isto NÃO é punição nem bloqueio de segurança — é encerramento administrativo. Tirar um
e-mail daqui é decisão do dono, do mesmo jeito que pôr.
"""
from __future__ import annotations

#: E-mails encerrados, com a data e o motivo ao lado — quem ler daqui a um ano precisa
#: saber por quê, e a lista sem motivo vira folclore.
ENCERRADAS: dict[str, str] = {
    # Conta pessoal da Pyetra (Google). O cadastro dela passou a ser só o corporativo
    # pjesus@conectamais.pro. Backup da linha em /var/lib/conecta/contas_removidas/.
    "andryapytt08@gmail.com": "encerrada em 14/09/2026 por decisão do Jordan — "
                              "o cadastro da Pyetra é pjesus@conectamais.pro",
}


def esta_encerrada(email: str | None) -> str | None:
    """Devolve o MOTIVO se o e-mail está encerrado, ou None. Tolera espaço e caixa alta."""
    return ENCERRADAS.get((email or "").strip().lower())
