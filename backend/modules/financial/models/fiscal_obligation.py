"""Modelo de Obrigacoes Fiscais e Configuracao ZFM/SUFRAMA."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from core.models.base import Base


class ObrigacaoTipo(StrEnum):
    """Tipo de obrigacao fiscal."""

    # Federais
    DCTF = "dctf"  # Declaracao de Debitos e Creditos Tributarios Federais
    DCTFWEB = "dctfweb"  # DCTF Web (previdenciario)
    DIRF = "dirf"  # Declaracao do Imposto Retido na Fonte
    PERDCOMP = "perdcomp"  # Pedido de Restituicao/Compensacao
    ECF = "ecf"  # Escrituracao Contabil Fiscal
    ECD = "ecd"  # Escrituracao Contabil Digital
    EFD_CONTRIBUICOES = "efd_contribuicoes"  # EFD PIS/COFINS
    EFD_REINF = "efd_reinf"  # EFD Reinf
    ESOCIAL = "esocial"  # eSocial
    DAS = "das"  # Documento de Arrecadacao do Simples Nacional
    DEFIS = "defis"  # Declaracao de Informacoes Socioeconômicas e Fiscais
    DASN = "dasn"  # Declaracao Anual do Simples Nacional

    # Estaduais
    EFD_ICMS_IPI = "efd_icms_ipi"  # EFD ICMS/IPI (SPED Fiscal)
    GIA = "gia"  # Guia de Informacao e Apuracao do ICMS
    SINTEGRA = "sintegra"  # Sistema Integrado de Informacoes sobre Operacoes Interestaduais
    DESTDA = "destda"  # Declaracao de Substituicao Tributaria (Simples)
    DECLAN = "declan"  # Declaracao Anual do IPM (Amazonas)

    # Municipais
    DES = "des"  # Declaracao Eletronica de Servicos
    GISSM = "gissm"  # Guia de Recolhimento ISS Manaus
    NFSE_MENSAL = "nfse_mensal"  # Relatorio mensal de NFS-e

    # Zona Franca
    SUFRAMA_RELATORIO = "suframa_relatorio"  # Relatorio de vendas para ZFM
    SUFRAMA_PIN = "suframa_pin"  # Protocolo de Ingresso de Mercadorias


class ObrigacaoStatus(StrEnum):
    """Status da obrigacao."""

    PENDENTE = "pendente"
    EM_ELABORACAO = "em_elaboracao"
    AGUARDANDO_DADOS = "aguardando_dados"
    PRONTA = "pronta"
    ENVIADA = "enviada"
    ACEITA = "aceita"
    REJEITADA = "rejeitada"
    RETIFICADA = "retificada"
    ATRASADA = "atrasada"
    ISENTA = "isenta"
    NAO_APLICAVEL = "nao_aplicavel"


class ObrigacaoFrequencia(StrEnum):
    """Frequencia da obrigacao."""

    MENSAL = "mensal"
    BIMESTRAL = "bimestral"
    TRIMESTRAL = "trimestral"
    QUADRIMESTRAL = "quadrimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"
    EVENTUAL = "eventual"


class ZonaFrancaTipo(StrEnum):
    """Tipo de beneficio Zona Franca."""

    ZFM = "zfm"  # Zona Franca de Manaus
    ALC = "alc"  # Area de Livre Comercio
    SUFRAMA_OUTRAS = "suframa_outras"  # Outras areas incentivadas


class SUFRAMAStatus(StrEnum):
    """Status do cadastro SUFRAMA."""

    ATIVO = "ativo"
    SUSPENSO = "suspenso"
    CANCELADO = "cancelado"
    EM_ANALISE = "em_analise"


class FiscalObligation(Base):
    """Obrigacao fiscal a ser cumprida."""

    __tablename__ = "fiscal_obligations"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    condominio_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)

    # Identificacao
    tipo = Column(String(30), nullable=False, index=True)
    nome = Column(String(100), nullable=False)
    descricao = Column(Text, nullable=True)

    # Periodo de referencia (competencia) — colunas reais do banco
    competencia_mes = Column(Integer, nullable=True)  # Null para obrigacoes anuais
    competencia_ano = Column(Integer, nullable=False)

    # Status e prazos
    status = Column(String(20), nullable=False, default=ObrigacaoStatus.PENDENTE.value, index=True)
    data_vencimento = Column(Date, nullable=False)

    # Valores
    valor_devido = Column(Numeric(15, 2), nullable=True)
    valor_pago = Column(Numeric(15, 2), nullable=True)
    data_pagamento = Column(Date, nullable=True)
    numero_recibo = Column(String(50), nullable=True)

    # Observacoes
    observacoes = Column(Text, nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = Column(Boolean, default=True, nullable=False)

    # Status considerados "cumpridos" (nao geram atraso)
    _STATUS_CUMPRIDOS = (
        ObrigacaoStatus.ENVIADA.value,
        ObrigacaoStatus.ACEITA.value,
        ObrigacaoStatus.ISENTA.value,
        ObrigacaoStatus.NAO_APLICAVEL.value,
        ObrigacaoStatus.RETIFICADA.value,
    )

    def __repr__(self) -> str:
        """Representacao string."""
        if self.competencia_mes:
            periodo = f"{self.competencia_ano:04d}-{self.competencia_mes:02d}"
        else:
            periodo = str(self.competencia_ano)
        return f"<FiscalObligation {self.tipo} {periodo} - {self.status}>"

    @property
    def is_entregue(self) -> bool:
        """Verifica se foi entregue/cumprida."""
        return self.status in self._STATUS_CUMPRIDOS

    @property
    def is_vencida(self) -> bool:
        """Verifica se obrigacao esta vencida."""
        if self.is_entregue:
            return False
        return date.today() > self.data_vencimento

    @property
    def is_atrasada(self) -> bool:
        """Verifica se obrigacao esta atrasada (vencida e nao cumprida)."""
        return self.is_vencida

    @property
    def dias_para_vencimento(self) -> int:
        """Dias restantes ate o vencimento (negativo se ja vencida)."""
        if not self.data_vencimento:
            return 0
        return (self.data_vencimento - date.today()).days


class SUFRAMAConfig(Base):
    """Configuracao SUFRAMA para Zona Franca de Manaus."""

    __tablename__ = "suframa_configs"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    condominio_id = Column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True)

    # Dados SUFRAMA
    inscricao_suframa = Column(String(20), nullable=False, unique=True)
    tipo_zona = Column(String(20), nullable=False, default=ZonaFrancaTipo.ZFM.value)
    status = Column(String(20), nullable=False, default=SUFRAMAStatus.ATIVO.value)
    data_inscricao = Column(Date, nullable=True)
    data_validade = Column(Date, nullable=True)

    # Empresa
    cnpj = Column(String(14), nullable=False)
    razao_social = Column(String(150), nullable=False)
    nome_fantasia = Column(String(60), nullable=True)

    # Localizacao
    endereco = Column(JSONB, nullable=True)
    codigo_municipio = Column(String(7), nullable=True)  # IBGE
    municipio_nome = Column(String(100), nullable=True)
    uf = Column(String(2), nullable=False, default="AM")

    # Atividades CNAE habilitadas (JSONB array)
    cnaes_habilitados = Column(JSONB, nullable=True, default=list)

    # Beneficios fiscais ativos
    beneficio_ipi = Column(Boolean, default=True)  # Isencao IPI
    beneficio_icms = Column(Boolean, default=True)  # Reducao/Isencao ICMS
    beneficio_pis_cofins = Column(Boolean, default=True)  # Suspensao PIS/COFINS
    beneficio_ii = Column(Boolean, default=False)  # Reducao II

    # Percentuais de reducao (quando aplicavel)
    reducao_icms_interno = Column(Numeric(8, 4), nullable=True)  # % reducao ICMS interno
    reducao_icms_interestadual = Column(Numeric(8, 4), nullable=True)  # % reducao interestadual
    credito_presumido_icms = Column(Numeric(8, 4), nullable=True)  # % credito presumido

    # Simples Nacional
    simples_nacional = Column(Boolean, default=True)
    simples_anexo = Column(String(5), nullable=True)  # I, II, III, IV, V
    simples_faixa = Column(String(5), nullable=True)  # 1, 2, 3, 4, 5, 6

    # Documentos (JSONB)
    # {"alvara": "url", "certidao_negativa": "url", ...}
    documentos = Column(JSONB, nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(PGUUID(as_uuid=True), nullable=True)
    active = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<SUFRAMAConfig {self.inscricao_suframa} - {self.status}>"

    @property
    def is_ativo(self) -> bool:
        """Verifica se cadastro SUFRAMA esta ativo."""
        if self.status != SUFRAMAStatus.ATIVO.value:
            return False
        if self.data_validade and self.data_validade < date.today():
            return False
        return self.active

    def get_beneficios_aplicaveis(self, cfop: str, _ncm: str) -> dict:
        """Retorna beneficios aplicaveis baseado em CFOP e NCM."""
        beneficios = {
            "ipi_isento": False,
            "icms_reducao": Decimal("0"),
            "icms_isento": False,
            "pis_suspenso": False,
            "cofins_suspenso": False,
            "credito_presumido": Decimal("0"),
        }

        if not self.is_ativo:
            return beneficios

        # Verificar CFOP de entrada na ZFM (1.xxx, 2.xxx para compras)
        # ou saida para ZFM (5.109, 5.110, 6.109, 6.110, etc.)
        cfops_zfm = ["5109", "5110", "6109", "6110", "1501", "2501"]
        is_operacao_zfm = cfop in cfops_zfm or cfop.startswith(("5", "6"))

        if is_operacao_zfm:
            if self.beneficio_ipi:
                beneficios["ipi_isento"] = True

            if self.beneficio_icms:
                if self.reducao_icms_interno:
                    beneficios["icms_reducao"] = self.reducao_icms_interno
                else:
                    beneficios["icms_isento"] = True  # Isencao total

            if self.beneficio_pis_cofins:
                beneficios["pis_suspenso"] = True
                beneficios["cofins_suspenso"] = True

            if self.credito_presumido_icms:
                beneficios["credito_presumido"] = self.credito_presumido_icms

        return beneficios


class SUFRAMAOperacao(Base):
    """Registro de operacao com beneficio SUFRAMA."""

    __tablename__ = "suframa_operacoes"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    condominio_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    suframa_config_id = Column(PGUUID(as_uuid=True), ForeignKey("suframa_configs.id"), nullable=True)
    nfe_id = Column(PGUUID(as_uuid=True), nullable=True)

    # Documento fiscal
    documento_tipo = Column(String(10), nullable=True)  # nfe, nfse
    documento_id = Column(PGUUID(as_uuid=True), nullable=True)
    chave_acesso = Column(String(44), nullable=True)
    numero_documento = Column(String(20), nullable=True)

    # Participante (destinatario/remetente)
    participante_cnpj = Column(String(14), nullable=False)
    participante_suframa = Column(String(20), nullable=True)
    participante_razao_social = Column(String(150), nullable=True)

    # Operacao
    data_operacao = Column(Date, nullable=False)
    cfop = Column(String(4), nullable=False)
    valor_operacao = Column(Numeric(15, 2), nullable=False)
    valor_produtos = Column(Numeric(15, 2), nullable=False)

    # Beneficios aplicados
    ipi_isento = Column(Boolean, default=False)
    ipi_economia = Column(Numeric(15, 2), nullable=True)  # Valor economizado

    icms_isento = Column(Boolean, default=False)
    icms_reducao_percentual = Column(Numeric(8, 4), nullable=True)
    icms_economia = Column(Numeric(15, 2), nullable=True)

    pis_suspenso = Column(Boolean, default=False)
    pis_economia = Column(Numeric(15, 2), nullable=True)

    cofins_suspenso = Column(Boolean, default=False)
    cofins_economia = Column(Numeric(15, 2), nullable=True)

    total_economia = Column(Numeric(15, 2), nullable=True)  # Total de impostos economizados

    # Valores desonerados/suspensos (colunas reais usadas por repo/respostas)
    valor_ipi_desonerado = Column(Numeric(15, 2), nullable=True)
    valor_icms_desonerado = Column(Numeric(15, 2), nullable=True)
    valor_pis_suspenso = Column(Numeric(15, 2), nullable=True)
    valor_cofins_suspenso = Column(Numeric(15, 2), nullable=True)

    # PIN (Protocolo de Ingresso de Mercadorias) — colunas reais
    numero_pin = Column(String(20), nullable=True)
    data_pin = Column(Date, nullable=True)
    status_pin = Column(String(20), nullable=True)
    # Aliases historicos (mantidos para compatibilidade)
    pin_numero = Column(String(50), nullable=True)
    pin_data = Column(Date, nullable=True)
    pin_status = Column(String(20), nullable=True)  # pendente, validado, rejeitado

    # Internamento (para operacoes de entrada)
    internamento_data = Column(Date, nullable=True)
    internamento_protocolo = Column(String(50), nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<SUFRAMAOperacao {self.numero_documento} - R$ {self.total_economia or 0}>"

    def calcular_economia(
        self,
        aliquota_ipi: Decimal = Decimal("0"),
        aliquota_icms: Decimal = Decimal("0"),
        aliquota_pis: Decimal = Decimal("1.65"),
        aliquota_cofins: Decimal = Decimal("7.6"),
    ) -> None:
        """Calcula economia tributaria da operacao."""
        base = self.valor_produtos

        if self.ipi_isento and aliquota_ipi > 0:
            self.ipi_economia = base * aliquota_ipi / 100

        if self.icms_isento and aliquota_icms > 0:
            self.icms_economia = base * aliquota_icms / 100
        elif self.icms_reducao_percentual and aliquota_icms > 0:
            icms_normal = base * aliquota_icms / 100
            icms_reduzido = base * (aliquota_icms * (1 - self.icms_reducao_percentual / 100)) / 100
            self.icms_economia = icms_normal - icms_reduzido

        if self.pis_suspenso:
            self.pis_economia = base * aliquota_pis / 100

        if self.cofins_suspenso:
            self.cofins_economia = base * aliquota_cofins / 100

        self.total_economia = (
            (self.ipi_economia or Decimal("0"))
            + (self.icms_economia or Decimal("0"))
            + (self.pis_economia or Decimal("0"))
            + (self.cofins_economia or Decimal("0"))
        )


class SimplesNacionalDAS(Base):
    """Registro de DAS do Simples Nacional."""

    __tablename__ = "simples_nacional_das"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    condominio_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)

    # Periodo
    competencia = Column(String(7), nullable=False, index=True)  # YYYY-MM
    ano = Column(Integer, nullable=False)
    mes = Column(Integer, nullable=False)

    # Anexo e Faixa
    anexo = Column(String(5), nullable=False)  # I, II, III, IV, V, VI
    faixa = Column(String(5), nullable=False)  # 1, 2, 3, 4, 5, 6

    # Faturamento
    receita_bruta_mes = Column(Numeric(15, 2), nullable=False)
    receita_bruta_12_meses = Column(Numeric(15, 2), nullable=False)
    fator_r = Column(Numeric(8, 4), nullable=True)  # Para Anexo V
    folha_pagamento_12_meses = Column(Numeric(15, 2), nullable=True)

    # Aliquotas
    aliquota_nominal = Column(Numeric(8, 4), nullable=False)
    parcela_deduzir = Column(Numeric(15, 2), nullable=False, default=Decimal("0"))
    aliquota_efetiva = Column(Numeric(8, 4), nullable=False)

    # Valor do DAS
    valor_das = Column(Numeric(15, 2), nullable=False)

    # Reparticao dos tributos (JSONB)
    # Para Anexo IV (Servicos): {"iss": X%, "cpp": 0%} - ISS nao incluso, CPP incluso
    reparticao = Column(JSONB, nullable=True)
    valor_irpj = Column(Numeric(15, 2), nullable=True)
    valor_csll = Column(Numeric(15, 2), nullable=True)
    valor_cofins = Column(Numeric(15, 2), nullable=True)
    valor_pis = Column(Numeric(15, 2), nullable=True)
    valor_cpp = Column(Numeric(15, 2), nullable=True)
    valor_icms = Column(Numeric(15, 2), nullable=True)
    valor_iss = Column(Numeric(15, 2), nullable=True)

    # Status
    status = Column(String(20), nullable=False, default="pendente")  # pendente, gerado, pago, vencido
    data_vencimento = Column(Date, nullable=False)
    data_pagamento = Column(Date, nullable=True)

    # Guia
    codigo_barras = Column(String(50), nullable=True)
    numero_das = Column(String(30), nullable=True)

    # ISS Retido (Anexo IV - nao inclui ISS no DAS)
    iss_retido = Column(Boolean, default=False)
    valor_iss_retido = Column(Numeric(15, 2), nullable=True)

    # Competencia (colunas reais usadas por repositorios/respostas)
    competencia_mes = Column(Integer, nullable=True)
    competencia_ano = Column(Integer, nullable=True)

    # Valores (colunas reais)
    valor_devido = Column(Numeric(15, 2), nullable=True)
    valor_pago = Column(Numeric(15, 2), nullable=True)
    numero_documento = Column(String(50), nullable=True)
    numero_recibo = Column(String(50), nullable=True)

    # Reparticao de tributos (colunas reais)
    reparticao_irpj = Column(Numeric(15, 2), nullable=True)
    reparticao_csll = Column(Numeric(15, 2), nullable=True)
    reparticao_cofins = Column(Numeric(15, 2), nullable=True)
    reparticao_pis = Column(Numeric(15, 2), nullable=True)
    reparticao_cpp = Column(Numeric(15, 2), nullable=True)
    reparticao_iss = Column(Numeric(15, 2), nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    active = Column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        """Representacao string."""
        return f"<SimplesNacionalDAS {self.competencia} - R$ {self.valor_das}>"

    @property
    def is_anexo_iv(self) -> bool:
        """Verifica se e Anexo IV (servicos de construcao)."""
        return self.anexo == "IV"

    @property
    def is_vencido(self) -> bool:
        """Verifica se DAS esta vencido."""
        if self.status == "pago":
            return False
        return date.today() > self.data_vencimento

    @property
    def is_anexo_iii(self) -> bool:
        """Verifica se e Anexo III (vigilancia, seguranca, limpeza)."""
        return self.anexo == "III"

    def calcular_reparticao_anexo_iii(self) -> None:
        """Calcula reparticao para Anexo III (vigilancia e seguranca).

        Anexo III - Servicos de vigilancia, limpeza ou conservacao

        Faixa 3 (RBT12 de 360k a 720k):
        - Aliquota nominal: 11,20%
        - Parcela a deduzir: R$ 9.360,00

        Percentuais de reparticao Faixa 3:
        - IRPJ: 4,00%
        - CSLL: 3,50%
        - COFINS: 12,82%
        - PIS: 2,78%
        - CPP: 43,40% (INSS patronal - INCLUSO no DAS)
        - ISS: 33,50% (INCLUSO no DAS)

        Nota: Diferente do Anexo IV, no Anexo III o ISS JA ESTA INCLUSO
        no DAS, nao precisa recolher separadamente para a prefeitura.

        IMPORTANTE para ZFM: Empresas de vigilancia na Zona Franca de Manaus
        podem ter beneficios adicionais de ISS municipal.
        """
        if not self.is_anexo_iii:
            return

        # Faixa 3 - Anexo III (RBT12 de 360k a 720k)
        # Aliquota nominal: 11,20%
        # Parcela a deduzir: R$ 9.360,00
        reparticao_faixa_3 = {
            "irpj": Decimal("4.00"),
            "csll": Decimal("3.50"),
            "cofins": Decimal("12.82"),
            "pis": Decimal("2.78"),
            "cpp": Decimal("43.40"),  # INSS patronal incluso
            "iss": Decimal("33.50"),  # ISS INCLUSO no DAS
        }

        self.reparticao = {k: float(v) for k, v in reparticao_faixa_3.items()}

        # Calcular valores por tributo (sobre o valor do DAS)
        valor_base = self.valor_das
        self.valor_irpj = valor_base * reparticao_faixa_3["irpj"] / 100
        self.valor_csll = valor_base * reparticao_faixa_3["csll"] / 100
        self.valor_cofins = valor_base * reparticao_faixa_3["cofins"] / 100
        self.valor_pis = valor_base * reparticao_faixa_3["pis"] / 100
        self.valor_cpp = valor_base * reparticao_faixa_3["cpp"] / 100
        self.valor_iss = valor_base * reparticao_faixa_3["iss"] / 100

        # No Anexo III, ISS esta incluso no DAS, nao e retido separadamente
        self.iss_retido = False
        self.valor_iss_retido = Decimal("0")

    def calcular_reparticao_anexo_iv(self) -> None:
        """Calcula reparticao para Anexo IV (construcao civil).

        Anexo IV - Percentuais de reparticao (Faixa 3):
        - IRPJ: 4,00%
        - CSLL: 3,50%
        - COFINS: 11,82%
        - PIS: 2,58%
        - CPP: 43,40% (INSS patronal)
        - ISS: 34,70% (NAO INCLUSO - recolhido a parte)

        Nota: ISS nao esta incluido no DAS do Anexo IV.
        O ISS deve ser recolhido separadamente para a prefeitura.
        """
        if not self.is_anexo_iv:
            return

        # Faixa 3 - Anexo IV (RBT12 de 360k a 720k)
        # Aliquota nominal: 11,20%
        # Parcela a deduzir: R$ 17.640,00
        reparticao_faixa_3 = {
            "irpj": Decimal("4.00"),
            "csll": Decimal("3.50"),
            "cofins": Decimal("11.82"),
            "pis": Decimal("2.58"),
            "cpp": Decimal("43.40"),
            "iss": Decimal("34.70"),  # Nao incluso no DAS
        }

        self.reparticao = {k: float(v) for k, v in reparticao_faixa_3.items()}

        # Calcular valores por tributo
        valor_base = self.valor_das
        self.valor_irpj = valor_base * reparticao_faixa_3["irpj"] / 100
        self.valor_csll = valor_base * reparticao_faixa_3["csll"] / 100
        self.valor_cofins = valor_base * reparticao_faixa_3["cofins"] / 100
        self.valor_pis = valor_base * reparticao_faixa_3["pis"] / 100
        self.valor_cpp = valor_base * reparticao_faixa_3["cpp"] / 100

        # ISS e calculado sobre a receita bruta, nao sobre o DAS
        # Aliquota ISS varia de 2% a 5% dependendo do municipio
        # Manaus usa 5% para servicos de construcao
        self.valor_iss = self.receita_bruta_mes * Decimal("5") / 100
        self.iss_retido = True
        self.valor_iss_retido = self.valor_iss

    def calcular_reparticao(self) -> None:
        """Calcula reparticao de tributos baseado no anexo."""
        if self.is_anexo_iii:
            self.calcular_reparticao_anexo_iii()
        elif self.is_anexo_iv:
            self.calcular_reparticao_anexo_iv()


# Tabela de aliquotas Simples Nacional - Anexo III (Vigilancia e Seguranca)
SIMPLES_ANEXO_III_FAIXAS = [
    {
        "faixa": "1",
        "rbt12_min": Decimal("0"),
        "rbt12_max": Decimal("180000"),
        "aliquota": Decimal("6.00"),
        "deducao": Decimal("0"),
    },
    {
        "faixa": "2",
        "rbt12_min": Decimal("180000.01"),
        "rbt12_max": Decimal("360000"),
        "aliquota": Decimal("11.20"),
        "deducao": Decimal("9360"),
    },
    {
        "faixa": "3",
        "rbt12_min": Decimal("360000.01"),
        "rbt12_max": Decimal("720000"),
        "aliquota": Decimal("13.50"),
        "deducao": Decimal("17640"),
    },
    {
        "faixa": "4",
        "rbt12_min": Decimal("720000.01"),
        "rbt12_max": Decimal("1800000"),
        "aliquota": Decimal("16.00"),
        "deducao": Decimal("35640"),
    },
    {
        "faixa": "5",
        "rbt12_min": Decimal("1800000.01"),
        "rbt12_max": Decimal("3600000"),
        "aliquota": Decimal("21.00"),
        "deducao": Decimal("125640"),
    },
    {
        "faixa": "6",
        "rbt12_min": Decimal("3600000.01"),
        "rbt12_max": Decimal("4800000"),
        "aliquota": Decimal("33.00"),
        "deducao": Decimal("648000"),
    },
]


def calcular_das_anexo_iii(receita_bruta_mes: Decimal, rbt12: Decimal) -> dict:
    """Calcula DAS do Simples Nacional Anexo III.

    Anexo III - Servicos de vigilancia, limpeza e conservacao.

    Args:
        receita_bruta_mes: Receita bruta do mes de apuracao
        rbt12: Receita bruta acumulada dos ultimos 12 meses

    Returns:
        Dict com valores calculados do DAS
    """
    # Encontrar faixa
    faixa_info = None
    for faixa in SIMPLES_ANEXO_III_FAIXAS:
        if faixa["rbt12_min"] <= rbt12 <= faixa["rbt12_max"]:
            faixa_info = faixa
            break

    if not faixa_info:
        # Acima do limite do Simples
        return {"erro": "RBT12 acima do limite do Simples Nacional"}

    # Calcular aliquota efetiva
    # Formula: (RBT12 x Aliquota - Parcela a Deduzir) / RBT12
    if rbt12 > 0:
        aliquota_efetiva = ((rbt12 * faixa_info["aliquota"] / 100) - faixa_info["deducao"]) / rbt12 * 100
    else:
        aliquota_efetiva = faixa_info["aliquota"]

    # Valor do DAS
    valor_das = receita_bruta_mes * aliquota_efetiva / 100

    # Reparticao para Faixa 3 (pode ser ajustado por faixa)
    reparticao = {
        "irpj": Decimal("4.00"),
        "csll": Decimal("3.50"),
        "cofins": Decimal("12.82"),
        "pis": Decimal("2.78"),
        "cpp": Decimal("43.40"),
        "iss": Decimal("33.50"),
    }

    return {
        "anexo": "III",
        "faixa": faixa_info["faixa"],
        "rbt12": rbt12,
        "receita_bruta_mes": receita_bruta_mes,
        "aliquota_nominal": faixa_info["aliquota"],
        "parcela_deduzir": faixa_info["deducao"],
        "aliquota_efetiva": aliquota_efetiva,
        "valor_das": valor_das,
        "reparticao": {k: float(v) for k, v in reparticao.items()},
        "iss_incluso": True,  # Diferenca importante do Anexo IV
        "cpp_incluso": True,  # INSS patronal incluso
    }
