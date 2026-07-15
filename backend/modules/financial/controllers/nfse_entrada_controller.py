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

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.publishers import publish_nota_emitida
from modules.financial.services.payable_auto_service import auto_criar_payables_nfse, processar_todas_pendentes

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Financial - NFS-e Entrada + Fiscal"])


# ── NFS-e Entrada ────────────────────────────────────────────────────────────


@router.get("/nfse-entrada")
async def listar_nfse_entrada(
    ano: int = Query(2026),
    competencia: str | None = Query(None),
    fornecedor_cnpj: str | None = Query(None),
    categoria: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Lista NFS-e recebidas de fornecedores (Lucro Real).

    FONTE REAL: nfse_tomadas_nacional (portal nacional gov.br, 182 notas em 2026).
    competencia é VARCHAR 'YYYY-MM' (não é date) => filtro de ano via LIKE :ano||'%'.
    Colunas: valor_servicos (plural!), iss_valor, prestador_cnpj/prestador_nome, descricao.
    Não existe 'categoria' nem 'valor_liquido' na fonte nacional.
    """
    conds = ["competencia LIKE :ano_like"]
    params: dict = {"ano": ano, "ano_like": f"{ano}%"}

    if competencia:
        conds.append("competencia = :comp")
        params["comp"] = competencia
    if fornecedor_cnpj:
        conds.append("prestador_cnpj = :cnpj")
        params["cnpj"] = re.sub(r"\D", "", fornecedor_cnpj)
    # NOTA: nfse_tomadas_nacional não tem coluna 'categoria'; o filtro é ignorado
    # (mantido na assinatura por compatibilidade de API).

    where = " AND ".join(conds)
    rows = (
        await db.execute(
            text(
                f"SELECT chave_acesso, numero, competencia, data_emissao, "
                f"prestador_cnpj, prestador_nome, valor_servicos, iss_valor, descricao "
                f"FROM nfse_tomadas_nacional WHERE {where} ORDER BY data_emissao DESC"
            ),
            params,
        )
    ).fetchall()

    total_valor = sum(float(r.valor_servicos or 0) for r in rows)
    return {
        "total": len(rows),
        "total_valor_bruto": round(total_valor, 2),
        "nfse_entrada": [dict(r._mapping) for r in rows],
    }


@router.post("/nfse-entrada/auto-criar-payables", status_code=200)
async def auto_criar_payables(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Cria contas a pagar automaticamente para NFS-e recebidas sem payable vinculado."""
    resultado = await auto_criar_payables_nfse(db)
    return {
        "success": True,
        "message": f"{resultado.get('criados', 0)} conta(s) a pagar criada(s), {resultado.get('erros', 0)} erro(s).",
        **resultado,
    }


@router.post("/payable/auto-criar", status_code=200)
async def auto_criar_payables_todas(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Processa todas as notas fiscais recebidas sem conta a pagar vinculada (NFS-e + NF-e)."""
    resultado = await processar_todas_pendentes(db)
    return {"status": "ok", "resultado": resultado}


@router.post("/payable/auto-criar/{nota_id}", status_code=200)
async def auto_criar_payable_nota(
    nota_id: str,
    tipo: str = Query(default="nfse", description="Tipo da nota: nfse ou nfe"),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Cria conta a pagar para uma nota fiscal específica."""
    from modules.financial.services.payable_auto_service import (
        criar_payable_de_nfe_entrada,
        criar_payable_de_nfse_entrada,
    )

    if tipo == "nfse":
        resultado = await criar_payable_de_nfse_entrada(db, nota_id)
    else:
        resultado = await criar_payable_de_nfe_entrada(db, nota_id)
    return {"status": "ok", "resultado": resultado}


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


@router.post("/bank-reconciliations/auto", status_code=201)
async def conciliacao_auto(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Conciliacao inteligente — 4 estrategias em cascata.

    S1: Nome do condominio na descricao do PIX
    S2: Valor exato do contrato
    S3: Valor ±5%
    S4: Palavras-chave na descricao
    """
    # Buscar receivables pendentes com nome do cliente extraido da descricao
    recs = (
        await db.execute(
            text(
                "SELECT id, gross_value, description "
                "FROM receivable_accounts "
                "WHERE status = 'pendente' "
                "ORDER BY gross_value DESC"
            )
        )
    ).fetchall()

    # Buscar transacoes de credito pendentes > R$ 500
    txs = (
        await db.execute(
            text(
                "SELECT id, amount, transaction_date, description "
                "FROM bank_transactions "
                "WHERE reconciliation_status = 'pendente' "
                "AND transaction_type = 'credit' "
                "AND amount > 500 "
                "ORDER BY amount DESC"
            )
        )
    ).fetchall()

    # Mapa nome_cliente -> receivable
    # Extrair nome do cliente da descricao do receivable ("Fatura Mar/2026 - XXX — NOME")
    rec_map: list[dict] = []
    for r in recs:
        desc = r.description or ""
        # Extrair nome apos " — " ou " - "
        nome = ""
        if " — " in desc:
            nome = desc.split(" — ")[-1].strip()
        elif " - " in desc:
            parts = desc.split(" - ")
            nome = parts[-1].strip() if len(parts) > 1 else ""
        # Extrair palavras-chave do nome (>3 chars, sem genericas)
        stop = {"condominio", "residencial", "edificio", "fatura", "mar", "2026", "portaria", "limpeza", "cftv"}
        palavras = [w.upper() for w in re.findall(r"\w+", nome) if len(w) > 3 and w.lower() not in stop]
        rec_map.append({"id": str(r.id), "valor": float(r.gross_value), "nome": nome, "palavras": palavras})

    tx_usadas: set[str] = set()
    conciliados: list[dict] = []
    pendentes_list: list[dict] = []

    for rec in rec_map:
        match_tx = None
        estrategia = ""

        for tx in txs:
            if str(tx.id) in tx_usadas:
                continue
            desc_upper = (tx.description or "").upper()

            # S1 — Nome do condominio na descricao PIX
            for palavra in rec["palavras"]:
                if palavra in desc_upper:
                    match_tx = tx
                    estrategia = f"S1_NOME:{palavra}"
                    break
            if match_tx:
                break

            # S2 — Valor exato
            if abs(float(tx.amount) - rec["valor"]) < 1.0:
                match_tx = tx
                estrategia = "S2_VALOR_EXATO"
                break

            # S3 — Valor ±5%
            margem = rec["valor"] * 0.05
            if abs(float(tx.amount) - rec["valor"]) <= margem:
                match_tx = tx
                estrategia = "S3_VALOR_5PCT"
                break

        if match_tx:
            tx_usadas.add(str(match_tx.id))
            await db.execute(
                text("UPDATE bank_transactions SET reconciliation_status='conciliado', updated_at=NOW() WHERE id=:tid"),
                {"tid": str(match_tx.id)},
            )
            await db.execute(
                text("UPDATE receivable_accounts SET status='pago', updated_at=NOW() WHERE id=:rid"),
                {"rid": rec["id"]},
            )
            conciliados.append(
                {
                    "cliente": rec["nome"],
                    "valor_rec": rec["valor"],
                    "valor_tx": float(match_tx.amount),
                    "data": str(match_tx.transaction_date),
                    "desc_tx": (match_tx.description or "")[:60],
                    "estrategia": estrategia,
                }
            )
        else:
            pendentes_list.append({"cliente": rec["nome"], "valor": rec["valor"]})

    await db.commit()
    total_valor = sum(c["valor_rec"] for c in conciliados)
    # Publisher GEDEON Event Bus — notas conciliadas
    if conciliados:
        try:
            import asyncio

            asyncio.create_task(
                publish_nota_emitida(
                    nota_id=f"conciliacao_{len(conciliados)}",
                    numero=str(len(conciliados)),
                    valor=round(total_valor, 2),
                    extra={
                        "tipo": "conciliacao_nfse_entrada",
                        "total_conciliados": len(conciliados),
                        "estrategias": list({c["estrategia"].split(":")[0] for c in conciliados}),
                    },
                )
            )
        except Exception:
            pass
    return {
        "total_receivables": len(rec_map),
        "conciliados": len(conciliados),
        "pendentes": len(pendentes_list),
        "percentual": round(len(conciliados) / max(1, len(rec_map)) * 100, 1),
        "valor_conciliado": round(total_valor, 2),
        "detalhes": conciliados,
        "pendentes_detalhe": pendentes_list,
        "estrategias": list({c["estrategia"].split(":")[0] for c in conciliados}),
    }


@router.get("/bank-reconciliations/status")
async def status_conciliacao(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Status da conciliacao bancaria."""
    rows = (
        await db.execute(
            text(
                "SELECT reconciliation_status, COUNT(*) as qtd, SUM(amount) as total "
                "FROM bank_transactions GROUP BY reconciliation_status"
            )
        )
    ).fetchall()
    return {"status": [dict(r._mapping) for r in rows]}


# ── Fiscal Stats (NFS-e fallback) ───────────────────────────────────────────


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


@router.get("/custos/resumo")
async def custos_resumo(
    mes: int = Query(3),
    ano: int = Query(2026),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Resumo de custos: folha + encargos + despesas com nota."""
    desp = (
        await db.execute(
            text(
                "SELECT COALESCE(SUM(valor_servico),0) as total, COUNT(*) as qtd "
                "FROM nfse_entrada "
                "WHERE EXTRACT(MONTH FROM competencia)=:mes "
                "AND EXTRACT(YEAR FROM competencia)=:ano"
            ),
            {"mes": mes, "ano": ano},
        )
    ).fetchone()

    # FOLHA REAL (hr_payslips) da competência — sem número fixo. Onde não há folha lançada, 0 (honesto).
    fol = (
        await db.execute(
            text(
                "SELECT COALESCE(SUM(total_earnings),0), COALESCE(SUM(fgts_value),0), "
                "COALESCE(SUM(inss_value),0), COUNT(*) "
                "FROM hr_payslips WHERE reference_year=:ano AND reference_month=:mes"
            ),
            {"mes": mes, "ano": ano},
        )
    ).fetchone()
    folha = float(fol[0] or 0)
    fgts = float(fol[1] or 0)
    inss = float(fol[2] or 0)
    n_holerites = int(fol[3] or 0)
    cpv = folha + fgts + inss
    desp_nota = float(desp.total) if desp else 0

    return {
        "competencia": f"{mes:02d}/{ano}",
        "cpv": {"folha": folha, "fgts": fgts, "inss": inss, "total": round(cpv, 2)},
        "despesas_operacionais": {"com_nota": round(desp_nota, 2), "qtd_notas": int(desp.qtd) if desp else 0},
        "total_custos": round(cpv + desp_nota, 2),
        "fonte_folha": "hr_payslips (real)",
        "holerites_no_mes": n_holerites,
        "aviso": None if n_holerites > 0 else "Sem folha lançada nesta competência (custo de folha = 0). Nada é estimado.",
    }


# ── Sync Portal Nacional ──────────────────────────────────────────────────────


@router.post("/nfse-entrada/sync", summary="Sincronizar NFS-e recebidas do Portal Nacional")
async def sync_nfse_entrada(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    _user: dict = Depends(get_current_user),
) -> dict:
    """Busca NFS-e onde CNPJ 35710481000103 é tomador e retorna resultado."""
    try:
        from modules.government_integrations.services.nfse_entrada_sync_service import (
            NFSeEntradaSyncService,
        )

        svc = NFSeEntradaSyncService()
        resultado = svc.buscar_nfse_recebidas(data_inicio, data_fim)
        return {"status": "ok", "resultado": resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nfse/sync-prestador", summary="Sincronizar NFS-e emitidas pelo Conecta Mais no Portal Nacional")
async def sync_nfse_prestador(
    data_inicio: str | None = None,
    data_fim: str | None = None,
    _user: dict = Depends(get_current_user),
) -> dict:
    """
    Busca NFS-e onde CNPJ 35710481000103 é PRESTADOR (emitente).

    Estratégia:
    - Tenta GET /nfse?cnpjPrestador= no Portal Nacional SEFIN v1.6
    - Portal Nacional não suporta consulta bulk por CNPJ (retorna 405)
    - Fallback: retorna notas da tabela local nfses (Manaus ABRASF)
    - GET /api/v1/financial/nfse lista essas notas com filtros adicionais
    """
    try:
        from modules.government_integrations.services.nfse_entrada_sync_service import (
            NFSeEntradaSyncService,
        )

        svc = NFSeEntradaSyncService()
        resultado = svc.buscar_nfse_emitidas(data_inicio, data_fim)
        return {"status": "ok", "resultado": resultado}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/nfse-entrada/status-sync", summary="Status das NFS-e recebidas no banco")
async def status_nfse_entrada(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Resumo das NFS-e recebidas registradas no banco."""
    row = (
        await db.execute(
            text(
                "SELECT COUNT(*) as total, "
                "COALESCE(SUM(valor_servico),0) as valor_total, "
                "MAX(created_at)::text as ultimo_sync "
                "FROM nfse_entrada"
            )
        )
    ).fetchone()
    return {
        "total_notas": int(row.total) if row else 0,
        "valor_total": float(row.valor_total) if row else 0,
        "ultimo_sync": row.ultimo_sync if row else None,
        "cnpj_tomador": "35710481000103",
        "endpoint_lista": "GET /api/v1/financial/nfse-entrada",
    }
