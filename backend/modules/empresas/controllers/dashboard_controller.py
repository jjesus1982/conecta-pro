"""Dashboard consolidado multi-empresa — dados REAIS do banco."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, get_tenant_id
from core.database import get_db
from modules.empresas.agents.obligations_monitor import ObligationsMonitorAgent
from modules.empresas.models.empresa import Empresa, Liminar
from modules.financial.agents.profitability_analyzer import ProfitabilityAnalyzerAgent
from modules.financial.agents.tax_calculator import TaxCalculatorAgent

router = APIRouter(prefix="/dashboard", tags=["Dashboard Multi-Empresa"])
_tax = TaxCalculatorAgent()
_profit = ProfitabilityAnalyzerAgent()
_obs = ObligationsMonitorAgent()
_DEFAULT_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _resolve_condominio_id(db: AsyncSession, condominio_id: UUID) -> UUID:
    """Resolve tenant padrão para o condominio real do banco."""
    if condominio_id == _DEFAULT_TENANT_ID:
        result = await db.execute(text("SELECT id FROM condominios LIMIT 1"))
        row = result.fetchone()
        if row:
            return UUID(str(row[0]))
    return condominio_id


def _inferir_empresa_por_tipo(tipo_servico: str, empresas: list[Empresa]) -> Empresa | None:
    """Infere qual empresa presta um tipo de servico baseado em tipos_servicos cadastrados."""
    for emp in empresas:
        tipos = emp.tipos_servicos or []
        if tipo_servico in tipos:
            return emp
    return None


async def _buscar_empresas(db: AsyncSession, condominio_id: UUID) -> list[dict]:
    """Busca empresas com liminares ativas."""
    stmt = select(Empresa).where(Empresa.condominio_id == condominio_id).order_by(Empresa.is_principal.desc())
    result = await db.execute(stmt)
    empresas = list(result.scalars().all())

    dados = []
    for emp in empresas:
        # Buscar liminares concedidas
        lim_stmt = select(Liminar).where(and_(Liminar.empresa_id == emp.id, Liminar.status == "concedida"))
        lim_result = await db.execute(lim_stmt)
        liminares_ativas = [lim.tipo for lim in lim_result.scalars().all()]

        dados.append(
            {
                "empresa": emp,
                "liminares_ativas": liminares_ativas,
            }
        )
    return dados


async def _receita_por_empresa(db: AsyncSession, empresas: list[Empresa], mes: int, ano: int) -> dict[str, dict]:
    """Calcula receita real por empresa, buscando de contratos e NFS-e."""
    receitas: dict[str, dict] = {}

    for emp in empresas:
        slug = emp.slug
        receitas[slug] = {
            "contratos_ativos": 0,
            "valor_mensal_contratos": Decimal("0"),
            "nfse_emitidas": 0,
            "valor_nfse": Decimal("0"),
            "postos_ativos": 0,
            "fonte": "sem_dados",
        }

        # 1. Buscar contratos ativos por tipo de servico desta empresa
        tipos = emp.tipos_servicos or []
        if tipos:
            try:
                contratos_sql = text("""
                    SELECT COUNT(*) as total, COALESCE(SUM(monthly_value), 0) as valor
                    FROM client_contracts
                    WHERE status = 'active'
                    AND service_type::text = ANY(:tipos)
                """)
                r = await db.execute(contratos_sql, {"tipos": tipos})
                row = r.fetchone()
                if row and row[0] > 0:
                    receitas[slug]["contratos_ativos"] = row[0]
                    receitas[slug]["valor_mensal_contratos"] = Decimal(str(row[1]))
                    receitas[slug]["fonte"] = "contratos"
            except Exception:
                await db.rollback()  # Reset transaction after enum error

        # 2. Buscar NFS-e emitidas no mes/ano (fonte da verdade: nfse_emitidas_nacional).
        #    A tabela nova nao tem prestador_cnpj: e um unico CNPJ (35.710.481/0001-03,
        #    a empresa principal). Atribuimos as NFS-e emitidas a empresa cujo CNPJ bate
        #    com o CNPJ prestador dessas notas. competencia e varchar 'YYYY-MM'.
        cnpj_prestador_nfse = "35.710.481/0001-03"
        cnpj_emp_limpo = (emp.cnpj or "").replace(".", "").replace("/", "").replace("-", "")
        cnpj_prestador_limpo = cnpj_prestador_nfse.replace(".", "").replace("/", "").replace("-", "")
        if emp.cnpj and cnpj_emp_limpo == cnpj_prestador_limpo:
            competencia = f"{ano:04d}-{mes:02d}"
            nfse_sql = text("""
                SELECT COUNT(*) as total, COALESCE(SUM(valor_servicos), 0) as valor
                FROM nfse_emitidas_nacional
                WHERE competencia = :competencia
            """)
            r = await db.execute(nfse_sql, {"competencia": competencia})
            row = r.fetchone()
            if row and row[0] > 0:
                receitas[slug]["nfse_emitidas"] = row[0]
                receitas[slug]["valor_nfse"] = Decimal(str(row[1]))
                if receitas[slug]["fonte"] == "sem_dados":
                    receitas[slug]["fonte"] = "nfse"
                else:
                    receitas[slug]["fonte"] = "contratos+nfse"

        # 3. Contar postos ativos por tipo de servico desta empresa
        if tipos:
            try:
                postos_sql = text("""
                    SELECT COUNT(*) FROM posts
                    WHERE status = 'active' AND post_type::text = ANY(:tipos)
                """)
                r = await db.execute(postos_sql, {"tipos": tipos})
                row = r.fetchone()
                if row:
                    receitas[slug]["postos_ativos"] = row[0]
            except Exception:
                await db.rollback()

    return receitas


def _melhor_receita(dados_empresa: dict) -> Decimal:
    """Retorna a melhor estimativa de receita: contratos > nfse > 0.

    Usado como FALLBACK (ex.: dashboard contabil sem lancamentos no razao).
    Prioriza a soma mensal de contratos como estimativa de recorrencia.
    """
    if dados_empresa["valor_mensal_contratos"] > 0:
        return dados_empresa["valor_mensal_contratos"]
    if dados_empresa["valor_nfse"] > 0:
        return dados_empresa["valor_nfse"]
    return Decimal("0")


def _receita_fiscal(dados_empresa: dict) -> tuple[Decimal, str]:
    """Receita para o dashboard FISCAL: fonte da verdade = NFS-e emitidas no mes.

    A visao fiscal deve refletir o faturamento efetivamente documentado (notas
    cStat 100 do mes), que varia mes a mes — nao a soma FIXA de contratos, que
    superestima meses parciais (ex.: junho tem 10 NFS-e reais, nao 6 contratos
    somados). Contratos ficam apenas como estimativa de fallback para meses sem
    NFS-e emitida (ex.: mes corrente em andamento).

    Retorna (receita, fonte).
    """
    if dados_empresa["valor_nfse"] > 0:
        return dados_empresa["valor_nfse"], "nfse"
    if dados_empresa["valor_mensal_contratos"] > 0:
        return dados_empresa["valor_mensal_contratos"], "contratos_estimativa"
    return Decimal("0"), "sem_dados"


@router.get("/fiscal/grupo")
async def dashboard_fiscal_grupo(
    mes: int = Query(default=date.today().month),
    ano: int = Query(default=date.today().year),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Dashboard fiscal consolidado do grupo — dados reais."""
    condominio_id = await _resolve_condominio_id(db, UUID(get_tenant_id(current_user)))
    empresas_dados = await _buscar_empresas(db, condominio_id)

    if not empresas_dados:
        return {
            "periodo": f"{mes:02d}/{ano}",
            "status": "sem_dados",
            "mensagem": "Nenhuma empresa cadastrada. Cadastre empresas em Multi-Empresa > Gestao.",
        }

    empresas = [e["empresa"] for e in empresas_dados]
    receitas = await _receita_por_empresa(db, empresas, mes, ano)

    resultado_empresas = {}
    total_receita = Decimal("0")
    total_impostos = Decimal("0")
    total_economia_liminares = Decimal("0")

    for ed in empresas_dados:
        emp = ed["empresa"]
        liminares = ed["liminares_ativas"]
        slug = emp.slug
        rec = receitas.get(slug, {})
        # Fonte fiscal = NFS-e efetivamente emitidas no mes (varia mes a mes).
        # Contratos so entram como estimativa em meses sem nota emitida.
        receita_mes, fonte_fiscal = _receita_fiscal(rec)
        total_receita += receita_mes

        empresa_result = {
            "slug": slug,
            "razao_social": emp.razao_social,
            "cnpj": emp.cnpj,
            "regime": emp.regime_tributario,
            "status": emp.status,
            "receita_mes": float(receita_mes),
            "fonte_receita": fonte_fiscal,
            "contratos_ativos": rec.get("contratos_ativos", 0),
            "nfse_emitidas": rec.get("nfse_emitidas", 0),
            "postos_ativos": rec.get("postos_ativos", 0),
        }

        # Calcular impostos apenas se houver receita
        if receita_mes > 0:
            if emp.regime_tributario == "lucro_real":
                lr = _tax.calcular_lucro_real(
                    receita_mes=receita_mes,
                    receita_trimestre=receita_mes * 3,
                )
                empresa_result["impostos_mes"] = float(lr.total_impostos_mes)
                empresa_result["carga_pct"] = float(lr.carga_tributaria_percentual)
                empresa_result["detalhamento"] = {
                    "irpj": float(lr.irpj + lr.irpj_adicional),
                    "csll": float(lr.csll),
                    "pis": float(lr.pis),
                    "cofins": float(lr.cofins),
                    "iss": float(lr.iss),
                }
                total_impostos += lr.total_impostos_mes

            elif emp.regime_tributario == "simples_nacional":
                rbt12 = receita_mes * 12
                sn = _tax.calcular_simples(
                    receita_mes=receita_mes,
                    rbt12=rbt12,
                    liminares=[],
                )
                empresa_result["impostos_sem_liminar"] = float(sn.valor_das)
                empresa_result["carga_pct_sem"] = float(sn.carga_tributaria_percentual)

                if liminares:
                    sn_lim = _tax.calcular_simples(
                        receita_mes=receita_mes,
                        rbt12=rbt12,
                        liminares=liminares,
                    )
                    empresa_result["impostos_com_liminar"] = float(sn_lim.valor_das)
                    empresa_result["carga_pct_com"] = float(sn_lim.carga_tributaria_percentual)
                    economia = sn.valor_das - sn_lim.valor_das
                    empresa_result["economia_liminar"] = float(economia)
                    total_economia_liminares += economia
                    total_impostos += sn_lim.valor_das
                else:
                    total_impostos += sn.valor_das

                empresa_result["liminares_ativas"] = liminares
                empresa_result["status_liminares"] = "ativas" if liminares else "nenhuma_concedida"
        else:
            empresa_result["impostos_mes"] = 0
            empresa_result["carga_pct"] = 0
            empresa_result["aviso"] = "Sem receita registrada. Cadastre contratos ou emita NFS-e."

        resultado_empresas[slug] = empresa_result

    # Obrigacoes do mes
    cal = _obs.gerar_calendario_grupo(mes, ano)

    return {
        "periodo": f"{mes:02d}/{ano}",
        "status": "com_dados" if total_receita > 0 else "sem_receita",
        "grupo": {
            "total_empresas": len(empresas),
            "total_receita_mes": float(total_receita),
            "total_impostos_mes": float(total_impostos),
            "economia_liminares": float(total_economia_liminares),
            "fonte": "dados_reais",
        },
        "empresas": resultado_empresas,
        "obrigacoes_mes": {
            "total": cal.total_obrigacoes,
            "criticas": cal.criticas,
            "atrasadas": cal.atrasadas,
            "pendentes": cal.pendentes,
        },
    }


@router.get("/rentabilidade/grupo")
async def dashboard_rentabilidade_grupo(
    mes: int = Query(default=date.today().month),
    ano: int = Query(default=date.today().year),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Dashboard de rentabilidade consolidado — dados reais."""
    condominio_id = await _resolve_condominio_id(db, UUID(get_tenant_id(current_user)))
    empresas_dados = await _buscar_empresas(db, condominio_id)

    if not empresas_dados:
        return {
            "status": "sem_dados",
            "mensagem": "Nenhuma empresa cadastrada.",
        }

    empresas = [e["empresa"] for e in empresas_dados]

    # 1. Receita REAL por service_type (NAO dividir a receita da empresa entre
    # todos os tipos cadastrados — cada contrato tem seu service_type proprio).
    receita_sql = text("""
        SELECT service_type::text AS tipo,
               COUNT(*) AS contratos,
               COALESCE(SUM(monthly_value), 0) AS valor
        FROM client_contracts
        WHERE status = 'active'
        GROUP BY service_type::text
    """)
    rr = await db.execute(receita_sql)
    receita_por_tipo = {
        row[0]: {"contratos": row[1], "valor": Decimal(str(row[2]))}
        for row in rr.fetchall()
    }

    # 2. Custo direto REAL de folha por post_type (monthly_cost). Hoje TODOS os
    # postos tem monthly_cost=0, entao custo_cadastrado=False e NAO exibimos
    # margem (evita margem falsa de 78-94% para uma empresa de vigilancia cujo
    # maior custo e a folha).
    custos_sql = text("""
        SELECT post_type,
               COUNT(*) AS postos,
               COALESCE(SUM(monthly_cost), 0) AS custo_total,
               COALESCE(SUM(current_headcount), 0) AS headcount,
               COUNT(*) FILTER (WHERE monthly_cost > 0) AS postos_com_custo
        FROM posts
        WHERE status = 'active'
        GROUP BY post_type
    """)
    custos_result = await db.execute(custos_sql)
    custos_por_tipo = {
        row[0]: {
            "postos": row[1],
            "custo": Decimal(str(row[2])),
            "headcount": row[3],
            "postos_com_custo": row[4],
        }
        for row in custos_result.fetchall()
    }

    # Mapear cada service_type para a empresa que o presta (via tipos_servicos)
    def _empresa_do_tipo(tipo: str):
        for ed in empresas_dados:
            if tipo in (ed["empresa"].tipos_servicos or []):
                return ed
        # fallback: empresa principal (primeira)
        return empresas_dados[0] if empresas_dados else None

    resultados = []
    for tipo, rinfo in receita_por_tipo.items():
        receita_tipo = rinfo["valor"]
        if receita_tipo <= 0:
            continue

        ed = _empresa_do_tipo(tipo)
        emp = ed["empresa"]
        liminares = ed["liminares_ativas"]

        custo_info = custos_por_tipo.get(tipo, {})
        custo_direto = custo_info.get("custo", Decimal("0"))
        custo_cadastrado = custo_direto > 0

        item = {
            "tipo_servico": tipo,
            "empresa": emp.slug,
            "regime": emp.regime_tributario,
            "receita_mes": float(receita_tipo),
            "contratos_ativos": rinfo["contratos"],
            "custo_direto": float(custo_direto),
            "custo_cadastrado": custo_cadastrado,
            "postos_ativos": custo_info.get("postos", 0),
            "postos_com_custo": custo_info.get("postos_com_custo", 0),
            "headcount": custo_info.get("headcount", 0),
            "fonte": "dados_reais",
        }

        if custo_cadastrado:
            rbt12 = receita_tipo * 12
            r = _profit.calcular_rentabilidade(
                receita_bruta_mes=receita_tipo,
                custo_direto_mes=custo_direto,
                custo_indireto_mes=custo_direto * Decimal("0.15"),
                tipo_servico=tipo,
                empresa_slug=emp.slug,
                regime=emp.regime_tributario,
                rbt12=rbt12,
                liminares=liminares,
            )
            item.update(
                {
                    "impostos_mes": float(r.impostos_mes),
                    "lucro_liquido_mes": float(r.lucro_liquido_mes),
                    "margem_pct": float(r.margem_liquida_percentual),
                    "situacao": r.situacao,
                    "alertas": r.alertas,
                }
            )
        else:
            # Sem custo de folha cadastrado: NAO calcular margem (seria falsa).
            item.update(
                {
                    "impostos_mes": None,
                    "lucro_liquido_mes": None,
                    "margem_pct": None,
                    "situacao": "custo_nao_cadastrado",
                    "alertas": [
                        "Custo de folha nao cadastrado no posto (monthly_cost=0). "
                        "Margem nao exibida para evitar rentabilidade falsa."
                    ],
                }
            )
        resultados.append(item)

    if not resultados:
        return {
            "status": "sem_dados",
            "mensagem": "Sem contratos ativos. Cadastre contratos para ver a rentabilidade.",
            "resumo_grupo": {
                "total_receita_mes": 0,
                "total_lucro_liquido_mes": 0,
                "margem_media_pct": None,
            },
            "por_contrato": [],
            "ranking": [],
            "alertas": [],
        }

    total_receita = sum(r["receita_mes"] for r in resultados)
    # So consolidar lucro/margem sobre os tipos COM custo cadastrado (base honesta)
    com_custo = [r for r in resultados if r["custo_cadastrado"]]
    receita_com_custo = sum(r["receita_mes"] for r in com_custo)
    total_lucro = sum(r["lucro_liquido_mes"] for r in com_custo)
    margem_media = round(total_lucro / receita_com_custo * 100, 2) if receita_com_custo else None
    receita_sem_custo = total_receita - receita_com_custo

    return {
        "status": "com_dados",
        "resumo_grupo": {
            "total_receita_mes": total_receita,
            "total_lucro_liquido_mes": total_lucro,
            "margem_media_pct": margem_media,
            "receita_com_custo_cadastrado": receita_com_custo,
            "receita_sem_custo_cadastrado": receita_sem_custo,
            "total_receita_anual_estimada": total_receita * 12,
            "aviso_custo": None
            if receita_sem_custo == 0
            else (
                f"R$ {receita_sem_custo:,.2f} de receita sem custo de folha cadastrado "
                "(monthly_cost=0): margem nao consolidada para esses servicos."
            ),
        },
        "por_contrato": resultados,
        "ranking": sorted(
            com_custo, key=lambda x: x["margem_pct"], reverse=True
        ),
        "alertas": [a for r in resultados for a in (r.get("alertas") or [])],
    }


@router.get("/contabil/grupo")
async def dashboard_contabil_grupo(
    mes: int = Query(default=date.today().month),
    ano: int = Query(default=date.today().year),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Dashboard contabil consolidado — dados reais."""
    condominio_id = await _resolve_condominio_id(db, UUID(get_tenant_id(current_user)))
    empresas_dados = await _buscar_empresas(db, condominio_id)

    if not empresas_dados:
        return {
            "periodo": f"{mes:02d}/{ano}",
            "status": "sem_dados",
            "mensagem": "Nenhuma empresa cadastrada.",
        }

    empresas = [e["empresa"] for e in empresas_dados]
    receitas = await _receita_por_empresa(db, empresas, mes, ano)

    # Ler o RAZAO REAL (accounting_entries) por empresa e competencia — mesma
    # fonte da apuracao Lucro Real (apuracao_lucro_real_service). O plano de
    # contas usa contas em texto: credito 3.1.1 = receita bruta de servicos;
    # debito 3.1.2 = deducoes/ISS sobre a receita; debito 4% ou 3.2% =
    # despesas/custos dedutiveis. Nao existem contas 5% (impostos sobre lucro
    # sao apurados, nao lancados). periodo_competencia e VARCHAR 'YYYY-MM'.
    competencia = f"{ano:04d}-{mes:02d}"
    razao_sql = text("""
        SELECT
            empresa_id,
            COALESCE(SUM(CASE WHEN conta_credito LIKE '3.1.1%%' THEN valor ELSE 0 END), 0) AS receita,
            COALESCE(SUM(CASE WHEN conta_debito  LIKE '3.1.2%%' THEN valor ELSE 0 END), 0) AS impostos,
            COALESCE(SUM(CASE WHEN conta_debito  LIKE '4%%'
                              OR  conta_debito  LIKE '3.2%%' THEN valor ELSE 0 END), 0) AS despesas,
            COUNT(*) AS lancamentos
        FROM accounting_entries
        WHERE status = 'confirmado'
          AND periodo_competencia = :competencia
        GROUP BY empresa_id
    """)
    r = await db.execute(razao_sql, {"competencia": competencia})
    razao_por_empresa: dict[str, dict] = {}
    receita_contabil = Decimal("0")
    despesas_contabil = Decimal("0")
    impostos_contabil = Decimal("0")
    total_lancamentos = 0
    for row in r.fetchall():
        eid = str(row[0]) if row[0] is not None else None
        rec_v = Decimal(str(row[1]))
        imp_v = Decimal(str(row[2]))
        desp_v = Decimal(str(row[3]))
        lanc_v = int(row[4])
        if eid is not None:
            razao_por_empresa[eid] = {
                "receita": rec_v,
                "impostos": imp_v,
                "despesas": desp_v,
                "lancamentos": lanc_v,
            }
        receita_contabil += rec_v
        impostos_contabil += imp_v
        despesas_contabil += desp_v
        total_lancamentos += lanc_v

    # Se nao ha lancamentos contabeis no periodo, cair para receita de contratos/NFS-e
    total_receita_real = Decimal("0")
    for emp in empresas:
        rec = receitas.get(emp.slug, {})
        total_receita_real += _melhor_receita(rec)

    tem_razao = total_lancamentos > 0
    receita_final = receita_contabil if tem_razao else total_receita_real
    lucro = receita_final - despesas_contabil - impostos_contabil
    margem = float(lucro / receita_final * 100) if receita_final > 0 else None

    por_empresa = {}
    for ed in empresas_dados:
        emp = ed["empresa"]
        rec = receitas.get(emp.slug, {})
        razao_emp = razao_por_empresa.get(str(emp.id), {})
        if razao_emp:
            receita_emp = razao_emp["receita"]
            lucro_emp = razao_emp["receita"] - razao_emp["impostos"] - razao_emp["despesas"]
            por_empresa[emp.slug] = {
                "razao_social": emp.razao_social,
                "regime": emp.regime_tributario,
                "receita_mes": float(receita_emp),
                "impostos_mes": float(razao_emp["impostos"]),
                "despesas_mes": float(razao_emp["despesas"]),
                "lucro_mes": float(lucro_emp),
                "total_lancamentos": razao_emp["lancamentos"],
                "fonte_receita": "contabilidade",
                "postos_ativos": rec.get("postos_ativos", 0),
                "contratos_ativos": rec.get("contratos_ativos", 0),
                "nfse_emitidas": rec.get("nfse_emitidas", 0),
            }
        else:
            receita_emp = _melhor_receita(rec)
            por_empresa[emp.slug] = {
                "razao_social": emp.razao_social,
                "regime": emp.regime_tributario,
                "receita_mes": float(receita_emp),
                "impostos_mes": 0.0,
                "despesas_mes": 0.0,
                "lucro_mes": float(receita_emp),
                "total_lancamentos": 0,
                "fonte_receita": rec.get("fonte", "sem_dados"),
                "postos_ativos": rec.get("postos_ativos", 0),
                "contratos_ativos": rec.get("contratos_ativos", 0),
                "nfse_emitidas": rec.get("nfse_emitidas", 0),
            }

    # Proxima exportacao para contador
    proximo_mes = mes + 1 if mes < 12 else 1
    proximo_ano = ano if mes < 12 else ano + 1

    tem_dados = receita_final > 0 or total_lancamentos > 0

    return {
        "periodo": f"{mes:02d}/{ano}",
        "status": "com_dados" if tem_dados else "sem_dados",
        "mensagem": None
        if tem_dados
        else "Sem lancamentos contabeis ou receita no periodo. Cadastre contratos, emita NFS-e ou registre lancamentos.",
        "grupo_consolidado": {
            "receita_bruta": float(receita_final),
            "despesas": float(despesas_contabil),
            "impostos": float(impostos_contabil),
            "lucro_liquido": float(lucro),
            "margem_liquida_pct": round(margem, 2) if margem is not None else None,
            "total_lancamentos": total_lancamentos,
            "fonte": "contabilidade"
            if tem_razao
            else ("contratos" if total_receita_real > 0 else "sem_dados"),
        },
        "por_empresa": por_empresa,
        "exportacao_contador": {
            "formato": "Dominio Sistemas (TOTVS)",
            "ultima_exportacao": None,
            "proxima_exportacao": f"05/{proximo_mes:02d}/{proximo_ano}",
            "status": "pendente",
        },
    }
