"""
Payment Controller — Pagamentos via Banco Inter
Suporte: boletos, DARF, tributos, lotes
"""

import os

from fastapi import APIRouter
from pydantic import BaseModel



def _build_inter_adapter():
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    creds = BankCredentials(
        client_id=os.getenv("INTER_CLIENT_ID", ""),
        client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
        certificate_path=os.getenv("INTER_CERT_PATH", "") or None,
        private_key_path=os.getenv("INTER_KEY_PATH", "") or None,
        environment=os.getenv("INTER_ENVIRONMENT", "production"),
    )
    return InterAdapter(creds)


router = APIRouter(
    prefix="/banking/payment",
    tags=["Banking — Pagamentos"],
)


class BarcodePaymentRequest(BaseModel):
    codigo_barras: str
    valor: float | None = None
    data_pagamento: str | None = None
    descricao: str = ""
    payable_id: str | None = None


class DARFRequest(BaseModel):
    cnpj_cpf: str = "35710481000103"
    periodo_apuracao: str  # YYYY-MM ou YYYY-MM-DD
    numero_referencia: str  # apenas números, max 30
    valor_principal: float
    valor_multa: float = 0
    valor_juros: float = 0
    codigo_receita: str = "6015"  # 6015=IRPJ 2372=CSLL 0561=COFINS 8109=PIS 2100=INSS
    data_vencimento: str | None = None
    descricao: str = "Pagamento DARF"
    nome_empresa: str = "CONECTAMAIS ELETRONICA LTDA"
    telefone_empresa: str = "92986465328"


class BatchPaymentItem(BaseModel):
    codigo_barras: str
    valor: float | None = None
    data_pagamento: str | None = None
    descricao: str = ""
    meu_identificador: str = ""


class BatchPaymentRequest(BaseModel):
    pagamentos: list[BatchPaymentItem]


