"""O corte do teto de mensagens tem de APARECER no relatório.

Em 23/08 uma varredura de 200 dias devolveu exatamente 300 mensagens e nenhum
boleto da Inviolável — que estava na caixa. O relatório dizia "300 mensagens"
como se fosse tudo. Num radar cuja função é não perder conta, corte mudo lê-se
como "não há nada".
"""

from modules.financial.services import boleto_email_service as S


class _IMAPFalso:
    """Caixa com 500 mensagens; nenhuma com boleto (o foco aqui é o corte)."""

    def __init__(self, *a, **k):
        pass

    def login(self, u, s):
        return "OK", []

    def select(self, pasta, readonly=False):
        return "OK", []

    def search(self, charset, criterio):
        return "OK", [b" ".join(str(i).encode() for i in range(1, 501))]

    def fetch(self, num, spec):
        return "OK", [None]

    def logout(self):
        return "BYE", []


def test_corte_aparece_no_relatorio(monkeypatch):
    monkeypatch.setattr(S, "_conf", lambda: ("u@x", "senha", "host", "INBOX"))
    monkeypatch.setattr(S.imaplib, "IMAP4_SSL", _IMAPFalso)
    monkeypatch.setattr(S, "MAX_MENSAGENS", 300)

    rel = S.varrer_e_registrar(None, dias=200, criar=False)

    assert rel["erro"] is None
    assert rel["mensagens"] == 300, "lê o teto"
    assert rel["truncado"] == 200, "e DIZ quantas ficaram de fora"


def test_sem_corte_truncado_e_zero(monkeypatch):
    class _Pequena(_IMAPFalso):
        def search(self, charset, criterio):
            return "OK", [b"1 2 3"]

    monkeypatch.setattr(S, "_conf", lambda: ("u@x", "senha", "host", "INBOX"))
    monkeypatch.setattr(S.imaplib, "IMAP4_SSL", _Pequena)

    rel = S.varrer_e_registrar(None, dias=30, criar=False)
    assert rel["mensagens"] == 3
    assert rel["truncado"] == 0
