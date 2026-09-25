"""Controller para modulo Fiscal - Endpoints de NF-e, NFS-e, SPED, Retencoes."""
# pylint: disable=too-many-lines,too-many-arguments,too-many-positional-arguments
# pylint: disable=unused-argument,fixme,logging-fstring-interpolation
# pylint: disable=raise-missing-from,redefined-outer-name,no-else-return

import logging
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user, require_permission
from core.database.session import get_db
from modules.financial.repositories.fiscal_repository import FiscalRepository
from modules.financial.schemas.fiscal_schemas import (
    CalculoLucroRealRequest,
    CalculoSimplesRequest,
    ComparativoRegimesRequest,
    ObrigacaoFiscalCreate,
    ObrigacaoFiscalListResponse,
    ObrigacaoFiscalResponse,
    ObrigacaoFiscalUpdate,
    RetencoesNFSeRequest,
    VerificacaoLimiteSimplesRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fiscal", tags=["Fiscal"])


def get_repository(db: AsyncSession = Depends(get_db)) -> FiscalRepository:
    """Retorna instancia do repository fiscal."""
    return FiscalRepository(db)


# ============================================================
# CFOP Endpoints
# ============================================================


# ============================================================
# NCM Endpoints
# ============================================================


# ============================================================
# Retencao Federal Endpoints
# ============================================================


# ============================================================
# NF-e Endpoints
# ============================================================


async def _atualizar_nota(db: AsyncSession, tabela: str, nota_id, data: dict, label: str) -> dict:
    """Atualiza uma nota fiscal (nfses/nfes) em rascunho via SQL cru na tabela REAL.

    Os models NFSe/NFe apontam para `nfse`/`nfe` (inexistentes) — todo query via model quebra;
    o LIST/GET já usam SQL cru na tabela real. Aqui idem: só grava colunas que EXISTEM na tabela.
    `tabela` é literal do endpoint (nunca input do usuário); nomes de coluna são whitelist do
    information_schema — sem risco de injeção."""
    row = (
        (await db.execute(text(f"SELECT id, status FROM {tabela} WHERE id = :id AND active IS true"), {"id": nota_id}))
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"{label} nao encontrada")
    if (row["status"] or "") != "rascunho":
        raise HTTPException(status_code=400, detail=f"Apenas {label} em rascunho pode ser editada")
    real_cols = {
        r[0]
        for r in (
            await db.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                {"t": tabela},
            )
        ).fetchall()
    }
    campos = {k: v for k, v in (data or {}).items() if v is not None and k in real_cols}
    if campos:
        sets = ", ".join(f"{k} = :{k}" for k in campos)
        await db.execute(
            text(f"UPDATE {tabela} SET {sets}, updated_at = now() WHERE id = :id"),
            {**campos, "id": nota_id},
        )
        await db.commit()
    updated = (await db.execute(text(f"SELECT * FROM {tabela} WHERE id = :id"), {"id": nota_id})).mappings().first()
    return dict(updated) if updated else {}


# ============================================================
# NFS-e Endpoints
# ============================================================


@router.get("/nfse")
async def listar_nfses(
    condominio_id: UUID | None = None,
    empresa_id: UUID | None = None,
    status: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_permission("fiscal:nfse:read")),
):
    """Lista NFS-e emitidas da fonte autoritativa `nfse_emitidas_nacional`.
    SÓ diretoria (require_permission fiscal:nfse:read; admin/perfil `all` passa) — a base
    contém os DOIS CNPJ e não pode vazar p/ qualquer logado. Passe `empresa_id` para
    escopar por CNPJ (Eletrônica/Patrimonial); sem ele, retorna consolidado (backward-compat).
    Devolve um array no formato que a tela consome. condominio_id é ignorado no filtro
    (as NFS-e da empresa pertencem aos condominio_ids reais e o front injeta um placeholder
    de dev). A tabela nacional nao tem coluna status/active/numero_rps/serie_rps/codigo_verificacao:
    todas as linhas sao autorizadas; competencia (varchar 'YYYY-MM') substitui data_competencia."""
    conds: list[str] = []
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    if empresa_id:
        conds.append("empresa_id = :empresa_id")
        params["empresa_id"] = str(empresa_id)
    # Filtro por status: a fonte so contem notas autorizadas. Se pedirem outro
    # status, o resultado e vazio (nao existem canceladas/rejeitadas aqui).
    if status and status.lower() not in ("autorizada", "autorizado", "authorized"):
        conds.append("1 = 0")
    if search:
        conds.append("(tomador_nome ILIKE :s OR numero::text ILIKE :s)")
        params["s"] = f"%{search}%"
    where = (" AND ".join(conds)) if conds else "TRUE"
    rows = (
        (
            await db.execute(
                text(
                    "SELECT chave_acesso, numero, competencia, "
                    "tomador_nome, tomador_cnpj, "
                    "valor_servicos, data_emissao, created_at "
                    f"FROM nfse_emitidas_nacional WHERE {where} "
                    "ORDER BY data_emissao DESC NULLS LAST, numero DESC LIMIT :limit OFFSET :offset"
                ),
                params,
            )
        )
        .mappings()
        .all()
    )

    def _iso(v):
        return v.isoformat() if v else None

    return [
        {
            "id": r["chave_acesso"]
            or r["numero"],  # é a CHAVE (50 dígitos), não UUID: o detalhe/DANFSe é /nfse-emitida/{chave}/danfse
            "chave_acesso": r["chave_acesso"],
            "danfse_url": f"/api/v1/financial/fiscal/nfse-emitida/{r['chave_acesso']}/danfse"
            if r["chave_acesso"]
            else None,
            "number": r["numero"],
            "series": None,
            "recipient_name": r["tomador_nome"],
            "recipient_document": r["tomador_cnpj"],
            "access_key": r["chave_acesso"],
            "amount": float(r["valor_servicos"] or 0),
            "total_amount": float(r["valor_servicos"] or 0),
            "net_amount": float(r["valor_servicos"] or 0),
            "status": "autorizada",
            "issue_date": _iso(r["data_emissao"]),
            "competence_date": r["competencia"],
            "created_at": _iso(r["created_at"]),
            # aliases PT p/ robustez
            "numero": r["numero"],
            "valor": float(r["valor_servicos"] or 0),
        }
        for r in rows
    ]


# ============================================================
# SPED Endpoints
# ============================================================


# ============================================================
# Obrigacao Fiscal Endpoints
# ============================================================


@router.post(
    "/obrigacao",
    response_model=ObrigacaoFiscalResponse,
    status_code=status.HTTP_201_CREATED,
)
async def criar_obrigacao(
    data: ObrigacaoFiscalCreate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:obrigacao:create")),
) -> ObrigacaoFiscalResponse:
    """Cria obrigacao fiscal."""
    obrigacao = await repo.create_obrigacao(
        data.condominio_id,
        data.model_dump(exclude={"condominio_id"}),
    )
    return ObrigacaoFiscalResponse.model_validate(obrigacao)


@router.get("/obrigacao", response_model=ObrigacaoFiscalListResponse)
async def listar_obrigacoes(
    condominio_id: UUID,
    tipo: str | None = None,
    status: str | None = None,
    mes: int | None = None,
    ano: int | None = None,
    vencimento_inicio: date | None = None,
    vencimento_fim: date | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> ObrigacaoFiscalListResponse:
    """Lista obrigacoes fiscais."""
    obrigacoes, total = await repo.list_obrigacoes(
        condominio_id=condominio_id,
        tipo=tipo,
        status=status,
        mes=mes,
        ano=ano,
        vencimento_inicio=vencimento_inicio,
        vencimento_fim=vencimento_fim,
        page=page,
        page_size=page_size,
    )

    pendentes = await repo.get_obrigacoes_pendentes(condominio_id)
    atrasadas = await repo.get_obrigacoes_atrasadas(condominio_id)

    return ObrigacaoFiscalListResponse(
        items=[ObrigacaoFiscalResponse.model_validate(o) for o in obrigacoes],
        total=total,
        proximas_a_vencer=len(pendentes),
        atrasadas=len(atrasadas),
    )


@router.get("/obrigacao/{obrigacao_id}", response_model=ObrigacaoFiscalResponse)
async def obter_obrigacao(
    obrigacao_id: UUID,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(get_current_user),
) -> ObrigacaoFiscalResponse:
    """Busca obrigacao por ID."""
    obrigacao = await repo.get_obrigacao_by_id(obrigacao_id)
    if not obrigacao:
        raise HTTPException(status_code=404, detail="Obrigacao nao encontrada")
    return ObrigacaoFiscalResponse.model_validate(obrigacao)


@router.patch("/obrigacao/{obrigacao_id}", response_model=ObrigacaoFiscalResponse)
async def atualizar_obrigacao(
    obrigacao_id: UUID,
    data: ObrigacaoFiscalUpdate,
    repo: FiscalRepository = Depends(get_repository),
    current_user: dict = Depends(require_permission("fiscal:obrigacao:update")),
) -> ObrigacaoFiscalResponse:
    """Atualiza obrigacao fiscal."""
    obrigacao = await repo.update_obrigacao(obrigacao_id, data.model_dump(exclude_unset=True))
    if not obrigacao:
        raise HTTPException(status_code=404, detail="Obrigacao nao encontrada")
    return ObrigacaoFiscalResponse.model_validate(obrigacao)


# ============================================================
# Simples Nacional / DAS Endpoints
# ============================================================


# ============================================================
# SUFRAMA Endpoints
# ============================================================


# ============================================================
# Dashboard e Estatisticas
# ============================================================


@router.get("/dashboard")
async def obter_dashboard_fiscal(
    condominio_id: UUID | None = None,
    mes: int = Query(default=None, ge=1, le=12),
    ano: int = Query(default=None, ge=2000),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Dashboard fiscal — lê a tabela REAL `nfses` (o model antigo apontava p/ `nfse`,
    inexistente, causando 500). Retorna o shape consumido pela tela (stats.*)."""
    if not mes:
        mes = date.today().month
    if not ano:
        ano = date.today().year

    _viva = "coalesce(cancelada,false) = false"
    total_nfse = (await db.execute(text(f"SELECT count(*) FROM nfse_emitidas_nacional WHERE {_viva}"))).scalar() or 0
    total_nfse_mes = (
        await db.execute(
            text(
                f"SELECT count(*) FROM nfse_emitidas_nacional WHERE {_viva} "
                "AND CAST(substr(competencia, 6, 2) AS int) = :m "
                "AND CAST(left(competencia, 4) AS int) = :a"
            ),
            {"m": mes, "a": ano},
        )
    ).scalar() or 0
    valor_total = (
        await db.execute(text(f"SELECT COALESCE(SUM(valor_servicos), 0) FROM nfse_emitidas_nacional WHERE {_viva}"))
    ).scalar() or 0
    valor_mes = (
        await db.execute(
            text(
                f"SELECT COALESCE(SUM(valor_servicos), 0) FROM nfse_emitidas_nacional WHERE {_viva} "
                "AND CAST(substr(competencia, 6, 2) AS int) = :m AND CAST(left(competencia, 4) AS int) = :a"
            ),
            {"m": mes, "a": ano},
        )
    ).scalar() or 0
    try:
        obrig_pend = (
            await db.execute(
                text("SELECT count(*) FROM fiscal_obligations WHERE active = true AND status = 'pendente'")
            )
        ).scalar() or 0
    except Exception:  # noqa: BLE001
        obrig_pend = 0

    notas_recentes = [
        {
            "tipo": "NFS-e",
            "numero": r["numero"],
            "valor": float(r["valor_servicos"] or 0),
            "data": r["data_emissao"].isoformat() if r["data_emissao"] else None,
            # nfse_emitidas_nacional so contem notas validas (cStat 100)
            "status": "autorizada",
        }
        for r in (
            await db.execute(
                text(
                    "SELECT numero, valor_servicos, data_emissao "
                    "FROM nfse_emitidas_nacional ORDER BY data_emissao DESC NULLS LAST LIMIT 5"
                )
            )
        )
        .mappings()
        .all()
    ]

    return {
        "stats": {
            "total_nfse_emitidas": int(total_nfse),
            "total_nfe_emitidas": 0,
            "total_nfe_mes": int(total_nfse_mes),  # chave histórica: é contagem de NFS-e (a empresa não emite NF-e)
            "total_nfse_mes": int(total_nfse_mes),
            "valor_total_nfse": float(valor_total),  # acumulado histórico
            "valor_total_nfse_historico": float(valor_total),
            "valor_nfse_mes": float(valor_mes),
            "obrigacoes_pendentes": int(obrig_pend),
        },
        "notas_recentes": notas_recentes,
        "obrigacoes_proximas": [],
        "alertas": [],
        "grafico_impostos": [],
        "grafico_notas": [],
    }


# ── Tax Calculator Multi-Regime ───────────────────────────────────────────────

from decimal import Decimal  # noqa: E402

from modules.financial.agents.tax_calculator import TaxCalculatorAgent  # noqa: E402

_tax_agent = TaxCalculatorAgent()


@router.post("/calcular/simples", summary="Calcular DAS Simples Nacional", status_code=201)
async def calcular_simples_nacional(
    dados: CalculoSimplesRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Calcula DAS do Simples Nacional (Anexo III - vigilância/serviços).
    Aplica liminares automaticamente se informadas.
    """
    resultado = _tax_agent.calcular_simples(
        receita_mes=Decimal(str(dados.receita_mes)),
        rbt12=Decimal(str(dados.rbt12)),
        liminares=dados.liminares,
    )
    return {
        "regime": "simples_nacional",
        "anexo": resultado.anexo,
        "receita_bruta_mes": float(resultado.receita_bruta_mes),
        "receita_bruta_12_meses": float(resultado.receita_bruta_12_meses),
        "aliquota_nominal": f"{float(resultado.aliquota_nominal) * 100:.2f}%",
        "aliquota_efetiva": f"{float(resultado.aliquota_efetiva) * 100:.2f}%",
        "valor_das": float(resultado.valor_das),
        "carga_tributaria": f"{float(resultado.carga_tributaria_percentual):.2f}%",
        "distribuicao": resultado.distribuicao,
        "liminares_aplicadas": resultado.liminares_aplicadas,
        "economia_liminares": float(resultado.economia_liminares),
    }


@router.post("/calcular/lucro-real", summary="Calcular impostos Lucro Real", status_code=201)
async def calcular_lucro_real(
    dados: CalculoLucroRealRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Calcula IRPJ, CSLL, PIS (nc), COFINS (nc), ISS no regime Lucro Real.
    """
    resultado = _tax_agent.calcular_lucro_real(
        receita_mes=Decimal(str(dados.receita_mes)),
        receita_trimestre=Decimal(str(dados.receita_trimestre)),
        custos_dedutiveis_mes=Decimal(str(dados.custos_dedutiveis_mes)),
    )
    return {
        "regime": "lucro_real",
        "receita_bruta_mes": float(resultado.receita_bruta_mes),
        "lucro_presumido_base": float(resultado.lucro_bruto),
        "irpj": float(resultado.irpj),
        "irpj_adicional": float(resultado.irpj_adicional),
        "csll": float(resultado.csll),
        "pis": float(resultado.pis),
        "cofins": float(resultado.cofins),
        "iss": float(resultado.iss),
        "total_impostos_mes": float(resultado.total_impostos_mes),
        "carga_tributaria": f"{float(resultado.carga_tributaria_percentual):.2f}%",
        "detalhamento": [
            {
                "nome": d.nome,
                "aliquota": float(d.aliquota),
                "base": float(d.base_calculo),
                "valor": float(d.valor),
            }
            for d in resultado.detalhamento
        ],
    }


@router.post("/calcular/comparativo-regimes", summary="Comparar Simples vs Lucro Real", status_code=201)
async def comparar_regimes(
    dados: ComparativoRegimesRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Compara carga tributária anual entre Simples Nacional e Lucro Real.
    Útil para decisão de mudança de regime.
    """
    resultado = _tax_agent.comparar_regimes(
        receita_anual=Decimal(str(dados.receita_anual)),
        custos_dedutiveis_anual=Decimal(str(dados.custos_dedutiveis_anual)),
        liminares=dados.liminares,
    )
    return {
        "receita_bruta_anual": float(resultado.receita_bruta_anual),
        "simples_nacional": {
            "total_anual": float(resultado.simples_nacional_total),
            "percentual": f"{float(resultado.simples_nacional_percentual):.2f}%",
        },
        "lucro_real": {
            "total_anual": float(resultado.lucro_real_total),
            "percentual": f"{float(resultado.lucro_real_percentual):.2f}%",
        },
        "economia_simples_anual": float(resultado.economia_simples),
        "recomendacao": resultado.recomendacao,
        "observacoes": resultado.observacoes,
    }


@router.post("/calcular/retencoes-nfse", summary="Calcular retenções na fonte NFS-e", status_code=201)
async def calcular_retencoes_nfse(
    dados: RetencoesNFSeRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Calcula INSS, IR, CSLL, PIS, COFINS, ISS retidos na fonte.
    Aplica liminares automaticamente.
    """
    # ⚠️ O regime é OBRIGATÓRIO, e o default `simples_nacional` que existia no schema era uma
    # armadilha. Sem liminar os dois regimes dão o mesmo total, então o buraco ficava
    # invisível — mas com liminar marcada e regime em branco o motor aplicava a liminar da
    # PATRIMONIAL a um cálculo da ELETRÔNICA (medido em 15/08/2026: R$1.850,00 contra
    # R$2.215,00 numa nota de R$10.000). Retenção decide quanto o cliente deposita; lacuna
    # aqui não se completa com palpite.
    #
    # A recusa fica AQUI, e não no schema, para a mensagem sair como STRING: o 422 do
    # Pydantic devolve `detail` como lista de objetos e o front imprimia "[object Object]".
    if not dados.regime_empresa:
        raise HTTPException(
            status_code=422,
            detail=(
                "Escolha o regime do emissor antes de calcular: simples_nacional "
                "(Patrimonial) ou lucro_real (Eletrônica). A retenção muda com o regime "
                "quando há liminar, e sem essa informação o valor sairia errado."
            ),
        )

    resultado = _tax_agent.calcular_retencoes_nfse(
        valor_servico=Decimal(str(dados.valor_servico)),
        regime_empresa=dados.regime_empresa,
        liminares=dados.liminares,
    )
    return {
        "valor_servico": float(resultado.valor_servico),
        "retencoes": {
            "inss_11pct": float(resultado.inss),
            "ir_1_5pct": float(resultado.ir),
            "csll_1pct": float(resultado.csll),
            "pis_0_65pct": float(resultado.pis),
            "cofins_3pct": float(resultado.cofins),
            "iss_5pct": float(resultado.iss),
        },
        "total_retencoes": float(resultado.total_retencoes),
        "valor_liquido_receber": float(resultado.valor_liquido),
        "liminares_aplicadas": resultado.liminares_aplicadas,
    }


@router.post("/calcular/verificar-limite-simples", summary="Verificar limite do Simples Nacional", status_code=201)
async def verificar_limite_simples(
    dados: VerificacaoLimiteSimplesRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Verifica se empresa está próxima ou além do limite do Simples Nacional.
    """
    return _tax_agent.verificar_limite_simples(
        rbt12=Decimal(str(dados.rbt12)),
    )


async def _buscar_xml_nfse(db, chave: str, cert_path: str | None, detalhe: dict | None = None) -> str | None:
    """A NFS-e assinada pelo fisco, pela chave, guardada em `nfse_emitidas_nacional.xml_nfse`.

    Leitura pura (`GET /nfse/{chave}`, mTLS) — não emite, não altera nada no fisco. É a única
    fonte dos blocos do DANFSe v2.0 que a tabela não tem: endereço do tomador, DPS, código da
    NBS, tributação federal e IBS/CBS. Falha de rede ou certificado NÃO derruba a impressão:
    devolve `None` e o DANFSe sai com «-» nos blocos que dependem do XML.

    O fisco **não** serve o PDF: `GET /nfse/DANFSe/{chave}` devolve 404 text/html (a página do
    IIS), medido em 25/09/2026 contra a produção. Serve o XML; o PDF é desenhado aqui.
    """
    import os  # noqa: PLC0415

    from sqlalchemy import text as _sql  # noqa: PLC0415

    try:
        from modules.government_integrations.core.nfse_nacional import (  # noqa: PLC0415
            AmbienteNacional,
            NFSeNacionalManager,
        )

        # ⚠️ A SENHA VEM DA MESMA EMPRESA QUE O CAMINHO — conserto de 25/09/2026.
        #
        # Aqui havia `certificado_path=cert_path` (da empresa) e
        # `certificado_senha=os.getenv("CERT_A1_PASSWORD")` (do ambiente). Assimetria:
        # caminho de uma fonte, senha de outra. Funciona por acaso enquanto só uma empresa
        # emite — e quebra em silêncio na segunda.
        #
        # Medido: as 26 NFS-e da PATRIMONIAL voltavam `status=erro_rede` porque o
        # `patrimonial.pfx` era aberto com a senha da Eletrônica. O relatório dizia «ADN
        # respondeu sem XML», que é falso: o ADN nunca foi consultado. Achado testando o ADN
        # com a nota nº 120, que o backfill dava como vazia e o fisco devolveu com 7.601
        # caracteres.
        senha = ""
        if cert_path:
            senha = (
                await db.execute(
                    _sql(
                        "SELECT coalesce(certificado_a1_senha,'') FROM empresas"
                        " WHERE coalesce(certificado_a1_path,'') = CAST(:p AS VARCHAR) LIMIT 1"
                    ),
                    {"p": cert_path},
                )
            ).scalar() or ""
        mgr = NFSeNacionalManager(
            ambiente=AmbienteNacional.PRODUCAO,
            certificado_path=cert_path or os.getenv("CERT_A1_PATH"),
            certificado_senha=senha or os.getenv("CERT_A1_PASSWORD"),
        )
        from starlette.concurrency import run_in_threadpool  # noqa: PLC0415

        fora = await run_in_threadpool(mgr.consultar_nfse, chave)
    except Exception as exc:  # noqa: BLE001 — imprimir a nota nunca depende do fisco estar de pé
        logger.warning(f"DANFSe {chave}: XML não veio do ADN ({type(exc).__name__}: {exc})")
        if detalhe is not None:
            detalhe["motivo"] = f"excecao:{type(exc).__name__}"
        return None
    xml = fora.get("xml_nfse")
    # `detalhe` existe para quem chama EM LOTE: sem ele, «falha de rede» e «o fisco não tem»
    # viram a mesma coisa — `None` —, e um relatório que soma os dois diz «o ADN não tem
    # essas notas» quando a verdade é «o nosso certificado não conseguiu perguntar».
    if detalhe is not None:
        detalhe["status"] = str(fora.get("status") or "")
        detalhe["c_stat"] = str(fora.get("c_stat") or "")
    if not xml:
        logger.info(f"DANFSe {chave}: ADN respondeu '{fora.get('status')}' sem XML.")
        return None
    await db.execute(
        _sql("UPDATE nfse_emitidas_nacional SET xml_nfse = :x WHERE chave_acesso = :c"),
        {"x": xml, "c": chave},
    )
    await db.commit()
    return xml


@router.get("/nfse-emitida/{chave}/danfse", summary="DANFSe (PDF) da NFS-e emitida (portal nacional)")
async def nfse_emitida_danfse(
    chave: str,
    download: bool = Query(False, description="1 = baixar; 0 = abrir inline"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """DANFSe da NFS-e EMITIDA (nfse_emitidas_nacional). Prestador = empresa emitente
    (join real em `empresas`, escopado por chave). Campos estruturados; a chave permite
    verificar a nota oficial no portal nacional."""
    from fastapi.responses import Response as _Resp
    from sqlalchemy import text as _t

    from modules.gedeon.services.nfse_danfse_generator import garantir_coluna_xml, gerar_danfse_de_emitida

    await garantir_coluna_xml(db)
    row = (
        (
            await db.execute(
                _t(
                    "SELECT e.chave_acesso, e.numero, e.competencia, e.data_emissao, e.tomador_cnpj, "
                    "e.tomador_nome, e.valor_servicos, e.iss_aliquota, e.iss_valor, e.inss_retido, "
                    "e.valor_liquido, e.descricao, e.codigo_servico, e.cancelada, e.xml_nfse, "
                    "emp.cnpj AS emit_cnpj, emp.razao_social AS emit_nome, "
                    "emp.inscricao_municipal AS emit_im, emp.certificado_a1_path "
                    "FROM nfse_emitidas_nacional e LEFT JOIN empresas emp ON emp.id = e.empresa_id "
                    "WHERE e.chave_acesso = :c LIMIT 1"
                ),
                {"c": chave},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="NFS-e emitida não encontrada")
    dados = dict(row)
    if not dados.get("xml_nfse"):
        dados["xml_nfse"] = await _buscar_xml_nfse(db, chave, dados.get("certificado_a1_path"))
    try:
        pdf = gerar_danfse_de_emitida(dados)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"falha ao gerar DANFSe: {exc}") from exc
    disp = "attachment" if download else "inline"
    nome = f"danfse_{row.get('numero') or chave[:14]}.pdf"
    return _Resp(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'{disp}; filename="{nome}"'}
    )
