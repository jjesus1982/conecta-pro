"""
Service para Ordem de Servico.
"""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.campo.models.ordem_servico import OrdemServico, StatusOS
from modules.campo.repositories.ordem_servico_repository import OrdemServicoRepository
from modules.campo.schemas.ordem_servico import (
    OrdemServicoCreate,
    OrdemServicoListItem,
    OrdemServicoUpdate,
    OSDashboardStats,
    OSFiltro,
    OSPaginatedResponse,
)


class OrdemServicoService:
    """Service para logica de negocio de Ordem de Servico."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o service."""
        self.db = db
        self.repository = OrdemServicoRepository(db)

    # =========================================================================
    # CRUD
    # =========================================================================

    async def criar_os(self, data: OrdemServicoCreate, created_by: UUID = None) -> OrdemServico:
        """Cria uma nova OS."""
        return await self.repository.create(data, created_by)

    async def obter_os(self, os_id: UUID) -> OrdemServico | None:
        """Obtem OS por ID."""
        return await self.repository.get_by_id(os_id)

    async def obter_os_por_numero(self, numero: str) -> OrdemServico | None:
        """Obtem OS por numero."""
        return await self.repository.get_by_numero(numero)

    async def atualizar_os(self, os_id: UUID, data: OrdemServicoUpdate, updated_by: UUID = None) -> OrdemServico | None:
        """Atualiza uma OS."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None
        return await self.repository.update(os, data, updated_by)

    async def excluir_os(self, os_id: UUID) -> bool:
        """Exclui uma OS (soft delete)."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return False
        return await self.repository.delete(os)

    # =========================================================================
    # LISTAGEM
    # =========================================================================

    async def listar_os(
        self,
        filtro: OSFiltro | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> OSPaginatedResponse:
        """Lista OS com paginacao."""
        skip = (page - 1) * page_size
        items, total = await self.repository.list_all(filtro, skip, page_size)

        return OSPaginatedResponse(
            items=[OrdemServicoListItem.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )

    async def listar_os_cliente(self, cliente_id: UUID) -> list[OrdemServico]:
        """Lista OS de um cliente."""
        return await self.repository.list_by_cliente(cliente_id)

    async def listar_os_tecnico(
        self,
        tecnico_id: UUID,
        data: date | None = None,
        apenas_abertas: bool = False,
    ) -> list[OrdemServico]:
        """Lista OS de um tecnico."""
        return await self.repository.list_by_tecnico(tecnico_id, data, apenas_abertas)

    async def listar_os_atrasadas(self) -> list[OrdemServico]:
        """Lista OS com SLA vencido."""
        return await self.repository.list_atrasadas()

    # =========================================================================
    # ACOES DO FLUXO
    # =========================================================================

    async def agendar_os(
        self,
        os_id: UUID,
        data_agendada: date,
        horario_inicio: time,
        horario_fim: time = None,
        tecnico_id: UUID = None,
    ) -> OrdemServico | None:
        """Agenda uma OS."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if os.status not in [StatusOS.ABERTA, StatusOS.RASCUNHO, StatusOS.REAGENDADA]:
            raise ValueError(f"OS em status {os.status.value} nao pode ser agendada")

        os.agendar(data_agendada, horario_inicio, horario_fim, tecnico_id)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def iniciar_deslocamento(self, os_id: UUID) -> OrdemServico | None:
        """Marca inicio do deslocamento."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if os.status != StatusOS.AGENDADA:
            raise ValueError(f"OS em status {os.status.value} nao pode iniciar deslocamento")

        os.iniciar_deslocamento()
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def fazer_checkin(
        self,
        os_id: UUID,
        latitude: float = None,
        longitude: float = None,
    ) -> OrdemServico | None:
        """Registra check-in no local."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if os.status not in [StatusOS.AGENDADA, StatusOS.EM_DESLOCAMENTO]:
            raise ValueError(f"OS em status {os.status.value} nao pode fazer check-in")

        os.fazer_checkin(latitude, longitude)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def fazer_checkout(
        self,
        os_id: UUID,
        latitude: float = None,
        longitude: float = None,
    ) -> OrdemServico | None:
        """Registra check-out do local."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if os.status != StatusOS.EM_ANDAMENTO:
            raise ValueError(f"OS em status {os.status.value} nao pode fazer check-out")

        os.fazer_checkout(latitude, longitude)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def pausar_os(self, os_id: UUID, motivo: str = None) -> OrdemServico | None:
        """Pausa uma OS em andamento."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if os.status != StatusOS.EM_ANDAMENTO:
            raise ValueError(f"OS em status {os.status.value} nao pode ser pausada")

        os.pausar(motivo)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def retomar_os(self, os_id: UUID) -> OrdemServico | None:
        """Retoma uma OS pausada."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if os.status != StatusOS.PAUSADA:
            raise ValueError(f"OS em status {os.status.value} nao pode ser retomada")

        os.retomar()
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def concluir_os(self, os_id: UUID, solucao: str = None) -> OrdemServico | None:
        """Conclui uma OS."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        # Permite a conclusão a partir de qualquer status ativo (operador de mesa pode
        # fechar uma OS resolvida sem depender do app de campo p/ passar por em_andamento).
        if os.status in [StatusOS.CONCLUIDA, StatusOS.CANCELADA, StatusOS.RASCUNHO]:
            raise ValueError(f"OS em status {os.status.value} nao pode ser concluida")

        os.concluir(solucao)
        os.calcular_valores()
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def cancelar_os(self, os_id: UUID, motivo: str, cancelado_por: UUID) -> OrdemServico | None:
        """Cancela uma OS."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if os.status == StatusOS.CONCLUIDA:
            raise ValueError("OS ja concluida nao pode ser cancelada")

        os.cancelar(motivo, cancelado_por)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def reagendar_os(self, os_id: UUID, nova_data: date, motivo: str) -> OrdemServico | None:
        """Reagenda uma OS."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if os.status in [StatusOS.CONCLUIDA, StatusOS.CANCELADA]:
            raise ValueError(f"OS em status {os.status.value} nao pode ser reagendada")

        os.reagendar(nova_data, motivo)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    # =========================================================================
    # AVALIACAO E ASSINATURA
    # =========================================================================

    async def registrar_avaliacao(
        self,
        os_id: UUID,
        nota: int,
        comentario: str = None,
    ) -> OrdemServico | None:
        """Registra avaliacao do cliente."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if nota < 1 or nota > 5:
            raise ValueError("Nota deve ser entre 1 e 5")

        os.registrar_avaliacao(nota, comentario)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    async def registrar_assinatura(
        self,
        os_id: UUID,
        url: str,
        nome: str,
        documento: str = None,
    ) -> OrdemServico | None:
        """Registra assinatura do cliente."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        os.registrar_assinatura(url, nome, documento)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    # =========================================================================
    # FOTOS
    # =========================================================================

    async def adicionar_foto(
        self,
        os_id: UUID,
        tipo: str,
        url: str,
        descricao: str = None,
    ) -> OrdemServico | None:
        """Adiciona foto a OS."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        if tipo not in ["antes", "durante", "depois"]:
            raise ValueError("Tipo de foto invalido")

        os.adicionar_foto(tipo, url, descricao)
        await self.db.commit()
        await self.db.refresh(os)
        return os

    # =========================================================================
    # MATERIAIS
    # =========================================================================

    async def atualizar_materiais(
        self,
        os_id: UUID,
        materiais_utilizados: list[dict],
    ) -> OrdemServico | None:
        """Atualiza materiais utilizados."""
        os = await self.repository.get_by_id(os_id)
        if not os:
            return None

        os.materiais_utilizados = materiais_utilizados

        # Recalcular valor de materiais
        valor_materiais = sum(
            Decimal(str(m.get("valor_unitario", 0))) * m.get("quantidade", 1) for m in materiais_utilizados
        )
        os.valor_materiais = valor_materiais
        os.calcular_valores()

        await self.db.commit()
        await self.db.refresh(os)
        return os

    # =========================================================================
    # ESTATISTICAS
    # =========================================================================

    async def obter_estatisticas(
        self,
        cliente_id: UUID = None,
        tecnico_id: UUID = None,
        periodo_dias: int = 30,
    ) -> OSDashboardStats:
        """Obtem estatisticas de OS."""
        return await self.repository.get_stats(cliente_id, tecnico_id, periodo_dias)
