"""Redesign builder — Configurações.

Estende `_build_configuracoes` (base: visao, usuarios) e liga as 6 telas sem
wiring com dado REAL: tenants (empresas/tenants), integrações (integration_logs),
templates de notificação, feature flags, config de sistema (limites/uso por
tenant) e o consultor (consultor_memorias). Tabelas vazias = 0 honesto.
"""

from modules.operacional.controllers.redesign_data_controller import (
    _build_configuracoes,
    _helpers,
    b,
    t,
)

SLUG = "configuracoes"
EXTRA_MENU: list[dict] = []
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y %H:%M"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "ativa", "habilitado", "enabled", "on", "success", "2xx", "producao"):
        return b(v or "—", "ok")
    if s in ("pendente", "trial", "rascunho", "gradual", "canary", "warning", "pausado"):
        return b(v or "—", "warn")
    if s in ("inativo", "cancelado", "suspenso", "desabilitado", "disabled", "error", "erro", "off", "5xx", "4xx"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


async def build(db) -> dict:
    out = await _build_configuracoes(db)
    _o2, _s2, tbl = _helpers(db)

    async def safe(key, coro):
        try:
            out[key] = await coro
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    # 1) Tenants — tenants
    await safe("tenants", tbl(
        "Tenants", "Empresas / tenants", "—",
        ["Código", "Nome", "Documento", "Plano", "Status"],
        "1fr 1.8fr 1.2fr 1fr 0.9fr",
        "SELECT coalesce(codigo,'—'), coalesce(nome,'—'), coalesce(documento,'—'), "
        "coalesce(plano::text,'—'), coalesce(status::text,'—') FROM tenants "
        "WHERE coalesce(ativo,true) ORDER BY created_at DESC LIMIT 100",
        lambda r: [t(r[0], 600, _ND), t(r[1]), t(r[2]), t((r[3] or "—").replace("_", " ")), _bs(r[4])]))

    # 2) Integrações — integration_logs (atividade real)
    await safe("integracoes", tbl(
        "Integrações", "Logs de integração", "—",
        ["Tipo", "Nível", "Método", "Caminho", "HTTP", "Quando"],
        "1fr 0.8fr 0.8fr 1.8fr 0.7fr 1.2fr",
        "SELECT coalesce(log_type::text,'—'), coalesce(level::text,'—'), coalesce(method::text,'—'), "
        "coalesce(path,'—'), coalesce(response_status_code::text,'—'), timestamp "
        "FROM integration_logs ORDER BY timestamp DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, _ND), _bs(r[1]), t(r[2]), t((r[3] or "—")[:60]), t(r[4]), t(_d(r[5]))]))

    # 3) Templates de notificação — ai_email_templates
    await safe("templates-notificacao", tbl(
        "Templates de notificação", "Modelos de mensagem", "—",
        ["Nome", "Código", "Categoria", "Assunto", "Ativo"],
        "1.4fr 1fr 1fr 1.8fr 0.7fr",
        "SELECT coalesce(name,'—'), coalesce(code,'—'), coalesce(category::text,'—'), "
        "coalesce(subject_template,'—'), coalesce(is_active,false) FROM ai_email_templates "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t((r[2] or "—").replace("_", " ")),
                   t((r[3] or "—")[:60]), (b("Ativo", "ok") if r[4] else b("—", "mut"))]))

    # 4) Feature flags — feature_flags
    await safe("feature-flags", tbl(
        "Feature flags", "Flags de funcionalidade", "—",
        ["Código", "Nome", "Tipo", "Estratégia", "Status"],
        "1.2fr 1.6fr 1fr 1fr 0.9fr",
        "SELECT coalesce(codigo,'—'), coalesce(nome,'—'), coalesce(tipo::text,'—'), "
        "coalesce(estrategia::text,'—'), coalesce(status::text,'—') FROM feature_flags "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t((r[2] or "—").replace("_", " ")),
                   t((r[3] or "—").replace("_", " ")), _bs(r[4])]))

    # 5) Configurações de sistema — limites/uso por tenant
    await safe("configuracoes-sistema", tbl(
        "Configurações de sistema", "Limites e uso por tenant", "—",
        ["Tenant", "Plano", "Usuários ativos", "Limite usuários", "Status"],
        "1.8fr 1fr 1fr 1fr 0.9fr",
        "SELECT coalesce(nome,'—'), coalesce(plano::text,'—'), coalesce(uso_usuarios_ativos,0), "
        "coalesce(limite_usuarios,0), coalesce(status::text,'—') FROM tenants "
        "ORDER BY created_at DESC LIMIT 100",
        lambda r: [t(r[0] or "—", 600, _ND), t((r[1] or "—").replace("_", " ")), t(str(r[2])), t(str(r[3])), _bs(r[4])]))

    # 6) Consultor — consultor_memorias
    await safe("consultor", tbl(
        "Consultor", "Memória do consultor IA", "—",
        ["Origem", "Conteúdo", "Fonte", "Quando"],
        "1fr 2.4fr 1fr 1.2fr",
        "SELECT coalesce(origem,'—'), coalesce(left(conteudo,110),'—'), coalesce(fonte,'—'), created_at "
        "FROM consultor_memorias WHERE coalesce(ativo,true) ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(r[2]), t(_d(r[3]))]))

    return out
