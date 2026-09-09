"""
Servico de Integracao com Google Drive.

Faz upload de kits documentais para o Google Drive, cria estrutura
de pastas e gera links compartilhaveis. Funciona de forma opcional:
se as credenciais do Drive nao estiverem configuradas, os metodos
retornam graciosamente sem erro.
"""

import logging
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.ged.models.client import GedClient
from modules.people_management.ged.models.document_kit import GedDocumentKit
from modules.people_management.ged.models.kit_document import KitDocument

logger = logging.getLogger(__name__)

#: 09/09/2026: subpastas de Funcionarios, no padrão do kit real (Villa Dei Fiori). O kit da contabilidade junta
#: tudo por categoria — "Contracheques.pdf", "Folhas de Ponto.pdf", "Recibos de Pagamento de Vale Transporte e
#: Alimentação.pdf" — e é assim que o DP procura.
CATEGORIA_FUNCIONARIO: dict[str, str] = {
    "folha_ponto": "Folhas de Ponto",
    "contracheque": "Contracheques",
    "comprovante_pagamento": "Comprovantes de Pagamento",
    "recibo_adiantamento": "Comprovantes de Pagamento",
    "comprovante_vt": "Recibos e Comprovantes de VA e VT",
    "comprovante_vr": "Recibos e Comprovantes de VA e VT",
    "comprovante_va": "Recibos e Comprovantes de VA e VT",
}

GOOGLE_CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_DRIVE_CREDENTIALS",
    "/opt/conecta-pro/config/google_drive_credentials.json",
)
GED_STORAGE_BASE = os.environ.get("GED_STORAGE_PATH", "/opt/conecta-pro/storage/ged")


def _get_drive_service():
    """Cria instancia do servico Google Drive API.

    Returns:
        googleapiclient.discovery.Resource ou None se nao configurado.
    """
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
            logger.debug("Credenciais do Google Drive nao encontradas em %s", GOOGLE_CREDENTIALS_PATH)
            return None

        creds = Credentials.from_service_account_file(
            GOOGLE_CREDENTIALS_PATH,
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        service = build("drive", "v3", credentials=creds)
        return service

    except ImportError:
        logger.debug("Bibliotecas do Google Drive nao instaladas (google-auth, google-api-python-client)")
        return None
    except Exception as e:
        logger.warning("Erro ao inicializar Google Drive: %s", e)
        return None


class GoogleDriveService:
    """Servico de integracao com Google Drive para kits documentais."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._service = None
        self._initialized = False

    def _ensure_service(self):
        """Inicializa o servico Drive sob demanda."""
        if not self._initialized:
            self._service = _get_drive_service()
            if self._service is None:
                # 09/09: o arquivo google_drive_credentials.json nunca existiu no container → "Drive não
                # configurado" e o kit do banco NUNCA subiu. O GEDEON já tem sessão OAuth viva (gdrive_service):
                # é o mesmo Drive v3, então o kit do banco usa a mesma sessão.
                try:
                    from modules.gdrive.services.gdrive_service import gdrive_service

                    if not gdrive_service._service:
                        gdrive_service.check_status()
                    self._service = gdrive_service._service
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Drive do kit: sessão do GEDEON indisponível: %s", exc)
            self._initialized = True
        return self._service

    async def check_credentials(self) -> dict:
        """Verifica se a API do Google Drive esta configurada.

        Returns:
            Dicionario com status da configuracao.
        """
        # Prioridade 1: OAuth2 tokens no banco (gdrive_config)
        try:
            from sqlalchemy import text as _sa_text

            row = (
                (
                    await self.db.execute(
                        _sa_text(
                            "SELECT owner_email, is_connected FROM gdrive_config WHERE is_connected = TRUE LIMIT 1"
                        )
                    )
                )
                .mappings()
                .first()
            )
            if row:
                return {
                    "configured": True,
                    "credentials_file_exists": os.path.exists(GOOGLE_CREDENTIALS_PATH),
                    "credentials_path": GOOGLE_CREDENTIALS_PATH,
                    "message": f"Google Drive conectado via OAuth2 ({row['owner_email']})",
                }
        except Exception as exc:
            logger.warning("GoogleDriveService.check_credentials OAuth2: %s", exc)

        # Prioridade 2: service account (arquivo JSON)
        service = self._ensure_service()
        credentials_exist = os.path.exists(GOOGLE_CREDENTIALS_PATH)

        if service:
            # Testar conexao listando a raiz
            try:
                (
                    service.files()
                    .list(
                        pageSize=1,
                        fields="files(id, name)",
                    )
                    .execute()
                )
                connected = True
                message = "Google Drive API configurada e conectada"
            except Exception as e:
                connected = False
                message = f"Credenciais encontradas mas conexao falhou: {str(e)}"
        else:
            connected = False
            if not credentials_exist:
                message = (
                    f"Credenciais nao encontradas em {GOOGLE_CREDENTIALS_PATH}. "
                    "Configure o arquivo de service account para habilitar a integracao."
                )
            else:
                message = (
                    "Bibliotecas do Google Drive nao instaladas. "
                    "Execute: pip install google-auth google-api-python-client"
                )

        return {
            "configured": connected,
            "credentials_file_exists": credentials_exist,
            "credentials_path": GOOGLE_CREDENTIALS_PATH,
            "message": message,
        }

    async def create_kit_folder(
        self,
        client_name: str,
        reference_month: str,
        parent_folder_id: str | None = None,
    ) -> dict:
        """Cria estrutura de pastas no Google Drive para um kit.

        Estrutura:
        [parent_folder]/
          [client_name]/
            [YYYY-MM] Kit Documental/
              Funcionarios/
              Certidoes/
              Guias/

        Args:
            client_name: Nome do cliente.
            reference_month: Mes de referencia (YYYY-MM).
            parent_folder_id: ID da pasta pai no Drive (opcional).

        Returns:
            Dicionario com IDs das pastas criadas.
        """
        service = self._ensure_service()
        if not service:
            logger.info("Google Drive nao configurado, ignorando criacao de pastas")
            return {
                "configured": False,
                "message": "Google Drive nao configurado",
                "folder_ids": {},
            }

        folder_ids = {}

        try:
            # Criar pasta do cliente
            client_folder = self._create_folder(
                service,
                name=client_name,
                parent_id=parent_folder_id,
            )
            folder_ids["client"] = client_folder

            # Criar pasta do mes
            month_folder = self._create_folder(
                service,
                name=f"{reference_month} Kit Documental",
                parent_id=client_folder,
            )
            folder_ids["month"] = month_folder

            # Criar subpastas
            for subfolder_name in ["Funcionarios", "Certidoes", "Guias", "Beneficios", "Financeiro"]:  # 09/09: "Outros" virou "Financeiro" (NFS-e + boleto); "Beneficios" = VT/VR da empresa
                subfolder_id = self._create_folder(
                    service,
                    name=subfolder_name,
                    parent_id=month_folder,
                )
                folder_ids[subfolder_name.lower()] = subfolder_id

            logger.info(
                "Pastas criadas no Drive para %s [%s]: %s",
                client_name,
                reference_month,
                folder_ids,
            )

            return {
                "configured": True,
                "message": "Pastas criadas com sucesso",
                "folder_ids": folder_ids,
            }

        except Exception as e:
            logger.error("Erro ao criar pastas no Drive: %s", e)
            return {
                "configured": True,
                "message": f"Erro ao criar pastas: {str(e)}",
                "folder_ids": folder_ids,
            }

    async def upload_to_drive(
        self,
        kit_id: str,
        file_path: str,
        folder_id: str | None = None,
    ) -> dict:
        """Faz upload de um arquivo para o Google Drive.

        Args:
            kit_id: UUID do kit (para referencia).
            file_path: Caminho local do arquivo.
            folder_id: ID da pasta de destino no Drive.

        Returns:
            Dicionario com ID do arquivo e link.
        """
        service = self._ensure_service()
        if not service:
            return {
                "configured": False,
                "message": "Google Drive nao configurado",
                "file_id": None,
                "link": None,
            }

        full_path = file_path
        if not os.path.isabs(file_path):
            full_path = os.path.join(GED_STORAGE_BASE, file_path)

        if not os.path.exists(full_path):
            return {
                "configured": True,
                "message": f"Arquivo nao encontrado: {full_path}",
                "file_id": None,
                "link": None,
            }

        try:
            from googleapiclient.http import MediaFileUpload

            file_metadata = {
                "name": os.path.basename(full_path),
                "description": f"Kit documental {kit_id}",
            }
            if folder_id:
                file_metadata["parents"] = [folder_id]

            # Detectar MIME type
            mime_type = "application/pdf"
            if full_path.endswith(".zip"):
                mime_type = "application/zip"
            elif full_path.endswith(".txt"):
                mime_type = "text/plain"

            media = MediaFileUpload(full_path, mimetype=mime_type, resumable=True)

            file_result = (
                service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, webViewLink",
                )
                .execute()
            )

            file_id = file_result.get("id")
            link = file_result.get("webViewLink")

            logger.info("Arquivo enviado ao Drive: %s (id=%s)", os.path.basename(full_path), file_id)

            return {
                "configured": True,
                "message": "Upload concluido",
                "file_id": file_id,
                "link": link,
            }

        except Exception as e:
            logger.error("Erro no upload para Drive: %s", e)
            return {
                "configured": True,
                "message": f"Erro no upload: {str(e)}",
                "file_id": None,
                "link": None,
            }

    async def sync_kit_to_drive(self, kit_id: str) -> dict:
        """Sincroniza todos os documentos de um kit com o Google Drive.

        Cria a estrutura de pastas, faz upload de todos os documentos
        e atualiza o link do Drive no kit.

        Args:
            kit_id: UUID do kit.

        Returns:
            Dicionario com resumo da sincronizacao.

        Raises:
            ValueError: Se kit nao encontrado.
        """
        service = self._ensure_service()
        if not service:
            return {
                "configured": False,
                "message": "Google Drive nao configurado",
                "uploaded": 0,
                "errors": 0,
            }

        # Buscar kit e cliente
        kit_result = await self.db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))
        kit = kit_result.scalar_one_or_none()
        if not kit:
            raise ValueError(f"Kit nao encontrado: {kit_id}")

        client_result = await self.db.execute(select(GedClient).where(GedClient.id == kit.client_id))
        client = client_result.scalar_one_or_none()
        client_name = client.name if client else "cliente_desconhecido"
        parent_folder_id = client.google_drive_folder_id if client else None

        # Criar estrutura de pastas
        ref_str = kit.reference_month.strftime("%Y-%m")
        folders_result = await self.create_kit_folder(
            client_name=client_name,
            reference_month=ref_str,
            parent_folder_id=parent_folder_id,
        )

        if not folders_result.get("configured"):
            return folders_result

        folder_ids = folders_result.get("folder_ids", {})

        # Buscar documentos
        docs_result = await self.db.execute(select(KitDocument).where(KitDocument.kit_id == kit_id))
        documents = docs_result.scalars().all()

        uploaded = 0
        substituidos = 0
        errors_list = []
        ja_na_pasta: dict[str, set[str]] = {}  # 09/09: não duplica arquivo já enviado (re-sync do mesmo kit)

        ids_por_nome: dict[str, dict[str, tuple[str, str]]] = {}

        def _nomes(fid: str) -> set[str]:
            if fid not in ja_na_pasta:
                try:
                    r = service.files().list(q=f"'{fid}' in parents and trashed=false", fields="files(id,name,md5Checksum)", pageSize=500).execute()
                    ja_na_pasta[fid] = {f["name"] for f in r.get("files", [])}
                    ids_por_nome[fid] = {f["name"]: (f["id"], f.get("md5Checksum") or "") for f in r.get("files", [])}
                except Exception:  # noqa: BLE001
                    ja_na_pasta[fid] = set()
                    ids_por_nome[fid] = {}
            return ja_na_pasta[fid]

        def _md5(path: str) -> str:
            import hashlib

            h = hashlib.md5()  # noqa: S324 — só comparação com o md5Checksum do Drive
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()

        for doc in documents:
            if not doc.file_path or not os.path.exists(doc.file_path):
                continue

            # Determinar pasta de destino
            if doc.employee_id:
                # 09/09/2026 (Jordan, olhando o kit real do Villa Dei Fiori): dentro de Funcionarios, subpastas por
                # CATEGORIA — é assim que a Pyetra procura (todas as folhas de ponto num lugar, todos os
                # contracheques noutro). O nome da pessoa continua no nome do arquivo.
                cat = CATEGORIA_FUNCIONARIO.get(doc.document_type)
                if cat and folder_ids.get("funcionarios"):
                    key = f"cat:{cat}"
                    if key not in folder_ids:
                        folder_ids[key] = self._create_folder(service, name=cat, parent_id=folder_ids["funcionarios"])
                    target_folder = folder_ids[key]
                else:
                    target_folder = folder_ids.get("funcionarios")
            elif (
                doc.document_type.startswith("cnd_")
                or doc.document_type.startswith("crf_")
                or doc.document_type.startswith("cndt_")
            ):
                target_folder = folder_ids.get("certidoes")
            elif doc.document_type in ("gfip_sefip", "grf_fgts", "gps_inss", "das_simples_nacional", "guia_issqn", "dar_sefaz") \
                    or doc.document_type.startswith("dctfweb"):
                target_folder = folder_ids.get("guias")
            elif doc.document_type in ("boleto_vt_sinetram", "relatorio_vt_sinetram", "relatorio_va_solides",
                                       "comprovante_pagto_sinetram", "comprovante_pagto_solides"):
                target_folder = folder_ids.get("beneficios")
            else:
                target_folder = folder_ids.get("financeiro")

            if target_folder and os.path.basename(doc.file_path) in _nomes(target_folder):
                fid_drive, md5_drive = ids_por_nome.get(target_folder, {}).get(os.path.basename(doc.file_path), ("", ""))
                if fid_drive and md5_drive and md5_drive != _md5(doc.file_path):
                    # 09/09: mesmo nome, conteúdo novo (ex.: PDF assinado) → substitui no lugar, mesmo id/link
                    try:
                        from googleapiclient.http import MediaFileUpload

                        service.files().update(fileId=fid_drive, media_body=MediaFileUpload(doc.file_path, resumable=True)).execute()
                        substituidos += 1
                    except Exception as exc:  # noqa: BLE001
                        errors_list.append({"document": doc.document_name, "error": f"substituição falhou: {exc}"})
                uploaded += 1
                continue
            upload_result = await self.upload_to_drive(
                kit_id=kit_id,
                file_path=doc.file_path,
                folder_id=target_folder,
            )

            if upload_result.get("file_id"):
                _nomes(target_folder).add(os.path.basename(doc.file_path)) if target_folder else None
                uploaded += 1
            else:
                errors_list.append(
                    {
                        "document": doc.document_name,
                        "error": upload_result.get("message", "Erro desconhecido"),
                    }
                )

        # Atualizar link do Drive no kit
        month_folder_id = folder_ids.get("month")
        if month_folder_id:
            kit.google_drive_link = f"https://drive.google.com/drive/folders/{month_folder_id}"
            # 09/09: subir ao Drive NÃO é entregar — a entrega ao cliente é ato manual (mark_kit_sent), decisão de 08/09
            await self.db.flush()

        logger.info(
            "Sync Drive concluido para kit %s: %d enviados, %d erros",
            kit_id,
            uploaded,
            len(errors_list),
        )

        return {
            "configured": True,
            "kit_id": kit_id,
            "uploaded": uploaded,
            "substituidos": substituidos,
            "errors": len(errors_list),
            "error_details": errors_list[:10],
            "drive_link": kit.google_drive_link,
            "folder_ids": folder_ids,
        }

    async def sync_documento(self, kit_id: str, doc_id: str) -> dict:
        """09/09/2026: o kit é montado À MEDIDA que cada processo termina — assinou/pagou → o arquivo vai para a
        pasta do kit na hora, sem esperar o sync do kit inteiro. Reusa a árvore (dedup) e substitui por md5."""
        service = self._ensure_service()
        if not service:
            return {"configured": False}
        kit = (await self.db.execute(select(GedDocumentKit).where(GedDocumentKit.id == kit_id))).scalar_one_or_none()
        doc = (await self.db.execute(select(KitDocument).where(KitDocument.id == doc_id))).scalar_one_or_none()
        if not kit or not doc or not doc.file_path or not os.path.exists(doc.file_path):
            return {"configured": True, "enviado": False, "motivo": "kit/documento/arquivo ausente"}
        client = (await self.db.execute(select(GedClient).where(GedClient.id == kit.client_id))).scalar_one_or_none()
        folders = await self.create_kit_folder(client_name=client.name if client else "cliente_desconhecido",
                                               reference_month=kit.reference_month.strftime("%Y-%m"),
                                               parent_folder_id=client.google_drive_folder_id if client else None)
        fids = folders.get("folder_ids", {})
        if not fids.get("month"):
            return {"configured": True, "enviado": False, "motivo": folders.get("message")}
        if doc.employee_id:
            cat = CATEGORIA_FUNCIONARIO.get(doc.document_type, "Outros documentos")
            alvo = self._create_folder(service, name=cat, parent_id=fids["funcionarios"])
        elif doc.document_type.startswith(("cnd_", "crf_", "cndt_")):
            alvo = fids.get("certidoes")
        elif doc.document_type in ("gfip_sefip", "grf_fgts", "gps_inss", "das_simples_nacional", "guia_issqn", "dar_sefaz") or doc.document_type.startswith("dctfweb"):
            alvo = fids.get("guias")
        elif doc.document_type in ("boleto_vt_sinetram", "relatorio_vt_sinetram", "relatorio_va_solides",
                                   "comprovante_pagto_sinetram", "comprovante_pagto_solides"):
            alvo = fids.get("beneficios")
        else:
            alvo = fids.get("financeiro")
        nome_arq = os.path.basename(doc.file_path)
        r = service.files().list(q=f"'{alvo}' in parents and name='{nome_arq}' and trashed=false", fields="files(id,md5Checksum)").execute()
        from googleapiclient.http import MediaFileUpload

        existentes = r.get("files", [])
        if existentes:
            import hashlib

            with open(doc.file_path, "rb") as _fh:
                h = hashlib.md5(_fh.read()).hexdigest()  # noqa: S324 — só compara com o md5Checksum do Drive
            if existentes[0].get("md5Checksum") == h:
                return {"configured": True, "enviado": False, "motivo": "já estava igual", "file_id": existentes[0]["id"]}
            service.files().update(fileId=existentes[0]["id"], media_body=MediaFileUpload(doc.file_path, resumable=True)).execute()
            return {"configured": True, "enviado": True, "substituido": True, "file_id": existentes[0]["id"]}
        up = self.upload_to_drive(kit_id=kit_id, file_path=doc.file_path, folder_id=alvo)
        up = await up
        if not kit.google_drive_link:
            kit.google_drive_link = f"https://drive.google.com/drive/folders/{fids['month']}"
            await self.db.flush()
        return {"configured": True, "enviado": bool(up.get("file_id")), "file_id": up.get("file_id"), "motivo": up.get("message")}

    async def get_drive_link(self, file_id: str) -> dict:
        """Obtem link compartilhavel de um arquivo no Drive.

        Args:
            file_id: ID do arquivo no Google Drive.

        Returns:
            Dicionario com link e permissoes.
        """
        service = self._ensure_service()
        if not service:
            return {
                "configured": False,
                "message": "Google Drive nao configurado",
                "link": None,
            }

        try:
            # Configurar permissao de leitura para "anyone with link"
            permission = {
                "type": "anyone",
                "role": "reader",
            }
            service.permissions().create(
                fileId=file_id,
                body=permission,
            ).execute()

            # Obter link
            file_info = (
                service.files()
                .get(
                    fileId=file_id,
                    fields="webViewLink, webContentLink",
                )
                .execute()
            )

            return {
                "configured": True,
                "file_id": file_id,
                "view_link": file_info.get("webViewLink"),
                "download_link": file_info.get("webContentLink"),
            }

        except Exception as e:
            logger.error("Erro ao obter link do Drive para %s: %s", file_id, e)
            return {
                "configured": True,
                "file_id": file_id,
                "message": f"Erro: {str(e)}",
                "link": None,
            }

    # --- Metodos auxiliares internos ---

    @staticmethod
    def _create_folder(service, name: str, parent_id: str | None = None) -> str:
        """Cria uma pasta no Google Drive.

        Args:
            service: Instancia do servico Google Drive.
            name: Nome da pasta.
            parent_id: ID da pasta pai (opcional).

        Returns:
            ID da pasta criada.
        """
        # 09/09: reusa a criação com dedup do GEDEON (pasta com o mesmo nome no mesmo pai = a mesma) — antes cada
        # sync criava a árvore inteira de novo
        try:
            from modules.gdrive.services.gdrive_service import gdrive_service

            if parent_id and gdrive_service._service is service:
                fid = gdrive_service._criar_pasta(name, parent_id)
                if fid:
                    return fid
        except Exception:  # noqa: BLE001
            pass
        folder_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            folder_metadata["parents"] = [parent_id]

        folder = (
            service.files()
            .create(
                body=folder_metadata,
                fields="id",
            )
            .execute()
        )

        return folder.get("id")
