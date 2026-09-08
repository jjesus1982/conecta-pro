"""
Kit Drive Service — Conecta PRO
Monta o kit documental no Google Drive:
1. Criar estrutura de pastas
2. Upload de cada documento do kit
3. Gerar link compartilhável
4. Salvar no banco (gdrive_kits)
5. Notificar ATLAS do kit concluído
"""

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

MESES_PT: dict[str, str] = {
    "01": "Janeiro",
    "02": "Fevereiro",
    "03": "Março",
    "04": "Abril",
    "05": "Maio",
    "06": "Junho",
    "07": "Julho",
    "08": "Agosto",
    "09": "Setembro",
    "10": "Outubro",
    "11": "Novembro",
    "12": "Dezembro",
}


def _get_session():
    from core.database.session import SyncSessionLocal

    return SyncSessionLocal()


def _fetch(query: str, params: dict[str, Any] | None = None) -> list[dict]:
    session = _get_session()
    try:
        result = session.execute(text(query), params or {})
        return [dict(r) for r in result.mappings()]
    except Exception as exc:
        logger.warning("KitDrive._fetch: %s", exc)
        return []
    finally:
        session.close()


def _exec(query: str, params: dict[str, Any] | None = None) -> bool:
    session = _get_session()
    try:
        session.execute(text(query), params or {})
        session.commit()
        return True
    except Exception as exc:
        logger.warning("KitDrive._exec: %s", exc)
        session.rollback()
        return False
    finally:
        session.close()


class KitDriveService:
    """Serviço de montagem de kit no Google Drive."""

    def _conectar_drive(self) -> bool:
        """Carregar tokens do banco e conectar (ou usar service account)."""
        from modules.gdrive.services.gdrive_service import gdrive_service

        if gdrive_service.esta_conectado():
            return True

        rows = _fetch(
            "SELECT access_token, refresh_token, token_expiry::text "
            "FROM gdrive_config WHERE is_connected = TRUE LIMIT 1"
        )
        if not rows:
            logger.warning("GDrive: tokens não encontrados em gdrive_config")
            return False

        row = rows[0]
        return gdrive_service.conectar_com_tokens(
            row.get("access_token", ""),
            row.get("refresh_token", ""),
            row.get("token_expiry"),
        )

    def _buscar_documentos_kit(self, client_id: str, competencia: str) -> list[dict]:
        """Buscar documentos do kit no banco GED via ged_kit_documents."""
        return _fetch(
            """
            SELECT
                gkd.file_path,
                gkd.document_name AS file_name,
                gkd.document_type,
                COALESCE(gkd.file_size_bytes, 0) AS file_size
            FROM ged_kit_documents gkd
            JOIN ged_document_kits gdk ON gdk.id = gkd.kit_id
            WHERE gdk.client_id = :client_id
              AND gdk.reference_month::text LIKE :comp_prefix
              AND gkd.file_path IS NOT NULL
            ORDER BY gkd.document_type, gkd.document_name
            """,
            {"client_id": client_id, "comp_prefix": f"{competencia}%"},
        )

    def _nome_pasta_mes(self, competencia: str) -> str:
        try:
            ano, mes = competencia.split("-")
            return f"{competencia} — {MESES_PT.get(mes, mes)} {ano}"
        except Exception:
            return competencia

    async def montar_kit_no_drive(
        self,
        client_id: str,
        competencia: str,
        tipo_kit: str = "maos_de_obra",
    ) -> dict[str, Any]:
        """
        Montar o kit completo no Drive:
        1. Conectar ao Drive
        2. Criar pastas cliente/mês
        3. Upload de cada documento
        4. Gerar link compartilhável
        5. Salvar no banco
        6. Notificar ATLAS + EventBus
        """
        from modules.gdrive.services.gdrive_service import gdrive_service

        # 1. Conectar
        if not self._conectar_drive():
            return {
                "sucesso": False,
                "erro": "Google Drive não autorizado",
                "acao": "Configure as credenciais em /opt/conecta-pro/config/google_drive_credentials.json",
            }

        # 2. Buscar nome do cliente
        cli_rows = _fetch(
            "SELECT name FROM ged_clients WHERE id::text = :cid LIMIT 1",
            {"cid": client_id},
        )
        if not cli_rows:
            # Fallback: buscar na tabela clients
            cli_rows = _fetch(
                "SELECT name FROM clients WHERE id::text = :cid LIMIT 1",
                {"cid": client_id},
            )
        if not cli_rows:
            return {"sucesso": False, "erro": "Cliente não encontrado"}
        client_name = cli_rows[0]["name"]

        # 3. Buscar documentos do kit
        docs = self._buscar_documentos_kit(client_id, competencia)
        if not docs:
            return {
                "sucesso": False,
                "erro": f"Nenhum documento encontrado para {client_name} {competencia}",
            }

        # 4. Garantir estrutura de pastas
        client_folder, month_folder = gdrive_service.garantir_estrutura_cliente(client_name, competencia)
        if not month_folder:
            return {"sucesso": False, "erro": "Falha ao criar estrutura de pastas no Drive"}

        # 5. Upload de cada documento
        uploads_ok = 0
        uploads_erro = 0
        detalhes: list[dict] = []

        for doc in docs:
            file_path = doc.get("file_path") or ""
            file_name = doc.get("file_name") or ""
            if not file_path:
                uploads_erro += 1
                continue
            try:
                result = gdrive_service.fazer_upload_arquivo(file_path, month_folder, file_name)
                if result:
                    uploads_ok += 1
                    detalhes.append(
                        {
                            "arquivo": file_name,
                            "id": result["id"],
                            "link": result.get("webViewLink", ""),
                            "status": "ok",
                        }
                    )
                    # Salvar upload no banco
                    _exec(
                        """
                        INSERT INTO gdrive_uploads
                            (client_id, competencia, file_name, file_id, folder_id, file_url, status)
                        VALUES
                            (:client_id, :competencia, :file_name, :file_id, :folder_id, :file_url, 'uploaded')
                        """,
                        {
                            "client_id": client_id,
                            "competencia": competencia,
                            "file_name": file_name,
                            "file_id": result["id"],
                            "folder_id": month_folder,
                            "file_url": result.get("webViewLink", ""),
                        },
                    )
                else:
                    uploads_erro += 1
                    detalhes.append({"arquivo": file_name, "status": "erro"})
            except Exception as exc:
                uploads_erro += 1
                detalhes.append({"arquivo": file_name, "status": "erro", "detalhe": str(exc)})

        # 6. Gerar link da pasta do mês
        share_link = gdrive_service.obter_link_pasta(month_folder, tornar_publico=False)  # holerites não podem ser públicos por link (08/09/2026)

        # 7. Salvar kit no banco (gdrive_kits + ged_document_kits.google_drive_link)
        _exec(
            """
            INSERT INTO gdrive_kits
                (client_id, competencia, folder_id, folder_url, share_link, total_docs, status)
            VALUES
                (:client_id, :competencia, :folder_id, :share_link, :share_link, :total_docs, 'concluido')
            ON CONFLICT (client_id, competencia) DO UPDATE SET
                folder_id  = EXCLUDED.folder_id,
                share_link = EXCLUDED.share_link,
                total_docs = EXCLUDED.total_docs,
                status     = 'concluido',
                updated_at = NOW()
            """,
            {
                "client_id": client_id,
                "competencia": competencia,
                "folder_id": month_folder or "",
                "share_link": share_link or "",
                "total_docs": uploads_ok,
            },
        )
        # Atualizar google_drive_link em ged_document_kits
        if share_link:
            _exec(
                """
                UPDATE ged_document_kits
                SET google_drive_link = :link, updated_at = NOW()
                WHERE client_id::text = :client_id
                  AND reference_month::text LIKE :comp_prefix
                """,
                {"link": share_link, "client_id": client_id, "comp_prefix": f"{competencia}%"},
            )

        # 8. Notificar ATLAS
        try:
            from modules.gedeon.agents.atlas import atlas

            atlas.registrar_kit_concluido(
                client_id=client_id,
                competencia=competencia,
                tipo_kit=tipo_kit,
                score_final=100 if uploads_erro == 0 else 70,
                docs_total=len(docs),
                docs_auto=uploads_ok,
                observacoes=f"Kit enviado ao Drive: {uploads_ok} docs",
                checklist_respostas={},
                movimentacoes=[],
                pendencias=[],
            )
        except Exception:
            pass

        # 9. Publicar evento no Event Bus
        try:
            import asyncio

            from infrastructure.event_bus import ConectaEvent, event_bus

            asyncio.create_task(
                event_bus.publish(
                    ConectaEvent(
                        event_type="ged.kit.enviado_drive",
                        payload={
                            "client_id": client_id,
                            "cliente": client_name,
                            "competencia": competencia,
                            "total_docs": len(docs),
                            "uploads_ok": uploads_ok,
                            "share_link": share_link,
                        },
                        source_module="gdrive",
                        cliente_id=client_id,
                        competencia=competencia,
                    )
                )
            )
        except Exception:
            pass

        logger.info(
            "Kit Drive: %s %s — %d/%d docs ok",
            client_name,
            competencia,
            uploads_ok,
            len(docs),
        )

        return {
            "sucesso": uploads_ok > 0,
            "cliente": client_name,
            "competencia": competencia,
            "total_docs": len(docs),
            "uploads_ok": uploads_ok,
            "uploads_erro": uploads_erro,
            "share_link": share_link,
            "folder_id": month_folder,
            "detalhes": detalhes,
        }

    def obter_link_kit(self, client_id: str, competencia: str) -> str | None:
        """Obter link do kit já montado no Drive."""
        rows = _fetch(
            "SELECT share_link FROM gdrive_kits "
            "WHERE client_id::text = :client_id AND competencia = :competencia "
            "AND status = 'concluido' LIMIT 1",
            {"client_id": client_id, "competencia": competencia},
        )
        return (rows[0]["share_link"] or None) if rows else None

    def listar_kits_drive(self, client_id: str | None = None) -> list[dict]:
        """Listar kits montados no Drive."""
        where = "WHERE gk.client_id::text = :client_id" if client_id else ""
        params = {"client_id": client_id} if client_id else {}
        rows = _fetch(
            f"""
            SELECT
                COALESCE(gc.name, gk.client_id::text) AS cliente,
                gk.competencia,
                gk.total_docs,
                gk.share_link,
                gk.status,
                gk.created_at::text AS criado_em
            FROM gdrive_kits gk
            LEFT JOIN ged_clients gc ON gc.id = gk.client_id
            {where}
            ORDER BY gk.created_at DESC
            LIMIT 50
            """,
            params,
        )
        return rows


# Singleton
kit_drive_service = KitDriveService()
