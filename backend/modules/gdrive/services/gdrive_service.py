"""
GDrive Service — Conecta PRO
Integração com Google Drive via OAuth2 (primário) ou Service Account (fallback).
Métodos: gerar_url_autorizacao, trocar_codigo_por_token, conectar_com_tokens,
         esta_conectado, verificar_conexao, garantir_estrutura_cliente,
         fazer_upload_arquivo, obter_link_pasta.
"""

import logging
import mimetypes
import os
from typing import Any

logger = logging.getLogger(__name__)

GOOGLE_CREDENTIALS_PATH = os.environ.get(
    "GOOGLE_DRIVE_CREDENTIALS",
    "/opt/conecta-pro/config/google_drive_credentials.json",
)
GED_STORAGE_BASE = os.environ.get("GED_STORAGE_PATH", "/opt/conecta-pro/storage/ged")

OAUTH2_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]
OAUTH2_CLIENT_CONFIG = {
    "web": {
        "client_id": os.environ.get("GDRIVE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GDRIVE_CLIENT_SECRET", ""),
        "redirect_uris": [os.environ.get("GDRIVE_REDIRECT_URI", "")],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

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


class GDriveService:
    """
    Serviço Google Drive — service account + fallback gracioso.
    Interface compatível com kit_drive_service.
    """

    def __init__(self) -> None:
        self._service: Any = None
        self._initialized: bool = False

    # ── CONEXÃO ───────────────────────────────────────────────────────────────

    def _init_service(self) -> bool:
        if self._initialized:
            return self._service is not None
        self._initialized = True
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build

            if not os.path.exists(GOOGLE_CREDENTIALS_PATH):
                logger.debug("GDrive: credenciais não encontradas em %s", GOOGLE_CREDENTIALS_PATH)
                return False

            creds = Credentials.from_service_account_file(
                GOOGLE_CREDENTIALS_PATH,
                scopes=["https://www.googleapis.com/auth/drive"],
            )
            self._service = build("drive", "v3", credentials=creds)
            logger.info("GDrive: serviço inicializado via service account")
            return True
        except ImportError:
            logger.debug("GDrive: google-auth não instalado")
            return False
        except Exception as exc:
            logger.warning("GDrive: erro ao inicializar: %s", exc)
            return False

    def esta_conectado(self) -> bool:
        """Verificar se o serviço Drive está conectado."""
        if self._service is not None:
            return True
        # Tentar OAuth2 do banco PRIMEIRO (antes de service account)
        try:
            import psycopg2

            raw_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
            if raw_url:
                conn = psycopg2.connect(raw_url)
                cur = conn.cursor()
                cur.execute(
                    "SELECT access_token, refresh_token, token_expiry "
                    "FROM gdrive_config WHERE is_connected = TRUE LIMIT 1"
                )
                row = cur.fetchone()
                conn.close()
                if row:
                    at, rt, exp = row
                    expiry_str = exp.isoformat() if exp else None
                    if self.conectar_com_tokens(at or "", rt or "", expiry_str):
                        return True
        except Exception as exc:
            logger.warning("GDrive esta_conectado: erro OAuth2 DB: %s", exc)
        return self._init_service()

    # ── OAUTH2 ────────────────────────────────────────────────────────────────

    def gerar_url_autorizacao(self) -> str:
        """
        Gerar URL OAuth2 para autorização do usuário.
        Jordan acessa esta URL uma vez e autoriza o acesso ao Drive.
        """
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_config(
            OAUTH2_CLIENT_CONFIG,
            scopes=OAUTH2_SCOPES,
            redirect_uri=os.environ.get("GDRIVE_REDIRECT_URI", ""),
        )
        url, _state = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        logger.info("GDrive: URL OAuth2 gerada")
        return url

    def trocar_codigo_por_token(self, code: str) -> dict:
        """
        Trocar código de autorização pelos tokens OAuth2.
        Chamado automaticamente no callback.
        """
        import os as _os

        from google_auth_oauthlib.flow import Flow

        # Necessário para evitar MismatchingStateError/ScopeChanged quando
        # Google retorna scopes extras via include_granted_scopes=true
        _os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
        # HTTPS em produção — não relaxar verificação de transporte
        _os.environ.pop("OAUTHLIB_INSECURE_TRANSPORT", None)

        flow = Flow.from_client_config(
            OAUTH2_CLIENT_CONFIG,
            scopes=OAUTH2_SCOPES,
            redirect_uri=_os.environ.get("GDRIVE_REDIRECT_URI", ""),
        )
        flow.fetch_token(code=code)
        creds = flow.credentials
        logger.info(
            "GDrive trocar_codigo: token=%s refresh=%s expiry=%s",
            "OK" if creds.token else "VAZIO",
            "OK" if creds.refresh_token else "VAZIO",
            creds.expiry,
        )
        return {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "expiry": creds.expiry.isoformat() if creds.expiry else None,
            "scopes": list(creds.scopes or []),
        }

    def conectar_com_tokens(
        self,
        access_token: str,
        refresh_token: str,
        token_expiry: str | None = None,
    ) -> bool:
        """
        Conectar via OAuth2 tokens (fluxo principal).
        Tenta service account como fallback se OAuth2 não disponível.
        """
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = Credentials(
                token=access_token,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=os.environ.get("GDRIVE_CLIENT_ID", ""),
                client_secret=os.environ.get("GDRIVE_CLIENT_SECRET", ""),
                scopes=OAUTH2_SCOPES,
            )
            self._service = build("drive", "v3", credentials=creds, cache_discovery=False)
            self._initialized = True
            logger.info("GDrive: conectado via OAuth2 tokens")
            return True
        except Exception as exc:
            logger.warning("GDrive: falha OAuth2, tentando service account: %s", exc)
            return self._init_service()

    # ── ESTRUTURA DE PASTAS ────────────────────────────────────────────────────

    def _criar_pasta(
        self,
        nome: str,
        parent_id: str | None = None,
    ) -> str | None:
        """Criar pasta no Drive; retorna o ID ou None em erro."""
        if not self._service:
            return None
        try:
            meta: dict[str, Any] = {
                "name": nome,
                "mimeType": "application/vnd.google-apps.folder",
            }
            if parent_id:
                meta["parents"] = [parent_id]
            # Verificar se já existe
            q = f"name='{nome}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            if parent_id:
                q += f" and '{parent_id}' in parents"
            result = self._service.files().list(q=q, fields="files(id)").execute()
            files = result.get("files", [])
            if len(files) == 1:
                return files[0]["id"]
            if len(files) > 1:
                # DUPLICADOS (ex.: criados por erro SSL transitório numa montagem): escolhe o
                # de MAIS conteúdo — nunca resolve pra uma pasta vazia. Conta a subárvore.
                def _conteudo(fid: str, prof: int = 0) -> int:
                    if prof > 3:
                        return 0
                    try:
                        ch = (
                            self._service.files()
                            .list(q=f"'{fid}' in parents and trashed=false", fields="files(id,mimeType)")
                            .execute()
                            .get("files", [])
                        )
                    except Exception:
                        return 0
                    total = 0
                    for c in ch:
                        if c.get("mimeType") == "application/vnd.google-apps.folder":
                            total += _conteudo(c["id"], prof + 1)
                        else:
                            total += 1
                    return total

                return max(files, key=lambda f: _conteudo(f["id"]))["id"]
            folder = self._service.files().create(body=meta, fields="id").execute()
            return folder.get("id")
        except Exception as exc:
            logger.warning("GDrive._criar_pasta(%s): %s", nome, exc)
            return None

    def _nome_pasta_mes(self, competencia: str) -> str:
        try:
            ano, mes = competencia.split("-")
            return f"{competencia} — {MESES_PT.get(mes, mes)} {ano}"
        except Exception:
            return competencia

    def garantir_estrutura_cliente(
        self,
        client_name: str,
        competencia: str,
        root_folder_id: str | None = None,
    ) -> tuple[str | None, str | None]:
        """
        Garantir existência de [cliente]/[competência].
        Retorna (client_folder_id, month_folder_id).
        """
        if not self._service:
            return None, None
        client_folder = self._criar_pasta(client_name, root_folder_id)
        if not client_folder:
            return None, None
        month_folder = self._criar_pasta(self._nome_pasta_mes(competencia), client_folder)
        return client_folder, month_folder

    # ── LISTAGEM / DOWNLOAD ──────────────────────────────────────────────────

    def listar_arquivos(self, folder_id: str) -> list[dict[str, Any]]:
        """Lista filhos diretos de uma pasta (arquivos e subpastas), sem lixeira.

        Retorna [{id, name, mimeType, modifiedTime, size}]. Vazio em falha (gracioso).
        """
        if not self._service:
            return []
        try:
            out: list[dict[str, Any]] = []
            token = None
            while True:
                resp = (
                    self._service.files()
                    .list(
                        q=f"'{folder_id}' in parents and trashed=false",
                        fields="nextPageToken, files(id,name,mimeType,modifiedTime,size)",
                        pageSize=200,
                        pageToken=token,
                    )
                    .execute()
                )
                out.extend(resp.get("files", []))
                token = resp.get("nextPageToken")
                if not token:
                    break
            return out
        except Exception as exc:
            logger.warning("GDrive.listar_arquivos(%s): %s", folder_id, exc)
            return []

    def baixar_arquivo(self, file_id: str, dest_path: str) -> bool:
        """Baixa um arquivo binário do Drive para dest_path. False em falha (gracioso)."""
        if not self._service:
            return False
        try:
            import io

            from googleapiclient.http import MediaIoBaseDownload

            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            request = self._service.files().get_media(fileId=file_id)
            buf = io.BytesIO()
            downloader = MediaIoBaseDownload(buf, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            with open(dest_path, "wb") as f:
                f.write(buf.getvalue())
            return True
        except Exception as exc:
            logger.warning("GDrive.baixar_arquivo(%s): %s", file_id, exc)
            return False

    # ── UPLOAD ────────────────────────────────────────────────────────────────

    def fazer_upload_arquivo(
        self,
        file_path: str,
        folder_id: str,
        file_name: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Upload de um arquivo para o Drive.
        Retorna dict {"id": ..., "webViewLink": ...} ou None.
        """
        if not self._service:
            return None
        full_path = file_path if os.path.isabs(file_path) else os.path.join(GED_STORAGE_BASE, file_path)
        if not os.path.exists(full_path):
            logger.warning("GDrive: arquivo não encontrado: %s", full_path)
            return None
        try:
            from googleapiclient.http import MediaFileUpload

            name = file_name or os.path.basename(full_path)
            mime, _ = mimetypes.guess_type(full_path)
            mime = mime or "application/octet-stream"
            meta: dict[str, Any] = {"name": name, "parents": [folder_id]}
            media = MediaFileUpload(full_path, mimetype=mime, resumable=True)
            result = self._service.files().create(body=meta, media_body=media, fields="id,webViewLink,name").execute()
            return result
        except Exception as exc:
            logger.warning("GDrive.fazer_upload_arquivo(%s): %s", full_path, exc)
            return None

    # ── COMPARTILHAMENTO ──────────────────────────────────────────────────────

    def obter_link_pasta(
        self,
        folder_id: str,
        tornar_publico: bool = True,
    ) -> str | None:
        """Obter link compartilhável da pasta; opcionalmente tornar pública."""
        if not self._service:
            return None
        try:
            if tornar_publico:
                self._service.permissions().create(
                    fileId=folder_id,
                    body={"type": "anyone", "role": "reader"},
                ).execute()
            meta = self._service.files().get(fileId=folder_id, fields="webViewLink").execute()
            return meta.get("webViewLink")
        except Exception as exc:
            logger.warning("GDrive.obter_link_pasta(%s): %s", folder_id, exc)
            return None

    def verificar_conexao(self) -> dict:
        """Verificar status da conexão com o Drive (retorna info do usuário)."""
        if not self._service:
            return {
                "conectado": False,
                "mensagem": "Não autorizado — acesse /api/v1/gdrive/autorizar",
            }
        try:
            about = self._service.about().get(fields="user,storageQuota").execute()
            user = about.get("user", {})
            quota = about.get("storageQuota", {})
            return {
                "conectado": True,
                "email": user.get("emailAddress", ""),
                "nome": user.get("displayName", ""),
                "storage_usado": quota.get("usage", "0"),
                "storage_total": quota.get("limit", "0"),
            }
        except Exception as exc:
            logger.error("GDrive: erro verificar conexão: %s", exc)
            return {"conectado": False, "erro": str(exc)}

    def check_status(self) -> dict[str, Any]:
        """Retornar status da configuração do GDrive.
        Prioridade: (1) serviço já em memória, (2) OAuth2 tokens no banco, (3) service account.
        """
        if self._service:
            return self.verificar_conexao()

        # Prioridade 2: OAuth2 tokens salvos no banco (gdrive_config)
        try:
            import psycopg2

            raw_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
            if raw_url:
                conn = psycopg2.connect(raw_url)
                cur = conn.cursor()
                cur.execute(
                    "SELECT owner_email, access_token, refresh_token, token_expiry "
                    "FROM gdrive_config WHERE is_connected = TRUE LIMIT 1"
                )
                row = cur.fetchone()
                conn.close()
                if row:
                    email, at, rt, exp = row
                    expiry_str = exp.isoformat() if exp else None
                    ok = self.conectar_com_tokens(at or "", rt or "", expiry_str)
                    if ok:
                        logger.info("GDrive: conectado via OAuth2 tokens do banco (%s)", email)
                        return {
                            "conectado": True,
                            "email": email,
                            "nome": email,
                            "tipo": "oauth2",
                            "fonte": "banco",
                            "token_expiry": expiry_str,
                            "mensagem": f"Google Drive conectado via OAuth2 ({email})",
                        }
        except Exception as exc:
            logger.warning("GDrive check_status: erro ao ler gdrive_config: %s", exc)

        # Prioridade 3: service account (arquivo JSON)
        connected = self._init_service()
        return {
            "configurado": connected,
            "credentials_path": GOOGLE_CREDENTIALS_PATH,
            "credentials_existem": os.path.exists(GOOGLE_CREDENTIALS_PATH),
            "mensagem": (
                "Google Drive conectado via service account"
                if connected
                else f"Credenciais não encontradas em {GOOGLE_CREDENTIALS_PATH}"
            ),
        }


# Singleton global
gdrive_service = GDriveService()
