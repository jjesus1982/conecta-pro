"""Model de mapeamento de riscos (PPRA/PGR)."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base as _declarative_base

try:
    from core.database import Base
except ImportError:
    Base = _declarative_base()


class RiskModel(Base):
    """Mapeamento de risco ocupacional."""

    __tablename__ = "gp_risks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    risk_id = Column(String(36), unique=True, nullable=False, index=True)
    # NULL honesto: PGR/LTCAT mapeiam riscos por FUNÇÃO (GES), não por posto
    # (migration 2026-07-08_sst_missao1 — os posto_id antigos eram órfãos).
    posto_id = Column(String(36), nullable=True, index=True)

    categoria = Column(String(20), nullable=False)  # fisico, quimico, biologico, ergonomico, acidente
    descricao = Column(Text, nullable=False)
    nivel = Column(String(20), nullable=False, default="medio")  # baixo, medio, alto, critico
    fonte_geradora = Column(String(255), nullable=True)

    medidas_controle = Column(JSON, nullable=True, default=list)
    epi_recomendado = Column(JSON, nullable=True, default=list)

    status = Column(String(20), nullable=False, default="identificado")

    # eSocial S-2240 (migration 2026-07-08_sst_missao1 — fontes: LTCAT/laudos MB)
    cod_agente_nocivo = Column(String(20), nullable=True)  # Tabela 24; NULL = não declarável/não enquadrado
    utiliz_epc = Column(String(1), nullable=True)  # 0=não se aplica, 1=não implementa, 2=implementa
    utiliz_epi = Column(String(1), nullable=True)  # 0=não se aplica, 1=não utilizado, 2=utilizado
    medicao = Column(Text, nullable=True)  # medição/conclusão REAL do laudo, com fonte e data
    funcoes_aplicaveis = Column(JSON, nullable=True)  # tokens AGP|LIDER|ASG|ARTIFICE|JARDINEIRO (PGR GES)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at = Column(DateTime, nullable=True, onupdate=lambda: datetime.now(UTC).replace(tzinfo=None))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "risk_id": self.risk_id,
            "posto_id": self.posto_id,
            "categoria": self.categoria,
            "descricao": self.descricao,
            "nivel": self.nivel,
            "medidas_controle": self.medidas_controle,
            "status": self.status,
            "cod_agente_nocivo": self.cod_agente_nocivo,
            "utiliz_epc": self.utiliz_epc,
            "utiliz_epi": self.utiliz_epi,
            "medicao": self.medicao,
            "funcoes_aplicaveis": self.funcoes_aplicaveis,
        }
