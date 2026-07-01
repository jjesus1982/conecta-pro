"""
modules/fase5/cct_compliance/models.py - CCT Models
===================================================
Modelos de dados para compliance CCT SINDCOND 2026
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import StatusValidacao, TipoBeneficio, TipoCargo, TipoJornada


class SalarioBase(BaseModel):
    """Salario base por cargo conforme CCT SINDCOND 2026."""

    model_config = ConfigDict(frozen=True)

    cargo: TipoCargo
    piso_salarial: Decimal = Field(..., ge=Decimal("0"))
    vigencia_inicio: date
    vigencia_fim: date
    reajuste_percentual: Decimal = Field(default=Decimal("7.1"))  # 2026
    sindicato: str = Field(default="SINDCOND")
    regiao: str = Field(default="SP")

    @property
    def salario_com_reajuste(self) -> Decimal:
        """Calcula salario com reajuste."""
        return (self.piso_salarial * (1 + self.reajuste_percentual / 100)).quantize(Decimal("0.01"))


class Beneficio(BaseModel):
    """Beneficio conforme CCT."""

    model_config = ConfigDict(frozen=True)

    tipo: TipoBeneficio
    valor_diario: Decimal | None = None
    valor_mensal: Decimal | None = None
    obrigatorio: bool = True
    descricao: str = ""

    @property
    def valor_estimado_mensal(self) -> Decimal:
        """Estima valor mensal do beneficio."""
        if self.valor_mensal:
            return self.valor_mensal
        if self.valor_diario:
            return (self.valor_diario * Decimal("22")).quantize(Decimal("0.01"))
        return Decimal("0")


class JornadaTrabalho(BaseModel):
    """Jornada de trabalho conforme CCT."""

    model_config = ConfigDict(frozen=True)

    tipo: TipoJornada
    horas_semanais: int
    horas_diarias: Decimal
    dias_trabalho: int
    intervalo_minutos: int = 60
    adicional_noturno_percentual: Decimal = Field(default=Decimal("20"))
    hora_extra_50_percentual: Decimal = Field(default=Decimal("50"))
    hora_extra_100_percentual: Decimal = Field(default=Decimal("100"))

    @property
    def carga_horaria_mensal(self) -> Decimal:
        """Calcula carga horaria mensal."""
        return (Decimal(str(self.horas_semanais)) * Decimal("4.33")).quantize(Decimal("0.01"))


class CargoSINDCOND(BaseModel):
    """Cargo completo conforme CCT SINDCOND 2026."""

    cargo_id: UUID = Field(default_factory=uuid4)
    tipo: TipoCargo
    nome: str
    descricao: str
    cbo: str = Field(..., pattern=r"^\d{4}-\d{2}$")

    # Salario
    salario_base: SalarioBase

    # Jornada
    jornadas_permitidas: list[TipoJornada]
    jornada_padrao: TipoJornada

    # Beneficios obrigatorios
    beneficios_obrigatorios: list[TipoBeneficio]

    # Adicionais
    permite_insalubridade: bool = False
    permite_periculosidade: bool = False

    # Requisitos
    escolaridade_minima: str = "Ensino Fundamental"
    experiencia_minima_meses: int = 0

    # Audit
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ValidacaoCCT(BaseModel):
    """Resultado de validacao CCT."""

    validacao_id: UUID = Field(default_factory=uuid4)
    funcionario_id: UUID | None = None
    cargo: TipoCargo
    data_validacao: datetime = Field(default_factory=datetime.utcnow)

    # Status
    status: StatusValidacao = Field(default=StatusValidacao.PENDENTE)
    score: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))

    # Validacoes individuais
    salario_conforme: bool = False
    salario_informado: Decimal = Field(default=Decimal("0"))
    salario_minimo_cct: Decimal = Field(default=Decimal("0"))
    diferenca_salario: Decimal = Field(default=Decimal("0"))

    jornada_conforme: bool = False
    jornada_informada: TipoJornada | None = None

    beneficios_conformes: bool = False
    beneficios_faltantes: list[TipoBeneficio] = Field(default_factory=list)

    # Alertas e recomendacoes
    alertas: list[str] = Field(default_factory=list)
    recomendacoes: list[str] = Field(default_factory=list)

    # Detalhes
    detalhes: dict[str, Any] = Field(default_factory=dict)

    def calcular_score(self) -> None:
        """Calcula score de conformidade."""
        pontos = Decimal("0")
        Decimal("100")

        # Salario: 40 pontos
        if self.salario_conforme:
            pontos += Decimal("40")

        # Jornada: 30 pontos
        if self.jornada_conforme:
            pontos += Decimal("30")

        # Beneficios: 30 pontos
        if self.beneficios_conformes:
            pontos += Decimal("30")

        self.score = pontos

        # Definir status
        if pontos >= Decimal("100"):
            self.status = StatusValidacao.CONFORME
        elif pontos >= Decimal("70"):
            self.status = StatusValidacao.ALERTA
        else:
            self.status = StatusValidacao.NAO_CONFORME


# Tabela de Pisos Salariais SINDCOND 2026 (com reajuste de 7.1%)
TABELA_PISOS_SINDCOND_2026: dict[TipoCargo, Decimal] = {
    # Portaria
    TipoCargo.PORTEIRO: Decimal("1847.12"),
    TipoCargo.PORTEIRO_LIDER: Decimal("2124.19"),
    TipoCargo.CONTROLADOR_ACESSO: Decimal("1847.12"),
    TipoCargo.AGENTE_PORTARIA: Decimal("1724.51"),
    TipoCargo.AGENTE_PORTARIA_LIDER: Decimal("2456.78"),
    # Limpeza
    TipoCargo.ZELADOR: Decimal("1970.23"),
    TipoCargo.FAXINEIRO: Decimal("1601.90"),
    TipoCargo.AUXILIAR_LIMPEZA: Decimal("1540.13"),
    TipoCargo.ENCARREGADO_LIMPEZA: Decimal("2247.30"),
    TipoCargo.JARDINEIRO: Decimal("1724.51"),
    TipoCargo.PISCINEIRO: Decimal("1847.12"),
    # Manutencao
    TipoCargo.AUXILIAR_MANUTENCAO: Decimal("1724.51"),
    TipoCargo.ELETRICISTA: Decimal("2370.41"),
    TipoCargo.ENCANADOR: Decimal("2124.19"),
    TipoCargo.PINTOR: Decimal("1970.23"),
    TipoCargo.PEDREIRO: Decimal("2124.19"),
    TipoCargo.MARCENEIRO: Decimal("2124.19"),
    # Administrativo
    TipoCargo.SINDICO_PROFISSIONAL: Decimal("4500.00"),
    TipoCargo.GERENTE_PREDIAL: Decimal("3800.00"),
    TipoCargo.AUXILIAR_ADMINISTRATIVO: Decimal("1847.12"),
    TipoCargo.RECEPCIONISTA: Decimal("1724.51"),
    TipoCargo.SECRETARIA: Decimal("1970.23"),
    # Especializado
    TipoCargo.ASCENSORISTA: Decimal("1847.12"),
    TipoCargo.GARAGISTA: Decimal("1724.51"),
    TipoCargo.MANOBRISTA: Decimal("1847.12"),
    TipoCargo.FOLGUISTA: Decimal("1724.51"),
    TipoCargo.MOTORISTA: Decimal("2247.30"),
    # Supervisao
    TipoCargo.SUPERVISOR_PORTARIA: Decimal("2616.63"),
    TipoCargo.SUPERVISOR_LIMPEZA: Decimal("2493.52"),
    TipoCargo.SUPERVISOR_MANUTENCAO: Decimal("2739.74"),
    TipoCargo.ENCARREGADO_GERAL: Decimal("2862.85"),
    # Outros
    TipoCargo.CASEIRO: Decimal("1847.12"),
    TipoCargo.GOVERNANTA: Decimal("2247.30"),
    TipoCargo.COPEIRA: Decimal("1601.90"),
    TipoCargo.COZINHEIRA: Decimal("1847.12"),
}

# Beneficios obrigatorios CCT 2026
BENEFICIOS_CCT_2026: dict[TipoBeneficio, Beneficio] = {
    TipoBeneficio.VALE_ALIMENTACAO: Beneficio(
        tipo=TipoBeneficio.VALE_ALIMENTACAO,
        valor_diario=Decimal("22.00"),
        obrigatorio=True,
        descricao="Vale alimentacao R$ 22,00/dia trabalhado",
    ),
    TipoBeneficio.CESTA_BASICA: Beneficio(
        tipo=TipoBeneficio.CESTA_BASICA,
        valor_mensal=Decimal("18.00"),
        obrigatorio=True,
        descricao="Auxilio cesta basica R$ 18,00/mes",
    ),
    TipoBeneficio.VALE_TRANSPORTE: Beneficio(
        tipo=TipoBeneficio.VALE_TRANSPORTE, obrigatorio=True, descricao="Vale transporte conforme legislacao"
    ),
    TipoBeneficio.SEGURO_VIDA: Beneficio(
        tipo=TipoBeneficio.SEGURO_VIDA, obrigatorio=True, descricao="Seguro de vida em grupo"
    ),
}
