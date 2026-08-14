"""ORM (SQLAlchemy 2.x) espelhando schema.sql. schema.sql é a fonte da verdade
para o DDL/migração; este módulo é o acesso da aplicação."""
from __future__ import annotations

import datetime as dt
from sqlalchemy import (
    BigInteger, String, Text, Boolean, DateTime, Date, ForeignKey, func
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Favorecido(Base):
    __tablename__ = "favorecido"
    __table_args__ = {"schema": "folha_efi"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    funcionario_id: Mapped[int] = mapped_column(BigInteger)
    nome: Mapped[str] = mapped_column(Text)
    documento: Mapped[str] = mapped_column(String(14))
    chave_pix: Mapped[str] = mapped_column(Text)
    chave_validada_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    chave_nome_bacen: Mapped[str | None] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)


class LotePagamento(Base):
    __tablename__ = "lote_pagamento"
    __table_args__ = {"schema": "folha_efi"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referencia: Mapped[str] = mapped_column(Text)
    competencia: Mapped[dt.date] = mapped_column(Date)
    empresa_cnpj: Mapped[str] = mapped_column(String(14))
    chave_pix_origem: Mapped[str] = mapped_column(Text)
    total_esperado_centavos: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Text, default="RASCUNHO")
    autorizado_por: Mapped[str | None] = mapped_column(Text)
    autorizado_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    itens: Mapped[list["Pagamento"]] = relationship(back_populates="lote")


class Pagamento(Base):
    __tablename__ = "pagamento"
    __table_args__ = {"schema": "folha_efi"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("folha_efi.lote_pagamento.id"))
    favorecido_id: Mapped[int] = mapped_column(ForeignKey("folha_efi.favorecido.id"))
    id_envio: Mapped[str] = mapped_column(String(35), unique=True)
    valor_centavos: Mapped[int] = mapped_column(BigInteger)
    chave_pix_destino: Mapped[str] = mapped_column(Text)
    info_pagador: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="PENDENTE")
    e2e_id: Mapped[str | None] = mapped_column(Text)
    tentativas: Mapped[int] = mapped_column(BigInteger, default=0)
    ultimo_erro: Mapped[str | None] = mapped_column(Text)
    enviado_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    liquidado_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    lote: Mapped[LotePagamento] = relationship(back_populates="itens")


class WebhookEvent(Base):
    __tablename__ = "webhook_event"
    __table_args__ = {"schema": "folha_efi"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    dedup_key: Mapped[str] = mapped_column(Text, unique=True)
    e2e_id: Mapped[str | None] = mapped_column(Text)
    id_envio: Mapped[str | None] = mapped_column(String(35))
    payload: Mapped[dict] = mapped_column(JSONB)
    processado_em: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class PagamentoEvento(Base):
    __tablename__ = "pagamento_evento"
    __table_args__ = {"schema": "folha_efi"}
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pagamento_id: Mapped[int] = mapped_column(ForeignKey("folha_efi.pagamento.id"))
    de_status: Mapped[str | None] = mapped_column(Text)
    para_status: Mapped[str] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(Text)
    detalhe: Mapped[dict | None] = mapped_column(JSONB)
