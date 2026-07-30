"""
Service para Visita.
"""

from datetime import date, time
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from modules.campo.models.visita import ResultadoVisita, StatusVisita, Visita
from modules.campo.repositories.visita_repository import VisitaRepository
from modules.campo.schemas.visita import (
    VisitaCreate,
    VisitaDashboardStats,
    VisitaFiltro,
    VisitaListItem,
    VisitaPaginatedResponse,
    VisitaUpdate,
)


def visita_to_pdf_dict(v) -> dict:
    """Monta o dict esperado por build_visit_report_pdf a partir de uma Visita real.

    Fonte ÚNICA do endpoint /campo/visitas/{id}/pdf e da tool gera-doc do chat (Fase 6 F4)
    — render fiel do registro, sem fabricar nem gravar. Não duplicar essa montagem.
    """
    def g(k, d=""):
        val = getattr(v, k, None)
        if isinstance(val, list):
            val = ", ".join(str(x) for x in val)
        elif isinstance(val, dict):
            val = "; ".join(f"{kk}: {vv}" for kk, vv in val.items())
        return val if val not in (None, "") else d

    dv = getattr(v, "data_visita", None)
    return {
        "numero": g("numero"),
        "tipo": g("tipo"),
        "cliente_nome": g("prospect_empresa") or g("prospect_nome") or g("responsavel_nome") or "—",
        "data_visita": dv.strftime("%d/%m/%Y") if hasattr(dv, "strftime") else str(dv or ""),
        "responsavel": g("responsavel_nome"),
        "descricao": g("descricao_atendimento"),
        "situacao_atual": g("objetivo"),
        "diagnostico_tecnico": g("levantamento"),
        "achados": g("necessidades_identificadas"),
        "oportunidade_comercial": g("interesse_nivel"),
        "proximos_passos": g("proximos_passos"),
        "panorama": g("resultado"),
        "corpo": g("descricao_atendimento"),
    }


class VisitaService:
    """Service para logica de negocio de Visita."""

    def __init__(self, db: AsyncSession) -> None:
        """Inicializa o service."""
        self.db = db
        self.repository = VisitaRepository(db)

    # =========================================================================
    # CRUD
    # =========================================================================

    async def criar_visita(self, data: VisitaCreate, created_by: UUID = None) -> Visita:
        """Cria uma nova visita."""
        return await self.repository.create(data, created_by)

    async def obter_visita(self, visita_id: UUID) -> Visita | None:
        """Obtem visita por ID."""
        return await self.repository.get_by_id(visita_id)

    async def obter_visita_por_numero(self, numero: str) -> Visita | None:
        """Obtem visita por numero."""
        return await self.repository.get_by_numero(numero)

    async def atualizar_visita(self, visita_id: UUID, data: VisitaUpdate, updated_by: UUID = None) -> Visita | None:
        """Atualiza uma visita."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None
        return await self.repository.update(visita, data, updated_by)

    async def excluir_visita(self, visita_id: UUID) -> bool:
        """Exclui uma visita (soft delete)."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return False
        return await self.repository.delete(visita)

    # =========================================================================
    # LISTAGEM
    # =========================================================================

    async def listar_visitas(
        self,
        filtro: VisitaFiltro | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> VisitaPaginatedResponse:
        """Lista visitas com paginacao."""
        skip = (page - 1) * page_size
        items, total = await self.repository.list_all(filtro, skip, page_size)

        return VisitaPaginatedResponse(
            items=[VisitaListItem.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )

    async def listar_visitas_responsavel(
        self,
        responsavel_id: UUID,
        data: date | None = None,
        apenas_agendadas: bool = False,
    ) -> list[Visita]:
        """Lista visitas de um responsavel."""
        return await self.repository.list_by_responsavel(responsavel_id, data, apenas_agendadas)

    async def listar_visitas_cliente(self, cliente_id: UUID) -> list[Visita]:
        """Lista visitas de um cliente."""
        return await self.repository.list_by_cliente(cliente_id)

    async def listar_visitas_lead(self, lead_id: UUID) -> list[Visita]:
        """Lista visitas de um lead."""
        return await self.repository.list_by_lead(lead_id)

    async def listar_pendentes_confirmacao(self) -> list[Visita]:
        """Lista visitas que precisam confirmacao."""
        return await self.repository.list_pendentes_confirmacao()

    # =========================================================================
    # ACOES DO FLUXO
    # =========================================================================

    async def confirmar_visita(
        self,
        visita_id: UUID,
        confirmado_por: str = None,
    ) -> Visita | None:
        """Confirma uma visita."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        if visita.status != StatusVisita.AGENDADA:
            raise ValueError(f"Visita em status {visita.status.value} nao pode ser confirmada")

        visita.confirmar(confirmado_por)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def iniciar_deslocamento(self, visita_id: UUID) -> Visita | None:
        """Marca inicio do deslocamento."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        if visita.status not in [StatusVisita.AGENDADA, StatusVisita.CONFIRMADA]:
            raise ValueError(f"Visita em status {visita.status.value} nao pode iniciar deslocamento")

        visita.iniciar_deslocamento()
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def fazer_checkin(
        self,
        visita_id: UUID,
        latitude: float = None,
        longitude: float = None,
    ) -> Visita | None:
        """Registra check-in no local."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        if visita.status not in [StatusVisita.AGENDADA, StatusVisita.CONFIRMADA, StatusVisita.EM_DESLOCAMENTO]:
            raise ValueError(f"Visita em status {visita.status.value} nao pode fazer check-in")

        visita.fazer_checkin(latitude, longitude)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def fazer_checkout(
        self,
        visita_id: UUID,
        latitude: float = None,
        longitude: float = None,
    ) -> Visita | None:
        """Registra check-out do local."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.fazer_checkout(latitude, longitude)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def registrar_resultado(
        self,
        visita_id: UUID,
        resultado: ResultadoVisita,
        descricao: str = None,
        proximos_passos: str = None,
    ) -> Visita | None:
        """Registra resultado da visita."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.registrar_resultado(resultado, descricao, proximos_passos)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def cancelar_visita(
        self,
        visita_id: UUID,
        motivo: str,
        cancelado_por: UUID,
    ) -> Visita | None:
        """Cancela uma visita."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        if visita.status == StatusVisita.REALIZADA:
            raise ValueError("Visita ja realizada nao pode ser cancelada")

        visita.cancelar(motivo, cancelado_por)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def reagendar_visita(
        self,
        visita_id: UUID,
        nova_data: date,
        novo_horario: time,
        motivo: str,
    ) -> Visita | None:
        """Reagenda uma visita."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        if visita.status in [StatusVisita.REALIZADA, StatusVisita.CANCELADA]:
            raise ValueError(f"Visita em status {visita.status.value} nao pode ser reagendada")

        visita.reagendar(nova_data, novo_horario, motivo)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    # =========================================================================
    # CONVERSAO COMERCIAL
    # =========================================================================

    async def registrar_interesse(
        self,
        visita_id: UUID,
        nivel: int,
        servicos: list[dict] = None,
    ) -> Visita | None:
        """Registra nivel de interesse."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        if nivel < 1 or nivel > 5:
            raise ValueError("Nivel de interesse deve ser entre 1 e 5")

        visita.registrar_interesse(nivel, servicos)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def vincular_proposta(
        self,
        visita_id: UUID,
        proposta_id: UUID,
        valor: Decimal,
    ) -> Visita | None:
        """Vincula proposta gerada a visita."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.gerar_proposta(proposta_id, valor)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def registrar_contrato(
        self,
        visita_id: UUID,
        contrato_id: UUID,
        valor: Decimal,
    ) -> Visita | None:
        """Registra fechamento de contrato."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.fechar_contrato(contrato_id, valor)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def registrar_nao_fechamento(
        self,
        visita_id: UUID,
        motivo: str,
        concorrente: str = None,
    ) -> Visita | None:
        """Registra motivo de nao fechamento."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.registrar_nao_fechamento(motivo, concorrente)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    # =========================================================================
    # LEVANTAMENTO TECNICO
    # =========================================================================

    async def adicionar_levantamento(
        self,
        visita_id: UUID,
        dados: dict,
    ) -> Visita | None:
        """Adiciona dados de levantamento tecnico."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.adicionar_levantamento(dados)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    async def adicionar_necessidade(
        self,
        visita_id: UUID,
        categoria: str,
        descricao: str,
        prioridade: int = 3,
        estimativa: Decimal = None,
    ) -> Visita | None:
        """Adiciona necessidade identificada."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.adicionar_necessidade(categoria, descricao, prioridade, estimativa)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    # =========================================================================
    # FOLLOW-UP
    # =========================================================================

    async def agendar_followup(
        self,
        visita_id: UUID,
        data: date,
        tipo: str,
        observacoes: str = None,
    ) -> Visita | None:
        """Agenda follow-up."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.agendar_followup(data, tipo, observacoes)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    # =========================================================================
    # FOTOS
    # =========================================================================

    async def adicionar_foto(
        self,
        visita_id: UUID,
        url: str,
        descricao: str = None,
        tipo: str = "geral",
    ) -> Visita | None:
        """Adiciona foto a visita."""
        visita = await self.repository.get_by_id(visita_id)
        if not visita:
            return None

        visita.adicionar_foto(url, descricao, tipo)
        await self.db.commit()
        await self.db.refresh(visita)
        return visita

    # =========================================================================
    # ESTATISTICAS
    # =========================================================================

    async def obter_estatisticas(
        self,
        responsavel_id: UUID = None,
        periodo_dias: int = 30,
    ) -> VisitaDashboardStats:
        """Obtem estatisticas de visitas."""
        return await self.repository.get_stats(responsavel_id, periodo_dias)
