"""
Model SQLAlchemy para tabela employees (funcionarios principais).
Sprint 21: Sync com banco de dados - campos criticos adicionados.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from core.database import Base


class Employee(Base):
    """Model para funcionarios - sincronizado com banco."""

    __tablename__ = "employees"

    # Identificacao
    id = Column(UUID(as_uuid=True), primary_key=True)
    solides_id = Column(String(50), nullable=True, index=True)
    matricula = Column(String(50), nullable=True, index=True)
    codigo = Column(String(20), nullable=True, index=True)

    # Dados pessoais
    nome = Column(String(255), nullable=False)
    nome_social = Column(String(255), nullable=True)
    cpf = Column(String(14), nullable=True, index=True)
    rg = Column(String(20), nullable=True)
    rg_orgao = Column(String(20), nullable=True)
    rg_uf = Column(String(2), nullable=True)
    data_nascimento = Column(Date, nullable=True)
    sexo = Column(String(1), nullable=True)
    estado_civil = Column(String(20), nullable=True)
    nacionalidade = Column(String(50), nullable=True)
    naturalidade = Column(String(100), nullable=True)
    nome_mae = Column(String(255), nullable=True)
    nome_pai = Column(String(255), nullable=True)

    # Contato
    email = Column(String(255), nullable=True)
    telefone = Column(String(20), nullable=True)
    celular = Column(String(20), nullable=True)
    contato_emergencia = Column(String(255), nullable=True)
    telefone_emergencia = Column(String(20), nullable=True)

    # Endereco
    cep = Column(String(10), nullable=True)
    logradouro = Column(String(255), nullable=True)
    numero = Column(String(20), nullable=True)
    complemento = Column(String(100), nullable=True)
    bairro = Column(String(100), nullable=True)
    cidade = Column(String(100), nullable=True)
    uf = Column(String(2), nullable=True)

    # Dados profissionais
    cargo = Column(String(100), nullable=True, index=True)
    cargo_id = Column(UUID(as_uuid=True), nullable=True)
    # Vínculo com o cargo da CCT (fonte única do piso). FK real p/ cct_cargos.
    cct_cargo_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    # Adicionais POR FUNCIONÁRIO (individuais, dependem do posto/atividade — NÃO do cargo).
    # Ex.: 2 ASG mesmo cargo, só quem limpa a lixeira tem insalubridade. Fonte: folha real (Domínio).
    insalubridade_percentual = Column(Numeric(5, 2), nullable=True, default=0)
    periculosidade_percentual = Column(Numeric(5, 2), nullable=True, default=0)
    adicional_ronda_percentual = Column(Numeric(5, 2), nullable=True, default=0)
    departamento = Column(String(100), nullable=True)
    departamento_id = Column(UUID(as_uuid=True), nullable=True)
    setor = Column(String(100), nullable=True)
    centro_custo = Column(String(100), nullable=True)
    gestor_id = Column(UUID(as_uuid=True), nullable=True)
    gestor_nome = Column(String(255), nullable=True)
    data_admissao = Column(Date, nullable=True)
    data_demissao = Column(Date, nullable=True)
    tipo_contrato = Column(String(50), nullable=True)
    regime_trabalho = Column(String(50), nullable=True)
    jornada_trabalho = Column(String(100), nullable=True)
    carga_horaria_semanal = Column(Integer, nullable=True)
    escala_padrao = Column(String(20), nullable=True)
    salario_base = Column(Numeric(10, 2), nullable=True)
    tipo_pagamento = Column(String(20), nullable=True)

    # Dados bancarios
    banco = Column(String(100), nullable=True)
    agencia = Column(String(20), nullable=True)
    conta = Column(String(30), nullable=True)
    tipo_conta = Column(String(20), nullable=True)
    pix = Column(String(100), nullable=True)

    # Documentos adicionais
    pis = Column(String(20), nullable=True)
    ctps_numero = Column(String(20), nullable=True)
    ctps_serie = Column(String(10), nullable=True)
    ctps_uf = Column(String(2), nullable=True)
    ctps_data_emissao = Column(Date, nullable=True)
    titulo_eleitor = Column(String(20), nullable=True)
    zona_eleitoral = Column(String(10), nullable=True)
    secao_eleitoral = Column(String(10), nullable=True)
    certificado_reservista = Column(String(20), nullable=True)

    # CNH e cursos
    cnh_numero = Column(String(20), nullable=True)
    cnh_categoria = Column(String(5), nullable=True)
    cnh_validade = Column(Date, nullable=True)
    # Curso de formação (nome da coluna no banco mantido por compatibilidade)
    curso_formacao = Column("curso_vigilante", Boolean, nullable=True)
    curso_formacao_validade = Column("curso_vigilante_validade", Date, nullable=True)
    cnv = Column(String(30), nullable=True)
    cnv_validade = Column(Date, nullable=True)
    porte_arma = Column(Boolean, nullable=True)
    porte_arma_numero = Column(String(30), nullable=True)
    porte_arma_validade = Column(Date, nullable=True)
    certificacoes = Column(JSONB, nullable=True)

    # Alocacao e posto
    posto_atual_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    posto_atual_nome = Column(String(255), nullable=True)
    cliente_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    cliente_nome = Column(String(255), nullable=True)
    data_inicio_posto = Column(Date, nullable=True)
    turno_padrao = Column(String(20), nullable=True)
    scale_template_id = Column(UUID(as_uuid=True), nullable=True)

    # Status e controle
    status = Column(String(20), nullable=True, index=True)
    motivo_inatividade = Column(String(255), nullable=True)
    data_retorno_previsto = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=True)

    # Perfil e competencias
    perfil_disc = Column(JSONB, nullable=True)
    perfil_predominante = Column(String(50), nullable=True)
    competencias = Column(JSONB, nullable=True)

    # Biometria e acesso
    foto_url = Column(String(500), nullable=True)
    biometria_facial = Column(Boolean, nullable=True)
    biometria_digital = Column(Boolean, nullable=True)
    cracha_numero = Column(String(20), nullable=True)

    # Outros
    dependentes = Column(JSONB, nullable=True)
    observacoes = Column(Text, nullable=True)
    dados_adicionais = Column(JSONB, nullable=True)

    # Sincronizacao
    sync_source = Column(String(20), nullable=True)
    last_synced_at = Column(DateTime, nullable=True)

    # Auditoria
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Employee(id={self.id}, nome={self.nome}, cpf={self.cpf})>"

    @property
    def nome_completo(self) -> str:
        """Retorna nome social se existir, senao nome."""
        return self.nome_social or self.nome

    @property
    def idade(self) -> int | None:
        """Calcula idade do funcionario."""
        if not self.data_nascimento:
            return None
        today = date.today()
        return (
            today.year
            - self.data_nascimento.year
            - ((today.month, today.day) < (self.data_nascimento.month, self.data_nascimento.day))
        )

    @property
    def tempo_empresa_dias(self) -> int | None:
        """Calcula tempo de empresa em dias."""
        if not self.data_admissao:
            return None
        fim = self.data_demissao or date.today()
        return (fim - self.data_admissao).days

    @property
    def endereco_completo(self) -> str:
        """Retorna endereco formatado."""
        parts = []
        if self.logradouro:
            addr = self.logradouro
            if self.numero:
                addr += f", {self.numero}"
            if self.complemento:
                addr += f" - {self.complemento}"
            parts.append(addr)
        if self.bairro:
            parts.append(self.bairro)
        if self.cidade and self.uf:
            parts.append(f"{self.cidade}/{self.uf}")
        if self.cep:
            parts.append(f"CEP: {self.cep}")
        return ", ".join(parts)

    @property
    def dados_bancarios_completos(self) -> bool:
        """Verifica se dados bancarios estao completos."""
        return bool(self.banco and self.agencia and self.conta)

    @property
    def cnh_valida(self) -> bool:
        """Verifica se CNH esta valida."""
        if not self.cnh_validade:
            return False
        return self.cnh_validade >= date.today()

    @property
    def curso_formacao_valido(self) -> bool:
        """Verifica se curso de formacao esta valido."""
        if not self.curso_formacao or not self.curso_formacao_validade:
            return False
        return self.curso_formacao_validade >= date.today()

    @property
    def cnv_valido(self) -> bool:
        """Verifica se CNV esta valido."""
        if not self.cnv_validade:
            return False
        return self.cnv_validade >= date.today()

    @property
    def porte_arma_valido(self) -> bool:
        """Verifica se porte de arma esta valido."""
        if not self.porte_arma or not self.porte_arma_validade:
            return False
        return self.porte_arma_validade >= date.today()
