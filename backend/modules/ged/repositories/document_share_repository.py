"""Repository para DocumentShare."""

import hashlib
import logging
import secrets
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ged.models.document_share import DocumentShare, ShareStatus, ShareType
from modules.ged.schemas.document_share import (
    DocumentShareCreate,
    DocumentShareFilter,
    DocumentShareUpdate,
)

logger = logging.getLogger(__name__)


class DocumentShareRepository:
    """Repository para operações de DocumentShare."""

    def __init__(self, session: AsyncSession):
        """Inicializa o repository."""
        self.session = session

    async def create(self, data: DocumentShareCreate) -> DocumentShare:
        """Cria um novo compartilhamento."""
        share_data = data.model_dump(exclude={"password"})

        # Gera token para compartilhamentos externos
        if data.share_type == ShareType.EXTERNO:
            share_data["share_token"] = secrets.token_urlsafe(32)
            share_data["share_link"] = f"/share/{share_data['share_token']}"

        # Hash da senha se fornecida
        if data.password:
            share_data["password_hash"] = hashlib.sha256(data.password.encode()).hexdigest()

        share = DocumentShare(**share_data)
        self.session.add(share)
        await self.session.flush()
        return share

    async def get_by_id(self, share_id: str) -> DocumentShare | None:
        """Busca compartilhamento por ID."""
        result = await self.session.execute(select(DocumentShare).where(DocumentShare.id == share_id))
        return result.scalar_one_or_none()

    async def get_by_token(self, token: str) -> DocumentShare | None:
        """Busca compartilhamento por token."""
        result = await self.session.execute(select(DocumentShare).where(DocumentShare.share_token == token))
        return result.scalar_one_or_none()

    async def update(self, share_id: str, data: DocumentShareUpdate) -> DocumentShare | None:
        """Atualiza um compartilhamento."""
        share = await self.get_by_id(share_id)
        if not share:
            return None

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(share, field, value)

        await self.session.flush()
        return share

    async def delete(self, share_id: str) -> bool:
        """Remove compartilhamento."""
        share = await self.get_by_id(share_id)
        if not share:
            return False

        await self.session.delete(share)
        await self.session.flush()
        return True

    async def list_with_filters(
        self,
        filters: DocumentShareFilter | None = None,
        skip: int = 0,
        limit: int = 20,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> tuple[list[DocumentShare], int]:
        """Lista compartilhamentos com filtros e paginação."""
        query = select(DocumentShare)

        if filters:
            if filters.document_id:
                query = query.where(DocumentShare.document_id == filters.document_id)
            if filters.share_type:
                query = query.where(DocumentShare.share_type == filters.share_type)
            if filters.status:
                query = query.where(DocumentShare.status == filters.status)
            if filters.shared_with_id:
                query = query.where(DocumentShare.shared_with_id == filters.shared_with_id)
            if filters.shared_by:
                query = query.where(DocumentShare.shared_by == filters.shared_by)

        # Contagem total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # Ordenação
        _valid_order_column_cols = {c.key for c in sa_inspect(DocumentShare).mapper.column_attrs}
        order_column = getattr(DocumentShare, order_by if order_by in _valid_order_column_cols else "created_at")
        if order_desc:
            query = query.order_by(order_column.desc())
        else:
            query = query.order_by(order_column.asc())

        # Paginação
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        shares = result.scalars().all()

        return list(shares), total

    async def get_by_document(self, document_id: str, active_only: bool = True) -> list[DocumentShare]:
        """Retorna compartilhamentos de um documento."""
        query = select(DocumentShare).where(DocumentShare.document_id == document_id)
        if active_only:
            query = query.where(DocumentShare.status == ShareStatus.ATIVO)

        result = await self.session.execute(query.order_by(DocumentShare.created_at.desc()))
        return list(result.scalars().all())

    async def get_by_recipient(
        self, recipient_id: str = None, recipient_email: str = None, skip: int = 0, limit: int = 20
    ) -> list[DocumentShare]:
        """Alias para get_by_user — compartilhamentos recebidos."""
        return await self.get_by_user(recipient_id or "", skip, limit)

    async def get_by_owner(self, owner_id: str, skip: int = 0, limit: int = 20) -> list[DocumentShare]:
        """Alias para get_shared_by_user — compartilhamentos criados."""
        return await self.get_shared_by_user(owner_id, skip, limit)

    async def get_by_user(self, user_id: str, skip: int = 0, limit: int = 20) -> list[DocumentShare]:
        """Retorna documentos compartilhados com usuário."""
        query = (
            select(DocumentShare)
            .where(
                and_(
                    DocumentShare.shared_with_id == user_id,
                    DocumentShare.status == ShareStatus.ATIVO,
                )
            )
            .order_by(DocumentShare.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_shared_by_user(self, user_id: str, skip: int = 0, limit: int = 20) -> list[DocumentShare]:
        """Retorna documentos que o usuário compartilhou."""
        query = (
            select(DocumentShare)
            .where(DocumentShare.shared_by == user_id)
            .order_by(DocumentShare.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def revoke(self, share_id: str, revoked_by: str) -> DocumentShare | None:
        """Revoga compartilhamento."""
        share = await self.get_by_id(share_id)
        if not share:
            return None
        share.revoke(revoked_by)
        await self.session.flush()
        return share

    async def extend_expiry(self, share_id: str, new_expiry: datetime) -> DocumentShare | None:
        """Estende validade do compartilhamento."""
        share = await self.get_by_id(share_id)
        if not share:
            return None
        share.extend_expiry(new_expiry)
        await self.session.flush()
        return share

    async def record_access(self, share_id: str) -> DocumentShare | None:
        """Registra acesso ao compartilhamento."""
        share = await self.get_by_id(share_id)
        if not share:
            return None
        share.record_access()
        await self.session.flush()
        return share

    async def record_view(self, share_id: str) -> bool:
        """Registra visualização."""
        share = await self.get_by_id(share_id)
        if not share:
            return False
        result = share.record_view()
        await self.session.flush()
        return result

    async def record_download(self, share_id: str) -> bool:
        """Registra download."""
        share = await self.get_by_id(share_id)
        if not share:
            return False
        result = share.record_download()
        await self.session.flush()
        return result

    # ── Contratos que `document_share_service` já chamava e nunca existiram aqui ────
    # Cinco métodos abaixo + `regenerate_token`: o service os invocava e a rota respondia
    # com AttributeError. As tabelas estão vazias (`ged_document_shares` = 0), então
    # ninguém tinha batido nisso ainda — mas as 23 rotas de compartilhamento ESTÃO
    # montadas e os componentes do front (`DocumentShareDialog.tsx`) as alcançam.

    async def get_by_document_and_recipient(
        self,
        document_id: str,
        recipient_id: str | None = None,
        recipient_email: str | None = None,
    ) -> DocumentShare | None:
        """Compartilhamento ATIVO deste documento para este destinatário, se houver.

        Serve ao "já existe compartilhamento para este destinatário?" do service. Casa por
        id OU por e-mail porque os dois caminhos existem no model (`shared_with_id` e
        `shared_with_email`) e um convite por e-mail nasce sem id de usuário.

        Sem `recipient_id` nem `recipient_email` devolve None em vez de o primeiro
        compartilhamento do documento — casar "qualquer um" com "nenhum informado" faria o
        service concluir que já existe e recusar um compartilhamento legítimo.
        """
        if not recipient_id and not recipient_email:
            return None
        for share in await self.get_by_document(document_id, active_only=True):
            if recipient_id and share.shared_with_id == recipient_id:
                return share
            if recipient_email and share.shared_with_email == recipient_email:
                return share
        return None

    async def accept(self, share_id: str, user_id: str) -> DocumentShare | None:
        """Destinatário aceita um compartilhamento PENDENTE.

        Só sai de `pendente`: aceitar o que já foi revogado ou expirou ressuscitaria acesso
        a documento — e acesso indevido a documento não se desfaz depois.
        """
        share = await self.get_by_id(share_id)
        if not share or share.status != ShareStatus.PENDENTE:
            return None
        share.status = ShareStatus.ATIVO
        if not share.shared_with_id:
            share.shared_with_id = user_id
        share.record_access()
        await self.session.flush()
        return share

    async def update_permission(self, share_id: str, permission) -> DocumentShare | None:
        """Troca a permissão do compartilhamento pela informada.

        `permissions` é uma lista JSONB, e a atribuição é feita com uma lista NOVA de
        propósito: mutar a existente in-place não marca o campo como sujo no SQLAlchemy e a
        troca não chegaria ao banco.
        """
        share = await self.get_by_id(share_id)
        if not share:
            return None
        valor = getattr(permission, "value", permission)
        share.permissions = [valor]
        await self.session.flush()
        return share

    async def set_password(self, share_id: str, password: str) -> DocumentShare | None:
        """Protege o compartilhamento com senha.

        Mesmo hash de `verify_password` (sha256 hex) — usar outro deixaria a senha gravada
        e nunca aceita na verificação.
        """
        share = await self.get_by_id(share_id)
        if not share:
            return None
        share.password_hash = hashlib.sha256(password.encode()).hexdigest()
        share.password_protected = True
        await self.session.flush()
        return share

    async def remove_password(self, share_id: str) -> DocumentShare | None:
        """Tira a senha. Limpa o hash junto — deixá-lo para trás guarda credencial morta."""
        share = await self.get_by_id(share_id)
        if not share:
            return None
        share.password_hash = None
        share.password_protected = False
        await self.session.flush()
        return share

    async def regenerate_token(self, share_id: str) -> str | None:
        """Novo token de acesso — invalida o link antigo, que é o motivo de regenerar.

        Não estava na lista de achados de `checar_repositorio` (nem esta, nem a
        `get_by_document` do repositório de TAGS): a trava tem um ponto cego quando o
        método existe em ALGUM repositório do módulo, mesmo que não no que `self.repository`
        aponta. Está no relatório de 13/08.
        """
        share = await self.get_by_id(share_id)
        if not share:
            return None
        share.share_token = secrets.token_urlsafe(32)
        await self.session.flush()
        return share.share_token

    async def verify_password(self, share_id: str, password: str) -> bool:
        """Verifica senha do compartilhamento."""
        share = await self.get_by_id(share_id)
        if not share or not share.password_protected:
            return True

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return share.password_hash == password_hash

    async def expire_old_shares(self) -> int:
        """Expira compartilhamentos antigos."""
        now = datetime.utcnow()
        query = select(DocumentShare).where(
            and_(
                DocumentShare.status == ShareStatus.ATIVO,
                DocumentShare.is_perpetual.is_(False),
                DocumentShare.expires_at < now,
            )
        )
        result = await self.session.execute(query)
        shares = result.scalars().all()

        count = 0
        for share in shares:
            share.check_and_expire()
            count += 1

        await self.session.flush()
        return count

    async def expire_overdue(self) -> int:
        """Expira shares com data de vencimento ultrapassada."""
        now = datetime.utcnow()
        query = select(DocumentShare).where(
            and_(
                DocumentShare.status == ShareStatus.ATIVO,
                DocumentShare.is_perpetual.is_(False),
                DocumentShare.expires_at < now,
            )
        )
        result = await self.session.execute(query)
        shares = result.scalars().all()

        count = 0
        for share in shares:
            share.check_and_expire()
            count += 1

        await self.session.flush()
        return count

    async def send_notification(self, share_id: str) -> DocumentShare | None:
        """Marca notificação como enviada."""
        share = await self.get_by_id(share_id)
        if not share:
            return None
        share.send_notification()
        await self.session.flush()
        return share

    async def get_stats(self, document_id: str = None) -> dict:
        """Retorna estatísticas de compartilhamentos."""
        query = select(DocumentShare)
        if document_id:
            query = query.where(DocumentShare.document_id == document_id)

        result = await self.session.execute(query)
        shares = result.scalars().all()

        stats = {
            "total_shares": len(shares),
            "active_shares": 0,
            "expired_shares": 0,
            "revoked_shares": 0,
            "by_type": {},
            "total_accesses": 0,
            "total_downloads": 0,
        }

        for share in shares:
            if share.status == ShareStatus.ATIVO:
                stats["active_shares"] += 1
            elif share.status == ShareStatus.EXPIRADO:
                stats["expired_shares"] += 1
            elif share.status == ShareStatus.REVOGADO:
                stats["revoked_shares"] += 1

            share_type = share.share_type.value
            stats["by_type"][share_type] = stats["by_type"].get(share_type, 0) + 1
            stats["total_accesses"] += share.access_count
            stats["total_downloads"] += share.download_count

        return stats
