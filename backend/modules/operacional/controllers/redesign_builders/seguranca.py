"""
redesign_builders/seguranca.py — T4 (LGPD/segurança da informação).
Sobrescreve _build_seguranca: reusa a base e ADICIONA consentimento, mascaramento,
criptografia, direito ao esquecimento e PIA/DPIA. Só VISIBILIDADE (leitura).
Vazio real = "aguardando dado" — nunca fabricar.
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_seguranca as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    initials,
    t,
)

SLUG = "seguranca"


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Consentimento (candidate_consents — termos aceitos, real) ----
    await safe("consentimento", tbl(
        "Consentimento", f"{await _scalar(db, 'SELECT count(*) FROM candidate_consents WHERE aceito=true')} termos aceitos",
        "—", ["Titular", "CPF", "Versão do termo", "Aceito", "Data"], "1.8fr 1.2fr 1.2fr 0.8fr 1.2fr",
        "SELECT coalesce(nome,'—'), coalesce(cpf,'—'), coalesce(termo_versao,'—'), aceito, aceito_em "
        "FROM candidate_consents ORDER BY aceito_em DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]),
                   b("Sim", "ok") if r[3] else b("Não", "bad"), t(_fmtdate(r[4]))]))

    # ---- Mascaramento (política de mascaramento — audit LGPD; honesto se vazio) ----
    await safe("mascaramento", tbl(
        "Mascaramento", "Eventos de acesso a dados pessoais (trilha LGPD)",
        "—", ["Ação", "Recurso", "Severidade", "Usuário", "Data"], "1.2fr 1.2fr 1fr 1.2fr 1.2fr",
        "SELECT coalesce(action::text,'—'), coalesce(resource_type::text,'—'), coalesce(severity::text,'—'), coalesce(user_id,'—'), created_at "
        "FROM lgpd_audit_logs ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [b((r[0] or '—').replace('_', ' ').capitalize(), "info"), t((r[1] or '—').replace('_', ' ').capitalize(), 600, "#0F1B3A"),
                   b((r[2] or '—').capitalize(), "warn"), t(r[3]), t(_fmtdate(r[4]))]))

    # ---- Criptografia (trilha de auditoria de acesso — infra criptografada em repouso) ----
    await safe("criptografia", tbl(
        "Criptografia", "Trilha de integridade (hash encadeado dos eventos LGPD)",
        "—", ["Ação", "Recurso", "Hash do evento", "Data"], "1.2fr 1.2fr 2fr 1.2fr",
        "SELECT coalesce(action::text,'—'), coalesce(resource_type::text,'—'), coalesce(left(event_hash,24),'—'), created_at "
        "FROM lgpd_audit_logs WHERE event_hash IS NOT NULL ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [b((r[0] or '—').replace('_', ' ').capitalize(), "info"), t((r[1] or '—').capitalize()),
                   t(r[2], 500, "#0F1B3A"), t(_fmtdate(r[3]))]))

    # ---- Direito ao esquecimento (lgpd_erasure_requests) ----
    await safe("esquecimento", tbl(
        "Direito ao esquecimento", f"{await _scalar(db, 'SELECT count(*) FROM lgpd_erasure_requests')} solicitações",
        "—", ["Titular", "Escopo", "Status", "Prazo", "Solicitado"], "1.6fr 1fr 1fr 1.1fr 1.1fr",
        "SELECT coalesce(titular_email,'—'), coalesce(scope::text,'—'), coalesce(status::text,'—'), deadline_at, created_at "
        "FROM lgpd_erasure_requests ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').capitalize(), "info"),
                   b((r[2] or '—').capitalize(), "ok" if (r[2] or '').lower() in ("concluido", "concluído", "completed") else "warn"),
                   t(_fmtdate(r[3])), t(_fmtdate(r[4]))]))

    # ---- PIA / DPIA (lgpd_pia_assessments — honesto se vazio) ----
    await safe("pia-dpia", tbl(
        "PIA / DPIA", f"{await _scalar(db, 'SELECT count(*) FROM lgpd_pia_assessments')} avaliações de impacto (aguardando dado se vazio)",
        "—", ["Projeto", "Status", "Nível de risco", "Requer DPIA", "Criado"], "2fr 1fr 1fr 0.9fr 1.1fr",
        "SELECT coalesce(project_name,'—'), coalesce(status::text,'—'), coalesce(risk_level::text,'—'), requires_dpia, created_at "
        "FROM lgpd_pia_assessments ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').capitalize(), "info"),
                   b((r[2] or '—').capitalize(), "warn"), b("Sim", "warn") if r[3] else b("Não", "mut"), t(_fmtdate(r[4]))]))

    return out
