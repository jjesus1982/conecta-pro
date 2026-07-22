"""
redesign_builders/empresas.py — T4.
Sobrescreve _build_empresas: reusa a base e ADICIONA demonstrativos (faturamento
por competência), rentabilidade (clientes por MRR/receita), liminares fiscais e
migrador (segmentação CNPJ1→CNPJ2). Só leitura — migração é curada pelo Jordan.
"""
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    _build_empresas as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    initials,
    t,
)

SLUG = "empresas"


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    out.update(await _base(db))

    # ---- Demonstrativos (faturamento NFS-e por competência — DRE-ish real) ----
    await safe("demonstrativos", tbl(
        "Demonstrativos", "Faturamento por competência (NFS-e emitidas)",
        "—", ["Competência", "NFS-e", "Faturado", "Líquido"], "1.2fr 1fr 1.2fr 1.2fr",
        "SELECT coalesce(competencia,'—'), count(*), coalesce(sum(valor_servicos),0), coalesce(sum(valor_liquido),0) "
        "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false GROUP BY competencia ORDER BY competencia DESC LIMIT 24",
        lambda r: [t(r[0], 600, "#0F1B3A"), b(f"{r[1]}", "info"), t(brl(r[2]), 600), t(brl(r[3]))]))

    # ---- Rentabilidade (clientes por MRR/receita/health) ----
    await safe("rentabilidade", tbl(
        "Rentabilidade", "Rentabilidade por cliente (MRR × receita)",
        "—", ["Cliente", "MRR", "Receita total", "Health"], "2fr 1fr 1.2fr 1fr",
        "SELECT name, coalesce(mrr,0), coalesce(total_revenue,0), health_score FROM clients WHERE ativo=true ORDER BY mrr DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(brl(r[1]), 600), t(brl(r[2])),
                   b(f"{float(r[3]):.0f}" if r[3] is not None else '—',
                     "ok" if (r[3] or 0) >= 70 else ("warn" if (r[3] or 0) >= 40 else "bad"))]))

    # ---- Liminares (fiscal_liminares) ----
    await safe("liminares", tbl(
        "Liminares", f"{await _scalar(db, 'SELECT count(*) FROM fiscal_liminares')} liminares fiscais",
        "—", ["Empresa", "Tributo", "Descrição", "Processo", "Status"], "1.2fr 1fr 2.2fr 1.3fr 0.9fr",
        "SELECT coalesce(empresa,'—'), coalesce(tributo,'—'), coalesce(descricao, tipo, '—'), coalesce(processo,'—'), coalesce(status,'—') "
        "FROM fiscal_liminares ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').upper(), "info"), t(r[2]),
                   t(r[3]), b((r[4] or '—').capitalize(), "ok" if (r[4] or '').lower() in ("deferida", "ativa", "vigente") else "warn")]))

    # ---- Migrador (segmentação CNPJ1→CNPJ2 por tipo de contrato — visibilidade) ----
    await safe("migrador", tbl(
        "Migrador CNPJ", "Segmentação de colaboradores para migração CNPJ1→CNPJ2 (curada pelo Jordan)",
        "—", ["Tipo de contrato", "Colaboradores"], "2fr 1fr",
        "SELECT coalesce(tipo_contrato,'—'), count(*) FROM employees WHERE is_active=true GROUP BY tipo_contrato ORDER BY count(*) DESC",
        lambda r: [t((r[0] or '—').upper(), 600, "#0F1B3A"), b(f"{r[1]} colaboradores", "info")]))

    return out
