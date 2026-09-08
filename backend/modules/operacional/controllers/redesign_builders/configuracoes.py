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
    initials,
    t,
)

SLUG = "configuracoes"
EXTRA_MENU: list[dict] = [
    {"id": "notificacoes-fila-resumo", "label": "Notificações — resumo", "icon": "M3 3v18h18"},
    {"id": "notificacoes-fila", "label": "Notificações — fila", "icon": "M3 3v18h18"},
]
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


# Traduções — plano/status do tenant e nível de log
_PLANO = {"enterprise": "Enterprise", "professional": "Profissional", "pro": "Pro",
          "basic": "Básico", "starter": "Starter", "free": "Grátis", "trial": "Trial"}
_TENANT_ST = {"active": ("Ativo", "ok"), "ativo": ("Ativo", "ok"), "inactive": ("Inativo", "mut"),
              "suspended": ("Suspenso", "bad"), "trial": ("Trial", "warn"), "cancelled": ("Cancelado", "bad")}
_LEVEL = {"info": ("Info", "info"), "error": ("Erro", "bad"), "warning": ("Aviso", "warn"),
          "warn": ("Aviso", "warn"), "debug": ("Debug", "mut"), "critical": ("Crítico", "bad")}


def _plano(v):
    return _PLANO.get((v or "").lower(), (v or "—").replace("_", " ").capitalize())


def _tenant_status(v):
    lbl, tone = _TENANT_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


def _level(v):
    lbl, tone = _LEVEL.get((v or "").lower(), ((v or "—").capitalize(), "info"))
    return b(lbl, tone)


_ROLE = {"funcionario": "Funcionário", "staff": "Equipe", "developer": "Desenvolvedor",
         "gerente_operacional": "Gerente Operacional", "supervisor": "Supervisor", "user": "Usuário",
         "admin": "Administrador", "lider": "Líder", "suporte": "Suporte", "operator": "Operador",
         "all": "Todos", "gestor": "Gestor", "financeiro": "Financeiro", "rh": "RH"}


def _role(v):
    return _ROLE.get((v or "").lower(), (v or "—").replace("_", " ").capitalize())


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
    # Usuários — SOBRESCREVE a base (Perfil vinha cru em snake_case) → rótulo PT
    await safe("usuarios", tbl(
        "Usuários", "Usuários do sistema", "—",
        ["Usuário", "E-mail", "Perfil", "Status"], "1.6fr 1.8fr 1fr 0.9fr",
        "SELECT coalesce(name,'—'), coalesce(email,'—'), coalesce(role::text,'—'), is_active FROM users ORDER BY name LIMIT 300",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0] or '')), t(r[1]), t(_role(r[2])),
                   b("Ativo", "ok") if r[3] else b("Inativo", "mut")]))

    await safe("tenants", tbl(
        "Tenants", "Empresas / tenants", "—",
        ["Código", "Nome", "Documento", "Plano", "Status"],
        "1fr 1.8fr 1.2fr 1fr 0.9fr",
        "SELECT coalesce(codigo,'—'), coalesce(nome,'—'), coalesce(documento,'—'), "
        "coalesce(plano::text,'—'), coalesce(status::text,'—') FROM tenants "
        "WHERE coalesce(ativo,true) ORDER BY created_at DESC LIMIT 100",
        lambda r: [t(r[0], 600, _ND), t(r[1]), t(r[2]), t(_plano(r[3])), _tenant_status(r[4])]))

    # 2) Integrações — integration_logs (atividade real)
    await safe("integracoes", tbl(
        "Integrações", "Logs de integração", "—",
        ["Tipo", "Nível", "Método", "Caminho", "HTTP", "Quando"],
        "1fr 0.8fr 0.8fr 1.8fr 0.7fr 1.2fr",
        "SELECT coalesce(log_type::text,'—'), coalesce(level::text,'—'), coalesce(method::text,'—'), "
        "coalesce(path,'—'), coalesce(response_status_code::text,'—'), timestamp "
        "FROM integration_logs ORDER BY timestamp DESC NULLS LAST LIMIT 200",
        lambda r: [t((r[0] or "—").replace("_", " ").capitalize(), 600, _ND), _level(r[1]), t(r[2]), t((r[3] or "—")[:60]), t(r[4]), t(_d(r[5]))]))

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
        lambda r: [t(r[0] or "—", 600, _ND), t(_plano(r[1])), t(str(r[2])), t(str(r[3])), _tenant_status(r[4])]))

    # 6) Consultor — consultor_memorias
    await safe("consultor", tbl(
        "Consultor", "Memória do consultor IA", "—",
        ["Origem", "Conteúdo", "Fonte", "Quando"],
        "1fr 2.4fr 1fr 1.2fr",
        "SELECT coalesce(origem,'—'), coalesce(left(conteudo,110),'—'), coalesce(fonte,'—'), created_at "
        "FROM consultor_memorias WHERE coalesce(ativo,true) ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(r[2]), t(_d(r[3]))]))

    await _ligar_lote3_20260908(db, out)
    return out


async def _ligar_lote3_20260908(db, out: dict) -> None:
    """LIGAR lote 3 (08/09/2026): rotas que existiam sem tela. Cada bloco é independente (try/except + rollback)."""
    import logging as _lg
    from sqlalchemy import text as _T
    from modules.operacional.controllers.redesign_data_controller import _helpers, t, b, brl
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]

    def _fd(v, fmt="%d/%m/%Y"):
        try:
            return v.strftime(fmt) if v else "—"
        except Exception:  # noqa: BLE001
            return str(v or "—")

    async def _n(sql):
        try:
            return (await db.execute(_T(sql))).scalar() or 0
        except Exception:  # noqa: BLE001
            await db.rollback(); return 0

    try:  # GET /notifications/queue + /queue/stats (por SQL)
        st = (await db.execute(_T("SELECT status::text, channel_type, count(*) FROM notification_queue GROUP BY 1,2 ORDER BY 3 DESC"))).fetchall()
        tot = sum(r[2] for r in st)
        painel = {"total": tot, "entregues": sum(r[2] for r in st if r[0] == "delivered"), "pendentes": sum(r[2] for r in st if r[0] == "pending"),
                  "expiradas": sum(r[2] for r in st if r[0] == "expired"), "falhas": sum(r[2] for r in st if r[0] in ("failed", "error")),
                  "por_status_e_canal": [{"status": r[0], "canal": r[1], "qtde": r[2]} for r in st]}
        out["notificacoes-fila-resumo"] = painel_de_dict("Fila de notificações — resumo", "Push/e-mail/WhatsApp enfileirados pelo sistema (sino, SST, alertas) · fonte: notification_queue", painel, kpis_de=["total", "entregues", "pendentes", "expiradas"])
        out["notificacoes-fila"] = await tbl(
            "Fila de notificações", f"{tot} item(ns) · últimos 200 · fonte: notification_queue", "—",
            ["Destinatário", "Canal", "Assunto", "Status", "Agendada", "Enviada", "Erro"], "1.4fr 0.7fr 2fr 0.8fr 0.9fr 0.9fr 1.2fr",
            "SELECT coalesce(recipient_name, recipient_address, '—'), coalesce(channel_type,'—'), coalesce(subject, left(body, 60), '—'), status::text, scheduled_at, sent_at, coalesce(last_error,'') "
            "FROM notification_queue ORDER BY coalesce(scheduled_at, created_at) DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0][:36], 600, "#0F1B3A"), t(r[1]), t(r[2][:60]), b(r[3].capitalize(), "ok" if r[3] == "delivered" else "warn" if r[3] == "pending" else "bad" if r[3] in ("failed", "error") else "mut"),
                       t(_fd(r[4], "%d/%m %H:%M")), t(_fd(r[5], "%d/%m %H:%M")), t(r[6][:40] or "—")])
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("notificacoes-fila: %s", exc)
