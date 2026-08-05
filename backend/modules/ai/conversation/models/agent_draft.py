"""AgentDraft — rascunho criado pelo agente/chat, aguardando aprovação humana.

Nada aqui é executado: `payload` guarda os args para o executor de domínio rodar SÓ na
aprovação (registry em acoes/rascunho.py). Propositor = agente; `solicitado_por` é trilha,
não exclui ninguém de aprovar. Ver docs/superpowers/plans/2026-08-05-central-rascunhos-agente.md.
"""
from sqlalchemy import Boolean, Column, DateTime, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.sql import func

from core.models import Base


class AgentDraft(Base):
    __tablename__ = "agent_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default="gen_random_uuid()")
    tipo = Column(Text, nullable=False)              # chave do executor (ex.: 'comunicado')
    modulo = Column(Text, nullable=False)
    titulo = Column(Text, nullable=False)
    resumo = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=False, server_default="{}")  # args p/ o executor
    status = Column(Text, nullable=False, server_default="rascunho")  # rascunho|aprovado|rejeitado|executado|falha
    gate = Column(Text, nullable=False, server_default="🔵")
    requires_otp = Column(Boolean, nullable=False, server_default="false")
    roles_aprovador = Column(ARRAY(Text), nullable=False)
    criado_por_agente = Column(Boolean, nullable=False, server_default="true")
    solicitado_por = Column(UUID(as_uuid=True), nullable=True)     # trilha, NÃO aprovador-excludente
    solicitado_por_nome = Column(Text, nullable=True)
    empresa_id = Column(UUID(as_uuid=True), nullable=True)
    entity_ref = Column(Text, nullable=True)          # id da linha de domínio após executar
    erro_execucao = Column(Text, nullable=True)
    decidido_por = Column(UUID(as_uuid=True), nullable=True)
    decidido_em = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
