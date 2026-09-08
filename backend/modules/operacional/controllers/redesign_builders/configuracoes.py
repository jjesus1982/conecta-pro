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
    await _ligar_lote5_20260908(db, out)
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


async def _ligar_lote5_20260908(db, out: dict, me=None) -> None:
    """LIGAR lote 5 (08/09/2026): rotas do people-management/users/SST que só existiam por API. Blocos independentes."""
    import logging as _lg
    from datetime import date as _dt
    from sqlalchemy import text as _T
    from modules.operacional.controllers.redesign_data_controller import _helpers, t, b, brl
    from modules.operacional.controllers.redesign_builders._ligar_generico import chamar, painel_de_dict, selecionar, tabela_de_lista
    _log = _lg.getLogger(__name__)
    _, _safe, tbl = _helpers(db)
    _SN = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
    hoje = _dt.today()

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

    async def _emps():
        try:
            return [{"value": str(i), "label": n} for i, n in (await db.execute(_T("SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400"))).fetchall()]
        except Exception:  # noqa: BLE001
            await db.rollback(); return []

    def _consulta(key, titulo, sub, endpoint, fields, method="GET"):
        out[key] = {"title": titulo, "sub": sub, "cta": "Consultar", "type": "form",
                    "submit": {"endpoint": endpoint, "method": method, "query": True, "okMsg": "Consulta feita — veja o resultado.", "showResult": True},
                    "fields": fields}

    try:  # POST /users/{id}/aprovar · PATCH /users/{id}/activate|deactivate|permissions · (GET /users/pending por SQL)
        # main_production carrega users.py por spec_from_file_location("users"); `import api.v1.endpoints.users`
        # importaria o pacote api.v1 inteiro (27 s no 1º pedido de cada worker — QA E2E 08/09). Reusa o módulo carregado.
        import importlib.util as _ilu, sys as _sys
        _u = _sys.modules.get("users")
        if _u is None or not hasattr(_u, "PERFIS_APROVACAO"):
            _spec = _ilu.spec_from_file_location("users", "/app/api/v1/endpoints/users.py"); _u = _ilu.module_from_spec(_spec); _spec.loader.exec_module(_u)
        MODULOS_VALIDOS, PERFIS_APROVACAO = _u.MODULOS_VALIDOS, _u.PERFIS_APROVACAO
        emps = await _emps()
        perfis = [{"value": k, "label": v.get("label", k) + (" (só o CEO)" if v.get("somente_ceo") else "")} for k, v in PERFIS_APROVACAO.items()]
        mods = [{"value": m, "label": m.replace("module:", "").upper()} for m in sorted(MODULOS_VALIDOS)]

        def _acoes(r):
            uid, nome, role, ativo, perms = r[4], r[0], (r[2] or "").lower(), bool(r[3]), r[5] or []
            acts = []
            if role == "pending":
                acts.append({"title": f"Aprovar usuário — {nome}", "sub": "Aplica o preset do perfil (role + permissões + vínculo) em uma chamada.",
                             "endpoint": f"/api/v1/users/{uid}/aprovar", "method": "POST", "btnLabel": "Aprovar", "btnStyle": "primary", "submitLabel": "Aprovar",
                             "okMsg": "Usuário aprovado. Recarregue.",
                             "fields": [selecionar("perfil", "Perfil*", perfis, "span 1"), selecionar("employee_id", "Colaborador (obrigatório p/ funcionário e líder)", emps, "span 1")]})
            if ativo:
                acts.append({"title": f"Desativar — {nome}", "endpoint": f"/api/v1/users/{uid}/deactivate", "method": "PATCH", "btnLabel": "Desativar", "btnStyle": "danger",
                             "submitLabel": "Desativar", "confirm": f"Desativar o acesso de {nome}?", "okMsg": "Usuário desativado. Recarregue.", "fields": []})
            else:
                acts.append({"title": f"Ativar — {nome}", "endpoint": f"/api/v1/users/{uid}/activate", "method": "PATCH", "btnLabel": "Ativar", "btnStyle": "outline",
                             "submitLabel": "Ativar", "okMsg": "Usuário ativado. Recarregue.", "fields": []})
            acts.append({"title": f"Permissões por módulo — {nome}", "sub": "Só o CEO altera. Financeiro não entra por aqui (users.py MODULOS_VALIDOS).",
                         "endpoint": f"/api/v1/users/{uid}/permissions", "method": "PATCH", "btnLabel": "Permissões", "btnStyle": "outline", "submitLabel": "Salvar",
                         "okMsg": "Permissões atualizadas. Recarregue.",
                         "fields": [{"key": "permissions", "label": "Módulos", "type": "multiselect", "span": "span 2", "options": mods, "value": __import__("json").dumps([p for p in perms if p in MODULOS_VALIDOS])}]})
            return acts
        out["usuarios"] = await tbl(
            "Usuários", f"{await _n('SELECT count(*) FROM users')} usuários · aprovar pendentes, ativar/desativar e permissões por linha · fonte: users", "—",
            ["Usuário", "E-mail", "Perfil", "Status", "Módulos"], "1.6fr 1.8fr 1fr 0.8fr 1.4fr",
            "SELECT coalesce(name,'—'), coalesce(email,'—'), coalesce(role::text,'—'), coalesce(is_active,false), id::text, permissions "
            "FROM users ORDER BY (role::text='pending') DESC, name LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), b("Pendente" if (r[2] or "").lower() == "pending" else (r[2] or "—").replace("_", " ").capitalize(), "warn" if (r[2] or "").lower() == "pending" else "info"),
                       b("Ativo", "ok") if r[3] else b("Inativo", "mut"), t(", ".join(str(p).replace("module:", "") for p in (r[5] or []))[:60] or "—")],
            actionsfn=_acoes)
    except Exception as exc:  # noqa: BLE001
        await db.rollback(); _log.warning("usuarios lote5: %s", exc)
