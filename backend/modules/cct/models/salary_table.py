"""
Tabela Salarial CCT 2026 — SINDECOMPRESTS/SINDICOND-AM.

50 cargos com pisos, adicionais de insalubridade/periculosidade.
Piso geral: R$ 1.670,00 — Reajuste: 7,1% (piso) / 4,5% (acima do piso).
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

# Constantes de reajuste
SALARIO_PISO = Decimal("1670.00")
REAJUSTE_PISO = Decimal("7.1")
REAJUSTE_ACIMA_PISO = Decimal("4.5")


class CargoAdditional(StrEnum):
    """Tipo de adicional vinculado ao cargo."""

    NENHUM = "nenhum"
    INSALUBRIDADE_10 = "insalubridade_10"
    PERICULOSIDADE_30 = "periculosidade_30"
    ADICIONAL_10 = "adicional_10"


@dataclass(frozen=True)
class SalaryEntry:
    """Entrada na tabela salarial CCT."""

    cargo: str
    piso: Decimal
    adicional: CargoAdditional = CargoAdditional.NENHUM


TABELA_SALARIAL_CCT_2026: tuple[SalaryEntry, ...] = (
    SalaryEntry("ADMINISTRADOR (BACHAREL)", Decimal("5854.04")),
    SalaryEntry("ADMINISTRADOR DE CONDOMINIOS (PODER HIERARQUICO)", Decimal("3340.27")),
    SalaryEntry("AGENTE DE FISCALIZACAO", Decimal("1670.00")),
    SalaryEntry("AJUDANTE DE MANUTENCAO", Decimal("1670.00")),
    SalaryEntry("AJUDANTE DE PEDREIRO CONDOMINIAL", Decimal("1670.00")),
    SalaryEntry("ANALISTA DE SISTEMA", Decimal("6639.18")),
    SalaryEntry(
        "ARTIFICE DE MANUTENCAO PREDIAL (ESPECIALIZADO NRS E ISO)",
        Decimal("2186.66"),
    ),
    SalaryEntry("ARTIFICE NAO ESPECIALIZADO", Decimal("1742.52")),
    SalaryEntry("ASCENSORISTA", Decimal("1670.00")),
    SalaryEntry("ASSISTENTE ADMINISTRATIVO CONDOMINIOS EMPRESAS", Decimal("2157.76")),
    SalaryEntry("AUXILIAR ADMINISTRATIVO NIVEL MEDIO", Decimal("1670.00")),
    SalaryEntry("AUXILIAR ADMINISTRATIVO NIVEL TECNICO", Decimal("2917.70")),
    SalaryEntry("AUX ADMINISTRATIVO", Decimal("1670.00")),
    SalaryEntry("AUXILIAR DE BOMBEIRO HIDRAULICO", Decimal("1670.00")),
    SalaryEntry(
        "AUXILIAR DE CONTROLE DE PRAGA HAB A",
        Decimal("1670.00"),
        CargoAdditional.INSALUBRIDADE_10,
    ),
    SalaryEntry(
        "AUXILIAR DE CONTROLE DE PRAGAS HAB B",
        Decimal("1670.00"),
        CargoAdditional.INSALUBRIDADE_10,
    ),
    SalaryEntry(
        "AUXILIAR DE CONTROLE DE PRAGA HAB A+B",
        Decimal("1679.86"),
        CargoAdditional.INSALUBRIDADE_10,
    ),
    SalaryEntry("AUXILIAR DE MANUTENCAO", Decimal("1670.00")),
    SalaryEntry("AUXILIAR DE MANUTENCAO CONDOMINIOS EMPRESAS", Decimal("2072.52")),
    SalaryEntry("AUXILIAR DE SERVICOS DE REFRIGERACAO", Decimal("1673.50")),
    SalaryEntry("BOMBEIRO HIDRAULICO", Decimal("2232.55")),
    SalaryEntry(
        "CARPINTEIROS E PEDREIROS CONDOMINIOS EMPRESAS",
        Decimal("2116.67"),
        CargoAdditional.ADICIONAL_10,
    ),
    SalaryEntry("CONCIERGE", Decimal("1670.00")),
    SalaryEntry("CONTROLADOR DE ACESSO", Decimal("1670.00")),
    SalaryEntry("COPEIRO A", Decimal("1670.00")),
    SalaryEntry(
        "ELETRICISTA DE ALTA TENSAO",
        Decimal("2180.78"),
        CargoAdditional.PERICULOSIDADE_30,
    ),
    SalaryEntry(
        "ELETRICISTA DE BAIXA TENSAO",
        Decimal("1670.00"),
        CargoAdditional.PERICULOSIDADE_30,
    ),
    SalaryEntry("ENCARREGADO DE ADMINISTRACAO", Decimal("3059.78")),
    SalaryEntry("ENCARREGADO DE MANUTENCAO", Decimal("3059.78")),
    SalaryEntry("ENCARREGADO DE OBRA", Decimal("3059.78")),
    SalaryEntry("ENCARREGADO DE PATRIMONIO", Decimal("3059.78")),
    SalaryEntry("ENCARREGADO DE SERVICOS GERAIS E SUPERVISOR", Decimal("2785.26")),
    SalaryEntry("FISCAL DE PATIO", Decimal("1670.00")),
    SalaryEntry("JARDINEIROS", Decimal("1670.00")),
    SalaryEntry("LIDER DE JARDINAGEM", Decimal("1965.97")),
    SalaryEntry("LIDER DE PORTARIA", Decimal("1787.53")),
    SalaryEntry("LIDER DE SERVICOS GERAIS", Decimal("1965.97")),
    SalaryEntry("MANUTENCAO DE CONDOMINIOS", Decimal("2785.26")),
    SalaryEntry("MONITORADOR DE CFTV", Decimal("1670.00")),
    SalaryEntry("MONITORADOR ELETRONICO", Decimal("1670.00")),
    SalaryEntry("PINTOR CONDOMINIAL", Decimal("2118.19")),
    SalaryEntry(
        "PISCINEIRO",
        Decimal("1670.00"),
        CargoAdditional.INSALUBRIDADE_10,
    ),
    SalaryEntry("PORTEIROS AGENTE DE PORTARIA GUARDETE", Decimal("1670.00")),
    SalaryEntry("RECEPCIONISTA DE CONDOMINIOS", Decimal("1670.00")),
    SalaryEntry("SECRETARIA DE CONDOMINIOS EMPRESAS", Decimal("2785.26")),
    SalaryEntry("SERVICOS GERAIS FAXINEIRO", Decimal("1670.00")),
    SalaryEntry("SUPERVISOR DE CONDOMINIOS ORGANICO", Decimal("3340.27")),
    SalaryEntry(
        "TECNICO EM MANUTENCAO EM MAQUINAS E EQUIPAMENTOS",
        Decimal("1870.19"),
        CargoAdditional.PERICULOSIDADE_30,
    ),
    SalaryEntry("TECNICO EM SEGURANCA DO TRABALHO", Decimal("1947.12")),
    SalaryEntry("TRATORISTA MARINA", Decimal("1776.68")),
    SalaryEntry("ZELADOR RESIDENTE CONDOMINIOS", Decimal("2777.46")),
)


def get_piso_by_cargo(cargo_nome: str) -> SalaryEntry | None:
    """Busca entrada na tabela salarial pelo nome do cargo (case-insensitive)."""
    cargo_upper = cargo_nome.strip().upper()
    for entry in TABELA_SALARIAL_CCT_2026:
        if entry.cargo == cargo_upper:
            return entry
    return None


def get_all_cargos() -> list[str]:
    """Retorna lista de todos os cargos da CCT."""
    return [entry.cargo for entry in TABELA_SALARIAL_CCT_2026]
