"""Service de batida de ponto — persiste no PostgreSQL.

Usa ClockPunchModel, JustificationModel e MonthlyClosingModel
para INSERT/SELECT/UPDATE na tabela gp_clock_punches.
Valida geofence via coordenadas do posto (Haversine).
"""

import logging
import math
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import extract, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.clock_punch import ClockPunchModel
from ..models.justification import JustificationModel
from ..models.monthly_closing import MonthlyClosingModel
from ..schemas.punch_schemas import JustificationCreate, PunchCreate

logger = logging.getLogger(__name__)

# Raio padrao de geofence em metros
GEOFENCE_RADIUS_METERS = 200.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia em metros entre dois pontos via formula Haversine.

    Args:
        lat1, lon1: Coordenadas do ponto 1 (graus decimais).
        lat2, lon2: Coordenadas do ponto 2 (graus decimais).

    Returns:
        Distancia em metros.
    """
    r = 6_371_000  # raio da Terra em metros
    p = math.pi / 180
    a = (
        0.5
        - math.cos((lat2 - lat1) * p) / 2
        + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    )
    return 2 * r * math.asin(math.sqrt(a))


class PunchService:
    """Service para operacoes de ponto eletronico com persistencia no banco."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def registrar_batida(self, data: PunchCreate) -> dict[str, Any]:
        """Registra uma batida de ponto no banco de dados.

        Args:
            data: Dados da batida (employee_id, tipo, facial, geo, etc.)

        Returns:
            Dicionario com os dados da batida registrada.
        """
        punch_id = str(uuid4())
        now = datetime.utcnow()
        timestamp = data.timestamp or now.isoformat()

        # Determinar status
        status = "normal"
        if data.is_offline:
            status = "offline"

        # Geofence check — validacao real via coordenadas do posto
        dentro_geofence = None
        distancia_metros = None
        posto_id = data.posto_id
        posto_nome = None

        if data.location and data.location.latitude and data.location.longitude:
            geofence = await self._validar_geofence(
                employee_id=data.employee_id,
                lat=data.location.latitude,
                lon=data.location.longitude,
                posto_id=posto_id,
            )
            dentro_geofence = geofence["dentro"]
            distancia_metros = geofence["distancia_metros"]
            posto_id = geofence.get("posto_id") or posto_id
            posto_nome = geofence.get("posto_nome")

            if not dentro_geofence:
                status = "fora_local"

        # Criar model e persistir
        punch = ClockPunchModel(
            punch_id=punch_id,
            employee_id=data.employee_id,
            punch_type=data.punch_type,
            punch_timestamp=datetime.fromisoformat(str(timestamp)),
            server_timestamp=now,
            status=status,
            facial_match=data.facial.match if data.facial else None,
            facial_confidence=data.facial.confidence if data.facial else None,
            latitude=data.location.latitude if data.location else None,
            longitude=data.location.longitude if data.location else None,
            dentro_geofence=dentro_geofence,
            distancia_posto_metros=distancia_metros,
            device_type=data.device_type or "web",
            is_offline=data.is_offline or False,
            posto_id=str(posto_id) if posto_id else None,
            posto_nome=str(posto_nome) if posto_nome else None,
        )
        self.db.add(punch)
        await self.db.flush()

        # Push bidirecional para Sólides (não bloqueia se falhar)
        await self._push_punch_to_solides(
            data.employee_id, data.punch_type, str(timestamp), status, data.device_type or "web"
        )

        logger.info(
            "Batida registrada no banco: %s employee=%s type=%s",
            punch_id,
            data.employee_id,
            data.punch_type,
        )
        return punch.to_dict()

    async def sync_offline_punches(self, punches: list[PunchCreate]) -> dict[str, Any]:
        """Sincroniza batidas feitas em modo offline.

        Verifica duplicatas por employee_id + timestamp + tipo antes de inserir.

        Args:
            punches: Lista de batidas offline para sincronizar.

        Returns:
            Resumo da sincronizacao (synced, duplicates, errors).
        """
        synced = 0
        duplicates = 0
        errors: list[dict[str, Any]] = []

        for p in punches:
            # Verificar duplicata no banco
            ts = p.timestamp or datetime.utcnow().isoformat()
            existing = await self.db.execute(
                select(ClockPunchModel.id)
                .where(
                    ClockPunchModel.employee_id == p.employee_id,
                    ClockPunchModel.punch_type == p.punch_type,
                    ClockPunchModel.punch_timestamp == datetime.fromisoformat(str(ts)),
                )
                .limit(1)
            )
            if existing.scalar_one_or_none():
                duplicates += 1
                continue

            try:
                await self.registrar_batida(p)
                synced += 1
            except Exception as e:
                logger.warning("Erro ao sincronizar batida: %s", e)
                errors.append({"employee_id": p.employee_id, "error": str(e)[:200]})

        return {
            "total_received": len(punches),
            "total_synced": synced,
            "total_duplicates": duplicates,
            "total_errors": len(errors),
            "errors": errors,
        }

    async def get_batidas_dia(self, employee_id: str, dia: str) -> list[dict[str, Any]]:
        """Retorna batidas de um funcionario em um dia especifico.

        Args:
            employee_id: ID do funcionario.
            dia: Data no formato YYYY-MM-DD.

        Returns:
            Lista de batidas do dia.
        """
        result = await self.db.execute(
            select(ClockPunchModel)
            .where(
                ClockPunchModel.employee_id == employee_id,
                func.date(ClockPunchModel.punch_timestamp) == func.date(dia),
            )
            .order_by(ClockPunchModel.punch_timestamp)
        )
        return [p.to_dict() for p in result.scalars().all()]

    async def get_espelho_mensal(self, employee_id: str, month: int, year: int) -> dict[str, Any]:
        """Retorna espelho de ponto mensal com totais.

        Args:
            employee_id: ID do funcionario.
            month: Mes (1-12).
            year: Ano.

        Returns:
            Dicionario com batidas do mes e totais.
        """
        result = await self.db.execute(
            select(ClockPunchModel)
            .where(
                ClockPunchModel.employee_id == employee_id,
                extract("month", ClockPunchModel.punch_timestamp) == month,
                extract("year", ClockPunchModel.punch_timestamp) == year,
            )
            .order_by(ClockPunchModel.punch_timestamp)
        )
        punches = list(result.scalars().all())
        batidas = [p.to_dict() for p in punches]

        # Agrupa as batidas por dia para montar o espelho (formato que o front consome:
        # dias[] com entrada1/saida1/entrada2/saida2/total). Cada par entrada->saida
        # soma minutos trabalhados; lidamos com até 2 pares (manhã/tarde) por dia.
        _SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sab", "Dom"]
        por_dia: dict[Any, list[ClockPunchModel]] = {}
        for p in punches:
            if not p.punch_timestamp:
                continue
            por_dia.setdefault(p.punch_timestamp.date(), []).append(p)

        def _hhmm(dt: datetime | None) -> str:
            return dt.strftime("%H:%M") if dt else ""

        dias: list[dict[str, Any]] = []
        total_min = 0
        for data_dia in sorted(por_dia):
            ps = sorted(por_dia[data_dia], key=lambda x: x.punch_timestamp)
            entradas = [
                x.punch_timestamp
                for x in ps
                if "entrada" in (x.punch_type or "").lower() or "retorno" in (x.punch_type or "").lower()
            ]
            saidas = [x.punch_timestamp for x in ps if "saida" in (x.punch_type or "").lower()]
            # se não houver tipagem confiável, intercala pela ordem (par/ímpar)
            if not entradas and not saidas:
                entradas = [x.punch_timestamp for i, x in enumerate(ps) if i % 2 == 0]
                saidas = [x.punch_timestamp for i, x in enumerate(ps) if i % 2 == 1]
            e1 = entradas[0] if len(entradas) > 0 else None
            s1 = saidas[0] if len(saidas) > 0 else None
            e2 = entradas[1] if len(entradas) > 1 else None
            s2 = saidas[1] if len(saidas) > 1 else None
            dia_min = 0
            for ent, sai in ((e1, s1), (e2, s2)):
                if ent and sai and sai > ent:
                    dia_min += int((sai - ent).total_seconds() // 60)
            total_min += dia_min
            dias.append(
                {
                    "dia": data_dia.strftime("%d/%m"),
                    "data": data_dia.isoformat(),
                    "dia_semana": _SEMANA[data_dia.weekday()],
                    "entrada1": _hhmm(e1),
                    "saida1": _hhmm(s1),
                    "entrada2": _hhmm(e2),
                    "saida2": _hhmm(s2),
                    "total": f"{dia_min // 60:02d}:{dia_min % 60:02d}",
                    "obs": "",
                }
            )

        total_trabalhado = f"{total_min // 60:02d}:{total_min % 60:02d}"

        return {
            "employee_id": employee_id,
            "month": month,
            "year": year,
            "competencia": f"{month:02d}/{year}",
            "total_batidas": len(batidas),
            "total_dias": len(dias),
            "total_trabalhado": total_trabalhado,
            "dias": dias,
            "batidas": batidas,
        }

    async def criar_justificativa(self, data: JustificationCreate) -> dict[str, Any]:
        """Cria uma justificativa de atraso ou falta no banco.

        Args:
            data: Dados da justificativa.

        Returns:
            Dicionario com a justificativa criada.
        """
        justification = JustificationModel(
            justification_id=str(uuid4()),
            employee_id=data.employee_id,
            punch_id=data.punch_id,
            justification_type=data.justification_type,
            reason=data.reason,
            category=data.category,
            status="pendente",
            attachments=data.attachments or [],
        )
        self.db.add(justification)
        await self.db.flush()

        # Push best-effort p/ Sólides em SAVEPOINT: se a query/conector falhar, faz rollback SÓ do
        # savepoint — a justificativa acima é preservada. Antes, a falha (coluna inexistente em
        # solides_employees) abortava a transação toda e o commit do get_db virava rollback
        # silencioso → justificativa perdida com 201 falso (data loss).
        try:
            async with self.db.begin_nested():
                await self._push_justification_to_solides(
                    data.employee_id, data.justification_type, data.reason, data.category
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("Push Sólides falhou (justificativa preservada): %s", e)

        logger.info("Justificativa criada: %s", justification.justification_id)
        return justification.to_dict()

    async def revisar_justificativa(
        self,
        justification_id: str,
        action: str,
        reviewer_id: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Aprova ou rejeita uma justificativa.

        Args:
            justification_id: ID da justificativa.
            action: 'aprovar' ou 'rejeitar'.
            reviewer_id: ID do revisor.
            notes: Observacoes do revisor.

        Returns:
            Dicionario com a justificativa atualizada.

        Raises:
            ValueError: Se justificativa nao encontrada.
        """
        result = await self.db.execute(
            select(JustificationModel).where(JustificationModel.justification_id == justification_id)
        )
        justification = result.scalar_one_or_none()
        if not justification:
            raise ValueError(f"Justificativa {justification_id} nao encontrada")

        justification.status = "aprovada" if action == "aprovar" else "rejeitada"
        justification.reviewed_by = reviewer_id
        justification.reviewed_at = datetime.utcnow()
        justification.review_notes = notes

        await self.db.flush()

        # Push bidirecional: envia status de revisão para Sólides
        await self._push_justification_review_to_solides(
            justification_id=justification_id,
            source_id=justification.source_id if hasattr(justification, "source_id") else None,
            approved=(action == "aprovar"),
            reviewer_notes=notes,
        )

        return justification.to_dict()

    async def get_justificativas_pendentes(self, employee_id: int | None = None) -> list[dict[str, Any]]:
        """Retorna justificativas pendentes de aprovacao.

        Args:
            employee_id: Filtro opcional por funcionario.

        Returns:
            Lista de justificativas pendentes.
        """
        query = select(JustificationModel).where(JustificationModel.status == "pendente")
        if employee_id:
            query = query.where(JustificationModel.employee_id == employee_id)

        query = query.order_by(JustificationModel.created_at.desc())
        result = await self.db.execute(query)
        return [j.to_dict() for j in result.scalars().all()]

    async def fechar_mes(
        self,
        employee_id: str,  # [Ponto loop] era int — employee_id e UUID
        month: int,
        year: int,
        fechado_por: str,
    ) -> dict[str, Any]:
        """Fecha o ponto mensal de um funcionario.

        Calcula totais de horas, extras, faltas e atrasos a partir
        das batidas do mes e persiste em gp_monthly_closings.

        Args:
            employee_id: ID do funcionario.
            month: Mes (1-12).
            year: Ano.
            fechado_por: ID de quem esta fechando.

        Returns:
            Dicionario com o fechamento.
        """
        # Contar batidas do mes
        count_result = await self.db.execute(
            select(func.count(ClockPunchModel.id)).where(
                ClockPunchModel.employee_id == employee_id,
                extract("month", ClockPunchModel.punch_timestamp) == month,
                extract("year", ClockPunchModel.punch_timestamp) == year,
            )
        )
        total_batidas = count_result.scalar() or 0

        # Estimar dias trabalhados (4 batidas = 1 dia)
        dias_trabalhados = total_batidas // 4 if total_batidas >= 4 else 0

        closing = MonthlyClosingModel(
            employee_id=employee_id,
            month=month,
            year=year,
            total_horas_trabalhadas=dias_trabalhados * 8.0,
            total_horas_extras_50=0.0,
            total_horas_extras_100=0.0,
            total_horas_noturnas=0.0,
            total_faltas=0,
            total_atrasos_minutos=0.0,
            total_dias_trabalhados=dias_trabalhados,
            fechado=True,
            fechado_por=fechado_por,
            fechado_em=datetime.utcnow(),
        )
        self.db.add(closing)
        await self.db.flush()

        logger.info(
            "Ponto fechado: employee=%s %02d/%d (%d batidas, %d dias)",
            employee_id,
            month,
            year,
            total_batidas,
            dias_trabalhados,
        )
        return closing.to_dict()

    # =========================================================================
    # PUSH SÓLIDES (Conecta PRO → Sólides)
    # =========================================================================

    async def _push_punch_to_solides(
        self,
        employee_id: str | int,
        punch_type: str,
        punch_timestamp: str,
        status: str,
        device_type: str,
    ) -> None:
        """Push batida para Sólides via connector — nunca bloqueia em caso de erro."""
        import os

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return  # Integração não configurada

        try:
            # Use savepoint to isolate Sólides query — prevents aborting the main transaction on failure
            async with self.db.begin_nested():
                result = await self.db.execute(
                    text("SELECT solides_id FROM solides_employees WHERE employee_id::text = :eid LIMIT 1"),
                    {"eid": str(employee_id)},
                )
                row = result.first()
                if not row or not row[0]:
                    logger.debug("Push Sólides: employee %s sem solides_id mapeado", employee_id)
                    return

                solides_employee_id = str(row[0])

            from modules.integrations.connectors.solides.connector import SolidesConnector

            connector = SolidesConnector(credentials={"api_token": api_token})
            await connector.push_punch_as_occurrence(
                employee_solides_id=solides_employee_id,
                punch_type=punch_type,
                punch_timestamp=punch_timestamp,
                status=status,
                device_type=device_type,
            )
        except Exception as e:
            logger.warning("Push Sólides (batida) falhou — não crítico: %s", e)

    async def _push_justification_to_solides(
        self,
        employee_id: int,
        justification_type: str,
        reason: str,
        category: str,
    ) -> None:
        """Push justificativa para Sólides como absenteísmo — nunca bloqueia em caso de erro."""
        import os

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return

        try:
            result = await self.db.execute(
                text("SELECT solides_id FROM solides_employees WHERE employee_id::text = :eid LIMIT 1"),
                {"eid": str(employee_id)},
            )
            row = result.first()
            if not row or not row[0]:
                return

            solides_employee_id = str(row[0])
            start_date = datetime.utcnow().date().isoformat()

            from modules.integrations.connectors.solides.connector import SolidesConnector

            connector = SolidesConnector(credentials={"api_token": api_token})
            await connector.push_justification_as_absence(
                employee_solides_id=solides_employee_id,
                justification_type=justification_type,
                reason=reason,
                category=category,
                start_date=start_date,
            )
        except Exception:
            # propaga p/ o SAVEPOINT do chamador (criar_justificativa) fazer rollback isolado;
            # a justificativa já persistida é preservada. NÃO engolir aqui (engolir deixava a
            # transação async abortada e o commit virava rollback silencioso).
            raise

    async def _push_justification_review_to_solides(
        self,
        justification_id: str,
        source_id: str | None,
        approved: bool,
        reviewer_notes: str | None,
    ) -> None:
        """Push de aprovação/rejeição de justificativa para Sólides — nunca bloqueia."""
        import os

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return

        # Extrair o ID do Sólides do source_id (formato: "solides_abs_123" ou "solides_occ_123")
        if not source_id:
            # Tentar buscar do DB
            try:
                result = await self.db.execute(
                    text("SELECT source_id FROM gp_justifications WHERE justification_id = :jid LIMIT 1"),
                    {"jid": justification_id},
                )
                row = result.fetchone()
                if row:
                    source_id = row[0]
            except Exception:
                return

        if not source_id or not source_id.startswith("solides_"):
            return  # Justificativa local, não do Sólides

        # Extrair ID Sólides do source_id
        # Formatos: "solides_abs_123" → "123" | "solides_occ_123" → "123"
        parts = source_id.split("_")
        if len(parts) < 3:
            return
        solides_absence_id = parts[-1]

        try:
            from modules.integrations.connectors.solides.connector import SolidesConnector

            connector = SolidesConnector(credentials={"api_token": api_token})
            await connector.update_absence_status(
                absence_solides_id=solides_absence_id,
                approved=approved,
                reviewer_notes=reviewer_notes,
            )
        except Exception as e:
            logger.warning("Push review Sólides falhou — não crítico: %s", e)

    # =========================================================================
    # GEOFENCE
    # =========================================================================

    async def _validar_geofence(
        self,
        employee_id: int | str,
        lat: float,
        lon: float,
        posto_id: int | str | None = None,
    ) -> dict[str, Any]:
        """Valida se o funcionario esta dentro do raio do posto.

        Busca o posto via:
        1. posto_id informado na batida
        2. Alocacao ativa do funcionario (allocations)
        3. Geofence zone vinculada ao posto

        Args:
            employee_id: ID do funcionario.
            lat: Latitude da batida.
            lon: Longitude da batida.
            posto_id: ID do posto (opcional).

        Returns:
            Dict com 'dentro' (bool), 'distancia_metros' (float),
            'posto_id', 'posto_nome', 'raio_metros'.
        """
        posto_lat = None
        posto_lon = None
        posto_nome = None
        raio = GEOFENCE_RADIUS_METERS

        try:
            # 1. Buscar posto por ID ou alocacao ativa
            if posto_id:
                row = await self.db.execute(
                    text("SELECT id, name, latitude, longitude FROM posts WHERE id::text = :pid"),
                    {"pid": str(posto_id)},
                )
            else:
                # Buscar posto via alocacao ativa do funcionario
                row = await self.db.execute(
                    text(
                        "SELECT p.id, p.name, p.latitude, p.longitude "
                        "FROM allocations a "
                        "JOIN posts p ON a.post_id = p.id "
                        "WHERE a.employee_id::text = :eid AND a.status = 'active' "
                        "ORDER BY a.created_at DESC LIMIT 1"
                    ),
                    {"eid": str(employee_id)},
                )
            posto = row.first()

            if posto:
                posto_id = str(posto[0])
                posto_nome = str(posto[1]) if posto[1] else None
                posto_lat = posto[2]
                posto_lon = posto[3]

            # 2. Se posto sem coords, tentar geofence_zones
            if not posto_lat or not posto_lon:
                gz_row = await self.db.execute(
                    text(
                        "SELECT center_latitude, center_longitude, radius_meters, name "
                        "FROM geofence_zones "
                        "WHERE post_id::text = :pid AND status = 'active' "
                        "LIMIT 1"
                    ),
                    {"pid": str(posto_id) if posto_id else ""},
                )
                gz = gz_row.first()
                if gz:
                    posto_lat = gz[0]
                    posto_lon = gz[1]
                    raio = gz[2] or GEOFENCE_RADIUS_METERS

        except Exception as exc:
            logger.warning("Erro ao buscar geofence: %s", exc)

        # 3. Calcular distancia
        if posto_lat and posto_lon:
            distancia = _haversine(lat, lon, posto_lat, posto_lon)
            dentro = distancia <= raio

            logger.info(
                "Geofence: employee=%s posto=%s dist=%.0fm raio=%.0fm %s",
                employee_id,
                posto_nome,
                distancia,
                raio,
                "DENTRO" if dentro else "FORA",
            )

            return {
                "dentro": dentro,
                "distancia_metros": round(distancia, 1),
                "posto_id": posto_id,
                "posto_nome": posto_nome,
                "raio_metros": raio,
            }

        # Sem coordenadas do posto — nao valida
        logger.info("Geofence: sem coordenadas do posto para employee=%s", employee_id)
        return {
            "dentro": None,
            "distancia_metros": None,
            "posto_id": posto_id,
            "posto_nome": posto_nome,
            "raio_metros": raio,
        }
