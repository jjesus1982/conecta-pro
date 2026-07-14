"""
Serviço de Férias — Departamento Pessoal.

FONTE DA VERDADE: a tabela canônica é `hr_vacation_requests` (superset da antiga
`vacation_requests`, que permanece INTACTA apenas como backup). O banco grava o
status em INGLÊS MAIÚSCULO (SUBMITTED/APPROVED/REJECTED/CANCELLED...); a tela e os
cards do DP trabalham em PT minúsculo, por isso o mapa PT↔EN é obrigatório.

Adiciona cálculo de saldo de férias com valores CLT reais (Decimal).
"""

import contextlib
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.operacional.models.employee import Employee
from modules.people_management.common.utils.clt_calculator import calcular_ferias

logger = logging.getLogger(__name__)

# Re-export do serviço existente de férias
try:
    from modules.hr.employee_portal.services import VacationService as PortalVacationService
except ImportError:
    PortalVacationService = None  # type: ignore[assignment, misc]

try:
    from modules.operacional.vacations.models import VacationRequest
except ImportError:
    VacationRequest = None  # type: ignore[assignment, misc]


# ---------------------------------------------------------------------------
# Mapa PT↔EN (fonte canônica grava EN maiúsculo; tela/cards trabalham em PT).
# ---------------------------------------------------------------------------
# EN (banco) → PT (bucket exibido)
_HVR_STATUS_EN_TO_PT = {
    "SUBMITTED": "pendente",
    "PENDING": "pendente",
    "APPROVED": "aprovado",
    "REJECTED": "rejeitado",
    "DRAFT": "rascunho",
    "CANCELLED": "cancelado",
    "SCHEDULED": "programado",
    "IN_PROGRESS": "em_andamento",
    "COMPLETED": "concluido",
    "INTERRUPTED": "interrompido",
    "PAID": "pago",
}

# PT (criação/aprovação) → EN (valor gravado na fonte canônica)
_HVR_STATUS_PT_TO_EN = {
    "pendente": "SUBMITTED",
    "submetido": "SUBMITTED",
    "aprovado": "APPROVED",
    "rejeitado": "REJECTED",
    "cancelado": "CANCELLED",
}

# condomínio canônico usado pela fonte da verdade (NOT NULL na tabela)
_HVR_DEFAULT_CONDOMINIO_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def _hvr_status_to_pt(raw: str | None) -> str:
    """Mapeia status EN (banco) → PT (bucket exibido)."""
    if not raw:
        return "desconhecido"
    return _HVR_STATUS_EN_TO_PT.get(str(raw).upper(), str(raw).lower())


def _hvr_days_str(days_requested) -> str | None:
    """Formata days_requested (int) no shape 'N dia(s)' que o front já espera."""
    if days_requested is None:
        return None
    try:
        n = int(days_requested)
    except (TypeError, ValueError):
        return str(days_requested)
    return f"{n} dia{'s' if n != 1 else ''}"


# SELECT canônico com JOIN em employees para o employee_name (a tabela
# hr_vacation_requests NÃO tem coluna employee_name — vem do JOIN).
_HVR_BASE_SELECT = """
    SELECT
        CAST(h.id AS TEXT) AS id,
        CAST(h.employee_id AS TEXT) AS employee_id,
        e.nome AS employee_name,
        h.status AS raw_status,
        h.request_code,
        h.start_date,
        h.end_date,
        h.days_requested,
        h.employee_notes,
        h.hr_notes,
        h.rejection_reason,
        CAST(h.hr_approved_by AS TEXT) AS approved_by,
        h.hr_approved_at AS approved_at,
        h.created_at,
        COALESCE(h.updated_at, h.created_at) AS updated_at
    FROM hr_vacation_requests h
    LEFT JOIN employees e ON e.id = h.employee_id
"""


def _hvr_row_to_ns(row) -> SimpleNamespace:
    """Converte uma linha canônica no objeto que o controller/schema espera
    (mesmos atributos do VacationRequestResponse: employee_name, status PT,
    days como string 'N dias', etc.)."""
    return SimpleNamespace(
        id=row.id,
        employee_id=row.employee_id,
        employee_name=row.employee_name,
        type="ferias",
        status=_hvr_status_to_pt(row.raw_status),
        start_date=row.start_date,
        end_date=row.end_date,
        days=_hvr_days_str(row.days_requested),
        reason=row.employee_notes,
        notes=row.hr_notes,
        approved_by=row.approved_by,
        approved_at=row.approved_at,
        rejected_reason=row.rejection_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class VacationService:
    """Serviço de Férias — visão DP (lê/grava em hr_vacation_requests)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._portal_service = None
        if PortalVacationService:
            with contextlib.suppress(Exception):
                self._portal_service = PortalVacationService(db)

    async def get_by_id(self, vacation_id: str | UUID) -> "SimpleNamespace | None":
        """Busca uma solicitação de férias pelo ID na fonte canônica.

        Args:
            vacation_id: ID da solicitação de férias.

        Returns:
            Objeto (SimpleNamespace) no shape do VacationRequestResponse, ou None.
        """
        result = await self.db.execute(
            text(_HVR_BASE_SELECT + " WHERE CAST(h.id AS TEXT) = :rid"),
            {"rid": str(vacation_id)},
        )
        row = result.fetchone()
        if not row:
            return None
        return _hvr_row_to_ns(row)

    async def list_by_employee(self, employee_id: str | UUID, page: int = 1, page_size: int = 20) -> dict:
        """Lista solicitações de férias de um funcionário específico (fonte canônica).

        Args:
            employee_id: ID do funcionário.
            page: Página atual.
            page_size: Itens por página.

        Returns:
            Dicionário com items, total e paginação.
        """
        emp_id = str(employee_id)

        total = (
            await self.db.execute(
                text("SELECT COUNT(*) FROM hr_vacation_requests WHERE CAST(employee_id AS TEXT) = :eid"),
                {"eid": emp_id},
            )
        ).scalar() or 0

        result = await self.db.execute(
            text(
                _HVR_BASE_SELECT
                + " WHERE CAST(h.employee_id AS TEXT) = :eid"
                + " ORDER BY h.created_at DESC OFFSET :off LIMIT :lim"
            ),
            {"eid": emp_id, "off": (page - 1) * page_size, "lim": page_size},
        )
        items = [_hvr_row_to_ns(r) for r in result.fetchall()]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    async def calculate_vacation_balance(self, employee_id: str | UUID) -> dict:
        """Calcula o saldo de férias do funcionário.

        Considera data de admissão, períodos aquisitivos e férias já gozadas.

        Args:
            employee_id: ID do funcionário.

        Returns:
            Dicionário com dados do saldo de férias.
        """
        result = await self.db.execute(select(Employee).where(Employee.id == str(employee_id)))
        employee = result.scalar_one_or_none()
        if not employee:
            raise ValueError(f"Funcionário {employee_id} não encontrado")

        data_admissao = employee.data_admissao
        if not data_admissao:
            return {
                "employee_id": str(employee_id),
                "employee_name": employee.nome,
                "dias_direito": 0,
                "dias_gozados": 0,
                "dias_saldo": 0,
                "periodos_aquisitivos": [],
                "message": "Data de admissão não informada",
            }

        today = date.today()
        # meses de vínculo em CALENDÁRIO — `delta.days // 30` usa ano de 360d e infla o
        # direito ~5 dias/ano (pode abrir período aquisitivo/concessivo antes da hora)
        from dateutil.relativedelta import relativedelta as _rd

        _rdv = _rd(today, data_admissao)
        meses_trabalhados = _rdv.years * 12 + _rdv.months

        # Dias de direito: 30 dias a cada 12 meses
        periodos_completos = meses_trabalhados // 12
        meses_periodo_atual = meses_trabalhados % 12
        dias_proporcional = int((30 / 12) * meses_periodo_atual)
        dias_direito_total = (periodos_completos * 30) + dias_proporcional

        # Buscar férias gozadas — fonte canônica hr_vacation_requests (status EN APPROVED).
        dias_gozados = 0
        try:
            gozadas = await self.db.execute(
                text(
                    "SELECT days_requested, start_date, end_date FROM hr_vacation_requests "
                    "WHERE CAST(employee_id AS TEXT) = :eid AND UPPER(status) = 'APPROVED' "
                    # só conta como GOZADA a que já foi consumida (end_date < hoje); férias
                    # FUTURAS aprovadas NÃO abatem o saldo — senão mascaram a dobra vencida
                    "AND end_date IS NOT NULL AND end_date < :today"
                ),
                {"eid": str(employee_id), "today": today},
            )
            for row in gozadas.fetchall():
                if row.days_requested:
                    dias_gozados += int(row.days_requested)
                elif row.start_date and row.end_date:
                    # +1: intervalo inclusivo
                    dias_gozados += (row.end_date - row.start_date).days + 1
        except Exception as e:
            logger.warning("Erro ao buscar férias gozadas: %s", e)

        dias_saldo = max(0, dias_direito_total - dias_gozados)

        # [Achado 5] Detecção de período aquisitivo VENCIDO (art. 137 CLT — dobra).
        # Cada período aquisitivo completo (12 meses) abre um período concessivo de mais
        # 12 meses para o empregador conceder as férias. Se um período aquisitivo já venceu
        # (>= 24 meses de admissão sem que essas férias tenham sido gozadas), o pagamento é
        # em DOBRA. Aproximação: dias vencidos = saldo que corresponde a períodos aquisitivos
        # já encerrados há mais de 12 meses e ainda não gozados.
        # Períodos concessivos já vencidos = períodos aquisitivos completos com mais de
        # 12 meses de "idade" (ou seja, admissão há >= 24 meses para o 1º, >=36 p/ o 2º...).
        periodos_concessivos_vencidos = max(0, (meses_trabalhados - 12) // 12)
        dias_potencial_vencido = periodos_concessivos_vencidos * 30
        # Dos dias em saldo, quantos pertencem a período aquisitivo já vencido (não gozado).
        dias_vencidos = max(0, min(dias_saldo, dias_potencial_vencido - 0))
        # Só há dobra sobre o que efetivamente ainda está em saldo e é de período vencido.
        dias_vencidos = min(dias_vencidos, dias_saldo)
        alerta_dobra = dias_vencidos > 0

        # Cálculo de valores monetários das férias com CLT real
        salario_base = Decimal(str(employee.salario_base or 0))
        valor_ferias = 0.0
        terco_constitucional = 0.0
        abono_pecuniario = 0.0
        total_bruto_ferias = 0.0

        if dias_saldo > 0 and salario_base > 0:
            dias_gozo = min(dias_saldo, 30)
            dias_abono = max(0, dias_saldo - 30) if dias_saldo > 30 else 0
            ferias_calc = calcular_ferias(salario_base, dias_gozo=dias_gozo, dias_abono=dias_abono)
            valor_ferias = float(ferias_calc["valor_ferias"])
            terco_constitucional = float(ferias_calc["terco_constitucional"])
            abono_pecuniario = float(ferias_calc["abono_pecuniario"])
            total_bruto_ferias = float(ferias_calc["total_bruto"])

        return {
            "employee_id": str(employee_id),
            "employee_name": employee.nome,
            "data_admissao": data_admissao.isoformat(),
            "meses_trabalhados": meses_trabalhados,
            "periodos_completos": periodos_completos,
            "dias_direito": dias_direito_total,
            "dias_gozados": dias_gozados,
            "dias_saldo": dias_saldo,
            "dias_proporcional_periodo_atual": dias_proporcional,
            # [Achado 5] Alerta de período aquisitivo vencido (art. 137 CLT — férias em DOBRA)
            "dias_vencidos": dias_vencidos,
            "periodos_concessivos_vencidos": periodos_concessivos_vencidos,
            "alerta_dobra": alerta_dobra,
            "aviso_dobra": (
                f"{dias_vencidos} dia(s) de férias em período aquisitivo VENCIDO "
                "(art. 137 CLT): pagamento em DOBRA se não concedidas"
                if alerta_dobra
                else None
            ),
            "valor_ferias": valor_ferias,
            "terco_constitucional": terco_constitucional,
            "abono_pecuniario": abono_pecuniario,
            "total_bruto_ferias": total_bruto_ferias,
        }

    async def approve_vacation(
        self,
        vacation_id: str | UUID,
        approved_by_id: str | UUID | None = None,
    ) -> dict:
        """Aprova uma solicitação de férias e notifica operações.

        Args:
            vacation_id: ID da solicitação de férias.
            approved_by_id: ID do usuário que aprovou.

        Returns:
            Dicionário com resultado da aprovação.
        """
        # Fonte canônica: hr_vacation_requests. Busca via SELECT canônico para obter
        # employee_id/nome/datas (usados na notificação e no evento).
        result = await self.db.execute(
            text(_HVR_BASE_SELECT + " WHERE CAST(h.id AS TEXT) = :rid"),
            {"rid": str(vacation_id)},
        )
        row = result.fetchone()
        if not row:
            raise ValueError(f"Solicitação de férias {vacation_id} não encontrada")

        # Grava status EN 'APPROVED' (vocabulário da fonte canônica) + trilha de
        # aprovação do DP (hr_approved / hr_approved_by / hr_approved_at). O mapa PT↔EN
        # devolve 'aprovado' para a tela; aqui persistimos EN.
        await self.db.execute(
            text(
                "UPDATE hr_vacation_requests SET status = 'APPROVED', hr_approved = true, "
                "hr_approved_by = CAST(:by AS uuid), hr_approved_at = :at, updated_at = :at "
                "WHERE CAST(id AS TEXT) = :rid"
            ),
            {
                "by": str(approved_by_id) if approved_by_id else None,
                "at": datetime.now(timezone.utc),
                "rid": str(vacation_id),
            },
        )
        await self.db.flush()

        # objeto para notificação/evento (shape estável, status já em PT 'aprovado')
        vacation = _hvr_row_to_ns(row)
        vacation.status = "aprovado"

        # Notificar operações (async, não bloqueia)
        try:
            from modules.operacional.services import notify_vacation_approved

            await notify_vacation_approved(vacation)
        except (ImportError, Exception) as e:
            logger.info("Notificação de férias não enviada: %s", e)

        try:
            from infrastructure.event_bus import ConectaEvent, EventTypes, event_bus

            await event_bus.publish(
                ConectaEvent(
                    event_type=EventTypes.DP_FERIAS_APROVADAS,
                    payload={
                        "vacation_id": str(vacation_id),
                        "employee_id": str(getattr(vacation, "employee_id", "")),
                        "start_date": str(getattr(vacation, "start_date", "")),
                        "end_date": str(getattr(vacation, "end_date", "")),
                        "days_requested": getattr(vacation, "days_requested", None),
                    },
                    source_module="dp",
                    funcionario_id=str(getattr(vacation, "employee_id", "")),
                )
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Falha ao publicar evento ferias: %s", exc)

        logger.info("Férias %s aprovadas", vacation_id)
        return {
            "vacation_id": str(vacation_id),
            "status": "aprovado",
            "message": "Férias aprovadas com sucesso",
            # campos usados pelo controller p/ publicar ferias_aprovadas (GEDEON)
            "employee_id": str(getattr(vacation, "employee_id", "") or ""),
            "employee_name": str(getattr(vacation, "employee_name", "") or ""),
            "start_date": str(getattr(vacation, "start_date", "") or ""),
            "end_date": str(getattr(vacation, "end_date", "") or ""),
        }

    async def reject_vacation(
        self,
        vacation_id: str | UUID,
        rejected_by_id: str | UUID | None = None,
        reason: str | None = None,
    ) -> dict:
        """Rejeita uma solicitação de férias na fonte canônica (status EN 'REJECTED')."""
        exists = await self.db.execute(
            text("SELECT 1 FROM hr_vacation_requests WHERE CAST(id AS TEXT) = :rid"),
            {"rid": str(vacation_id)},
        )
        if not exists.fetchone():
            raise ValueError(f"Solicitação de férias {vacation_id} não encontrada")

        await self.db.execute(
            text(
                "UPDATE hr_vacation_requests SET status = 'REJECTED', "
                "rejected_by = CAST(:by AS uuid), rejected_at = :at, "
                "rejection_reason = :reason, updated_at = :at WHERE CAST(id AS TEXT) = :rid"
            ),
            {
                "by": str(rejected_by_id) if rejected_by_id else None,
                "at": datetime.now(timezone.utc),
                "reason": reason,
                "rid": str(vacation_id),
            },
        )
        await self.db.flush()
        return {"vacation_id": str(vacation_id), "status": "rejeitado", "message": "Férias rejeitadas"}

    async def cancel_vacation(
        self,
        vacation_id: str | UUID,
        cancelled_by_id: str | UUID | None = None,
        reason: str | None = None,
    ) -> dict:
        """Cancela (soft-delete) uma solicitação na fonte canônica (status EN 'CANCELLED').

        NUNCA hard-delete: preserva a solicitação (dado trabalhista). O front trata
        HTTP 200/204 como remoção da lista e a solicitação passa a contar no bucket
        'cancelado'.
        """
        exists = await self.db.execute(
            text("SELECT 1 FROM hr_vacation_requests WHERE CAST(id AS TEXT) = :rid"),
            {"rid": str(vacation_id)},
        )
        if not exists.fetchone():
            raise ValueError(f"Solicitação de férias {vacation_id} não encontrada")

        await self.db.execute(
            text(
                "UPDATE hr_vacation_requests SET status = 'CANCELLED', "
                "cancelled_by = CAST(:by AS uuid), cancelled_at = :at, "
                "cancellation_reason = :reason, updated_at = :at WHERE CAST(id AS TEXT) = :rid"
            ),
            {
                "by": str(cancelled_by_id) if cancelled_by_id else None,
                "at": datetime.now(timezone.utc),
                "reason": reason,
                "rid": str(vacation_id),
            },
        )
        await self.db.flush()
        return {"vacation_id": str(vacation_id), "status": "cancelado", "message": "Solicitação cancelada"}

    async def sync_vacations_from_solides(
        self,
        employee_id: str | None = None,
        periodo_inicio: str | None = None,
        periodo_fim: str | None = None,
    ) -> dict:
        """Sincroniza férias do Sólides para o sistema de férias do DP.

        Busca absences do tipo FERIAS/VACATION e cria registros locais
        em gp_justifications, evitando duplicatas via source_id.

        Returns:
            Dict com total_importadas, total_atualizadas, erros.
        """
        import os
        from datetime import date
        from uuid import uuid4

        import httpx

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            logger.warning("sync_vacations_from_solides: SOLIDES_API_TOKEN não configurado")
            return {"success": False, "reason": "no_token", "total_importadas": 0}

        hoje = date.today()
        inicio = periodo_inicio or hoje.replace(day=1).isoformat()
        fim = periodo_fim or hoje.isoformat()

        importadas = 0
        atualizadas = 0
        erros: list[dict] = []

        try:
            base_url = os.getenv("SOLIDES_BASE_URL", "https://employer.tangerino.com.br")
            headers = {"Authorization": f"Basic {api_token}", "Accept": "application/json"}
            params: dict = {"startDate": inicio, "endDate": fim, "page": 0, "size": 200}
            if employee_id:
                params["employeeId"] = employee_id

            resp = httpx.get(f"{base_url}/absence/find-all", headers=headers, params=params, timeout=30)
            if resp.status_code != 200:
                return {"success": False, "reason": f"api_{resp.status_code}", "total_importadas": 0}

            data = resp.json()
            absences = data if isinstance(data, list) else data.get("content", data.get("data", []))

            ferias_types = {"FERIAS", "VACATION", "FÉRIAS", "ANNUAL_LEAVE", "FOLGA"}
            ferias = [
                a
                for a in absences
                if str(a.get("type", "")).upper() in ferias_types
                or "FERIA" in str(a.get("type", "")).upper()
                or "VACATION" in str(a.get("type", "")).upper()
            ]

            for absence in ferias:
                try:
                    solides_id = str(absence.get("id", ""))
                    solides_emp_id = str(absence.get("employeeId") or absence.get("employee_id", ""))
                    start_raw = absence.get("startDate") or absence.get("start_date", "")
                    end_raw = absence.get("endDate") or absence.get("end_date", start_raw)
                    if not start_raw:
                        continue

                    row = (
                        await self.db.execute(
                            text("SELECT employee_id FROM solides_employees WHERE solides_id::text = :sid LIMIT 1"),
                            {"sid": solides_emp_id},
                        )
                    ).fetchone()
                    if not row:
                        continue
                    local_emp_id = row[0]

                    source_id = f"solides_ferias_{solides_id}"
                    dup = (
                        await self.db.execute(
                            text("SELECT 1 FROM gp_justifications WHERE source_id = :sid LIMIT 1"),
                            {"sid": source_id},
                        )
                    ).fetchone()
                    if dup:
                        atualizadas += 1
                        continue

                    await self.db.execute(
                        text("""
                            INSERT INTO gp_justifications
                            (justification_id, employee_id, justification_type, reason, category,
                             status, source, source_id, created_at)
                            VALUES (:jid, :eid, 'falta',
                                    :reason, 'outro', 'aprovada', 'solides', :source_id, NOW())
                        """),
                        {
                            "jid": str(uuid4()),
                            "eid": local_emp_id,
                            "reason": f"Férias Sólides: {start_raw[:10]} a {end_raw[:10] if end_raw else start_raw[:10]}",
                            "source_id": source_id,
                        },
                    )
                    await self.db.flush()
                    importadas += 1

                except Exception as e:
                    erros.append({"absence_id": str(absence.get("id", "")), "error": str(e)[:200]})

        except Exception as e:
            logger.error("sync_vacations_from_solides erro: %s", e)
            return {"success": False, "error": str(e), "total_importadas": 0}

        logger.info(
            "sync_vacations_from_solides: %d importadas, %d atualizadas, %d erros",
            importadas,
            atualizadas,
            len(erros),
        )
        return {
            "success": True,
            "total_importadas": importadas,
            "total_atualizadas": atualizadas,
            "total_erros": len(erros),
            "erros": erros,
        }
