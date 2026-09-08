"""Controller NFS-e Entrada + Fiscal Stats + Conciliacao + Custos.

Endpoints para:
- NFS-e de fornecedores (compras com nota)
- Resumo fiscal para Receita Federal (Lucro Real)
- Conciliacao bancaria automatica
- Resumo de custos
"""

import logging
import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Financial - NFS-e Entrada + Fiscal"])


# ── NFS-e Entrada ────────────────────────────────────────────────────────────


@router.get("/nfse-entrada")
async def listar_nfse_entrada(
    ano: int = Query(2026),
    competencia: str | None = Query(None),
    fornecedor_cnpj: str | None = Query(None),
    categoria: str | None = Query(None),
    empresa: str | None = Query(None, description="slug: conecta_eletronica | conecta_patrimonial"),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Lista NFS-e RECEBIDAS (tomadas) dos 2 CNPJs, com CATEGORIA (via suppliers), EMPRESA
    e flag de PDF. FONTE REAL: nfse_tomadas_nacional (portal nacional gov.br).
    A categoria vem de suppliers.category (editável = override manual do Jordan)."""
    conds = ["nt.competencia LIKE :ano_like"]
    params: dict = {"ano": ano, "ano_like": f"{ano}%"}
    if competencia:
        conds.append("nt.competencia = :comp")
        params["comp"] = competencia
    if fornecedor_cnpj:
        conds.append("regexp_replace(COALESCE(nt.prestador_cnpj,''),'[^0-9]','','g') = :cnpj")
        params["cnpj"] = re.sub(r"\D", "", fornecedor_cnpj)
    if empresa:
        conds.append("e.slug = :empresa")
        params["empresa"] = empresa
    if categoria:
        conds.append("COALESCE(s.category,'outros') = :categoria")
        params["categoria"] = categoria

    where = " AND ".join(conds)
    rows = (await db.execute(text(
        f"SELECT nt.chave_acesso, nt.numero, nt.competencia, nt.data_emissao, "
        f"nt.prestador_cnpj, nt.prestador_nome, nt.valor_servicos, nt.iss_valor, nt.descricao, "
        f"COALESCE(e.slug,'-') AS empresa, COALESCE(s.category,'outros') AS categoria, "
        f"(nt.xml_raw IS NOT NULL) AS tem_xml "
        f"FROM nfse_tomadas_nacional nt "
        f"LEFT JOIN empresas e ON e.id = nt.empresa_id "
        f"LEFT JOIN suppliers s ON regexp_replace(COALESCE(s.cpf_cnpj,''),'[^0-9]','','g') = "
        f"          regexp_replace(COALESCE(nt.prestador_cnpj,''),'[^0-9]','','g') "
        f"WHERE {where} ORDER BY nt.data_emissao DESC"), params)).fetchall()

    itens = [dict(r._mapping) for r in rows]
    total_valor = sum(float(r.valor_servicos or 0) for r in rows)
    por_cat: dict[str, dict] = {}
    for it in itens:
        c = it["categoria"]
        por_cat.setdefault(c, {"qtd": 0, "total": 0.0})
        por_cat[c]["qtd"] += 1
        por_cat[c]["total"] = round(por_cat[c]["total"] + float(it["valor_servicos"] or 0), 2)
    return {
        "total": len(itens),
        "total_valor_bruto": round(total_valor, 2),
        "por_categoria": por_cat,
        "nfse_entrada": itens,
    }


@router.get("/nfse-entrada/{chave}/pdf", summary="PDF (DANFSe) da NFS-e recebida")
async def pdf_nfse_entrada(
    chave: str,
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
):
    """Gera o PDF da nota tomada: do XML guardado (fiel) ou dos campos (fallback)."""
    from modules.gedeon.services.nfse_danfse_generator import gerar_danfse_de_nfse, gerar_danfse_pdf

    row = (await db.execute(text(
        "SELECT chave_acesso, numero, competencia, data_emissao, prestador_cnpj, prestador_nome, "
        "valor_servicos, iss_valor, descricao, xml_raw FROM nfse_tomadas_nacional "
        "WHERE chave_acesso = :c LIMIT 1"), {"c": chave})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    try:
        pdf = gerar_danfse_pdf(row["xml_raw"]) if row.get("xml_raw") else gerar_danfse_de_nfse(dict(row))
    except Exception as exc:  # noqa: BLE001
        logger.error("Falha ao gerar PDF da nota tomada %s: %s", chave, exc)
        raise HTTPException(status_code=500, detail="Falha ao gerar o PDF da nota.") from exc
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="nfse-recebida-{chave[:14]}.pdf"'})


@router.get("/nfse-entrada/resumo-fiscal")
async def resumo_fiscal(
    ano: int = Query(2026),
    mes: int | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Resumo por fornecedor para Receita Federal.

    FONTE REAL: nfse_tomadas_nacional. competencia é VARCHAR 'YYYY-MM'.
    Filtro de ano via LIKE :ano||'%'; filtro de mês compara a competencia exata 'YYYY-MM'.
    A fonte nacional não tem 'categoria' (removida do GROUP BY) nem 'valor_liquido'
    (líquido = valor_servicos - iss_valor retido). valor bruto = valor_servicos.
    """
    p: dict = {"ano_like": f"{ano}%"}
    if mes:
        filtro = "AND competencia = :comp"
        p["comp"] = f"{ano}-{int(mes):02d}"
    else:
        filtro = ""
    rows = (
        await db.execute(
            text(
                f"SELECT prestador_cnpj, prestador_nome, "
                f"COUNT(*) as qtd, SUM(valor_servicos) as total_bruto, "
                f"SUM(valor_servicos - COALESCE(iss_valor, 0)) as total_liquido "
                f"FROM nfse_tomadas_nacional "
                f"WHERE competencia LIKE :ano_like {filtro} "
                f"GROUP BY prestador_cnpj, prestador_nome "
                f"ORDER BY total_bruto DESC"
            ),
            p,
        )
    ).fetchall()
    total = sum(float(r.total_bruto or 0) for r in rows)
    return {
        "ano": ano,
        "mes": mes,
        "total_despesas_documentadas": round(total, 2),
        "fornecedores": len(rows),
        "detalhes": [dict(r._mapping) for r in rows],
        "aviso": "Despesas sem NFS-e vinculada podem gerar malha fina no Lucro Real",
    }


# ── Conciliacao Bancaria ─────────────────────────────────────────────────────


@router.get("/fiscal/stats-real")
async def fiscal_stats_real(
    condominio_id: UUID = Query(None),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Stats fiscais baseadas em NFS-e reais emitidas (fonte autoritativa).

    FONTE: nfse_emitidas_nacional (portal nacional ADN, só cStat 100 — mesma fonte
    do DRE/relatorios). A tabela legada `nfses` cobria só jan-fev/2026 (27 notas) e
    subreportava a receita de serviço em ~62%.
    """
    nfse = (
        await db.execute(
            text(
                "SELECT COUNT(*) as total, "
                "COALESCE(SUM(valor_servicos),0) as receita, "
                "COALESCE(SUM(iss_valor),0) as iss "
                "FROM nfse_emitidas_nacional"
            )
        )
    ).fetchone()
    # competencia é VARCHAR 'YYYY-MM' na fonte nacional — usar direto (padrão do DRE)
    por_mes = (
        await db.execute(
            text(
                "SELECT competencia as mes, "
                "COUNT(*) as qtd, SUM(valor_servicos) as valor "
                "FROM nfse_emitidas_nacional GROUP BY competencia ORDER BY competencia"
            )
        )
    ).fetchall()
    return {
        "total_nfse": int(nfse.total) if nfse else 0,
        "receita_bruta": float(nfse.receita) if nfse else 0,
        "iss_total": float(nfse.iss) if nfse else 0,
        "receita_liquida": float((nfse.receita or 0) - (nfse.iss or 0)) if nfse else 0,
        "por_mes": [dict(r._mapping) for r in por_mes],
    }


# ── Custos Resumo ───────────────────────────────────────────────────────────


