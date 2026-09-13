"""Repository para AFDRecord."""

import hashlib
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.hr.rep_integration.models import (
    AFDRecord,
    AFDRecordType,
)
from modules.hr.rep_integration.schemas import (
    AFDRecordCreate,
    AFDRecordFilter,
)


class AFDRecordRepository:
    """Repository para operações de AFDRecord."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: AFDRecordCreate) -> AFDRecord:
        """Cria novo registro AFD."""
        record = AFDRecord(
            device_id=data.device_id,
            condominio_id=data.condominio_id,
            nsr=data.nsr,
            record_type=data.record_type,
            afd_line=data.afd_line,
            record_date=data.record_date,
            record_time=data.record_time,
            pis_number=data.pis_number,
            cnpj=data.cnpj,
            cei=data.cei,
            company_name=data.company_name,
            rep_serial=data.rep_serial,
            rep_manufacturer=data.rep_manufacturer,
            rep_model=data.rep_model,
            generation_date=data.generation_date,
            start_date=data.start_date,
            end_date=data.end_date,
            original_date=data.original_date,
            original_time=data.original_time,
            adjusted_date=data.adjusted_date,
            adjusted_time=data.adjusted_time,
            event_id=data.event_id,
            line_hash=data.line_hash,
        )

        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def create_from_event(
        self,
        device_id: UUID,
        condominio_id: UUID,
        nsr: int,
        record_date: date,
        record_time,
        pis_number: str,
        event_id: UUID = None,
    ) -> AFDRecord:
        """Cria registro AFD tipo 3 a partir de um evento."""
        afd_line = AFDRecord.generate_type3_record(
            nsr=nsr,
            record_date=record_date,
            record_time=record_time,
            pis=pis_number,
        )

        line_hash = hashlib.sha256(afd_line.encode()).hexdigest()

        record = AFDRecord(
            device_id=device_id,
            condominio_id=condominio_id,
            nsr=nsr,
            record_type=AFDRecordType.TIME_RECORD.value,
            afd_line=afd_line,
            record_date=record_date,
            record_time=record_time,
            pis_number=pis_number,
            event_id=event_id,
            line_hash=line_hash,
        )

        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_by_id(self, record_id: UUID) -> AFDRecord | None:
        """Busca registro por ID."""
        result = await self.db.execute(select(AFDRecord).where(AFDRecord.id == record_id))
        return result.scalar_one_or_none()

    async def get_by_device_nsr(
        self,
        device_id: UUID,
        nsr: int,
    ) -> AFDRecord | None:
        """Busca registro por dispositivo e NSR."""
        result = await self.db.execute(
            select(AFDRecord).where(
                AFDRecord.device_id == device_id,
                AFDRecord.nsr == nsr,
            )
        )
        return result.scalar_one_or_none()

    async def list_records(
        self,
        filters: AFDRecordFilter,
        page: int = 1,
        page_size: int = 100,
    ) -> tuple[list[AFDRecord], int]:
        """Lista registros com filtros e paginação."""
        query = select(AFDRecord)

        # Aplicar filtros
        if filters.device_id:
            query = query.where(AFDRecord.device_id == filters.device_id)
        if filters.condominio_id:
            query = query.where(AFDRecord.condominio_id == filters.condominio_id)
        if filters.record_type:
            query = query.where(AFDRecord.record_type == filters.record_type)
        if filters.pis_number:
            query = query.where(AFDRecord.pis_number == filters.pis_number)
        if filters.date_from:
            query = query.where(AFDRecord.record_date >= filters.date_from)
        if filters.date_to:
            query = query.where(AFDRecord.record_date <= filters.date_to)
        if filters.is_exported is not None:
            query = query.where(AFDRecord.is_exported == filters.is_exported)
        if filters.is_valid is not None:
            query = query.where(AFDRecord.is_valid == filters.is_valid)
        if filters.nsr_from:
            query = query.where(AFDRecord.nsr >= filters.nsr_from)
        if filters.nsr_to:
            query = query.where(AFDRecord.nsr <= filters.nsr_to)

        # Contagem total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginação
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size)
        query = query.order_by(AFDRecord.nsr)

        result = await self.db.execute(query)
        records = result.scalars().all()

        return list(records), total

    async def get_records_for_export(
        self,
        device_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[AFDRecord]:
        """Retorna registros para exportação AFD."""
        result = await self.db.execute(
            select(AFDRecord)
            .where(
                AFDRecord.device_id == device_id,
                AFDRecord.record_type == AFDRecordType.TIME_RECORD.value,
                AFDRecord.record_date >= start_date,
                AFDRecord.record_date <= end_date,
                AFDRecord.is_valid.is_(True),
            )
            .order_by(AFDRecord.nsr)
        )
        return list(result.scalars().all())

    async def generate_afd_file(  # pylint: disable=too-many-locals
        self,
        device_id: UUID,
        start_date: date,
        end_date: date,
        company_cnpj: str,
        company_cei: str,
        company_name: str,
        rep_serial: str,
        manufacturer: str,
        model: str,
    ) -> str:
        """Gera conteúdo do arquivo AFD completo."""
        lines = []

        # Buscar registros
        records = await self.get_records_for_export(device_id, start_date, end_date)

        if not records:
            return ""

        # Calcular NSRs
        nsr_header = 1
        nsr_company = 2
        nsr_trailer = len(records) + 3

        # Tipo 1 - Cabeçalho
        header = AFDRecord.generate_type1_header(
            nsr=nsr_header,
            rep_serial=rep_serial,
            manufacturer=manufacturer,
            model=model,
            start_date=start_date,
            end_date=end_date,
        )
        lines.append(header)

        # Tipo 2 - Empregador
        company = AFDRecord.generate_type2_company(
            nsr=nsr_company,
            cnpj=company_cnpj,
            cei=company_cei,
            company_name=company_name,
        )
        lines.append(company)

        # Tipo 3 - Marcações
        for record in records:
            lines.append(record.afd_line)

        # Tipo 9 - Trailer
        trailer = AFDRecord.generate_type9_trailer(
            nsr=nsr_trailer,
            total_records=len(records),
        )
        lines.append(trailer)

        return "\n".join(lines)

    async def mark_as_exported(
        self,
        record_ids: list[UUID],
        export_file_id: UUID = None,
    ) -> int:
        """Marca registros como exportados."""
        result = await self.db.execute(
            update(AFDRecord)
            .where(AFDRecord.id.in_(record_ids))
            .values(
                is_exported=True,
                exported_at=datetime.utcnow(),
                export_file_id=export_file_id,
            )
        )
        await self.db.commit()
        return result.rowcount

    async def validate_afd_line(self, line: str) -> dict:
        """Valida uma linha AFD."""
        errors = []

        if len(line) < 10:
            errors.append("Linha muito curta (mínimo 10 caracteres)")
            return {"is_valid": False, "errors": errors}

        # NSR
        try:
            nsr = int(line[0:9])
            if nsr <= 0:
                errors.append("NSR deve ser maior que zero")
        except ValueError:
            errors.append("NSR inválido")

        # Tipo
        record_type = line[9]
        if record_type not in ["1", "2", "3", "4", "9"]:
            errors.append(f"Tipo de registro inválido: {record_type}")

        # Validações específicas por tipo
        if record_type == "3":
            if len(line) < 34:
                errors.append("Registro tipo 3 incompleto")
            else:
                # Data
                try:
                    datetime.strptime(line[10:18], "%d%m%Y")
                except ValueError:
                    errors.append("Data inválida")

                # Hora
                try:
                    datetime.strptime(line[18:22], "%H%M")
                except ValueError:
                    errors.append("Hora inválida")

                # PIS
                pis = line[22:34].strip()
                if not pis.isdigit():
                    errors.append("PIS deve conter apenas dígitos")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "nsr": nsr if "nsr" in dir() else None,
            "record_type": record_type,
        }

    async def get_last_nsr(self, device_id: UUID) -> int | None:
        """Retorna último NSR do dispositivo."""
        result = await self.db.execute(select(func.max(AFDRecord.nsr)).where(AFDRecord.device_id == device_id))
        return result.scalar()

    async def get_statistics(
        self,
        device_id: UUID = None,
        condominio_id: UUID = None,
    ) -> dict:
        """Retorna estatísticas de registros AFD."""
        base_where = []
        if device_id:
            base_where.append(AFDRecord.device_id == device_id)
        if condominio_id:
            base_where.append(AFDRecord.condominio_id == condominio_id)

        # frente 01: os `select(func.count())` sem FROM contavam 1 (o SELECT sozinho) e o
        # group_by só existia no ramo sem filtro — a rota dizia "1 registro" havendo 1.116.
        base = select(func.count(AFDRecord.id))
        for w in base_where:
            base = base.where(w)
        total = (await self.db.execute(base)).scalar() or 0

        por_tipo_q = select(AFDRecord.record_type, func.count(AFDRecord.id))
        for w in base_where:
            por_tipo_q = por_tipo_q.where(w)
        by_type = dict((await self.db.execute(por_tipo_q.group_by(AFDRecord.record_type))).all())

        exported = (await self.db.execute(base.where(AFDRecord.is_exported.is_(True)))).scalar() or 0
        invalid = (await self.db.execute(base.where(AFDRecord.is_valid.is_(False)))).scalar() or 0

        return {
            "total_records": total,
            "records_by_type": by_type,
            "exported_count": exported,
            "pending_export": total - exported,
            "invalid_count": invalid,
            # tipo 3 é marcação de REP-C/REP-A; tipo 7 é a nossa, de REP-P
            "time_records": by_type.get("3", 0) + by_type.get("7", 0),
        }
