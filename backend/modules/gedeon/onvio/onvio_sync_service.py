"""
GEDEON Fase 3 — Onvio Sync Service (versão consolidada pós-auditoria T7)

Mudanças vs versão anterior:
- BUG #2 FIX: abandonar FOLDER_MAP (8/9 IDs inválidos). Usar listagem flat + containerId.
- BUG #3 FIX: STORAGE_BASE = /app/uploads/onvio (volume montado no container).
- BUG #1 FIX: depende do onvio_client.py reescrito (auth UDSLongToken).
"""

import logging
import time
from pathlib import Path

from sqlalchemy.orm import Session

from modules.gedeon.models.onvio_models import (
    FgtsGuia,
    InssGuia,
    OnvioDocument,
    OnvioSyncLog,
)
from modules.gedeon.onvio.onvio_client import OnvioClient
from modules.gedeon.onvio.onvio_parser import classificar_item_onvio as classificar_documento

logger = logging.getLogger(__name__)

# BUG #3 FIX: volume /app/uploads montado no container (T7 + D.3 confirmaram)
STORAGE_BASE = Path("/app/uploads/onvio")


class OnvioSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.client = OnvioClient()

    def sync_completo(self, mes_ref: str | None = None) -> dict:
        """
        Sincroniza documentos do Onvio.

        Args:
            mes_ref: Filtra por mês (ex: "03.2026"). Se None, baixa tudo.
        """
        inicio = time.time()
        log = OnvioSyncLog(mes_ref=mes_ref or "all", status="running")
        self.db.add(log)
        self.db.commit()

        try:
            # BUG #2 FIX: listagem flat — NÃO usa FOLDER_MAP
            todos_docs = self.client.listar_todos_documentos()
            logger.info(f"Onvio retornou {len(todos_docs)} documentos totais")

            novos = erros = pulados = 0
            erros_detalhe = []

            EXTENSOES_VALIDAS = {".pdf", ".PDF"}

            for item in todos_docs:
                try:
                    nome = item.get("name", "")
                    ext = "." + nome.rsplit(".", 1)[-1] if "." in nome else ""

                    # Pular arquivos não-PDF (xlsx, xlt, docx, etc.)
                    if ext not in EXTENSOES_VALIDAS:
                        pulados += 1
                        continue

                    # Pular se já importado
                    if self._ja_importado(item.get("id")):
                        pulados += 1
                        continue

                    # Classificar
                    cl = classificar_documento(item)

                    # Filtrar por mês (se especificado)
                    if mes_ref and cl.mes_ref and cl.mes_ref != mes_ref:
                        continue

                    # Baixar + salvar
                    caminho = self._baixar_e_salvar(item, cl)
                    self._salvar_db(item, cl, caminho)
                    novos += 1

                except Exception as e:
                    logger.error(f"Erro doc {item.get('name', '?')}: {e}")
                    erros_detalhe.append(f"{item.get('name', '?')}: {str(e)[:100]}")
                    erros += 1

            log.status = "success" if erros == 0 else "partial"
            log.docs_baixados = novos + erros
            log.docs_novos = novos
            log.docs_erro = erros
            log.duracao_s = time.time() - inicio
            log.detalhes = (
                f"Total API: {len(todos_docs)} | Novos: {novos} | "
                f"Pulados (já existentes): {pulados} | Erros: {erros}\n" + "\n".join(erros_detalhe[:10])
            )
            self.db.commit()

            # Fase 2: extrai VALOR/vencimento das guias recém-baixadas. Sem isto as linhas
            # fgts_guias/inss_guias nasciam com valor=NULL (oráculo furado) até alguém chamar
            # /extrair-valores à mão — que nunca acontecia. Defensivo: falha aqui não derruba
            # o sync (os PDFs já estão salvos; a extração é re-tentável).
            extracao = None
            try:
                from modules.gedeon.onvio.pdf_extractor.enrichment_service import EnrichmentService

                extracao = EnrichmentService(self.db).extrair_todos()
            except Exception as ee:  # noqa: BLE001
                logger.warning("Extração de valores pós-sync falhou (segue): %s", ee)

            return {
                "status": log.status,
                "total_api": len(todos_docs),
                "novos": novos,
                "pulados": pulados,
                "erros": erros,
                "duracao": log.duracao_s,
                "extracao": extracao,
            }

        except Exception as e:
            log.status = "error"
            log.detalhes = str(e)[:500]
            log.duracao_s = time.time() - inicio
            self.db.commit()
            logger.exception("Falha crítica no sync_completo")
            raise

    def _ja_importado(self, onvio_id: str) -> bool:
        return self.db.query(OnvioDocument).filter_by(onvio_id=onvio_id).first() is not None

    def _baixar_e_salvar(self, item: dict, cl) -> str:
        """Baixa PDF e salva em /app/uploads/onvio/<categoria>/<mes>/<nome>.pdf"""
        # BUG #2 FIX: usar containerId (T7 confirmou campo correto)
        container_id = item.get("containerId") or item.get("parentId")
        if not container_id:
            raise ValueError(f"Documento {item.get('id')} sem containerId")

        doc_id = item.get("id")
        mes = cl.mes_ref or "sem-ref"
        cat_dir = STORAGE_BASE / cl.categoria / mes
        cat_dir.mkdir(parents=True, exist_ok=True)

        nome_seguro = item.get("name", f"{doc_id}.pdf").replace("/", "_")
        caminho = cat_dir / nome_seguro

        pdf = self.client.baixar_pdf(container_id, doc_id)
        caminho.write_bytes(pdf)
        return str(caminho)

    def _salvar_db(self, item: dict, cl, caminho: str) -> None:
        """Insere em onvio_documents + tabelas específicas (fgts/inss)."""
        doc = OnvioDocument(
            onvio_id=item.get("id"),
            onvio_folder_id=item.get("containerId") or item.get("parentId", ""),
            nome_arquivo=item.get("name", ""),
            categoria=cl.categoria,
            mes_ref=cl.mes_ref,
            caminho_local=caminho,
            tamanho_bytes=Path(caminho).stat().st_size,
            data_onvio=item.get("createdDate"),
            processado=False,
        )
        self.db.add(doc)

        # Registros específicos por categoria
        if cl.categoria in ("fgts_guia", "fgts_consignado", "fgts_relatorio"):
            self.db.add(
                FgtsGuia(
                    mes_ref=cl.mes_ref or "",
                    tipo=cl.categoria.replace("fgts_", "").upper(),
                    arquivo_pdf=caminho,
                )
            )
        elif cl.categoria == "inss_guia":
            self.db.add(
                InssGuia(
                    mes_ref=cl.mes_ref or "",
                    arquivo_pdf=caminho,
                )
            )

        self.db.commit()
