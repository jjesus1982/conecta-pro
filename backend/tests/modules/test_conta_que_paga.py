"""Conta vazia não vira Cora por padrão — vira recusa.

Os dois pontos de saída (lote de diaristas e folha CLT) assumiam 'cora' quando o
campo vinha em branco. Padrão silencioso ali escolhe de qual CNPJ o dinheiro sai.
Medido na tela em 23/08: sem escolher a conta, nenhum OTP era emitido e o modal
fechava sem dizer por quê.
"""

import pytest
from fastapi import HTTPException

from modules.operacional.controllers.redesign_builders.financeiro import _conta_que_paga


@pytest.mark.parametrize("valor", ["cora", "inter", "INTER", " Cora "])
def test_conta_valida_passa(valor):
    assert _conta_que_paga({"origem": valor}) in ("cora", "inter")


@pytest.mark.parametrize("payload", [{}, {"origem": ""}, {"origem": "   "}, {"origem": None},
                                     {"origem": "asaas"}, {"origem": "banco do brasil"}])
def test_conta_ausente_ou_desconhecida_e_recusada(payload):
    with pytest.raises(HTTPException) as e:
        _conta_que_paga(payload)
    assert e.value.status_code == 400
    assert "Escolha a conta" in str(e.value.detail)
