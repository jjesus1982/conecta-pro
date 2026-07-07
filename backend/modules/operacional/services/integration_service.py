"""
Serviço de Integração Diaristas-Operacional.

Fornece funcionalidades para:
- Alocar diaristas a postos de trabalho
- Vincular schedules de diaristas a shifts
- Dashboard unificado de ocupação
- Métricas consolidadas
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from modules.operacional.diaristas.models import (
    Diarist,
    DiaristAssignment,
    DiaristSchedule,
    DiaristStatus,
)
from modules.operacional.models import (
    Allocation,
    AllocationStatus,
    Post,
    PostStatus,
    Scale,
    ScaleStatus,
    Shift,
    ShiftStatus,
)

logger = logging.getLogger(__name__)


class IntegrationService:
    """Serviço de integração entre Diaristas e módulo Operacional."""

    def __init__(self, db: Session):
        self.db = db

    # =========================================================================
    # ALOCAÇÃO DE DIARISTAS A POSTOS
    # =========================================================================

    # Valores REAIS dos ENUMs do PostgreSQL (fonte: \d diarist_assignments).
    # ATENÇÃO: os StrEnums em diaristas/models/diarist.py (AssignmentStatus/
    # AssignmentType/RecurrenceType) estão DESALINHADOS do banco — usar os
    # literais abaixo em escrita, senão o INSERT falha com
    # "invalid input value for enum".
    _PG_ASSIGNMENT_STATUS_ATIVO = "ATIVO"  # assignment_status: ATIVO|PAUSADO|ENCERRADO|CANCELADO
    _PG_ASSIGNMENT_STATUS_ENCERRADO = "ENCERRADO"
    _PG_ASSIGNMENT_STATUS_OCUPANTES = ("ATIVO", "PAUSADO")  # bloqueiam nova alocação
    _PG_ASSIGNMENT_TIPO_CONDOMINIO = "CONDOMINIO"  # assignment_type: CONDOMINIO|UNIDADE|AREA_COMUM
    _PG_ASSIGNMENT_TIPO_UNIDADE = "UNIDADE"
    _PG_RECORRENCIA_AVULSO = "AVULSO"  # recurrence_type: AVULSO|SEMANAL|QUINZENAL|MENSAL

    def alocar_diarista_posto(
        self,
        diarista_id: UUID,
        condominio_id: UUID,
        data_inicio: date,
        data_fim: date | None = None,
        unidade_id: UUID | None = None,
        valor_acordado: Decimal | None = None,
        observacoes: str | None = None,
    ) -> DiaristAssignment:
        """
        Aloca um diarista a um condomínio (schema atual de diarist_assignments).

        REWRITE (Ciclo 3, item 15): o schema antigo (post_id, shift_id,
        cliente_id, contrato_id, client_name, location, start_date, end_date,
        notes, created_by) NÃO EXISTE MAIS. O schema atual usa
        condominio_id/unidade_id/data_inicio/data_fim/observacoes.
        Parâmetros antigos SEM equivalente foram removidos:
        - post_id      → substituído por condominio_id (tabela condominios)
        - shift_id     → sem coluna equivalente (turno agora é hora_inicio/hora_fim)
        - cliente_id   → sem coluna equivalente
        - contrato_id  → sem coluna equivalente
        - created_by   → sem coluna equivalente

        Args:
            diarista_id: ID do diarista (tabela diarists)
            condominio_id: ID do condomínio (tabela condominios) — NOT NULL no banco
            data_inicio: Data de início da alocação
            data_fim: Data de fim (opcional, para alocações temporárias)
            unidade_id: ID da unidade dentro do condomínio (opcional)
            valor_acordado: Valor acordado; se None, usa diarists.valor_diaria do cadastro
            observacoes: Observações adicionais

        Returns:
            DiaristAssignment criado
        """
        # Verificar diarista existe e está ativo (diarists.ativo boolean + status varchar)
        diarista = self.db.query(Diarist).filter(Diarist.id == diarista_id, Diarist.ativo.is_(True)).first()

        if not diarista:
            raise ValueError(f"Diarista {diarista_id} não encontrado ou inativo")

        if diarista.status != DiaristStatus.ATIVO.value:
            raise ValueError(f"Diarista não está disponível. Status: {diarista.status}")

        # Verificar condomínio existe (tabela condominios não tem model ORM neste módulo;
        # diarist_assignments.condominio_id também não tem FK no banco — validar via SQL)
        condominio_existe = self.db.execute(
            text("SELECT 1 FROM condominios WHERE id = :cid"), {"cid": str(condominio_id)}
        ).first()

        if not condominio_existe:
            raise ValueError(f"Condomínio {condominio_id} não encontrado")

        # Verificar se não há conflito de alocação vigente no período
        # (períodos se sobrepõem: existente.data_inicio <= novo_fim E
        #  (existente.data_fim IS NULL OU existente.data_fim >= novo_inicio))
        conflito_query = self.db.query(DiaristAssignment).filter(
            DiaristAssignment.diarist_id == diarista_id,
            DiaristAssignment.status.in_(self._PG_ASSIGNMENT_STATUS_OCUPANTES),
            or_(DiaristAssignment.data_fim.is_(None), DiaristAssignment.data_fim >= data_inicio),
        )
        if data_fim is not None:
            conflito_query = conflito_query.filter(DiaristAssignment.data_inicio <= data_fim)

        conflito = conflito_query.first()

        if conflito:
            raise ValueError(f"Diarista já possui alocação ativa no período: Assignment {conflito.id}")

        # Criar assignment (somente colunas REAIS de diarist_assignments).
        # tipo/status/recorrencia: literais dos ENUMs do PG — os defaults do
        # model ("avulso"/"rascunho"/"nenhuma") são inválidos no banco.
        # dias_semana=None explícito: o default do model ([] via JSONB) é
        # incompatível com a coluna weekday_array2[] do banco.
        assignment = DiaristAssignment(
            diarist_id=diarista_id,
            condominio_id=condominio_id,
            unidade_id=unidade_id,
            tipo=self._PG_ASSIGNMENT_TIPO_UNIDADE if unidade_id else self._PG_ASSIGNMENT_TIPO_CONDOMINIO,
            data_inicio=data_inicio,
            data_fim=data_fim,
            recorrencia=self._PG_RECORRENCIA_AVULSO,
            dias_semana=None,
            valor_acordado=valor_acordado if valor_acordado is not None else diarista.valor_diaria,
            status=self._PG_ASSIGNMENT_STATUS_ATIVO,
            observacoes=observacoes,
        )

        self.db.add(assignment)

        # NOTA: DiaristStatus atual (ativo/inativo/suspenso/...) não tem valor
        # "em serviço" (antigo ON_ASSIGNMENT não existe mais) — o status do
        # diarista NÃO é alterado; "em serviço" deriva das alocações ATIVO.

        self.db.commit()
        self.db.refresh(assignment)

        logger.info(
            f"Diarista {diarista_id} alocado ao condomínio {condominio_id} "
            f"de {data_inicio} até {data_fim or 'indefinido'}"
        )

        return assignment

    def desalocar_diarista_posto(
        self,
        assignment_id: UUID,
        motivo: str | None = None,
    ) -> DiaristAssignment:
        """
        Encerra a alocação de um diarista (schema atual de diarist_assignments).

        REWRITE (Ciclo 3, item 15): encerrar = status ENCERRADO + data_fim=hoje.
        Parâmetro antigo removido sem equivalente:
        - updated_by → sem coluna equivalente no schema atual

        Args:
            assignment_id: ID da alocação
            motivo: Motivo da desalocação (anexado em observacoes)

        Returns:
            DiaristAssignment atualizado
        """
        assignment = self.db.query(DiaristAssignment).filter(DiaristAssignment.id == assignment_id).first()

        if not assignment:
            raise ValueError(f"Assignment {assignment_id} não encontrado")

        if assignment.status == self._PG_ASSIGNMENT_STATUS_ENCERRADO:
            raise ValueError(f"Assignment {assignment_id} já está encerrado")

        assignment.status = self._PG_ASSIGNMENT_STATUS_ENCERRADO
        assignment.data_fim = date.today()
        if motivo:
            assignment.observacoes = ((assignment.observacoes or "") + f"\nDesalocação: {motivo}").strip()

        # NOTA: sem equivalente para o antigo "voltar diarista para ACTIVE" —
        # DiaristStatus atual não tem ON_ASSIGNMENT; o status do diarista não
        # é alterado na alocação, portanto nada a reverter aqui.

        self.db.commit()
        self.db.refresh(assignment)

        logger.info(f"Assignment {assignment_id} encerrado (data_fim={assignment.data_fim})")

        return assignment

    # =========================================================================
    # DASHBOARD UNIFICADO
    # =========================================================================

    def get_dashboard_unificado(
        self,
        data_referencia: date | None = None,
        cliente_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Retorna dashboard unificado com métricas de operacional e diaristas.

        Args:
            data_referencia: Data de referência (default: hoje)
            cliente_id: Filtrar por cliente específico

        Returns:
            Dict com métricas consolidadas
        """
        data_ref = data_referencia or date.today()

        # Métricas de Postos
        postos_query = self.db.query(Post)
        if cliente_id:
            postos_query = postos_query.filter(Post.client_id == cliente_id)

        total_postos = postos_query.count()
        postos_ativos = postos_query.filter(Post.status == PostStatus.ACTIVE).count()
        postos_inativos = postos_query.filter(Post.status == PostStatus.INACTIVE).count()

        # Métricas de Escalas
        escalas_query = self.db.query(Scale).filter(Scale.start_date <= data_ref, Scale.end_date >= data_ref)

        escalas_ativas = escalas_query.filter(Scale.status == ScaleStatus.ACTIVE).count()
        escalas_em_execucao = escalas_query.filter(Scale.status == ScaleStatus.IN_PROGRESS).count()

        # Métricas de Turnos do dia
        turnos_hoje = self.db.query(Shift).filter(func.date(Shift.start_time) == data_ref).count()

        turnos_em_andamento = (
            self.db.query(Shift)
            .filter(func.date(Shift.start_time) == data_ref, Shift.status == ShiftStatus.IN_PROGRESS)
            .count()
        )

        # Métricas de Alocações (funcionários fixos)
        alocacoes_ativas = self.db.query(Allocation).filter(Allocation.status == AllocationStatus.ACTIVE).count()

        # Métricas de Diaristas
        total_diaristas = self.db.query(Diarist).filter(Diarist.is_active).count()

        diaristas_ativos = (
            self.db.query(Diarist).filter(Diarist.is_active, Diarist.status == DiaristStatus.ACTIVE).count()
        )

        diaristas_em_servico = (
            self.db.query(Diarist).filter(Diarist.is_active, Diarist.status == DiaristStatus.ON_ASSIGNMENT).count()
        )

        diaristas_suspensos = (
            self.db.query(Diarist).filter(Diarist.is_active, Diarist.status == DiaristStatus.SUSPENDED).count()
        )

        # Assignments de diaristas do dia
        assignments_hoje = (
            self.db.query(DiaristAssignment)
            .filter(
                DiaristAssignment.status == "active",
                DiaristAssignment.start_date <= data_ref,
                or_(DiaristAssignment.end_date.is_(None), DiaristAssignment.end_date >= data_ref),
            )
            .count()
        )

        # Schedules de diaristas do dia
        schedules_hoje = self.db.query(DiaristSchedule).filter(DiaristSchedule.date == data_ref).count()

        schedules_confirmados = (
            self.db.query(DiaristSchedule)
            .filter(DiaristSchedule.date == data_ref, DiaristSchedule.status == "confirmed")
            .count()
        )

        schedules_checkin = (
            self.db.query(DiaristSchedule)
            .filter(DiaristSchedule.date == data_ref, DiaristSchedule.actual_check_in.isnot(None))
            .count()
        )

        # Calcular taxa de ocupação
        capacidade_postos = postos_ativos * 3  # Assumindo 3 turnos por posto
        ocupacao_funcionarios = alocacoes_ativas
        ocupacao_diaristas = assignments_hoje
        ocupacao_total = ocupacao_funcionarios + ocupacao_diaristas
        taxa_ocupacao = (ocupacao_total / capacidade_postos * 100) if capacidade_postos > 0 else 0

        return {
            "data_referencia": data_ref.isoformat(),
            "postos": {
                "total": total_postos,
                "ativos": postos_ativos,
                "inativos": postos_inativos,
            },
            "escalas": {
                "ativas": escalas_ativas,
                "em_execucao": escalas_em_execucao,
            },
            "turnos": {
                "hoje": turnos_hoje,
                "em_andamento": turnos_em_andamento,
            },
            "funcionarios": {
                "alocacoes_ativas": alocacoes_ativas,
            },
            "diaristas": {
                "total": total_diaristas,
                "disponiveis": diaristas_ativos,
                "em_servico": diaristas_em_servico,
                "suspensos": diaristas_suspensos,
                "assignments_hoje": assignments_hoje,
                "schedules_hoje": schedules_hoje,
                "schedules_confirmados": schedules_confirmados,
                "com_checkin": schedules_checkin,
            },
            "ocupacao": {
                "capacidade_estimada": capacidade_postos,
                "funcionarios_alocados": ocupacao_funcionarios,
                "diaristas_alocados": ocupacao_diaristas,
                "total_alocado": ocupacao_total,
                "taxa_ocupacao_percentual": round(taxa_ocupacao, 2),
            },
            "alertas": self._gerar_alertas(data_ref),
        }

    def _gerar_alertas(self, data_referencia: date) -> list[dict[str, Any]]:
        """Gera alertas automáticos baseados na situação atual."""
        alertas = []

        # Alerta: Postos sem cobertura
        postos_sem_cobertura = (
            self.db.query(Post)
            .filter(Post.status == PostStatus.ACTIVE)
            .outerjoin(Allocation, and_(Allocation.post_id == Post.id, Allocation.status == AllocationStatus.ACTIVE))
            .filter(Allocation.id.is_(None))
            .count()
        )

        if postos_sem_cobertura > 0:
            alertas.append(
                {
                    "tipo": "warning",
                    "categoria": "cobertura",
                    "mensagem": f"{postos_sem_cobertura} posto(s) sem funcionário fixo alocado",
                    "acao_sugerida": "Alocar funcionário ou diarista aos postos descobertos",
                }
            )

        # Alerta: Diaristas com check-in atrasado
        agora = datetime.now()
        if agora.hour >= 8:  # Após 8h
            schedules_atrasados = (
                self.db.query(DiaristSchedule)
                .filter(
                    DiaristSchedule.date == data_referencia,
                    DiaristSchedule.status == "confirmed",
                    DiaristSchedule.actual_check_in.is_(None),
                    DiaristSchedule.scheduled_start <= agora.time(),
                )
                .count()
            )

            if schedules_atrasados > 0:
                alertas.append(
                    {
                        "tipo": "error",
                        "categoria": "presenca",
                        "mensagem": f"{schedules_atrasados} diarista(s) com check-in atrasado",
                        "acao_sugerida": "Entrar em contato para verificar situação",
                    }
                )

        # Alerta: Poucos diaristas disponíveis
        diaristas_disponiveis = (
            self.db.query(Diarist).filter(Diarist.is_active, Diarist.status == DiaristStatus.ACTIVE).count()
        )

        if diaristas_disponiveis < 5:
            alertas.append(
                {
                    "tipo": "info",
                    "categoria": "disponibilidade",
                    "mensagem": f"Apenas {diaristas_disponiveis} diarista(s) disponível(is)",
                    "acao_sugerida": "Considerar recrutar mais diaristas",
                }
            )

        return alertas

    # =========================================================================
    # MÉTRICAS E RELATÓRIOS
    # =========================================================================

    def get_metricas_periodo(
        self,
        data_inicio: date,
        data_fim: date,
        cliente_id: UUID | None = None,
    ) -> dict[str, Any]:
        """
        Retorna métricas consolidadas para um período.

        Args:
            data_inicio: Data inicial do período
            data_fim: Data final do período
            cliente_id: Filtrar por cliente (opcional)

        Returns:
            Dict com métricas do período
        """
        # Total de dias no período
        dias_periodo = (data_fim - data_inicio).days + 1

        # Schedules de diaristas no período
        schedules_query = self.db.query(DiaristSchedule).filter(
            DiaristSchedule.date >= data_inicio, DiaristSchedule.date <= data_fim
        )

        total_schedules = schedules_query.count()
        schedules_realizados = schedules_query.filter(DiaristSchedule.status == "completed").count()
        schedules_cancelados = schedules_query.filter(DiaristSchedule.status == "cancelled").count()
        schedules_faltas = schedules_query.filter(DiaristSchedule.status == "no_show").count()

        # Horas trabalhadas
        horas_trabalhadas = self.db.query(func.sum(DiaristSchedule.hours_worked)).filter(
            DiaristSchedule.date >= data_inicio, DiaristSchedule.date <= data_fim, DiaristSchedule.status == "completed"
        ).scalar() or Decimal("0")

        # Taxa de comparecimento
        taxa_comparecimento = schedules_realizados / total_schedules * 100 if total_schedules > 0 else 0

        # Turnos do período (funcionários fixos)
        turnos_periodo = (
            self.db.query(Shift)
            .filter(func.date(Shift.start_time) >= data_inicio, func.date(Shift.start_time) <= data_fim)
            .count()
        )

        turnos_concluidos = (
            self.db.query(Shift)
            .filter(
                func.date(Shift.start_time) >= data_inicio,
                func.date(Shift.start_time) <= data_fim,
                Shift.status == ShiftStatus.COMPLETED,
            )
            .count()
        )

        return {
            "periodo": {
                "inicio": data_inicio.isoformat(),
                "fim": data_fim.isoformat(),
                "dias": dias_periodo,
            },
            "diaristas": {
                "total_schedules": total_schedules,
                "realizados": schedules_realizados,
                "cancelados": schedules_cancelados,
                "faltas": schedules_faltas,
                "taxa_comparecimento": round(taxa_comparecimento, 2),
                "horas_trabalhadas": float(horas_trabalhadas),
            },
            "funcionarios": {
                "total_turnos": turnos_periodo,
                "turnos_concluidos": turnos_concluidos,
                "taxa_conclusao": round(turnos_concluidos / turnos_periodo * 100 if turnos_periodo > 0 else 0, 2),
            },
            "consolidado": {
                "total_servicos": total_schedules + turnos_periodo,
                "servicos_concluidos": schedules_realizados + turnos_concluidos,
            },
        }

    def get_ocupacao_postos(
        self,
        data_referencia: date | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retorna ocupação detalhada de cada posto.

        Args:
            data_referencia: Data de referência (default: hoje)

        Returns:
            Lista com status de ocupação de cada posto
        """
        data_ref = data_referencia or date.today()

        postos = self.db.query(Post).filter(Post.status == PostStatus.ACTIVE).all()

        resultado = []

        for posto in postos:
            # Buscar alocações de funcionários fixos
            alocacoes = (
                self.db.query(Allocation)
                .filter(Allocation.post_id == posto.id, Allocation.status == AllocationStatus.ACTIVE)
                .all()
            )

            # Buscar assignments de diaristas
            assignments = (
                self.db.query(DiaristAssignment)
                .filter(
                    DiaristAssignment.post_id == posto.id,
                    DiaristAssignment.status == "active",
                    DiaristAssignment.start_date <= data_ref,
                    or_(DiaristAssignment.end_date.is_(None), DiaristAssignment.end_date >= data_ref),
                )
                .all()
            )

            resultado.append(
                {
                    "posto_id": str(posto.id),
                    "posto_nome": posto.name,
                    "posto_tipo": posto.type.value if hasattr(posto.type, "value") else str(posto.type),
                    "funcionarios_alocados": len(alocacoes),
                    "diaristas_alocados": len(assignments),
                    "total_alocados": len(alocacoes) + len(assignments),
                    "status": "coberto" if (alocacoes or assignments) else "descoberto",
                    "detalhes": {
                        "funcionarios": [
                            {"allocation_id": str(a.id), "employee_id": str(a.employee_id)} for a in alocacoes
                        ],
                        "diaristas": [
                            {"assignment_id": str(a.id), "diarist_id": str(a.diarist_id)} for a in assignments
                        ],
                    },
                }
            )

        return resultado

    def sugerir_diarista_posto(
        self,
        post_id: UUID,
        data: date,
        habilidades_requeridas: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Sugere diaristas disponíveis para um posto.

        Args:
            post_id: ID do posto
            data: Data desejada
            habilidades_requeridas: Lista de habilidades necessárias

        Returns:
            Lista de diaristas sugeridos ordenados por adequação

        PERFORMANCE OPTIMIZATION (2026-02-05):
        - Pre-fetch all schedules in single query to avoid N+1
        - Use set for O(1) conflict lookup
        - Reduces queries from N+1 to 2 queries total
        """
        # Buscar diaristas disponíveis
        diaristas_disponiveis = (
            self.db.query(Diarist).filter(Diarist.is_active, Diarist.status == DiaristStatus.ACTIVE).all()
        )

        if not diaristas_disponiveis:
            return []

        # PERFORMANCE: Pre-fetch all schedules in single query (evita N+1)
        diarista_ids = [d.id for d in diaristas_disponiveis]
        schedules_ocupados = (
            self.db.query(DiaristSchedule)
            .filter(
                DiaristSchedule.diarist_id.in_(diarista_ids),
                DiaristSchedule.date == data,
                DiaristSchedule.status.in_(["scheduled", "confirmed"]),
            )
            .all()
        )

        # Create set for O(1) lookup
        diaristas_ocupados_ids = {s.diarista_id for s in schedules_ocupados}

        # Filtrar quem não tem conflito na data
        sugestoes = []

        for diarista in diaristas_disponiveis:
            # PERFORMANCE: O(1) lookup instead of query
            if diarista.id in diaristas_ocupados_ids:
                continue

            # Calcular score de adequação
            score = 100
            motivos = []

            # Verificar habilidades
            if habilidades_requeridas and hasattr(diarista, "skills"):
                skills_diarista = diarista.skills or []
                matches = len(set(habilidades_requeridas) & set(skills_diarista))
                if matches < len(habilidades_requeridas):
                    score -= (len(habilidades_requeridas) - matches) * 10
                    motivos.append(f"Faltam {len(habilidades_requeridas) - matches} habilidades")

            # Verificar avaliação média
            if hasattr(diarista, "average_rating") and diarista.average_rating:
                if diarista.average_rating >= 4.5:
                    score += 10
                    motivos.append("Avaliação excelente")
                elif diarista.average_rating < 3.5:
                    score -= 20
                    motivos.append("Avaliação baixa")

            sugestoes.append(
                {
                    "diarist_id": str(diarista.id),
                    "nome": diarista.full_name,
                    "score": score,
                    "motivos": motivos,
                    "avaliacao": float(diarista.average_rating)
                    if hasattr(diarista, "average_rating") and diarista.average_rating
                    else None,
                    "total_servicos": diarista.total_assignments if hasattr(diarista, "total_assignments") else 0,
                }
            )

        # Ordenar por score
        sugestoes.sort(key=lambda x: x["score"], reverse=True)

        return sugestoes[:10]  # Top 10


# Singleton para uso global
def get_integration_service(db: Session) -> IntegrationService:
    """Factory function para obter instância do serviço."""
    return IntegrationService(db)
