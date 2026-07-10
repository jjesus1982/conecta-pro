"""
Fluxo FALTA → SUBSTITUTO direto do Quadro de Presença (Operacional).

Une as duas metades que existiam desconexas: shifts/mark-missed (só ligava a
flag) e a tabela `substitutions` (CRUD sem uso). Agora, do próprio quadro:

- POST /presenca/falta/{shift_id}            → registra a falta (shift 'missed'
  + needs_substitution) e ABRE a substituição (substitutions, status pending).
  Idempotente: repetir devolve a substituição já aberta.
- GET  /presenca/substitutos/{substitution_id} → sugestões REAIS de cobertura:
  funcionários compatíveis LIVRES no dia (sem turno, sem férias) e diaristas
  ativos do Fluxo 2 com o VALOR AUTOMÁTICO da diária (diaria_precos).
- POST /presenca/substituir/{substitution_id}  → escala o substituto:
  * funcionário → cria o turno espelho no posto e confirma a substituição;
  * diarista    → lança a diária (valor automático, elo financeiro do dia 15)
                  e confirma a substituição com o diarista na nota.
  Diarista novo? A UI usa o cadastro rápido existente
  (POST /operacional/diarias/diaristas — CPF+PIX obrigatórios) e volta aqui.

REGRAS:
- Escopo por posto: líder opera o próprio posto; gestor, todos (scope.py).
- Falta só de HOJE ou de ONTEM (noturno da véspera) — retroagir mais é
  correção de histórico, não operação do dia.
- Quem já tem presença registrada (batida/check-in) não pode ser marcado
  faltoso → 409.
- Substituto funcionário com turno ativo no dia → 409 (nunca dois postos).
- NUNCA fabricar: sem preço de diária cadastrado p/ função|turno → 422.

Timezone: America/Manaus naive, como o resto do quadro (docstring do
presence_controller).
"""

import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logging import logger
from modules.operacional.diaristas import diarias_service
from modules.operacional.scope import (
    OperationalScope,
    get_operational_scope,
    scope_post_ids_or_403,
)

router = APIRouter(prefix="/presenca", tags=["Operacional - Falta e Substituto"])

TZ_MANAUS = ZoneInfo("America/Manaus")

# Motivo da UI → SubstitutionReason (enum String(50) da tabela substitutions)
MOTIVOS = {
    "falta": "no_show",
    "atestado": "sick_leave",
    "emergencia": "emergency",
    "pessoal": "personal",
    "outro": "other",
}

# Cargos que se cobrem entre si (líder cobre agente e vice-versa)
CARGOS_COMPATIVEIS = {
    "AGENTE DE PORTARIA": ["AGENTE DE PORTARIA", "LÍDER DE PORTARIA"],
    "LÍDER DE PORTARIA": ["AGENTE DE PORTARIA", "LÍDER DE PORTARIA"],
}

# Cargo do faltoso → função da tabela de diárias (planilha do Jordan)
CARGO_PARA_FUNCAO = {
    "AGENTE DE PORTARIA": "AGENTE DE PORTARIA",
    "LÍDER DE PORTARIA": "AGENTE DE PORTARIA",
    "AGENTE DE SERVIÇOS GERAIS": "AUX. SERVIÇOS GERAIS",
    "JARDINEIRO": "JARDINEIRO",
    "ARTÍFICE": "AJUDANTE",
}


def _hoje_manaus() -> date:
    return datetime.now(TZ_MANAUS).date()


def _agora_manaus() -> datetime:
    return datetime.now(TZ_MANAUS).replace(tzinfo=None)


class FaltaBody(BaseModel):
    motivo: str = Field(default="falta", pattern="^(falta|atestado|emergencia|pessoal|outro)$")
    detalhes: str | None = Field(default=None, max_length=500)


class SubstituirBody(BaseModel):
    tipo: str = Field(pattern="^(funcionario|diarista)$")
    employee_id: str | None = None
    diarista_id: int | None = None
    funcao: str | None = None
    turno: str | None = None
    observacao: str | None = Field(default=None, max_length=500)


def _post_no_escopo(scope: OperationalScope, post_id: str) -> None:
    pids = scope_post_ids_or_403(scope)
    if pids is not None and post_id not in pids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Você não opera este posto.",
        )


async def _shift_completo(db: AsyncSession, shift_id: str) -> dict:
    try:
        uuid.UUID(shift_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Turno não encontrado.")
    row = (
        await db.execute(
            text(
                """
                SELECT s.id::text, s.employee_id::text, s.post_id::text, s.scale_id::text,
                       s.shift_date, s.planned_start_time, s.planned_end_time,
                       s.planned_break_minutes, s.planned_hours, s.is_night_shift,
                       s.status, s.actual_start_time, p.name AS post_nome, e.nome, e.cargo
                FROM shifts s
                JOIN posts p ON p.id = s.post_id
                LEFT JOIN employees e ON e.id = s.employee_id
                WHERE s.id = CAST(:s AS uuid) AND s.is_active
                """
            ),
            {"s": shift_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Turno não encontrado.")
    keys = ["id", "employee_id", "post_id", "scale_id", "shift_date", "inicio", "fim",
            "pausa", "horas", "noturno", "status", "actual_start", "post_nome", "nome", "cargo"]
    return dict(zip(keys, row))


async def _substituicao_ou_404(db: AsyncSession, substitution_id: str) -> dict:
    try:
        uuid.UUID(substitution_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Substituição não encontrada.")
    row = (
        await db.execute(
            text(
                """
                SELECT su.id::text, su.shift_id::text, su.post_id::text,
                       su.original_employee_id::text, su.status, su.reason,
                       su.substitution_date, p.name, e.nome, e.cargo,
                       s.planned_start_time, s.planned_end_time, s.scale_id::text,
                       s.planned_break_minutes, s.planned_hours, s.is_night_shift
                FROM substitutions su
                JOIN shifts s ON s.id = su.shift_id
                JOIN posts p ON p.id = su.post_id
                LEFT JOIN employees e ON e.id = su.original_employee_id
                WHERE su.id = CAST(:i AS uuid) AND su.is_active
                """
            ),
            {"i": substitution_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Substituição não encontrada.")
    keys = ["id", "shift_id", "post_id", "original_employee_id", "status", "reason",
            "data", "post_nome", "faltoso_nome", "faltoso_cargo", "inicio", "fim",
            "scale_id", "pausa", "horas", "noturno"]
    return dict(zip(keys, row))


def _turno_diaria(inicio) -> str:
    """Turno da diária derivado do horário do turno (regra do quadro: >=15h = noturno)."""
    return "NOTURNO" if inicio and inicio.hour >= 15 else "DIURNO"


@router.post("/falta/{shift_id}", status_code=status.HTTP_201_CREATED)
async def registrar_falta(
    shift_id: str,
    body: FaltaBody,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
):
    """Marca a falta do turno e abre a substituição do dia (idempotente)."""
    shift = await _shift_completo(db, shift_id)
    _post_no_escopo(scope, shift["post_id"])

    if not shift["employee_id"]:
        raise HTTPException(status_code=422, detail="Turno sem colaborador — não há falta a registrar.")
    hoje = _hoje_manaus()
    if not (hoje - timedelta(days=1) <= shift["shift_date"] <= hoje):
        raise HTTPException(status_code=422, detail="Falta só pode ser registrada para o turno de hoje ou de ontem (noturno da véspera).")
    if shift["status"] in ("cancelled", "completed"):
        raise HTTPException(status_code=422, detail=f"Turno está '{shift['status']}' — não cabe falta.")
    if shift["actual_start"] is not None:
        raise HTTPException(status_code=409, detail=f"{shift['nome']} já tem presença registrada neste turno.")

    # Batida real na janela do turno também bloqueia (mesma lógica do quadro)
    ini_janela = datetime.combine(shift["shift_date"], shift["inicio"]) - timedelta(hours=2)
    fim_janela = (
        datetime.combine(shift["shift_date"] + timedelta(days=1), datetime.min.time().replace(hour=7))
        if shift["inicio"].hour >= 15
        else datetime.combine(shift["shift_date"], shift["fim"])
    )
    batida = (
        await db.execute(
            text(
                """
                SELECT 1 FROM gp_clock_punches
                WHERE employee_id = CAST(:e AS uuid)
                  AND (punch_timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'America/Manaus')
                      BETWEEN :ini AND :fim
                LIMIT 1
                """
            ),
            {"e": shift["employee_id"], "ini": ini_janela, "fim": fim_janela},
        )
    ).first()
    if batida:
        raise HTTPException(status_code=409, detail=f"{shift['nome']} tem batida de ponto na janela deste turno — não é falta.")

    # Idempotência: substituição já aberta para este turno
    existente = (
        await db.execute(
            text(
                """SELECT id::text, status FROM substitutions
                   WHERE shift_id=CAST(:s AS uuid) AND is_active AND status IN ('pending','confirmed')"""
            ),
            {"s": shift_id},
        )
    ).first()
    if existente:
        return {
            "ok": True, "ja_existia": True, "substitution_id": existente[0],
            "status": existente[1], "faltoso": shift["nome"], "posto": shift["post_nome"],
        }

    autoria = f"FALTA registrada por {scope.user_name} em {_agora_manaus().strftime('%d/%m %H:%M')} (motivo: {body.motivo})"
    await db.execute(
        text(
            """UPDATE shifts SET status='missed', needs_substitution=true,
               notes=COALESCE(notes,'') || ' | ' || :aut, updated_at=now()
               WHERE id=CAST(:s AS uuid)"""
        ),
        {"s": shift_id, "aut": autoria},
    )
    sub_id = str(uuid.uuid4())
    await db.execute(
        text(
            """
            INSERT INTO substitutions (id, shift_id, post_id, original_employee_id,
                reason, reason_details, status, substitution_date, requested_at,
                requested_by, notification_sent, is_overtime, is_active, created_at, updated_at)
            VALUES (CAST(:id AS uuid), CAST(:sh AS uuid), CAST(:p AS uuid), CAST(:e AS uuid),
                :motivo, :det, 'pending', :dia, now(),
                CAST(:u AS uuid), false, false, true, now(), now())
            """
        ),
        {"id": sub_id, "sh": shift_id, "p": shift["post_id"], "e": shift["employee_id"],
         "motivo": MOTIVOS[body.motivo], "det": body.detalhes, "dia": shift["shift_date"],
         "u": scope.user_id},
    )
    await db.commit()
    logger.info(f"[falta] {scope.user_name}: {shift['nome']} faltou em {shift['post_nome']} ({body.motivo}) → substituição {sub_id}")
    return {
        "ok": True, "ja_existia": False, "substitution_id": sub_id, "status": "pending",
        "faltoso": shift["nome"], "cargo": shift["cargo"], "posto": shift["post_nome"],
        "data": str(shift["shift_date"]), "motivo": body.motivo,
    }


@router.get("/substitutos/{substitution_id}")
async def sugerir_substitutos(
    substitution_id: str,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
):
    """Sugestões REAIS de cobertura: funcionários livres no dia + diaristas com preço."""
    sub = await _substituicao_ou_404(db, substitution_id)
    _post_no_escopo(scope, sub["post_id"])

    cargo = (sub["faltoso_cargo"] or "").upper()
    cargos_ok = CARGOS_COMPATIVEIS.get(cargo, [cargo] if cargo else [])

    funcionarios = []
    if cargos_ok:
        rows = (
            await db.execute(
                text(
                    """
                    SELECT DISTINCT ON (e.id) e.id::text, e.nome, e.cargo, p2.name,
                           (a.post_id = CAST(:post AS uuid)) AS mesmo_posto
                    FROM employees e
                    LEFT JOIN allocations a ON a.employee_id=e.id AND a.status='active' AND a.is_active
                    LEFT JOIN posts p2 ON p2.id=a.post_id
                    WHERE e.status='ativo' AND upper(e.cargo) = ANY(CAST(:cargos AS text[]))
                      AND e.id <> CAST(:faltoso AS uuid)
                      AND NOT EXISTS (
                        SELECT 1 FROM shifts s2 WHERE s2.employee_id=e.id AND s2.shift_date=:dia
                          AND s2.is_active AND NOT s2.is_off_day
                          AND s2.status IN ('scheduled','in_progress','completed'))
                      AND NOT EXISTS (
                        SELECT 1 FROM hr_vacation_requests v WHERE v.employee_id=e.id
                          AND upper(v.status) IN ('APPROVED','IN_PROGRESS','SCHEDULED')
                          AND :dia BETWEEN v.start_date AND v.end_date)
                    ORDER BY e.id, mesmo_posto DESC
                    """
                ),
                {"cargos": cargos_ok, "faltoso": sub["original_employee_id"],
                 "dia": sub["data"], "post": sub["post_id"]},
            )
        ).all()
        funcionarios = sorted(
            [
                {"employee_id": r[0], "nome": r[1], "cargo": r[2],
                 "posto_atual": r[3], "mesmo_posto": bool(r[4]),
                 "disponibilidade": "de folga hoje (sem turno agendado)"}
                for r in rows
            ],
            key=lambda f: (not f["mesmo_posto"], f["nome"]),
        )

    # Diaristas do Fluxo 2 (planilha) com o valor automático da diária
    funcao_sugerida = CARGO_PARA_FUNCAO.get(cargo)
    turno_diaria = _turno_diaria(sub["inicio"])
    valor_sugerido = (
        await diarias_service.preco_de(db, funcao_sugerida, turno_diaria) if funcao_sugerida else None
    )
    dia_rows = (
        await db.execute(
            text(
                """SELECT id, nome, cpf, pix, COALESCE(funcoes, '{}') FROM diaria_diaristas
                   WHERE ativo ORDER BY (COALESCE(funcoes,'{}') @> ARRAY[CAST(:f AS text)]) DESC, nome"""
            ),
            {"f": funcao_sugerida or ""},
        )
    ).all()
    cadastros = await diarias_service.cadastros(db)

    return {
        "substitution_id": sub["id"],
        "status": sub["status"],
        "posto": sub["post_nome"],
        "data": str(sub["data"]),
        "faltoso": {"nome": sub["faltoso_nome"], "cargo": sub["faltoso_cargo"]},
        "turno": {"inicio": str(sub["inicio"])[:5], "fim": str(sub["fim"])[:5]},
        "funcionarios": funcionarios,
        "diaristas": [
            {"diarista_id": r[0], "nome": r[1], "cpf": r[2], "pix_ok": bool(r[3]),
             "funcoes": list(r[4]), "tem_funcao_sugerida": funcao_sugerida in list(r[4]) if funcao_sugerida else False}
            for r in dia_rows
        ],
        "diaria": {
            "funcao_sugerida": funcao_sugerida,
            "turno_sugerido": turno_diaria,
            "valor_sugerido": valor_sugerido,
            "funcoes_disponiveis": cadastros.get("funcoes", []),
            "precos": cadastros.get("precos", []),
        },
    }


@router.post("/substituir/{substitution_id}")
async def escalar_substituto(
    substitution_id: str,
    body: SubstituirBody,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
):
    """Escala o substituto do dia: funcionário (turno espelho) ou diarista (diária automática)."""
    sub = await _substituicao_ou_404(db, substitution_id)
    _post_no_escopo(scope, sub["post_id"])
    if sub["status"] != "pending":
        raise HTTPException(status_code=409, detail=f"Substituição já está '{sub['status']}'.")

    agora = _agora_manaus()

    if body.tipo == "funcionario":
        if not body.employee_id:
            raise HTTPException(status_code=422, detail="Informe employee_id do substituto.")
        emp = (
            await db.execute(
                text("SELECT id::text, nome, cargo FROM employees WHERE id=CAST(:e AS uuid) AND status='ativo'"),
                {"e": body.employee_id},
            )
        ).first()
        if not emp:
            raise HTTPException(status_code=404, detail="Substituto não encontrado ou não está ativo.")
        if emp[0] == sub["original_employee_id"]:
            raise HTTPException(status_code=422, detail="O substituto não pode ser o próprio faltoso.")
        conflito = (
            await db.execute(
                text(
                    """SELECT p.name FROM shifts s JOIN posts p ON p.id=s.post_id
                       WHERE s.employee_id=CAST(:e AS uuid) AND s.shift_date=:dia AND s.is_active
                         AND NOT s.is_off_day AND s.status IN ('scheduled','in_progress','completed')
                       LIMIT 1"""
                ),
                {"e": body.employee_id, "dia": sub["data"]},
            )
        ).first()
        if conflito:
            raise HTTPException(status_code=409, detail=f"{emp[1]} já tem turno hoje em {conflito[0]} — nunca dois postos no mesmo dia.")

        novo_shift = str(uuid.uuid4())
        nota = (
            f"SUBSTITUIÇÃO: cobre a falta de {sub['faltoso_nome']} ({sub['reason']}) — "
            f"escalado por {scope.user_name} em {agora.strftime('%d/%m %H:%M')}."
        )
        await db.execute(
            text(
                """
                INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date,
                    planned_start_time, planned_end_time, planned_break_minutes, status,
                    is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
                    planned_hours, actual_hours, overtime_hours, night_hours, base_pay,
                    overtime_pay, night_bonus, holiday_bonus, total_pay, notes, is_active,
                    created_at, updated_at)
                VALUES (CAST(:id AS uuid), CAST(:sc AS uuid), CAST(:emp AS uuid),
                    CAST(:post AS uuid), :dia, :ini, :fim, :pausa, 'scheduled',
                    false, :noturno, false, false, false, :h, 0,0,0,0,0,0,0,0,
                    :nota, true, now(), now())
                """
            ),
            {"id": novo_shift, "sc": sub["scale_id"], "emp": body.employee_id,
             "post": sub["post_id"], "dia": sub["data"], "ini": sub["inicio"],
             "fim": sub["fim"], "pausa": sub["pausa"] or 60, "noturno": bool(sub["noturno"]),
             "h": float(sub["horas"] or 12), "nota": nota},
        )
        await db.execute(
            text(
                """UPDATE substitutions SET substitute_employee_id=CAST(:e AS uuid),
                   status='confirmed', confirmed_at=now(), approved_by=CAST(:u AS uuid),
                   notes=COALESCE(notes,'') || :nota, updated_at=now()
                   WHERE id=CAST(:i AS uuid)"""
            ),
            {"e": body.employee_id, "u": scope.user_id, "i": substitution_id,
             "nota": f"Coberto por {emp[1]} (funcionário). {body.observacao or ''}"},
        )
        await db.execute(
            text("UPDATE shifts SET needs_substitution=false, updated_at=now() WHERE id=CAST(:s AS uuid)"),
            {"s": sub["shift_id"]},
        )
        await db.commit()
        logger.info(f"[substituto] {scope.user_name}: {emp[1]} cobre {sub['faltoso_nome']} em {sub['post_nome']} ({sub['data']})")
        return {
            "ok": True, "tipo": "funcionario", "substituto": emp[1],
            "shift_id": novo_shift, "posto": sub["post_nome"], "data": str(sub["data"]),
        }

    # ── diarista ──
    if not body.diarista_id:
        raise HTTPException(status_code=422, detail="Informe diarista_id.")
    diarista = (
        await db.execute(
            text("SELECT id, nome FROM diaria_diaristas WHERE id=:d AND ativo"),
            {"d": body.diarista_id},
        )
    ).first()
    if not diarista:
        raise HTTPException(status_code=404, detail="Diarista não encontrado ou inativo. Cadastre pelo cadastro rápido (CPF+PIX obrigatórios).")
    funcao = body.funcao or CARGO_PARA_FUNCAO.get((sub["faltoso_cargo"] or "").upper())
    if not funcao:
        raise HTTPException(status_code=422, detail="Informe a função da diária (sem mapeamento automático para este cargo).")
    turno = body.turno or _turno_diaria(sub["inicio"])
    obs = (
        f"Substituição de {sub['faltoso_nome']} ({sub['reason']}) em {sub['post_nome']} — "
        f"via quadro de presença por {scope.user_name}. {body.observacao or ''}"
    ).strip()

    # Confirma a substituição ANTES do lançamento (lancar() faz o commit da transação)
    await db.execute(
        text(
            """UPDATE substitutions SET status='confirmed', confirmed_at=now(),
               approved_by=CAST(:u AS uuid),
               notes=COALESCE(notes,'') || :nota, updated_at=now()
               WHERE id=CAST(:i AS uuid)"""
        ),
        {"u": scope.user_id, "i": substitution_id,
         "nota": f"Coberto por DIARISTA {diarista[1]} (#{diarista[0]}), função {funcao}/{turno}."},
    )
    await db.execute(
        text("UPDATE shifts SET needs_substitution=false, updated_at=now() WHERE id=CAST(:s AS uuid)"),
        {"s": sub["shift_id"]},
    )
    resultado = await diarias_service.lancar(
        db, data=str(sub["data"]), diarista_id=body.diarista_id, funcao=funcao,
        posto=sub["post_nome"], turno=turno, observacao=obs, user_id=scope.user_id,
    )
    if not resultado.get("ok"):
        await db.rollback()
        raise HTTPException(status_code=422, detail=resultado.get("mensagem", "Falha ao lançar a diária."))
    logger.info(
        f"[substituto] {scope.user_name}: diarista {diarista[1]} cobre {sub['faltoso_nome']} "
        f"em {sub['post_nome']} ({sub['data']}) — diária R${resultado['valor']:.2f} (lançamento #{resultado['id']})"
    )
    return {
        "ok": True, "tipo": "diarista", "substituto": diarista[1],
        "lancamento_id": resultado["id"], "valor_diaria": resultado["valor"],
        "funcao": funcao, "turno": resultado["turno"],
        "posto": sub["post_nome"], "data": str(sub["data"]),
    }
