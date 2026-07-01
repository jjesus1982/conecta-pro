"""
GED Agent - Gestao Eletronica de Documentos / Kits Documentais.
Armazenamento, kits mensais, exportacao, Google Drive.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from ..core.events import Event, GPEventTypes
from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


# ==========================================
# SKILLS
# ==========================================


class StorageSkill:
    """Armazenamento, indexacao e busca de documentos."""

    # 70 tipos de documentos
    DOCUMENT_TYPES = {
        # Admissionais (10)
        "ficha_registro": {"categoria": "admissional", "obrigatorio": True},
        "contrato_trabalho": {"categoria": "admissional", "obrigatorio": True},
        "ctps_anotacao": {"categoria": "admissional", "obrigatorio": True},
        "declaracao_dependentes_ir": {"categoria": "admissional", "obrigatorio": True},
        "opcao_vt": {"categoria": "admissional", "obrigatorio": True},
        "termo_confidencialidade": {"categoria": "admissional", "obrigatorio": True},
        "autorizacao_desconto": {"categoria": "admissional", "obrigatorio": False},
        "foto_3x4": {"categoria": "admissional", "obrigatorio": True},
        "comprovante_residencia": {"categoria": "admissional", "obrigatorio": True},
        "certidoes_pessoais": {"categoria": "admissional", "obrigatorio": True},
        # Mensais (6)
        "contracheque": {"categoria": "mensal", "obrigatorio": True},
        "folha_ponto": {"categoria": "mensal", "obrigatorio": True},
        "comprovante_vt": {"categoria": "mensal", "obrigatorio": False},
        "comprovante_va_vr": {"categoria": "mensal", "obrigatorio": False},
        "recibo_pagamento": {"categoria": "mensal", "obrigatorio": True},
        "espelho_ponto": {"categoria": "mensal", "obrigatorio": True},
        # Disciplinares (5)
        "advertencia_verbal": {"categoria": "disciplinar", "obrigatorio": False},
        "advertencia_escrita": {"categoria": "disciplinar", "obrigatorio": True},
        "suspensao": {"categoria": "disciplinar", "obrigatorio": True},
        "termo_compromisso": {"categoria": "disciplinar", "obrigatorio": False},
        "ocorrencia_posto": {"categoria": "disciplinar", "obrigatorio": False},
        # SST (14)
        "aso_admissional": {"categoria": "sst", "obrigatorio": True},
        "aso_periodico": {"categoria": "sst", "obrigatorio": True},
        "aso_demissional": {"categoria": "sst", "obrigatorio": True},
        "aso_retorno": {"categoria": "sst", "obrigatorio": False},
        "aso_mudanca_funcao": {"categoria": "sst", "obrigatorio": False},
        "ficha_epi": {"categoria": "sst", "obrigatorio": True},
        "termo_epi": {"categoria": "sst", "obrigatorio": True},
        "laudo_ltcat": {"categoria": "sst", "obrigatorio": True},
        "laudo_insalubridade": {"categoria": "sst", "obrigatorio": False},
        "laudo_periculosidade": {"categoria": "sst", "obrigatorio": False},
        "ppra_pgr": {"categoria": "sst", "obrigatorio": True},
        "pcmso": {"categoria": "sst", "obrigatorio": True},
        "ata_cipa": {"categoria": "sst", "obrigatorio": False},
        "certificado_nr": {"categoria": "sst", "obrigatorio": False},
        # Ferias (3)
        "aviso_ferias": {"categoria": "ferias", "obrigatorio": True},
        "recibo_ferias": {"categoria": "ferias", "obrigatorio": True},
        "abono_pecuniario": {"categoria": "ferias", "obrigatorio": False},
        # Rescisao (6)
        "aviso_previo": {"categoria": "rescisao", "obrigatorio": True},
        "trct": {"categoria": "rescisao", "obrigatorio": True},
        "termo_quitacao": {"categoria": "rescisao", "obrigatorio": True},
        "guia_seguro_desemprego": {"categoria": "rescisao", "obrigatorio": True},
        "carta_referencia": {"categoria": "rescisao", "obrigatorio": False},
        "entrevista_desligamento": {"categoria": "rescisao", "obrigatorio": False},
        # Treinamento (4)
        "lista_presenca": {"categoria": "treinamento", "obrigatorio": True},
        "certificado_treinamento": {"categoria": "treinamento", "obrigatorio": True},
        "avaliacao_reacao": {"categoria": "treinamento", "obrigatorio": False},
        "material_didatico": {"categoria": "treinamento", "obrigatorio": False},
        # Avaliacao (4)
        "avaliacao_desempenho": {"categoria": "avaliacao", "obrigatorio": False},
        "feedback_360": {"categoria": "avaliacao", "obrigatorio": False},
        "pdi": {"categoria": "avaliacao", "obrigatorio": False},
        "formulario_promocao": {"categoria": "avaliacao", "obrigatorio": False},
        # Afastamentos (8)
        "atestado_medico": {"categoria": "afastamento", "obrigatorio": True},
        "declaracao_comparecimento": {"categoria": "afastamento", "obrigatorio": False},
        "atestado_acompanhante": {"categoria": "afastamento", "obrigatorio": False},
        "licenca_maternidade": {"categoria": "afastamento", "obrigatorio": True},
        "licenca_paternidade": {"categoria": "afastamento", "obrigatorio": True},
        "auxilio_doenca": {"categoria": "afastamento", "obrigatorio": True},
        "cat": {"categoria": "afastamento", "obrigatorio": True},
        "atestado_obito": {"categoria": "afastamento", "obrigatorio": True},
        # Operacionais (5)
        "escala_mes": {"categoria": "operacional", "obrigatorio": True},
        "ordem_servico": {"categoria": "operacional", "obrigatorio": False},
        "relatorio_ronda": {"categoria": "operacional", "obrigatorio": False},
        "checkin_checkout": {"categoria": "operacional", "obrigatorio": False},
        "ocorrencia_cliente": {"categoria": "operacional", "obrigatorio": False},
        # Certidoes Empresa (5)
        "cnd_federal": {"categoria": "certidao", "obrigatorio": True},
        "cnd_estadual": {"categoria": "certidao", "obrigatorio": True},
        "cnd_municipal": {"categoria": "certidao", "obrigatorio": True},
        "crf_fgts": {"categoria": "certidao", "obrigatorio": True},
        "cndt": {"categoria": "certidao", "obrigatorio": True},
    }

    def get_document_types(self, categoria: str | None = None) -> dict[str, Any]:
        """Retorna tipos de documentos, opcionalmente filtrado por categoria."""
        if categoria:
            return {k: v for k, v in self.DOCUMENT_TYPES.items() if v["categoria"] == categoria}
        return self.DOCUMENT_TYPES

    def get_document_count(self) -> int:
        """Retorna total de tipos de documentos cadastrados."""
        return len(self.DOCUMENT_TYPES)

    def get_mandatory_documents(self, categoria: str | None = None) -> list[str]:
        """Retorna documentos obrigatorios."""
        docs = self.get_document_types(categoria)
        return [k for k, v in docs.items() if v["obrigatorio"]]

    def get_categories(self) -> list[str]:
        """Retorna lista de categorias unicas."""
        return list({v["categoria"] for v in self.DOCUMENT_TYPES.values()})


class KitBuilderSkill:
    """Montagem de kits documentais por cliente/mes."""

    def build_kit(
        self,
        client_id: str,
        month: int,
        year: int,
        employee_ids: list[str],
        document_types: list[str] | None = None,
    ) -> dict[str, Any]:
        """Monta um kit documental."""
        if document_types is None:
            document_types = [
                "contracheque",
                "folha_ponto",
                "espelho_ponto",
                "cnd_federal",
                "cnd_estadual",
                "cnd_municipal",
                "crf_fgts",
                "cndt",
            ]

        kit_id = str(uuid4())
        return {
            "kit_id": kit_id,
            "client_id": client_id,
            "reference": f"{year}-{month:02d}",
            "employee_count": len(employee_ids),
            "document_types": document_types,
            "expected_documents": len(employee_ids) * len(document_types),
            "status": "montando",
            "created_at": datetime.utcnow().isoformat(),
        }


class ExportSkill:
    """Exportacao de documentos em diversos formatos."""

    SUPPORTED_FORMATS = ["pdf", "zip", "xlsx"]

    def prepare_export(
        self,
        kit_id: str,
        output_format: str = "pdf",
        include_index: bool = True,
    ) -> dict[str, Any]:
        """Prepara exportacao de um kit."""
        if output_format not in self.SUPPORTED_FORMATS:
            raise ValueError(f"Formato nao suportado: {output_format}")

        return {
            "export_id": str(uuid4()),
            "kit_id": kit_id,
            "format": output_format,
            "include_index": include_index,
            "status": "preparando",
            "created_at": datetime.utcnow().isoformat(),
        }


class DriveSkill:
    """Integracao com Google Drive."""

    def prepare_upload(
        self,
        file_name: str,
        file_size: int,
        folder_path: str,
    ) -> dict[str, Any]:
        """Prepara upload para Google Drive."""
        return {
            "upload_id": str(uuid4()),
            "file_name": file_name,
            "file_size": file_size,
            "folder_path": folder_path,
            "status": "pending",
        }


# ==========================================
# GED AGENT
# ==========================================


class GEDAgent(BaseAgent):
    """Agent do GED - Gestao Eletronica de Documentos."""

    AGENT_NAME = "GED_AGENT"
    AGENT_VERSION = "1.0.0"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.register_skill("STORAGE", StorageSkill())
        self.register_skill("KIT_BUILDER", KitBuilderSkill())
        self.register_skill("EXPORT", ExportSkill())
        self.register_skill("DRIVE", DriveSkill())

    @property
    def handled_events(self) -> list[str]:
        return [
            GPEventTypes.DOCUMENTO_CRIADO,
            GPEventTypes.DOCUMENTO_ASSINADO,
            GPEventTypes.FOLHA_FECHADA,
            GPEventTypes.PONTO_MES_FECHADO,
            GPEventTypes.FUNCIONARIO_ADMITIDO,
            GPEventTypes.FUNCIONARIO_DEMITIDO,
            GPEventTypes.ASO_REALIZADO,
            GPEventTypes.EPI_ENTREGUE,
            GPEventTypes.CERTIFICADO_EMITIDO,
            GPEventTypes.TREINAMENTO_REALIZADO,
        ]

    async def _process_event(self, event: Event) -> None:
        handlers = {
            GPEventTypes.DOCUMENTO_CRIADO: self._on_documento_criado,
            GPEventTypes.FUNCIONARIO_ADMITIDO: self._on_funcionario_admitido,
            GPEventTypes.FOLHA_FECHADA: self._on_folha_fechada,
        }
        handler = handlers.get(event.event_type)
        if handler:
            await handler(event)
        else:
            logger.debug(f"GED: Arquivando evento {event.event_type}")

    async def _on_documento_criado(self, event: Event) -> None:
        logger.info(f"GED: Documento recebido para arquivamento: {event.payload.get('tipo')}")
        await self.emit_event(
            event_type=GPEventTypes.DOCUMENTO_ARQUIVADO,
            payload=event.payload,
            affected_modules=["PORTAL"],
        )

    async def _on_funcionario_admitido(self, event: Event) -> None:
        employee_id = event.payload.get("employee_id")
        logger.info(f"GED: Criando pasta para novo funcionario {employee_id}")

    async def _on_folha_fechada(self, event: Event) -> None:
        logger.info("GED: Folha fechada, preparando kit documental")
        await self.emit_event(
            event_type=GPEventTypes.KIT_MONTADO,
            payload={"month": event.payload.get("month")},
            affected_modules=["PORTAL"],
        )
