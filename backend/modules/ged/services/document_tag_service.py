"""Service para DocumentTag."""

import builtins
import logging
import re

from sqlalchemy.ext.asyncio import AsyncSession

from modules.ged.models.document_tag import TagColor, TagType
from modules.ged.repositories.document_repository import DocumentRepository
from modules.ged.repositories.document_tag_repository import DocumentTagRepository
from modules.ged.schemas.document_tag import (
    DocumentTagCreate,
    DocumentTagFilter,
    DocumentTagListResponse,
    DocumentTagResponse,
    DocumentTagTreeNode,
    DocumentTagUpdate,
)

logger = logging.getLogger(__name__)


def _tag_to_response(tag) -> DocumentTagResponse:
    """Converte DocumentTag model para response sem triggering lazy loads."""
    return DocumentTagResponse(
        id=str(tag.id),
        name=tag.name,
        slug=tag.slug,
        description=tag.description,
        tag_type=tag.tag_type,
        parent_id=str(tag.parent_id) if tag.parent_id else None,
        color=tag.color if hasattr(tag, "color") and tag.color else "blue",
        icon=tag.icon if hasattr(tag, "icon") else None,
        condominium_id=str(tag.condominium_id) if hasattr(tag, "condominium_id") and tag.condominium_id else None,
        is_global=tag.is_global if hasattr(tag, "is_global") else False,
        is_active=tag.is_active if hasattr(tag, "is_active") else True,
        is_system=tag.is_system if hasattr(tag, "is_system") else False,
        usage_count=tag.usage_count if hasattr(tag, "usage_count") else 0,
        last_used_at=tag.last_used_at if hasattr(tag, "last_used_at") else None,
        order=tag.order if hasattr(tag, "order") else 0,
        created_at=tag.created_at,
        updated_at=tag.updated_at,
        created_by=str(tag.created_by) if tag.created_by else "",
        is_category=tag.tag_type == TagType.CATEGORIA,
        has_children=bool(tag.parent_id is None and tag.tag_type == TagType.CATEGORIA),
        full_path=tag.name,
        document_count=len(tag.documents) if hasattr(tag, "documents") and tag.documents is not None else 0,
    )


class DocumentTagService:
    """Service para operações de tags."""

    def __init__(self, session: AsyncSession):
        """Inicializa o service."""
        self.session = session
        self.repository = DocumentTagRepository(session)
        self.document_repository = DocumentRepository(session)

    async def create(self, data: DocumentTagCreate) -> DocumentTagResponse:
        """Cria uma nova tag."""
        # Verifica se já existe tag com mesmo nome no escopo
        existing = await self.repository.get_by_name(
            name=data.name,
            condominium_id=data.condominium_id,
        )
        if existing:
            raise ValueError("Já existe tag com este nome")

        tag = await self.repository.create(data)
        await self.session.commit()
        logger.info("Tag criada: %s - %s", tag.id, tag.name)
        return DocumentTagResponse.model_validate(tag)

    async def get_by_id(self, tag_id: str) -> DocumentTagResponse | None:
        """Busca tag por ID."""
        tag = await self.repository.get_by_id(tag_id)
        if not tag:
            return None
        return DocumentTagResponse.model_validate(tag)

    async def get_by_name(self, name: str, condominium_id: str = None) -> DocumentTagResponse | None:
        """Busca tag por nome."""
        tag = await self.repository.get_by_name(name, condominium_id)
        if not tag:
            return None
        return DocumentTagResponse.model_validate(tag)

    async def get_by_slug(self, slug: str, condominium_id: str = None) -> DocumentTagResponse | None:
        """Busca tag por slug."""
        tag = await self.repository.get_by_slug(slug, condominium_id)
        if not tag:
            return None
        return DocumentTagResponse.model_validate(tag)

    async def update(self, tag_id: str, data: DocumentTagUpdate) -> DocumentTagResponse | None:
        """Atualiza tag."""
        tag = await self.repository.update(tag_id, data)
        if not tag:
            return None
        await self.session.commit()
        logger.info("Tag atualizada: %s", tag_id)
        return DocumentTagResponse.model_validate(tag)

    async def delete(self, tag_id: str) -> bool:
        """Remove tag."""
        # Verifica se é tag do sistema
        tag = await self.repository.get_by_id(tag_id)
        if tag and tag.is_system:
            raise ValueError("Não é possível remover tag do sistema")

        result = await self.repository.soft_delete(tag_id)
        if result:
            await self.session.commit()
            logger.info("Tag removida: %s", tag_id)
        return result

    async def list(
        self,
        filters: DocumentTagFilter | None = None,
        page: int = 1,
        page_size: int = 50,
        order_by: str = "name",
        order_desc: bool = False,
    ) -> DocumentTagListResponse:
        """Lista tags com filtros."""
        skip = (page - 1) * page_size
        tags, total = await self.repository.list_with_filters(
            filters=filters,
            skip=skip,
            limit=page_size,
            order_by=order_by,
            order_desc=order_desc,
        )

        pages = (total + page_size - 1) // page_size if total > 0 else 0

        return DocumentTagListResponse(
            items=[_tag_to_response(t) for t in tags],
            total=total,
            page=page,
            page_size=page_size,
            pages=pages,
        )

    async def get_by_type(self, tag_type: TagType, condominium_id: str = None) -> builtins.list[DocumentTagResponse]:
        """Retorna tags por tipo."""
        tags = await self.repository.get_by_type(tag_type, condominium_id)
        return [_tag_to_response(t) for t in tags]

    async def get_tree(self, condominium_id: str = None) -> builtins.list[DocumentTagTreeNode]:
        """Retorna árvore de tags."""
        tags = await self.repository.get_tree(condominium_id)

        # Constrói árvore
        tag_map = {}
        root_nodes = []

        for tag in tags:
            node = DocumentTagTreeNode(
                id=str(tag.id),
                name=tag.name,
                slug=tag.slug,
                tag_type=tag.tag_type,
                color=tag.color if tag.color else "blue",
                icon=tag.icon if hasattr(tag, "icon") else None,
                document_count=tag.usage_count if hasattr(tag, "usage_count") else 0,
                children=[],
            )
            tag_map[tag.id] = node

            if tag.parent_id and tag.parent_id in tag_map:
                tag_map[tag.parent_id].children.append(node)
            else:
                root_nodes.append(node)

        return root_nodes

    async def add_to_document(self, tag_id: str, document_id: str) -> bool:
        """Adiciona tag a documento."""
        # Verifica se tag existe
        tag = await self.repository.get_by_id(tag_id)
        if not tag:
            raise ValueError("Tag não encontrada")

        # Verifica se documento existe
        document = await self.document_repository.get_by_id(document_id)
        if not document:
            raise ValueError("Documento não encontrado")

        # Verifica se já está associada
        is_associated = await self.repository.is_associated(tag_id, document_id)
        if is_associated:
            return True  # Já associada

        # `assign_to_document(document_id, tag_id, created_by)` — NOMEADO, porque a
        # ordem dos dois primeiros e o INVERSO do que este service usava. Trocar so o
        # nome do metodo gravaria o documento no lugar da tag e vice-versa.
        # `created_by` e nullable na tabela; este caminho nao recebe o usuario.
        result = await self.repository.assign_to_document(
            document_id=document_id, tag_id=tag_id, created_by=None
        )
        if result:
            await self.session.commit()
            logger.info("Tag %s adicionada ao documento %s", tag_id, document_id)
        return result

    async def remove_from_document(self, tag_id: str, document_id: str) -> bool:
        """Remove tag de documento."""
        result = await self.repository.remove_from_document(document_id=document_id, tag_id=tag_id)
        if result:
            await self.session.commit()
            logger.info("Tag %s removida do documento %s", tag_id, document_id)
        return result

    async def get_by_document(self, document_id: str) -> builtins.list[DocumentTagResponse]:
        """Retorna tags de um documento."""
        tags = await self.repository.get_document_tags(document_id)
        return [_tag_to_response(t) for t in tags]

    async def get_documents_by_tag(self, tag_id: str, page: int = 1, page_size: int = 20) -> builtins.list[str]:
        """Retorna IDs de documentos com a tag."""
        skip = (page - 1) * page_size
        return await self.repository.get_documents_by_tag(tag_id, skip, page_size)

    async def set_document_tags(
        self, document_id: str, tag_ids: builtins.list[str]
    ) -> builtins.list[DocumentTagResponse]:
        """Define tags de um documento."""
        # Verifica documento
        document = await self.document_repository.get_by_id(document_id)
        if not document:
            raise ValueError("Documento não encontrado")

        # Verifica se todas as tags existem
        for tag_id in tag_ids:
            tag = await self.repository.get_by_id(tag_id)
            if not tag:
                raise ValueError(f"Tag não encontrada: {tag_id}")

        await self.repository.set_document_tags(document_id, tag_ids)
        await self.session.commit()
        logger.info("Tags definidas para documento %s: %s", document_id, tag_ids)

        return await self.get_by_document(document_id)

    async def get_most_used(self, condominium_id: str = None, limit: int = 10) -> builtins.list[DocumentTagResponse]:
        """Retorna tags mais usadas."""
        tags = await self.repository.get_most_used(condominium_id, limit)
        return [_tag_to_response(t) for t in tags]

    async def search(
        self, query: str, condominium_id: str = None, limit: int = 10
    ) -> builtins.list[DocumentTagResponse]:
        """Busca tags por texto."""
        tags = await self.repository.search(query, condominium_id, limit)
        return [_tag_to_response(t) for t in tags]

    async def merge_tags(self, source_tag_id: str, target_tag_id: str) -> DocumentTagResponse:
        """Mescla duas tags."""
        source = await self.repository.get_by_id(source_tag_id)
        if not source:
            raise ValueError("Tag origem não encontrada")

        target = await self.repository.get_by_id(target_tag_id)
        if not target:
            raise ValueError("Tag destino não encontrada")

        if source.is_system:
            raise ValueError("Não é possível mesclar tag do sistema")

        # Move documentos para tag destino
        await self.repository.merge_tags(source_tag_id, target_tag_id)

        # Remove tag origem
        await self.repository.soft_delete(source_tag_id)

        await self.session.commit()
        logger.info("Tags mescladas: %s -> %s", source_tag_id, target_tag_id)

        return DocumentTagResponse.model_validate(target)

    async def get_suggested_tags(
        self, text: str, condominium_id: str = None, limit: int = 5
    ) -> builtins.list[DocumentTagResponse]:
        """Sugere tags baseado no texto."""
        # Extrai palavras-chave do texto
        keywords = self._extract_keywords(text)

        # Busca tags que correspondem
        suggested = []
        for keyword in keywords[:10]:
            tags = await self.repository.search(keyword, condominium_id, 3)
            for tag in tags:
                if tag not in suggested:
                    suggested.append(tag)
                    if len(suggested) >= limit:
                        break
            if len(suggested) >= limit:
                break

        return [_tag_to_response(t) for t in suggested]

    def _extract_keywords(self, text: str) -> builtins.list[str]:
        """Extrai palavras-chave do texto."""
        # Remove caracteres especiais
        text = re.sub(r"[^\w\s]", " ", text.lower())

        # Remove stopwords básicas (PT e EN)
        stopwords = {
            "de",
            "da",
            "do",
            "das",
            "dos",
            "a",
            "o",
            "as",
            "os",
            "um",
            "uma",
            "uns",
            "umas",
            "e",
            "ou",
            "para",
            "por",
            "em",
            "no",
            "na",
            "nos",
            "nas",
            "com",
            "sem",
            "que",
            "se",
            "ao",
            "aos",
            "este",
            "esta",
            "esse",
            "essa",
            "the",
            "an",
            "and",
            "or",
            "for",
            "in",
            "on",
            "at",
        }

        # Extrai palavras únicas
        words = text.split()
        keywords = []
        for word in words:
            word = word.strip()
            if len(word) >= 3 and word not in stopwords:
                if word not in keywords:
                    keywords.append(word)

        return keywords

    async def create_default_tags(self, condominium_id: str, created_by: str) -> builtins.list[DocumentTagResponse]:
        """Cria tags padrão."""
        default_tags = [
            {"name": "Importante", "type": TagType.PRIORIDADE, "color": TagColor.VERMELHO},
            {"name": "Urgente", "type": TagType.PRIORIDADE, "color": TagColor.LARANJA},
            {"name": "Pendente", "type": TagType.STATUS, "color": TagColor.AMARELO},
            {"name": "Concluído", "type": TagType.STATUS, "color": TagColor.VERDE},
            {"name": "Em Análise", "type": TagType.STATUS, "color": TagColor.AZUL},
            {"name": "Arquivado", "type": TagType.STATUS, "color": TagColor.CINZA},
            {"name": "Contrato", "type": TagType.CATEGORIA, "color": TagColor.ROXO},
            {"name": "Financeiro", "type": TagType.DEPARTAMENTO, "color": TagColor.VERDE},
            {"name": "Jurídico", "type": TagType.DEPARTAMENTO, "color": TagColor.AZUL},
            {"name": "Administrativo", "type": TagType.DEPARTAMENTO, "color": TagColor.CINZA},
        ]

        created = []
        for tag_data in default_tags:
            # Verifica se já existe
            existing = await self.repository.get_by_name(tag_data["name"], condominium_id)
            if existing:
                continue

            data = DocumentTagCreate(
                name=tag_data["name"],
                tag_type=tag_data["type"],
                color=tag_data["color"],
                condominium_id=condominium_id,
                created_by=created_by,
                is_system=True,
            )
            tag = await self.repository.create(data)
            created.append(DocumentTagResponse.model_validate(tag))

        await self.session.commit()
        logger.info(
            "%s tags padrão criadas para condomínio %s",
            len(created),
            condominium_id,
        )
        return created

    async def get_stats(self, condominium_id: str = None) -> dict:
        """Retorna estatísticas de tags."""
        return await self.repository.get_stats(condominium_id)
