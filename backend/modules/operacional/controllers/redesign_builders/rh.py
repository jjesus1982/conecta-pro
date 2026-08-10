"""Redesign builder — RH (recrutamento, treinamento, carreira, clima, IA).

Estende o `_build_rh` do monólito (base: dashboard, candidatos, entrevistas,
certificados) e liga as 10 telas sem wiring, lendo SEMPRE tabelas REAIS.
Telas com tabela conceitualmente certa porém vazia devolvem 0 linhas honestas
("sem registro"), nunca mock.
"""

from modules.operacional.controllers.redesign_data_controller import (
    _build_rh,
    _helpers,
    b,
    brl,
    initials,
    t,
)

SLUG = "rh"
_ICO_CCT = "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"

EXTRA_MENU: list[dict] = [
    # CCT SINDECOMPRESTS AM000613/2025 — as 6 calculadoras existiam no backend sem tela.
    {"id": "cct-hora-extra", "label": "CCT — Hora extra", "icon": _ICO_CCT},
    {"id": "cct-noturno", "label": "CCT — Adicional noturno", "icon": _ICO_CCT},
    {"id": "cct-decimo-terceiro", "label": "CCT — 13º salário", "icon": _ICO_CCT},
    {"id": "cct-validar-salario", "label": "CCT — Validar salário", "icon": _ICO_CCT},
    {"id": "cct-auditar-salario", "label": "CCT — Auditar salário", "icon": _ICO_CCT},
    {"id": "cct-reajuste", "label": "CCT — Reajuste", "icon": _ICO_CCT},
    {"id": "consultor-perguntar", "label": "Consultor de RH", "icon": _ICO_CCT},
    {"id": "cct-invalidar-cache", "label": "CCT — Limpar cache", "icon": _ICO_CCT},
    # Apoio à DECISÃO disciplinar — consultivo: nenhuma destas cria, aprova ou aplica medida.
    {"id": "disc-recomendar", "label": "Disciplinar — recomendar medida", "icon": _ICO_CCT},
    {"id": "disc-conformidade", "label": "Disciplinar — conformidade CLT", "icon": _ICO_CCT},
    {"id": "disc-proporcionalidade", "label": "Disciplinar — proporcionalidade", "icon": _ICO_CCT},
    {"id": "consultor-arquivo", "label": "Consultor de RH — com anexo", "icon": _ICO_CCT},
    {"id": "curriculo-texto", "label": "Analisar currículo (texto)", "icon": _ICO_CCT},
    {"id": "curriculo-arquivo", "label": "Analisar currículo (PDF/DOCX)", "icon": _ICO_CCT},
    {"id": "disc-medidas", "label": "Medidas disciplinares", "icon": _ICO_CCT},
    {"id": "disc-nova", "label": "Nova medida disciplinar", "icon": _ICO_CCT},
    {"id": "disc-templates", "label": "Modelos de medida", "icon": _ICO_CCT},
    {"id": "disc-template-novo", "label": "Novo modelo de medida", "icon": _ICO_CCT},
    {"id": "disc-verificar-assinatura", "label": "Verificar assinatura", "icon": _ICO_CCT},
    {"id": "cct-convencoes", "label": "CCT — convencoes e feriados", "icon": _ICO_CCT},
]

_MOTIVO = [{"value": v, "label": lbl} for v, lbl in (
    ("falta", "Falta"), ("atraso", "Atraso"), ("insubordinacao", "Insubordinação"),
    ("indisciplina", "Indisciplina"), ("dano_patrimonio", "Dano ao patrimônio"),
    ("negligencia", "Negligência"), ("embriaguez", "Embriaguez"),
    ("abandono_emprego", "Abandono de emprego"), ("ato_improbidade", "Ato de improbidade"),
    ("violacao_segredo", "Violação de segredo"))]
_MEDIDA = [{"value": v, "label": lbl} for v, lbl in (
    ("advertencia_verbal", "Advertência verbal"), ("advertencia_escrita", "Advertência escrita"),
    ("suspensao", "Suspensão"), ("demissao_justa_causa", "Demissão por justa causa"))]

# 12x36 e a jornada real dos agentes de portaria — nasce selecionada como padrao do campo.
_JORNADAS = [{"value": "12x36", "label": "12x36 (agentes de portaria)"},
             {"value": "44h", "label": "44h semanais"},
             {"value": "40h", "label": "40h semanais"}]
_SIM_NAO = [{"value": "false", "label": "Não"}, {"value": "true", "label": "Sim"}]
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


_TR_ST = {"scheduled": ("Agendado", "info"), "completed": ("Concluído", "ok"),
          "in_progress": ("Em andamento", "warn"), "cancelled": ("Cancelado", "mut"),
          "canceled": ("Cancelado", "mut"), "confirmed": ("Confirmado", "ok")}


def _tr_status(v):
    lbl, tone = _TR_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Admissão/Onboarding — espelha statusConfig do clássico (dp/admissao/page.tsx)
_ADM_ST = {"documents_pending": ("Documentos Pendentes", "warn"), "medical_exam": ("Exame Médico", "info"),
           "contract_signing": ("Assinatura de Contrato", "warn"), "in_progress": ("Em Andamento", "info"),
           "completed": ("Concluída", "ok"), "cancelled": ("Cancelada", "mut")}


def _adm_status(v):
    lbl, tone = _ADM_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


# Cursos — espelha categoryLabels do clássico (rh/cursos/page.tsx, sem acento p/ fidelidade)
_CURSO_CAT = {"mandatory_security": "Obrigatorio Seguranca", "mandatory_safety": "Obrigatorio SST",
              "technical": "Tecnico", "behavioral": "Comportamental", "leadership": "Lideranca",
              "compliance": "Compliance", "onboarding": "Integracao", "other": "Outros"}


def _curso_cat(v):
    return _CURSO_CAT.get((v or "").lower(), v or "—")


# Avaliações — espelha statusLabels + tipos do clássico (rh/avaliacoes/page.tsx)
_AVAL_ST = {"draft": ("Rascunho", "mut"), "self_assessment": ("Auto-Avaliação", "info"),
            "manager_review": ("Revisão Gestor", "warn"), "completed": ("Concluída", "ok"),
            "in_progress": ("Em Andamento", "warn")}
_AVAL_TIPO = {"annual": "Anual", "quarterly": "Trimestral", "semiannual": "Semestral",
              "monthly": "Mensal", "probation": "Experiência"}


def _aval_status(v):
    lbl, tone = _AVAL_ST.get((v or "").lower(), (v or "—", "info"))
    return b(lbl, tone)


_CAREER_ST = {"active": ("Ativo", "ok"), "completed": ("Concluído", "ok"),
              "in_progress": ("Em andamento", "warn"), "paused": ("Pausado", "warn"),
              "cancelled": ("Cancelado", "bad")}
_AREA = {"rh": "RH", "operacional": "Operacional", "folha": "Folha", "financeiro": "Financeiro",
         "beneficios_sst": "Benefícios/SST", "juridico": "Jurídico", "fiscal": "Fiscal", "dp": "DP"}


def _career_status(v):
    lbl, tone = _CAREER_ST.get((v or "").lower(), ((v or "—").capitalize(), "info"))
    return b(lbl, tone)


def _area(v):
    return _AREA.get((v or "").lower(), (v or "—").replace("_", " ").capitalize())


def _bs(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "concluido", "concluida", "aprovado", "hired",
             "contratado", "publicado", "published", "aberto", "open"):
        return b(v or "—", "ok")
    if s in ("pendente", "em_andamento", "aguardando", "screened", "interviewed",
             "offered", "rascunho", "draft", "pausado", "andamento"):
        return b(v or "—", "warn")
    if s in ("rejeitado", "reprovado", "cancelado", "rejected", "withdrawn", "fechado", "closed"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


def _bb(v, sim="Sim", nao="Não", ts="ok", tn="mut"):
    return b(sim, ts) if v else b(nao, tn)


async def build(db) -> dict:
    out = await _build_rh(db)
    _o2, _s2, tbl = _helpers(db)

    async def safe(key, coro):
        try:
            out[key] = await coro
        except Exception:
            try:
                await db.rollback()
            except Exception:
                pass

    # 1) Vagas — job_positions
    await safe("vagas", tbl(
        "Vagas", "Posições abertas", "Nova vaga",
        ["Vaga", "Departamento", "Nível", "Vagas", "Status"],
        "2fr 1.3fr 1fr 0.7fr 0.9fr",
        "SELECT coalesce(title,'—'), coalesce(department,'—'), coalesce(position_level,'—'), "
        "coalesce(vacancies,0), coalesce(status,'—') FROM job_positions "
        "WHERE coalesce(is_deleted,false)=false ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(r[2]), t(str(r[3])), _bs(r[4])]))

    # 2) Candidaturas — applications (real; hoje 0 = honesto "sem candidatura")
    await safe("candidaturas", tbl(
        "Candidaturas", "Aplicações às vagas", "—",
        ["Candidato", "Etapa", "Ordem", "Rating", "Aplicada", "Status"],
        "1.6fr 1.3fr 0.6fr 0.6fr 1fr 0.9fr",
        "SELECT coalesce(nullif(trim(c.name),''),'aguardando dado'), "
        "coalesce(a.current_step,'—'), coalesce(a.step_order,0), coalesce(a.rating,0), "
        "a.applied_at, coalesce(a.status,'—') "
        "FROM applications a LEFT JOIN candidates c ON c.id = a.candidate_id "
        "WHERE coalesce(a.is_active,true) "
        "ORDER BY a.applied_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], w=600, tc='#0f172a'), t(r[1]), t(str(r[2])), t(str(r[3])), t(_d(r[4])), _bs(r[5])]))

    # 3) Onboarding — MESMA fonte do clássico (/onboarding/dashboard): colaboradores em período
    #    de experiência (admitidos há até 90 dias, ativos). O endpoint clássico NÃO popula
    #    progresso/etapas (vêm 0) — não fabrico barra; mostro o dado real (admissão + dias na empresa).
    await safe("onboarding", tbl(
        "Onboarding", "Colaboradores em período de experiência (admitidos há até 90 dias)", "—",
        ["Colaborador", "Cargo", "Data Admissão", "Dias na empresa"],
        "2fr 1.6fr 1fr 1fr",
        "SELECT nome, coalesce(cargo,'—'), data_admissao, (CURRENT_DATE - data_admissao) AS dias "
        "FROM employees WHERE data_admissao >= CURRENT_DATE - INTERVAL '90 days' AND status='ativo' "
        "ORDER BY data_admissao DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(_d(r[2])),
                   t(f"{int(r[3])} dias" if r[3] is not None else "—")]))

    # 4) Treinamentos — trainings (real; 0 = honesto)
    await safe("treinamentos", tbl(
        "Treinamentos", "Turmas de treinamento — local, instrutor e vagas", "—",
        ["Treinamento", "Início", "Fim", "Local", "Instrutor", "Vagas", "Status"],
        "1.9fr 0.9fr 0.9fr 1.4fr 1.2fr 0.7fr 0.9fr",
        "SELECT coalesce(title,'—'), start_date, end_date, coalesce(location,'—'), "
        "coalesce(instructor_name,'—'), coalesce(current_participants,0), coalesce(max_participants,0), "
        "coalesce(status::text,'—') FROM trainings ORDER BY start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(_d(r[1])), t(_d(r[2])), t(r[3]), t(r[4]),
                   t(f"{r[5]}/{r[6]}"), _tr_status(r[7])]))

    # 5) Cursos — training_courses (real; 0 = honesto)
    await safe("cursos", tbl(
        "Cursos", "Catálogo de cursos", "—",
        ["Curso", "Categoria", "Carga (h)", "Obrigatório", "Provedor"],
        "2fr 1.2fr 0.8fr 1fr 1.2fr",
        "SELECT coalesce(name,'—'), coalesce(category::text,'—'), coalesce(duration_hours,0), "
        "coalesce(is_mandatory,false), coalesce(provider,'—') FROM training_courses "
        "WHERE coalesce(is_active,true) ORDER BY name LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(_curso_cat(r[1])), t(str(r[2])), _bb(r[3], "Sim", "Não", "warn", "mut"), t(r[4])]))

    # 6) Avaliações — operacional_avaliacoes_equipe
    # MESMA fonte do clássico (/human-resources/performance/reviews = performance_reviews), NÃO
    # operacional_avaliacoes_equipe (tabela operacional). Colunas iguais: Colaborador/Avaliador/Tipo/Score/Status.
    await safe("avaliacoes", tbl(
        "Avaliações", "Avaliações de desempenho (RH)", "—",
        ["Colaborador", "Avaliador", "Tipo", "Score", "Status"],
        "1.8fr 1.6fr 1fr 0.8fr 1fr",
        "SELECT emp.nome, rev.nome, pr.type::text, coalesce(pr.calibrated_score, pr.overall_score), pr.status::text "
        "FROM performance_reviews pr "
        "LEFT JOIN employees emp ON emp.id::text = pr.employee_id::text "
        "LEFT JOIN employees rev ON rev.id::text = pr.reviewer_id::text "
        "ORDER BY pr.created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1] or "—"),
                   t(_AVAL_TIPO.get((r[2] or "").lower(), (r[2] or "—").capitalize())),
                   t(f"{float(r[3]):.1f}" if r[3] is not None else "—", 600),
                   _aval_status(r[4])]))

    # 7) Carreira — career_plans (real; 0 = honesto)
    await safe("carreira", tbl(
        "Carreira", "Planos de carreira", "—",
        ["Colaborador", "Posição atual", "Alvo", "Prazo (m)", "Status"],
        "1.6fr 1.4fr 1.4fr 0.8fr 0.9fr",
        "SELECT coalesce(e.nome, c.employee_id::text), coalesce(c.current_position,'—'), "
        "coalesce(c.target_position,'—'), coalesce(c.estimated_timeline_months,0), coalesce(c.status::text,'—') "
        "FROM career_plans c LEFT JOIN employees e ON e.id::text = c.employee_id::text "
        "ORDER BY c.created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(r[2]), t(str(r[3])), _career_status(r[4])]))

    # 8) Clima — climate_surveys (real; 0 = honesto)
    await safe("clima", tbl(
        "Clima", "Pesquisas de clima", "—",
        ["Pesquisa", "Frequência", "Respostas", "Score médio", "Ativo"],
        "2fr 1fr 0.9fr 1fr 0.8fr",
        "SELECT coalesce(nome,'—'), coalesce(frequencia,'—'), coalesce(total_respostas,0), "
        "coalesce(score_medio,0), coalesce(ativo,false) FROM climate_surveys "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(str(r[2])), t("n/d" if (r[2] or 0)==0 else f"{float(r[3]):.1f}", 500, "#94A3B8" if (r[2] or 0)==0 else "#334155"), _bb(r[4], "Ativo", "—", "ok", "mut")]))

    # 9) Turnover — turnover_audit_logs
    # MESMA base do clássico (/human-resources/turnover/dashboard = employees): o dashboard NÃO
    # entrega predições por colaborador (tabela de risco vazia no clássico). O dado real de turnover
    # são os DESLIGAMENTOS + motivo; motivo nulo = data_gap honesto ("aguardando dado"), não fabrico.
    await safe("turnover", tbl(
        "Turnover", "Desligamentos recentes — o motivo alimenta a análise de causas", "—",
        ["Colaborador", "Cargo", "Data Desligamento", "Motivo"],
        "2fr 1.5fr 1.2fr 1.6fr",
        "SELECT nome, coalesce(cargo,'—'), data_demissao, "
        "nullif(trim(coalesce(motivo_desligamento,'')),'') AS motivo "
        "FROM employees WHERE data_demissao IS NOT NULL ORDER BY data_demissao DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(_d(r[2])),
                   t(r[3] or "aguardando dado", 500, "#334155" if r[3] else "#94A3B8")]))

    # 9b) Registrar motivo de desligamento (ESCRITA real → POST /human-resources/turnover/registrar-motivo)
    #     Fecha o data_gap do turnover: o RH informa o motivo REAL (vocabulário CLT). Não fabrica.
    try:
        from sqlalchemy import text as _sqltext
        from modules.people_management.human_resources.controllers.turnover_controller import (
            MOTIVOS_DESLIGAMENTO as _MOT,
        )
        _desl = (await db.execute(_sqltext(
            "SELECT CAST(id AS TEXT), nome, coalesce(cargo,'—'), to_char(data_demissao,'DD/MM/YYYY') "
            "FROM employees WHERE data_demissao IS NOT NULL "
            "AND nullif(trim(coalesce(motivo_desligamento,'')),'') IS NULL "
            "ORDER BY data_demissao DESC"
        ))).all()
        _opts = [{"value": r[0], "label": f"{r[1]} · {r[2]} · desl. {r[3]}"} for r in _desl]
        _sub = (f"{len(_opts)} desligado(s) aguardando motivo — informe a causa real (alimenta a análise)"
                if _opts else "Todos os desligados já têm motivo informado. ✓")
        out["registrar-motivo-desligamento"] = {
            "title": "Registrar motivo de desligamento",
            "sub": _sub, "cta": "Registrar", "type": "form",
            "submit": {"endpoint": "/api/v1/people-management/human-resources/turnover/registrar-motivo",
                       "okMsg": "Motivo registrado"},
            "fields": [
                {"key": "employee_id", "label": "Colaborador desligado*", "type": "select",
                 "span": "span 2", "ph": "Selecione o desligado", "options": _opts},
                {"key": "motivo", "label": "Motivo (CLT)*", "type": "select", "span": "span 2",
                 "ph": "Selecione o motivo", "options": [{"value": k, "label": v} for k, v in _MOT.items()]},
                {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2",
                 "ph": "Opcional — detalhe da rescisão"},
            ],
        }
    except Exception:
        try:
            await db.rollback()
        except Exception:
            pass

    # 10) RH IA — rh_consultas
    await safe("ia", tbl(
        "RH IA", "Consultas ao assistente de RH", "—",
        ["Área", "Competência", "Pergunta", "Escalonar", "Data"],
        "1fr 0.9fr 2fr 0.8fr 1fr",
        "SELECT coalesce(area,'—'), coalesce(competencia,'—'), coalesce(pergunta,'—'), "
        "coalesce(escalonar,false), created_at FROM rh_consultas ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(_area(r[0]), 600, _ND), t(r[1]), t((r[2] or "—")[:90]), _bb(r[3], "Sim", "Não", "bad", "ok"), t(_d(r[4]))]))

    # ── CCT SINDECOMPRESTS AM000613/2025 — 6 calculadoras sem tela (2026-08-10) ──────
    # O backend calculava hora extra, adicional noturno com hora reduzida (52min30s), 13o,
    # piso e reajuste; nada disso tinha superficie. Sao a base da folha e o Portte era a
    # unica forma de conferir. Contratos por introspecao dos schemas, nao adivinhados.
    #
    # TODAS levam showResult: o numero E o produto. Sem a flag a tela diria "Calculado" e
    # jogaria fora o valor — o defeito que o QA do fiscal achou. Ate o front subir a chave
    # e ignorada, entao ja nasce certo.
    #
    # NENHUMA move dinheiro nem escreve folha: sao calculo puro. A unica que grava e
    # 'auditar', que registra o resultado da auditoria — e esta marcada como tal.
    out["cct-hora-extra"] = {
        "title": "CCT — Calcular hora extra",
        "sub": "50% em dia normal, 100% em feriado. Inclui intrajornada não concedida.",
        "cta": "Calcular", "type": "form",
        "submit": {"endpoint": "/api/v1/cct/jornadas/hora-extra", "okMsg": "Hora extra calculada",
                   "showResult": True},
        "fields": [
            {"key": "salario_base", "label": "Salário base (R$)*", "type": "number", "span": "span 1",
             "ph": "1670.00"},
            {"key": "jornada_tipo", "label": "Jornada", "type": "select", "span": "span 1",
             "ph": "12x36 (padrão)", "options": _JORNADAS},
            {"key": "horas_extras_normais", "label": "Horas extras — dia normal", "type": "number",
             "span": "span 1", "ph": "0"},
            {"key": "horas_extras_feriado", "label": "Horas extras — feriado", "type": "number",
             "span": "span 1", "ph": "0"},
            {"key": "intrajornada_nao_concedida", "label": "Intrajornada não concedida?",
             "type": "select", "span": "span 2", "ph": "Não", "options": _SIM_NAO},
        ],
    }
    out["cct-noturno"] = {
        "title": "CCT — Calcular adicional noturno",
        "sub": "Hora noturna reduzida (52min30s) no período 22h–05h, como manda a CCT.",
        "cta": "Calcular", "type": "form",
        "submit": {"endpoint": "/api/v1/cct/jornadas/adicional-noturno",
                   "okMsg": "Adicional noturno calculado", "showResult": True},
        "fields": [
            {"key": "salario_base", "label": "Salário base (R$)*", "type": "number", "span": "span 1",
             "ph": "1670.00"},
            {"key": "jornada_tipo", "label": "Jornada", "type": "select", "span": "span 1",
             "ph": "12x36 (padrão)", "options": _JORNADAS},
            {"key": "horas_noturnas", "label": "Horas no período noturno (22h–05h)*", "type": "number",
             "span": "span 2", "ph": "Ex.: 56"},
        ],
    }
    out["cct-decimo-terceiro"] = {
        "title": "CCT — Calcular 13º salário",
        "sub": "Integral e proporcional, com as duas parcelas e o prazo da segunda (20/dez).",
        "cta": "Calcular", "type": "form",
        "submit": {"endpoint": "/api/v1/cct/rescisao/decimo-terceiro", "okMsg": "13º calculado",
                   "showResult": True},
        "fields": [
            {"key": "salario_base", "label": "Salário base (R$)*", "type": "number", "span": "span 1",
             "ph": "1670.00"},
            {"key": "meses_trabalhados", "label": "Meses trabalhados* (1 a 12)", "type": "number",
             "span": "span 1", "ph": "12"},
            {"key": "adicionais_mensais", "label": "Adicionais mensais (R$)", "type": "number",
             "span": "span 2", "ph": "0 — noturno, insalubridade, etc."},
        ],
    }
    out["cct-validar-salario"] = {
        "title": "CCT — Validar salário contra o piso",
        "sub": "Confere se o salário respeita o piso do cargo na CCT. Só consulta — não grava.",
        "cta": "Validar", "type": "form",
        "submit": {"endpoint": "/api/v1/cct/salarios/validar", "okMsg": "Salário validado",
                   "showResult": True},
        "fields": [
            {"key": "cargo", "label": "Cargo (como está na tabela CCT)*", "type": "text",
             "span": "span 2", "ph": "Ex.: Agente de Portaria"},
            {"key": "salario_atual", "label": "Salário atual (R$)*", "type": "number", "span": "span 1",
             "ph": "1670.00"},
            {"key": "employee_id", "label": "Colaborador (id) — opcional", "type": "text",
             "span": "span 1"},
        ],
    }
    out["cct-auditar-salario"] = {
        "title": "CCT — Auditar salário (registra)",
        "sub": "Mesma validação da tela anterior, porém GRAVA a auditoria no banco para "
               "trilha. Use quando quiser deixar registro; para só conferir, use Validar.",
        "cta": "Auditar e registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/cct/salarios/auditar", "okMsg": "Auditoria registrada",
                   "showResult": True},
        "fields": [
            {"key": "cargo", "label": "Cargo (como está na tabela CCT)*", "type": "text",
             "span": "span 2", "ph": "Ex.: Agente de Portaria"},
            {"key": "salario_atual", "label": "Salário atual (R$)*", "type": "number", "span": "span 1",
             "ph": "1670.00"},
            {"key": "employee_id", "label": "Colaborador (id)", "type": "text", "span": "span 1"},
        ],
    }
    out["cct-reajuste"] = {
        "title": "CCT — Calcular reajuste",
        "sub": "7,1% para quem está no piso, 4,5% acima dele. Informe o cargo para o sistema "
               "saber em qual regra você cai.",
        "cta": "Calcular", "type": "form",
        "submit": {"endpoint": "/api/v1/cct/salarios/reajuste", "okMsg": "Reajuste calculado",
                   "showResult": True},
        "fields": [
            {"key": "salario_atual", "label": "Salário atual (R$)*", "type": "number", "span": "span 1",
             "ph": "1670.00"},
            {"key": "cargo", "label": "Cargo — define se está no piso", "type": "text",
             "span": "span 1", "ph": "Ex.: Agente de Portaria"},
        ],
    }

    out["consultor-perguntar"] = {
        "title": "Consultor de RH",
        "sub": "Pergunta ancorada nos dados reais de RH. É consulta — não altera nada.",
        "cta": "Perguntar", "type": "form",
        "submit": {"endpoint": "/api/v1/rh/consultor/perguntar", "okMsg": "Consulta respondida",
                   "showResult": True},
        "fields": [
            {"key": "area", "label": "Área*", "type": "text", "span": "span 2",
             "ph": "Ex.: treinamento, clima, carreira"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["cct-invalidar-cache"] = {
        "title": "CCT — Limpar cache",
        "sub": "Use depois de alterar piso, convenção ou feriado: as calculadoras acima leem "
               "do cache e continuariam devolvendo o valor antigo.",
        "cta": "Limpar cache", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/admin/cct/cache/invalidar",
                   "okMsg": "Cache da CCT limpo"},
        "fields": [],
    }

    # ── APOIO À DECISÃO DISCIPLINAR (2026-08-10) ────────────────────────────────────
    # O sistema tinha 17 rotas de medida disciplinar sem superficie: da para VER a medida
    # (KPI e lista no operacional) e nao da para agir. As 14 de ACAO (criar, submeter,
    # aprovar, rejeitar, assinar, recusar, templates) ficam com o terminal do operacional,
    # porque o menu delas vive em _op_grupos.py e o modulo e curado a mao.
    #
    # Estas 3 sao CONSULTIVAS — nao criam, nao aprovam, nao aplicam nada. Sao o passo que
    # vem ANTES de decidir, e por isso cabem no RH sem invadir o operacional.
    #
    # As 3 quase entraram como "botao seco": meu extrator ignora parametro chamado
    # `request` (achando que e o Request do FastAPI) e aqui `request` E o modelo Pydantic.
    # Sairiam sem nenhum campo e dariam 422 em todo clique. Reconferi as 12 telas secas que
    # ja tinha entregue — todas secas de verdade.
    out["disc-recomendar"] = {
        "title": "Disciplinar — qual medida cabe aqui?",
        "sub": "Recomenda o tipo de medida com base no histórico do colaborador. É opinião "
               "de apoio: não cria medida nenhuma.",
        "cta": "Recomendar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/discipline/medidas-administrativas/ia/recomendar",
                   "okMsg": "Recomendação gerada", "showResult": True},
        "fields": [
            {"key": "employee_id", "label": "Colaborador (id)*", "type": "text", "span": "span 1"},
            {"key": "incident_date", "label": "Data do ocorrido*", "type": "date", "span": "span 1"},
            {"key": "reason_category", "label": "Motivo*", "type": "select", "span": "span 2",
             "ph": "Selecione", "options": _MOTIVO},
            {"key": "reason_description", "label": "O que aconteceu*", "type": "textarea",
             "span": "span 2", "ph": "Descreva o fato — é o que sustenta a medida"},
        ],
    }
    out["disc-conformidade"] = {
        "title": "Disciplinar — a medida está conforme a CLT?",
        "sub": "Confere a medida pretendida contra a CLT (prazo entre o fato e a aplicação, "
               "enquadramento). Consulta — não aplica nada.",
        "cta": "Validar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/discipline/medidas-administrativas/ia/validar-conformidade",
                   "okMsg": "Conformidade validada", "showResult": True},
        "fields": [
            {"key": "action_type", "label": "Medida pretendida*", "type": "select", "span": "span 2",
             "ph": "Selecione", "options": _MEDIDA},
            {"key": "reason_category", "label": "Motivo*", "type": "select", "span": "span 2",
             "ph": "Selecione", "options": _MOTIVO},
            {"key": "incident_date", "label": "Data do ocorrido*", "type": "date", "span": "span 1"},
            {"key": "application_date", "label": "Data da aplicação*", "type": "date", "span": "span 1"},
            {"key": "reason_description", "label": "O que aconteceu*", "type": "textarea",
             "span": "span 2"},
        ],
    }
    out["disc-proporcionalidade"] = {
        "title": "Disciplinar — a medida é proporcional?",
        "sub": "Pesa a medida contra o histórico (advertências e suspensões anteriores) e o "
               "tempo de casa. É o teste que evita punição desproporcional.",
        "cta": "Verificar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/discipline/medidas-administrativas/ia/verificar-proporcionalidade",
                   "okMsg": "Proporcionalidade verificada", "showResult": True},
        "fields": [
            {"key": "action_type", "label": "Medida pretendida*", "type": "select", "span": "span 2",
             "ph": "Selecione", "options": _MEDIDA},
            {"key": "reason_category", "label": "Motivo*", "type": "select", "span": "span 2",
             "ph": "Selecione", "options": _MOTIVO},
            {"key": "previous_warnings", "label": "Advertências anteriores*", "type": "number",
             "span": "span 1", "ph": "0"},
            {"key": "previous_suspensions", "label": "Suspensões anteriores*", "type": "number",
             "span": "span 1", "ph": "0"},
            {"key": "employee_tenure_days", "label": "Tempo de casa (dias)*", "type": "number",
             "span": "span 2", "ph": "Ex.: 540"},
        ],
    }

    # ── Anexo e currículo (submit.query; nas de anexo, multipart+query) ─────────────
    out["consultor-arquivo"] = {
        "title": "Consultor de RH — analisando um anexo",
        "sub": "Anexe o documento e pergunte sobre ele. O arquivo é lido para responder, "
               "não fica guardado.",
        "cta": "Analisar", "type": "form",
        "submit": {"endpoint": "/api/v1/rh/consultor/perguntar-arquivo",
                   "multipart": True, "query": True,
                   "okMsg": "Análise concluída", "showResult": True},
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Área", "type": "text", "span": "span 2",
             "ph": "Ex.: treinamento, clima, carreira"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["curriculo-texto"] = {
        "title": "Analisar currículo (texto colado)",
        "sub": "Extrai dados estruturados do currículo. Use quando você já tem o texto — "
               "para arquivo, use a tela ao lado.",
        "cta": "Analisar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/human-resources/recruitment/resume/parse-text",
                   "query": True, "okMsg": "Currículo analisado", "showResult": True},
        "fields": [
            {"key": "text", "label": "Texto do currículo*", "type": "textarea", "span": "span 2",
             "ph": "Cole o conteúdo do currículo"},
        ],
    }
    out["curriculo-arquivo"] = {
        "title": "Analisar currículo (PDF/DOCX)",
        "sub": "Faz o parsing do arquivo e devolve os dados estruturados. Não cria candidato "
               "— é leitura.",
        "cta": "Analisar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/human-resources/recruitment/resume/parse",
                   "multipart": True, "okMsg": "Currículo analisado", "showResult": True},
        "fields": [
            {"key": "file", "label": "Currículo (PDF ou DOCX)*", "type": "file", "span": "span 2"},
        ],
    }

    # ── CICLO DE VIDA DISCIPLINAR (2026-08-10) ──────────────────────────────────────
    # O sistema tinha 17 rotas e nenhuma acao alcancavel: dava para VER a medida (KPI no
    # operacional) e nao dava para criar, submeter, aprovar, rejeitar ou assinar. As 8 de
    # {action_id} viram acao por LINHA aqui; a listagem e a fonte do id.
    #
    # Fica no RH, e nao no operacional, porque o menu de la vive em _op_grupos.py — modulo
    # curado a mao. Medida disciplinar e assunto de RH; o operacional segue mostrando o KPI.
    _DISC_TONE = {"rascunho": "mut", "pendente_aprovacao": "warn", "aprovada": "ok",
                  "rejeitada": "bad", "pendente_assinatura": "warn", "assinada": "ok",
                  "recusada_assinatura": "bad", "aplicada": "ok", "cancelada": "mut"}

    def _disc_acoes(r):
        aid, st = r[0], (r[6] or "").lower()
        A = []
        if st == "rascunho":
            A.append({"title": f"Submeter para aprovacao — {r[1]}",
                      "endpoint": f"/api/v1/people-management/hr/discipline/medidas-administrativas/{aid}/submeter",
                      "method": "POST", "btnLabel": "Submeter", "submitLabel": "Submeter para aprovacao",
                      "btnStyle": "primary", "okMsg": "Medida submetida. Recarregue.", "fields": []})
        if st == "pendente_aprovacao":
            A.append({"title": f"Aprovar a medida de {r[1]}",
                      "sub": "Aprovada, ela segue para assinatura do colaborador.",
                      "endpoint": f"/api/v1/people-management/hr/discipline/medidas-administrativas/{aid}/aprovar",
                      "method": "POST", "btnLabel": "Aprovar", "submitLabel": "Aprovar medida",
                      "btnStyle": "primary", "okMsg": "Medida aprovada. Recarregue.", "fields": []})
            A.append({"title": f"Rejeitar a medida de {r[1]}",
                      "endpoint": f"/api/v1/people-management/hr/discipline/medidas-administrativas/{aid}/rejeitar",
                      "method": "POST", "btnLabel": "Rejeitar", "submitLabel": "Rejeitar medida",
                      "btnStyle": "outline", "okMsg": "Medida rejeitada. Recarregue.",
                      "fields": [{"key": "motivo", "label": "Motivo da rejeicao", "type": "textarea",
                                  "value": "", "span": "span 2"}]})
        if st in ("aprovada", "pendente_assinatura"):
            A.append({"title": f"Registrar assinatura — {r[1]}",
                      "endpoint": f"/api/v1/people-management/hr/discipline/medidas-administrativas/{aid}/assinar",
                      "method": "POST", "btnLabel": "Assinar", "submitLabel": "Registrar assinatura",
                      "btnStyle": "primary", "okMsg": "Assinatura registrada. Recarregue.", "fields": []})
            A.append({"title": f"Registrar RECUSA de assinatura — {r[1]}",
                      "sub": "O colaborador se recusou a assinar. A CLT admite; o registro com "
                             "testemunha e o que sustenta a medida.",
                      "endpoint": f"/api/v1/people-management/hr/discipline/medidas-administrativas/{aid}/recusar-assinatura",
                      "method": "POST", "btnLabel": "Recusou", "submitLabel": "Registrar recusa",
                      "btnStyle": "outline", "okMsg": "Recusa registrada. Recarregue.",
                      "fields": [{"key": "testemunha", "label": "Testemunha da recusa", "type": "text",
                                  "value": "", "span": "span 2"}]})
        A.append({"title": f"Gerar o documento da medida de {r[1]}",
                  "endpoint": f"/api/v1/people-management/hr/discipline/medidas-administrativas/gerar-documento?action_id={aid}",
                  "method": "POST", "btnLabel": "Documento", "submitLabel": "Gerar documento",
                  "btnStyle": "outline", "okMsg": "Documento gerado.", "fields": []})
        if st in ("rascunho", "rejeitada"):
            A.append({"title": f"Excluir a medida de {r[1]}",
                      "sub": "So em rascunho ou rejeitada — medida aplicada nao se apaga.",
                      "endpoint": f"/api/v1/people-management/hr/discipline/medidas-administrativas/{aid}",
                      "method": "DELETE", "btnLabel": "Excluir", "submitLabel": "Excluir medida",
                      "btnStyle": "outline", "okMsg": "Medida excluida. Recarregue.", "fields": []})
        return A or None

    await safe("disc-medidas", tbl(
        "Medidas disciplinares", "Ciclo completo: criar, submeter, aprovar, assinar", "Nova medida",
        ["Colaborador", "Medida", "Motivo", "Ocorrido", "Status"],
        "1.7fr 1.2fr 1.2fr 1fr 1.1fr",
        "SELECT id, coalesce(employee_name,'—'), coalesce(action_type::text,'—'), "
        "coalesce(reason_category::text,'—'), incident_date, coalesce(code,'—'), "
        "coalesce(status::text,'—') "
        "FROM disciplinary_actions ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, _ND, initials(r[1] or "")),
                   b((r[2] or '—').replace('_', ' ').capitalize(), "info"),
                   t((r[3] or '—').replace('_', ' ').capitalize()),
                   t(str(r[4])[:10] if r[4] else '—'),
                   b((r[6] or '—').replace('_', ' ').capitalize(), _DISC_TONE.get((r[6] or '').lower(), "info"))],
        actionsfn=_disc_acoes))
    if isinstance(out.get("disc-medidas"), dict):
        out["disc-medidas"]["ctaTo"] = "disc-nova"

    out["disc-nova"] = {
        "title": "Nova medida disciplinar",
        "sub": "Nasce como RASCUNHO — nada acontece com o colaborador ate voce submeter e "
               "alguem aprovar. Use as telas de apoio antes: recomendar, conformidade, "
               "proporcionalidade.",
        "cta": "Criar rascunho", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/discipline/medidas-administrativas",
                   "okMsg": "Medida criada (rascunho)"},
        "fields": [
            {"key": "employee_id", "label": "Colaborador (id)*", "type": "text", "span": "span 1"},
            {"key": "employee_name", "label": "Nome do colaborador*", "type": "text", "span": "span 1"},
            {"key": "employee_cpf", "label": "CPF*", "type": "text", "span": "span 1"},
            {"key": "employee_position", "label": "Cargo", "type": "text", "span": "span 1"},
            {"key": "action_type", "label": "Medida*", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": _MEDIDA},
            {"key": "reason_category", "label": "Motivo*", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": _MOTIVO},
            {"key": "incident_date", "label": "Data do ocorrido*", "type": "date", "span": "span 1"},
            {"key": "application_date", "label": "Data de aplicacao", "type": "date", "span": "span 1"},
            {"key": "suspension_days", "label": "Dias de suspensao (max 30)", "type": "number",
             "span": "span 1", "ph": "so para suspensao"},
            {"key": "witness_1_name", "label": "Testemunha", "type": "text", "span": "span 1"},
            {"key": "reason_description", "label": "O que aconteceu*", "type": "textarea",
             "span": "span 2", "ph": "E o que sustenta a medida — seja especifico"},
        ],
    }
    await safe("disc-templates", tbl(
        "Modelos de medida", "Textos-padrao por tipo de medida", "Novo modelo",
        ["Modelo", "Tipo", "Padrao"], "2fr 1.4fr 0.8fr",
        "SELECT id, coalesce(name,'—'), coalesce(action_type::text,'—'), coalesce(is_default,false) "
        "FROM disciplinary_templates ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, _ND), b((r[2] or '—').replace('_', ' ').capitalize(), "info"),
                   b("Padrao", "ok") if r[3] else b("—", "mut")],
        actionsfn=lambda r: [
            {"title": f"Excluir o modelo {r[1]}",
             "endpoint": f"/api/v1/people-management/hr/discipline/medidas-administrativas/templates/{r[0]}",
             "method": "DELETE", "btnLabel": "Excluir", "submitLabel": "Excluir modelo",
             "btnStyle": "outline", "okMsg": "Modelo excluido. Recarregue.", "fields": []},
        ]))
    if isinstance(out.get("disc-templates"), dict):
        out["disc-templates"]["ctaTo"] = "disc-template-novo"

    out["disc-template-novo"] = {
        "title": "Novo modelo de medida",
        "sub": "Texto-padrao usado ao gerar o documento da medida.",
        "cta": "Criar modelo", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/discipline/medidas-administrativas/templates",
                   "okMsg": "Modelo criado"},
        "fields": [
            {"key": "name", "label": "Nome do modelo*", "type": "text", "span": "span 1"},
            {"key": "action_type", "label": "Para qual medida*", "type": "select", "span": "span 1",
             "ph": "Selecione", "options": _MEDIDA},
            {"key": "description", "label": "Descricao", "type": "text", "span": "span 2"},
            {"key": "content", "label": "Texto do documento*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["disc-verificar-assinatura"] = {
        "title": "Verificar assinatura de documento",
        "sub": "Confere se a assinatura registrada corresponde ao documento. Leitura — nao "
               "assina nem invalida nada.",
        "cta": "Verificar", "type": "form",
        "submit": {"endpoint": "/api/v1/people-management/hr/discipline/assinaturas/verificar",
                   "okMsg": "Verificacao concluida", "showResult": True},
        "fields": [
            {"key": "signature_id", "label": "Assinatura (id)*", "type": "text", "span": "span 2"},
            {"key": "document_content", "label": "Conteudo do documento*", "type": "textarea",
             "span": "span 2"},
        ],
    }

    # Convencoes da CCT (2026-08-10): adicionar feriado leva {convencao_id} no CAMINHO ->
    # acao por LINHA. Feriado da convencao muda o calculo de hora extra a 100%.
    await safe("cct-convencoes", tbl(
        "CCT — convencoes", "Convencoes coletivas e seus feriados", "—",
        ["Sindicato", "Registro MTE", "Vigencia", "Municipio", "Vigente"],
        "2fr 1.2fr 1.4fr 1fr 0.8fr",
        "SELECT id, coalesce(sindicato_trabalhadores,'—'), coalesce(registro_mte,'—'), "
        "data_inicio, data_fim, coalesce(municipio,'—'), coalesce(is_vigente,false) "
        "FROM cct_convencoes ORDER BY data_inicio DESC NULLS LAST LIMIT 100",
        lambda r: [t((r[1] or '—')[:44], 600, _ND), t(r[2]),
                   t(f"{str(r[3])[:10]} a {str(r[4])[:10]}" if r[3] and r[4] else '—'),
                   t(r[5]), b("Vigente", "ok") if r[6] else b("—", "mut")],
        actionsfn=lambda r: [
            {"title": f"Adicionar feriado a convencao {r[2]}",
             "sub": "Feriado da convencao muda o calculo: hora extra em feriado e 100%, nao 50%. "
                    "Depois de adicionar, limpe o cache da CCT.",
             "endpoint": f"/api/v1/people-management/admin/cct/convencoes/{r[0]}/feriados",
             "method": "POST", "btnLabel": "Feriado", "submitLabel": "Adicionar feriado",
             "btnStyle": "outline", "okMsg": "Feriado adicionado. Limpe o cache da CCT.",
             "fields": [
                 {"key": "data_feriado", "label": "Data*", "type": "date", "value": "", "span": "span 1"},
                 {"key": "tipo", "label": "Tipo*", "type": "select", "value": "", "span": "span 1",
                  "options": [{"value": "nacional", "label": "Nacional"},
                              {"value": "estadual", "label": "Estadual"},
                              {"value": "municipal", "label": "Municipal"},
                              {"value": "categoria", "label": "Da categoria"}]},
                 {"key": "nome", "label": "Nome do feriado*", "type": "text", "value": "",
                  "span": "span 2"},
             ]},
        ]))

    return out
