"""
redesign_builders/financeiro.py — T4 (cluster financeiro/comercial).
Sobrescreve o _build_financeiro do monólito: reusa a base (dashboard, contas a
pagar/receber, clientes, fornecedores, diaristas, Inter, formulários) e ADICIONA
as ~21 telas que faltavam, todas lendo o DADO REAL do clássico.

Regra de ouro: dinheiro que SAI e transmissão legal = GATED (só visibilidade).
Nunca fabricar dado — vazio real = tabela honesta "aguardando dado".
Ver auditoria/parity/DIVISAO_3T.md + BRIEFING_T4.md.
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_financeiro as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    initials,
    t,
)

SLUG = "financeiro"


def _simnao(v) -> dict:
    return b("Sim", "info") if v else b("—", "mut")


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    # Base do monólito (10 telas já provadas) — reusa sem duplicar.
    out.update(await _base(db))

    # ---- Fluxo de caixa (bank_transactions — entradas/saídas reais) ----
    await safe("fluxo-caixa", tbl(
        "Fluxo de caixa", f"{await _scalar(db, 'SELECT count(*) FROM bank_transactions')} lançamentos bancários",
        "—", ["Data", "Tipo", "Descrição", "Valor", "Status"], "1fr 1.1fr 2fr 1fr 1fr",
        "SELECT transaction_date, coalesce(transaction_type,'—'), coalesce(description,memo,'—'), amount, coalesce(status,'—') "
        "FROM bank_transactions ORDER BY transaction_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), b((r[1] or '—').replace('_', ' ').capitalize(), "info"),
                   t(r[2]), t(brl(r[3]), 600, "#0F1B3A"), t((r[4] or '—').capitalize())]))

    # ---- Conciliação bancária (inter_conciliacao_folha — folha x extrato Inter) ----
    await safe("conciliacao", tbl(
        "Conciliação bancária", f"{await _scalar(db, 'SELECT count(*) FROM inter_conciliacao_folha')} itens conciliados (folha × Inter)",
        "—", ["Competência", "Líquido", "Prevista", "Paga", "Status"], "1fr 1fr 1fr 1fr 0.9fr",
        "SELECT coalesce(competencia,'—'), valor_liquido, data_prevista, data_paga, coalesce(status,'—') "
        "FROM inter_conciliacao_folha ORDER BY data_prevista DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), t(_fmtdate(r[2])), t(_fmtdate(r[3])),
                   b((r[4] or '—').capitalize(), "ok" if (r[3] is not None) else "warn")]))

    # ---- Boletos (inter_cobrancas — cobranças emitidas via Inter) ----
    await safe("boletos", tbl(
        "Boletos", f"{await _scalar(db, 'SELECT count(*) FROM inter_cobrancas')} cobranças Inter",
        "—", ["Número", "Valor", "Vencimento", "Status", "Descrição"], "1fr 1fr 1fr 0.9fr 2fr",
        "SELECT coalesce(seu_numero,'—'), valor, vencimento, coalesce(status,'—'), coalesce(descricao,'—') "
        "FROM inter_cobrancas ORDER BY vencimento DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), t(_fmtdate(r[2])),
                   b((r[3] or '—').capitalize(), "ok" if (r[3] or '').upper() in ("RECEBIDO", "PAGO") else "warn"), t(r[4])]))

    # ---- Cobranças (receivable_accounts em aberto) ----
    await safe("cobrancas", tbl(
        "Cobranças", "Recebíveis em aberto (pendente/parcial)",
        "—", ["Cliente", "Descrição", "Valor", "Vencimento", "Status"], "1.5fr 2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(customer_name,'—'), coalesce(description,'—'), net_value, due_date, coalesce(status,'—') "
        "FROM receivable_accounts WHERE status IN ('pendente','parcial') ORDER BY due_date NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600), t(_fmtdate(r[3])),
                   b((r[4] or '—').capitalize(), "warn")]))

    # ---- Banking (extrato bancário consolidado com contraparte/saldo) ----
    await safe("banking", tbl(
        "Banking", "Extrato bancário consolidado",
        "—", ["Data", "Contraparte", "Descrição", "Valor", "Saldo"], "1fr 1.5fr 2fr 1fr 1fr",
        "SELECT transaction_date, coalesce(counterparty_name,contraparte_nome,'—'), coalesce(description,memo,'—'), amount, balance_after "
        "FROM bank_transactions ORDER BY transaction_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), t(r[1], 600, "#0F1B3A"), t(r[2]), t(brl(r[3]), 600),
                   t(brl(r[4]) if r[4] is not None else '—')]))

    # ---- Banco Inter (extrato Inter real) ----
    await safe("inter", tbl(
        "Banco Inter", f"{await _scalar(db, 'SELECT count(*) FROM inter_transactions')} lançamentos no extrato Inter",
        "—", ["Data", "Operação", "Descrição", "Valor", "Tipo"], "1fr 0.9fr 2fr 1fr 1.1fr",
        "SELECT data_lancamento, coalesce(tipo_operacao,'—'), coalesce(titulo,descricao,'—'), valor, coalesce(tipo_transacao,'—') "
        "FROM inter_transactions ORDER BY data_lancamento DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), b("Crédito" if r[1] == 'C' else ("Débito" if r[1] == 'D' else (r[1] or '—')),
                                        "ok" if r[1] == 'C' else "mut"),
                   t(r[2]), t(brl(r[3]), 600, "#0F1B3A"), t(r[4])]))

    # ---- Compras (nfe_compras_estoque — itens comprados por NF-e) ----
    await safe("compras", tbl(
        "Compras", f"{await _scalar(db, 'SELECT count(*) FROM nfe_compras_estoque')} itens de compra (NF-e)",
        "—", ["Código", "Item", "Qtd", "Custo unit.", "Última compra"], "1fr 2fr 0.8fr 1fr 1fr",
        "SELECT coalesce(item_code,'—'), coalesce(descricao,'—'), qty_on_hand, unit_cost, last_purchase_date "
        "FROM nfe_compras_estoque ORDER BY last_purchase_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(str(r[2]) if r[2] is not None else '—'),
                   t(brl(r[3]) if r[3] is not None else '—', 600), t(_fmtdate(r[4]))]))

    # ---- Estoque (saldo atual + custo médio) ----
    await safe("estoque", tbl(
        "Estoque", "Saldo de estoque (a partir das NF-e de compra)",
        "—", ["Código", "Item", "Unid.", "Saldo", "Custo médio"], "1fr 2fr 0.8fr 0.9fr 1fr",
        "SELECT coalesce(item_code,'—'), coalesce(descricao,'—'), coalesce(unidade,'—'), qty_on_hand, avg_cost "
        "FROM nfe_compras_estoque ORDER BY descricao LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]),
                   t(str(r[3]) if r[3] is not None else '—', 600), t(brl(r[4]) if r[4] is not None else '—')]))

    # ---- Faturamento (NFS-e emitidas — receita) ----
    await safe("faturamento", tbl(
        "Faturamento", f"{await _scalar(db, 'SELECT count(*) FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false')} NFS-e emitidas",
        "—", ["Número", "Competência", "Tomador", "Serviços", "Líquido"], "1fr 1fr 2fr 1fr 1fr",
        "SELECT coalesce(numero,'—'), coalesce(competencia,'—'), coalesce(tomador_nome,'—'), valor_servicos, valor_liquido "
        "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false ORDER BY data_emissao DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(brl(r[3]), 600), t(brl(r[4]))]))

    # ---- Fiscal (tributos sobre NFS-e emitidas — ISS/INSS retido) ----
    await safe("fiscal", tbl(
        "Fiscal", "Tributos sobre NFS-e emitidas (ISS / INSS retido)",
        "—", ["Competência", "NFS-e", "Base", "ISS", "INSS ret."], "1fr 1fr 1fr 1fr 1fr",
        "SELECT coalesce(competencia,'—'), coalesce(numero,'—'), valor_servicos, iss_valor, inss_retido "
        "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false ORDER BY data_emissao DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2])), t(brl(r[3])),
                   t(brl(r[4]) if r[4] is not None else brl(0))]))

    # ---- NFS-e entrada (notas tomadas) ----
    await safe("nfse-entrada", tbl(
        "NFS-e entrada", f"{await _scalar(db, 'SELECT count(*) FROM nfse_tomadas_nacional')} notas tomadas",
        "—", ["Número", "Competência", "Prestador", "Serviços", "ISS"], "1fr 1fr 2fr 1fr 1fr",
        "SELECT coalesce(numero,'—'), coalesce(competencia,'—'), coalesce(prestador_nome,'—'), valor_servicos, iss_valor "
        "FROM nfse_tomadas_nacional ORDER BY data_emissao DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(brl(r[3]), 600),
                   t(brl(r[4]) if r[4] is not None else brl(0))]))

    # ---- Orçamentos (financial_orcamentos — chaves orçamentárias) ----
    await safe("orcamentos", tbl(
        "Orçamentos", f"{await _scalar(db, 'SELECT count(*) FROM financial_orcamentos')} chaves orçamentárias",
        "—", ["Chave", "Valor", "Atualizado por", "Data"], "2fr 1fr 1.3fr 1fr",
        "SELECT coalesce(chave,'—'), valor, coalesce(updated_by,'—'), updated_at "
        "FROM financial_orcamentos ORDER BY updated_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), t(r[2]), t(_fmtdate(r[3]))]))

    # ---- Precificação (crm_pricing_funcoes — tabela CCT de funções) ----
    await safe("precificacao", tbl(
        "Precificação", f"{await _scalar(db, 'SELECT count(*) FROM crm_pricing_funcoes WHERE ativo=true')} funções (base CCT)",
        "—", ["Função", "Piso", "Noturno", "Periculosidade", "Insalubridade"], "2fr 1fr 1fr 1fr 1fr",
        "SELECT nome, salario_base, noturno, periculosidade, insalubridade "
        "FROM crm_pricing_funcoes WHERE ativo=true ORDER BY ordem NULLS LAST LIMIT 50",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), _simnao(r[2]), _simnao(r[3]), _simnao(r[4])]))

    # ---- Custos (financial_custos_recorrentes) ----
    await safe("custos", tbl(
        "Custos", f"{await _scalar(db, 'SELECT count(*) FROM financial_custos_recorrentes')} custos recorrentes",
        "—", ["Categoria", "Descrição", "Valor", "Dia venc.", "Ativo"], "1.2fr 2fr 1fr 0.8fr 0.7fr",
        "SELECT coalesce(categoria,'—'), coalesce(descricao,'—'), valor, dia_vencimento, ativo "
        "FROM financial_custos_recorrentes ORDER BY valor DESC LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600),
                   t(str(r[3]) if r[3] is not None else '—'), b("Ativo", "ok") if r[4] else b("Inativo", "mut")]))

    # ---- Contabilidade (razão — extrato bancário categorizado) ----
    await safe("contabilidade", tbl(
        "Contabilidade", "Lançamentos categorizados (razão a partir do extrato)",
        "—", ["Data", "Conta/Categoria", "Histórico", "D/C", "Valor"], "1fr 1.3fr 2fr 0.9fr 1fr",
        "SELECT transaction_date, coalesce(category,'—'), coalesce(description,memo,'—'), coalesce(transaction_type,'—'), amount "
        "FROM bank_transactions WHERE category IS NOT NULL ORDER BY transaction_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), t((r[1] or '—').replace('_', ' ').capitalize(), 600, "#0F1B3A"),
                   t(r[2]), b((r[3] or '—').replace('_', ' ').capitalize(), "info"), t(brl(r[4]), 600)]))

    # ---- Contratos (contracts — carteira financeira) ----
    await safe("contratos", tbl(
        "Contratos", f"{await _scalar(db, 'SELECT count(*) FROM contracts')} contratos",
        "—", ["Nº", "Contrato", "Mensal", "Status", "Início"], "1fr 2fr 1fr 0.9fr 1fr",
        "SELECT coalesce(contract_number,'—'), coalesce(name,'—'), monthly_value, coalesce(status::text,'—'), start_date "
        "FROM contracts ORDER BY start_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]) if r[2] is not None else '—', 600),
                   b((r[3] or '—').capitalize(), "ok" if (r[3] or '').lower() in ("active", "ativo", "assinado", "signed") else "info"),
                   t(_fmtdate(r[4]))]))

    # ---- Raio-X (KPIs financeiros reais) ----
    await safe("raio-x", tbl(
        "Raio-X financeiro", "Indicadores-chave (financial_kpis)",
        "—", ["Indicador", "Valor", "Unidade", "Status"], "2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(nome,'—'), valor_atual, coalesce(unidade,'—'), coalesce(status::text,'—') "
        'FROM financial_kpis WHERE ativo=true ORDER BY "order" NULLS LAST LIMIT 50',
        lambda r: [t(r[0], 600, "#0F1B3A"),
                   t((brl(r[1]) if (r[2] or '') == 'R$' else (f"{float(r[1]):g}" if r[1] is not None else '—')), 600),
                   t(r[2]), b((r[3] or '—').capitalize(), "ok" if (r[3] or '').upper() == "ACTIVE" else "mut")]))

    # ---- CFO IA (histórico de consultas — READ) ----
    await safe("cfo", tbl(
        "CFO IA", f"{await _scalar(db, 'SELECT count(*) FROM financial_cfo_consultas')} consultas (histórico)",
        "—", ["Área", "Pergunta", "Autor", "Data"], "1fr 2.5fr 1fr 1fr",
        "SELECT coalesce(area,'—'), left(coalesce(pergunta,'—'),90), coalesce(created_by,'—'), created_at "
        "FROM financial_cfo_consultas ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [b((r[0] or '—').capitalize(), "info"), t(r[1], 600, "#0F1B3A"), t(r[2]), t(_fmtdate(r[3]))]))

    # ---- Agentes (áreas ativas do CFO IA, agregadas — real) ----
    await safe("agentes", tbl(
        "Agentes IA", "Áreas de consultoria ativas (CFO IA)",
        "—", ["Agente / Área", "Consultas", "Última consulta"], "2fr 1fr 1.2fr",
        "SELECT coalesce(area,'—'), count(*), max(created_at) FROM financial_cfo_consultas GROUP BY area ORDER BY count(*) DESC",
        lambda r: [t((r[0] or '—').capitalize(), 600, "#0F1B3A"), b(f"{r[1]} consultas", "info"), t(_fmtdate(r[2]))]))

    # ---- Relatórios (indicadores disponíveis para relatórios — real) ----
    await safe("relatorios", tbl(
        "Relatórios", "Indicadores disponíveis para relatórios",
        "—", ["Indicador", "Categoria", "Valor atual", "Frequência"], "2fr 1.2fr 1fr 1fr",
        "SELECT coalesce(nome,'—'), coalesce(categoria::text,'—'), valor_atual, coalesce(frequencia::text,'—') "
        'FROM financial_kpis WHERE ativo=true ORDER BY "order" NULLS LAST LIMIT 50',
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').capitalize(), "mut"),
                   t(f"{float(r[2]):g}" if r[2] is not None else '—', 600), t((r[3] or '—').capitalize())]))

    # ---- Custeio CCT — o form de compute já existe no monólito sob 'custeio-cct';
    #      o menu-id real é 'custeio' → aponta a mesma ferramenta (compute puro, nada é gravado).
    if "custeio-cct" in out:
        out["custeio"] = out["custeio-cct"]

    return out
