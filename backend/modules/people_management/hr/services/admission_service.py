"""
Serviço de Admissão — Departamento Pessoal.

Gerencia o workflow completo de admissão: criação do processo,
atualização de status, geração de checklist e conclusão
(criação do registro de Employee).
"""

import logging
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.people_management.hr.models.admission import (
    AdmissionProcess,
    AdmissionStatus,
)

logger = logging.getLogger(__name__)

# Checklist padrão para admissão em empresa de vigilância
DEFAULT_ADMISSION_CHECKLIST = {
    "documentos_pessoais": {
        "rg": False,
        "cpf": False,
        "titulo_eleitor": False,
        "carteira_reservista": False,
        "comprovante_residencia": False,
        "certidao_nascimento_casamento": False,
        "foto_3x4": False,
        "declaracao_dependentes": False,
        "comprovante_escolaridade": False,
    },
    "documentos_trabalhistas": {
        "ctps": False,
        "pis_pasep": False,
        "certificado_escolaridade": False,
        "certidao_nascimento_filhos": False,
        "cartao_vacina_filhos": False,
        "comprovante_endereco_atualizado": False,
    },
    "documentos_seguranca": {
        "curso_vigilante": False,
        "cnv_carteira_nacional_vigilante": False,
        "certificado_reciclagem": False,
        "registro_policia_federal": False,
        "antecedentes_criminais": False,
        "exame_toxicologico": False,
    },
    "exames": {
        "aso_admissional": False,
        "exame_psicotecnico": False,
        "laudo_pcd": False,
    },
    "bancarios": {
        "dados_conta_bancaria": False,
        "comprovante_abertura_conta": False,
    },
}


class AdmissionService:
    """Serviço para processos de admissão."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_admission(
        self,
        data: dict,
        created_by_id: str | UUID | None = None,
    ) -> AdmissionProcess:
        """Cria um novo processo de admissão.

        Args:
            data: Dados do processo (schema AdmissionProcessCreate).
            created_by_id: ID do usuário que criou.

        Returns:
            Instância de AdmissionProcess criada.
        """
        admission = AdmissionProcess(
            id=uuid4(),
            candidate_name=data.get("candidate_name"),
            cpf=data.get("cpf"),
            position=data.get("position"),
            department=data.get("department"),
            contract_type=data.get("contract_type", "CLT"),
            candidate_id=data.get("candidate_id"),
            job_position_id=data.get("job_position_id"),
            expected_start_date=data.get("expected_start_date"),
            salary_proposed=data.get("salary_proposed"),
            workplace_id=data.get("workplace_id"),
            checklist=data.get("checklist") or DEFAULT_ADMISSION_CHECKLIST,
            notes=data.get("notes"),
            status=AdmissionStatus.DOCUMENTS_PENDING,
            created_by_id=str(created_by_id) if created_by_id else None,
        )
        self.db.add(admission)
        await self.db.flush()
        await self.db.refresh(admission)
        logger.info("Processo de admissão criado: %s", admission.id)
        return admission

    async def get_by_id(self, admission_id: str | UUID) -> AdmissionProcess | None:
        """Busca processo de admissão por ID."""
        result = await self.db.execute(select(AdmissionProcess).where(AdmissionProcess.id == str(admission_id)))
        return result.scalar_one_or_none()

    async def list_admissions(
        self,
        status: AdmissionStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """Lista processos de admissão com filtro e paginação.

        Args:
            status: Filtro por status (opcional).
            page: Página atual.
            page_size: Itens por página.

        Returns:
            Dicionário com items, total, page, page_size, total_pages.
        """
        from sqlalchemy import func

        query = select(AdmissionProcess)
        count_query = select(func.count()).select_from(AdmissionProcess)

        if status:
            query = query.where(AdmissionProcess.status == status)
            count_query = count_query.where(AdmissionProcess.status == status)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0
        total_pages = max(1, (total + page_size - 1) // page_size)

        query = query.order_by(AdmissionProcess.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(query)
        items = result.scalars().all()

        from modules.people_management.hr.schemas.admission import AdmissionProcessResponse

        serialized = [AdmissionProcessResponse.model_validate(item).model_dump(mode="json") for item in items]

        return {
            "items": serialized,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    async def update_status(
        self,
        admission_id: str | UUID,
        new_status: AdmissionStatus,
        data: dict | None = None,
    ) -> AdmissionProcess | None:
        """Atualiza o status do processo de admissão.

        Args:
            admission_id: ID do processo.
            new_status: Novo status.
            data: Dados adicionais a atualizar.

        Returns:
            Processo atualizado ou None se não encontrado.
        """
        admission = await self.get_by_id(admission_id)
        if not admission:
            return None

        admission.status = new_status
        if data:
            for key, value in data.items():
                if hasattr(admission, key) and value is not None:
                    setattr(admission, key, value)

        await self.db.flush()
        await self.db.refresh(admission)
        logger.info("Admissão %s atualizada para status: %s", admission_id, new_status)
        return admission

    def generate_document_checklist(
        self,
        include_security: bool = True,
    ) -> dict:
        """Gera checklist de documentos para admissão.

        Args:
            include_security: Se True, inclui documentos de vigilância.

        Returns:
            Dicionário de checklist com categorias e itens.
        """
        checklist = {
            "documentos_pessoais": dict(DEFAULT_ADMISSION_CHECKLIST["documentos_pessoais"]),
            "documentos_trabalhistas": dict(DEFAULT_ADMISSION_CHECKLIST["documentos_trabalhistas"]),
            "exames": dict(DEFAULT_ADMISSION_CHECKLIST["exames"]),
            "bancarios": dict(DEFAULT_ADMISSION_CHECKLIST["bancarios"]),
        }
        if include_security:
            checklist["documentos_seguranca"] = dict(DEFAULT_ADMISSION_CHECKLIST["documentos_seguranca"])
        return checklist

    async def complete_admission(
        self,
        admission_id: str | UUID,
        employee_data: dict,
    ) -> dict:
        """Conclui o processo de admissão e cria o registro de Employee.

        Args:
            admission_id: ID do processo de admissão.
            employee_data: Dados para criação do Employee.

        Returns:
            Dicionário com admission e employee criados.
        """
        from modules.operacional.models.employee import Employee

        admission = await self.get_by_id(admission_id)
        if not admission:
            raise ValueError(f"Admissão {admission_id} não encontrada")

        if admission.status == AdmissionStatus.COMPLETED:
            raise ValueError("Admissão já concluída")

        # CCT fonte única: resolver cargo/piso da CCT (prefere cct_cargo_id do form; senão mapeia nome)
        from sqlalchemy import text as _sqltext

        _cct_id = employee_data.get("cct_cargo_id") or getattr(admission, "cct_cargo_id", None)
        _cargo_nome = employee_data.get("cargo") or getattr(admission, "position", None)
        _piso = None
        try:
            if _cct_id:
                _row = (
                    await self.db.execute(
                        _sqltext("SELECT cargo_nome, piso_salarial FROM cct_cargos WHERE id = :c"),
                        {"c": str(_cct_id)},
                    )
                ).mappings().first()
            else:
                # Fallback: casa o nome livre com o cargo CCT (acento/caixa-insensível)
                _row = (
                    await self.db.execute(
                        _sqltext(
                            "SELECT id, cargo_nome, piso_salarial FROM cct_cargos "
                            "WHERE unaccent(upper(cargo_nome)) = unaccent(upper(:n)) LIMIT 1"
                        ),
                        {"n": _cargo_nome or ""},
                    )
                ).mappings().first()
                if _row:
                    _cct_id = _row["id"]
            if _row:
                _cargo_nome = _row["cargo_nome"]
                _piso = _row["piso_salarial"]
        except Exception as _e:  # noqa: BLE001
            logger.warning("Admissão: falha ao resolver cargo CCT: %s", _e)

        # Criar Employee
        employee = Employee(
            id=uuid4(),
            nome=employee_data.get("nome", ""),
            email=employee_data.get("email"),
            cpf=employee_data.get("cpf"),
            matricula=employee_data.get("matricula"),
            cargo=_cargo_nome or employee_data.get("cargo"),
            cct_cargo_id=_cct_id,
            departamento=employee_data.get("departamento"),
            telefone=employee_data.get("telefone"),
            data_admissao=admission.actual_start_date or admission.expected_start_date,
            salario_base=admission.salary_proposed or _piso,
            status="Ativo",
        )
        self.db.add(employee)
        await self.db.flush()

        # Atualizar admissão
        admission.employee_id = str(employee.id)
        admission.status = AdmissionStatus.COMPLETED
        if not admission.actual_start_date:
            admission.actual_start_date = admission.expected_start_date

        await self.db.flush()
        await self.db.refresh(admission)
        await self.db.refresh(employee)

        logger.info(
            "Admissão %s concluída — Employee %s criado",
            admission_id,
            employee.id,
        )

        # Publicar evento de funcionário admitido no ConectaEventBus
        try:
            import asyncio

            from infrastructure.event_bus import ConectaEvent, EventTypes, event_bus

            asyncio.create_task(
                event_bus.publish(
                    ConectaEvent(
                        event_type=EventTypes.DP_FUNCIONARIO_ADMITIDO,
                        payload={
                            "employee_id": str(employee.id),
                            "nome": employee.nome,
                            "cargo": employee.cargo or "",
                            "departamento": employee.departamento or "",
                            "data_admissao": str(employee.data_admissao) if employee.data_admissao else None,
                            "admission_id": str(admission_id),
                        },
                        source_module="dp",
                        funcionario_id=str(employee.id),
                    )
                )
            )
        except Exception as _pub_err:
            logger.warning("Falha ao publicar DP_FUNCIONARIO_ADMITIDO: %s", _pub_err)

        return {"admission": admission, "employee": employee}
