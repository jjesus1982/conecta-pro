"""Service de dashboard e inconsistencias do Ponto — wiring real com DB e CCT."""

import logging
import os
from datetime import date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# A empresa opera em Manaus (UTC-4) e as batidas são gravadas em horário local.
# date.today() usa o fuso do servidor (UTC) e, à noite, "vira o dia" antes de Manaus,
# zerando presença/registros de hoje. Por isso o "hoje" do ponto é sempre Manaus.
TZ_MANAUS = ZoneInfo("America/Manaus")


def _hoje_manaus() -> date:
    return datetime.now(TZ_MANAUS).date()


# Constantes CCT 2026 SINDECOMPRESTS
HORA_NOTURNA_MINUTOS = 52.5
ADICIONAL_NOTURNO_PCT = 0.20
HORA_EXTRA_50_PCT = 0.50
HORA_EXTRA_100_PCT = 1.00
INTRAJORNADA_MINIMA_HORAS = 1.0
JORNADA_MAXIMA_12X36_HORAS = 12.0
BANCO_HORAS_PRAZO_MESES = 6


def get_dashboard(db: Session) -> dict[str, Any]:
    """Retorna dados do dashboard de ponto com dados reais do banco."""
    hoje = _hoje_manaus().isoformat()

    # Total colaboradores ativos
    total = db.execute(text("SELECT COUNT(*) FROM employees WHERE status='ativo'")).scalar() or 0

    # Sem escala
    sem_escala = (
        db.execute(
            text("SELECT COUNT(*) FROM employees WHERE status='ativo' AND (escala_padrao IS NULL OR escala_padrao='')")
        ).scalar()
        or 0
    )

    # Presentes hoje (batida de entrada hoje)
    presentes = (
        db.execute(
            text(
                "SELECT COUNT(DISTINCT employee_id) FROM gp_clock_punches "
                "WHERE punch_type='entrada' AND DATE(punch_timestamp)=:hoje"
            ),
            {"hoje": hoje},
        ).scalar()
        or 0
    )

    # Pontos em aberto (entrada sem saida hoje)
    em_aberto = (
        db.execute(
            text(
                "SELECT COUNT(DISTINCT e.employee_id) FROM gp_clock_punches e "
                "WHERE e.punch_type='entrada' AND DATE(e.punch_timestamp)=:hoje "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM gp_clock_punches s "
                "  WHERE s.employee_id=e.employee_id AND s.punch_type='saida' "
                "  AND DATE(s.punch_timestamp)=:hoje"
                ")"
            ),
            {"hoje": hoje},
        ).scalar()
        or 0
    )

    # Afastados
    afastados = (
        db.execute(text("SELECT COUNT(*) FROM employees WHERE status IN ('afastado','ferias','licenca')")).scalar() or 0
    )

    # Distribuicao por escala
    escalas_raw = db.execute(
        text(
            "SELECT COALESCE(escala_padrao, 'sem_escala') as escala, COUNT(*) as qtd "
            "FROM employees WHERE status='ativo' "
            "GROUP BY escala_padrao ORDER BY qtd DESC"
        )
    ).fetchall()
    por_escala = {row[0]: row[1] for row in escalas_raw}

    # Ultima sync solides — a sync 24/7 (funcionários incremental + batidas) grava em
    # solides_sync_log; a tabela solides_employees.last_synced_at ficou congelada (jan/18).
    # Usa o log real de sync e cai pro valor antigo só se o log estiver vazio.
    ultima_sync = db.execute(
        text(
            "SELECT GREATEST("
            "  (SELECT MAX(started_at) FROM solides_sync_log WHERE status='completed'),"
            "  (SELECT MAX(last_synced_at) FROM solides_employees)"
            ")"
        )
    ).scalar()

    return {
        "total_colaboradores": total,
        "presentes_hoje": presentes,
        "ausentes_hoje": max(0, total - presentes - afastados),
        "afastados": afastados,
        "inconsistencias_periodo": _contar_inconsistencias_mes(db),
        "sem_escala": sem_escala,
        "pontos_em_aberto": em_aberto,
        "banco_horas": {"total_credito": 0.0, "total_debito": 0.0, "saldo_medio": 0.0},
        "por_escala": por_escala,
        "ultima_sync_solides": ultima_sync.isoformat() if ultima_sync else None,
    }


def get_inconsistencias(
    db: Session,
    periodo_inicio: str | None = None,
    periodo_fim: str | None = None,
) -> dict[str, Any]:
    """Analisa inconsistencias do periodo usando regras CCT."""
    hoje = date.today()
    inicio = periodo_inicio or hoje.replace(day=1).isoformat()
    fim = periodo_fim or hoje.isoformat()

    items: list[dict[str, Any]] = []

    # 1. Colaboradores sem escala
    sem_escala = db.execute(
        text(
            "SELECT id, nome, cargo FROM employees WHERE status='ativo' AND (escala_padrao IS NULL OR escala_padrao='')"
        )
    ).fetchall()
    for row in sem_escala:
        items.append(
            {
                "employee_id": str(row[0]),
                "employee_nome": row[1],
                "data": inicio,
                "tipo": "escala_nao_cadastrada",
                "descricao": f"Colaborador {row[1]} sem escala definida",
                "gravidade": "alta",
                "resolvida": False,
            }
        )

    # 2. Entradas sem saida (ponto em aberto)
    abertos = db.execute(
        text(
            "SELECT e.employee_id, DATE(e.punch_timestamp) as dia "
            "FROM gp_clock_punches e "
            "WHERE e.punch_type='entrada' "
            "AND DATE(e.punch_timestamp) BETWEEN :ini AND :fim "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM gp_clock_punches s "
            "  WHERE s.employee_id=e.employee_id AND s.punch_type='saida' "
            "  AND DATE(s.punch_timestamp)=DATE(e.punch_timestamp)"
            ") ORDER BY dia DESC"
        ),
        {"ini": inicio, "fim": fim},
    ).fetchall()
    for row in abertos:
        items.append(
            {
                "employee_id": str(row[0]),
                "employee_nome": f"Emp#{row[0]}",
                "data": str(row[1]),
                "tipo": "ponto_em_aberto",
                "descricao": f"Entrada registrada sem saida em {row[1]}",
                "gravidade": "alta",
                "resolvida": False,
            }
        )

    # 3. Jornadas excedidas (>12h para 12x36)
    jornadas = db.execute(
        text(
            "SELECT ent.employee_id, DATE(ent.punch_timestamp) as dia, "
            "  EXTRACT(EPOCH FROM (sai.punch_timestamp - ent.punch_timestamp))/3600 as horas "
            "FROM gp_clock_punches ent "
            "JOIN gp_clock_punches sai ON ent.employee_id=sai.employee_id "
            "  AND sai.punch_type='saida' "
            "  AND DATE(sai.punch_timestamp)=DATE(ent.punch_timestamp) "
            "WHERE ent.punch_type='entrada' "
            "AND DATE(ent.punch_timestamp) BETWEEN :ini AND :fim "
            "AND EXTRACT(EPOCH FROM (sai.punch_timestamp - ent.punch_timestamp))/3600 > :max_h "
            "ORDER BY dia DESC"
        ),
        {"ini": inicio, "fim": fim, "max_h": JORNADA_MAXIMA_12X36_HORAS},
    ).fetchall()
    for row in jornadas:
        items.append(
            {
                "employee_id": str(row[0]),
                "employee_nome": f"Emp#{row[0]}",
                "data": str(row[1]),
                "tipo": "jornada_excedida",
                "descricao": f"Jornada de {row[2]:.1f}h excede limite 12h CCT (12x36)",
                "gravidade": "alta",
                "resolvida": False,
            }
        )

    # 4. Intrajornada nao concedida (<1h de intervalo)
    intervalos = db.execute(
        text(
            "SELECT sa.employee_id, DATE(sa.punch_timestamp) as dia, "
            "  EXTRACT(EPOCH FROM (ret.punch_timestamp - sa.punch_timestamp))/60 as min_intervalo "
            "FROM gp_clock_punches sa "
            "JOIN gp_clock_punches ret ON sa.employee_id=ret.employee_id "
            "  AND ret.punch_type='retorno_almoco' "
            "  AND DATE(ret.punch_timestamp)=DATE(sa.punch_timestamp) "
            "WHERE sa.punch_type='saida_almoco' "
            "AND DATE(sa.punch_timestamp) BETWEEN :ini AND :fim "
            "AND EXTRACT(EPOCH FROM (ret.punch_timestamp - sa.punch_timestamp))/60 < :min_m "
            "ORDER BY dia DESC"
        ),
        {"ini": inicio, "fim": fim, "min_m": INTRAJORNADA_MINIMA_HORAS * 60},
    ).fetchall()
    for row in intervalos:
        items.append(
            {
                "employee_id": str(row[0]),
                "employee_nome": f"Emp#{row[0]}",
                "data": str(row[1]),
                "tipo": "intrajornada_nao_concedida",
                "descricao": f"Intervalo de {row[2]:.0f}min abaixo do minimo 60min CCT",
                "gravidade": "media",
                "resolvida": False,
            }
        )

    # Sumarizar por tipo e gravidade
    por_tipo: dict[str, int] = {}
    por_gravidade: dict[str, int] = {}
    for item in items:
        por_tipo[item["tipo"]] = por_tipo.get(item["tipo"], 0) + 1
        por_gravidade[item["gravidade"]] = por_gravidade.get(item["gravidade"], 0) + 1

    return {
        "periodo_inicio": inicio,
        "periodo_fim": fim,
        "total_inconsistencias": len(items),
        "por_tipo": por_tipo,
        "por_gravidade": por_gravidade,
        "items": items,
    }


def get_banco_horas(db: Session, employee_id: str) -> dict[str, Any]:
    """Retorna saldo de banco de horas do colaborador."""
    emp = db.execute(text("SELECT id, nome FROM employees WHERE CAST(id AS TEXT)=:eid"), {"eid": employee_id}).first()

    if not emp:
        return {"error": "Colaborador nao encontrado"}

    # Calcular horas extras do mes atual
    hoje = date.today()
    inicio_mes = hoje.replace(day=1).isoformat()

    he = (
        db.execute(
            text(
                "SELECT COALESCE(SUM("
                "  CASE WHEN EXTRACT(EPOCH FROM (sai.punch_timestamp - ent.punch_timestamp))/3600 > 12 "
                "  THEN EXTRACT(EPOCH FROM (sai.punch_timestamp - ent.punch_timestamp))/3600 - 12 "
                "  ELSE 0 END"
                "), 0) as total_he "
                "FROM gp_clock_punches ent "
                "JOIN gp_clock_punches sai ON ent.employee_id=sai.employee_id "
                "  AND sai.punch_type='saida' "
                "  AND DATE(sai.punch_timestamp)=DATE(ent.punch_timestamp) "
                "WHERE ent.punch_type='entrada' "
                "AND CAST(ent.employee_id AS TEXT)=:eid "
                "AND DATE(ent.punch_timestamp) >= :ini"
            ),
            {"eid": employee_id, "ini": inicio_mes},
        ).scalar()
        or 0.0
    )

    # Prazo CCT: 6 meses para compensacao
    vencimento = (hoje + timedelta(days=BANCO_HORAS_PRAZO_MESES * 30)).isoformat()

    return {
        "employee_id": employee_id,
        "employee_nome": emp[1],
        "saldo_horas": float(he),
        "creditos": float(he),
        "debitos": 0.0,
        "vencimento_proximo": vencimento,
        "detalhes": [],
    }


def get_colaboradores_sem_escala(db: Session) -> list[dict[str, Any]]:
    """Retorna lista de colaboradores sem escala cadastrada."""
    rows = db.execute(
        text(
            "SELECT id, nome, cargo, data_admissao FROM employees "
            "WHERE status='ativo' AND (escala_padrao IS NULL OR escala_padrao='') "
            "ORDER BY nome"
        )
    ).fetchall()

    return [
        {
            "employee_id": str(row[0]),
            "nome": row[1],
            "cargo": row[2],
            "data_admissao": row[3].isoformat() if row[3] else None,
        }
        for row in rows
    ]


def _check_justifications_columns(db: Session) -> set[str]:
    """Retorna o conjunto de colunas existentes em gp_justifications."""
    try:
        rows = db.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name='gp_justifications'")
        ).fetchall()
        return {row[0] for row in rows}
    except Exception:
        return set()


def _fetch_solides_entities(token: str, entity_path: str, start_date: str, end_date: str) -> list[dict]:
    """Busca entidades do Tangerino API de forma sincrona via httpx."""
    base_url = "https://employer.tangerino.com.br"
    headers = {"Authorization": f"Basic {token}", "Accept": "application/json"}
    params = {"startDate": start_date, "endDate": end_date, "page": 0, "size": 100}

    try:
        resp = httpx.get(f"{base_url}{entity_path}", headers=headers, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("content", data.get("data", []))
        return []
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            # Endpoint descontinuado ou plano sem modulo — nao e erro, apenas sem dados
            logger.warning(
                "Tangerino API endpoint indisponivel (404) para %s — descontinuado ou fora do plano. "
                "Ausencias/ocorrencias nao importadas neste ciclo.",
                entity_path,
            )
            return []
        logger.warning("Tangerino API HTTP error %s for %s: %s", exc.response.status_code, entity_path, exc)
        raise
    except Exception as exc:
        logger.warning("Tangerino API error for %s: %s", entity_path, exc)
        raise


def _map_absence_type(type_name: str | None) -> tuple[str, str]:
    """Mapeia tipo de ausencia Solides para (justification_type, category)."""
    if not type_name:
        return ("falta", "outro")
    t = type_name.lower()
    if any(k in t for k in ("doenca", "medico", "saude", "hospital", "cid", "atestado")):
        return ("falta", "saude")
    if any(k in t for k in ("familia", "filho", "luto", "natalidade", "paternidade", "maternidade")):
        return ("falta", "familiar")
    if any(k in t for k in ("parcial", "atraso", "hora")):
        return ("atraso", "outro")
    return ("falta", "outro")


def sync_solides_ponto(db: Session, periodo_inicio: str | None, periodo_fim: str | None) -> dict[str, Any]:
    """Sincroniza dados de ponto do Solides Tangerino para o sistema."""
    hoje = date.today()
    inicio = periodo_inicio or hoje.replace(day=1).isoformat()
    fim = periodo_fim or hoje.isoformat()

    token = os.getenv("SOLIDES_API_TOKEN")

    if not token:
        logger.warning(
            "SOLIDES_API_TOKEN nao configurado — sync_solides_ponto retornando stub. "
            "Configure a variavel de ambiente para ativar a sincronizacao real."
        )
        incons = _contar_inconsistencias_mes(db)
        return {
            "success": True,
            "message": f"Sincronizacao simulada (token nao configurado) para periodo {inicio} a {fim}",
            "total_importados": 0,
            "total_atualizados": 0,
            "total_inconsistencias": incons,
            "erros": ["SOLIDES_API_TOKEN nao configurado"],
        }

    erros: list[str] = []
    total_importados = 0
    total_atualizados = 0

    # Verificar colunas disponiveis em gp_justifications
    cols = _check_justifications_columns(db)
    has_source = "source" in cols
    has_source_id = "source_id" in cols

    # ------------------------------------------------------------------ #
    # 1. Importar AUSENCIAS                                                #
    # ------------------------------------------------------------------ #
    try:
        absences = _fetch_solides_entities(token, "/absence/find-all", inicio, fim)
        logger.info("Tangerino: %d ausencias recebidas para o periodo %s a %s", len(absences), inicio, fim)

        for absence in absences:
            try:
                solides_id = str(absence.get("id", ""))
                source_id_val = f"solides_{solides_id}"

                # Dedup: checar se ja existe
                if has_source_id:
                    exists = db.execute(
                        text("SELECT 1 FROM gp_justifications WHERE source_id = :sid LIMIT 1"),
                        {"sid": source_id_val},
                    ).scalar()
                else:
                    # Fallback: checar pelo campo reason com prefixo
                    exists = db.execute(
                        text("SELECT 1 FROM gp_justifications WHERE reason LIKE :pat LIMIT 1"),
                        {"pat": f"%[solides_{solides_id}]%"},
                    ).scalar()

                if exists:
                    continue

                # Resolver employee local via solides_employees
                solides_emp_id = str(absence.get("employeeId", absence.get("employee_id", "")))
                local_emp = None
                if solides_emp_id:
                    local_emp = db.execute(
                        text("SELECT employee_id FROM solides_employees WHERE solides_id = :sid"),
                        {"sid": solides_emp_id},
                    ).scalar()

                if not local_emp:
                    logger.debug(
                        "Ausencia solides_id=%s: employee solides_id=%s nao mapeado localmente",
                        solides_id,
                        solides_emp_id,
                    )
                    continue

                type_name = absence.get("absenceTypeName") or absence.get("type") or absence.get("typeName")
                jtype, category = _map_absence_type(type_name)
                reason_text = absence.get("description") or type_name or "Ausencia Solides"
                if not has_source_id:
                    reason_text = f"{reason_text} [solides_{solides_id}]"

                now = datetime.utcnow()
                new_id = str(uuid4())

                if has_source and has_source_id:
                    db.execute(
                        text(
                            "INSERT INTO gp_justifications "
                            "(justification_id, employee_id, justification_type, reason, category, "
                            " status, source, source_id, created_at) "
                            "VALUES (:jid, :eid, :jtype, :reason, :cat, 'aprovada', :src, :sid, :now)"
                        ),
                        {
                            "jid": new_id,
                            "eid": local_emp,
                            "jtype": jtype,
                            "reason": reason_text,
                            "cat": category,
                            "src": "solides",
                            "sid": source_id_val,
                            "now": now,
                        },
                    )
                elif has_source_id:
                    db.execute(
                        text(
                            "INSERT INTO gp_justifications "
                            "(justification_id, employee_id, justification_type, reason, category, "
                            " status, source_id, created_at) "
                            "VALUES (:jid, :eid, :jtype, :reason, :cat, 'aprovada', :sid, :now)"
                        ),
                        {
                            "jid": new_id,
                            "eid": local_emp,
                            "jtype": jtype,
                            "reason": reason_text,
                            "cat": category,
                            "sid": source_id_val,
                            "now": now,
                        },
                    )
                else:
                    db.execute(
                        text(
                            "INSERT INTO gp_justifications "
                            "(justification_id, employee_id, justification_type, reason, category, "
                            " status, created_at) "
                            "VALUES (:jid, :eid, :jtype, :reason, :cat, 'aprovada', :now)"
                        ),
                        {
                            "jid": new_id,
                            "eid": local_emp,
                            "jtype": jtype,
                            "reason": reason_text,
                            "cat": category,
                            "now": now,
                        },
                    )

                total_importados += 1

            except Exception as exc:
                logger.warning("Erro ao importar ausencia solides_id=%s: %s", absence.get("id"), exc)
                erros.append(f"Ausencia {absence.get('id')}: {exc}")

    except Exception as exc:
        msg = f"Erro ao buscar ausencias do Tangerino: {exc}"
        logger.error(msg)
        erros.append(msg)

    # ------------------------------------------------------------------ #
    # 2. Importar OCORRENCIAS                                              #
    # ------------------------------------------------------------------ #
    try:
        occurrences = _fetch_solides_entities(token, "/occurrence/find-all", inicio, fim)
        logger.info("Tangerino: %d ocorrencias recebidas para o periodo %s a %s", len(occurrences), inicio, fim)

        for occ in occurrences:
            try:
                solides_id = str(occ.get("id", ""))
                source_id_val = f"solides_occ_{solides_id}"

                if has_source_id:
                    exists = db.execute(
                        text("SELECT 1 FROM gp_justifications WHERE source_id = :sid LIMIT 1"),
                        {"sid": source_id_val},
                    ).scalar()
                else:
                    exists = db.execute(
                        text("SELECT 1 FROM gp_justifications WHERE reason LIKE :pat LIMIT 1"),
                        {"pat": f"%[solides_occ_{solides_id}]%"},
                    ).scalar()

                if exists:
                    continue

                solides_emp_id = str(occ.get("employeeId", occ.get("employee_id", "")))
                local_emp = None
                if solides_emp_id:
                    local_emp = db.execute(
                        text("SELECT employee_id FROM solides_employees WHERE solides_id = :sid"),
                        {"sid": solides_emp_id},
                    ).scalar()

                if not local_emp:
                    logger.debug(
                        "Ocorrencia solides_id=%s: employee solides_id=%s nao mapeado localmente",
                        solides_id,
                        solides_emp_id,
                    )
                    continue

                type_name = occ.get("occurrenceTypeName") or occ.get("type") or occ.get("typeName")
                reason_text = occ.get("description") or type_name or "Ocorrencia Solides"
                if not has_source_id:
                    reason_text = f"{reason_text} [solides_occ_{solides_id}]"

                now = datetime.utcnow()
                new_id = str(uuid4())

                if has_source and has_source_id:
                    db.execute(
                        text(
                            "INSERT INTO gp_justifications "
                            "(justification_id, employee_id, justification_type, reason, category, "
                            " status, source, source_id, created_at) "
                            "VALUES (:jid, :eid, 'atraso', :reason, 'outro', 'aprovada', :src, :sid, :now)"
                        ),
                        {
                            "jid": new_id,
                            "eid": local_emp,
                            "reason": reason_text,
                            "src": "solides",
                            "sid": source_id_val,
                            "now": now,
                        },
                    )
                elif has_source_id:
                    db.execute(
                        text(
                            "INSERT INTO gp_justifications "
                            "(justification_id, employee_id, justification_type, reason, category, "
                            " status, source_id, created_at) "
                            "VALUES (:jid, :eid, 'atraso', :reason, 'outro', 'aprovada', :sid, :now)"
                        ),
                        {
                            "jid": new_id,
                            "eid": local_emp,
                            "reason": reason_text,
                            "sid": source_id_val,
                            "now": now,
                        },
                    )
                else:
                    db.execute(
                        text(
                            "INSERT INTO gp_justifications "
                            "(justification_id, employee_id, justification_type, reason, category, "
                            " status, created_at) "
                            "VALUES (:jid, :eid, 'atraso', :reason, 'outro', 'aprovada', :now)"
                        ),
                        {
                            "jid": new_id,
                            "eid": local_emp,
                            "reason": reason_text,
                            "now": now,
                        },
                    )

                total_importados += 1

            except Exception as exc:
                logger.warning("Erro ao importar ocorrencia solides_id=%s: %s", occ.get("id"), exc)
                erros.append(f"Ocorrencia {occ.get('id')}: {exc}")

    except Exception as exc:
        msg = f"Erro ao buscar ocorrencias do Tangerino: {exc}"
        logger.error(msg)
        erros.append(msg)

    # Commit dos registros importados
    if total_importados > 0:
        try:
            db.commit()
        except Exception as exc:
            logger.error("Erro ao commitar registros importados do Solides: %s", exc)
            erros.append(f"Commit falhou: {exc}")
            db.rollback()
            total_importados = 0

    # Rodar engine de inconsistencias apos sync
    incons = _contar_inconsistencias_mes(db)

    return {
        "success": True,
        "message": f"Sincronizacao concluida para periodo {inicio} a {fim}",
        "total_importados": total_importados,
        "total_atualizados": total_atualizados,
        "total_inconsistencias": incons,
        "erros": erros,
    }


def sync_escalas_from_solides(db: Session) -> dict[str, Any]:
    """Sincroniza escalas de trabalho do Sólides para employees.escala_padrao.

    Busca work_schedules do Tangerino e atualiza employees via solides_id.
    """
    api_token = os.getenv("SOLIDES_API_TOKEN")
    if not api_token:
        logger.warning("SOLIDES_API_TOKEN não configurado — sync_escalas ignorado")
        return {"success": True, "total_atualizados": 0, "erros": []}

    base_url = "https://employer.tangerino.com.br"
    headers = {"Authorization": f"Basic {api_token}", "Accept": "application/json"}
    atualizados = 0
    erros: list[dict[str, Any]] = []

    try:
        # Buscar todos os colaboradores com suas escalas
        resp = httpx.get(
            f"{base_url}/employee/find-all",
            headers=headers,
            params={"page": 0, "size": 200},
            timeout=30.0,
        )
        if resp.status_code != 200:
            logger.warning("Sólides /employee/find-all retornou %d", resp.status_code)
            return {
                "success": False,
                "total_atualizados": 0,
                "erros": [{"error": f"HTTP {resp.status_code}"}],
            }

        data = resp.json()
        employees = data.get("content", data) if isinstance(data, dict) else data

        for emp in employees:
            solides_id = str(emp.get("id", ""))
            if not solides_id:
                continue

            # Pegar escala do colaborador — campo workSchedule ou workScaleType
            work_schedule = (
                emp.get("workScaleType") or emp.get("workSchedule") or emp.get("escala") or emp.get("scheduleType")
            )

            if not work_schedule:
                # Tentar buscar via work-schedule separado
                ws = emp.get("workSchedule") or {}
                work_schedule = ws.get("name") or ws.get("type") if isinstance(ws, dict) else None

            if not work_schedule:
                continue

            # Mapear tipo de escala Sólides para formato Conecta PRO
            escala_map = {
                "12X36": "12x36",
                "12x36": "12x36",
                "DOZE_TRINTA_SEIS": "12x36",
                "5X2": "5x2",
                "5x2": "5x2",
                "CINCO_DOIS": "5x2",
                "6X1": "6x1",
                "6x1": "6x1",
                "SEIS_UM": "6x1",
                "PLANTAO": "plantao",
                "ESCALA_LIVRE": "livre",
            }
            escala_padrao = escala_map.get(str(work_schedule).upper(), str(work_schedule).lower()[:20])

            try:
                r = db.execute(
                    text(
                        "UPDATE employees SET escala_padrao = :escala "
                        "WHERE solides_id = :sid "
                        "AND (escala_padrao IS NULL OR escala_padrao != :escala)"
                    ),
                    {"escala": escala_padrao, "sid": solides_id},
                )
                if r.rowcount > 0:
                    atualizados += 1
            except Exception as e:
                erros.append({"solides_id": solides_id, "error": str(e)[:100]})

        if atualizados > 0:
            db.commit()

    except Exception as e:
        logger.warning("Erro ao sincronizar escalas do Sólides: %s", e)
        erros.append({"error": str(e)[:200]})

    logger.info("[Sólides] Escalas sincronizadas: %d atualizadas, %d erros", atualizados, len(erros))
    return {
        "success": True,
        "total_atualizados": atualizados,
        "erros": erros,
    }


def registrar_ajuste(db: Session, ajuste: dict[str, Any]) -> dict[str, Any]:
    """Registra ajuste manual de ponto pelo DP."""
    from uuid import uuid4

    punch_id = str(uuid4())
    now = datetime.utcnow()

    # employee_id na gp_clock_punches eh integer — usar hash do UUID
    emp_int = abs(hash(ajuste["employee_id"])) % 2147483647

    db.execute(
        text(
            "INSERT INTO gp_clock_punches "
            "(punch_id, employee_id, punch_type, punch_timestamp, server_timestamp, "
            " status, device_type, is_offline, sync_attempts, created_at, created_by) "
            "VALUES (:pid, :eid, :pt, CAST(:ts AS TIMESTAMP), :now, "
            "'normal', 'ajuste_dp', false, 0, :now, :por)"
        ),
        {
            "pid": punch_id,
            "eid": emp_int,
            "pt": ajuste["punch_type"],
            "ts": ajuste["timestamp"],
            "now": now,
            "por": ajuste["ajustado_por"],
        },
    )
    db.commit()

    logger.info(
        "Ajuste de ponto registrado: punch_id=%s employee=%s motivo=%s",
        punch_id,
        ajuste["employee_id"],
        ajuste["motivo"],
    )

    return {
        "success": True,
        "punch_id": punch_id,
        "message": f"Ajuste registrado para {ajuste['data']}",
    }


def _contar_inconsistencias_mes(db: Session) -> int:
    """Conta inconsistencias do mes corrente."""
    hoje = date.today()
    inicio = hoje.replace(day=1).isoformat()
    fim = hoje.isoformat()

    # Sem escala
    sem_escala = (
        db.execute(
            text("SELECT COUNT(*) FROM employees WHERE status='ativo' AND (escala_padrao IS NULL OR escala_padrao='')")
        ).scalar()
        or 0
    )

    # Pontos em aberto
    abertos = (
        db.execute(
            text(
                "SELECT COUNT(DISTINCT e.employee_id) FROM gp_clock_punches e "
                "WHERE e.punch_type='entrada' "
                "AND DATE(e.punch_timestamp) BETWEEN :ini AND :fim "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM gp_clock_punches s "
                "  WHERE s.employee_id=e.employee_id AND s.punch_type='saida' "
                "  AND DATE(s.punch_timestamp)=DATE(e.punch_timestamp))"
            ),
            {"ini": inicio, "fim": fim},
        ).scalar()
        or 0
    )

    return sem_escala + abertos
