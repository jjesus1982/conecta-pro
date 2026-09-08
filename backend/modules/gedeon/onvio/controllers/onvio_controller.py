"""GEDEON Fase 3 — Onvio API Endpoints"""

import asyncio
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_db
from core.database.session import get_sync_db
from modules.gedeon.models.onvio_models import FgtsGuia, InssGuia, OnvioDocument, OnvioSyncLog
from modules.gedeon.onvio.onvio_client import OnvioClient
from modules.gedeon.onvio.onvio_parser import classificar_documento
from modules.gedeon.onvio.onvio_sync_service import OnvioSyncService

# EnrichmentService importado lazily em /extrair-valores (requer pdfplumber)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/onvio", tags=["Onvio Sync"])

# CNPJ-like pattern: 14 consecutive digits (para identificar docs DCTFWEB sem prefixo)
_CNPJ_RE = re.compile(r"\d{14}")


def _classificar_extras(nome: str) -> str | None:
    """
    Pós-processamento para documentos que parser v2 deixa como 'outros'.
    Captura padrões de nomes reais do Onvio que o parser não cobre.
    Retorna nova categoria ou None (mantém 'outros').
    """
    u = nome.upper()
    u_ns = u.replace(" ", "").replace("_", "").replace("-", "")
    u_nc = u.replace("Ç", "C").replace("Ã", "A").replace("Á", "A").replace("É", "E").replace("Ê", "E").replace("Ó", "O")

    # TRCT = Termo de Rescisão de Contrato de Trabalho
    if "TRCT" in u:
        return "rescisao"

    # DCTFWEB sem prefixo "DCTFWEB" — identificado por CNPJ de 14 dígitos no nome
    has_cnpj = bool(_CNPJ_RE.search(nome))
    if has_cnpj:
        if "DECLARACAOCOMPLETA" in u_ns or "DECLARACAO" in u_nc:
            return "dctfweb_declaracao"
        if "RESUMOCREDITOS" in u_ns:
            return "dctfweb_resumo_creditos"
        if "RESUMODEBITOS" in u_ns:
            return "dctfweb_resumo_debitos"
        if "RECIBO" in u:
            return "dctfweb_recibo"
        if "GUIAPAGAMENTO" in u_ns:
            return "inss_guia"

    # DAS / Simples Nacional — variantes sem a palavra "SIMPLES"
    if "EXIBIRDAS" in u_ns or "EXIBIR" in u and "DAS" in u:
        return "das_simples_nacional"
    if "GUIA DAS" in u or "GUIA_DAS" in u_ns:
        return "das_simples_nacional"
    if "PGDAS" in u:
        return "das_simples_nacional"
    if "SIMPLES NACIONAL" in u or "SIMPLESNACIONAL" in u_ns:
        return "das_simples_nacional"

    # Parcelamento — PARC_ com underscores (sem espaço em "SIMPLES NACIONAL")
    if "PARC" in u and ("SIMPLESNACIONAL" in u_ns or "SIMPLENACIONAL" in u_ns or "DIVIDA" in u):
        return "parcelamento_simples"
    if "PARCELA" in u and "PGFN" in u:
        return "parcelamento_simples"
    if "ENTRADA" in u and "DIVIDA" in u and "SIMPLES" in u_nc:
        return "parcelamento_simples"

    # DAR ICMS (variante de dar_sefaz)
    if "DAR" in u and "ICMS" in u:
        return "dar_sefaz"

    # Empresa / Cadastrais
    if "CNPJ" in u:
        return "empresa_docs"
    if "INSCRICAO MUNICIPAL" in u_nc or "INSCRICAOMUNICIPAL" in u_ns:
        return "empresa_docs"
    if "CARTEIRA DE TRABALHO" in u:
        return "ficha_registro"
    if "TERMO" in u and ("RESPONSABILIDADE" in u or "RESPONSABILIDADE" in u_nc):
        return "empresa_docs"
    if "REQUERIMENTO SD" in u:
        return "atestado"
    if "RELACAO DE AFASTAMENTOS" in u_nc or "RELAÇÃO DE AFASTAMENTOS" in u:
        return "afastamento"
    if "FOLHAS DE PONTO" in u or "FOLHA DE PONTO" in u:
        return "folha_ponto"
    if "RESULTADO" in u and "PERICIA" in u_nc:
        return "aso"

    return None


_CATEGORIAS_FISCAIS = [
    "inss_guia",
    "fgts_guia",
    "fgts_consignado",
    "fgts_relatorio",
    "fgts_consignado_relatorio",
    "dctfweb_declaracao",
    "dctfweb_recibo",
    "dctfweb_debitos",
    "dctfweb_creditos",
    "dctfweb_resumo_debitos",
    "dctfweb_resumo_creditos",
    "dctfweb_extrato",
    "dctfweb_situacao",
]


@router.get("/status")
async def status_sessao():
    """Verifica se a sessão Onvio está ativa no Redis."""
    c = OnvioClient()
    return {"sessao_valida": c.validar_sessao(), "redis_key": "onvio:session"}


@router.post("/sync")
async def trigger_sync(
    mes_ref: str | None = None,
):
    """Inicia sincronização completa ou filtrada por mês (MM.AAAA)."""

    def _run_sync() -> dict:
        with get_sync_db() as sync_db:
            svc = OnvioSyncService(sync_db)
            return svc.sync_completo(mes_ref=mes_ref)

    try:
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, _run_sync)
        return {"message": "Sync iniciado", "resultado": resultado}
    except Exception as exc:
        logger.error("Erro no sync Onvio: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/documentos")
async def listar_documentos(
    categoria: str | None = None,
    mes_ref: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Lista documentos importados do Onvio."""
    stmt = select(OnvioDocument).order_by(OnvioDocument.data_onvio.desc()).limit(limit)
    if categoria:
        stmt = stmt.where(OnvioDocument.categoria == categoria)
    if mes_ref:
        stmt = stmt.where(OnvioDocument.mes_ref == mes_ref)

    result = await db.execute(stmt)
    docs = result.scalars().all()

    count_stmt = select(func.count(OnvioDocument.id))
    if categoria:
        count_stmt = count_stmt.where(OnvioDocument.categoria == categoria)
    if mes_ref:
        count_stmt = count_stmt.where(OnvioDocument.mes_ref == mes_ref)
    total = (await db.execute(count_stmt)).scalar() or 0

    return {
        "total": total,
        "documentos": [
            {
                "id": str(d.id),
                "nome": d.nome_arquivo,
                "categoria": d.categoria,
                "mes_ref": d.mes_ref,
                "data_onvio": str(d.data_onvio),
            }
            for d in docs
        ],
    }


@router.get("/historico")
async def historico_sync(limit: int = 20, db: AsyncSession = Depends(get_db)):
    """Retorna histórico de execuções de sync."""
    result = await db.execute(select(OnvioSyncLog).order_by(OnvioSyncLog.created_at.desc()).limit(limit))
    logs = result.scalars().all()
    return [
        {
            "id": str(l.id),
            "mes_ref": l.mes_ref,
            "status": l.status,
            "novos": l.docs_novos,
            "erros": l.docs_erro,
            "duracao_s": l.duracao_s,
            "created_at": str(l.created_at),
        }
        for l in logs
    ]


@router.get("/stats")
async def stats_documentos(db: AsyncSession = Depends(get_db)):
    """Totais de documentos por categoria."""
    result = await db.execute(
        select(OnvioDocument.categoria, func.count(OnvioDocument.id)).group_by(OnvioDocument.categoria)
    )
    cats = result.fetchall()
    count_result = await db.execute(select(func.count(OnvioDocument.id)))
    total = count_result.scalar() or 0
    return {"total": total, "por_categoria": dict(cats)}


@router.post("/reclassificar")
async def reclassificar_documentos():
    """
    Reaplica o parser v2 a TODOS os documentos já importados.
    NÃO baixa do Onvio — apenas atualiza categoria e mes_ref.
    Limpa e repopula fgts_guias e inss_guias com base na nova classificação.
    """

    def _run():
        with get_sync_db() as db:
            docs = db.query(OnvioDocument).all()
            total = len(docs)
            mudancas = {"categoria": 0, "mes_ref": 0}
            por_categoria: dict = {}

            for d in docs:
                resultado = classificar_documento(d.nome_arquivo)
                nova_cat = resultado.get("categoria", "outros")
                novo_mes = resultado.get("mes_ref")

                # Pós-processamento: captura padrões que parser v2 não cobre
                if nova_cat == "outros":
                    extra = _classificar_extras(d.nome_arquivo)
                    if extra:
                        nova_cat = extra

                if d.categoria != nova_cat:
                    d.categoria = nova_cat
                    mudancas["categoria"] += 1
                if d.mes_ref != novo_mes:
                    d.mes_ref = novo_mes
                    mudancas["mes_ref"] += 1

                por_categoria[nova_cat] = por_categoria.get(nova_cat, 0) + 1

            # 08/09/2026: o DELETE apagava valor/vencimento/código de barras de 38 guias (R$ 269 mil)
            # e o extrator não repõe (extraido_em fica preenchido). Agora só cria o que falta.
            _fgts_ok = {r[0] for r in db.query(FgtsGuia.onvio_doc_id).all()}
            _inss_ok = {r[0] for r in db.query(InssGuia.onvio_doc_id).all()}

            fgts_count = 0
            inss_count = 0
            for d in docs:
                cat = d.categoria or ""
                if not (d.mes_ref or "").strip():
                    continue  # sem competência não vira guia (gerava linhas com mes_ref vazio)
                if cat.startswith("fgts_") and cat != "fgts_crf":
                    if d.id in _fgts_ok:
                        continue
                    db.add(
                        FgtsGuia(
                            mes_ref=d.mes_ref or "",
                            tipo=cat.replace("fgts_", "").upper(),
                            arquivo_pdf=d.caminho_local,
                            onvio_doc_id=d.id,
                        )
                    )
                    fgts_count += 1
                elif cat == "inss_guia":
                    if d.id in _inss_ok:
                        continue
                    db.add(
                        InssGuia(
                            mes_ref=d.mes_ref or "",
                            arquivo_pdf=d.caminho_local,
                            onvio_doc_id=d.id,
                        )
                    )
                    inss_count += 1

            db.commit()

            return {
                "total_processados": total,
                "mudancas": mudancas,
                "fgts_guias_criados": fgts_count,
                "inss_guias_criados": inss_count,
                "por_categoria": dict(sorted(por_categoria.items(), key=lambda x: -x[1])),
            }

    try:
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, _run)
        return resultado
    except Exception as exc:
        logger.error("Erro na reclassificação: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/extrair-valores")
async def extrair_valores(
    forcar: bool = False,
    limite: int | None = None,
    _: dict = Depends(get_current_user),
):
    """
    Orquestra extração de valores dos PDFs fiscais.

    Query params:
      - forcar: reprocessa docs já extraídos (default False)
      - limite: processa apenas N primeiros — útil em testes (default: sem limite)
    """

    def _run():
        from modules.gedeon.onvio.pdf_extractor.enrichment_service import EnrichmentService  # noqa: PLC0415

        with get_sync_db() as db:
            service = EnrichmentService(db)
            return service.extrair_todos(forcar=forcar, limite=limite)

    try:
        loop = asyncio.get_event_loop()
        resultado = await loop.run_in_executor(None, _run)
        return resultado
    except Exception as exc:
        logger.error("Erro na extração de valores: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/valores-fiscais-resumo")
async def valores_fiscais_resumo(db: AsyncSession = Depends(get_db)):
    """Resumo agregado de valores fiscais extraídos (FGTS + INSS)."""
    # FGTS por tipo
    fgts_sql = """
        SELECT tipo,
               COUNT(*) AS cnt,
               COALESCE(SUM(valor), 0) AS soma
        FROM fgts_guias
        WHERE valor IS NOT NULL
        GROUP BY tipo
        ORDER BY soma DESC
    """
    fgts_rows = (await db.execute(text(fgts_sql))).mappings().all()
    fgts_por_tipo = [{"tipo": r["tipo"], "count": r["cnt"], "soma": float(r["soma"])} for r in fgts_rows]
    fgts_total = sum(row["soma"] for row in fgts_por_tipo)
    fgts_registros = sum(row["count"] for row in fgts_por_tipo)

    # INSS total
    inss_sql = """
        SELECT COUNT(*) AS cnt,
               COALESCE(SUM(valor), 0) AS soma
        FROM inss_guias
        WHERE valor IS NOT NULL
    """
    inss_row = (await db.execute(text(inss_sql))).mappings().one()
    inss_total = float(inss_row["soma"])
    inss_registros = int(inss_row["cnt"])

    # Total de docs e taxa de extração
    total_docs = (await db.execute(text("SELECT COUNT(*) FROM onvio_documents"))).scalar() or 0

    cats_placeholder = ", ".join(f"'{c}'" for c in _CATEGORIAS_FISCAIS)
    total_fiscais = (
        await db.execute(text(f"SELECT COUNT(*) FROM onvio_documents WHERE categoria IN ({cats_placeholder})"))
    ).scalar() or 0

    docs_extraidos = (
        await db.execute(text("SELECT COUNT(*) FROM onvio_documents WHERE extraido_em IS NOT NULL"))
    ).scalar() or 0

    taxa = round(docs_extraidos / total_fiscais * 100, 1) if total_fiscais else 0.0

    # Distribuição por confiança
    conf_alta = (
        await db.execute(text("SELECT COUNT(*) FROM onvio_documents WHERE confianca_extracao >= 0.90"))
    ).scalar() or 0
    conf_media = (
        await db.execute(
            text("SELECT COUNT(*) FROM onvio_documents WHERE confianca_extracao >= 0.70 AND confianca_extracao < 0.90")
        )
    ).scalar() or 0
    conf_baixa = (
        await db.execute(text("SELECT COUNT(*) FROM onvio_documents WHERE confianca_extracao < 0.70"))
    ).scalar() or 0

    return {
        "fgts": {
            "por_tipo": fgts_por_tipo,
            "total_brl": fgts_total,
            "total_registros": fgts_registros,
        },
        "inss": {
            "total_brl": inss_total,
            "total_registros": inss_registros,
        },
        "consolidado": {
            "valor_total_fiscal_brl": round(fgts_total + inss_total, 2),
            "total_docs_sistema": total_docs,
            "total_docs_fiscais": total_fiscais,
            "docs_extraidos": docs_extraidos,
            "taxa_extracao_pct": taxa,
        },
        "confianca": {
            "alta_auto_save": conf_alta,
            "media_revisao_manual": conf_media,
            "baixa_rejeitado": conf_baixa,
        },
    }
