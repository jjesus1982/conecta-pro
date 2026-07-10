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

GANCHO ICP-Brasil (assinatura QUALIFICADA com certificado A1): ver
`_apply_qualified_signature`. Hoje levanta NotImplementedError de propósito —
o nível eletrônico simples é o implementado agora, conforme escopo.

TZ: todos os timestamps de evidência são gravados no fuso America/Manaus
(o servidor roda nesse fuso); as colunas DateTime armazenam naive local Manaus,
padrão já adotado no restante do ERP (ponto, folha, SST).
"""

from __future__ import annotations

import hashlib
import logging
import os
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
            level: SIMPLE (implementado) ou QUALIFIED (gancho ICP-Brasil).
            certificate_ref: Metadados do certificado A1 (só p/ QUALIFIED).

        Returns:
            Dict com signature_id, signature_hash, signed_at (ISO Manaus),
            request_status, group_completed (bool).

        Raises:
            ValueError: request inexistente, já assinada, tipo divergente ou
                solicitação expirada.
            NotImplementedError: se level=QUALIFIED (gancho ainda não ativo).
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
            # Gancho ICP-Brasil — deliberadamente não implementado agora.
            return await self._apply_qualified_signature(
                req=req,
                signer_type=signer_type,
                signer_id=signer_id,
                signer_name=eff_name,
                certificate_ref=certificate_ref,
                signed_at=signed_at,
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

        await self.db.commit()

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
        if req.access_code and access_code != req.access_code:
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
                }
            )

        # completa o hash de cada assinatura, se houver
        sig_ids = [r.signature_id for r in reqs if r.signature_id]
        if sig_ids:
            hash_map = await self._hashes_for(sig_ids)
            for s in signatarios:
                if s["signature_id"]:
                    s["signature_hash"] = hash_map.get(s["signature_id"])

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

    async def _apply_qualified_signature(self, **_: Any) -> dict[str, Any]:
        """GANCHO ICP-Brasil (A1/A3). Não implementado no escopo atual.

        Quando ativado, deverá:
          1. Carregar o .pfx (A1) da empresa (senha do cofre/env).
          2. Assinar o PDF (PAdES) ou o hash do documento (CAdES) via cryptography
             / pyhanko, embutindo o certificado e o carimbo de tempo.
          3. Persistir certificate_issuer/serial/valid_from/valid_to em
             sig_signatures e marcar signature_type=DIGITAL.
        """
        raise NotImplementedError(
            "Assinatura QUALIFICADA (ICP-Brasil A1) ainda não implementada. "
            "Use level=SIMPLE (eletrônica simples) por enquanto."
        )

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

    async def _hashes_for(self, sig_ids: list[uuid.UUID]) -> dict[str, str]:
        result = await self.db.execute(
            select(Signature.id, Signature.signature_hash).where(Signature.id.in_(sig_ids))
        )
        return {str(row[0]): row[1] for row in result.all()}

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
