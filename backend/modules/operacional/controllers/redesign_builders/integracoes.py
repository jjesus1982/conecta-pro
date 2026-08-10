"""Integrações (T1) — delega ao _build_integracoes e ESTENDE com logs (chamadas de
integração) e sync (histórico de sincronização Sólides). Leitura real."""
from datetime import date

from modules.operacional.controllers.redesign_data_controller import (
    _build_integracoes, _helpers, b, t,
)

SLUG = "integracoes"
_ICO_I = "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"

EXTRA_MENU: list[dict] = [
    {"id": "onvio-reclassificar", "label": "Reclassificar (Onvio)", "icon": _ICO_I},
    {"id": "solides-sincronizar", "label": "Sincronizar ponto (Sólides)", "icon": _ICO_I},
    {"id": "drive-conectar", "label": "Conectar Google Drive", "icon": _ICO_I},
    {"id": "drive-desconectar", "label": "Desconectar Google Drive", "icon": _ICO_I},
    {"id": "onvio-extrair", "label": "Extrair valores (Onvio)", "icon": _ICO_I},
    {"id": "solides-vincular-kits", "label": "Vincular benefícios aos kits", "icon": _ICO_I},
]


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

    # Fio solto (2026-08-10): a reclassificação do Onvio existia no backend sem botão.
    out["onvio-reclassificar"] = {
        "title": "Reclassificar lançamentos (Onvio)",
        "sub": "Reprocessa a classificação contábil dos lançamentos importados do Onvio. "
               "Não apaga lançamento — só reclassifica.",
        "cta": "Reclassificar", "type": "form",
        "submit": {"endpoint": "/api/v1/onvio/reclassificar", "okMsg": "Reclassificação disparada"},
        "fields": [],
    }
    out["solides-sincronizar"] = {
        "title": "Sincronizar ponto com o Sólides Tangerino",
        "sub": "Puxa as batidas do Sólides para o ERP. Só LÊ do Sólides — não escreve lá.",
        "cta": "Sincronizar agora", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/ponto/sincronizar-solides",
                   "okMsg": "Sincronização de ponto disparada"},
        "fields": [],
    }
    out["drive-conectar"] = {
        "title": "Conectar Google Drive",
        "sub": "Inicia a conexão usada pelo GED para guardar e buscar os kits.",
        "cta": "Conectar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/ged/config/drive/connect",
                   "okMsg": "Conexão com o Drive iniciada"},
        "fields": [],
    }
    out["drive-desconectar"] = {
        "title": "Desconectar Google Drive",
        "sub": "Encerra a conexão. O GED para de guardar e buscar kits no Drive até reconectar.",
        "cta": "Desconectar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/ged/config/drive/disconnect",
                   "method": "DELETE", "okMsg": "Google Drive desconectado",
                   "confirm": "Desconectar o Drive interrompe o GED de guardar e buscar kits. Confirma?"},
        "fields": [],
    }
    # Query fixa no endpoint (padrão já usado no financeiro): rota que lê QUERY funciona
    # sem tela de campo quando o valor é derivável. Ver nota longa em documentos.py.
    _h = date.today()
    out["onvio-extrair"] = {
        "title": "Extrair valores dos documentos (Onvio)",
        "sub": "Lê os documentos importados e extrai os valores. Só processa o que ainda não "
               "foi extraído — rodar de novo não refaz o que já saiu.",
        "cta": "Extrair", "type": "form",
        "submit": {"endpoint": "/api/v1/onvio/extrair-valores", "okMsg": "Extração disparada"},
        "fields": [],
    }
    out["solides-vincular-kits"] = {
        "title": f"Vincular benefícios aos kits — {_h.month:02d}/{_h.year}",
        "sub": "Liga os benefícios do Sólides aos kits da competência corrente (VT/VR).",
        "cta": "Vincular", "type": "form",
        "submit": {"endpoint": f"/api/v1/integrations/solides/beneficios/vincular-kits?mes_ref={_h.month:02d}.{_h.year}",
                   "okMsg": "Vinculação disparada"},
        "fields": [],
    }

    return out
