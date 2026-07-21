"""
redesign_builders/recrutamento.py — T4.
Sobrescreve _build_recrutamento: reusa a base e ADICIONA candidaturas. Só leitura.
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_recrutamento as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    initials,
    t,
)

SLUG = "recrutamento"


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Candidaturas (candidates — lista com origem/status) ----
    await safe("candidaturas", tbl(
        "Candidaturas", f"{await _scalar(db, 'SELECT count(*) FROM candidates WHERE is_active=true')} candidaturas ativas",
        "—", ["Candidato", "Cargo pretendido", "Origem", "Status", "Data"], "1.8fr 1.6fr 1fr 1fr 1fr",
        "SELECT name, coalesce(current_position, headline, '—'), coalesce(source,'—'), coalesce(status,'—'), created_at "
        "FROM candidates WHERE is_active=true ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), b((r[2] or '—').capitalize(), "mut"),
                   b((r[3] or '—').capitalize(), "info"), t(_fmtdate(r[4]))]))

    return out
