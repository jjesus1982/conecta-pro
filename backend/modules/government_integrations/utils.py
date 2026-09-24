"""
Utilitários para validação e formatação de documentos e integração com serviços governamentais.
"""

import re
from decimal import Decimal
from enum import Enum
from typing import Any


class CalculoError(Exception):
    """Exceção para erros em cálculos trabalhistas."""

    pass


class ESocialEnvironment(Enum):
    """Ambientes do eSocial."""

    PRODUCAO = "1"
    PRODUCAO_RESTRITA = "2"
    HOMOLOGACAO = "2"  # Alias para PRODUCAO_RESTRITA


class DocumentType(Enum):
    """Tipos de documentos fiscais."""

    NFE = "nfe"
    NFCE = "nfce"
    CTE = "cte"


def validar_cpf(cpf: str) -> bool:
    """
    Valida número de CPF.

    Args:
        cpf: String contendo o CPF (pode conter pontos e traços)

    Returns:
        True se CPF válido, False caso contrário
    """
    # Remove formatação
    cpf = re.sub(r"[^0-9]", "", cpf)

    # Verifica se tem 11 dígitos
    if len(cpf) != 11:
        return False

    # Verifica se todos os dígitos são iguais
    if cpf == cpf[0] * 11:
        return False

    # Calcula o primeiro dígito verificador
    # (soma*10) % 11 JÁ É o dígito (10 vira 0). Estava `11 - resto`, que é a fórmula da OUTRA
    # variante (soma % 11) — misturadas, reprovavam CPF válido (529.982.247-25 → dígito 9 em
    # vez de 2). Achado pela frente DGX F6 em 24/09/2026; usada pela consulta à Receita.
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    digito1 = 0 if resto == 10 else resto

    # Verifica o primeiro dígito
    if int(cpf[9]) != digito1:
        return False

    # Calcula o segundo dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    digito2 = 0 if resto == 10 else resto

    # Verifica o segundo dígito
    return int(cpf[10]) == digito2


def validar_cnpj(cnpj: str) -> bool:
    """
    Valida número de CNPJ.

    Args:
        cnpj: String contendo o CNPJ (pode conter pontos, traços e barra)

    Returns:
        True se CNPJ válido, False caso contrário
    """
    # Remove formatação
    cnpj = re.sub(r"[^0-9]", "", cnpj)

    # Verifica se tem 14 dígitos
    if len(cnpj) != 14:
        return False

    # Verifica se todos os dígitos são iguais
    if cnpj == cnpj[0] * 14:
        return False

    # Algoritmo de validação do CNPJ
    multiplicadores1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    multiplicadores2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    # Calcula primeiro dígito verificador
    soma = sum(int(cnpj[i]) * multiplicadores1[i] for i in range(12))
    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto

    # Verifica primeiro dígito
    if int(cnpj[12]) != digito1:
        return False

    # Calcula segundo dígito verificador
    soma = sum(int(cnpj[i]) * multiplicadores2[i] for i in range(13))
    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto

    # Verifica segundo dígito
    return int(cnpj[13]) == digito2


def formatar_cpf(cpf: str) -> str:
    """
    Formata CPF com pontos e traço.

    Args:
        cpf: String contendo o CPF (apenas números)

    Returns:
        CPF formatado (000.000.000-00)
    """
    cpf = re.sub(r"[^0-9]", "", cpf)
    if len(cpf) != 11:
        return cpf

    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def formatar_cnpj(cnpj: str) -> str:
    """
    Formata CNPJ com pontos, barra e traço.

    Args:
        cnpj: String contendo o CNPJ (apenas números)

    Returns:
        CNPJ formatado (00.000.000/0000-00)
    """
    cnpj = re.sub(r"[^0-9]", "", cnpj)
    if len(cnpj) != 14:
        return cnpj

    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


def get_receita_service() -> dict[str, Any] | None:
    """
    Configura e retorna cliente para serviços da Receita Federal.

    Returns:
        Dict com configuração do serviço ou None se não disponível
    """
    # Por enquanto retorna uma configuração básica
    # Em produção, seria configurado com APIs reais da Receita Federal
    return {"base_url": "https://www.receitaws.com.br/v1", "timeout": 30, "available": True}


def get_fgts_inss_manager() -> dict[str, Any] | None:
    """
    Configura e retorna gerenciador para cálculos de FGTS e INSS.

    Returns:
        Dict com configuração do gerenciador ou None se não disponível
    """
    # Configuração básica para cálculos trabalhistas
    return {
        "fgts_rate": Decimal("0.08"),  # 8%
        "inss_table": [
            {"min": Decimal("0.00"), "max": Decimal("1412.00"), "rate": Decimal("0.075")},
            {"min": Decimal("1412.01"), "max": Decimal("2666.68"), "rate": Decimal("0.09")},
            {"min": Decimal("2666.69"), "max": Decimal("4000.03"), "rate": Decimal("0.12")},
            {"min": Decimal("4000.04"), "max": Decimal("7786.02"), "rate": Decimal("0.14")},
        ],
        "available": True,
    }


def get_esocial_transmitter() -> dict[str, Any] | None:
    """
    Configura e retorna transmissor do eSocial.

    Returns:
        Dict com configuração do transmissor ou None se não disponível
    """
    # Configuração básica para transmissão eSocial
    return {
        "ambiente": ESocialEnvironment.PRODUCAO_RESTRITA,
        "url_webservice": "https://webservices.producaorestrita.esocial.gov.br",
        "versao": "2.5.0",
        "available": True,
    }


def get_sefaz_manager() -> dict[str, Any] | None:
    """
    Configura e retorna gerenciador da SEFAZ.

    Returns:
        Dict com configuração do gerenciador ou None se não disponível
    """
    # Configuração básica para SEFAZ
    return {
        "ambiente": "homologacao",
        "uf": "SP",  # Estado padrão
        "certificado_path": None,
        "timeout": 30,
        "available": True,
    }
