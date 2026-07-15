"""
Universal Signature Service — Motor central de assinatura eletrônica.

Encapsula a criação de solicitações de assinatura, a coleta das assinaturas
(por funcionário, empresa ou cliente via link), a consulta de status por
documento e a verificação de integridade por hash.

Persistência única:
- `sig_signature_requests`  — 1 linha por (documento × signatário) exigido.
- `sig_signatures`          — 1 linha por assinatura efetivamente coletada.

Assinatura eletrônica SIMPLES (nível legal "eletrônica" da MP 2.200-2/ICP-Brasil,
art. 10 §2º — validade por acordo entre partes):
    hash = SHA-256( doc_hash|document_type|document_id|signer_type|signer_key
                    |timestamp_iso|secret )
As evidências (IP, user-agent, timestamp em America/Manaus, PIN/token) compõem a
trilha de auditoria (`audit_log`) que confere não-repúdio.

Assinatura QUALIFICADA ICP-Brasil (certificado A1): ver
`_apply_qualified_signature`. Assina o PDF do contrato em PAdES com o A1 da
empresa (CNPJ 35.710.481/0001-03, AC SOLUTI/ICP-Brasil) — fé pública. Só a
EMPRESA (COMPANY) assina em nível QUALIFIED; funcionário/cliente seguem SIMPLE.
A mecânica criptográfica fica em `qualified_signer.py` (pyhanko/PAdES); a senha
do .p12 vem só da env CERT_A1_PASSWORD.

TZ: todos os timestamps de evidência são gravados no fuso America/Manaus
(o servidor roda nesse fuso); as colunas DateTime armazenam naive local Manaus,
padrão já adotado no restante do ERP (ponto, folha, SST).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ai.signature.models.signature import (
    Signature,
    SignatureSource,
    SignatureStatus,
    SignatureType,
)
from modules.ai.signature.models.signature_request import (
    RequestStatus,
    SignatureRequest,
)

logger = logging.getLogger(__name__)

MANAUS_TZ = ZoneInfo("America/Manaus")

# Organização única do ERP (não há multi-tenancy real). tenant_id é NOT NULL nas
# tabelas sig_*, então usamos um UUID fixo determinístico como "a empresa".
DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

# --------------------------------------------------------------------------- #
# HISTÓRICO × CORRENTE (M2) — classificação de solicitações pendentes.
#
# O retroativo dos kits criou ~1131 pedidos de assinatura de meses passados
# (contracheque 03..06/2026, folha de ponto, comprovantes VT/VA/VR, além de
# eventos como férias/rescisão/contrato). O funcionário NÃO deve ser confrontado
# com um "paredão" obrigatório de 16-23 assinaturas de competências antigas.
#
# Uma solicitação é HISTÓRICA/OPCIONAL (não entra na pilha obrigatória) quando:
#   1) sua COMPETÊNCIA (mês a que o documento se refere, lida do título/nome/
#      reference_code no formato MM/AAAA ou AAAA-MM) é ANTERIOR ao mês corrente; OU
#   2) não há competência legível MAS foi criada no LOTE RETROATIVO — isto é, até
#      o instante de virada abaixo (eventos como férias/rescisão do batch antigo).
# Documentos novos daqui pra frente (criados após o cutoff, competência corrente)
# entram normalmente em "a assinar agora". Nada é apagado — só reclassificado.
#
# Reversível/ajustável por env, sem migração de banco (computado em tempo de
# leitura). O default = dia seguinte ao lote retroativo dos kits (2026-07-11).
RETROATIVO_CUTOFF_DEFAULT = "2026-07-12T00:00:00"

# Competência MM/AAAA (aceita separador / . -) e AAAA-MM. Bordas de dígito para
# não casar pedaços de outras sequências numéricas.
_COMP_MMYYYY = re.compile(r"(?<!\d)(0?[1-9]|1[0-2])[/.\-](20\d{2})(?!\d)")
_COMP_YYYYMM = re.compile(r"(?<!\d)(20\d{2})[/.\-](0[1-9]|1[0-2])(?!\d)")


def _retroativo_cutoff() -> datetime:
    """Instante de virada M2 (naive local Manaus). Configurável por env."""
    raw = os.getenv("ASSINATURA_RETROATIVO_CUTOFF", RETROATIVO_CUTOFF_DEFAULT)
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.fromisoformat(RETROATIVO_CUTOFF_DEFAULT)


def _competencia_de(texto: Any) -> tuple[int, int] | None:
    """Extrai (ano, mês) de um texto com competência MM/AAAA ou AAAA-MM; None se não houver."""
    if not texto:
        return None
    s = str(texto)
    m = _COMP_MMYYYY.search(s)
    if m:
        return (int(m.group(2)), int(m.group(1)))
    m = _COMP_YYYYMM.search(s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def _now_manaus() -> datetime:
    """Retorna agora no fuso America/Manaus como datetime naive (padrão do ERP)."""
    return datetime.now(MANAUS_TZ).replace(tzinfo=None)


def _get_signature_secret() -> str:
    """Secret para o hash. Reusa PORTAL_SIGNATURE_SECRET (mesmo do fluxo EPI)."""
    secret = os.getenv("PORTAL_SIGNATURE_SECRET")
    if not secret:
        raise RuntimeError(
            "Variavel de ambiente PORTAL_SIGNATURE_SECRET nao definida. "
            "Defina em .env antes de iniciar o servidor."
        )
    return secret


class SignerType(StrEnum):
    """Tipos de assinante suportados pelo motor universal."""

    EMPLOYEE = "employee"  # Funcionário — assina pelo Portal do Funcionário
    COMPANY = "company"  # Empresa — Jordan/Pyetra pelo painel admin
    CUSTOMER = "customer"  # Cliente — assina por link seguro (token único)


class SignatureLevel(StrEnum):
    """Nível legal da assinatura."""

    SIMPLE = "simple"  # Eletrônica simples (SHA-256 + evidências) — implementado
    QUALIFIED = "qualified"  # Qualificada ICP-Brasil (A1/A3) — gancho, futuro


@dataclass
class SignerInput:
    """Definição de um signatário exigido numa solicitação.

    Attributes:
        signer_type: EMPLOYEE, COMPANY ou CUSTOMER.
        signer_name: Nome do signatário (obrigatório).
        signer_id: UUID do funcionário (employees.id) ou do usuário admin.
            Opcional para CUSTOMER (assina por link, sem conta).
        signer_email: E-mail — usado para notificar / enviar link ao cliente.
        signer_phone: Telefone (opcional).
        signer_document: CPF/CNPJ do signatário (opcional, evidência).
        order: Ordem no fluxo multi-assinatura (1-based). Default 1.
    """

    signer_type: SignerType
    signer_name: str
    signer_id: uuid.UUID | None = None
    signer_email: str | None = None
    signer_phone: str | None = None
    signer_document: str | None = None
    order: int = 1


@dataclass
class SignatureEvidence:
    """Evidências capturadas no ato da assinatura (trilha de auditoria)."""

    ip_address: str | None = None
    user_agent: str | None = None
    device: str | None = None
    location: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class UniversalSignatureService:
    """Motor central de assinatura eletrônica multi-signatário.

    Uso típico (para o agente dos geradores de PDF):

        svc = UniversalSignatureService(db)
        req = await svc.criar_solicitacao_assinatura(
            document_type="contract",
            document_id="<uuid-do-contrato>",
            signers=[SignerInput(SignerType.COMPANY, "Conecta Mais Eletronica",
                                 signer_id=admin_user_id)],
            title="Contrato de Prestação de Serviços - Cliente X",
            document_hash=sha256_do_pdf,          # opcional mas recomendado
            requested_by=admin_user_id,
        )
        # -> req["requests"][0]["id"], e para CUSTOMER: req["requests"][i]["public_token"]

    Attributes:
        db: Sessão async do SQLAlchemy.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # 1) CRIAR SOLICITAÇÃO
    # ------------------------------------------------------------------ #
    async def criar_solicitacao_assinatura(
        self,
        *,
        document_type: str,
        document_id: str,
        signers: list[SignerInput],
        title: str,
        document_name: str | None = None,
        document_path: str | None = None,
        document_hash: str | None = None,
        requested_by: uuid.UUID | None = None,
        requested_by_name: str | None = None,
        purpose: str = "signature",
        expires_in_days: int | None = 30,
        reference_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Cria uma solicitação de assinatura para 1..N signatários.

        Gera uma linha em `sig_signature_requests` por signatário exigido.
        Para signatários do tipo CUSTOMER, gera um `access_token` (link único)
        e um `access_code` (PIN de 6 dígitos) para verificação.

        Args:
            document_type: Tipo do documento (ex.: "contract", "proposal",
                "payslip", "ficha_epi", "service_order"). Livre — o motor não
                restringe.
            document_id: ID do documento (string; UUID ou id textual).
            signers: Lista de SignerInput (>= 1).
            title: Título humano da solicitação (aparece no painel/link).
            document_name: Nome de exibição do documento (default = title).
            document_path: Caminho do PDF gerado (opcional).
            document_hash: SHA-256 do conteúdo do PDF (recomendado — garante
                integridade: se o PDF mudar, a verificação acusa).
            requested_by: UUID de quem solicitou (admin). Se None, usa o
                DEFAULT_TENANT_ID como placeholder (coluna é NOT NULL).
            requested_by_name: Nome de quem solicitou.
            purpose: Propósito (livre; ex. "signature", "approval").
            expires_in_days: Validade do link/solicitação (None = sem expiração).
            reference_code: Código externo de referência (opcional).
            metadata: Dados extras persistidos em extra_data.

        Returns:
            Dict com:
              - request_group_id: id da 1ª request (âncora do grupo)
              - document_type, document_id
              - total_signers
              - requests: lista de dicts, um por signatário, cada um com
                {id, signer_type, signer_name, order, status,
                 public_token (só CUSTOMER), public_pin (só CUSTOMER)}

        Raises:
            ValueError: Se signers vazio ou signer_name ausente.
        """
        if not signers:
            raise ValueError("É necessário ao menos um signatário (signers vazio).")

        now = _now_manaus()
        expires_at = None
        if expires_in_days is not None:
            from datetime import timedelta

            expires_at = now + timedelta(days=expires_in_days)

        requested_by_uuid = requested_by or DEFAULT_TENANT_ID
        parent_id: uuid.UUID | None = None
        created: list[dict[str, Any]] = []

        for idx, signer in enumerate(sorted(signers, key=lambda s: s.order)):
            if not signer.signer_name:
                raise ValueError("signer_name é obrigatório para cada signatário.")

            req = SignatureRequest(
                id=uuid.uuid4(),
                tenant_id=DEFAULT_TENANT_ID,
                title=title,
                description=None,
                reference_code=reference_code,
                status=RequestStatus.PENDING,
                document_id=self._coerce_doc_uuid(document_id),
                document_type=document_type,
                document_name=document_name or title,
                document_path=document_path,
                document_hash=document_hash,
                signer_id=signer.signer_id,
                signer_type=str(signer.signer_type),
                signer_name=signer.signer_name,
                signer_email=signer.signer_email,
                signer_phone=signer.signer_phone,
                signer_document=signer.signer_document,
                signature_order=signer.order,
                total_signers=len(signers),
                parent_request_id=parent_id,
                expires_at=expires_at,
                due_date=expires_at,
                requires_authentication=signer.signer_type != SignerType.CUSTOMER,
                requested_by=requested_by_uuid,
                requested_by_name=requested_by_name,
                created_at=now,
                updated_at=now,
                extra_data=metadata,
                # guardamos o document_id original (string) sempre no extra_data,
                # pois nem todo document_id é UUID.
                custom_fields={"document_id_raw": str(document_id)},
            )

            # CLIENTE assina por link: token único + PIN
            if signer.signer_type == SignerType.CUSTOMER:
                req.access_token = secrets.token_urlsafe(32)
                req.access_code = f"{secrets.randbelow(1_000_000):06d}"

            self.db.add(req)
            # a 1ª request vira âncora (parent) das demais
            if idx == 0:
                parent_id = req.id

            entry: dict[str, Any] = {
                "id": str(req.id),
                "signer_type": str(signer.signer_type),
                "signer_name": signer.signer_name,
                "order": signer.order,
                "status": str(RequestStatus.PENDING),
            }
            if signer.signer_type == SignerType.CUSTOMER:
                entry["public_token"] = req.access_token
                entry["public_pin"] = req.access_code
            created.append(entry)

        await self.db.commit()

        logger.info(
            "Solicitação de assinatura criada: doc_type=%s doc_id=%s signers=%d group=%s",
            document_type,
            document_id,
            len(signers),
            parent_id,
        )

        # GATILHO M1: avisa no sino do Portal cada FUNCIONÁRIO signatário de que há
        # documento para assinar. À prova de falha (sessão própria, erros engolidos):
        # notificar NUNCA pode quebrar a criação da solicitação de assinatura.
        try:
            from modules.signatures.helpers.notificar_assinatura_pendente import (
                notificar_assinatura_pendente_para_employees,
            )

            await notificar_assinatura_pendente_para_employees(
                signers, document_type=document_type, title=title
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Falha ao disparar notificação de assinatura pendente (doc_type=%s): %s",
                document_type,
                exc,
            )

        return {
            "request_group_id": str(parent_id),
            "document_type": document_type,
            "document_id": str(document_id),
            "total_signers": len(signers),
            "requests": created,
        }

    # ------------------------------------------------------------------ #
    # 2) ASSINAR
    # ------------------------------------------------------------------ #
    async def assinar(
        self,
        *,
        request_id: uuid.UUID,
        signer_type: SignerType,
        signer_id: uuid.UUID | None = None,
        signer_name: str | None = None,
        signer_document: str | None = None,
        evidence: SignatureEvidence | None = None,
        level: SignatureLevel = SignatureLevel.SIMPLE,
        certificate_ref: dict[str, Any] | None = None,
        pdf_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Coleta a assinatura de um signatário numa solicitação.

        Gera a linha em `sig_signatures` (hash SHA-256 + evidências), vincula à
        request, e marca a request como SIGNED/COMPLETED.

        Args:
            request_id: UUID da linha em sig_signature_requests a assinar.
            signer_type: Deve casar com o signer_type da request.
            signer_id: UUID do assinante (funcionário/admin). Ignorado p/ cliente.
            signer_name: Nome (fallback ao da request).
            signer_document: CPF/CNPJ (evidência; fallback ao da request).
            evidence: IP, user-agent, device, location.
            level: SIMPLE (eletrônica simples) ou QUALIFIED (ICP-Brasil A1).
                QUALIFIED só é aceito para signer_type=COMPANY (titular do cert).
            certificate_ref: Referências p/ QUALIFIED (ex.: {"pdf_path": "..."}).
            pdf_bytes: Bytes do PDF do contrato (obrigatório p/ QUALIFIED quando não
                houver document_path/pdf_path). Ignorado em nível SIMPLE.

        Returns:
            Dict com signature_id, signature_hash, signed_at (ISO Manaus),
            request_status, group_completed (bool). Em QUALIFIED, inclui ainda
            level, icp_brasil, signed_document_path e certificate{...}.

        Raises:
            ValueError: request inexistente, já assinada, tipo divergente,
                solicitação expirada, ou QUALIFIED por não-COMPANY / sem PDF.
            QualifiedSignatureError: cert vencido, CERT_A1_PASSWORD ausente ou
                .p12 indisponível (assinatura qualificada).
        """
        req = await self._get_request(request_id)
        if req is None:
            raise ValueError(f"Solicitação {request_id} não encontrada.")

        if req.status in (RequestStatus.SIGNED, RequestStatus.COMPLETED):
            raise ValueError(f"Solicitação {request_id} já está assinada.")
        if req.status in (RequestStatus.CANCELLED, RequestStatus.REJECTED):
            raise ValueError(f"Solicitação {request_id} está {req.status} e não pode ser assinada.")
        if req.is_expired:
            req.status = RequestStatus.EXPIRED
            await self.db.commit()
            raise ValueError(f"Solicitação {request_id} expirou.")

        if str(req.signer_type) != str(signer_type):
            raise ValueError(
                f"Tipo de assinante divergente: solicitação exige "
                f"'{req.signer_type}', recebido '{signer_type}'."
            )

        signed_at = _now_manaus()
        eff_name = signer_name or req.signer_name
        eff_doc = signer_document or req.signer_document

        if level == SignatureLevel.QUALIFIED:
            # Assinatura QUALIFICADA ICP-Brasil (A1) — PAdES embutido no PDF.
            # Exclusiva da EMPRESA (COMPANY), titular do certificado.
            return await self._apply_qualified_signature(
                req=req,
                signer_type=signer_type,
                signer_id=signer_id,
                signer_name=eff_name,
                certificate_ref=certificate_ref,
                signed_at=signed_at,
                evidence=evidence,
                pdf_bytes=pdf_bytes,
            )

        # Assinatura eletrônica SIMPLES
        signer_key = str(signer_id) if signer_id else (eff_doc or eff_name or str(req.id))
        signature_hash = self._generate_hash(
            document_hash=req.document_hash,
            document_type=req.document_type or "",
            document_id=str(req.document_id or (req.custom_fields or {}).get("document_id_raw", "")),
            signer_type=str(signer_type),
            signer_key=signer_key,
            timestamp=signed_at,
        )

        ev = evidence or SignatureEvidence()

        sig = Signature(
            id=uuid.uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            owner_id=signer_id,
            owner_type=str(signer_type),
            owner_name=eff_name,
            owner_document=eff_doc,
            signature_type=SignatureType.ELECTRONIC,
            status=SignatureStatus.VERIFIED,
            source=SignatureSource.API,
            hash_algorithm="SHA-256",
            signature_hash=signature_hash,
            is_verified=True,
            verified_at=signed_at,
            is_active=True,
            capture_ip=ev.ip_address,
            capture_device=ev.device,
            capture_user_agent=ev.user_agent,
            capture_location=ev.location,
            created_at=signed_at,
            updated_at=signed_at,
            created_by=signer_id,
            extra_data={"level": str(level), **(ev.extra or {})},
        )
        self.db.add(sig)
        await self.db.flush()  # garante sig.id

        # Vincula à request e marca como assinada
        req.signature_id = sig.id
        req.signed_at = signed_at
        req.status = RequestStatus.SIGNED
        req.signing_ip = ev.ip_address
        req.signing_user_agent = ev.user_agent
        req.signing_device = ev.device
        req.signing_location = ev.location
        req.signed_document_hash = req.document_hash
        req.updated_at = signed_at
        req.last_activity_at = signed_at
        req.audit_log = self._append_audit(
            req.audit_log,
            action="signed",
            at=signed_at,
            signer_type=str(signer_type),
            signer_name=eff_name,
            ip=ev.ip_address,
            signature_hash=signature_hash,
        )

        # Grupo completo? (todos os signatários do mesmo documento assinaram)
        group_completed = await self._maybe_complete_group(req)

        # Persiste a assinatura ANTES de qualquer efeito colateral. Assim uma falha
        # do hook (DB/loop/constraint) NÃO pode desfazer a assinatura — o hook roda
        # depois, com commit/rollback próprios.
        await self.db.commit()

        # Hook pós-assinatura por tipo de documento (fire-and-forget, nunca quebra).
        await self._pos_assinatura_hook(req, signed_at)

        logger.info(
            "Documento assinado: request=%s signer_type=%s hash=%s group_completed=%s",
            request_id,
            signer_type,
            signature_hash[:16],
            group_completed,
        )

        return {
            "signature_id": str(sig.id),
            "signature_hash": signature_hash,
            "signed_at": signed_at.isoformat(),
            "request_status": str(req.status),
            "group_completed": group_completed,
        }

    async def assinar_por_token(
        self,
        *,
        access_token: str,
        access_code: str | None = None,
        signer_name: str | None = None,
        signer_document: str | None = None,
        evidence: SignatureEvidence | None = None,
    ) -> dict[str, Any]:
        """Assina uma solicitação de CLIENTE via link seguro (token de uso único).

        Args:
            access_token: Token do link público.
            access_code: PIN de 6 dígitos (se a request exigir; obrigatório).
            signer_name: Nome informado pelo cliente (fallback ao da request).
            signer_document: CPF/CNPJ informado (evidência).
            evidence: IP/user-agent/device.

        Returns:
            Mesmo payload de `assinar`.

        Raises:
            ValueError: token inválido, PIN incorreto, já assinado ou expirado.
        """
        req = await self._get_request_by_token(access_token)
        if req is None:
            raise ValueError("Link de assinatura inválido.")
        if req.access_code:
            import secrets as _secrets

            # comparação em tempo CONSTANTE (evita timing attack no PIN de 6 dígitos)
            if not _secrets.compare_digest(str(access_code or ""), str(req.access_code)):
                raise ValueError("PIN de verificação incorreto.")

        return await self.assinar(
            request_id=req.id,
            signer_type=SignerType.CUSTOMER,
            signer_id=None,
            signer_name=signer_name,
            signer_document=signer_document,
            evidence=evidence,
        )

    # ------------------------------------------------------------------ #
    # 3) STATUS POR DOCUMENTO
    # ------------------------------------------------------------------ #
    async def status(
        self,
        *,
        document_type: str,
        document_id: str,
    ) -> dict[str, Any]:
        """Retorna o status de assinatura de um documento (todos os signatários).

        Args:
            document_type: Tipo do documento.
            document_id: ID do documento.

        Returns:
            Dict com document_type/document_id, status_geral
            (pending|partial|completed|none), total_signers, signed_count e a
            lista `signatarios` com o estado de cada um.
        """
        reqs = await self._get_requests_for_document(document_type, document_id)
        if not reqs:
            return {
                "document_type": document_type,
                "document_id": str(document_id),
                "status_geral": "none",
                "total_signers": 0,
                "signed_count": 0,
                "signatarios": [],
            }

        signatarios = []
        signed_count = 0
        for r in reqs:
            is_signed = r.status in (RequestStatus.SIGNED, RequestStatus.COMPLETED)
            if is_signed:
                signed_count += 1
            signatarios.append(
                {
                    "request_id": str(r.id),
                    "signer_type": r.signer_type,
                    "signer_name": r.signer_name,
                    "order": r.signature_order,
                    "status": str(r.status),
                    "signed_at": r.signed_at.isoformat() if r.signed_at else None,
                    "signature_hash": None,  # preenchido abaixo se assinado
                    "signature_id": str(r.signature_id) if r.signature_id else None,
                    # metadados preenchidos abaixo se assinado (nível/certificado ICP-Brasil)
                    "level": None,
                    "signature_type": None,
                    "certificate_issuer": None,
                    "certificate_serial": None,
                    "certificate_valid_to": None,
                }
            )

        # completa hash + metadados de cada assinatura coletada, se houver
        sig_ids = [r.signature_id for r in reqs if r.signature_id]
        if sig_ids:
            sig_map = await self._signatures_for(sig_ids)
            for s in signatarios:
                info = sig_map.get(s["signature_id"]) if s["signature_id"] else None
                if info:
                    s.update(info)

        total = len(reqs)
        if signed_count == 0:
            status_geral = "pending"
        elif signed_count < total:
            status_geral = "partial"
        else:
            status_geral = "completed"

        return {
            "document_type": document_type,
            "document_id": str(document_id),
            "status_geral": status_geral,
            "total_signers": total,
            "signed_count": signed_count,
            "signatarios": signatarios,
        }

    # ------------------------------------------------------------------ #
    # 4) VERIFICAR HASH
    # ------------------------------------------------------------------ #
    async def verificar(self, signature_hash: str) -> dict[str, Any]:
        """Verifica a validade/autenticidade de uma assinatura pelo hash.

        Args:
            signature_hash: Hash SHA-256 emitido no ato da assinatura.

        Returns:
            Dict com is_valid e, se encontrada, os dados do signatário e do
            documento vinculado.
        """
        query = select(Signature).where(Signature.signature_hash == signature_hash)
        result = await self.db.execute(query)
        sig = result.scalar_one_or_none()

        if not sig:
            return {
                "is_valid": False,
                "reason": "Assinatura não encontrada.",
                "signature_hash": signature_hash,
            }

        # request vinculada (documento)
        rq = await self.db.execute(
            select(SignatureRequest).where(SignatureRequest.signature_id == sig.id)
        )
        req = rq.scalar_one_or_none()

        return {
            "is_valid": bool(sig.is_valid),
            "signature_hash": signature_hash,
            "signer_type": sig.owner_type,
            "signer_name": sig.owner_name,
            "signer_document": sig.owner_document,
            "signed_at": sig.verified_at.isoformat() if sig.verified_at else None,
            "hash_algorithm": sig.hash_algorithm,
            "level": (sig.extra_data or {}).get("level") if sig.extra_data else None,
            "document_type": req.document_type if req else None,
            "document_id": (
                str(req.document_id) if req and req.document_id
                else (req.custom_fields or {}).get("document_id_raw") if req else None
            ),
            "document_hash": req.document_hash if req else None,
            "status": str(req.status) if req else None,
        }

    async def invalidar(self, signature_hash: str, reason: str) -> bool:
        """Invalida (revoga) uma assinatura pelo hash.

        Args:
            signature_hash: Hash da assinatura.
            reason: Motivo da revogação.

        Returns:
            True se revogada; False se não encontrada.
        """
        result = await self.db.execute(
            select(Signature).where(Signature.signature_hash == signature_hash)
        )
        sig = result.scalar_one_or_none()
        if not sig:
            return False
        sig.is_active = False
        sig.status = SignatureStatus.REVOKED
        sig.notes = f"Revogada: {reason}"
        sig.updated_at = _now_manaus()
        await self.db.commit()
        logger.info("Assinatura revogada: hash=%s motivo=%s", signature_hash[:16], reason)
        return True

    # ------------------------------------------------------------------ #
    # Helpers internos
    # ------------------------------------------------------------------ #
    def _generate_hash(
        self,
        *,
        document_hash: str | None,
        document_type: str,
        document_id: str,
        signer_type: str,
        signer_key: str,
        timestamp: datetime,
    ) -> str:
        """Gera o hash SHA-256 da assinatura (doc + signatário + tempo + secret)."""
        payload = (
            f"{document_hash or ''}|{document_type}|{document_id}|"
            f"{signer_type}|{signer_key}|{timestamp.isoformat()}|"
            f"{_get_signature_secret()}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    async def _apply_qualified_signature(
        self,
        *,
        req: SignatureRequest,
        signer_type: SignerType,
        signer_id: uuid.UUID | None,
        signer_name: str | None,
        certificate_ref: dict[str, Any] | None,
        signed_at: datetime,
        evidence: SignatureEvidence | None = None,
        pdf_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Assinatura QUALIFICADA ICP-Brasil (certificado A1) — PAdES no PDF.

        Só a EMPRESA (COMPANY) assina em nível QUALIFIED: é a titular do
        certificado A1 (CNPJ 35.710.481/0001-03). Funcionário e cliente NÃO têm
        certificado próprio — assinam sempre em nível SIMPLE.

        Fluxo:
          1. Obtém os bytes do PDF do contrato (parâmetro `pdf_bytes`, ou lê de
             `req.document_path`, ou de `certificate_ref['pdf_path']`).
          2. Assina o PDF com o A1 (pyhanko/PAdES) — assinatura ICP-Brasil
             embutida, com a cadeia completa. Valida validade antes.
          3. Grava o PDF assinado em uploads/signed/ e aponta
             `req.signed_document_path`.
          4. Persiste uma linha `sig_signatures` com signature_type=DIGITAL e os
             metadados do certificado (issuer/serial/valid_from/valid_to).
          5. Marca a request SIGNED e, se todos assinaram, completa o grupo.

        Raises:
            ValueError: se o assinante não for COMPANY (política) ou faltar o PDF.
            QualifiedSignatureError: falha no motor PAdES (cert vencido, senha
                ausente, .p12 indisponível) — mensagem honesta, sem vazar segredo.
        """
        from modules.signatures.services.qualified_signer import (
            assinar_pdf_icp_brasil,
        )

        if signer_type != SignerType.COMPANY:
            raise ValueError(
                "Assinatura QUALIFICADA (ICP-Brasil A1) é exclusiva da EMPRESA "
                "(titular do certificado). Funcionário/cliente assinam em nível "
                "SIMPLE."
            )

        # 1) Bytes do PDF a assinar.
        source = pdf_bytes
        if source is None and certificate_ref and certificate_ref.get("pdf_path"):
            source = self._read_pdf(certificate_ref["pdf_path"])
        if source is None and req.document_path:
            source = self._read_pdf(req.document_path)
        if not source:
            raise ValueError(
                "PDF do contrato não disponível para assinatura qualificada. "
                "Forneça pdf_bytes, req.document_path ou certificate_ref['pdf_path']."
            )

        # 2) Assina (valida validade do cert dentro; senha só via env).
        result = assinar_pdf_icp_brasil(
            source,
            reason=f"Assinatura qualificada ICP-Brasil — {req.document_type or 'contrato'}",
            location="Manaus/AM",
            contact_info=signer_name,
        )

        # 3) Grava o PDF assinado.
        signed_path = self._save_signed_pdf(
            result.signed_pdf,
            document_type=req.document_type or "contract",
            request_id=req.id,
        )
        signed_hash = hashlib.sha256(result.signed_pdf).hexdigest()

        # 4) Persiste a assinatura DIGITAL com metadados do certificado.
        ev = evidence or SignatureEvidence()
        sig = Signature(
            id=uuid.uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            owner_id=signer_id,
            owner_type=str(signer_type),
            owner_name=signer_name,
            owner_document=req.signer_document,
            signature_type=SignatureType.DIGITAL,
            status=SignatureStatus.VERIFIED,
            source=SignatureSource.CERTIFICATE,
            hash_algorithm="SHA-256",
            signature_hash=signed_hash,
            is_verified=True,
            verified_at=signed_at,
            is_active=True,
            certificate_issuer=result.certificate_issuer_cn[:255],
            certificate_serial=result.certificate_serial[:100],
            certificate_valid_from=result.certificate_valid_from,
            certificate_valid_to=result.certificate_valid_to,
            capture_ip=ev.ip_address,
            capture_device=ev.device,
            capture_user_agent=ev.user_agent,
            capture_location=ev.location,
            created_at=signed_at,
            updated_at=signed_at,
            created_by=signer_id,
            extra_data={
                "level": str(SignatureLevel.QUALIFIED),
                "icp_brasil": True,
                "pades": True,
                "certificate_subject": result.certificate_subject_cn,
                "signed_document_path": signed_path,
                **(ev.extra or {}),
            },
        )
        self.db.add(sig)
        await self.db.flush()

        req.signature_id = sig.id
        req.signed_at = signed_at
        req.status = RequestStatus.SIGNED
        req.signed_document_path = signed_path
        req.signed_document_hash = signed_hash
        req.signing_ip = ev.ip_address
        req.signing_user_agent = ev.user_agent
        req.updated_at = signed_at
        req.last_activity_at = signed_at
        req.audit_log = self._append_audit(
            req.audit_log,
            action="signed_qualified",
            at=signed_at,
            signer_type=str(signer_type),
            signer_name=signer_name,
            level="qualified",
            certificate_issuer=result.certificate_issuer_cn,
            certificate_serial=result.certificate_serial,
            signed_document_hash=signed_hash,
        )

        group_completed = await self._maybe_complete_group(req)
        await self.db.commit()

        logger.info(
            "Contrato assinado QUALIFICADO (ICP-Brasil): request=%s issuer=%s serial=%s group_completed=%s",
            req.id,
            result.certificate_issuer_cn,
            result.certificate_serial,
            group_completed,
        )

        return {
            "signature_id": str(sig.id),
            "signature_hash": signed_hash,
            "signed_at": signed_at.isoformat(),
            "request_status": str(req.status),
            "group_completed": group_completed,
            "level": str(SignatureLevel.QUALIFIED),
            "icp_brasil": True,
            "signed_document_path": signed_path,
            "certificate": {
                "subject": result.certificate_subject_cn,
                "issuer": result.certificate_issuer_cn,
                "serial": result.certificate_serial,
                "valid_from": result.certificate_valid_from.isoformat(),
                "valid_to": result.certificate_valid_to.isoformat(),
            },
        }

    @staticmethod
    def _read_pdf(path: str) -> bytes | None:
        """Lê os bytes de um PDF do disco; None se ausente."""
        try:
            with open(path, "rb") as fh:
                return fh.read()
        except OSError:
            return None

    @staticmethod
    def _save_signed_pdf(
        signed_pdf: bytes, *, document_type: str, request_id: uuid.UUID
    ) -> str:
        """Grava o PDF assinado (PAdES) em uploads/signed/ e devolve o caminho."""
        base = os.getenv("SIGNED_DOCS_DIR", "/app/uploads/signed")
        os.makedirs(base, exist_ok=True)
        fname = f"{document_type}_{request_id}_assinado_icp.pdf"
        path = os.path.join(base, fname)
        with open(path, "wb") as fh:
            fh.write(signed_pdf)
        return path

    @staticmethod
    def _coerce_doc_uuid(document_id: str) -> uuid.UUID | None:
        """Converte document_id para UUID quando possível (coluna é UUID nullable).

        Se não for UUID (id textual), retorna None — o id original fica preservado
        em custom_fields['document_id_raw'] e é usado nas buscas.
        """
        try:
            return uuid.UUID(str(document_id))
        except (ValueError, AttributeError, TypeError):
            return None

    @staticmethod
    def _append_audit(
        current: list[dict[str, Any]] | None,
        **entry: Any,
    ) -> list[dict[str, Any]]:
        """Anexa uma entrada à trilha de auditoria (audit_log JSONB)."""
        log = list(current or [])
        log.append({k: (v if not isinstance(v, datetime) else v.isoformat()) for k, v in entry.items()})
        return log

    async def _get_request(self, request_id: uuid.UUID) -> SignatureRequest | None:
        result = await self.db.execute(
            select(SignatureRequest).where(SignatureRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    _PENDING_STATUSES = (
        RequestStatus.PENDING,
        RequestStatus.SENT,
        RequestStatus.VIEWED,
        RequestStatus.SIGNING,
    )

    async def _pendentes_query(self, employee_id: uuid.UUID) -> list[SignatureRequest]:
        """Solicitações PENDENTES do funcionário (signer_type=employee, DELE)."""
        result = await self.db.execute(
            select(SignatureRequest)
            .where(
                SignatureRequest.signer_type == str(SignerType.EMPLOYEE),
                SignatureRequest.signer_id == employee_id,
                SignatureRequest.status.in_([str(s) for s in self._PENDING_STATUSES]),
            )
            .order_by(SignatureRequest.created_at.asc())
        )
        return list(result.scalars().all())

    def _eh_opcional(
        self, r: SignatureRequest, ref_ym: tuple[int, int], cutoff: datetime
    ) -> bool:
        """Solicitação é HISTÓRICA/OPCIONAL? (competência antiga OU lote retroativo).

        Ver bloco "HISTÓRICO × CORRENTE (M2)" no topo do módulo.
        """
        comp = (
            _competencia_de(r.reference_code)
            or _competencia_de(r.document_name)
            or _competencia_de(r.title)
            or _competencia_de((r.extra_data or {}).get("competencia") if r.extra_data else None)
        )
        if comp is not None:
            # Competência anterior ao mês corrente → histórico.
            return comp < ref_ym
        # Sem competência legível: histórico se veio do lote retroativo (até o cutoff).
        if r.created_at is not None and r.created_at <= cutoff:
            return True
        return False

    @staticmethod
    def _serialize_pendente(r: SignatureRequest, opcional: bool) -> dict:
        """Serializa uma solicitação pendente para a tela, com a flag `opcional`."""
        return {
            "request_id": str(r.id),
            "title": r.title,
            "document_type": r.document_type,
            "document_name": r.document_name,
            "reference_code": r.reference_code,
            "status": str(r.status),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "is_expired": r.is_expired,
            "purpose": str(r.purpose) if r.purpose else None,
            # M2: True = histórico/opcional (competência antiga ou lote retroativo);
            # False = corrente, entra na pilha obrigatória "a assinar agora".
            "opcional": opcional,
        }

    async def pendentes_do_funcionario(self, employee_id: uuid.UUID) -> list[dict]:
        """Lista TODAS as solicitações de assinatura PENDENTES de um funcionário.

        Filtra por signer_type='employee' e signer_id=employee_id, apenas as que
        ainda não foram assinadas (pending/sent/viewed/signing). Base da tela
        "Meus documentos a assinar" do self-service — o funcionário só enxerga o
        que é DELE (segurança por employee_id). Cada item traz a flag `opcional`
        (histórico) para retrocompatibilidade; a separação vem em
        `pendentes_do_funcionario_separado`.
        """
        reqs = await self._pendentes_query(employee_id)
        now = _now_manaus()
        ref_ym = (now.year, now.month)
        cutoff = _retroativo_cutoff()
        return [
            self._serialize_pendente(r, self._eh_opcional(r, ref_ym, cutoff))
            for r in reqs
        ]

    async def pendentes_do_funcionario_separado(self, employee_id: uuid.UUID) -> dict:
        """Separa os pendentes em CORRENTE (a assinar agora) × HISTÓRICO (opcional).

        Returns:
            {a_assinar_agora:[...], historico_opcional:[...],
             total_a_assinar, total_historico}. A pilha obrigatória (badge) é só
            `a_assinar_agora`; o histórico é assinável mas não confronta o usuário.
        """
        reqs = await self._pendentes_query(employee_id)
        now = _now_manaus()
        ref_ym = (now.year, now.month)
        cutoff = _retroativo_cutoff()
        a_assinar: list[dict] = []
        historico: list[dict] = []
        for r in reqs:
            opcional = self._eh_opcional(r, ref_ym, cutoff)
            item = self._serialize_pendente(r, opcional)
            (historico if opcional else a_assinar).append(item)
        return {
            "a_assinar_agora": a_assinar,
            "historico_opcional": historico,
            "total_a_assinar": len(a_assinar),
            "total_historico": len(historico),
        }

    async def assinar_lote(
        self,
        *,
        employee_id: uuid.UUID,
        request_ids: list[uuid.UUID],
        evidence: SignatureEvidence | None = None,
    ) -> dict[str, Any]:
        """Assina em LOTE várias solicitações do PRÓPRIO funcionário (self-service).

        Segurança (mesma regra de POST /{id}/sign para EMPLOYEE): valida a posse de
        CADA request ANTES de assinar qualquer uma — signer_type='employee' e
        signer_id == employee_id. Se QUALQUER request não pertencer ao funcionário
        (ou não existir), levanta PermissionError e NADA é assinado.

        Cada assinatura é REAL: gera sua própria linha em sig_signatures (hash
        SHA-256 + evidências), tal qual a assinatura individual. Requests já
        assinadas/expiradas/canceladas são puladas e reportadas em `ignorados`,
        sem abortar o lote.

        Args:
            employee_id: employee_id do JWT (dono das assinaturas).
            request_ids: UUIDs das solicitações a assinar (o controller limita a 50).
            evidence: IP/user-agent/device/location (trilha de auditoria).

        Returns:
            {total, total_assinados, assinados:[{request_id, signature_hash,
             signed_at}], ignorados:[{request_id, motivo}]}.

        Raises:
            PermissionError: alguma request não existe ou não é do funcionário.
        """
        from modules.signatures.helpers.solicitar_assinatura_documento import (
            nivel_assinatura,
        )

        if not request_ids:
            return {"total": 0, "total_assinados": 0, "assinados": [], "ignorados": []}

        # 1) valida posse de TODAS antes de assinar qualquer uma (all-or-nothing).
        doc_types: dict[uuid.UUID, str] = {}
        for rid in request_ids:
            r = await self._get_request(rid)
            if r is None:
                raise PermissionError(f"Solicitação {rid} não encontrada.")
            if str(r.signer_type) != str(SignerType.EMPLOYEE) or str(r.signer_id) != str(
                employee_id
            ):
                raise PermissionError(
                    "Você não pode assinar um documento que não é seu."
                )
            # captura o tipo agora (string) para não fazer lazy-load após os commits.
            doc_types[rid] = r.document_type or ""

        # 2) assina cada uma (pulando já assinadas/expiradas sem abortar o lote).
        assinados: list[dict[str, Any]] = []
        ignorados: list[dict[str, Any]] = []
        for rid in request_ids:
            try:
                res = await self.assinar(
                    request_id=rid,
                    signer_type=SignerType.EMPLOYEE,
                    signer_id=employee_id,
                    evidence=evidence,
                    level=nivel_assinatura(doc_types[rid], SignerType.EMPLOYEE),
                )
                assinados.append(
                    {
                        "request_id": str(rid),
                        "signature_hash": res["signature_hash"],
                        "signed_at": res["signed_at"],
                    }
                )
            except ValueError as exc:
                ignorados.append({"request_id": str(rid), "motivo": str(exc)})
            except Exception as exc:  # noqa: BLE001
                # erro operacional (DB/loop asyncpg): NÃO derruba o lote inteiro —
                # limpa a sessão e segue para os demais itens
                try:
                    await self.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
                ignorados.append({"request_id": str(rid), "motivo": f"erro: {exc}"})

        return {
            "total": len(request_ids),
            "total_assinados": len(assinados),
            "assinados": assinados,
            "ignorados": ignorados,
        }

    async def _get_request_by_token(self, token: str) -> SignatureRequest | None:
        result = await self.db.execute(
            select(SignatureRequest).where(SignatureRequest.access_token == token)
        )
        return result.scalar_one_or_none()

    async def _get_requests_for_document(
        self, document_type: str, document_id: str
    ) -> list[SignatureRequest]:
        """Busca todas as requests de um documento (por UUID ou id textual)."""
        doc_uuid = self._coerce_doc_uuid(document_id)
        conditions = [SignatureRequest.document_type == document_type]
        query = select(SignatureRequest).where(*conditions)
        result = await self.db.execute(query)
        rows = list(result.scalars().all())
        # filtra por document_id (UUID) OU document_id_raw (custom_fields)
        matched = []
        for r in rows:
            if doc_uuid is not None and r.document_id == doc_uuid:
                matched.append(r)
            elif (r.custom_fields or {}).get("document_id_raw") == str(document_id):
                matched.append(r)
        return sorted(matched, key=lambda r: r.signature_order or 0)

    async def _signatures_for(self, sig_ids: list[uuid.UUID]) -> dict[str, dict[str, Any]]:
        """Busca hash + nível + metadados do certificado (ICP-Brasil) de cada assinatura.

        Usado por `status()` para o bloco de autenticidade distinguir a assinatura
        eletrônica simples (funcionário/cliente) da qualificada ICP-Brasil (empresa),
        exibindo emissor/série do certificado A1 quando houver.
        """
        result = await self.db.execute(
            select(
                Signature.id,
                Signature.signature_hash,
                Signature.signature_type,
                Signature.certificate_issuer,
                Signature.certificate_serial,
                Signature.certificate_valid_to,
                Signature.extra_data,
            ).where(Signature.id.in_(sig_ids))
        )
        out: dict[str, dict[str, Any]] = {}
        for row in result.all():
            extra = row.extra_data or {}
            sig_type = getattr(row.signature_type, "value", row.signature_type)
            out[str(row.id)] = {
                "signature_hash": row.signature_hash,
                "signature_type": str(sig_type) if sig_type else None,
                "level": extra.get("level"),
                "certificate_issuer": row.certificate_issuer,
                "certificate_serial": row.certificate_serial,
                "certificate_valid_to": (
                    row.certificate_valid_to.isoformat() if row.certificate_valid_to else None
                ),
            }
        return out

    async def _pos_assinatura_hook(self, req: SignatureRequest, signed_at: Any) -> None:
        """Efeitos colaterais por document_type após a assinatura.

        - espelho_ponto (funcionário homologa): grava
          time_sheets.approved_by_employee=true + employee_approved_at.

        Fire-and-forget: qualquer erro é logado e engolido — a assinatura já foi
        registrada e não pode ser desfeita por um efeito colateral.
        """
        try:
            if (req.document_type or "") != "espelho_ponto":
                return
            if str(req.signer_type or "").lower() != "employee":
                return
            doc_id = str(req.document_id or (req.custom_fields or {}).get("document_id_raw", "")).strip()
            if not doc_id:
                return
            from sqlalchemy import text as _sql

            result = await self.db.execute(
                _sql(
                    "UPDATE time_sheets SET approved_by_employee = true, "
                    "employee_approved_at = :ts "
                    "WHERE CAST(id AS TEXT) = :d"
                ),
                {"ts": signed_at, "d": doc_id},
            )
            await self.db.commit()
            if getattr(result, "rowcount", 0):
                logger.info("Espelho de ponto homologado pelo funcionário: time_sheet=%s", doc_id)
            else:
                # honestidade: assinatura OK, mas o id não casou nenhum time_sheet —
                # NÃO afirmar "homologado" (evita divergência assinado × homologado)
                logger.warning(
                    "Hook espelho_ponto: nenhum time_sheet id=%s (assinatura OK, homologação NÃO gravada)",
                    doc_id,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Hook pós-assinatura (espelho_ponto) falhou: %s", exc)
            try:
                await self.db.rollback()
            except Exception:  # noqa: BLE001
                pass

    async def _maybe_complete_group(self, req: SignatureRequest) -> bool:
        """Se todos os signatários do documento assinaram, marca o grupo COMPLETED."""
        siblings = await self._get_requests_for_document(
            req.document_type or "",
            str(req.document_id or (req.custom_fields or {}).get("document_id_raw", "")),
        )
        if not siblings:
            return False
        all_signed = all(
            s.status in (RequestStatus.SIGNED, RequestStatus.COMPLETED)
            or s.id == req.id
            for s in siblings
        )
        if all_signed:
            for s in siblings:
                s.status = RequestStatus.COMPLETED
            return True
        return False
