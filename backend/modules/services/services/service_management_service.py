"""
ServiceManagementService - Lógica de Negócio
Sprint 31: Gestão de Serviços
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from modules.services.models import (
    OrderStatus,
    ServiceCatalog,
    ServiceExecution,
    ServiceOrder,
    ServiceReport,
    SLAConfig,
)
from modules.services.repositories import ServiceRepository
from modules.services.schemas import (
    ServiceCatalogCreate,
    ServiceCatalogUpdate,
    ServiceExecutionCreate,
    ServiceOrderCreate,
    ServiceOrderFilter,
    ServiceOrderUpdate,
    ServiceReportCreate,
    ServiceReportUpdate,
    SLAConfigCreate,
    SLAConfigUpdate,
)

logger = logging.getLogger(__name__)


class ServiceManagementService:
    """
    Serviço para gerenciamento de serviços.
    Implementa a lógica de negócio do módulo.
    """

    def __init__(self, db: Session):
        """
        Inicializa o serviço.

        Args:
            db: Sessão do banco de dados
        """
        self.db = db
        self.repository = ServiceRepository(db)

    # ============================================================
    # SERVICE CATALOG MANAGEMENT
    # ============================================================

    def create_service(self, data: ServiceCatalogCreate, user_id: UUID | None = None) -> ServiceCatalog:
        """
        Cria um novo serviço no catálogo.

        Args:
            data: Dados do serviço
            user_id: ID do usuário criador

        Returns:
            ServiceCatalog: Serviço criado
        """
        logger.info(f"Criando serviço: {data.name}")

        service = self.repository.create_service_catalog(data)

        if user_id:
            service.created_by = user_id

        self.db.commit()
        self.db.refresh(service)

        logger.info(f"Serviço criado: {service.id} - {service.code}")
        return service

    def update_service(
        self, service_id: UUID, data: ServiceCatalogUpdate, user_id: UUID | None = None
    ) -> ServiceCatalog | None:
        """
        Atualiza um serviço.

        Args:
            service_id: ID do serviço
            data: Dados para atualização
            user_id: ID do usuário

        Returns:
            ServiceCatalog ou None
        """
        service = self.repository.get_service_catalog_by_id(service_id)
        if not service:
            logger.warning(f"Serviço não encontrado: {service_id}")
            return None

        updated = self.repository.update_service_catalog(service_id, data)

        if updated and user_id:
            updated.updated_by = user_id
            self.db.commit()
            self.db.refresh(updated)

        logger.info(f"Serviço atualizado: {service_id}")
        return updated

    def activate_service(self, service_id: UUID) -> ServiceCatalog | None:
        """Ativa um serviço."""
        service = self.repository.get_service_catalog_by_id(service_id)
        if service:
            service.activate()
            self.db.commit()
            self.db.refresh(service)
            logger.info(f"Serviço ativado: {service_id}")
        return service

    def deactivate_service(self, service_id: UUID) -> ServiceCatalog | None:
        """Desativa um serviço."""
        service = self.repository.get_service_catalog_by_id(service_id)
        if service:
            service.deactivate()
            self.db.commit()
            self.db.refresh(service)
            logger.info(f"Serviço desativado: {service_id}")
        return service

    def discontinue_service(self, service_id: UUID) -> ServiceCatalog | None:
        """Descontinua um serviço."""
        service = self.repository.get_service_catalog_by_id(service_id)
        if service:
            service.discontinue()
            self.db.commit()
            self.db.refresh(service)
            logger.info(f"Serviço descontinuado: {service_id}")
        return service

    def calculate_service_price(
        self, service_id: UUID, quantity: float = 1.0, is_emergency: bool = False
    ) -> Decimal | None:
        """
        Calcula o preço de um serviço.

        Args:
            service_id: ID do serviço
            quantity: Quantidade
            is_emergency: Se é emergência

        Returns:
            Decimal ou None
        """
        service = self.repository.get_service_catalog_by_id(service_id)
        if not service:
            return None
        return service.calculate_price(quantity, is_emergency)

    # ============================================================
    # SERVICE ORDER MANAGEMENT
    # ============================================================

    def create_order(self, data: ServiceOrderCreate, user_id: UUID | None = None) -> ServiceOrder:
        """
        Cria uma nova ordem de serviço.

        Args:
            data: Dados da ordem
            user_id: ID do usuário

        Returns:
            ServiceOrder: Ordem criada
        """
        logger.info(f"Criando ordem de serviço: {data.title}")

        service = self.repository.get_service_catalog_by_id(data.service_id)
        if not service:
            raise ValueError(f"Serviço não encontrado: {data.service_id}")

        if not service.is_available:
            raise ValueError(f"Serviço indisponível: {service.name}")

        order = self.repository.create_service_order(data)

        if user_id:
            order.created_by = user_id

        if not data.estimated_value and service.base_price:
            order.estimated_value = service.base_price

        if service.requires_approval:
            order.status = OrderStatus.RASCUNHO
        else:
            order.submit()

        self.db.commit()
        self.db.refresh(order)

        logger.info(f"Ordem criada: {order.id} - {order.order_number}")
        return order

    def update_order(
        self, order_id: UUID, data: ServiceOrderUpdate, user_id: UUID | None = None
    ) -> ServiceOrder | None:
        """
        Atualiza uma ordem de serviço.

        Args:
            order_id: ID da ordem
            data: Dados para atualização
            user_id: ID do usuário

        Returns:
            ServiceOrder ou None
        """
        order = self.repository.get_service_order_by_id(order_id)
        if not order:
            logger.warning(f"Ordem não encontrada: {order_id}")
            return None

        if order.status in [OrderStatus.CONCLUIDA, OrderStatus.CANCELADA]:
            raise ValueError("Ordem finalizada não pode ser editada")

        updated = self.repository.update_service_order(order_id, data)

        if updated and user_id:
            updated.updated_by = user_id
            self.db.commit()
            self.db.refresh(updated)

        logger.info(f"Ordem atualizada: {order_id}")
        return updated

    def submit_order(self, order_id: UUID) -> ServiceOrder | None:
        """Submete uma ordem para aprovação."""
        order = self.repository.get_service_order_by_id(order_id)
        if order:
            order.submit()
            self.db.commit()
            self.db.refresh(order)
            logger.info(f"Ordem submetida: {order_id}")
        return order

    def approve_order(self, order_id: UUID, approver_id: UUID | None = None) -> ServiceOrder | None:
        """Aprova uma ordem de serviço."""
        order = self.repository.get_service_order_by_id(order_id)
        if order:
            order.approve()
            if approver_id:
                order.approved_by = approver_id
            self.db.commit()
            self.db.refresh(order)
            logger.info(f"Ordem aprovada: {order_id}")
        return order

    def reject_order(self, order_id: UUID, reason: str, rejector_id: UUID | None = None) -> ServiceOrder | None:
        """Rejeita uma ordem de serviço."""
        order = self.repository.get_service_order_by_id(order_id)
        if order:
            order.reject(reason)
            if rejector_id:
                order.updated_by = rejector_id
            self.db.commit()
            self.db.refresh(order)
            logger.info(f"Ordem rejeitada: {order_id}")
        return order

    def schedule_order(
        self,
        order_id: UUID,
        scheduled_date: date,
        time_start: str | None = None,
        time_end: str | None = None,
        technician_id: UUID | None = None,
        technician_name: str | None = None,
    ) -> ServiceOrder | None:
        """
        Agenda uma ordem de serviço.

        Args:
            order_id: ID da ordem
            scheduled_date: Data agendada
            time_start: Horário início
            time_end: Horário fim
            technician_id: ID do técnico
            technician_name: Nome do técnico

        Returns:
            ServiceOrder ou None
        """
        order = self.repository.get_service_order_by_id(order_id)
        if not order:
            return None

        order.schedule(scheduled_date, time_start, time_end)

        if technician_id or technician_name:
            order.assign_technician(technician_id, technician_name)

        self.db.commit()
        self.db.refresh(order)
        logger.info(f"Ordem agendada: {order_id} para {scheduled_date}")
        return order

    def start_order(self, order_id: UUID) -> ServiceOrder | None:
        """Inicia uma ordem de serviço."""
        order = self.repository.get_service_order_by_id(order_id)
        if order:
            order.start()
            self.db.commit()
            self.db.refresh(order)
            logger.info(f"Ordem iniciada: {order_id}")
        return order

    def pause_order(self, order_id: UUID, reason: str) -> ServiceOrder | None:
        """Pausa uma ordem de serviço."""
        order = self.repository.get_service_order_by_id(order_id)
        if order:
            order.pause(reason)
            self.db.commit()
            self.db.refresh(order)
            logger.info(f"Ordem pausada: {order_id}")
        return order

    def resume_order(self, order_id: UUID) -> ServiceOrder | None:
        """Retoma uma ordem pausada."""
        order = self.repository.get_service_order_by_id(order_id)
        if order:
            order.resume()
            self.db.commit()
            self.db.refresh(order)
            logger.info(f"Ordem retomada: {order_id}")
        return order

    def complete_order(
        self, order_id: UUID, final_value: Decimal | None = None, completion_notes: str | None = None
    ) -> ServiceOrder | None:
        """
        Conclui uma ordem de serviço.

        Args:
            order_id: ID da ordem
            final_value: Valor final
            completion_notes: Notas de conclusão

        Returns:
            ServiceOrder ou None
        """
        order = self.repository.get_service_order_by_id(order_id)
        if not order:
            return None

        order.complete()

        if final_value:
            order.final_value = final_value
        elif order.estimated_value:
            order.final_value = order.estimated_value

        if completion_notes:
            order.completion_notes = completion_notes

        service = self.repository.get_service_catalog_by_id(order.service_id)
        if service and order.final_value:
            service.update_metrics(order.final_value, order.rating)

        sla = self._get_applicable_sla(order)
        if sla:
            within_sla = self._check_sla_compliance(order, sla)
            order.sla_resolution_met = within_sla
            sla.update_metrics(within_sla)

        self.db.commit()
        self.db.refresh(order)
        logger.info(f"Ordem concluída: {order_id}")
        return order

    def cancel_order(self, order_id: UUID, reason: str) -> ServiceOrder | None:
        """Cancela uma ordem de serviço."""
        order = self.repository.get_service_order_by_id(order_id)
        if order:
            order.cancel(reason)
            self.db.commit()
            self.db.refresh(order)
            logger.info(f"Ordem cancelada: {order_id}")
        return order

    def rate_order(self, order_id: UUID, rating: int, feedback: str | None = None) -> ServiceOrder | None:
        """
        Avalia uma ordem de serviço.

        Args:
            order_id: ID da ordem
            rating: Nota (1-5)
            feedback: Feedback

        Returns:
            ServiceOrder ou None
        """
        order = self.repository.get_service_order_by_id(order_id)
        if not order:
            return None

        order.rate(rating, feedback)

        service = self.repository.get_service_catalog_by_id(order.service_id)
        if service:
            service.update_metrics(order.final_value or Decimal("0"), rating)

        self.db.commit()
        self.db.refresh(order)
        logger.info(f"Ordem avaliada: {order_id} - Nota: {rating}")
        return order

    def get_overdue_orders(self) -> list[ServiceOrder]:
        """Retorna ordens em atraso."""
        orders = self.repository.list_service_orders(ativo=True, limit=1000)
        overdue = []
        for order in orders:
            if order.is_overdue:
                overdue.append(order)
        return overdue

    def get_orders_at_risk(self, threshold_hours: int = 4) -> list[tuple[ServiceOrder, int]]:
        """
        Retorna ordens em risco de atraso.

        Args:
            threshold_hours: Horas para considerar em risco

        Returns:
            Lista de tuplas (ordem, minutos restantes)
        """
        at_risk = []
        orders, _total = self.repository.list_orders(
            filters=ServiceOrderFilter(status=OrderStatus.EM_ANDAMENTO), limit=1000
        )

        now = datetime.utcnow()
        threshold = timedelta(hours=threshold_hours)

        for order in orders:
            sla = self._get_applicable_sla(order)
            if sla and order.started_at:
                deadline = sla.calculate_deadline(order.started_at)
                remaining = deadline - now
                if timedelta() < remaining < threshold:
                    at_risk.append((order, int(remaining.total_seconds() / 60)))

        return sorted(at_risk, key=lambda x: x[1])

    # ============================================================
    # SERVICE EXECUTION MANAGEMENT
    # ============================================================

    def create_execution(self, data: ServiceExecutionCreate, user_id: UUID | None = None) -> ServiceExecution:
        """
        Cria uma execução de serviço.

        Args:
            data: Dados da execução
            user_id: ID do usuário

        Returns:
            ServiceExecution: Execução criada
        """
        logger.info(f"Criando execução para ordem: {data.order_id}")

        order = self.repository.get_service_order_by_id(data.order_id)
        if not order:
            raise ValueError(f"Ordem não encontrada: {data.order_id}")

        existing = self.repository.list_service_executions(order_id=data.order_id, limit=100)
        sequence = len(existing) + 1

        execution = self.repository.create_service_execution(data)
        execution.sequence = sequence

        if user_id:
            execution.created_by = user_id

        self.db.commit()
        self.db.refresh(execution)

        logger.info(f"Execução criada: {execution.id}")
        return execution

    def start_travel(self, execution_id: UUID) -> ServiceExecution | None:
        """Inicia deslocamento."""
        execution = self.repository.get_service_execution_by_id(execution_id)
        if execution:
            execution.start_travel()
            self.db.commit()
            self.db.refresh(execution)
            logger.info(f"Deslocamento iniciado: {execution_id}")
        return execution

    def arrive_at_location(self, execution_id: UUID) -> ServiceExecution | None:
        """Registra chegada no local."""
        execution = self.repository.get_service_execution_by_id(execution_id)
        if execution:
            execution.arrive_at_location()
            self.db.commit()
            self.db.refresh(execution)
            logger.info(f"Chegada registrada: {execution_id}")
        return execution

    def start_execution(self, execution_id: UUID) -> ServiceExecution | None:
        """Inicia execução do serviço."""
        execution = self.repository.get_service_execution_by_id(execution_id)
        if execution:
            execution.start_execution()

            order = self.repository.get_service_order_by_id(execution.order_id)
            if order and order.status != OrderStatus.EM_ANDAMENTO:
                order.start()

            self.db.commit()
            self.db.refresh(execution)
            logger.info(f"Execução iniciada: {execution_id}")
        return execution

    def pause_execution(self, execution_id: UUID, reason: str) -> ServiceExecution | None:
        """Pausa a execução."""
        execution = self.repository.get_service_execution_by_id(execution_id)
        if execution:
            execution.pause_execution(reason)
            self.db.commit()
            self.db.refresh(execution)
            logger.info(f"Execução pausada: {execution_id}")
        return execution

    def resume_execution(self, execution_id: UUID) -> ServiceExecution | None:
        """Retoma a execução."""
        execution = self.repository.get_service_execution_by_id(execution_id)
        if execution:
            execution.resume_execution()
            self.db.commit()
            self.db.refresh(execution)
            logger.info(f"Execução retomada: {execution_id}")
        return execution

    def finish_execution(
        self,
        execution_id: UUID,
        work_description: str | None = None,
        findings: str | None = None,
        recommendations: str | None = None,
    ) -> ServiceExecution | None:
        """
        Finaliza a execução.

        Args:
            execution_id: ID da execução
            work_description: Descrição do trabalho
            findings: Achados
            recommendations: Recomendações

        Returns:
            ServiceExecution ou None
        """
        execution = self.repository.get_service_execution_by_id(execution_id)
        if not execution:
            return None

        execution.finish_execution()

        if work_description:
            execution.work_description = work_description
        if findings:
            execution.findings = findings
        if recommendations:
            execution.recommendations = recommendations

        self.db.commit()
        self.db.refresh(execution)
        logger.info(f"Execução finalizada: {execution_id}")
        return execution

    def add_material_to_execution(
        self, execution_id: UUID, material_name: str, quantity: float, unit_price: Decimal
    ) -> ServiceExecution | None:
        """Adiciona material à execução."""
        execution = self.repository.get_service_execution_by_id(execution_id)
        if execution:
            execution.add_material(material_name, quantity, unit_price)
            self.db.commit()
            self.db.refresh(execution)
            logger.info(f"Material adicionado: {material_name}")
        return execution

    def update_checklist_item(
        self, execution_id: UUID, item_index: int, completed: bool, notes: str | None = None
    ) -> ServiceExecution | None:
        """Atualiza item do checklist."""
        execution = self.repository.get_service_execution_by_id(execution_id)
        if execution:
            execution.update_checklist_item(item_index, completed, notes)
            self.db.commit()
            self.db.refresh(execution)
            logger.info(f"Checklist atualizado: item {item_index}")
        return execution

    def add_signature(
        self, execution_id: UUID, signer_name: str, signature_data: str, signer_role: str
    ) -> ServiceExecution | None:
        """Adiciona assinatura à execução."""
        execution = self.repository.get_service_execution_by_id(execution_id)
        if execution:
            execution.add_signature(signer_name, signature_data, signer_role)
            self.db.commit()
            self.db.refresh(execution)
            logger.info(f"Assinatura adicionada: {signer_name}")
        return execution

    # ============================================================
    # SERVICE REPORT MANAGEMENT
    # ============================================================

    def create_report(self, data: ServiceReportCreate, user_id: UUID | None = None) -> ServiceReport:
        """
        Cria um relatório de serviço.

        Args:
            data: Dados do relatório
            user_id: ID do usuário

        Returns:
            ServiceReport: Relatório criado
        """
        logger.info(f"Criando relatório: {data.title}")

        order = self.repository.get_service_order_by_id(data.order_id)
        if not order:
            raise ValueError(f"Ordem não encontrada: {data.order_id}")

        report = self.repository.create_service_report(data)

        if user_id:
            report.author_id = user_id
            report.created_by = user_id

        self.db.commit()
        self.db.refresh(report)

        logger.info(f"Relatório criado: {report.id}")
        return report

    def update_report(
        self, report_id: UUID, data: ServiceReportUpdate, user_id: UUID | None = None
    ) -> ServiceReport | None:
        """Atualiza um relatório."""
        report = self.repository.get_service_report_by_id(report_id)
        if not report:
            return None

        if not report.is_draft:
            raise ValueError("Relatório finalizado não pode ser editado")

        updated = self.repository.update_service_report(report_id, data)

        if updated and user_id:
            updated.updated_by = user_id
            self.db.commit()
            self.db.refresh(updated)

        logger.info(f"Relatório atualizado: {report_id}")
        return updated

    def finalize_report(self, report_id: UUID) -> ServiceReport | None:
        """Finaliza um relatório."""
        report = self.repository.get_service_report_by_id(report_id)
        if report:
            report.finalize()
            self.db.commit()
            self.db.refresh(report)
            logger.info(f"Relatório finalizado: {report_id}")
        return report

    def review_report(
        self, report_id: UUID, reviewer_id: UUID, reviewer_name: str, review_notes: str | None = None
    ) -> ServiceReport | None:
        """Revisa um relatório."""
        report = self.repository.get_service_report_by_id(report_id)
        if report:
            report.review(reviewer_id, reviewer_name, review_notes)
            self.db.commit()
            self.db.refresh(report)
            logger.info(f"Relatório revisado: {report_id}")
        return report

    def approve_report(self, report_id: UUID, approver_id: UUID, approver_name: str) -> ServiceReport | None:
        """Aprova um relatório."""
        report = self.repository.get_service_report_by_id(report_id)
        if report:
            report.approve(approver_id, approver_name)
            self.db.commit()
            self.db.refresh(report)
            logger.info(f"Relatório aprovado: {report_id}")
        return report

    def send_report(self, report_id: UUID, recipient: str) -> ServiceReport | None:
        """Marca relatório como enviado."""
        report = self.repository.get_service_report_by_id(report_id)
        if report:
            report.send(recipient)
            self.db.commit()
            self.db.refresh(report)
            logger.info(f"Relatório enviado para: {recipient}")
        return report

    def add_report_section(self, report_id: UUID, title: str, content: str, order: int) -> ServiceReport | None:
        """Adiciona seção ao relatório."""
        report = self.repository.get_service_report_by_id(report_id)
        if report:
            report.add_section(title, content, order)
            self.db.commit()
            self.db.refresh(report)
            logger.info(f"Seção adicionada: {title}")
        return report

    def add_report_photo(self, report_id: UUID, photo_url: str, caption: str | None = None) -> ServiceReport | None:
        """Adiciona foto ao relatório."""
        report = self.repository.get_service_report_by_id(report_id)
        if report:
            report.add_photo(photo_url, caption)
            self.db.commit()
            self.db.refresh(report)
            logger.info(f"Foto adicionada ao relatório: {report_id}")
        return report

    def add_non_conformity(self, report_id: UUID, description: str, severity: str) -> ServiceReport | None:
        """Adiciona não conformidade ao relatório."""
        report = self.repository.get_service_report_by_id(report_id)
        if report:
            report.add_non_conformity(description, severity)
            self.db.commit()
            self.db.refresh(report)
            logger.info(f"Não conformidade adicionada: {severity}")
        return report

    # ============================================================
    # SLA MANAGEMENT
    # ============================================================

    def create_sla_config(self, data: SLAConfigCreate, user_id: UUID | None = None) -> SLAConfig:
        """Cria configuração de SLA."""
        logger.info(f"Criando SLA: {data.name}")

        sla = self.repository.create_sla_config(data)

        if user_id:
            sla.created_by = user_id

        self.db.commit()
        self.db.refresh(sla)

        logger.info(f"SLA criado: {sla.id}")
        return sla

    def update_sla_config(self, sla_id: UUID, data: SLAConfigUpdate, user_id: UUID | None = None) -> SLAConfig | None:
        """Atualiza configuração de SLA."""
        sla = self.repository.get_sla_config_by_id(sla_id)
        if not sla:
            return None

        updated = self.repository.update_sla_config(sla_id, data)

        if updated and user_id:
            updated.updated_by = user_id
            self.db.commit()
            self.db.refresh(updated)

        logger.info(f"SLA atualizado: {sla_id}")
        return updated

    def activate_sla(self, sla_id: UUID) -> SLAConfig | None:
        """Ativa um SLA."""
        sla = self.repository.get_sla_config_by_id(sla_id)
        if sla:
            sla.activate()
            self.db.commit()
            self.db.refresh(sla)
            logger.info(f"SLA ativado: {sla_id}")
        return sla

    def deactivate_sla(self, sla_id: UUID) -> SLAConfig | None:
        """Desativa um SLA."""
        sla = self.repository.get_sla_config_by_id(sla_id)
        if sla:
            sla.deactivate()
            self.db.commit()
            self.db.refresh(sla)
            logger.info(f"SLA desativado: {sla_id}")
        return sla

    def set_default_sla(self, sla_id: UUID, service_id: UUID | None = None) -> SLAConfig | None:
        """Define SLA como padrão."""
        if service_id:
            current_defaults = self.repository.list_sla_configs(service_id=service_id, is_default=True, is_active=True)
            for current_sla in current_defaults:
                current_sla.is_default = False

        sla = self.repository.get_sla_config_by_id(sla_id)
        if sla:
            sla.set_as_default()
            self.db.commit()
            self.db.refresh(sla)
            logger.info(f"SLA definido como padrão: {sla_id}")
        return sla

    def get_sla_compliance_report(
        self, sla_id: UUID, start_date: date | None = None, end_date: date | None = None
    ) -> dict[str, Any]:
        """
        Gera relatório de compliance do SLA.

        Args:
            sla_id: ID do SLA
            start_date: Data inicial
            end_date: Data final

        Returns:
            Dict com relatório de compliance
        """
        sla = self.repository.get_sla_config_by_id(sla_id)
        if not sla:
            return {}

        return {
            "sla_id": str(sla.id),
            "sla_name": sla.name,
            "period": {"start": str(start_date) if start_date else None, "end": str(end_date) if end_date else None},
            "metrics": {
                "total_orders": sla.total_orders,
                "orders_within_sla": sla.orders_within_sla,
                "orders_breached": sla.orders_breached,
                "compliance_percent": float(sla.current_compliance_percent or 0),
                "breach_rate": sla.breach_rate,
                "status": sla.compliance_status,
            },
            "targets": {
                "response_time_minutes": sla.response_time_minutes,
                "resolution_time_minutes": sla.resolution_time_minutes,
                "availability_percent": float(sla.target_availability_percent or 0),
            },
        }

    # ============================================================
    # HELPER METHODS
    # ============================================================

    def _get_applicable_sla(self, order: ServiceOrder) -> SLAConfig | None:
        """Retorna SLA aplicável à ordem."""
        if order.contract_id:
            slas = self.repository.list_sla_configs(contract_id=order.contract_id, is_active=True)
            if slas:
                return slas[0]

        if order.client_id:
            slas = self.repository.list_sla_configs(client_id=order.client_id, is_active=True)
            if slas:
                return slas[0]

        slas = self.repository.list_sla_configs(service_id=order.service_id, is_default=True, is_active=True)
        if slas:
            return slas[0]

        slas = self.repository.list_sla_configs(is_default=True, is_active=True)
        return slas[0] if slas else None

    def _check_sla_compliance(self, order: ServiceOrder, sla: SLAConfig) -> bool:
        """Verifica compliance do SLA."""
        if not order.started_at or not order.completed_at:
            return True

        if not sla.resolution_time_minutes:
            return True

        duration = order.completed_at - order.started_at
        duration_minutes = duration.total_seconds() / 60

        priority_multiplier = 1.0
        if sla.priority_multipliers and order.priority:
            priority_multiplier = sla.priority_multipliers.get(order.priority.value, 1.0)

        adjusted_limit = sla.resolution_time_minutes * priority_multiplier

        return duration_minutes <= adjusted_limit
