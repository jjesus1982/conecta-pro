"""Testes de `modules/crm/services/phone.py`.

Este módulo é o NÚCLEO do dedup de lead: `match_key_br` decide se dois contatos
são a mesma pessoa nos 10 caminhos que criam lead. Estava sem nenhum teste.

O que precisa valer, e por quê:
- formatos diferentes do MESMO número têm que dar a MESMA chave (é o que impede
  o formulário e o WhatsApp de criarem dois leads da mesma pessoa);
- número curto demais devolve None em vez de adivinhar (chave fraca casaria
  pessoas diferentes — pior que duplicar).
"""

import pytest

from modules.crm.services.phone import (
    canonical_br,
    display_br,
    match_key_br,
    only_digits,
    to_e164_br,
)


class TestOnlyDigits:
    def test_remove_tudo_que_nao_e_digito(self):
        assert only_digits("+55 (92) 9 8646-5328") == "5592986465328"

    def test_none_e_vazio_viram_string_vazia(self):
        assert only_digits(None) == ""
        assert only_digits("") == ""


class TestCanonicalBr:
    def test_tira_ddi_55(self):
        assert canonical_br("5592986465328") == "92986465328"

    def test_mantem_sem_ddi(self):
        assert canonical_br("92986465328") == "92986465328"

    def test_vazio_devolve_none(self):
        assert canonical_br("") is None
        assert canonical_br(None) is None

    def test_nao_valida_comprimento(self):
        """`canonical_br` é só NORMALIZADOR — não julga se o número é plausível.
        A guarda de comprimento vive no `match_key_br`, que é quem decide
        identidade. Separar os papéis é proposital."""
        assert canonical_br("12345") == "12345"
        assert match_key_br("12345") is None


class TestMatchKeyBr:
    """A chave de pareamento: DDD + 8 últimos dígitos."""

    # Todos são o MESMO telefone escrito de jeitos diferentes — a chave tem que
    # ser idêntica, senão o dedup falha e nasce lead duplicado.
    MESMO_NUMERO = [
        "92986465328",
        "5592986465328",
        "+55 (92) 9 8646-5328",
        "(92) 98646-5328",
        "92 98646 5328",
        "+55 92 986465328",
    ]

    @pytest.mark.parametrize("bruto", MESMO_NUMERO)
    def test_formatos_diferentes_mesma_chave(self, bruto):
        assert match_key_br(bruto) == "9286465328"

    def test_com_e_sem_nono_digito_casam(self):
        """O 9 extra do celular não pode separar o mesmo contato."""
        assert match_key_br("92986465328") == match_key_br("9286465328")

    def test_ddd_diferente_nao_casa(self):
        """Mesmo sufixo, DDD diferente = pessoas diferentes."""
        assert match_key_br("92986465328") != match_key_br("11986465328")

    def test_curto_demais_devolve_none(self):
        """Nunca adivinhar: sem dígitos suficientes não dá para afirmar que é a
        mesma pessoa. None faz o chamador criar lead novo, que é o seguro."""
        for curto in ("12345", "999", "", None):
            assert match_key_br(curto) is None

    def test_chave_tem_10_caracteres(self):
        assert len(match_key_br("+55 (92) 9 8646-5328")) == 10


class TestToE164Br:
    def test_celular_11_digitos(self):
        assert to_e164_br("(92) 98646-5328") == "+5592986465328"

    def test_fixo_10_digitos(self):
        assert to_e164_br("9232345678") == "+559232345678"

    def test_invalido_devolve_none(self):
        assert to_e164_br("123") is None


class TestDisplayBr:
    def test_formata_celular(self):
        assert display_br("5592986465328") == "+55 (92) 9 8646-5328"

    def test_invalido_nao_quebra(self):
        assert display_br("123") is None


class TestRegressaoDedup:
    """O caso real que motivou tudo: o mesmo contato entrando por caminhos
    diferentes (formulário grava com máscara, WhatsApp grava só dígitos)."""

    def test_formulario_e_whatsapp_convergem(self):
        do_formulario = "(92) 9 9988-7766"
        do_whatsapp = "5592999887766"
        assert match_key_br(do_formulario) == match_key_br(do_whatsapp)

    def test_pessoas_diferentes_nao_convergem(self):
        assert match_key_br("92999887766") != match_key_br("92988776655")
