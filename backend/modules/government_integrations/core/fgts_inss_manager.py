"""
Module: fgts_inss_manager
Description: Gerenciador de integracoes com FGTS e INSS
             - Calculo e recolhimento FGTS
             - Contribuicoes previdenciarias INSS
             - Geracao de guias (GRF, GPS, DARF)
             - Consultas cadastrais e certidoes
Author: Claude AI + Human Developer
Date: 2026-01-10
Quality Score Target: 99+/100
Compliance: Lei 8.036/1990 (FGTS), Lei 8.212/1991 (INSS)
"""

import hashlib
import logging
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

Base = declarative_base()


# =============================================================================
# ENUMS
# =============================================================================


class TipoRecolhimento(StrEnum):
    """Tipos de recolhimento FGTS."""

    MENSAL = "mensal"
    RESCISORIO = "rescisorio"
    RECURSAL = "recursal"
    PARCELAMENTO = "parcelamento"


class CodigoRecolhimento(StrEnum):
    """Codigos de recolhimento FGTS."""

    RECOLHIMENTO_MENSAL = "115"  # Recolhimento ao FGTS
    RECOLHIMENTO_RESCISORIO = "418"  # Deposito rescisorio
    RECOLHIMENTO_RECURSAL = "604"  # Deposito recursal
    RECOLHIMENTO_DECLARATORIO = "145"  # Recolhimento declaratorio


class ModalidadeSaque(StrEnum):
    """Modalidades de saque FGTS."""

    DEMISSAO_SEM_JUSTA_CAUSA = "01"
    TERMINO_CONTRATO = "02"
    APOSENTADORIA = "03"
    FALECIMENTO = "04"
    DOENCA_GRAVE = "05"
    CASA_PROPRIA = "06"
    SAQUE_ANIVERSARIO = "07"
    CALAMIDADE = "08"


class CategoriaContribuinte(StrEnum):
    """Categorias de contribuinte INSS."""

    EMPREGADO = "empregado"
    DOMESTICO = "domestico"
    CONTRIBUINTE_INDIVIDUAL = "contribuinte_individual"
    SEGURADO_ESPECIAL = "segurado_especial"
    FACULTATIVO = "facultativo"
    MEI = "mei"


class TipoGuia(StrEnum):
    """Tipos de guia de recolhimento."""

    GRF = "grf"  # Guia de Recolhimento do FGTS
    GRRF = "grrf"  # Guia de Recolhimento Rescisorio do FGTS
    GPS = "gps"  # Guia da Previdencia Social
    DARF = "darf"  # Documento de Arrecadacao de Receitas Federais
    DAE = "dae"  # Documento de Arrecadacao do eSocial


class StatusGuia(StrEnum):
    """Status de guia de recolhimento."""

    GERADA = "gerada"
    PENDENTE = "pendente"
    PAGA = "paga"
    VENCIDA = "vencida"
    CANCELADA = "cancelada"


class StatusCertidao(StrEnum):
    """Status de certidao."""

    NEGATIVA = "negativa"
    POSITIVA = "positiva"
    POSITIVA_EFEITO_NEGATIVA = "positiva_efeito_negativa"


class TipoCertidao(StrEnum):
    """Tipos de certidao."""

    CRF = "crf"  # Certificado de Regularidade do FGTS
    CND_INSS = "cnd_inss"  # Certidao Negativa de Debitos INSS
    CPEND = "cpend"  # Certidao Positiva com Efeito de Negativa


# =============================================================================
# EXCEPTIONS
# =============================================================================


class FGTSINSSError(Exception):
    """Erro base para operacoes FGTS/INSS."""

    def __init__(self, message: str, code: str | None = None, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class CalculoError(FGTSINSSError):
    """Erro no calculo de valores."""

    pass


class GuiaError(FGTSINSSError):
    """Erro na geracao de guias."""

    pass


class ConsultaError(FGTSINSSError):
    """Erro em consultas."""

    pass


class TransmissaoError(FGTSINSSError):
    """Erro na transmissao de dados."""

    pass


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass
class TabelaINSS:
    """Tabela de contribuicao INSS (aliquotas progressivas)."""

    vigencia: date
    faixas: list[dict[str, Decimal]] = field(default_factory=list)
    teto: Decimal = Decimal("0")

    @classmethod
    def tabela_2024(cls) -> "TabelaINSS":
        """Tabela INSS vigente em 2024."""
        return cls(
            vigencia=date(2024, 1, 1),
            faixas=[
                {"ate": Decimal("1412.00"), "aliquota": Decimal("7.5")},
                {"ate": Decimal("2666.68"), "aliquota": Decimal("9.0")},
                {"ate": Decimal("4000.03"), "aliquota": Decimal("12.0")},
                {"ate": Decimal("7786.02"), "aliquota": Decimal("14.0")},
            ],
            teto=Decimal("7786.02"),
        )

    @classmethod
    def tabela_2025(cls) -> "TabelaINSS":
        """Tabela INSS vigente em 2025."""
        return cls(
            vigencia=date(2025, 1, 1),
            faixas=[
                {"ate": Decimal("1518.00"), "aliquota": Decimal("7.5")},
                {"ate": Decimal("2793.88"), "aliquota": Decimal("9.0")},
                {"ate": Decimal("4190.83"), "aliquota": Decimal("12.0")},
                {"ate": Decimal("8157.41"), "aliquota": Decimal("14.0")},
            ],
            teto=Decimal("8157.41"),
        )


@dataclass
class Trabalhador:
    """Dados do trabalhador."""

    id: str
    cpf: str
    pis_pasep: str
    nome: str
    data_admissao: date
    data_nascimento: date | None = None
    categoria: CategoriaContribuinte = CategoriaContribuinte.EMPREGADO
    cargo: str | None = None
    ctps_numero: str | None = None
    ctps_serie: str | None = None
    ctps_uf: str | None = None


@dataclass
class Remuneracao:
    """Dados de remuneracao do trabalhador."""

    trabalhador_id: str
    competencia: date  # Primeiro dia do mes
    salario_base: Decimal
    horas_extras: Decimal = Decimal("0")
    adicional_noturno: Decimal = Decimal("0")
    comissoes: Decimal = Decimal("0")
    gratificacoes: Decimal = Decimal("0")
    dsr: Decimal = Decimal("0")  # Descanso semanal remunerado
    outros: Decimal = Decimal("0")
    faltas_dias: int = 0
    faltas_horas: Decimal = Decimal("0")

    @property
    def total_proventos(self) -> Decimal:
        """Calcula total de proventos."""
        return (
            self.salario_base
            + self.horas_extras
            + self.adicional_noturno
            + self.comissoes
            + self.gratificacoes
            + self.dsr
            + self.outros
        )

    @property
    def base_fgts(self) -> Decimal:
        """Base de calculo do FGTS."""
        return self.total_proventos

    @property
    def base_inss(self) -> Decimal:
        """Base de calculo do INSS."""
        return self.total_proventos


@dataclass
class CalculoFGTS:
    """Resultado do calculo FGTS."""

    trabalhador_id: str
    competencia: date
    base_calculo: Decimal
    aliquota: Decimal  # 8% padrao
    valor_deposito: Decimal
    valor_multa: Decimal = Decimal("0")  # 40% rescisao
    saldo_anterior: Decimal = Decimal("0")
    saldo_atual: Decimal = Decimal("0")
    tipo: TipoRecolhimento = TipoRecolhimento.MENSAL

    @property
    def valor_total(self) -> Decimal:
        """Valor total a recolher."""
        return self.valor_deposito + self.valor_multa


@dataclass
class CalculoINSS:
    """Resultado do calculo INSS."""

    trabalhador_id: str
    competencia: date
    base_calculo: Decimal
    valor_contribuicao: Decimal
    aliquota_efetiva: Decimal
    faixas_aplicadas: list[dict] = field(default_factory=list)
    teto_aplicado: bool = False
    categoria: CategoriaContribuinte = CategoriaContribuinte.EMPREGADO


@dataclass
class Guia:
    """Guia de recolhimento."""

    id: str
    tipo: TipoGuia
    competencia: date
    vencimento: date
    valor_principal: Decimal
    valor_juros: Decimal = Decimal("0")
    valor_multa: Decimal = Decimal("0")
    valor_total: Decimal = Decimal("0")
    codigo_barras: str | None = None
    linha_digitavel: str | None = None
    numero_documento: str | None = None
    status: StatusGuia = StatusGuia.GERADA
    empresa_cnpj: str | None = None
    empresa_razao_social: str | None = None
    data_geracao: datetime = field(default_factory=datetime.now)
    data_pagamento: datetime | None = None
    trabalhadores: list[str] = field(default_factory=list)
    detalhamento: dict = field(default_factory=dict)


@dataclass
class Certidao:
    """Certidao de regularidade."""

    id: str
    tipo: TipoCertidao
    status: StatusCertidao
    documento: str  # CNPJ ou CPF
    razao_social: str | None = None
    data_emissao: datetime = field(default_factory=datetime.now)
    data_validade: datetime = field(default_factory=datetime.now)
    codigo_controle: str | None = None
    observacoes: str | None = None
    pendencias: list[dict] = field(default_factory=list)


@dataclass
class ExtratoFGTS:
    """Extrato de conta FGTS."""

    pis_pasep: str
    empresa_cnpj: str
    saldo_total: Decimal
    movimentacoes: list[dict] = field(default_factory=list)
    data_consulta: datetime = field(default_factory=datetime.now)
    conta_ativa: bool = True


# =============================================================================
# MODELS SQLAlchemy
# =============================================================================


class GuiaRecolhimentoModel(Base):
    """Modelo de guia de recolhimento."""

    __tablename__ = "fgts_inss_guias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(SQLEnum(TipoGuia), nullable=False)
    competencia = Column(Date, nullable=False)
    vencimento = Column(Date, nullable=False)

    valor_principal = Column(Numeric(15, 2), nullable=False)
    valor_juros = Column(Numeric(15, 2), default=0)
    valor_multa = Column(Numeric(15, 2), default=0)
    valor_total = Column(Numeric(15, 2), nullable=False)

    codigo_barras = Column(String(60))
    linha_digitavel = Column(String(60))
    numero_documento = Column(String(30))

    empresa_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    empresa_cnpj = Column(String(14), nullable=False)
    empresa_razao_social = Column(String(200))

    status = Column(SQLEnum(StatusGuia), default=StatusGuia.GERADA)
    data_geracao = Column(DateTime, default=datetime.utcnow)
    data_pagamento = Column(DateTime)

    trabalhadores = Column(JSONB, default=list)
    detalhamento = Column(JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_guias_empresa_competencia", "empresa_id", "competencia"),
        Index("ix_guias_tipo_status", "tipo", "status"),
    )


class RecolhimentoFGTSModel(Base):
    """Modelo de recolhimento FGTS individual."""

    __tablename__ = "fgts_recolhimentos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guia_id = Column(UUID(as_uuid=True), ForeignKey("fgts_inss_guias.id"))

    trabalhador_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    trabalhador_cpf = Column(String(11), nullable=False)
    trabalhador_pis = Column(String(11), nullable=False)
    trabalhador_nome = Column(String(200))

    competencia = Column(Date, nullable=False)
    tipo = Column(SQLEnum(TipoRecolhimento), default=TipoRecolhimento.MENSAL)
    codigo_recolhimento = Column(SQLEnum(CodigoRecolhimento))

    base_calculo = Column(Numeric(15, 2), nullable=False)
    aliquota = Column(Numeric(5, 2), default=8)
    valor_deposito = Column(Numeric(15, 2), nullable=False)
    valor_multa = Column(Numeric(15, 2), default=0)
    valor_total = Column(Numeric(15, 2), nullable=False)

    saldo_anterior = Column(Numeric(15, 2), default=0)
    saldo_atual = Column(Numeric(15, 2), default=0)

    data_calculo = Column(DateTime, default=datetime.utcnow)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_fgts_trabalhador_competencia", "trabalhador_id", "competencia"),)


class ContribuicaoINSSModel(Base):
    """Modelo de contribuicao INSS individual."""

    __tablename__ = "inss_contribuicoes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    guia_id = Column(UUID(as_uuid=True), ForeignKey("fgts_inss_guias.id"))

    trabalhador_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    trabalhador_cpf = Column(String(11), nullable=False)
    trabalhador_nome = Column(String(200))
    categoria = Column(SQLEnum(CategoriaContribuinte))

    competencia = Column(Date, nullable=False)

    base_calculo = Column(Numeric(15, 2), nullable=False)
    valor_contribuicao = Column(Numeric(15, 2), nullable=False)
    aliquota_efetiva = Column(Numeric(5, 4), nullable=False)

    faixas_aplicadas = Column(JSONB, default=list)
    teto_aplicado = Column(Boolean, default=False)

    data_calculo = Column(DateTime, default=datetime.utcnow)

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_inss_trabalhador_competencia", "trabalhador_id", "competencia"),)


class CertidaoModel(Base):
    """Modelo de certidao emitida/consultada."""

    __tablename__ = "fgts_inss_certidoes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tipo = Column(SQLEnum(TipoCertidao), nullable=False)
    status = Column(SQLEnum(StatusCertidao), nullable=False)

    documento = Column(String(14), nullable=False, index=True)
    razao_social = Column(String(200))

    data_emissao = Column(DateTime, nullable=False)
    data_validade = Column(DateTime, nullable=False)
    codigo_controle = Column(String(50))

    observacoes = Column(Text)
    pendencias = Column(JSONB, default=list)

    created_at = Column(DateTime, default=datetime.utcnow)


# =============================================================================
# CALCULATORS
# =============================================================================


class CalculadoraFGTS:
    """Calculadora de FGTS."""

    ALIQUOTA_PADRAO = Decimal("8.0")
    ALIQUOTA_APRENDIZ = Decimal("2.0")
    MULTA_RESCISORIA = Decimal("40.0")
    MULTA_RESCISORIA_CULPA_RECIPROCA = Decimal("20.0")

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.CalculadoraFGTS")

    def calcular_deposito_mensal(
        self, trabalhador: Trabalhador, remuneracao: Remuneracao, is_aprendiz: bool = False
    ) -> CalculoFGTS:
        """
        Calcula deposito mensal do FGTS.

        Args:
            trabalhador: Dados do trabalhador
            remuneracao: Dados da remuneracao
            is_aprendiz: Se e menor aprendiz (aliquota 2%)

        Returns:
            Resultado do calculo FGTS
        """
        try:
            aliquota = self.ALIQUOTA_APRENDIZ if is_aprendiz else self.ALIQUOTA_PADRAO
            base = remuneracao.base_fgts

            valor_deposito = (base * aliquota / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            self.logger.info(
                f"FGTS calculado para {trabalhador.cpf}: base={base}, aliquota={aliquota}%, valor={valor_deposito}"
            )

            return CalculoFGTS(
                trabalhador_id=trabalhador.id,
                competencia=remuneracao.competencia,
                base_calculo=base,
                aliquota=aliquota,
                valor_deposito=valor_deposito,
                tipo=TipoRecolhimento.MENSAL,
            )

        except Exception as e:
            self.logger.error(f"Erro ao calcular FGTS: {e}")
            raise CalculoError(f"Erro no calculo FGTS: {e}")

    def calcular_rescisao(
        self,
        trabalhador: Trabalhador,
        saldo_fgts: Decimal,
        motivo: ModalidadeSaque,
        remuneracao_final: Remuneracao | None = None,
        aviso_previo_indenizado: bool = False,
        valor_aviso: Decimal = Decimal("0"),
    ) -> CalculoFGTS:
        """
        Calcula FGTS rescisorio.

        Args:
            trabalhador: Dados do trabalhador
            saldo_fgts: Saldo atual na conta FGTS
            motivo: Modalidade de saque
            remuneracao_final: Remuneracao do mes da rescisao
            aviso_previo_indenizado: Se tem aviso previo indenizado
            valor_aviso: Valor do aviso previo

        Returns:
            Resultado do calculo FGTS rescisorio
        """
        try:
            # Deposito do mes
            valor_deposito = Decimal("0")
            base_calculo = Decimal("0")

            if remuneracao_final:
                base_calculo = remuneracao_final.base_fgts
                valor_deposito = (base_calculo * self.ALIQUOTA_PADRAO / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            # FGTS sobre aviso previo indenizado
            if aviso_previo_indenizado and valor_aviso > 0:
                fgts_aviso = (valor_aviso * self.ALIQUOTA_PADRAO / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                valor_deposito += fgts_aviso
                base_calculo += valor_aviso

            # Multa rescisoria
            valor_multa = Decimal("0")
            if motivo == ModalidadeSaque.DEMISSAO_SEM_JUSTA_CAUSA:
                # 40% sobre saldo total (incluindo deposito do mes)
                saldo_para_multa = saldo_fgts + valor_deposito
                valor_multa = (saldo_para_multa * self.MULTA_RESCISORIA / Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            saldo_final = saldo_fgts + valor_deposito

            self.logger.info(
                f"FGTS rescisorio calculado: deposito={valor_deposito}, multa={valor_multa}, saldo_final={saldo_final}"
            )

            return CalculoFGTS(
                trabalhador_id=trabalhador.id,
                competencia=date.today().replace(day=1),
                base_calculo=base_calculo,
                aliquota=self.ALIQUOTA_PADRAO,
                valor_deposito=valor_deposito,
                valor_multa=valor_multa,
                saldo_anterior=saldo_fgts,
                saldo_atual=saldo_final,
                tipo=TipoRecolhimento.RESCISORIO,
            )

        except Exception as e:
            self.logger.error(f"Erro ao calcular FGTS rescisorio: {e}")
            raise CalculoError(f"Erro no calculo FGTS rescisorio: {e}")

    def calcular_13_salario(
        self,
        trabalhador: Trabalhador,
        valor_13: Decimal,
        parcela: int = 2,  # 1 ou 2 parcela
    ) -> CalculoFGTS:
        """
        Calcula FGTS sobre 13o salario.

        Args:
            trabalhador: Dados do trabalhador
            valor_13: Valor do 13o salario (parcela)
            parcela: Numero da parcela (1 ou 2)

        Returns:
            Resultado do calculo
        """
        try:
            # FGTS e recolhido apenas na 2a parcela sobre o total
            if parcela == 1:
                return CalculoFGTS(
                    trabalhador_id=trabalhador.id,
                    competencia=date.today().replace(day=1),
                    base_calculo=Decimal("0"),
                    aliquota=self.ALIQUOTA_PADRAO,
                    valor_deposito=Decimal("0"),
                    tipo=TipoRecolhimento.MENSAL,
                )

            valor_deposito = (valor_13 * self.ALIQUOTA_PADRAO / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            return CalculoFGTS(
                trabalhador_id=trabalhador.id,
                competencia=date(date.today().year, 12, 1),
                base_calculo=valor_13,
                aliquota=self.ALIQUOTA_PADRAO,
                valor_deposito=valor_deposito,
                tipo=TipoRecolhimento.MENSAL,
            )

        except Exception as e:
            self.logger.error(f"Erro ao calcular FGTS 13o: {e}")
            raise CalculoError(f"Erro no calculo FGTS 13o: {e}")


class CalculadoraINSS:
    """Calculadora de contribuicoes INSS com aliquotas progressivas."""

    def __init__(self, tabela: TabelaINSS | None = None):
        self.logger = logging.getLogger(f"{__name__}.CalculadoraINSS")
        self.tabela = tabela or TabelaINSS.tabela_2025()

    def atualizar_tabela(self, tabela: TabelaINSS) -> None:
        """Atualiza tabela de contribuicao."""
        self.tabela = tabela
        self.logger.info(f"Tabela INSS atualizada para vigencia {tabela.vigencia}")

    def calcular_contribuicao(self, trabalhador: Trabalhador, remuneracao: Remuneracao) -> CalculoINSS:
        """
        Calcula contribuicao INSS com aliquotas progressivas.

        Args:
            trabalhador: Dados do trabalhador
            remuneracao: Dados da remuneracao

        Returns:
            Resultado do calculo INSS
        """
        try:
            base = min(remuneracao.base_inss, self.tabela.teto)
            teto_aplicado = remuneracao.base_inss > self.tabela.teto

            valor_total = Decimal("0")
            faixas_aplicadas = []
            valor_anterior = Decimal("0")

            for faixa in self.tabela.faixas:
                limite = faixa["ate"]
                aliquota = faixa["aliquota"]

                if base <= valor_anterior:
                    break

                base_faixa = min(base, limite) - valor_anterior

                if base_faixa > 0:
                    valor_faixa = (base_faixa * aliquota / Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_UP
                    )
                    valor_total += valor_faixa

                    faixas_aplicadas.append(
                        {
                            "faixa_ate": str(limite),
                            "aliquota": str(aliquota),
                            "base_faixa": str(base_faixa),
                            "valor": str(valor_faixa),
                        }
                    )

                valor_anterior = limite

            aliquota_efetiva = Decimal("0")
            if base > 0:
                aliquota_efetiva = (valor_total / base * Decimal("100")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                )

            self.logger.info(
                f"INSS calculado para {trabalhador.cpf}: "
                f"base={base}, valor={valor_total}, aliquota_efetiva={aliquota_efetiva}%"
            )

            return CalculoINSS(
                trabalhador_id=trabalhador.id,
                competencia=remuneracao.competencia,
                base_calculo=base,
                valor_contribuicao=valor_total,
                aliquota_efetiva=aliquota_efetiva,
                faixas_aplicadas=faixas_aplicadas,
                teto_aplicado=teto_aplicado,
                categoria=trabalhador.categoria,
            )

        except Exception as e:
            self.logger.error(f"Erro ao calcular INSS: {e}")
            raise CalculoError(f"Erro no calculo INSS: {e}")

    def calcular_contribuicao_patronal(
        self,
        folha_total: Decimal,
        rat: Decimal = Decimal("2.0"),
        fap: Decimal = Decimal("1.0"),
        outras_entidades: Decimal = Decimal("5.8"),
    ) -> dict[str, Decimal]:
        """
        Calcula contribuicao patronal INSS.

        Args:
            folha_total: Total da folha de pagamento
            rat: Risco Ambiental do Trabalho (1%, 2% ou 3%)
            fap: Fator Acidentario de Prevencao (0.5 a 2.0)
            outras_entidades: Terceiros (SESI, SENAI, etc.)

        Returns:
            Dicionario com valores das contribuicoes
        """
        try:
            # Contribuicao patronal basica: 20%
            patronal_basica = (folha_total * Decimal("20") / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            # RAT ajustado pelo FAP
            rat_ajustado = (rat * fap).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            valor_rat = (folha_total * rat_ajustado / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            # Terceiros
            valor_terceiros = (folha_total * outras_entidades / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            total = patronal_basica + valor_rat + valor_terceiros

            return {
                "folha_total": folha_total,
                "patronal_basica": patronal_basica,
                "aliquota_patronal": Decimal("20.0"),
                "rat": rat,
                "fap": fap,
                "rat_ajustado": rat_ajustado,
                "valor_rat": valor_rat,
                "outras_entidades": outras_entidades,
                "valor_terceiros": valor_terceiros,
                "total": total,
            }

        except Exception as e:
            self.logger.error(f"Erro ao calcular patronal: {e}")
            raise CalculoError(f"Erro no calculo patronal: {e}")


# =============================================================================
# GUIA GENERATORS
# =============================================================================


class GeradorGuiaBase(ABC):
    """Base para geradores de guia."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def gerar(self, **kwargs) -> Guia:
        """Gera a guia."""
        pass

    def _gerar_codigo_barras(self, dados: dict) -> str:
        """Gera codigo de barras padrao FEBRABAN."""
        # Simplificado - implementacao real seguiria padrao FEBRABAN
        hash_dados = hashlib.sha256(str(dados).encode()).hexdigest()[:44]
        return hash_dados

    def _gerar_linha_digitavel(self, codigo_barras: str) -> str:
        """Gera linha digitavel a partir do codigo de barras."""
        # Simplificado
        return f"{codigo_barras[:5]}.{codigo_barras[5:10]} {codigo_barras[10:15]}.{codigo_barras[15:21]} {codigo_barras[21:26]}.{codigo_barras[26:32]} {codigo_barras[32]} {codigo_barras[33:]}"

    def _calcular_vencimento(self, competencia: date, tipo: TipoGuia) -> date:
        """Calcula data de vencimento da guia."""
        if tipo in [TipoGuia.GRF, TipoGuia.GRRF]:
            # FGTS vence dia 7 do mes seguinte
            proximo_mes = competencia.replace(day=1) + timedelta(days=32)
            return proximo_mes.replace(day=7)
        elif tipo == TipoGuia.GPS:
            # GPS vence dia 20 do mes seguinte
            proximo_mes = competencia.replace(day=1) + timedelta(days=32)
            return proximo_mes.replace(day=20)
        elif tipo == TipoGuia.DAE:
            # DAE (eSocial domestico) vence dia 7 do mes seguinte
            proximo_mes = competencia.replace(day=1) + timedelta(days=32)
            return proximo_mes.replace(day=7)
        else:
            # DARF vence ultimo dia util do mes seguinte
            proximo_mes = competencia.replace(day=1) + timedelta(days=32)
            ultimo_dia = (proximo_mes.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
            return ultimo_dia


class GeradorGRF(GeradorGuiaBase):
    """Gerador de GRF - Guia de Recolhimento do FGTS."""

    def gerar(
        self, empresa_cnpj: str, empresa_razao_social: str, competencia: date, calculos: list[CalculoFGTS]
    ) -> Guia:
        """
        Gera GRF para recolhimento mensal.

        Args:
            empresa_cnpj: CNPJ da empresa
            empresa_razao_social: Razao social
            competencia: Competencia (mes/ano)
            calculos: Lista de calculos FGTS por trabalhador

        Returns:
            Guia GRF gerada
        """
        try:
            valor_total = sum(c.valor_deposito for c in calculos)
            vencimento = self._calcular_vencimento(competencia, TipoGuia.GRF)

            dados_guia = {
                "tipo": "GRF",
                "cnpj": empresa_cnpj,
                "competencia": competencia.isoformat(),
                "valor": str(valor_total),
                "qtd_trabalhadores": len(calculos),
            }

            codigo_barras = self._gerar_codigo_barras(dados_guia)
            linha_digitavel = self._gerar_linha_digitavel(codigo_barras)

            guia = Guia(
                id=str(uuid.uuid4()),
                tipo=TipoGuia.GRF,
                competencia=competencia,
                vencimento=vencimento,
                valor_principal=valor_total,
                valor_total=valor_total,
                codigo_barras=codigo_barras,
                linha_digitavel=linha_digitavel,
                numero_documento=f"GRF{competencia.strftime('%Y%m')}{empresa_cnpj[:8]}",
                empresa_cnpj=empresa_cnpj,
                empresa_razao_social=empresa_razao_social,
                trabalhadores=[c.trabalhador_id for c in calculos],
                detalhamento={
                    "qtd_trabalhadores": len(calculos),
                    "soma_bases": str(sum(c.base_calculo for c in calculos)),
                    "codigo_recolhimento": CodigoRecolhimento.RECOLHIMENTO_MENSAL.value,
                },
            )

            self.logger.info(
                f"GRF gerada: competencia={competencia}, valor={valor_total}, trabalhadores={len(calculos)}"
            )

            return guia

        except Exception as e:
            self.logger.error(f"Erro ao gerar GRF: {e}")
            raise GuiaError(f"Erro na geracao da GRF: {e}")


class GeradorGRRF(GeradorGuiaBase):
    """Gerador de GRRF - Guia de Recolhimento Rescisorio do FGTS."""

    def gerar(
        self,
        empresa_cnpj: str,
        empresa_razao_social: str,
        calculo: CalculoFGTS,
        trabalhador: Trabalhador,
        data_desligamento: date,
    ) -> Guia:
        """
        Gera GRRF para rescisao.

        Args:
            empresa_cnpj: CNPJ da empresa
            empresa_razao_social: Razao social
            calculo: Calculo FGTS rescisorio
            trabalhador: Dados do trabalhador
            data_desligamento: Data do desligamento

        Returns:
            Guia GRRF gerada
        """
        try:
            valor_total = calculo.valor_total
            vencimento = data_desligamento + timedelta(days=10)  # 10 dias uteis

            dados_guia = {
                "tipo": "GRRF",
                "cnpj": empresa_cnpj,
                "cpf": trabalhador.cpf,
                "valor": str(valor_total),
                "data_desligamento": data_desligamento.isoformat(),
            }

            codigo_barras = self._gerar_codigo_barras(dados_guia)
            linha_digitavel = self._gerar_linha_digitavel(codigo_barras)

            guia = Guia(
                id=str(uuid.uuid4()),
                tipo=TipoGuia.GRRF,
                competencia=data_desligamento.replace(day=1),
                vencimento=vencimento,
                valor_principal=calculo.valor_deposito,
                valor_multa=calculo.valor_multa,
                valor_total=valor_total,
                codigo_barras=codigo_barras,
                linha_digitavel=linha_digitavel,
                numero_documento=f"GRRF{data_desligamento.strftime('%Y%m%d')}{trabalhador.cpf}",
                empresa_cnpj=empresa_cnpj,
                empresa_razao_social=empresa_razao_social,
                trabalhadores=[trabalhador.id],
                detalhamento={
                    "trabalhador_nome": trabalhador.nome,
                    "trabalhador_cpf": trabalhador.cpf,
                    "trabalhador_pis": trabalhador.pis_pasep,
                    "data_desligamento": data_desligamento.isoformat(),
                    "saldo_fgts": str(calculo.saldo_anterior),
                    "deposito_mes": str(calculo.valor_deposito),
                    "multa_40": str(calculo.valor_multa),
                    "codigo_recolhimento": CodigoRecolhimento.RECOLHIMENTO_RESCISORIO.value,
                },
            )

            self.logger.info(f"GRRF gerada: trabalhador={trabalhador.cpf}, valor_total={valor_total}")

            return guia

        except Exception as e:
            self.logger.error(f"Erro ao gerar GRRF: {e}")
            raise GuiaError(f"Erro na geracao da GRRF: {e}")


class GeradorGPS(GeradorGuiaBase):
    """Gerador de GPS - Guia da Previdencia Social."""

    def gerar(
        self,
        empresa_cnpj: str,
        empresa_razao_social: str,
        competencia: date,
        contribuicoes_empregados: list[CalculoINSS],
        contribuicao_patronal: dict[str, Decimal],
    ) -> Guia:
        """
        Gera GPS para recolhimento previdenciario.

        Args:
            empresa_cnpj: CNPJ da empresa
            empresa_razao_social: Razao social
            competencia: Competencia
            contribuicoes_empregados: Contribuicoes dos empregados
            contribuicao_patronal: Contribuicao patronal calculada

        Returns:
            Guia GPS gerada
        """
        try:
            valor_empregados = sum(c.valor_contribuicao for c in contribuicoes_empregados)
            valor_patronal = contribuicao_patronal.get("total", Decimal("0"))
            valor_total = valor_empregados + valor_patronal

            vencimento = self._calcular_vencimento(competencia, TipoGuia.GPS)

            dados_guia = {
                "tipo": "GPS",
                "cnpj": empresa_cnpj,
                "competencia": competencia.isoformat(),
                "valor": str(valor_total),
            }

            codigo_barras = self._gerar_codigo_barras(dados_guia)
            linha_digitavel = self._gerar_linha_digitavel(codigo_barras)

            guia = Guia(
                id=str(uuid.uuid4()),
                tipo=TipoGuia.GPS,
                competencia=competencia,
                vencimento=vencimento,
                valor_principal=valor_total,
                valor_total=valor_total,
                codigo_barras=codigo_barras,
                linha_digitavel=linha_digitavel,
                numero_documento=f"GPS{competencia.strftime('%Y%m')}{empresa_cnpj[:8]}",
                empresa_cnpj=empresa_cnpj,
                empresa_razao_social=empresa_razao_social,
                trabalhadores=[c.trabalhador_id for c in contribuicoes_empregados],
                detalhamento={
                    "qtd_trabalhadores": len(contribuicoes_empregados),
                    "valor_empregados": str(valor_empregados),
                    "valor_patronal_basico": str(contribuicao_patronal.get("patronal_basica", 0)),
                    "valor_rat": str(contribuicao_patronal.get("valor_rat", 0)),
                    "valor_terceiros": str(contribuicao_patronal.get("valor_terceiros", 0)),
                    "valor_patronal_total": str(valor_patronal),
                    "codigo_pagamento": "2100",  # Empresas em geral
                },
            )

            self.logger.info(f"GPS gerada: competencia={competencia}, valor_total={valor_total}")

            return guia

        except Exception as e:
            self.logger.error(f"Erro ao gerar GPS: {e}")
            raise GuiaError(f"Erro na geracao da GPS: {e}")


# =============================================================================
# SERVICE PRINCIPAL
# =============================================================================


class FGTSINSSManager:
    """
    Gerenciador principal de FGTS e INSS.

    Responsavel por:
    - Calculos de FGTS e INSS
    - Geracao de guias de recolhimento
    - Consultas cadastrais
    - Emissao de certidoes
    - Integracao com Conectividade Social e sistemas governamentais
    """

    def __init__(
        self, db_session: Any | None = None, tabela_inss: TabelaINSS | None = None, ambiente: str = "producao"
    ):
        """
        Inicializa o gerenciador.

        Args:
            db_session: Sessao do banco de dados
            tabela_inss: Tabela de contribuicao INSS
            ambiente: Ambiente (producao ou homologacao)
        """
        self.db = db_session
        self.ambiente = ambiente
        self.logger = logging.getLogger(f"{__name__}.FGTSINSSManager")

        # Calculadoras
        self.calc_fgts = CalculadoraFGTS()
        self.calc_inss = CalculadoraINSS(tabela_inss)

        # Geradores de guia
        self.gerador_grf = GeradorGRF()
        self.gerador_grrf = GeradorGRRF()
        self.gerador_gps = GeradorGPS()

        self.logger.info(f"FGTSINSSManager inicializado - ambiente: {ambiente}")

    # -------------------------------------------------------------------------
    # CALCULOS FGTS
    # -------------------------------------------------------------------------

    async def calcular_fgts_mensal(
        self, trabalhadores: list[Trabalhador], remuneracoes: list[Remuneracao]
    ) -> list[CalculoFGTS]:
        """
        Calcula FGTS mensal para lista de trabalhadores.

        Args:
            trabalhadores: Lista de trabalhadores
            remuneracoes: Lista de remuneracoes

        Returns:
            Lista de calculos FGTS
        """
        calculos = []
        rem_por_trabalhador = {r.trabalhador_id: r for r in remuneracoes}

        for trabalhador in trabalhadores:
            rem = rem_por_trabalhador.get(trabalhador.id)
            if rem:
                calculo = self.calc_fgts.calcular_deposito_mensal(trabalhador, rem)
                calculos.append(calculo)

        self.logger.info(f"FGTS mensal calculado para {len(calculos)} trabalhadores")
        return calculos

    async def calcular_fgts_rescisorio(
        self,
        trabalhador: Trabalhador,
        saldo_fgts: Decimal,
        motivo: ModalidadeSaque,
        remuneracao_final: Remuneracao | None = None,
        aviso_previo_indenizado: bool = False,
        valor_aviso: Decimal = Decimal("0"),
    ) -> CalculoFGTS:
        """
        Calcula FGTS rescisorio.

        Args:
            trabalhador: Dados do trabalhador
            saldo_fgts: Saldo atual FGTS
            motivo: Modalidade de saque
            remuneracao_final: Remuneracao do mes
            aviso_previo_indenizado: Se tem aviso indenizado
            valor_aviso: Valor do aviso

        Returns:
            Calculo FGTS rescisorio
        """
        return self.calc_fgts.calcular_rescisao(
            trabalhador=trabalhador,
            saldo_fgts=saldo_fgts,
            motivo=motivo,
            remuneracao_final=remuneracao_final,
            aviso_previo_indenizado=aviso_previo_indenizado,
            valor_aviso=valor_aviso,
        )

    # -------------------------------------------------------------------------
    # CALCULOS INSS
    # -------------------------------------------------------------------------

    async def calcular_inss_mensal(
        self, trabalhadores: list[Trabalhador], remuneracoes: list[Remuneracao]
    ) -> list[CalculoINSS]:
        """
        Calcula INSS mensal para lista de trabalhadores.

        Args:
            trabalhadores: Lista de trabalhadores
            remuneracoes: Lista de remuneracoes

        Returns:
            Lista de calculos INSS
        """
        calculos = []
        rem_por_trabalhador = {r.trabalhador_id: r for r in remuneracoes}

        for trabalhador in trabalhadores:
            rem = rem_por_trabalhador.get(trabalhador.id)
            if rem:
                calculo = self.calc_inss.calcular_contribuicao(trabalhador, rem)
                calculos.append(calculo)

        self.logger.info(f"INSS mensal calculado para {len(calculos)} trabalhadores")
        return calculos

    async def calcular_inss_patronal(
        self, folha_total: Decimal, rat: Decimal = Decimal("2.0"), fap: Decimal = Decimal("1.0")
    ) -> dict[str, Decimal]:
        """
        Calcula contribuicao patronal INSS.

        Args:
            folha_total: Total da folha
            rat: Risco Ambiental do Trabalho
            fap: Fator Acidentario de Prevencao

        Returns:
            Dicionario com valores
        """
        return self.calc_inss.calcular_contribuicao_patronal(folha_total=folha_total, rat=rat, fap=fap)

    # -------------------------------------------------------------------------
    # GERACAO DE GUIAS
    # -------------------------------------------------------------------------

    async def gerar_grf(
        self, empresa_cnpj: str, empresa_razao_social: str, competencia: date, calculos: list[CalculoFGTS]
    ) -> Guia:
        """
        Gera GRF para recolhimento mensal.

        Args:
            empresa_cnpj: CNPJ da empresa
            empresa_razao_social: Razao social
            competencia: Competencia
            calculos: Calculos FGTS

        Returns:
            Guia GRF
        """
        guia = self.gerador_grf.gerar(
            empresa_cnpj=empresa_cnpj,
            empresa_razao_social=empresa_razao_social,
            competencia=competencia,
            calculos=calculos,
        )

        if self.db:
            await self._salvar_guia(guia)

        return guia

    async def gerar_grrf(
        self,
        empresa_cnpj: str,
        empresa_razao_social: str,
        calculo: CalculoFGTS,
        trabalhador: Trabalhador,
        data_desligamento: date,
    ) -> Guia:
        """
        Gera GRRF para rescisao.

        Args:
            empresa_cnpj: CNPJ
            empresa_razao_social: Razao social
            calculo: Calculo FGTS rescisorio
            trabalhador: Trabalhador
            data_desligamento: Data desligamento

        Returns:
            Guia GRRF
        """
        guia = self.gerador_grrf.gerar(
            empresa_cnpj=empresa_cnpj,
            empresa_razao_social=empresa_razao_social,
            calculo=calculo,
            trabalhador=trabalhador,
            data_desligamento=data_desligamento,
        )

        if self.db:
            await self._salvar_guia(guia)

        return guia

    async def gerar_gps(
        self,
        empresa_cnpj: str,
        empresa_razao_social: str,
        competencia: date,
        contribuicoes: list[CalculoINSS],
        folha_total: Decimal,
        rat: Decimal = Decimal("2.0"),
        fap: Decimal = Decimal("1.0"),
    ) -> Guia:
        """
        Gera GPS para recolhimento previdenciario.

        Args:
            empresa_cnpj: CNPJ
            empresa_razao_social: Razao social
            competencia: Competencia
            contribuicoes: Contribuicoes dos empregados
            folha_total: Total da folha
            rat: RAT
            fap: FAP

        Returns:
            Guia GPS
        """
        patronal = await self.calcular_inss_patronal(folha_total, rat, fap)

        guia = self.gerador_gps.gerar(
            empresa_cnpj=empresa_cnpj,
            empresa_razao_social=empresa_razao_social,
            competencia=competencia,
            contribuicoes_empregados=contribuicoes,
            contribuicao_patronal=patronal,
        )

        if self.db:
            await self._salvar_guia(guia)

        return guia

    async def gerar_dae(
        self,
        empregador_cpf: str,
        empregador_nome: str,
        trabalhador: Trabalhador,
        remuneracao: Remuneracao,
        competencia: date,
    ) -> Guia:
        """
        Gera DAE - Documento de Arrecadacao eSocial (domesticos).

        Args:
            empregador_cpf: CPF do empregador
            empregador_nome: Nome do empregador
            trabalhador: Trabalhador domestico
            remuneracao: Remuneracao
            competencia: Competencia

        Returns:
            Guia DAE
        """
        try:
            # Calculos
            fgts = self.calc_fgts.calcular_deposito_mensal(trabalhador, remuneracao)
            inss_empregado = self.calc_inss.calcular_contribuicao(trabalhador, remuneracao)

            # INSS patronal domestico: 8%
            inss_patronal = (remuneracao.base_inss * Decimal("8") / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            # Seguro acidente: 0.8%
            seguro_acidente = (remuneracao.base_inss * Decimal("0.8") / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            # FGTS antecipacao multa rescisoria: 3.2%
            fgts_multa = (remuneracao.base_fgts * Decimal("3.2") / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            valor_total = (
                fgts.valor_deposito + inss_empregado.valor_contribuicao + inss_patronal + seguro_acidente + fgts_multa
            )

            vencimento = competencia.replace(day=1) + timedelta(days=37)
            vencimento = vencimento.replace(day=7)

            dados_guia = {
                "tipo": "DAE",
                "cpf_empregador": empregador_cpf,
                "cpf_trabalhador": trabalhador.cpf,
                "competencia": competencia.isoformat(),
                "valor": str(valor_total),
            }

            codigo_barras = self.gerador_grf._gerar_codigo_barras(dados_guia)
            linha_digitavel = self.gerador_grf._gerar_linha_digitavel(codigo_barras)

            guia = Guia(
                id=str(uuid.uuid4()),
                tipo=TipoGuia.DAE,
                competencia=competencia,
                vencimento=vencimento,
                valor_principal=valor_total,
                valor_total=valor_total,
                codigo_barras=codigo_barras,
                linha_digitavel=linha_digitavel,
                numero_documento=f"DAE{competencia.strftime('%Y%m')}{trabalhador.cpf}",
                empresa_cnpj=empregador_cpf,
                empresa_razao_social=empregador_nome,
                trabalhadores=[trabalhador.id],
                detalhamento={
                    "trabalhador_nome": trabalhador.nome,
                    "trabalhador_cpf": trabalhador.cpf,
                    "fgts_8": str(fgts.valor_deposito),
                    "fgts_multa_3_2": str(fgts_multa),
                    "inss_empregado": str(inss_empregado.valor_contribuicao),
                    "inss_patronal_8": str(inss_patronal),
                    "seguro_acidente_0_8": str(seguro_acidente),
                    "base_calculo": str(remuneracao.total_proventos),
                },
            )

            if self.db:
                await self._salvar_guia(guia)

            self.logger.info(f"DAE gerada: competencia={competencia}, valor={valor_total}")

            return guia

        except Exception as e:
            self.logger.error(f"Erro ao gerar DAE: {e}")
            raise GuiaError(f"Erro na geracao do DAE: {e}")

    # -------------------------------------------------------------------------
    # CONSULTAS E CERTIDOES
    # -------------------------------------------------------------------------

    async def consultar_extrato_fgts(self, pis_pasep: str, empresa_cnpj: str) -> ExtratoFGTS:
        """
        Consulta extrato FGTS via Conectividade Social.

        Args:
            pis_pasep: Numero PIS/PASEP
            empresa_cnpj: CNPJ da empresa

        Returns:
            Extrato FGTS

        Note:
            Em ambiente real, faria chamada ao Conectividade Social
        """
        try:
            self.logger.info(f"Consultando extrato FGTS: PIS={pis_pasep}, CNPJ={empresa_cnpj}")

            # Simulacao - em producao integraria com Conectividade Social
            if self.ambiente == "homologacao":
                return ExtratoFGTS(
                    pis_pasep=pis_pasep,
                    empresa_cnpj=empresa_cnpj,
                    saldo_total=Decimal("15432.67"),
                    movimentacoes=[
                        {"data": "2025-12-07", "tipo": "Deposito", "valor": "450.00", "competencia": "2025-11"},
                        {"data": "2025-11-07", "tipo": "Deposito", "valor": "450.00", "competencia": "2025-10"},
                    ],
                    conta_ativa=True,
                )

            raise ConsultaError("Consulta ao Conectividade Social nao implementada", code="NOT_IMPLEMENTED")

        except FGTSINSSError:
            raise
        except Exception as e:
            self.logger.error(f"Erro ao consultar extrato FGTS: {e}")
            raise ConsultaError(f"Erro na consulta de extrato: {e}")

    async def emitir_crf(self, cnpj: str) -> Certidao:
        """
        Emite CRF - Certificado de Regularidade do FGTS.

        Args:
            cnpj: CNPJ da empresa

        Returns:
            Certidao CRF
        """
        try:
            self.logger.info(f"Emitindo CRF para CNPJ: {cnpj}")

            # NAO fabricar certidao "regular": a consulta real a CAIXA ainda
            # nao esta implementada. Emitir CRF sem consulta produziria uma
            # certidao de regularidade FALSA. Ser honesto.
            raise NotImplementedError(
                "Emissao de CRF (FGTS) via CAIXA nao implementada. "
                "NAO ha base para afirmar regularidade."
            )

        except NotImplementedError:
            raise
        except Exception as e:
            self.logger.error(f"Erro ao emitir CRF: {e}")
            raise ConsultaError(f"Erro na emissao do CRF: {e}")

    async def emitir_cnd_inss(self, cnpj: str) -> Certidao:
        """
        Emite CND - Certidao Negativa de Debitos INSS.

        Args:
            cnpj: CNPJ da empresa

        Returns:
            Certidao CND
        """
        try:
            self.logger.info(f"Emitindo CND INSS para CNPJ: {cnpj}")

            # NAO fabricar certidao "negativa": a consulta real a Receita
            # Federal ainda nao esta implementada. Emitir CND sem consulta
            # produziria uma certidao de regularidade FALSA. Ser honesto.
            raise NotImplementedError(
                "Emissao de CND-INSS via Receita Federal nao implementada. "
                "NAO ha base para afirmar regularidade."
            )

        except NotImplementedError:
            raise
        except Exception as e:
            self.logger.error(f"Erro ao emitir CND INSS: {e}")
            raise ConsultaError(f"Erro na emissao da CND: {e}")

    async def verificar_regularidade(self, cnpj: str) -> dict[str, Any]:
        """
        Verifica regularidade fiscal (FGTS + INSS).

        Args:
            cnpj: CNPJ da empresa

        Returns:
            Status de regularidade
        """
        try:
            crf = await self.emitir_crf(cnpj)
            cnd = await self.emitir_cnd_inss(cnpj)

            regular_fgts = crf.status in [StatusCertidao.NEGATIVA, StatusCertidao.POSITIVA_EFEITO_NEGATIVA]
            regular_inss = cnd.status in [StatusCertidao.NEGATIVA, StatusCertidao.POSITIVA_EFEITO_NEGATIVA]

            return {
                "cnpj": cnpj,
                "regular": regular_fgts and regular_inss,
                "fgts": {
                    "status": crf.status.value,
                    "validade": crf.data_validade.isoformat(),
                    "codigo_controle": crf.codigo_controle,
                },
                "inss": {
                    "status": cnd.status.value,
                    "validade": cnd.data_validade.isoformat(),
                    "codigo_controle": cnd.codigo_controle,
                },
                "data_consulta": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Erro ao verificar regularidade: {e}")
            raise ConsultaError(f"Erro na verificacao de regularidade: {e}")

    # -------------------------------------------------------------------------
    # PROCESSAMENTO EM LOTE
    # -------------------------------------------------------------------------

    async def processar_folha_mensal(
        self,
        empresa_cnpj: str,
        empresa_razao_social: str,
        competencia: date,
        trabalhadores: list[Trabalhador],
        remuneracoes: list[Remuneracao],
        rat: Decimal = Decimal("2.0"),
        fap: Decimal = Decimal("1.0"),
    ) -> dict[str, Any]:
        """
        Processa folha mensal completa (FGTS + INSS).

        Args:
            empresa_cnpj: CNPJ
            empresa_razao_social: Razao social
            competencia: Competencia
            trabalhadores: Lista de trabalhadores
            remuneracoes: Lista de remuneracoes
            rat: RAT
            fap: FAP

        Returns:
            Resultado do processamento com guias geradas
        """
        try:
            self.logger.info(
                f"Processando folha mensal: CNPJ={empresa_cnpj}, "
                f"competencia={competencia}, trabalhadores={len(trabalhadores)}"
            )

            # Calculos FGTS
            calculos_fgts = await self.calcular_fgts_mensal(trabalhadores, remuneracoes)

            # Calculos INSS
            calculos_inss = await self.calcular_inss_mensal(trabalhadores, remuneracoes)

            # Total da folha para patronal
            folha_total = sum(r.total_proventos for r in remuneracoes)

            # Gerar guias
            grf = await self.gerar_grf(
                empresa_cnpj=empresa_cnpj,
                empresa_razao_social=empresa_razao_social,
                competencia=competencia,
                calculos=calculos_fgts,
            )

            gps = await self.gerar_gps(
                empresa_cnpj=empresa_cnpj,
                empresa_razao_social=empresa_razao_social,
                competencia=competencia,
                contribuicoes=calculos_inss,
                folha_total=folha_total,
                rat=rat,
                fap=fap,
            )

            resultado = {
                "empresa_cnpj": empresa_cnpj,
                "competencia": competencia.isoformat(),
                "qtd_trabalhadores": len(trabalhadores),
                "folha_total": str(folha_total),
                "fgts": {
                    "total_depositos": str(sum(c.valor_deposito for c in calculos_fgts)),
                    "guia": {
                        "id": grf.id,
                        "numero": grf.numero_documento,
                        "valor": str(grf.valor_total),
                        "vencimento": grf.vencimento.isoformat(),
                        "codigo_barras": grf.codigo_barras,
                    },
                },
                "inss": {
                    "total_empregados": str(sum(c.valor_contribuicao for c in calculos_inss)),
                    "guia": {
                        "id": gps.id,
                        "numero": gps.numero_documento,
                        "valor": str(gps.valor_total),
                        "vencimento": gps.vencimento.isoformat(),
                        "codigo_barras": gps.codigo_barras,
                    },
                },
                "processado_em": datetime.now().isoformat(),
            }

            self.logger.info(f"Folha processada: FGTS={grf.valor_total}, GPS={gps.valor_total}")

            return resultado

        except Exception as e:
            self.logger.error(f"Erro ao processar folha: {e}")
            raise FGTSINSSError(f"Erro no processamento da folha: {e}")

    # -------------------------------------------------------------------------
    # HELPERS PRIVADOS
    # -------------------------------------------------------------------------

    async def _salvar_guia(self, guia: Guia) -> None:
        """Salva guia no banco de dados."""
        if not self.db:
            return

        try:
            model = GuiaRecolhimentoModel(
                id=uuid.UUID(guia.id),
                tipo=guia.tipo,
                competencia=guia.competencia,
                vencimento=guia.vencimento,
                valor_principal=guia.valor_principal,
                valor_juros=guia.valor_juros,
                valor_multa=guia.valor_multa,
                valor_total=guia.valor_total,
                codigo_barras=guia.codigo_barras,
                linha_digitavel=guia.linha_digitavel,
                numero_documento=guia.numero_documento,
                empresa_cnpj=guia.empresa_cnpj,
                empresa_razao_social=guia.empresa_razao_social,
                status=guia.status,
                trabalhadores=guia.trabalhadores,
                detalhamento=guia.detalhamento,
            )
            self.db.add(model)
            await self.db.commit()
        except Exception as e:
            self.logger.error(f"Erro ao salvar guia: {e}")
            await self.db.rollback()

    async def _salvar_certidao(self, certidao: Certidao) -> None:
        """Salva certidao no banco de dados."""
        if not self.db:
            return

        try:
            model = CertidaoModel(
                id=uuid.UUID(certidao.id),
                tipo=certidao.tipo,
                status=certidao.status,
                documento=certidao.documento,
                razao_social=certidao.razao_social,
                data_emissao=certidao.data_emissao,
                data_validade=certidao.data_validade,
                codigo_controle=certidao.codigo_controle,
                observacoes=certidao.observacoes,
                pendencias=certidao.pendencias,
            )
            self.db.add(model)
            await self.db.commit()
        except Exception as e:
            self.logger.error(f"Erro ao salvar certidao: {e}")
            await self.db.rollback()


# =============================================================================
# SINGLETON E FUNCOES AUXILIARES
# =============================================================================

_fgts_inss_manager: FGTSINSSManager | None = None


def get_fgts_inss_manager() -> FGTSINSSManager:
    """Retorna instancia singleton do FGTSINSSManager."""
    global _fgts_inss_manager
    if _fgts_inss_manager is None:
        raise RuntimeError("FGTSINSSManager nao inicializado. Chame init_fgts_inss_manager primeiro.")
    return _fgts_inss_manager


def init_fgts_inss_manager(
    db_session: Any | None = None, tabela_inss: TabelaINSS | None = None, ambiente: str = "producao"
) -> FGTSINSSManager:
    """
    Inicializa o singleton FGTSINSSManager.

    Args:
        db_session: Sessao do banco de dados
        tabela_inss: Tabela INSS (usa 2025 se nao informada)
        ambiente: Ambiente de execucao

    Returns:
        Instancia do FGTSINSSManager
    """
    global _fgts_inss_manager
    _fgts_inss_manager = FGTSINSSManager(db_session=db_session, tabela_inss=tabela_inss, ambiente=ambiente)
    return _fgts_inss_manager


def validar_pis_pasep(pis: str) -> bool:
    """
    Valida numero PIS/PASEP.

    Args:
        pis: Numero PIS/PASEP (11 digitos)

    Returns:
        True se valido
    """
    pis = re.sub(r"\D", "", pis)

    if len(pis) != 11:
        return False

    if pis == pis[0] * 11:
        return False

    # Calculo do digito verificador
    pesos = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma = sum(int(pis[i]) * pesos[i] for i in range(10))
    resto = soma % 11
    digito = 11 - resto if resto >= 2 else 0

    return digito == int(pis[10])


def formatar_pis_pasep(pis: str) -> str:
    """
    Formata PIS/PASEP: XXX.XXXXX.XX-X

    Args:
        pis: Numero PIS (apenas digitos)

    Returns:
        PIS formatado
    """
    pis = re.sub(r"\D", "", pis)
    if len(pis) == 11:
        return f"{pis[:3]}.{pis[3:8]}.{pis[8:10]}-{pis[10]}"
    return pis


def calcular_aliquota_efetiva_inss(base: Decimal, tabela: TabelaINSS | None = None) -> Decimal:
    """
    Calcula aliquota efetiva INSS para uma base.

    Args:
        base: Base de calculo
        tabela: Tabela INSS (usa 2025 se nao informada)

    Returns:
        Aliquota efetiva em percentual
    """
    if tabela is None:
        tabela = TabelaINSS.tabela_2025()

    base = min(base, tabela.teto)
    valor_total = Decimal("0")
    valor_anterior = Decimal("0")

    for faixa in tabela.faixas:
        limite = faixa["ate"]
        aliquota = faixa["aliquota"]

        if base <= valor_anterior:
            break

        base_faixa = min(base, limite) - valor_anterior
        if base_faixa > 0:
            valor_total += base_faixa * aliquota / Decimal("100")

        valor_anterior = limite

    if base > 0:
        return (valor_total / base * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return Decimal("0")
