"""
Celery Tasks para sincronização Sólides.
Sprint 33: Integration Framework

Tasks agendadas para sincronização automática e health checks.
"""

import asyncio
import logging
import os
from datetime import datetime
from uuid import UUID, uuid4

from celery import shared_task

logger = logging.getLogger(__name__)


# ==================== SYNC LOG HELPERS ====================


def _log_sync_start(db_url: str, condominio_id: str | None, sync_type: str, triggered_by: str) -> str | None:
    """Insere linha na solides_sync_log com status=running e retorna o log_id."""
    if not db_url:
        return None
    try:
        from sqlalchemy import create_engine
        from sqlalchemy import text as sa_text

        log_id = str(uuid4())
        # Resolve condominio_id: usa o informado ou busca da config
        cid = condominio_id
        if not cid:
            engine = create_engine(db_url)
            with engine.connect() as conn:
                row = conn.execute(sa_text("SELECT condominio_id FROM solides_integration_config LIMIT 1")).first()
                if row:
                    cid = str(row[0])
                else:
                    cid = "615bbcf6-f473-48aa-a304-43eaea9bfaf7"
        else:
            engine = create_engine(db_url)

        with engine.connect() as conn:
            conn.execute(
                sa_text(
                    "INSERT INTO solides_sync_log "
                    "(id, condominio_id, entity_type, sync_type, direction, status, "
                    " started_at, triggered_by, ativo, created_at) "
                    "VALUES (:id, :cid, 'all', :stype, 'solides_to_conecta', 'running', "
                    " :ts, :tby, true, :ts)"
                ),
                {"id": log_id, "cid": cid, "stype": sync_type, "ts": datetime.utcnow(), "tby": triggered_by},
            )
            conn.commit()
        return log_id
    except Exception as exc:
        logger.warning("[Solides] Não foi possível criar sync_log: %s", exc)
        return None


def _log_sync_end(
    db_url: str, log_id: str | None, success: bool, duration_ms: int, items: int, created: int, updated: int = 0
) -> None:
    """Atualiza linha na solides_sync_log com resultado final."""
    if not db_url or not log_id:
        return
    try:
        from sqlalchemy import create_engine
        from sqlalchemy import text as sa_text

        final_status = "completed" if success else "failed"
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute(
                sa_text(
                    "UPDATE solides_sync_log SET "
                    "  status = :st, completed_at = :ts, duration_ms = :dur, "
                    "  items_processed = :proc, items_created = :creat, items_updated = :upd "
                    "WHERE id = :id"
                ),
                {
                    "st": final_status,
                    "ts": datetime.utcnow(),
                    "dur": duration_ms,
                    "proc": items,
                    "creat": created,
                    "upd": updated,
                    "id": log_id,
                },
            )
            conn.commit()
    except Exception as exc:
        logger.warning("[Solides] Não foi possível atualizar sync_log %s: %s", log_id, exc)


def get_event_loop():
    """Obtém ou cria event loop para execução de código async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


def run_async(coro):
    """Executa coroutine de forma síncrona."""
    loop = get_event_loop()
    return loop.run_until_complete(coro)


def _fetch_tangerino_lookup_maps(api_token: str) -> tuple[dict, dict]:
    """Busca job-roles e work-schedules da API Tangerino para lookup por ID.

    Retorna:
        job_roles_map: {id: description} para resolver jobRoleDTO.id → nome cargo
        schedules_map: {id: name} para resolver currentWorkSchedule.id → nome escala
    """
    import requests

    job_roles_map: dict = {}
    schedules_map: dict = {}
    if not api_token:
        return job_roles_map, schedules_map

    headers = {"Authorization": f"Basic {api_token}", "Accept": "application/json"}
    base = "https://employer.tangerino.com.br"

    try:
        resp = requests.get(f"{base}/job-role/find-all", headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("content", data) if isinstance(data, dict) else data
            for jr in items if isinstance(items, list) else []:
                if jr.get("id"):
                    job_roles_map[jr["id"]] = jr.get("description", "")
    except Exception as exc:
        logger.warning("[Solides] Erro ao buscar job-roles: %s", exc)

    try:
        resp = requests.get(f"{base}/work-schedule", params={"size": 200}, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("content", data) if isinstance(data, dict) else data
            for ws in items if isinstance(items, list) else []:
                if ws.get("id"):
                    schedules_map[ws["id"]] = ws.get("name", "")
    except Exception as exc:
        logger.warning("[Solides] Erro ao buscar work-schedules: %s", exc)

    logger.info("[Solides] Lookup maps: %d job-roles, %d schedules", len(job_roles_map), len(schedules_map))
    return job_roles_map, schedules_map


def _resolve_escala(schedule_name: str) -> str:
    """Converte nome de escala Tangerino para código padronizado (max 20 chars).

    Retorna "" se o padrão não for reconhecido (evita StringDataRightTruncation).
    """
    if not schedule_name:
        return ""
    s = schedule_name.upper()
    if "12" in s and "36" in s:
        return "12x36"
    if "24" in s and "72" in s:
        return "24x72"
    if "44" in s or "8H" in s or "8 H" in s:
        return "44h"
    if "36" in s and "H" in s:
        return "36h"
    if "30" in s:
        return "30h"
    if "COMERCIAL" in s or "ESCRIT" in s:
        return "44h"
    # Turnos de portaria (diurno/noturno) sem identificação de horas = 12x36
    if "PORTARIA" in s or "DIURNO" in s or "NOTURNO" in s:
        return "12x36"
    # Não reconhecido: não atualizar (evita truncamento em varchar(20))
    return ""


def _propagate_employees_to_db(solides_employees: list[dict]) -> dict:
    """Propaga dados do Sólides para tabela employees (por CPF).

    Campos sincronizados (disponíveis na API Tangerino /employee/find-all):
      data_nascimento, sexo, pis, data_admissao, solides_id, nome,
      matricula (via externalId), cargo (via jobRoleDTO.id),
      escala_padrao (via currentWorkSchedule.id), data_demissao/status.

    Campos NÃO disponíveis na API Tangerino (requerem entrada manual):
      estado_civil, nome_mae, nome_pai, rg, ctps_*, titulo_eleitor,
      naturalidade, nacionalidade, telefone, celular, endereço.

    Returns:
        Dict com estatisticas de propagacao.
    """
    from datetime import datetime

    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
    if not db_url:
        logger.warning("[Solides] DATABASE_URL nao configurado, pulando propagacao")
        return {"propagated": 0, "error": "no_db_url"}

    # Pre-fetch lookup maps para cargo e escala
    api_token = os.getenv("SOLIDES_API_TOKEN", "")
    job_roles_map, schedules_map = _fetch_tangerino_lookup_maps(api_token)

    engine = create_engine(db_url)
    updated = 0
    created = 0
    not_found = 0
    inactivated = 0
    cpfs_solides = set()

    with engine.connect() as conn:
        for emp in solides_employees:
            cpf = (emp.get("cpf") or "").replace(".", "").replace("-", "").strip()
            if not cpf:
                continue
            cpfs_solides.add(cpf)

            # Parse birthDate (ms timestamp)
            birth = None
            bd = emp.get("birthDate")
            if bd:
                try:
                    birth = datetime.fromtimestamp(bd / 1000).date()
                except Exception:
                    pass

            # Parse admissionDate
            adm = None
            ad = emp.get("admissionDate")
            if ad:
                try:
                    adm = datetime.fromtimestamp(ad / 1000).date()
                except Exception:
                    pass

            # Parse terminationDate (demissão)
            termination = None
            td = emp.get("terminationDate")
            if td:
                try:
                    if isinstance(td, (int, float)):
                        termination = datetime.fromtimestamp(td / 1000).date()
                    elif isinstance(td, str):
                        termination = datetime.fromisoformat(td[:10]).date()
                except Exception:
                    pass

            # Gender (varchar(1)) — API retorna "MASCULINO"/"FEMININO"
            gender = emp.get("gender", "")
            sexo = None
            if "FEM" in gender.upper():
                sexo = "F"
            elif "MASC" in gender.upper():
                sexo = "M"

            pis = (emp.get("pis", "") or "")[:20]
            sid = str(emp.get("id", ""))
            name = emp.get("name", "")

            # Matricula via externalId (API retorna "000206" → armazenar "206")
            external_id = (emp.get("externalId") or "").strip()
            matricula = None
            if external_id:
                try:
                    matricula = str(int(external_id))
                except ValueError:
                    matricula = external_id[:20]

            # Cargo via jobRoleDTO.id → job_roles_map (corrige bug: API usa jobRoleDTO, não jobRole)
            job_role_dto = emp.get("jobRoleDTO", {})
            job_role_id = job_role_dto.get("id") if isinstance(job_role_dto, dict) else None
            cargo_nome = job_roles_map.get(job_role_id, "") if job_role_id else ""
            # Fallback para campo legado (webhook/outros paths)
            if not cargo_nome:
                legacy = emp.get("jobRole", {})
                if isinstance(legacy, dict):
                    cargo_nome = legacy.get("name", "") or legacy.get("description", "")
                elif isinstance(legacy, str):
                    cargo_nome = legacy

            # Escala via currentWorkSchedule.id → schedules_map (corrige bug: API usa currentWorkSchedule)
            ws_dto = emp.get("currentWorkSchedule", {})
            ws_id = ws_dto.get("id") if isinstance(ws_dto, dict) else None
            schedule_name = schedules_map.get(ws_id, "") if ws_id else ""
            # Fallback para campo legado
            if not schedule_name:
                legacy_ws = emp.get("workSchedule") or emp.get("work_schedule") or {}
                if isinstance(legacy_ws, dict):
                    schedule_name = legacy_ws.get("name", "") or legacy_ws.get("description", "")
                elif isinstance(legacy_ws, str):
                    schedule_name = legacy_ws

            sets = []
            params = {"cpf": cpf}
            if birth:
                sets.append("data_nascimento = :b")
                params["b"] = birth
            if sexo:
                sets.append("sexo = :s")
                params["s"] = sexo
            if pis:
                sets.append("pis = :p")
                params["p"] = pis
            if adm:
                sets.append("data_admissao = :a")
                params["a"] = adm
            if sid:
                sets.append("solides_id = :sid")
                params["sid"] = sid
            if name:
                sets.append("nome = :nome")
                params["nome"] = name
            if matricula:
                sets.append("matricula = :mat")
                params["mat"] = matricula
            if cargo_nome:
                sets.append("cargo = :cargo")
                params["cargo"] = cargo_nome[:100].upper()

            if termination:
                sets.append("data_demissao = :td")
                params["td"] = termination
                sets.append("status = :st")
                params["st"] = "inativo"

            escala = _resolve_escala(schedule_name)
            if escala:
                sets.append("escala_padrao = :escala")
                params["escala"] = escala

            if sets:
                # Fix B: sempre bumpar updated_at para auditabilidade do sync
                sets.append("updated_at = NOW()")
                # Se há demissão, atualizar mesmo que já esteja inativo (para garantir data_demissao)
                status_filter = "AND status IN ('ativo', 'inativo')" if termination else "AND status = 'ativo'"
                sql = f"UPDATE employees SET {', '.join(sets)} WHERE cpf = :cpf {status_filter}"
                r = conn.execute(text(sql), params)
                if r.rowcount > 0:
                    updated += 1
                else:
                    # Fix A: CPF não casou com employee ativo.
                    #  - Se o CPF NÃO existe em employees → INSERT (novo contratado no Sólides).
                    #  - Se existe mas está inativo → NÃO inserir (evita CPF duplicado); reativação é manual.
                    exists = conn.execute(
                        text("SELECT 1 FROM employees WHERE cpf = :cpf LIMIT 1"), {"cpf": cpf}
                    ).first()
                    if exists or not name:
                        not_found += 1
                    else:
                        ins_cols = ["id", "nome", "cpf", "status", "created_at", "updated_at"]
                        ins_vals = ["gen_random_uuid()", ":nome", ":cpf", "'ativo'", "NOW()", "NOW()"]
                        ins_params = {"nome": name, "cpf": cpf}
                        for col, key, val in [
                            ("data_nascimento", "b", birth),
                            ("sexo", "s", sexo),
                            ("pis", "p", pis),
                            ("data_admissao", "a", adm),
                            ("solides_id", "sid", sid),
                            ("matricula", "mat", matricula),
                            ("cargo", "cargo", (cargo_nome[:100].upper() if cargo_nome else None)),
                            ("escala_padrao", "escala", escala),
                        ]:
                            if val:
                                ins_cols.append(col)
                                ins_vals.append(f":{key}")
                                ins_params[key] = val
                        ins_sql = f"INSERT INTO employees ({', '.join(ins_cols)}) VALUES ({', '.join(ins_vals)})"
                        conn.execute(text(ins_sql), ins_params)
                        created += 1

        # Inativar quem tem solides_id mas nao esta mais no Solides
        if cpfs_solides:
            cpf_list = ",".join(f"'{c}'" for c in cpfs_solides)
            inact_sql = text(
                f"UPDATE employees SET status = 'inativo', data_demissao = CURRENT_DATE "
                f"WHERE solides_id IS NOT NULL AND cpf NOT IN ({cpf_list}) "
                f"AND status = 'ativo' AND data_demissao IS NULL"
            )
            r = conn.execute(inact_sql)
            inactivated = r.rowcount

        conn.commit()

    logger.info(
        "[Solides] Propagacao: %d atualizados, %d criados, %d sem match, %d inativados",
        updated,
        created,
        not_found,
        inactivated,
    )
    return {
        "propagated": updated,
        "created": created,
        "not_found": not_found,
        "inactivated": inactivated,
        "total_solides": len(solides_employees),
    }


# ==================== SYNC TASKS ====================


@shared_task(
    bind=True,
    name="solides.full_sync",
    max_retries=3,
    default_retry_delay=300,
    soft_time_limit=3600,
    time_limit=3900,
)
def sync_solides_full(
    self, condominio_id: str = None, entity_types: list[str] | None = None, triggered_by: str = "scheduler"
):
    """
    Task para sincronização completa com Sólides.

    Args:
        condominio_id: ID do condomínio (opcional)
        entity_types: Tipos de entidade (ou todas configuradas)
        triggered_by: Quem disparou (user, scheduler, webhook)
    """
    logger.info("[Solides Task] Iniciando full sync")
    db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
    started_at = datetime.utcnow()
    log_id = _log_sync_start(db_url, condominio_id, "full", triggered_by)

    async def _sync():
        from modules.integrations.connectors.solides.connector import SolidesConnector

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return {"success": False, "error": "SOLIDES_API_TOKEN não configurado"}

        connector = SolidesConnector(
            account_id=uuid4(),
            tenant_id=UUID(condominio_id) if condominio_id else uuid4(),
            config={},
            credentials={"api_token": api_token},
        )

        await connector.setup()

        try:
            results = {
                "employees": 0,
                "job_roles": 0,
                "workplaces": 0,
                "work_schedules": 0,
            }

            # Sincronizar cada entidade
            employees_data = []
            for entity_type in entity_types or ["employees", "job_roles", "workplaces", "work_schedules"]:
                try:
                    result = await connector.fetch_entities(entity_type, page_size=100)
                    if result.success:
                        results[entity_type] = len(result.data)
                        logger.info(f"[Solides Task] Sincronizado {entity_type}: {len(result.data)} registros")
                        if entity_type == "employees":
                            employees_data = result.data
                except Exception as e:
                    logger.error(f"[Solides Task] Erro ao sincronizar {entity_type}: {e}")

            # Propagar dados dos funcionarios para tabela employees
            propagation = {"propagated": 0}
            if employees_data:
                try:
                    propagation = _propagate_employees_to_db(employees_data)
                    logger.info(f"[Solides Task] Propagacao: {propagation}")
                except Exception as e:
                    logger.error(f"[Solides Task] Erro na propagacao: {e}")
                    propagation = {"propagated": 0, "error": str(e)}

            return {
                "success": True,
                "triggered_by": triggered_by,
                "results": results,
                "total": sum(results.values()),
                "propagation": propagation,
            }
        finally:
            await connector.teardown()

    try:
        ret = run_async(_sync())
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        total = ret.get("total", 0) if isinstance(ret, dict) else 0
        prop = ret.get("propagation", {}) if isinstance(ret, dict) else {}
        _log_sync_end(
            db_url,
            log_id,
            ret.get("success", False) if isinstance(ret, dict) else False,
            duration_ms,
            total,
            prop.get("created", 0),
            prop.get("propagated", 0),
        )
        return ret
    except Exception as e:
        logger.error(f"[Solides Task] Erro no full sync: {e}")
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        _log_sync_end(db_url, log_id, False, duration_ms, 0, 0)
        raise self.retry(exc=e)


@shared_task(
    bind=True,
    name="solides.incremental_sync",
    max_retries=5,
    default_retry_delay=60,
    soft_time_limit=600,
    time_limit=660,
)
def sync_solides_incremental(self, condominio_id: str = None, entity_types: list[str] | None = None):
    """
    Task para sincronização incremental com Sólides.
    """
    logger.debug("[Solides Task] Iniciando incremental sync")
    db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
    started_at = datetime.utcnow()
    log_id = _log_sync_start(db_url, condominio_id, "incremental", "scheduler")

    async def _sync():
        from modules.integrations.connectors.solides.connector import SolidesConnector

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return {"success": False, "error": "Token não configurado"}

        connector = SolidesConnector(
            account_id=uuid4(),
            tenant_id=UUID(condominio_id) if condominio_id else uuid4(),
            config={},
            credentials={"api_token": api_token},
        )

        await connector.setup()

        try:
            # Busca funcionarios atuais do Solides
            result = await connector.fetch_entities("employees", page_size=100)

            propagation = {"propagated": 0}
            if result.success and result.data:
                try:
                    propagation = _propagate_employees_to_db(result.data)
                except Exception as e:
                    logger.error(f"[Solides Task] Erro na propagacao incremental: {e}")
                    propagation = {"propagated": 0, "error": str(e)}

            return {
                "success": result.success,
                "processed": len(result.data) if result.success else 0,
                "propagation": propagation,
            }
        finally:
            await connector.teardown()

    try:
        ret = run_async(_sync())
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        processed = ret.get("processed", 0) if isinstance(ret, dict) else 0
        prop = ret.get("propagation", {}) if isinstance(ret, dict) else {}
        _log_sync_end(
            db_url,
            log_id,
            ret.get("success", False) if isinstance(ret, dict) else False,
            duration_ms,
            processed,
            prop.get("created", 0),
            prop.get("propagated", 0),
        )
        return ret
    except Exception as e:
        logger.error(f"[Solides Task] Erro no incremental sync: {e}")
        duration_ms = int((datetime.utcnow() - started_at).total_seconds() * 1000)
        _log_sync_end(db_url, log_id, False, duration_ms, 0, 0)
        raise self.retry(exc=e)


@shared_task(name="solides.sync_all_condominios_incremental")
def sync_all_condominios_incremental():
    """
    Task para sincronização incremental de TODOS os condomínios ativos.
    """
    logger.info("[Solides Task] Iniciando sync incremental de todos condomínios")

    # Por enquanto, executa um único sync global
    # Futuramente: buscar lista de condomínios configurados
    result = sync_solides_incremental.delay()

    return {"condominios": 1, "task_id": str(result.id)}


@shared_task(name="solides.sync_single_entity")
def sync_single_entity(condominio_id: str = None, entity_type: str = "employees", solides_id: str = None):
    """
    Task para sincronizar uma única entidade.
    """
    logger.info(f"[Solides Task] Sync single entity: {entity_type}/{solides_id}")

    async def _sync():
        from modules.integrations.connectors.solides.connector import SolidesConnector

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return {"success": False, "error": "Token não configurado"}

        connector = SolidesConnector(
            account_id=uuid4(),
            tenant_id=UUID(condominio_id) if condominio_id else uuid4(),
            config={},
            credentials={"api_token": api_token},
        )

        await connector.setup()

        try:
            if solides_id:
                result = await connector.fetch_entity_by_id(entity_type, solides_id)
                return {"success": result is not None, "action": "fetched" if result else "not_found", "data": result}
            else:
                return {"success": False, "error": "solides_id é obrigatório"}
        finally:
            await connector.teardown()

    return run_async(_sync())


# ==================== HEALTH CHECK TASKS ====================


@shared_task(name="solides.health_check")
def check_solides_health(condominio_id: str = None):
    """
    Task para verificar saúde da conexão com Sólides.
    """
    logger.debug("[Solides Task] Health check")

    async def _check():
        from modules.integrations.connectors.solides.connector import SolidesConnector

        api_token = os.getenv("SOLIDES_API_TOKEN")
        if not api_token:
            return {"status": "error", "message": "Token não configurado"}

        connector = SolidesConnector(
            account_id=uuid4(),
            tenant_id=UUID(condominio_id) if condominio_id else uuid4(),
            config={},
            credentials={"api_token": api_token},
        )

        await connector.setup()

        try:
            result = await connector.health_check()
            return {
                "status": "healthy" if result.healthy else "unhealthy",
                "latency_ms": result.latency_ms,
                "message": result.message,
                "api": result.details.get("api", "unknown"),
            }
        finally:
            await connector.teardown()

    return run_async(_check())


@shared_task(name="solides.health_check_all")
def check_all_solides_health():
    """
    Task para verificar saúde de TODAS as integrações ativas.
    """
    logger.info("[Solides Task] Health check de todas integrações")

    # Executa um único health check global
    result = check_solides_health.delay()

    return {"condominios_checked": 1, "task_id": str(result.id)}


# ==================== WEBHOOK PROCESSING ====================


@shared_task(name="solides.process_webhook_queue")
def process_webhooks():
    """
    Task para processar webhooks enfileirados.
    """
    logger.debug("[Solides Task] Processando webhooks")

    # Placeholder - implementar quando webhooks forem configurados
    return {"processed": 0, "message": "Nenhum webhook na fila"}


@shared_task(name="solides.retry_failed_webhooks")
def retry_failed_webhooks():
    """
    Task para reprocessar webhooks que falharam.
    """
    logger.info("[Solides Task] Reprocessando webhooks com falha")

    # Placeholder - implementar quando webhooks forem configurados
    return {"retried": 0, "message": "Nenhum webhook com falha"}


# ==================== CLEANUP TASKS ====================


@shared_task(name="solides.cleanup_old_logs")
def cleanup_old_sync_logs(days: int = 30):
    """
    Task para limpar logs antigos de sincronização.
    """
    logger.info(f"[Solides Task] Limpando logs mais antigos que {days} dias")

    # Placeholder - implementar com banco de dados
    return {"deleted_logs": 0, "message": f"Cleanup de logs > {days} dias"}


@shared_task(name="solides.cleanup_old_webhooks")
def cleanup_old_webhook_logs(days: int = 7):
    """
    Task para limpar logs antigos de webhooks.
    """
    logger.info(f"[Solides Task] Limpando webhooks mais antigos que {days} dias")

    # Placeholder - implementar com banco de dados
    return {"deleted_webhooks": 0, "message": f"Cleanup de webhooks > {days} dias"}


# ==================== WORK SCHEDULE SYNC ====================


@shared_task(name="integrations.sync_work_schedules_from_solides", bind=True, max_retries=2)
def sync_work_schedules_from_solides(self) -> dict:
    """Sincroniza escalas de trabalho do Sólides para employees.escala_padrao."""
    import os

    api_token = os.getenv("SOLIDES_API_TOKEN")
    if not api_token:
        logger.warning("[Solides] SOLIDES_API_TOKEN não configurado — pulando sync de escalas")
        return {"success": False, "reason": "no_token"}

    try:
        db_url = os.environ.get("DATABASE_URL", "").replace("+asyncpg", "")
        if not db_url:
            return {"success": False, "reason": "no_db_url"}

        from sqlalchemy import create_engine
        from sqlalchemy import text as sa_text

        engine = create_engine(db_url)

        # Buscar escalas do Sólides de forma síncrona via httpx
        import httpx

        headers = {"Authorization": f"Basic {api_token}", "Accept": "application/json"}
        base_url = os.getenv("SOLIDES_BASE_URL", "https://employer.tangerino.com.br")

        resp = httpx.get(f"{base_url}/work-schedule", headers=headers, timeout=30)
        if resp.status_code != 200:
            logger.warning("[Solides] Erro ao buscar work-schedules: %s", resp.status_code)
            return {"success": False, "reason": f"api_error_{resp.status_code}"}

        data = resp.json()
        schedules = data if isinstance(data, list) else data.get("content", data.get("data", []))

        # Mapear id → nome normalizado
        schedule_map = {}
        for s in schedules:
            sid = str(s.get("id", ""))
            name = s.get("name", "") or s.get("description", "")
            if sid and name:
                sched_upper = name.upper()
                if "12" in sched_upper and "36" in sched_upper:
                    schedule_map[sid] = "12x36"
                elif "44" in sched_upper or "8H" in sched_upper:
                    schedule_map[sid] = "44h"
                elif "24" in sched_upper and "72" in sched_upper:
                    schedule_map[sid] = "24x72"
                else:
                    schedule_map[sid] = name[:30]

        # Buscar employees com solides_id e atualizar escala
        updated = 0
        with engine.connect() as conn:
            # Buscar employees com solides_id mapeado
            rows = conn.execute(
                sa_text(
                    "SELECT e.id, se.extra_data "
                    "FROM employees e "
                    "JOIN solides_employees se ON se.employee_id = e.id "
                    "WHERE e.status = 'ativo'"
                )
            ).fetchall()

            for row in rows:
                emp_id = row[0]
                extra = row[1] or {}
                sched_id = str(extra.get("workScheduleId", "") or extra.get("work_schedule_id", ""))
                if sched_id and sched_id in schedule_map:
                    conn.execute(
                        sa_text("UPDATE employees SET escala_padrao = :e WHERE id = :id"),
                        {"e": schedule_map[sched_id], "id": emp_id},
                    )
                    updated += 1

            conn.commit()

        logger.info("[Solides] Escalas sincronizadas: %d colaboradores atualizados", updated)
        return {"success": True, "updated": updated, "schedules_found": len(schedule_map)}

    except Exception as e:
        logger.error("[Solides] Erro ao sincronizar escalas: %s", e)
        return {"success": False, "error": str(e)}


# ==================== HELPER FUNCTIONS ====================


def schedule_full_sync(condominio_id: str = None, delay_seconds: int = 0):
    """
    Agenda full sync para um condomínio.
    """
    return sync_solides_full.apply_async(
        args=[condominio_id], kwargs={"triggered_by": "manual"}, countdown=delay_seconds, queue="integrations"
    )


def schedule_incremental_sync(condominio_id: str = None):
    """
    Agenda sync incremental para um condomínio.
    """
    return sync_solides_incremental.apply_async(args=[condominio_id], queue="integrations")


def schedule_entity_sync(condominio_id: str, entity_type: str, solides_id: str):
    """
    Agenda sync de uma entidade específica.
    """
    return sync_single_entity.apply_async(args=[condominio_id, entity_type, solides_id], queue="integrations")
