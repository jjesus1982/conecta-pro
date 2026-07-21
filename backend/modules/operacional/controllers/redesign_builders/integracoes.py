"""Integrações (T1) — delega ao _build_integracoes e ESTENDE com logs (chamadas de
integração) e sync (histórico de sincronização Sólides). Leitura real."""
from modules.operacional.controllers.redesign_data_controller import (
    _build_integracoes, _helpers, b, t,
)

SLUG = "integracoes"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out = await _build_integracoes(db)  # base: visao, solides
    _, _safe, tbl = _helpers(db)

    # Logs de integração (chamadas HTTP) — integration_logs
    _lvl = {"error": "bad", "erro": "bad", "critical": "bad", "warn": "warn", "warning": "warn", "info": "info", "debug": "mut"}
    try:
        out["logs"] = await tbl(
            "Logs de integração", "Chamadas recentes (webhooks/API)", "—",
            ["Horário", "Método", "Path", "HTTP", "Nível"], "1fr 0.8fr 1.9fr 0.7fr 0.8fr",
            "SELECT to_char(created_at,'DD/MM HH24:MI'), coalesce(method,'—'), coalesce(path,'—'), response_status_code, coalesce(level::text,'—') "
            "FROM integration_logs ORDER BY created_at DESC LIMIT 200",
            lambda r: [t(r[0] or '—'), b(r[1] or '—', "info"), t((r[2] or '—')[:46]),
                       b(str(r[3]), "ok" if r[3] and 200 <= r[3] < 400 else "bad") if r[3] is not None else t("—"),
                       b((r[4] or '—').capitalize(), _lvl.get((r[4] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass

    # Histórico de sincronização Sólides — solides_sync_log
    _st = {"completed": "ok", "success": "ok", "concluido": "ok", "failed": "bad", "error": "bad", "partial": "warn", "running": "warn", "in_progress": "warn"}
    try:
        out["sync"] = await tbl(
            "Sincronizações (Sólides)", "Histórico de sync (RH/ponto)", "—",
            ["Entidade", "Tipo", "Direção", "Proc.", "Criados", "Atualiz.", "Falhas", "Status"],
            "1fr 0.9fr 1.5fr 0.7fr 0.7fr 0.7fr 0.7fr 0.9fr",
            "SELECT coalesce(entity_type::text,'—'), coalesce(sync_type::text,'—'), coalesce(direction::text,'—'), "
            "items_processed, items_created, items_updated, items_failed, coalesce(status::text,'—') "
            "FROM solides_sync_log ORDER BY started_at DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0] or '—', 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ')),
                       t((r[2] or '—').replace('solides_to_conecta', 'Sólides → Conecta').replace('conecta_to_solides', 'Conecta → Sólides').replace('_', ' ')),
                       t(str(int(r[3] or 0))), t(str(int(r[4] or 0))), t(str(int(r[5] or 0))),
                       b(str(int(r[6] or 0)), "bad" if (r[6] or 0) > 0 else "mut"),
                       b((r[7] or '—').capitalize(), _st.get((r[7] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass

    return out
