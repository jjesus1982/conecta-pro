"""
Service EPI (NR-6) - Equipamentos de Protecao Individual
=========================================================

Logica de negocio para gestao de EPIs.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from modules.health_occupational.models.epi import (
    EPI,
    EPIDelivery,
    EPIInventory,
)
from modules.health_occupational.schemas.epi import (
    EPICreateRequest,
    EPIDeliveryRequest,
    EPIDeliveryUpdateRequest,
    EPIInventoryUpdateRequest,
    EPIUpdateRequest,
)

logger = logging.getLogger(__name__)


class EPIService:
    """Service para gerenciamento de EPIs (NR-6)."""

    def __init__(self, db: Session | None = None):
        self.db = db

    # ==========================================================================
    # EPI Catalog Operations
    # ==========================================================================

    def create_epi(self, request: EPICreateRequest, created_by: UUID | None = None) -> EPI:
        """
        Cadastra novo EPI.

        Args:
            request: Dados do EPI.
            created_by: UUID do usuario que criou.

        Returns:
            EPI cadastrado.
        """
        # Verificar se CA ja existe
        existing = self.db.query(EPI).filter(EPI.ca_number == request.ca_number).first()
        if existing:
            raise ValueError(f"EPI com CA {request.ca_number} ja cadastrado")

        epi = EPI(
            nome=request.nome,
            descricao=request.descricao,
            codigo_interno=request.codigo_interno,
            categoria=request.categoria,
            ca_number=request.ca_number,
            ca_validade=request.ca_validade,
            fabricante=request.fabricante,
            modelo=request.modelo,
            validade_dias=request.validade_dias,
            especificacoes=request.especificacoes,
            riscos_protegidos=request.riscos_protegidos,
            instrucoes_uso=request.instrucoes_uso,
            instrucoes_higienizacao=request.instrucoes_higienizacao,
            instrucoes_armazenamento=request.instrucoes_armazenamento,
            imagem_url=request.imagem_url,
            created_by=created_by,
        )

        self.db.add(epi)
        self.db.flush()

        # Criar registro de estoque
        inventory = EPIInventory(
            epi_id=epi.id,
            quantidade_atual=0,
            quantidade_minima=10,
        )
        self.db.add(inventory)

        self.db.commit()
        self.db.refresh(epi)

        logger.info("EPI cadastrado: nome=%s, CA=%s", request.nome, request.ca_number)
        return epi

    def get_epi(self, epi_id: UUID) -> EPI | None:
        """Busca EPI por ID."""
        return self.db.query(EPI).filter(EPI.id == epi_id).first()

    def get_epi_by_ca(self, ca_number: str) -> EPI | None:
        """Busca EPI pelo numero do CA."""
        return self.db.query(EPI).filter(EPI.ca_number == ca_number).first()

    def update_epi(self, epi_id: UUID, request: EPIUpdateRequest) -> EPI | None:
        """Atualiza EPI."""
        epi = self.get_epi(epi_id)
        if not epi:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(epi, field, value)

        self.db.commit()
        self.db.refresh(epi)
        return epi

    def list_epis(
        self,
        categoria: str | None = None,
        ativo: bool | None = True,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """Lista EPIs cadastrados."""
        if not self.db:
            return {"items": [], "total": 0, "page": page, "size": size}

        from sqlalchemy import text

        try:
            where = "WHERE 1=1"
            params: dict = {"limit": size, "offset": (page - 1) * size}

            if categoria:
                where += " AND categoria = :categoria"
                params["categoria"] = categoria
            if ativo is not None:
                where += " AND ativo = :ativo"
                params["ativo"] = ativo

            total = self.db.execute(text(f"SELECT count(*) FROM health_epi_catalog {where}"), params).scalar() or 0

            rows = self.db.execute(
                text(
                    f"SELECT id, nome, descricao, ca_numero, categoria, fabricante, validade_meses, ativo, created_at FROM health_epi_catalog {where} ORDER BY nome LIMIT :limit OFFSET :offset"
                ),
                params,
            ).fetchall()

            items = [
                {
                    "id": str(r.id),
                    "nome": r.nome,
                    "descricao": r.descricao,
                    "ca_numero": r.ca_numero,
                    "categoria": r.categoria,
                    "fabricante": r.fabricante,
                    "validade_meses": r.validade_meses,
                    "ativo": r.ativo,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

            return {"items": items, "total": total, "page": page, "size": size}
        except Exception as e:
            logger.error("Erro ao listar EPIs: %s", e)
            return {"items": [], "total": 0, "page": page, "size": size}

    def deactivate_epi(self, epi_id: UUID) -> EPI | None:
        """Desativa EPI."""
        epi = self.get_epi(epi_id)
        if not epi:
            return None

        epi.ativo = False
        self.db.commit()
        self.db.refresh(epi)
        return epi

    # ==========================================================================
    # EPI Delivery Operations
    # ==========================================================================

    def register_delivery(
        self,
        request: EPIDeliveryRequest,
        entregue_por: UUID | None = None,
    ) -> EPIDelivery:
        """
        Registra entrega de EPI para funcionario.

        Args:
            request: Dados da entrega.
            entregue_por: UUID de quem entregou.

        Returns:
            EPIDelivery registrada.
        """
        epi = self.get_epi(request.epi_id)
        if not epi:
            raise ValueError(f"EPI {request.epi_id} nao encontrado")

        if not epi.ativo:
            raise ValueError("EPI inativo, nao pode ser entregue")

        # Verificar estoque
        inventory = self.get_inventory(request.epi_id)
        if inventory and inventory.quantidade_atual < request.quantidade:
            raise ValueError(
                f"Estoque insuficiente: disponivel={inventory.quantidade_atual}, solicitado={request.quantidade}"
            )

        # Calcular validade
        data_validade = date.today() + timedelta(days=epi.validade_dias)

        delivery = EPIDelivery(
            epi_id=request.epi_id,
            funcionario_id=request.funcionario_id,
            quantidade=request.quantidade,
            motivo=request.motivo,
            ca_number=request.ca_number,
            data_validade=data_validade,
            observacoes=request.observacoes,
            treinamento_realizado=request.treinamento_realizado,
            data_treinamento=datetime.utcnow() if request.treinamento_realizado else None,
            entregue_por=entregue_por,
        )

        self.db.add(delivery)

        # Atualizar estoque
        if inventory:
            inventory.quantidade_atual -= request.quantidade
            inventory.ultima_saida = datetime.utcnow()

        self.db.commit()
        self.db.refresh(delivery)

        try:
            import asyncio

            from infrastructure.message_bus.events import Event, EventType, publish_event

            event = Event(
                type=EventType.EPI_ENTREGUE,
                source="health_occupational.epi_service",
                data={
                    "entrega_id": str(delivery.id),
                    "epi_id": str(delivery.epi_id),
                    "funcionario_id": str(delivery.funcionario_id),
                    "quantidade": delivery.quantidade,
                    "motivo": delivery.motivo,
                    "data_validade": delivery.data_validade.isoformat() if delivery.data_validade else None,
                },
            )
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(publish_event(event))
            else:
                asyncio.run(publish_event(event))
        except Exception as _pub_err:
            logger.warning("Falha ao publicar evento EPI_ENTREGUE: %s", _pub_err)

        logger.info(
            "Entrega de EPI registrada: funcionario=%s, epi=%s, qtd=%d",
            request.funcionario_id,
            request.epi_id,
            request.quantidade,
        )

        return delivery

    def get_delivery(self, delivery_id: UUID) -> EPIDelivery | None:
        """Busca entrega por ID."""
        return self.db.query(EPIDelivery).filter(EPIDelivery.id == delivery_id).first()

    def update_delivery(
        self,
        delivery_id: UUID,
        request: EPIDeliveryUpdateRequest,
    ) -> EPIDelivery | None:
        """Atualiza registro de entrega."""
        delivery = self.get_delivery(delivery_id)
        if not delivery:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(delivery, field, value)

        if request.assinatura_funcionario:
            delivery.data_assinatura = datetime.utcnow()

        self.db.commit()
        self.db.refresh(delivery)
        return delivery

    def register_return(
        self,
        delivery_id: UUID,
        motivo: str,
        condicao: str,
    ) -> EPIDelivery | None:
        """Registra devolucao de EPI."""
        delivery = self.get_delivery(delivery_id)
        if not delivery:
            return None

        delivery.devolvido = True
        delivery.data_devolucao = datetime.utcnow()
        delivery.motivo_devolucao = motivo
        delivery.condicao_devolucao = condicao

        # Se em boa condicao, devolver ao estoque
        if condicao == "bom":
            inventory = self.get_inventory(delivery.epi_id)
            if inventory:
                inventory.quantidade_atual += delivery.quantidade
                inventory.ultima_entrada = datetime.utcnow()

        self.db.commit()
        self.db.refresh(delivery)

        logger.info(
            "Devolucao de EPI registrada: delivery=%s, condicao=%s",
            delivery_id,
            condicao,
        )

        return delivery

    def get_employee_record(self, funcionario_id: UUID) -> dict[str, Any]:
        """
        Retorna ficha de EPI do funcionario.

        Args:
            funcionario_id: UUID do funcionario.

        Returns:
            Dict com historico de EPIs.
        """
        deliveries = (
            self.db.query(EPIDelivery)
            .filter(EPIDelivery.funcionario_id == funcionario_id)
            .order_by(EPIDelivery.data_entrega.desc())
            .all()
        )

        active_epis = [d for d in deliveries if not d.devolvido and not d.esta_vencido]
        expired_epis = [d for d in deliveries if not d.devolvido and d.esta_vencido]
        returned_epis = [d for d in deliveries if d.devolvido]

        return {
            "funcionario_id": str(funcionario_id),
            "entregas": deliveries,
            "total_entregas": len(deliveries),
            "epis_ativos": active_epis,
            "epis_vencidos": expired_epis,
            "epis_devolvidos": returned_epis,
        }

    def list_employee_deliveries(
        self,
        funcionario_id: UUID,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """Lista entregas de um funcionario."""
        query = self.db.query(EPIDelivery).filter(EPIDelivery.funcionario_id == funcionario_id)

        total = query.count()
        deliveries = query.order_by(EPIDelivery.data_entrega.desc()).offset((page - 1) * size).limit(size).all()

        return {
            "items": deliveries,
            "total": total,
            "page": page,
            "size": size,
        }

    # ==========================================================================
    # Inventory Operations
    # ==========================================================================

    def get_inventory(self, epi_id: UUID) -> EPIInventory | None:
        """Busca estoque de um EPI."""
        return self.db.query(EPIInventory).filter(EPIInventory.epi_id == epi_id).first()

    def update_inventory(
        self,
        epi_id: UUID,
        request: EPIInventoryUpdateRequest,
    ) -> EPIInventory | None:
        """Atualiza estoque de EPI."""
        inventory = self.get_inventory(epi_id)
        if not inventory:
            return None

        update_data = request.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(inventory, field, value)

        self.db.commit()
        self.db.refresh(inventory)
        return inventory

    def add_to_inventory(
        self,
        epi_id: UUID,
        quantidade: int,
        lote: str | None = None,
        validade_lote: date | None = None,
    ) -> EPIInventory:
        """Adiciona itens ao estoque."""
        inventory = self.get_inventory(epi_id)
        if not inventory:
            raise ValueError(f"Estoque para EPI {epi_id} nao encontrado")

        inventory.quantidade_atual += quantidade
        inventory.ultima_entrada = datetime.utcnow()

        if lote:
            inventory.lote_atual = lote
        if validade_lote:
            inventory.data_validade_lote = validade_lote

        self.db.commit()
        self.db.refresh(inventory)

        logger.info("Estoque atualizado: epi=%s, +%d unidades", epi_id, quantidade)
        return inventory

    def list_inventory(
        self,
        categoria: str | None = None,
        low_stock_only: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Lista estoque de EPIs.

        Args:
            categoria: Filtrar por categoria.
            low_stock_only: Apenas com estoque baixo.

        Returns:
            Lista de itens de estoque.
        """
        if not self.db:
            return []

        from sqlalchemy import text

        try:
            sql = (
                "SELECT i.id, i.epi_id, c.nome, c.categoria, c.ca_numero, "
                "i.quantidade_disponivel, i.quantidade_minima, i.lote, "
                "i.data_validade, i.localizacao "
                "FROM health_epi_inventory i "
                "JOIN health_epi_catalog c ON i.epi_id = c.id "
                "WHERE 1=1"
            )
            params: dict = {}

            if categoria:
                sql += " AND c.categoria = :categoria"
                params["categoria"] = categoria

            if low_stock_only:
                sql += " AND i.quantidade_disponivel < i.quantidade_minima"

            sql += " ORDER BY c.nome"
            rows = self.db.execute(text(sql), params).fetchall()

            return [
                {
                    "epi_id": str(row.epi_id),
                    "epi_nome": row.nome,
                    "categoria": row.categoria,
                    "ca_numero": row.ca_numero,
                    "quantidade_disponivel": row.quantidade_disponivel,
                    "quantidade_minima": row.quantidade_minima,
                    "estoque_baixo": (row.quantidade_disponivel or 0) < (row.quantidade_minima or 5),
                    "lote": row.lote,
                    "data_validade": row.data_validade.isoformat() if row.data_validade else None,
                    "localizacao": row.localizacao,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error("Erro ao listar estoque EPI: %s", e)
            return []

    # ==========================================================================
    # EPI Categories Info
    # ==========================================================================

    def get_epi_categories(self) -> dict[str, Any]:
        """Retorna informacoes sobre categorias de EPI."""
        return {
            "categorias": [
                {"id": "cabeca", "nome": "Protecao da Cabeca", "exemplos": ["capacete", "capuz"]},
                {"id": "olhos", "nome": "Protecao dos Olhos", "exemplos": ["oculos", "mascara_solda"]},
                {"id": "face", "nome": "Protecao da Face", "exemplos": ["protetor_facial", "mascara"]},
                {"id": "auditivo", "nome": "Protecao Auditiva", "exemplos": ["protetor_auricular", "abafador"]},
                {"id": "respiratorio", "nome": "Protecao Respiratoria", "exemplos": ["respirador", "mascara_pff2"]},
                {"id": "tronco", "nome": "Protecao do Tronco", "exemplos": ["avental", "colete"]},
                {"id": "membros_superiores", "nome": "Protecao Membros Superiores", "exemplos": ["luvas", "mangotes"]},
                {
                    "id": "membros_inferiores",
                    "nome": "Protecao Membros Inferiores",
                    "exemplos": ["calcado_seguranca", "perneira"],
                },
                {"id": "corpo_inteiro", "nome": "Protecao Corpo Inteiro", "exemplos": ["macacao", "conjunto"]},
                {"id": "quedas", "nome": "Protecao Contra Quedas", "exemplos": ["cinturao", "trava_quedas"]},
            ],
        }

    # ==========================================================================
    # Statistics
    # ==========================================================================

    def get_statistics(self) -> dict[str, Any]:
        """Retorna estatisticas de EPI."""
        if not self.db:
            return {
                "total_epis_ativos": 0,
                "entregas_ano": 0,
                "itens_baixo_estoque": 0,
                "assinaturas_pendentes": 0,
            }

        from sqlalchemy import text

        try:
            total_epis = (
                self.db.execute(text("SELECT count(*) FROM health_epi_catalog WHERE ativo = true")).scalar() or 0
            )

            total_deliveries = (
                self.db.execute(
                    text(
                        "SELECT count(*) FROM gp_epi_deliveries WHERE extract(year from data_entrega) = extract(year from current_date)"
                    )
                ).scalar()
                or 0
            )

            low_stock = (
                self.db.execute(
                    text("SELECT count(*) FROM health_epi_inventory WHERE quantidade_disponivel < quantidade_minima")
                ).scalar()
                or 0
            )

            pending_signatures = (
                self.db.execute(
                    text("SELECT count(*) FROM gp_epi_deliveries WHERE assinatura_funcionario IS NULL")
                ).scalar()
                or 0
            )

            return {
                "total_epis_ativos": total_epis,
                "entregas_ano": total_deliveries,
                "itens_baixo_estoque": low_stock,
                "assinaturas_pendentes": pending_signatures,
            }
        except Exception as e:
            logger.error("Erro ao consultar estatisticas EPI: %s", e)
            return {
                "total_epis_ativos": 0,
                "entregas_ano": 0,
                "itens_baixo_estoque": 0,
                "assinaturas_pendentes": 0,
            }
