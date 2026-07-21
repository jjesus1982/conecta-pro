"""
redesign_builders/servicos.py — T4.
Sobrescreve _build_servicos: reusa a base e ADICIONA agendamentos e contratos.
Só leitura. Vazio real = "aguardando dado".
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_servicos as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    initials,
    t,
)

SLUG = "servicos"


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Agendamentos (diarist_schedules — honesto se vazio) ----
    await safe("agendamentos", tbl(
        "Agendamentos", f"{await _scalar(db, 'SELECT count(*) FROM diarist_schedules')} agendamentos (aguardando dado se vazio)",
        "—", ["Data", "Check-in", "Check-out", "Valor previsto", "Status"], "1fr 1fr 1fr 1.1fr 0.9fr",
        "SELECT data_trabalho, hora_inicio, hora_fim, valor_previsto, coalesce(status::text,'—') "
        "FROM diarist_schedules ORDER BY data_trabalho DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0]), 600, "#0F1B3A"), t(str(r[1]) if r[1] is not None else '—'),
                   t(str(r[2]) if r[2] is not None else '—'), t(brl(r[3]) if r[3] is not None else '—', 600),
                   b((r[4] or '—').capitalize(), "info")]))

    # ---- Contratos de serviço (contracts) ----
    await safe("contratos", tbl(
        "Contratos", f"{await _scalar(db, 'SELECT count(*) FROM contracts')} contratos",
        "—", ["Nº", "Contrato", "Mensal", "Status", "Início"], "1fr 2fr 1fr 0.9fr 1fr",
        "SELECT coalesce(contract_number,'—'), coalesce(name,'—'), monthly_value, coalesce(status::text,'—'), start_date "
        "FROM contracts ORDER BY start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]) if r[2] is not None else '—', 600),
                   b((r[3] or '—').capitalize(), "ok" if (r[3] or '').lower() in ("active", "ativo", "assinado", "signed") else "info"),
                   t(_fmtdate(r[4]))]))

    return out
