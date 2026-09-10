"""
Servico de Integracao com Google Drive.

Faz upload de kits documentais para o Google Drive, cria estrutura
de pastas e gera links compartilhaveis. Funciona de forma opcional:
se as credenciais do Drive nao estiverem configuradas, os metodos
retornam graciosamente sem erro.
"""

import logging
import os
import re

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


#: Onde moram os kits deste Drive: "GEDEON — Kits Documentais (Conecta Mais)". Não é palpite — é a pasta que
#: já guarda os 24 condomínios e onde a Pyetra procura. Sem isso, cliente sem `google_drive_folder_id` ganhava
#: uma pasta NOVA solta na raiz do Meu Drive a cada sincronização (medido em 09/09: duas do Michelangelo).
#: Em que pasta do kit cada tipo de documento da EMPRESA (employee_id IS NULL) mora.
#:
#: 10/09/2026 — o Jordan abriu a pasta Financeiro do primeiro kit real e achou lá dentro seis GUIAS
#: (DARF IRRF, DCTFWeb, EFD-Reinf, FGTS, INSS Patronal, ISS Manaus), o 13º de 2025 e NFS-e de janeiro,
#: com a pasta Guias vazia. A regra anterior nomeava SEIS tipos e mandava TODO O RESTO para Financeiro:
#:     doc.document_type in ("gfip_sefip","grf_fgts","gps_inss","das_simples_nacional","guia_issqn","dar_sefaz")
#:     or doc.document_type.startswith("dctfweb")   # <- "dctf_declaracao" não começa com "dctfweb"
#: São 78 tipos gravados no banco. Setenta e dois caíam no `else`.
#:
#: Convenção codificada à mão é a fábrica de defeito desta casa: o mapa agora é EXPLÍCITO e completo
#: contra o que existe, e tipo desconhecido não some calado — vai para Financeiro e GRITA no log, com
#: um oráculo cobrando (test_oraculo_pasta_do_documento).
PASTA_DO_TIPO: dict[str, str] = {
    # ── Certidões negativas da empresa ──────────────────────────────────────────────────
    "cnd_federal": "certidoes",
    "cnd_estadual": "certidoes",
    "cnd_municipal": "certidoes",
    "cnd_trabalhista": "certidoes",
    "cndt_trabalhista": "certidoes",
    "crf_fgts": "certidoes",
    "cnd_caixa": "certidoes",
    "cnd_receita": "certidoes",
    "cnd_rfb": "certidoes",
    "cnd_sefaz": "certidoes",
    "cnd_prefeitura": "certidoes",
    "certidao": "certidoes",
    # ── Guias de recolhimento, suas declarações e os comprovantes de pagamento ──────────
    "das_simples_nacional": "guias",
    "parcelamento_simples": "guias",
    "gps_inss": "guias",
    "grf_fgts": "guias",
    "gfip_sefip": "guias",
    "guia_issqn": "guias",
    "dar_sefaz": "guias",
    "dctfweb_declaracao": "guias",
    "dctfweb_recibo": "guias",
    "dctfweb_extrato": "guias",
    "dctfweb_resumo_creditos": "guias",
    "dctfweb_resumo_debitos": "guias",
    "dctfweb_creditos": "guias",
    "dctfweb_debitos": "guias",
    # a família "dctf_" (sem "web") é a mesma coisa com outro vocabulário — era ela que vazava
    "dctf_declaracao": "guias",
    "dctf_recibo": "guias",
    "dctf_extrato": "guias",
    "fgts_guia": "guias",
    "fgts_relatorio": "guias",
    "gfd_fgts": "guias",
    "gfd_fgts_mensal": "guias",
    "relatorio_gfd_fgts": "guias",
    "comprovante_fgts": "guias",
    "comp_pag_fgts": "guias",
    "inss_guia": "guias",
    "inss_mensal": "guias",
    # ── Benefícios: a EMPRESA comprando e distribuindo VT/VA ────────────────────────────
    "boleto_vt_sinetram": "beneficios",
    "relatorio_vt_sinetram": "beneficios",
    "relatorio_va_solides": "beneficios",
    "relatorio_pedido_va": "beneficios",
    "comprovante_pagto_sinetram": "beneficios",
    "comprovante_pagto_solides": "beneficios",
    "comp_va_solides": "beneficios",
    "comp_vt_va_combinado": "beneficios",
    "recibo_vt_va": "beneficios",
    "declaracao_vt": "beneficios",
    # ── Financeiro: o que a Conecta Mais COBRA do condomínio ────────────────────────────
    "nfse": "financeiro",
    "nfs_servico": "financeiro",
    "nota_fiscal": "financeiro",
    "boleto": "financeiro",
    "boleto_nfse": "financeiro",
    # ── Consolidados da folha: são do bloco de PESSOAL, não do financeiro ───────────────
    "folha_pagamento": "funcionarios",
    "contracheques_consolidado": "funcionarios",
    "folhas_ponto_consolidado": "funcionarios",
    "folhas_ponto": "funcionarios",
    "recibo_folha": "funcionarios",
    "decimo_terceiro": "funcionarios",
    "recibo_decimo_terceiro": "funcionarios",
    "ficha_empregado": "funcionarios",
    "comp_salario_individual": "funcionarios",
    "aso": "funcionarios",
    # os mesmos tipos existem por funcionário E consolidados; aqui só vale o consolidado
    # (employee_id IS NULL) — o por-funcionário é roteado antes, por CATEGORIA_FUNCIONARIO
    "contracheque": "funcionarios",
    "comprovante_vt": "beneficios",
    "aviso_previo_ferias": "funcionarios",
    "outros": "funcionarios",
}


RAIZ_KITS_DRIVE = os.environ.get("GDRIVE_KITS_ROOT_FOLDER_ID") or "1oigpHoCvFT-M2tm96FDvE0LvowciNLKJ"


#: nome de arquivo com carimbo de hash do coletor ("cnd_receita_61e697a58521.pdf", "dctf_recibo_072026_52d6.pdf")
_RE_NOME_DE_MAQUINA = re.compile(
    r"(?:_[0-9a-f]{12}"  # carimbo de hash do coletor: cnd_receita_61e697a58521.pdf
    r"|[_-]?\d{11,}"  # identificador cru, quase sempre o CNPJ: sefaz_am_66014833000110.pdf
    r")\.[A-Za-z0-9]+$"
)


def pasta_do_documento(document_type: str, kit_id: str = "", document_name: str = "") -> str:
    """Chave da subpasta do kit para um documento de EMPRESA. Desconhecido não some: grita e vai p/ financeiro."""
    pasta = PASTA_DO_TIPO.get(str(document_type))
    if pasta is None:
        logger.warning(
            "kit %s: tipo '%s' (%s) não está em PASTA_DO_TIPO — Financeiro por omissão",
            kit_id or "?",
            document_type,
            document_name or "?",
        )
        return "financeiro"
    return pasta


def _nome_no_drive(document_name: str | None, caminho: str) -> str:
    """Nome que o CLIENTE vê na pasta.

    09/09/2026 (1º kit REAL): os documentos vindos do coletor subiam com o nome interno do arquivo —
    `dctf_declaracao_072026_b85caae8195f.pdf` na pasta que o síndico abre. Quando o nome do arquivo carrega o
    hash do coletor, vale o `document_name` do kit ("DCTFWeb 07/2026"); nos demais, o nome do arquivo já é bom
    (o gerador escreve "Contracheque_08.2026_FULANO.pdf") e não se mexe, senão cada sync renomeia tudo.
    """
    base = os.path.basename(caminho)
    if not document_name or not _RE_NOME_DE_MAQUINA.search(base):
        return base
    ext = os.path.splitext(base)[1] or ".pdf"
    limpo = re.sub(r"[\\/:*?\"<>|]", "-", document_name).strip()
    if not limpo:
        return base
    return limpo if limpo.lower().endswith(ext.lower()) else f"{limpo}{ext}"


def _caminho_real(file_path: str | None) -> str | None:
    """Resolve o caminho do arquivo do kit, absoluto ou relativo a /app/uploads.

    09/09/2026 (1º kit REAL, Michelangelo): 16 documentos legítimos ficaram fora do Drive porque o coletor
    gravou caminho RELATIVO ("ged/kits/x.pdf") e a sincronização testava `os.path.exists` a partir do cwd.
    O arquivo existia em /app/uploads/ged/kits/x.pdf o tempo todo — sumia calado, sem erro nenhum.
    """
    if not file_path or file_path.startswith("http"):
        return None
    if os.path.isabs(file_path):
        return file_path if os.path.exists(file_path) else None
    for base in ("/app/uploads", "/app"):
        cand = os.path.join(base, file_path)
        if os.path.exists(cand):
            return cand
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
                parent_id=parent_folder_id or RAIZ_KITS_DRIVE,
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
            for subfolder_name in [
                "Funcionarios",
                "Certidoes",
                "Guias",
                "Beneficios",
                "Financeiro",
            ]:  # 09/09: "Outros" virou "Financeiro" (NFS-e + boleto); "Beneficios" = VT/VR da empresa
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
        nome_no_drive: str | None = None,
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
                "name": nome_no_drive or os.path.basename(full_path),
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
                    r = (
                        service.files()
                        .list(
                            q=f"'{fid}' in parents and trashed=false", fields="files(id,name,md5Checksum)", pageSize=500
                        )
                        .execute()
                    )
                    ja_na_pasta[fid] = {f["name"] for f in r.get("files", [])}
                    ids_por_nome[fid] = {f["name"]: (f["id"], f.get("md5Checksum") or "") for f in r.get("files", [])}
                except Exception:  # noqa: BLE001
                    ja_na_pasta[fid] = set()
                    ids_por_nome[fid] = {}
            return ja_na_pasta[fid]

        def _md5(path: str) -> str:
            import hashlib

            h = hashlib.md5(usedforsecurity=False)  # noqa: S324 — só comparação com o md5Checksum do Drive
            with open(path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            return h.hexdigest()

        for doc in documents:
            caminho = _caminho_real(doc.file_path)
            if not caminho:
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
            else:
                target_folder = folder_ids.get(pasta_do_documento(doc.document_type, kit_id, doc.document_name))

            nome_arquivo = _nome_no_drive(doc.document_name, caminho)
            if target_folder and nome_arquivo in _nomes(target_folder):
                fid_drive, md5_drive = ids_por_nome.get(target_folder, {}).get(nome_arquivo, ("", ""))
                # documento anexado à mão (comprovante oficial do banco) sobe uma vez e não é substituído depois
                if str(getattr(doc, "source_module", "")) == "manual" and fid_drive:
                    uploaded += 1
                    continue
                if fid_drive and md5_drive and md5_drive != _md5(caminho):
                    # 09/09: mesmo nome, conteúdo novo (ex.: PDF assinado) → substitui no lugar, mesmo id/link
                    try:
                        from googleapiclient.http import MediaFileUpload

                        service.files().update(
                            fileId=fid_drive, media_body=MediaFileUpload(caminho, resumable=True)
                        ).execute()
                        substituidos += 1
                    except Exception as exc:  # noqa: BLE001
                        errors_list.append({"document": doc.document_name, "error": f"substituição falhou: {exc}"})
                uploaded += 1
                continue
            upload_result = await self.upload_to_drive(
                kit_id=kit_id,
                file_path=caminho,
                folder_id=target_folder,
                nome_no_drive=nome_arquivo,
            )

            if upload_result.get("file_id"):
                _nomes(target_folder).add(nome_arquivo) if target_folder else None
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
        caminho = _caminho_real(doc.file_path) if doc else None
        if not kit or not doc or not caminho:
            return {"configured": True, "enviado": False, "motivo": "kit/documento/arquivo ausente"}
        client = (await self.db.execute(select(GedClient).where(GedClient.id == kit.client_id))).scalar_one_or_none()
        folders = await self.create_kit_folder(
            client_name=client.name if client else "cliente_desconhecido",
            reference_month=kit.reference_month.strftime("%Y-%m"),
            parent_folder_id=client.google_drive_folder_id if client else None,
        )
        fids = folders.get("folder_ids", {})
        if not fids.get("month"):
            return {"configured": True, "enviado": False, "motivo": folders.get("message")}
        if doc.employee_id:
            cat = CATEGORIA_FUNCIONARIO.get(doc.document_type, "Outros documentos")
            alvo = self._create_folder(service, name=cat, parent_id=fids["funcionarios"])
        else:
            alvo = fids.get(pasta_do_documento(doc.document_type, kit_id, doc.document_name))
        nome_arq = _nome_no_drive(doc.document_name, caminho)
        _q_nome = nome_arq.replace("\\", "\\\\").replace(
            "'", "\\'"
        )  # nome vem de texto livre: escapar para a query do Drive
        r = (
            service.files()
            .list(q=f"'{alvo}' in parents and name='{_q_nome}' and trashed=false", fields="files(id,md5Checksum)")
            .execute()
        )
        from googleapiclient.http import MediaFileUpload

        existentes = r.get("files", [])
        if existentes:
            import hashlib

            with open(caminho, "rb") as _fh:
                h = hashlib.md5(_fh.read(), usedforsecurity=False).hexdigest()  # noqa: S324 — comparação com o md5Checksum do Drive
            if existentes[0].get("md5Checksum") == h:
                return {
                    "configured": True,
                    "enviado": False,
                    "motivo": "já estava igual",
                    "file_id": existentes[0]["id"],
                }
            service.files().update(
                fileId=existentes[0]["id"], media_body=MediaFileUpload(caminho, resumable=True)
            ).execute()
            return {"configured": True, "enviado": True, "substituido": True, "file_id": existentes[0]["id"]}
        up = self.upload_to_drive(kit_id=kit_id, file_path=caminho, folder_id=alvo, nome_no_drive=nome_arq)
        up = await up
        if not kit.google_drive_link:
            kit.google_drive_link = f"https://drive.google.com/drive/folders/{fids['month']}"
            await self.db.flush()
        return {
            "configured": True,
            "enviado": bool(up.get("file_id")),
            "file_id": up.get("file_id"),
            "motivo": up.get("message"),
        }

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
