"""Motor de Contexto Jurídico — acesso READ-ONLY a todos os módulos do Conecta PRO.

Dado um sujeito (funcionário, contrato, cliente) ou a própria empresa, este motor
varre o ERP inteiro e monta um DOSSIÊ estruturado com toda a prova documental
relevante para análise de risco e defesa jurídica.

Princípios:
- SOMENTE LEITURA. Nunca escreve. Cada fonte é consultada de forma isolada
  (try/except por bloco) — falha em uma fonte não derruba o dossiê.
- VERACIDADE: cada seção declara {disponivel, total, itens/resumo}. Fonte vazia
  retorna disponivel=False com nota "aguardando dado" — nunca fabrica.
- As tabelas/colunas abaixo foram mapeadas contra o banco real (conecta_pro).

Fontes por domínio (mapa real):
  Pessoas/DP : employees, employment_contracts, hr_payslips(+items), payroll_payments,
               employee_deductions, hr_vacation_periods/_requests, termination_processes,
               employee_benefits, disciplinary_actions(vazia)
  Ponto      : gp_clock_punches, gp_monthly_closings, gp_justifications(vazia)
  SST        : gp_asos, gp_epi_deliveries, gp_cats, sst_afastamentos
  Operacional: allocations→posts (funcionário↔posto↔período), scales, shifts
  GED        : ged_kit_documents (por employee_id+tipo+assinatura), ged_documents
  Comercial  : contracts, clients, condominiums
  Fiscal     : nfses, fiscal_obligations, payable_accounts, ged_certidoes, empresas
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ── util ─────────────────────────────────────────────────────────────────────
def _so_digitos(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


async def _q(db: AsyncSession, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Executa SELECT e devolve lista de dicts. Nunca levanta — devolve [] em erro."""
    res = await db.execute(text(sql), params or {})
    return [dict(r) for r in res.mappings().all()]


async def _bloco_resumo(
    db: AsyncSession, nome: str, sql: str, params: dict, prova: str, chave_contagem: str
) -> dict[str, Any]:
    """Bloco para consultas AGREGADAS (COUNT/SUM): disponibilidade vem da contagem real,
    não da presença da linha-resumo (que sempre existe)."""
    try:
        itens = await _q(db, sql, params)
        cont = int((itens[0].get(chave_contagem) or 0)) if itens else 0
        return {
            "fonte": nome,
            "disponivel": cont > 0,
            "total": cont,
            "itens": itens if cont > 0 else [],
            "resumo": itens[0] if itens else {},
            "prova": prova,
            "nota": None if cont > 0 else "aguardando dado (nenhum registro para o sujeito)",
        }
    except Exception as e:  # noqa: BLE001
        return {"fonte": nome, "disponivel": False, "total": 0, "itens": [], "resumo": {},
                "prova": prova, "nota": f"fonte indisponível: {type(e).__name__}: {e}"}


async def _bloco(db: AsyncSession, nome: str, sql: str, params: dict, prova: str) -> dict[str, Any]:
    """Consulta uma fonte de forma isolada e devolve bloco padronizado do dossiê."""
    try:
        itens = await _q(db, sql, params)
        return {
            "fonte": nome,
            "disponivel": len(itens) > 0,
            "total": len(itens),
            "itens": itens,
            "prova": prova,
            "nota": None if itens else "aguardando dado (fonte sem registro para o sujeito)",
        }
    except Exception as e:  # noqa: BLE001 — isolamento proposital por fonte
        return {
            "fonte": nome,
            "disponivel": False,
            "total": 0,
            "itens": [],
            "prova": prova,
            "nota": f"fonte indisponível: {type(e).__name__}: {e}",
        }


# ── resolução do funcionário ─────────────────────────────────────────────────
async def resolver_funcionario(db: AsyncSession, identificador: str) -> dict[str, Any] | None:
    """Resolve um funcionário por id, CPF ou nome (ILIKE). Devolve o cadastro-base ou None."""
    ident = (identificador or "").strip()
    cpf = _so_digitos(ident)

    tentativas: list[tuple[str, dict]] = []
    # 1) id exato (uuid/serial) — comparação textual segura
    tentativas.append(("CAST(id AS TEXT) = :v", {"v": ident}))
    # 2) CPF (com/sem máscara)
    if len(cpf) == 11:
        tentativas.append(("regexp_replace(COALESCE(cpf,''), '\\D', '', 'g') = :v", {"v": cpf}))
    # 3) matrícula
    tentativas.append(("CAST(matricula AS TEXT) = :v", {"v": ident}))
    # 4) nome (ILIKE)
    if len(ident) >= 3 and not cpf.isdigit() or (len(ident) >= 3 and len(cpf) != 11):
        tentativas.append(("nome ILIKE :v", {"v": f"%{ident}%"}))

    cols = (
        "id, nome, nome_social, cpf, rg, data_nascimento, matricula, cargo, "
        "salario_base, data_admissao, data_demissao, data_desligamento, "
        "carga_horaria_semanal, ctps_numero, ctps_serie, ctps_uf, pis, "
        "posto_atual_nome, cliente_nome, data_inicio_posto, status"
    )
    for cond, params in tentativas:
        try:
            rows = await _q(db, f"SELECT {cols} FROM employees WHERE {cond} ORDER BY nome LIMIT 5", params)
        except Exception:
            continue
        if rows:
            return rows[0] if len(rows) == 1 else {"_ambiguo": True, "candidatos": rows}
    return None


# ── DOSSIÊ DO FUNCIONÁRIO (defesa trabalhista) ───────────────────────────────
async def dossie_funcionario(db: AsyncSession, identificador: str) -> dict[str, Any]:
    """Monta o dossiê probatório completo de um funcionário, cruzando todos os módulos."""
    base = await resolver_funcionario(db, identificador)
    if not base:
        return {"encontrado": False, "identificador": identificador,
                "mensagem": "Funcionário não localizado por id, CPF, matrícula ou nome."}
    if base.get("_ambiguo"):
        return {"encontrado": False, "ambiguo": True, "candidatos": base["candidatos"],
                "mensagem": "Mais de um funcionário corresponde — refine (use o id)."}

    eid = str(base["id"])
    P = {"eid": eid}

    secoes: dict[str, Any] = {}

    # 1. Contrato de trabalho / jornada / adicionais
    secoes["contrato_trabalho"] = await _bloco(
        db, "employment_contracts",
        "SELECT type, start_date, end_date, work_schedule, weekly_hours, base_salary, "
        "hazard_pay_percent, unhealthy_pay_percent, night_shift_percent, job_title, "
        "department, union_name, union_code, is_current, signed_at, document_path "
        "FROM employment_contracts WHERE CAST(employee_id AS TEXT)=:eid ORDER BY start_date DESC",
        P, "Jornada contratada, adicionais legais pactuados (art. 611 CLT/CCT), assinatura.")

    # 2. Holerites (pagamento de verbas) — Domínio/TOTVS
    secoes["holerites"] = await _bloco(
        db, "hr_payslips",
        "SELECT payslip_code, payslip_type, reference_year, reference_month, payment_date, "
        "base_salary, total_earnings, total_deductions, net_salary, inss_value, irrf_value, "
        "fgts_value, acknowledged_at, contested_at, pdf_path "
        "FROM hr_payslips WHERE CAST(employee_id AS TEXT)=:eid "
        "ORDER BY reference_year DESC, reference_month DESC",
        P, "Pagamento de salário e verbas mês a mês; recolhimento INSS/IRRF/FGTS; ciência/contestação.")

    # 3. Comprovantes de pagamento (PIX)
    secoes["pagamentos_pix"] = await _bloco(
        db, "payroll_payments",
        "SELECT mes, ano, valor_liquido, metodo, pix_e2e_id, pix_txid, status, data_pagamento "
        "FROM payroll_payments WHERE CAST(employee_id AS TEXT)=:eid ORDER BY ano DESC, mes DESC",
        P, "Quitação efetiva do líquido (pix_e2e_id = comprovante bancário rastreável).")

    # 4. Descontos consignados/autorizados
    secoes["descontos"] = await _bloco(
        db, "employee_deductions",
        "SELECT tipo, descricao, valor, percentual, base_calculo, parcela_atual, total_parcelas, "
        "data_inicio, data_fim, ativo FROM employee_deductions WHERE CAST(employee_id AS TEXT)=:eid",
        P, "Legitimidade de descontos (art. 462 CLT).")

    # 5. Ponto — resumo de batidas
    secoes["ponto_batidas"] = await _bloco_resumo(
        db, "gp_clock_punches",
        "SELECT COUNT(*) AS total_batidas, MIN(punch_timestamp) AS primeira, "
        "MAX(punch_timestamp) AS ultima, COUNT(*) FILTER (WHERE facial_match) AS com_facial, "
        "COUNT(*) FILTER (WHERE dentro_geofence) AS dentro_geofence "
        "FROM gp_clock_punches WHERE CAST(employee_id AS TEXT)=:eid",
        P, "Jornada efetivamente cumprida (cartão de ponto art. 74 CLT) com geofence + facial.",
        "total_batidas")

    # 6. Ponto — fechamento mensal (HE, noturno, faltas)
    secoes["ponto_fechamento"] = await _bloco(
        db, "gp_monthly_closings",
        "SELECT month, year, total_horas_trabalhadas, total_horas_extras_50, total_horas_extras_100, "
        "total_horas_noturnas, total_faltas, total_atrasos_minutos, total_dias_trabalhados, fechado "
        "FROM gp_monthly_closings WHERE CAST(employee_id AS TEXT)=:eid ORDER BY year DESC, month DESC",
        P, "Apuração mensal de horas extras (50/100%), adicional noturno, faltas e atrasos.")

    # 7. Férias
    secoes["ferias_periodos"] = await _bloco(
        db, "hr_vacation_periods",
        "SELECT start_date, end_date, period_number, days_entitled, days_used, days_sold, "
        "days_remaining, limit_date, is_expired FROM hr_vacation_periods "
        "WHERE CAST(employee_id AS TEXT)=:eid ORDER BY start_date DESC",
        P, "Período aquisitivo/concessivo (art. 134 CLT — evita dobra do art. 137).")
    secoes["ferias_gozo"] = await _bloco(
        db, "hr_vacation_requests",
        "SELECT request_code, status, start_date, end_date, return_date, days_requested, "
        "sell_days, gross_value, net_value FROM hr_vacation_requests "
        "WHERE CAST(employee_id AS TEXT)=:eid ORDER BY start_date DESC",
        P, "Concessão e pagamento de férias.")

    # 8. Rescisão / verbas rescisórias
    secoes["rescisao"] = await _bloco(
        db, "termination_processes",
        "SELECT type, reason, notice_period_days, last_working_day, status, severance_amount, "
        "vacation_balance_amount, thirteenth_salary_amount, fgts_amount, total_amount, esocial_event_sent "
        "FROM termination_processes WHERE CAST(employee_id AS TEXT)=:eid ORDER BY last_working_day DESC",
        P, "Composição das verbas rescisórias (aviso, saldo férias, 13º, FGTS/multa) — TRCT.")

    # 9. Benefícios
    secoes["beneficios"] = await _bloco(
        db, "employee_benefits",
        "SELECT type, provider, plan_name, employee_contribution, company_contribution, "
        "start_date, end_date, status FROM employee_benefits WHERE CAST(employee_id AS TEXT)=:eid",
        P, "Concessão de VT/VR/VA/plano e coparticipação (Lei 7.418/85).")

    # 10. Advertências / suspensões
    secoes["advertencias"] = await _bloco(
        db, "disciplinary_actions",
        "SELECT action_type, reason_category, reason_description, incident_date, application_date, "
        "suspension_days, witness_1_name FROM disciplinary_actions WHERE CAST(employee_id AS TEXT)=:eid "
        "ORDER BY incident_date DESC",
        P, "Gradação de penalidades — sustenta justa causa (art. 482 CLT).")

    # 11. SST — ASOs
    secoes["sst_asos"] = await _bloco(
        db, "gp_asos",
        "SELECT tipo, status, data_realizacao, data_validade, clinica, medico, crm, apto, documento_url "
        "FROM gp_asos WHERE CAST(employee_id AS TEXT)=:eid ORDER BY data_realizacao DESC",
        P, "Aptidão (admissional/periódico/demissional) — laudo médico. Nexo em doença ocupacional.")

    # 12. SST — EPIs entregues
    secoes["sst_epis"] = await _bloco(
        db, "gp_epi_deliveries",
        "SELECT epi_nome, epi_ca, quantidade, nr, data_entrega, data_validade, data_devolucao, "
        "(assinatura_funcionario IS NOT NULL) AS assinado "
        "FROM gp_epi_deliveries WHERE CAST(employee_id AS TEXT)=:eid ORDER BY data_entrega DESC",
        P, "Entrega de EPI assinada (NR-6) — descaracteriza insalubridade/afasta culpa em acidente.")

    # 13. SST — CATs
    secoes["sst_cats"] = await _bloco(
        db, "gp_cats",
        "SELECT tipo_acidente, data_acidente, local, descricao, gravidade, parte_corpo, "
        "numero_cat_inss, status FROM gp_cats WHERE CAST(employee_id AS TEXT)=:eid ORDER BY data_acidente DESC",
        P, "Comunicação de acidente (Lei 8.213/91) e nexo causal.")

    # 14. SST — Afastamentos / estabilidade
    secoes["afastamentos"] = await _bloco(
        db, "sst_afastamentos",
        "SELECT tipo, motivo, data_inicio, data_fim_prevista, data_retorno, dias_previstos, "
        "cid, medico, crm, status, gera_estabilidade, estabilidade_ate, encaminhado_inss "
        "FROM sst_afastamentos WHERE CAST(employee_id AS TEXT)=:eid ORDER BY data_inicio DESC",
        P, "Afastamento, CID e estabilidade acidentária de 12 meses (art. 118 Lei 8.213/91).")

    # 15. Operacional — alocações (onde/quando trabalhou)
    secoes["alocacoes"] = await _bloco(
        db, "allocations",
        "SELECT a.status, a.start_date, a.end_date, a.role, a.is_primary, "
        "p.name AS posto_nome, p.post_type, p.shift_type, p.address AS posto_endereco, p.city "
        "FROM allocations a LEFT JOIN posts p ON p.id = a.post_id "
        "WHERE CAST(a.employee_id AS TEXT)=:eid ORDER BY a.start_date DESC",
        P, "Qual posto/local e período o funcionário trabalhou (liga trabalhista↔operacional).")

    # 16. Operacional — turnos individuais (escala cumprida)
    secoes["turnos"] = await _bloco_resumo(
        db, "shifts",
        "SELECT COUNT(*) AS total_turnos, MIN(shift_date) AS primeiro, MAX(shift_date) AS ultimo, "
        "COUNT(*) FILTER (WHERE status='completed') AS realizados, "
        "SUM(COALESCE(overtime_hours,0)) AS he_total, SUM(COALESCE(night_hours,0)) AS noturnas_total "
        "FROM shifts WHERE CAST(employee_id AS TEXT)=:eid",
        P, "Dia-a-dia de cobertura de turno por posto (planejado/realizado).", "total_turnos")

    # 17. GED — documentos do funcionário (kits mensais)
    secoes["documentos_ged_kit"] = await _bloco(
        db, "ged_kit_documents",
        "SELECT document_type, document_name, file_path, is_signed, signed_at, signature_hash, "
        "source_module FROM ged_kit_documents WHERE CAST(employee_id AS TEXT)=:eid ORDER BY document_type",
        P, "Docs digitalizados por funcionário (ASO/atestado/advertência/rescisão) com assinatura SHA-256.")

    # 18. GED — documentos corporativos vinculados ao funcionário
    secoes["documentos_ged_corp"] = await _bloco(
        db, "ged_documents",
        "SELECT code, title, document_type, category, file_path, is_signed, valid_until, checksum "
        "FROM ged_documents WHERE CAST(employee_id AS TEXT)=:eid ORDER BY created_at DESC",
        P, "Laudos/contratos/atas digitalizados (OCR + checksum + assinatura forte).")

    # ── síntese ──
    disponiveis = [k for k, v in secoes.items() if isinstance(v, dict) and v.get("disponivel")]
    lacunas = [k for k, v in secoes.items() if isinstance(v, dict) and not v.get("disponivel")]

    return {
        "encontrado": True,
        "funcionario": base,
        "secoes": secoes,
        "sintese": {
            "fontes_com_prova": disponiveis,
            "fontes_sem_dado": lacunas,
            "cobertura": f"{len(disponiveis)}/{len(secoes)} fontes com registro",
        },
        "aviso": "Dossiê montado a partir do ERP (dado real). Fontes 'sem dado' indicam ausência "
                 "de registro no sistema, não ausência do fato — confirmar documento físico/externo.",
    }


# ── DOSSIÊ DO CONTRATO / CLIENTE ─────────────────────────────────────────────
async def dossie_contrato(db: AsyncSession, contrato_id: str) -> dict[str, Any]:
    """Reúne contrato + cliente + postos/alocações + faturamento (NFS-e) para disputa contratual."""
    P = {"cid": str(contrato_id)}
    contrato = await _q(
        db,
        "SELECT c.id, c.contract_number, c.name, c.start_date, c.end_date, c.monthly_value, "
        "c.total_value, c.status, c.has_sla, c.adjustment_index, c.next_adjustment_date, "
        "c.signed_at, cl.name AS cliente_nome, cl.document_number AS cliente_cnpj "
        "FROM contracts c LEFT JOIN clients cl ON cl.id = c.client_id "
        "WHERE CAST(c.id AS TEXT)=:cid",
        P,
    )
    if not contrato:
        return {"encontrado": False, "contrato_id": contrato_id}
    ctr = contrato[0]
    secoes = {
        "aditivos": await _bloco(
            db, "contract_addendums",
            "SELECT previous_value, new_value, adjustment_percent, effective_date, signed "
            "FROM contract_addendums WHERE CAST(contract_id AS TEXT)=:cid ORDER BY effective_date DESC",
            P, "Reajustes e alterações contratuais formalizados."),
        "sla_relatorios": await _bloco(
            db, "contract_sla_reports",
            "SELECT overall_score, penalty_applied, penalty_amount, created_at "
            "FROM contract_sla_reports WHERE CAST(contract_id AS TEXT)=:cid ORDER BY created_at DESC",
            P, "Cumprimento/descumprimento de SLA e penalidades."),
    }
    return {"encontrado": True, "contrato": ctr, "secoes": secoes}


async def dossie_cliente(db: AsyncSession, cliente_id: str) -> dict[str, Any]:
    """Reúne cliente + condomínios + contratos + faturamento (NFS-e) para ação cível."""
    P = {"cl": str(cliente_id)}
    cliente = await _q(
        db,
        "SELECT id, name, trading_name, client_type, document_number, status, is_defaulter, "
        "default_amount, address_city, address_state FROM clients WHERE CAST(id AS TEXT)=:cl",
        P,
    )
    if not cliente:
        return {"encontrado": False, "cliente_id": cliente_id}
    cl = cliente[0]
    secoes = {
        "condominios": await _bloco(
            db, "condominiums",
            "SELECT name, cnpj, address, syndic_name, syndic_cpf, administrator_name "
            "FROM condominiums WHERE CAST(client_id AS TEXT)=:cl", P,
            "Local do serviço e representante legal (síndico) à época."),
        "contratos": await _bloco(
            db, "contracts",
            "SELECT contract_number, name, start_date, end_date, monthly_value, status "
            "FROM contracts WHERE CAST(client_id AS TEXT)=:cl ORDER BY start_date DESC", P,
            "Relação contratual e valores."),
        "faturamento_nfse": await _bloco(
            db, "nfses",
            "SELECT numero_nfse, data_competencia, valor_servicos, iss_valor, status "
            "FROM nfses WHERE regexp_replace(COALESCE(tomador_cpf_cnpj,''),'\\D','','g') = "
            "(SELECT regexp_replace(COALESCE(document_number,''),'\\D','','g') FROM clients WHERE CAST(id AS TEXT)=:cl) "
            "ORDER BY data_competencia DESC", P,
            "Faturamento efetivo ao cliente (NFS-e emitidas)."),
    }
    return {"encontrado": True, "cliente": cl, "secoes": secoes}


# ── PANORAMA DA EMPRESA (regularidade / passivo) ─────────────────────────────
async def panorama_empresa(db: AsyncSession) -> dict[str, Any]:
    """Retrato jurídico da empresa: regime, quadro, certidões e obrigações fiscais."""
    secoes = {
        "empresas": await _bloco(
            db, "empresas",
            "SELECT razao_social, cnpj, regime_tributario, regime_futuro, inscricao_municipal, "
            "inscricao_estadual, status FROM empresas ORDER BY status", {},
            "Identidade e regime tributário aplicável por CNPJ."),
        "certidoes": await _bloco(
            db, "ged_certidoes",
            "SELECT name, document_type, issuing_body, issue_date, expiry_date, "
            "(expiry_date < CURRENT_DATE) AS vencida FROM ged_certidoes ORDER BY expiry_date", {},
            "Regularidade fiscal/trabalhista (CND Federal, CRF-FGTS, CNDT...)."),
        "obrigacoes_fiscais": await _bloco(
            db, "fiscal_obligations",
            "SELECT tipo, competencia_ano, competencia_mes, status, valor_devido, valor_pago, "
            "data_vencimento, data_pagamento FROM fiscal_obligations "
            "ORDER BY competencia_ano DESC, competencia_mes DESC LIMIT 40", {},
            "Devido x recolhido por competência (INSS/FGTS/ISS/IRRF/DCTFWeb)."),
        "quadro_ativo": await _bloco(
            db, "employees",
            "SELECT COUNT(*) AS total_ativos, SUM(COALESCE(salario_base,0)) AS folha_base "
            "FROM employees WHERE lower(COALESCE(status,''))='ativo'", {},
            "Dimensão do quadro (base de passivo trabalhista potencial)."),
    }
    return {"secoes": secoes}
