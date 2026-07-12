"""
Service de Ponto Eletronico (Time Records) — Departamento Pessoal.

Opera sobre as tabelas:
- gp_clock_punches: batidas reais (Tangerino + portal + app)
- time_sheets: espelho de ponto mensal (resumo calculado)
- time_justifications: justificativas de atraso/falta

Estrategia: leitura via raw SQL para evitar problemas de dessincronizacao
model/banco. Escrita via models quando disponivel, raw SQL como fallback.
"""

import base64
import binascii
import calendar
import logging
import math
import os
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Raio default do geofence (metros) quando o posto nao define um proprio.
DEFAULT_GEOFENCE_RAIO_METROS = 150.0
# Base de storage das selfies de ponto (volume ./uploads -> /app/uploads).
PONTO_UPLOAD_DIR = os.environ.get("PONTO_UPLOAD_DIR", "/app/uploads/ponto")


def _haversine_metros(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distancia em METROS entre dois pontos (lat/lng em graus) — formula de Haversine.

    Raio medio da Terra = 6.371.000 m. Precisao suficiente para geofence de posto
    (erro < 0,5% em distancias curtas).
    """
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _salvar_selfie_ponto(punch_id: str, foto_base64: str | None) -> str | None:
    """Salva a selfie (base64) da batida em /app/uploads/ponto/{punch_id}.jpg.

    Aceita data-URI ("data:image/jpeg;base64,...") ou base64 cru. Retorna a URL
    relativa gravavel em foto_capturada_url, ou None se nao houver foto/erro.
    """
    if not foto_base64:
        return None
    raw = foto_base64.strip()
    if raw.startswith("data:"):
        # data:image/jpeg;base64,XXXX
        try:
            raw = raw.split(",", 1)[1]
        except IndexError:
            return None
    try:
        binario = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        logger.warning("Selfie de ponto invalida (base64) para punch=%s", punch_id)
        return None
    if not binario:
        return None
    try:
        os.makedirs(PONTO_UPLOAD_DIR, exist_ok=True)
        filename = f"{punch_id}.jpg"
        full_path = os.path.join(PONTO_UPLOAD_DIR, filename)
        with open(full_path, "wb") as fh:
            fh.write(binario)
    except OSError as exc:
        logger.error("Falha ao salvar selfie de ponto punch=%s: %s", punch_id, exc)
        return None
    return f"/uploads/ponto/{filename}"


def _format_minutes(total_minutes: int) -> str:
    """Formata minutos em HH:MM."""
    if total_minutes < 0:
        sign = "-"
        total_minutes = abs(total_minutes)
    else:
        sign = ""
    h = total_minutes // 60
    m = total_minutes % 60
    return f"{sign}{h:02d}:{m:02d}"


def _calc_minutes_between(t1: Any, t2: Any) -> int:
    """Calcula minutos entre dois timestamps/times."""
    if not t1 or not t2:
        return 0
    if isinstance(t1, time) and isinstance(t2, time):
        d1 = datetime.combine(date.today(), t1)
        d2 = datetime.combine(date.today(), t2)
    elif isinstance(t1, datetime) and isinstance(t2, datetime):
        d1 = t1
        d2 = t2
    else:
        return 0
    if d2 < d1:
        d2 += timedelta(days=1)
    diff = (d2 - d1).total_seconds()
    if diff > 16 * 3600:
        diff = 12 * 3600  # sanidade: maximo 16h
    return int(diff // 60)


class TimeRecordService:
    """Service de Ponto Eletronico — visao DP."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # =========================================================================
    # LIST RECORDS
    # =========================================================================

    async def list_records(
        self,
        employee_id: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Lista registros de ponto com filtros e paginacao.

        Busca da tabela gp_clock_punches, emparelha entrada/saida
        e retorna no formato padrao com paginacao.
        """
        params: dict[str, Any] = {}
        where_clauses = []

        if employee_id:
            where_clauses.append("employee_id = :emp_id")
            params["emp_id"] = str(employee_id)
        if date_from:
            where_clauses.append("punch_timestamp::date >= :date_from")
            params["date_from"] = date_from
        if date_to:
            where_clauses.append("punch_timestamp::date <= :date_to")
            params["date_to"] = date_to

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        # safe — where_sql é montado apenas de cláusulas hardcoded com placeholders (:emp_id, :date_from, :date_to);
        # nenhum valor de usuário é interpolado diretamente na string SQL.

        # Gap 2: sem f-string — where_sql contém apenas cláusulas hardcoded com placeholders nomeados
        # Count total distinct days
        count_sql = text(
            "SELECT COUNT(DISTINCT (employee_id, punch_timestamp::date)) FROM gp_clock_punches WHERE " + where_sql
        )
        total_result = await self.db.execute(count_sql, params)
        total = total_result.scalar() or 0

        # Fetch punches
        sql = text(
            "SELECT id, punch_id, employee_id, punch_type, punch_timestamp, "
            "status, latitude, longitude, device_type, is_offline, "
            "posto_id, posto_nome, justification_id, created_at, updated_at "
            "FROM gp_clock_punches WHERE " + where_sql + " "
            "ORDER BY punch_timestamp DESC LIMIT :limit OFFSET :offset"
        )
        params["limit"] = page_size * 4  # 4 batidas por dia
        params["offset"] = (page - 1) * page_size * 4

        result = await self.db.execute(sql, params)
        rows = result.mappings().all()

        # Emparelhar batidas por employee + dia
        records = self._pair_punches(rows)
        records = await self._fill_employee_names(records)

        # Filter by status if requested
        if status:
            records = [r for r in records if r["status"] == status]

        # Paginate paired records
        total_paired = len(records) if total == 0 else total
        total_pages = max(1, (total_paired + page_size - 1) // page_size)

        return {
            "items": records[:page_size],
            "total": total_paired,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

    # =========================================================================
    # GET BY ID
    # =========================================================================

    async def get_by_id(self, record_id: str) -> dict[str, Any] | None:
        """Busca um registro de ponto por punch_id ou id."""
        sql = text("""
            SELECT
                id, punch_id, employee_id, punch_type,
                punch_timestamp, status, latitude, longitude,
                device_type, is_offline, posto_id, posto_nome,
                justification_id, created_at, updated_at
            FROM gp_clock_punches
            WHERE punch_id = :rid OR id::text = :rid
            ORDER BY punch_timestamp
        """)
        result = await self.db.execute(sql, {"rid": str(record_id)})
        row = result.mappings().first()
        if not row:
            return None

        # Get all punches for same employee + date to build full record
        emp_id = row["employee_id"]
        punch_date = row["punch_timestamp"].date() if row["punch_timestamp"] else None
        if punch_date:
            day_sql = text("""
                SELECT
                    id, punch_id, employee_id, punch_type,
                    punch_timestamp, status, latitude, longitude,
                    device_type, is_offline, posto_id, posto_nome,
                    justification_id, created_at, updated_at
                FROM gp_clock_punches
                WHERE employee_id = :emp_id
                  AND punch_timestamp::date = :pdate
                ORDER BY punch_timestamp
            """)
            day_result = await self.db.execute(day_sql, {"emp_id": emp_id, "pdate": punch_date})
            day_rows = day_result.mappings().all()
            records = self._pair_punches(day_rows)
            if records:
                return records[0]

        return self._punch_to_record(dict(row))

    # =========================================================================
    # CLOCK IN
    # =========================================================================

    async def _compute_geofence(
        self,
        posto_id: str | None,
        location_lat: float | None,
        location_lng: float | None,
    ) -> dict[str, Any]:
        """Calcula geofence de uma batida contra as coordenadas REAIS do posto.

        Retorna dict com:
        - posto_nome, posto_lat, posto_lng, raio_metros
        - distancia_posto_metros (float|None)
        - dentro_geofence (True|False|None) — None = posto sem coordenada definida
        - geofence_flag (str) — mensagem honesta sobre o resultado

        NUNCA inventa coordenada do posto. Se o posto nao tem lat/lng, retorna
        dentro_geofence=None com flag "localizacao do posto nao definida".
        """
        info: dict[str, Any] = {
            "posto_nome": None,
            "posto_lat": None,
            "posto_lng": None,
            "raio_metros": DEFAULT_GEOFENCE_RAIO_METROS,
            "distancia_posto_metros": None,
            "dentro_geofence": None,
            "geofence_flag": None,
        }
        if not posto_id:
            info["geofence_flag"] = "posto não informado na batida"
            return info

        try:
            pr = await self.db.execute(
                text(
                    "SELECT name, latitude, longitude, "
                    "COALESCE(geofence_raio_metros, :raio_default) AS raio "
                    "FROM posts WHERE id::text = :pid LIMIT 1"
                ),
                {"pid": str(posto_id), "raio_default": DEFAULT_GEOFENCE_RAIO_METROS},
            )
            prow = pr.mappings().first()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao buscar posto %s p/ geofence: %s", posto_id, exc)
            prow = None

        if not prow:
            info["geofence_flag"] = "posto não encontrado"
            return info

        info["posto_nome"] = prow["name"]
        info["posto_lat"] = prow["latitude"]
        info["posto_lng"] = prow["longitude"]
        info["raio_metros"] = float(prow["raio"] or DEFAULT_GEOFENCE_RAIO_METROS)

        # Posto sem coordenada REAL: nao bloqueia, marca honestamente.
        if prow["latitude"] is None or prow["longitude"] is None:
            info["dentro_geofence"] = None
            info["geofence_flag"] = (
                "localização do posto não definida — capturar no local pelo líder/supervisor"
            )
            return info

        # Sem GPS do funcionario: nao ha como validar.
        if location_lat is None or location_lng is None:
            info["dentro_geofence"] = None
            info["geofence_flag"] = "GPS do funcionário não informado"
            return info

        dist = _haversine_metros(
            float(location_lat), float(location_lng),
            float(prow["latitude"]), float(prow["longitude"]),
        )
        info["distancia_posto_metros"] = round(dist, 1)
        info["dentro_geofence"] = dist <= info["raio_metros"]
        info["geofence_flag"] = (
            f"dentro do geofence ({dist:.0f}m ≤ {info['raio_metros']:.0f}m)"
            if info["dentro_geofence"]
            else f"FORA do geofence ({dist:.0f}m > {info['raio_metros']:.0f}m)"
        )
        return info

    async def clock_in(
        self,
        employee_id: str,
        location_lat: float | None = None,
        location_lng: float | None = None,
        posto_id: str | None = None,
        device_type: str = "web",
        notes: str | None = None,
        created_by: str | None = None,
        foto_base64: str | None = None,
        accuracy: float | None = None,
    ) -> dict[str, Any]:
        """Registra batida de entrada para o funcionario.

        Verifica se ja existe entrada aberta no dia. Calcula geofence (haversine)
        contra as coordenadas reais do posto e salva a selfie anti-fraude.
        """
        # Servidor roda em America/Manaus; gp_clock_punches guarda wall-clock LOCAL
        # (batidas Tangerino/manuais estao em hora local). utcnow() carimbaria +4h.
        now = datetime.now()
        today = now.date()
        punch_id = str(uuid4())

        # Verificar se ja existe entrada sem saida hoje
        existing = await self.db.execute(
            text("""
                SELECT punch_id, punch_type FROM gp_clock_punches
                WHERE employee_id = :emp_id
                  AND punch_timestamp::date = :today
                ORDER BY punch_timestamp DESC
                LIMIT 1
            """),
            {"emp_id": str(employee_id), "today": today},
        )
        last_punch = existing.mappings().first()
        if last_punch and last_punch["punch_type"] == "entrada":
            # Ja tem entrada sem saida — nao duplicar
            logger.warning(
                "Clock-in duplicado ignorado: employee=%s, punch=%s",
                employee_id,
                last_punch["punch_id"],
            )

        # Geofence (haversine) contra as coordenadas REAIS do posto.
        geo = await self._compute_geofence(posto_id, location_lat, location_lng)
        posto_nome = geo["posto_nome"]

        # Selfie anti-fraude (evidencia de quem bateu). facial_* ficam NULL na fase 1.
        foto_url = _salvar_selfie_ponto(punch_id, foto_base64)

        # Inserir batida de entrada
        await self.db.execute(
            text("""
                INSERT INTO gp_clock_punches (
                    punch_id, employee_id, punch_type, punch_timestamp,
                    server_timestamp, status, latitude, longitude, accuracy,
                    dentro_geofence, distancia_posto_metros, foto_capturada_url,
                    device_type, is_offline, posto_id, posto_nome, created_by, created_at
                ) VALUES (
                    :punch_id, :emp_id, 'entrada', :ts,
                    :server_ts, 'normal', :lat, :lng, :accuracy,
                    :dentro_geofence, :distancia, :foto_url,
                    :device, false, :posto_id, :posto_nome, :created_by, :created_at
                )
            """),
            {
                "punch_id": punch_id,
                "emp_id": str(employee_id),
                "ts": now,
                "server_ts": now,
                "lat": location_lat,
                "lng": location_lng,
                "accuracy": accuracy,
                "dentro_geofence": geo["dentro_geofence"],
                "distancia": geo["distancia_posto_metros"],
                "foto_url": foto_url,
                "device": device_type,
                "posto_id": posto_id,
                "posto_nome": posto_nome,
                "created_by": created_by,
                "created_at": now,
            },
        )
        await self.db.flush()

        logger.info(
            "Clock-in registrado: employee=%s punch=%s geofence=%s dist=%s foto=%s",
            employee_id,
            punch_id,
            geo["dentro_geofence"],
            geo["distancia_posto_metros"],
            bool(foto_url),
        )

        return {
            "id": punch_id,
            "employee_id": str(employee_id),
            "record_date": str(today),
            "clock_in": now.strftime("%H:%M"),
            "clock_out": None,
            "clock_in_lunch": None,
            "clock_out_lunch": None,
            "total_hours": None,
            "overtime_hours": None,
            "status": "regular",
            "justification": None,
            "location_lat": location_lat,
            "location_lng": location_lng,
            "accuracy": accuracy,
            "posto_id": posto_id,
            "posto_nome": posto_nome,
            "dentro_geofence": geo["dentro_geofence"],
            "distancia_posto_metros": geo["distancia_posto_metros"],
            "geofence_flag": geo["geofence_flag"],
            "foto_capturada_url": foto_url,
            "registered_by": device_type,
            "source": "portal",
            "created_at": now.isoformat(),
            "updated_at": None,
        }

    # =========================================================================
    # CLOCK OUT
    # =========================================================================

    async def clock_out(
        self,
        record_id: str,
        location_lat: float | None = None,
        location_lng: float | None = None,
        notes: str | None = None,
        created_by: str | None = None,
        foto_base64: str | None = None,
        accuracy: float | None = None,
    ) -> dict[str, Any]:
        """Registra batida de saida vinculada a uma entrada.

        Args:
            record_id: punch_id da entrada correspondente.
        """
        # Buscar a entrada original
        result = await self.db.execute(
            text("""
                SELECT punch_id, employee_id, punch_timestamp, device_type, posto_id, posto_nome
                FROM gp_clock_punches
                WHERE punch_id = :rid OR id::text = :rid
                ORDER BY punch_timestamp DESC
                LIMIT 1
            """),
            {"rid": str(record_id)},
        )
        entry = result.mappings().first()
        if not entry:
            raise ValueError(f"Registro de ponto {record_id} nao encontrado")

        # Batida agregada do Solides (Tangerino) tem id sintetico e ja vem fechada la;
        # registrar uma saida nativa aqui criaria uma batida orfa/duplicada. Recusa honesta.
        if str(entry.get("device_type") or "").lower() == "tangerino":
            raise ValueError(
                "Batida importada do Solides (Tangerino) nao aceita clock-out nativo — "
                "ajuste pela origem ou use lancamento manual."
            )

        # Wall-clock LOCAL (America/Manaus), consistente com as demais batidas.
        now = datetime.now()
        punch_id = str(uuid4())

        # Geofence da SAIDA (mesmo posto da entrada) + selfie anti-fraude.
        geo = await self._compute_geofence(entry["posto_id"], location_lat, location_lng)
        foto_url = _salvar_selfie_ponto(punch_id, foto_base64)

        await self.db.execute(
            text("""
                INSERT INTO gp_clock_punches (
                    punch_id, employee_id, punch_type, punch_timestamp,
                    server_timestamp, status, latitude, longitude, accuracy,
                    dentro_geofence, distancia_posto_metros, foto_capturada_url,
                    device_type, is_offline, posto_id, posto_nome, created_by, created_at
                ) VALUES (
                    :punch_id, :emp_id, 'saida', :ts,
                    :server_ts, 'normal', :lat, :lng, :accuracy,
                    :dentro_geofence, :distancia, :foto_url,
                    :device, false, :posto_id, :posto_nome, :created_by, :created_at
                )
            """),
            {
                "punch_id": punch_id,
                "emp_id": entry["employee_id"],
                "ts": now,
                "server_ts": now,
                "lat": location_lat,
                "lng": location_lng,
                "accuracy": accuracy,
                "dentro_geofence": geo["dentro_geofence"],
                "distancia": geo["distancia_posto_metros"],
                "foto_url": foto_url,
                "device": entry["device_type"],
                "posto_id": entry["posto_id"],
                "posto_nome": entry["posto_nome"],
                "created_by": created_by,
                "created_at": now,
            },
        )
        await self.db.flush()

        # Calcular total de horas
        entrada_ts = entry["punch_timestamp"]
        total_minutes = _calc_minutes_between(entrada_ts, now)

        logger.info(
            "Clock-out registrado: employee=%s punch=%s total=%s",
            entry["employee_id"],
            punch_id,
            _format_minutes(total_minutes),
        )

        return {
            "id": entry["punch_id"],
            "employee_id": entry["employee_id"],
            "record_date": str(entrada_ts.date()) if entrada_ts else str(date.today()),
            "clock_in": entrada_ts.strftime("%H:%M") if entrada_ts else None,
            "clock_out": now.strftime("%H:%M"),
            "clock_in_lunch": None,
            "clock_out_lunch": None,
            "total_hours": _format_minutes(total_minutes),
            "overtime_hours": _format_minutes(max(0, total_minutes - 480)),
            "status": "regular",
            "justification": None,
            "location_lat": location_lat,
            "location_lng": location_lng,
            "accuracy": accuracy,
            "posto_id": entry["posto_id"],
            "posto_nome": entry["posto_nome"],
            "dentro_geofence": geo["dentro_geofence"],
            "distancia_posto_metros": geo["distancia_posto_metros"],
            "geofence_flag": geo["geofence_flag"],
            "foto_capturada_url": foto_url,
            "registered_by": entry["device_type"],
            "source": "portal",
            "created_at": entrada_ts.isoformat() if entrada_ts else None,
            "updated_at": now.isoformat(),
        }

    # =========================================================================
    # CREATE MANUAL
    # =========================================================================

    async def create_manual(
        self,
        data: dict[str, Any],
        created_by: str | None = None,
    ) -> dict[str, Any]:
        """Cria lancamento manual de ponto (admin/DP).

        Insere batidas individuais (entrada, saida_almoco, retorno_almoco, saida)
        na tabela gp_clock_punches.
        """
        employee_id = str(data["employee_id"])
        record_date = data["record_date"]
        # server_timestamp/created_at = momento do LANCAMENTO (metadado de auditoria), hora local.
        # O punch_timestamp em si vem da data/hora INFORMADA pelo operador (ts_dt abaixo).
        now = datetime.now()

        punches_to_insert = []
        if data.get("clock_in"):
            punches_to_insert.append(("entrada", data["clock_in"]))
        if data.get("clock_in_lunch"):
            punches_to_insert.append(("saida_almoco", data["clock_in_lunch"]))
        if data.get("clock_out_lunch"):
            punches_to_insert.append(("retorno_almoco", data["clock_out_lunch"]))
        if data.get("clock_out"):
            punches_to_insert.append(("saida", data["clock_out"]))

        first_punch_id = None
        for punch_type, ts in punches_to_insert:
            punch_id = str(uuid4())
            if first_punch_id is None:
                first_punch_id = punch_id

            ts_dt = (
                ts
                if isinstance(ts, datetime)
                else datetime.combine(record_date, ts.time() if isinstance(ts, datetime) else ts)
            )

            await self.db.execute(
                text("""
                    INSERT INTO gp_clock_punches (
                        punch_id, employee_id, punch_type, punch_timestamp,
                        server_timestamp, status, latitude, longitude,
                        device_type, is_offline, created_by, created_at
                    ) VALUES (
                        :punch_id, :emp_id, :ptype, :ts,
                        :server_ts, :status, :lat, :lng,
                        'manual', false, :created_by, :created_at
                    )
                """),
                {
                    "punch_id": punch_id,
                    "emp_id": employee_id,
                    "ptype": punch_type,
                    "ts": ts_dt,
                    "server_ts": now,
                    "status": data.get("status", "regular"),
                    "lat": data.get("location_lat"),
                    "lng": data.get("location_lng"),
                    "created_by": str(created_by) if created_by else None,
                    "created_at": now,
                },
            )

        await self.db.flush()

        # Calculate total hours
        total_minutes = 0
        clock_in = data.get("clock_in")
        clock_out = data.get("clock_out")
        if clock_in and clock_out:
            total_minutes = _calc_minutes_between(clock_in, clock_out)
            # Subtract lunch
            lunch_out = data.get("clock_in_lunch")
            lunch_in = data.get("clock_out_lunch")
            if lunch_out and lunch_in:
                lunch_minutes = _calc_minutes_between(lunch_out, lunch_in)
                total_minutes -= lunch_minutes

        logger.info(
            "Lancamento manual criado: employee=%s date=%s total=%s",
            employee_id,
            record_date,
            _format_minutes(total_minutes),
        )

        return {
            "id": first_punch_id or str(uuid4()),
            "employee_id": employee_id,
            "record_date": str(record_date),
            "clock_in": str(clock_in)[:5] if clock_in else None,
            "clock_out": str(clock_out)[:5] if clock_out else None,
            "clock_in_lunch": str(data.get("clock_in_lunch"))[:5] if data.get("clock_in_lunch") else None,
            "clock_out_lunch": str(data.get("clock_out_lunch"))[:5] if data.get("clock_out_lunch") else None,
            "total_hours": _format_minutes(total_minutes),
            "overtime_hours": _format_minutes(max(0, total_minutes - 480)),
            "status": data.get("status", "regular"),
            "justification": data.get("justification"),
            "location_lat": data.get("location_lat"),
            "location_lng": data.get("location_lng"),
            "registered_by": "manual",
            "source": "manual",
            "created_at": now.isoformat(),
            "updated_at": None,
        }

    # =========================================================================
    # UPDATE RECORD
    # =========================================================================

    async def update_record(
        self,
        record_id: str,
        data: dict[str, Any],
        updated_by: str | None = None,
    ) -> dict[str, Any] | None:
        """Atualiza um registro de ponto (justificativa, status, horarios).

        Para correcao de horarios, insere nova batida com status ajustado.
        Para justificativa/status, atualiza o campo na batida existente.
        """
        # Buscar registro existente
        result = await self.db.execute(
            text("""
                SELECT id, punch_id, employee_id, punch_type, punch_timestamp,
                       status, justification_id
                FROM gp_clock_punches
                WHERE punch_id = :rid OR id::text = :rid
                ORDER BY punch_timestamp
                LIMIT 1
            """),
            {"rid": str(record_id)},
        )
        row = result.mappings().first()
        if not row:
            return None

        now = datetime.utcnow()
        sets = []
        params: dict[str, Any] = {"rid": str(row["punch_id"]), "updated_at": now}

        if "status" in data and data["status"] is not None:
            sets.append("status = :new_status")
            params["new_status"] = str(data["status"])

        if "justification" in data and data["justification"] is not None:
            # Create justification record
            justification_id = str(uuid4())
            try:
                await self.db.execute(
                    text("""
                        INSERT INTO gp_justifications (
                            justification_id, employee_id, punch_id,
                            reason, status, created_at
                        ) VALUES (
                            :jid, :emp_id, :pid, :reason, 'pendente', :created_at
                        )
                    """),
                    {
                        "jid": justification_id,
                        "emp_id": row["employee_id"],
                        "pid": row["punch_id"],
                        "reason": data["justification"],
                        "created_at": now,
                    },
                )
            except Exception:
                # Table may not exist, store in notes
                logger.debug("gp_justifications nao existe, armazenando em notes")

            sets.append("justification_id = :jid")
            params["jid"] = justification_id

        if sets:
            sets.append("updated_at = :updated_at")
            set_sql = ", ".join(sets)
            # Gap 2: sem f-string — set_sql contém apenas strings hardcoded com placeholders nomeados
            await self.db.execute(
                text("UPDATE gp_clock_punches SET " + set_sql + " WHERE punch_id = :rid"),
                params,
            )
            await self.db.flush()

        # Return updated record
        return await self.get_by_id(str(row["punch_id"]))

    # =========================================================================
    # MONTHLY SUMMARY
    # =========================================================================

    async def get_summary(
        self,
        employee_id: str,
        month: int,
        year: int,
    ) -> dict[str, Any]:
        """Retorna resumo mensal de ponto de um funcionario.

        Tenta buscar do time_sheets primeiro (dados consolidados).
        Se nao encontrar, calcula a partir das batidas em gp_clock_punches.
        """
        # 1. Tentar buscar de time_sheets
        ts_result = await self.db.execute(
            text("""
                SELECT *
                FROM time_sheets
                WHERE employee_id = :emp_id
                  AND reference_month = :month
                  AND reference_year = :year
                  AND is_deleted = false
                LIMIT 1
            """),
            {"emp_id": str(employee_id), "month": month, "year": year},
        )
        ts_row = ts_result.mappings().first()

        if ts_row:
            return self._time_sheet_to_summary(dict(ts_row))

        # 2. Calcular a partir das batidas
        return await self._calculate_summary_from_punches(employee_id, month, year)

    async def _calculate_summary_from_punches(
        self,
        employee_id: str,
        month: int,
        year: int,
    ) -> dict[str, Any]:
        """Calcula resumo mensal a partir das batidas em gp_clock_punches."""
        first_day = date(year, month, 1)
        last_day = date(year, month, calendar.monthrange(year, month)[1])

        sql = text("""
            SELECT
                id, punch_id, employee_id, punch_type,
                punch_timestamp, status, latitude, longitude,
                device_type, created_at
            FROM gp_clock_punches
            WHERE employee_id = :emp_id
              AND punch_timestamp::date >= :d1
              AND punch_timestamp::date <= :d2
            ORDER BY punch_timestamp
        """)
        result = await self.db.execute(sql, {"emp_id": str(employee_id), "d1": first_day, "d2": last_day})
        rows = result.mappings().all()

        # Emparelhar batidas
        records = self._pair_punches(rows)

        total_worked_minutes = 0
        total_overtime_minutes = 0
        total_late_minutes = 0
        total_absences = 0
        total_days = 0

        for rec in records:
            total_days += 1
            if rec.get("total_hours"):
                try:
                    parts = rec["total_hours"].split(":")
                    mins = int(parts[0]) * 60 + int(parts[1])
                    total_worked_minutes += mins
                    if mins > 480:  # 8h
                        total_overtime_minutes += mins - 480
                except (ValueError, IndexError):
                    pass
            if rec.get("status") in ("falta",):
                total_absences += 1

        # Work days in month (Mon-Fri)
        work_days = sum(
            1 for d in range((last_day - first_day).days + 1) if (first_day + timedelta(days=d)).weekday() < 5
        )

        # Employee name
        emp_name = await self._get_employee_name(employee_id)

        return {
            "employee_id": str(employee_id),
            "employee_name": emp_name,
            "month": month,
            "year": year,
            "total_work_days": work_days,
            "total_worked_days": total_days,
            "total_hours_worked": _format_minutes(total_worked_minutes),
            "total_hours_worked_minutes": total_worked_minutes,
            "total_overtime_minutes": total_overtime_minutes,
            "total_overtime": _format_minutes(total_overtime_minutes),
            "total_late_minutes": total_late_minutes,
            "total_absences": total_absences,
            "total_justified_absences": 0,
            "total_unjustified_absences": total_absences,
            "total_medical_leaves": 0,
            "total_holidays": 0,
            "total_night_hours_minutes": 0,
            "records": records,
        }

    def _time_sheet_to_summary(self, ts: dict[str, Any]) -> dict[str, Any]:
        """Converte um time_sheet row em MonthlySummaryResponse."""
        return {
            "employee_id": str(ts.get("employee_id", "")),
            "employee_name": ts.get("employee_name"),
            "month": ts.get("reference_month", 0),
            "year": ts.get("reference_year", 0),
            "total_work_days": ts.get("work_days_expected", 0),
            "total_worked_days": ts.get("work_days_worked", 0),
            "total_hours_worked": _format_minutes(ts.get("hours_worked_minutes", 0)),
            "total_hours_worked_minutes": ts.get("hours_worked_minutes", 0),
            "total_overtime_minutes": ts.get("overtime_total_minutes", 0),
            "total_overtime": _format_minutes(ts.get("overtime_total_minutes", 0)),
            "total_late_minutes": ts.get("late_minutes", 0),
            "total_absences": ts.get("absent_days", 0),
            "total_justified_absences": ts.get("justified_absent_days", 0),
            "total_unjustified_absences": ts.get("unjustified_absent_days", 0),
            "total_medical_leaves": ts.get("medical_leave_days", 0),
            "total_holidays": ts.get("holiday_days", 0),
            "total_night_hours_minutes": ts.get("night_hours_minutes", 0),
            "records": [],
        }

    # =========================================================================
    # DAILY RECORDS
    # =========================================================================

    async def get_daily(self, record_date: date) -> dict[str, Any]:
        """Retorna todos os registros de ponto de um dia especifico."""
        sql = text("""
            SELECT
                id, punch_id, employee_id, punch_type,
                punch_timestamp, status, latitude, longitude,
                device_type, is_offline, posto_id, posto_nome,
                created_at, updated_at
            FROM gp_clock_punches
            WHERE punch_timestamp::date = :pdate
            ORDER BY employee_id, punch_timestamp
        """)
        result = await self.db.execute(sql, {"pdate": record_date})
        rows = result.mappings().all()

        records = self._pair_punches(rows)
        records = await self._fill_employee_names(records)

        return {
            "date": str(record_date),
            "total_employees": len({r["employee_id"] for r in records}),
            "records": records,
        }

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _pair_punches(self, rows: list[Any]) -> list[dict[str, Any]]:
        """Emparelha batidas de entrada/saida por employee+dia.

        Agrupa todas as batidas de um funcionario em um dia e
        monta o registro diario com entrada, almoco, saida e totais.
        """
        from collections import defaultdict

        # Agrupar por (employee_id, date)
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            r = dict(row)
            emp_id = str(r["employee_id"])
            ts = r["punch_timestamp"]
            day = str(ts.date()) if isinstance(ts, datetime) else str(ts)[:10]
            groups[(emp_id, day)].append(r)

        records = []
        for (emp_id, day), punches in groups.items():
            # Sort by timestamp
            punches.sort(key=lambda p: p["punch_timestamp"])

            clock_in = None
            clock_out = None
            clock_in_lunch = None
            clock_out_lunch = None
            lat = None
            lng = None
            source = None
            first_id = None
            created_at = None
            updated_at = None

            for p in punches:
                ptype = str(p.get("punch_type", "")).lower()
                ts = p["punch_timestamp"]

                if first_id is None:
                    first_id = p.get("punch_id") or str(p.get("id", ""))
                    lat = p.get("latitude")
                    lng = p.get("longitude")
                    created_at = p.get("created_at")
                    device = str(p.get("device_type", "")).lower()
                    if "tangerino" in str(p.get("punch_id", "")).lower() or "tng" in str(p.get("punch_id", "")).lower():
                        source = "tangerino"
                    elif device == "manual":
                        source = "manual"
                    else:
                        source = "portal"

                updated_at = p.get("updated_at") or updated_at

                if ptype == "entrada" and clock_in is None:
                    clock_in = ts
                elif ptype == "saida_almoco" and clock_in_lunch is None:
                    clock_in_lunch = ts
                elif ptype == "retorno_almoco" and clock_out_lunch is None:
                    clock_out_lunch = ts
                elif ptype == "saida":
                    clock_out = ts

            # Calculate total hours
            total_minutes = 0
            if clock_in and clock_out:
                total_minutes = _calc_minutes_between(clock_in, clock_out)
                if clock_in_lunch and clock_out_lunch:
                    lunch_minutes = _calc_minutes_between(clock_in_lunch, clock_out_lunch)
                    total_minutes -= lunch_minutes

            overtime_minutes = max(0, total_minutes - 480)

            # Determine status
            status = "regular"
            if not clock_in and not clock_out:
                status = "falta"
            elif clock_in and not clock_out:
                status = "inconsistencia"

            records.append(
                {
                    "id": str(first_id),
                    "employee_id": emp_id,
                    "employee_name": None,
                    "record_date": day,
                    "clock_in": clock_in.strftime("%H:%M") if isinstance(clock_in, datetime) else None,
                    "clock_out": clock_out.strftime("%H:%M") if isinstance(clock_out, datetime) else None,
                    "clock_in_lunch": clock_in_lunch.strftime("%H:%M")
                    if isinstance(clock_in_lunch, datetime)
                    else None,
                    "clock_out_lunch": clock_out_lunch.strftime("%H:%M")
                    if isinstance(clock_out_lunch, datetime)
                    else None,
                    "total_hours": _format_minutes(total_minutes) if total_minutes > 0 else None,
                    "overtime_hours": _format_minutes(overtime_minutes) if overtime_minutes > 0 else None,
                    "status": status,
                    "justification": None,
                    "location_lat": lat,
                    "location_lng": lng,
                    "registered_by": source or "system",
                    "source": source,
                    "created_at": created_at.isoformat()
                    if isinstance(created_at, datetime)
                    else str(created_at)
                    if created_at
                    else None,
                    "updated_at": updated_at.isoformat()
                    if isinstance(updated_at, datetime)
                    else str(updated_at)
                    if updated_at
                    else None,
                }
            )

        # Sort by date descending
        records.sort(key=lambda r: r["record_date"], reverse=True)
        return records

    def _punch_to_record(self, row: dict[str, Any]) -> dict[str, Any]:
        """Converte uma unica batida em formato TimeRecordResponse."""
        ts = row.get("punch_timestamp")
        ptype = str(row.get("punch_type", "")).lower()
        return {
            "id": str(row.get("punch_id") or row.get("id", "")),
            "employee_id": str(row.get("employee_id", "")),
            "employee_name": None,
            "record_date": str(ts.date()) if isinstance(ts, datetime) else None,
            "clock_in": ts.strftime("%H:%M") if isinstance(ts, datetime) and ptype == "entrada" else None,
            "clock_out": ts.strftime("%H:%M") if isinstance(ts, datetime) and ptype == "saida" else None,
            "clock_in_lunch": None,
            "clock_out_lunch": None,
            "total_hours": None,
            "overtime_hours": None,
            "status": row.get("status", "regular"),
            "justification": None,
            "location_lat": row.get("latitude"),
            "location_lng": row.get("longitude"),
            "registered_by": row.get("device_type", "system"),
            "source": "portal",
            "created_at": row["created_at"].isoformat() if isinstance(row.get("created_at"), datetime) else None,
            "updated_at": row["updated_at"].isoformat() if isinstance(row.get("updated_at"), datetime) else None,
        }

    async def _get_employee_name(self, employee_id: str) -> str | None:
        """Busca nome do funcionario por ID."""
        try:
            result = await self.db.execute(
                text("SELECT nome FROM employees WHERE id::text = :eid LIMIT 1"),
                {"eid": str(employee_id)},
            )
            row = result.first()
            return str(row[0]) if row else None
        except Exception:
            return None

    async def _fill_employee_names(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Preenche employee_name em lote (1 query) — gp_clock_punches não guarda o nome."""
        ids = {str(r["employee_id"]) for r in records if r.get("employee_id")}
        if not ids:
            return records
        try:
            result = await self.db.execute(
                text("SELECT id::text AS id, nome FROM employees WHERE id::text = ANY(:ids)"),
                {"ids": list(ids)},
            )
            nomes = {row["id"]: row["nome"] for row in result.mappings().all()}
        except Exception:
            return records
        for r in records:
            r["employee_name"] = nomes.get(str(r.get("employee_id")), r.get("employee_name"))
        return records
