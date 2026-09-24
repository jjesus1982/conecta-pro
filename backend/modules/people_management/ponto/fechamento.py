"""Fechamento do ponto como ATO (DGX T2, 24/09/2026).

Por que existe: o mês "fechava" em dois lugares (`time_sheets.status='fechado'` pelo espelho e
`gp_monthly_closings.fechado` pelo fechamento mensal) e NENHUM escritor de batida perguntava.
Ajuste do DP, lançamento manual e importação gravavam em competência fechada — e o espelho
fechado/homologado ficava mentindo para a assinatura. Na DGX o dia de apontamento fechado é
`bloqueado` no cartão e reabrir é ato com autor.

Aqui: UMA pergunta (`competencia_fechada`) para todos os escritores de DP, e UMA reabertura
com motivo obrigatório, registrada em `ponto_reaberturas`. A batida do app (`/batida`) NÃO
passa por aqui: o mês fecha depois de acabar, e a batida do app é de hoje.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text

# mesmo conjunto que o leitor do espelho considera "mês fechado" (espelho_service.STATUS_FECHADO_SET)
STATUS_FECHADO = ("fechado", "aprovado", "revisado", "enviado_folha")

_SQL_FECHADO = """
SELECT 'espelho' AS origem, coalesce(closed_by_name, closed_by_id, '') AS quem, closed_at AS quando,
       status
  FROM time_sheets
 WHERE employee_id = :e AND reference_month = :m AND reference_year = :y
   AND lower(coalesce(status,'')) IN ('fechado','aprovado','revisado','enviado_folha')
UNION ALL
SELECT 'fechamento mensal', coalesce(fechado_por, ''), fechado_em, 'fechado'
  FROM gp_monthly_closings
 WHERE employee_id = :e AND month = :m AND year = :y AND fechado IS TRUE
LIMIT 1
"""

_DDL = (
    "CREATE TABLE IF NOT EXISTS ponto_reaberturas ("
    " id serial PRIMARY KEY, employee_id varchar(50) NOT NULL, mes integer NOT NULL, ano integer NOT NULL,"
    " motivo text NOT NULL, quem varchar(120), espelhos integer NOT NULL DEFAULT 0,"
    " fechamentos integer NOT NULL DEFAULT 0, status_anterior text, created_at timestamptz DEFAULT now())",
    "CREATE INDEX IF NOT EXISTS ix_ponto_reaberturas_emp ON ponto_reaberturas (employee_id, ano, mes)",
)
_ensured = False


async def _ensure(db) -> None:
    global _ensured  # noqa: PLW0603 — uma vez por processo, como config_ponto
    if _ensured:
        return
    for stmt in _DDL:
        await db.execute(text(stmt))
    await db.commit()
    _ensured = True


def _dia(dia) -> date:
    if isinstance(dia, datetime):
        return dia.date()
    if isinstance(dia, date):
        return dia
    return datetime.fromisoformat(str(dia)[:19]).date()


def _msg(row, mes: int, ano: int) -> str:
    quando = row[2].strftime("%d/%m/%Y") if isinstance(row[2], datetime) else ""
    quem = f" por {row[1]}" if row[1] else ""
    return (
        f"Competência {mes:02d}/{ano} está FECHADA ({row[0]}{quem}{' em ' + quando if quando else ''}). "
        "Para lançar ou corrigir batida, reabra o mês com motivo (Ponto & Jornada → Reabrir mês)."
    )


def competencia_fechada_sync(db, employee_id, dia: date | datetime) -> str | None:
    """Session síncrona. Devolve a mensagem da trava ou None se a competência está aberta."""
    d = _dia(dia)
    row = db.execute(text(_SQL_FECHADO), {"e": str(employee_id), "m": d.month, "y": d.year}).first()
    return _msg(row, d.month, d.year) if row else None


async def competencia_fechada(db, employee_id, dia: date | datetime) -> str | None:
    """AsyncSession. Mesma pergunta."""
    d = _dia(dia)
    row = (await db.execute(text(_SQL_FECHADO), {"e": str(employee_id), "m": d.month, "y": d.year})).first()
    return _msg(row, d.month, d.year) if row else None


async def reabrir(db, employee_id: str, mes: int, ano: int, motivo: str, quem: str) -> dict:
    """Reabre a competência de UMA pessoa nos dois lugares, com motivo. Recusa espelho já ENVIADO à
    folha (mesma regra de `reopen_time_sheet`) e recusa quando não havia nada fechado."""
    await _ensure(db)
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise ValueError("Motivo obrigatório (mínimo 5 caracteres) — reabrir mês é ato com autor.")
    if not (1 <= int(mes) <= 12):
        raise ValueError("Mês inválido.")
    p = {"e": str(employee_id), "m": int(mes), "y": int(ano)}
    enviado = (
        await db.execute(
            text(
                "SELECT 1 FROM time_sheets WHERE employee_id=:e AND reference_month=:m AND reference_year=:y "
                "AND lower(coalesce(status,''))='enviado_folha'"
            ),
            p,
        )
    ).first()
    if enviado:
        raise ValueError("Espelho já ENVIADO à folha — não se reabre por aqui; corrija pela folha.")
    anterior = (
        await db.execute(
            text(
                "SELECT string_agg(DISTINCT status, ',') FROM time_sheets WHERE employee_id=:e "
                "AND reference_month=:m AND reference_year=:y"
            ),
            p,
        )
    ).scalar()
    nota = f"\n[Reaberta em {datetime.now().strftime('%d/%m/%Y %H:%M')} por {quem}] Motivo: {motivo}"
    espelhos = (
        await db.execute(
            text(
                "UPDATE time_sheets SET status='aberto', closed_at=NULL, closed_by_id=NULL, closed_by_name=NULL, "
                "approved_by_employee=false, approved_by_manager=false, approved_by_hr=false, "
                "internal_notes = coalesce(internal_notes,'') || :nota "
                "WHERE employee_id=:e AND reference_month=:m AND reference_year=:y "
                "AND lower(coalesce(status,'')) IN ('fechado','aprovado','revisado')"
            ),
            dict(p, nota=nota),
        )
    ).rowcount
    fechamentos = (
        await db.execute(
            text(
                "UPDATE gp_monthly_closings SET fechado=false, updated_at=now(), "
                "observacoes = coalesce(observacoes,'') || :nota "
                "WHERE employee_id=:e AND month=:m AND year=:y AND fechado IS TRUE"
            ),
            dict(p, nota=nota),
        )
    ).rowcount
    if not espelhos and not fechamentos:
        raise ValueError(f"Competência {int(mes):02d}/{int(ano)} desta pessoa não estava fechada — nada a reabrir.")
    rid = (
        await db.execute(
            text(
                "INSERT INTO ponto_reaberturas (employee_id, mes, ano, motivo, quem, espelhos, fechamentos, status_anterior) "
                "VALUES (:e, :m, :y, :motivo, :quem, :esp, :fec, :ant) RETURNING id"
            ),
            dict(p, motivo=motivo, quem=(quem or "")[:120], esp=espelhos, fec=fechamentos, ant=anterior),
        )
    ).scalar()
    await db.commit()
    return {"id": rid, "espelhos": espelhos, "fechamentos": fechamentos, "status_anterior": anterior}
