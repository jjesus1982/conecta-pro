"""
EnrichmentService — Orquestra os 3 extractors e persiste resultados.
Executado de forma síncrona dentro de run_in_executor no endpoint.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from modules.gedeon.models.onvio_models import FgtsGuia, InssGuia, OnvioDocument
from modules.gedeon.onvio.pdf_extractor.base import ExtractionResult
from modules.gedeon.onvio.pdf_extractor.das_extractor import DASExtractor
from modules.gedeon.onvio.pdf_extractor.dctfweb_extractor import DCTFWebExtractor
from modules.gedeon.onvio.pdf_extractor.fgts_extractor import FGTSExtractor
from modules.gedeon.onvio.pdf_extractor.inss_extractor import INSSExtractor

logger = logging.getLogger(__name__)

EXTRACTOR_MAP: dict[str, tuple] = {
    "inss_guia": (INSSExtractor, {}),
    "das_simples_nacional": (DASExtractor, {}),  # valor → onvio_documents.detalhes_json (padrão DCTFWeb)
    "fgts_guia": (FGTSExtractor, {"subtipo": "guia"}),
    "fgts_consignado": (FGTSExtractor, {"subtipo": "consignado"}),
    "fgts_relatorio": (FGTSExtractor, {"subtipo": "relatorio"}),
    "fgts_consignado_relatorio": (FGTSExtractor, {"subtipo": "consignado_relatorio"}),
    "dctfweb_declaracao": (DCTFWebExtractor, {"subtipo": "declaracao"}),
    "dctfweb_recibo": (DCTFWebExtractor, {"subtipo": "recibo"}),
    "dctfweb_debitos": (DCTFWebExtractor, {"subtipo": "debitos"}),
    "dctfweb_creditos": (DCTFWebExtractor, {"subtipo": "creditos"}),
    "dctfweb_resumo_debitos": (DCTFWebExtractor, {"subtipo": "resumo_debitos"}),
    "dctfweb_resumo_creditos": (DCTFWebExtractor, {"subtipo": "resumo_creditos"}),
    "dctfweb_extrato": (DCTFWebExtractor, {"subtipo": "extrato"}),
    "dctfweb_situacao": (DCTFWebExtractor, {"subtipo": "situacao"}),
}

THRESHOLD_FINAL = 0.90
THRESHOLD_REVISAO = 0.70
COMMIT_EVERY = 20


class EnrichmentService:
    def __init__(self, db: Session):
        self.db = db
        self._extractor_cache: dict[str, object] = {}

    def _get_extractor(self, categoria: str):
        if categoria in self._extractor_cache:
            return self._extractor_cache[categoria]
        info = EXTRACTOR_MAP.get(categoria)
        if not info:
            return None
        ExtractorClass, kwargs = info
        instance = ExtractorClass(**kwargs)
        self._extractor_cache[categoria] = instance
        return instance

    def extrair_todos(self, forcar: bool = False, limite: int | None = None) -> dict:
        """
        Orquestra extração para todos os docs fiscais com extractor disponível.

        Args:
            forcar: se True reprocessa docs já extraídos
            limite: limita N primeiros (para testes)
        """
        inicio = time.time()

        query = self.db.query(OnvioDocument).filter(OnvioDocument.categoria.in_(list(EXTRACTOR_MAP.keys())))
        if not forcar:
            query = query.filter(OnvioDocument.extraido_em.is_(None))
        if limite:
            query = query.limit(limite)

        docs = query.all()
        total = len(docs)

        # Docs de categorias sem extractor (folha_pagamento, contratos, etc.)
        # nunca entram no loop — contamos separadamente para o relatório
        sem_extractor_count = (
            self.db.query(OnvioDocument).filter(~OnvioDocument.categoria.in_(list(EXTRACTOR_MAP.keys()))).count()
        )

        stats: dict = {
            "processados": 0,
            "salvos_final": 0,
            "salvos_revisao": 0,
            "pulados_baixa_conf": 0,
            "pulados_sem_extractor": sem_extractor_count,
            "erros": 0,
            "por_categoria": {},
        }
        erros_detalhe: list[str] = []

        for idx, doc in enumerate(docs):
            categoria = doc.categoria or "sem_categoria"
            stats["por_categoria"].setdefault(categoria, 0)
            stats["por_categoria"][categoria] += 1

            try:
                extractor = self._get_extractor(categoria)
                if not extractor:
                    stats["pulados_sem_extractor"] += 1
                    continue

                if not doc.caminho_local:
                    erros_detalhe.append(f"{doc.id}: sem caminho_local")
                    stats["erros"] += 1
                    doc.extraido_em = datetime.utcnow()
                    doc.metodo_extracao = "sem_caminho"
                    doc.confianca_extracao = 0.0
                    continue

                pdf_path = Path(doc.caminho_local)
                if not pdf_path.exists():
                    erros_detalhe.append(f"{doc.id}: arquivo não existe — {pdf_path}")
                    stats["erros"] += 1
                    doc.extraido_em = datetime.utcnow()
                    doc.metodo_extracao = "arquivo_nao_encontrado"
                    doc.confianca_extracao = 0.0
                    continue

                result: ExtractionResult = extractor.extract(pdf_path)
                stats["processados"] += 1
                self._persistir(doc, result, stats)

            except Exception as e:
                logger.exception(f"Erro ao processar doc {doc.id}")
                erros_detalhe.append(f"{doc.id}: {str(e)[:100]}")
                stats["erros"] += 1
                doc.extraido_em = datetime.utcnow()
                doc.metodo_extracao = "erro"
                doc.confianca_extracao = 0.0
                doc.detalhes_json = {"erro": str(e)[:200]}

            if (idx + 1) % COMMIT_EVERY == 0:
                self.db.commit()
                logger.info(f"Commit parcial: {idx + 1}/{total}")

        self.db.commit()

        stats["duracao_s"] = round(time.time() - inicio, 2)
        stats["erros_detalhe"] = erros_detalhe[:10]
        return stats

    def _persistir(self, doc: OnvioDocument, result: ExtractionResult, stats: dict) -> None:
        agora = datetime.utcnow()
        doc.extraido_em = agora
        doc.confianca_extracao = result.confianca
        doc.metodo_extracao = result.metodo_extracao
        doc.detalhes_json = result.to_dict()

        if result.confianca >= THRESHOLD_FINAL:
            doc.revisao_manual = False
            stats["salvos_final"] += 1
            self._atualizar_tabela_especifica(doc, result, revisao=False)
        elif result.confianca >= THRESHOLD_REVISAO:
            doc.revisao_manual = True
            stats["salvos_revisao"] += 1
            self._atualizar_tabela_especifica(doc, result, revisao=True)
        else:
            stats["pulados_baixa_conf"] += 1

    def _atualizar_tabela_especifica(self, doc: OnvioDocument, result: ExtractionResult, revisao: bool) -> None:
        categoria = doc.categoria or ""

        if categoria == "inss_guia":
            guia = self.db.query(InssGuia).filter(InssGuia.onvio_doc_id == doc.id).first()
            if not guia:
                guia = self.db.query(InssGuia).filter(InssGuia.arquivo_pdf == doc.caminho_local).first()
            if guia:
                guia.valor = result.valor
                guia.vencimento = result.vencimento
                guia.codigo_barras = result.codigo_barras
                guia.confianca_extracao = result.confianca
                guia.metodo_extracao = result.metodo_extracao
                guia.revisao_manual = revisao
                guia.detalhes_json = result.to_dict()
                guia.extraido_em = datetime.utcnow()

        elif categoria.startswith("fgts_"):
            guia = self.db.query(FgtsGuia).filter(FgtsGuia.onvio_doc_id == doc.id).first()
            if not guia:
                guia = self.db.query(FgtsGuia).filter(FgtsGuia.arquivo_pdf == doc.caminho_local).first()
            if guia:
                guia.valor = result.valor
                guia.vencimento = result.vencimento
                guia.codigo_barras = result.codigo_barras
                guia.confianca_extracao = result.confianca
                guia.metodo_extracao = result.metodo_extracao
                guia.revisao_manual = revisao
                guia.detalhes_json = result.to_dict()
                guia.extraido_em = datetime.utcnow()

        # DCTFWeb: valores ficam em onvio_documents.detalhes_json — sem tabela própria (FASE B3)
