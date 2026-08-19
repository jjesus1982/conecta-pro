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
    def __init__(self, db: Session, client_id: str | None = None, empresa_id=None):
        """`client_id`/`empresa_id` amarram esta sincronizacao a UMA empresa.
        Sem eles, comportamento historico: a Eletronica."""
        self.db = db
        self.client = OnvioClient(client_id)
        self.empresa_id = empresa_id

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

            novos = erros = pulados = rebaixados = 0
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

                    # Catalogado JÁ e com o PDF em disco → pular de verdade.
                    #
                    # ⚠️ Antes bastava existir a LINHA no banco. Documento catalogado cujo
                    # arquivo se perdeu (ou nunca chegou a ser escrito) ficava marcado como
                    # importado para sempre e NUNCA era rebaixado. Medido em 18/08/2026: o
                    # sync devolveu `total_api 989, novos 0, pulados 989` com **319
                    # documentos sem arquivo em disco** — entre eles 20 dos 33 DAMs de
                    # parcelamento, que a rotina do fiscal lê do disco. Catálogo não é
                    # acervo. [[feedback_verde_que_nao_prova_nada]]
                    existente = self._registro(item.get("id"))
                    if existente is not None and existente.caminho_local and Path(existente.caminho_local).exists():
                        pulados += 1
                        continue

                    # Classificar
                    cl = classificar_documento(item)

                    # Filtrar por mês (se especificado)
                    if mes_ref and cl.mes_ref and cl.mes_ref != mes_ref:
                        continue

                    if existente is not None:
                        # Linha já existe: só o ponteiro para o arquivo estava furado.
                        # NÃO chamar _salvar_db, que sempre INSERE e duplicaria o registro.
                        caminho = self._baixar_e_salvar(item, cl)
                        existente.caminho_local = caminho
                        existente.tamanho_bytes = Path(caminho).stat().st_size
                        rebaixados += 1
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
                f"Pulados (já existentes): {pulados} | Rebaixados: {rebaixados} | Erros: {erros}\n"
                + "\n".join(erros_detalhe[:10])
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
                "rebaixados": rebaixados,
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
        return self._registro(onvio_id) is not None

    def _registro(self, onvio_id: str):
        """A linha do documento, ou None. Existir a linha NÃO prova que o PDF está em disco."""
        return self.db.query(OnvioDocument).filter_by(onvio_id=onvio_id).first()

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
            empresa_id=self.empresa_id,
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


def sync_todas_empresas(db, mes_ref: str | None = None) -> dict:
    """Sincroniza o Onvio de TODA empresa que tenha clientId cadastrado.

    A conta jjesus@conectamais.pro enxerga as duas (Eletrônica code 25, Patrimonial
    code 102) com UMA sessão — o seletor do Onvio só troca qual clientId a listagem pede.
    Antes disso o clientId era constante no código e a Patrimonial simplesmente não
    existia para o sistema: 983 documentos da Eletrônica no banco e ZERO dela.

    Isso importa porque quem emprega os porteiros dos 7 postos é a PATRIMONIAL. O kit do
    condomínio prova que a EMPREGADORA recolheu; com uma empresa só, ele vinha provando
    o recolhimento da outra.
    """
    from sqlalchemy import text as _text

    empresas = (
        db.execute(
            _text(
                "SELECT id, slug, onvio_client_id FROM empresas  WHERE coalesce(onvio_client_id,'') <> '' ORDER BY slug"
            )
        )
        .mappings()
        .all()
    )
    if not empresas:
        return {"status": "erro", "motivo": "nenhuma empresa com onvio_client_id cadastrado"}

    out: dict = {"empresas": {}, "total_novos": 0, "total_erros": 0}
    for e in empresas:
        try:
            r = OnvioSyncService(db, client_id=e["onvio_client_id"], empresa_id=e["id"]).sync_completo(mes_ref=mes_ref)
        except Exception as exc:  # noqa: BLE001 — uma empresa quebrada não cala a outra
            logger.warning("sync Onvio de %s falhou: %s", e["slug"], exc)
            out["empresas"][e["slug"]] = {"status": "erro", "erro": str(exc)}
            out["total_erros"] += 1
            continue
        out["empresas"][e["slug"]] = r
        out["total_novos"] += int(r.get("novos") or 0)
        out["total_erros"] += int(r.get("erros") or 0)
    return out


def sincronizar_todas_empresas(db: Session, mes_ref: str | None = None) -> dict:
    """Sincroniza o Onvio de CADA empresa que tem `onvio_client_id`.

    ⭐ Existe porque o mapa `empresas.onvio_client_id` foi criado (migration c5d6e7f8a9b0),
    populado com os dois CNPJs, e **ninguém o lia**: todo caminho instanciava
    `OnvioSyncService(db)` sem argumento, o que cai no padrão histórico — a Eletrônica. A
    Patrimonial tinha 147 documentos no Onvio, incluindo as cinco CNDs que a Portte deposita,
    e nenhuma rotina os trazia. Medido em 19/08/2026.

    A regra existia e faltava o gatilho — a mesma doença que já tinha escondido nove
    parcelamentos e a baixa por recibo.

    ⚠️ Uma empresa falhar NÃO pode impedir a outra: o Onvio nega documento de cliente ao qual
    a conta não tem vínculo (403), e antes de 19/08 era exatamente esse o caso da Patrimonial.
    Cada empresa é sincronizada isolada e o erro dela vira linha no relatório.
    """
    from sqlalchemy import text as _t

    linhas = db.execute(_t(
        "SELECT id::text, slug, onvio_client_id FROM empresas "
        " WHERE coalesce(onvio_client_id, '') <> '' "
        "   AND lower(coalesce(status, 'ativa')) NOT IN ('inativa', 'encerrada') "
        " ORDER BY slug")).fetchall()

    rel: dict = {"empresas": {}, "total_novos": 0, "total_rebaixados": 0}
    for empresa_id, slug, client_id in linhas:
        try:
            r = OnvioSyncService(db, client_id=client_id, empresa_id=empresa_id).sync_completo(
                mes_ref=mes_ref) or {}
            rel["empresas"][slug] = {k: r.get(k) for k in
                                     ("status", "total_api", "novos", "rebaixados", "erros")}
            rel["total_novos"] += int(r.get("novos") or 0)
            rel["total_rebaixados"] += int(r.get("rebaixados") or 0)
        except Exception as exc:  # noqa: BLE001 — uma empresa não derruba a outra
            logger.error("[onvio] sync de %s falhou: %s", slug, exc)
            rel["empresas"][slug] = {"status": "erro", "erro": str(exc)[:200]}
    logger.info("[onvio] sync multi-empresa: %s", rel["empresas"])
    return rel
