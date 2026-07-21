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
EXTRA_MENU: list[dict] = []
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


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
        ["Etapa", "Ordem", "Rating", "Aplicada", "Status"],
        "1.6fr 0.7fr 0.7fr 1fr 0.9fr",
        "SELECT coalesce(current_step,'—'), coalesce(step_order,0), coalesce(rating,0), "
        "applied_at, coalesce(status,'—') FROM applications WHERE coalesce(is_active,true) "
        "ORDER BY applied_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0]), t(str(r[1])), t(str(r[2])), t(_d(r[3])), _bs(r[4])]))

    # 3) Onboarding — admission_processes
    await safe("onboarding", tbl(
        "Onboarding", "Processos de integração", "—",
        ["Candidato", "Cargo", "Início previsto", "Status"],
        "2fr 1.4fr 1fr 0.9fr",
        "SELECT coalesce(candidate_name,'—'), coalesce(position,'—'), expected_start_date, "
        "coalesce(status,'—') FROM admission_processes ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(_d(r[2])), _bs(r[3])]))

    # 4) Treinamentos — trainings (real; 0 = honesto)
    await safe("treinamentos", tbl(
        "Treinamentos", "Turmas de treinamento", "—",
        ["Treinamento", "Início", "Fim", "Participantes", "Status"],
        "2fr 1fr 1fr 1fr 0.9fr",
        "SELECT coalesce(title,'—'), start_date, end_date, coalesce(current_participants,0), "
        "coalesce(status::text,'—') FROM trainings ORDER BY start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(_d(r[1])), t(_d(r[2])), t(str(r[3])), _bs(r[4])]))

    # 5) Cursos — training_courses (real; 0 = honesto)
    await safe("cursos", tbl(
        "Cursos", "Catálogo de cursos", "—",
        ["Curso", "Categoria", "Carga (h)", "Obrigatório", "Provedor"],
        "2fr 1.2fr 0.8fr 1fr 1.2fr",
        "SELECT coalesce(name,'—'), coalesce(category::text,'—'), coalesce(duration_hours,0), "
        "coalesce(is_mandatory,false), coalesce(provider,'—') FROM training_courses "
        "WHERE coalesce(is_active,true) ORDER BY name LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(str(r[2])), _bb(r[3], "Sim", "Não", "warn", "mut"), t(r[4])]))

    # 6) Avaliações — operacional_avaliacoes_equipe
    await safe("avaliacoes", tbl(
        "Avaliações", "Avaliações de equipe", "—",
        ["Colaborador", "Avaliador", "Nota", "Competência", "Data"],
        "1.8fr 1.5fr 0.7fr 1fr 1fr",
        "SELECT coalesce(e.nome, a.employee_id::text), coalesce(a.avaliador_nome,'—'), "
        "coalesce(a.nota,0), coalesce(to_char(a.competencia,'MM/YYYY'),'—'), a.criada_em "
        "FROM operacional_avaliacoes_equipe a LEFT JOIN employees e ON e.id::text = a.employee_id::text "
        "ORDER BY a.criada_em DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(str(r[2])), t(r[3]), t(_d(r[4]))]))

    # 7) Carreira — career_plans (real; 0 = honesto)
    await safe("carreira", tbl(
        "Carreira", "Planos de carreira", "—",
        ["Colaborador", "Posição atual", "Alvo", "Prazo (m)", "Status"],
        "1.6fr 1.4fr 1.4fr 0.8fr 0.9fr",
        "SELECT coalesce(e.nome, c.employee_id::text), coalesce(c.current_position,'—'), "
        "coalesce(c.target_position,'—'), coalesce(c.estimated_timeline_months,0), coalesce(c.status::text,'—') "
        "FROM career_plans c LEFT JOIN employees e ON e.id::text = c.employee_id::text "
        "ORDER BY c.created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND, initials(r[0] or "")), t(r[1]), t(r[2]), t(str(r[3])), _bs(r[4])]))

    # 8) Clima — climate_surveys (real; 0 = honesto)
    await safe("clima", tbl(
        "Clima", "Pesquisas de clima", "—",
        ["Pesquisa", "Frequência", "Respostas", "Score médio", "Ativo"],
        "2fr 1fr 0.9fr 1fr 0.8fr",
        "SELECT coalesce(nome,'—'), coalesce(frequencia,'—'), coalesce(total_respostas,0), "
        "coalesce(score_medio,0), coalesce(ativo,false) FROM climate_surveys "
        "ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0] or "—", 600, _ND), t(r[1]), t(str(r[2])), t(f"{float(r[3]):.1f}"), _bb(r[4], "Ativo", "—", "ok", "mut")]))

    # 9) Turnover — turnover_audit_logs
    await safe("turnover", tbl(
        "Turnover", "Trilha de auditoria de turnover", "—",
        ["Ação", "Recurso", "Funcionário", "Data"],
        "1.4fr 1.2fr 1.6fr 1.2fr",
        "SELECT coalesce(l.acao,'—'), coalesce(l.recurso,'—'), "
        "coalesce(e.nome, l.funcionario_id::text, '—'), l.created_at "
        "FROM turnover_audit_logs l LEFT JOIN employees e ON e.id::text = l.funcionario_id::text "
        "ORDER BY l.created_at DESC LIMIT 200",
        lambda r: [t((r[0] or "—").replace("_", " ")), t(r[1]), t(r[2] or "—"), t(_d(r[3], "%d/%m/%Y %H:%M"))]))

    # 10) RH IA — rh_consultas
    await safe("ia", tbl(
        "RH IA", "Consultas ao assistente de RH", "—",
        ["Área", "Competência", "Pergunta", "Escalonar", "Data"],
        "1fr 0.9fr 2fr 0.8fr 1fr",
        "SELECT coalesce(area,'—'), coalesce(competencia,'—'), coalesce(pergunta,'—'), "
        "coalesce(escalonar,false), created_at FROM rh_consultas ORDER BY created_at DESC LIMIT 200",
        lambda r: [t(r[0], 600, _ND), t(r[1]), t((r[2] or "—")[:90]), _bb(r[3], "Sim", "Não", "bad", "ok"), t(_d(r[4]))]))

    return out
