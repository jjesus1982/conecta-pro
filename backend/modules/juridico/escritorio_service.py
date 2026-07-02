"""Gestão do Escritório Jurídico Externo + ROI (Jurídico).

Mede a REDUÇÃO da dependência do escritório jurídico externo pago.
Registra cada demanda jurídica e quem a resolveu:
  - 'interno'    -> resolvida internamente (com apoio do Consultor IA)
  - 'escritorio' -> encaminhada ao escritório externo pago

Calcula o ROI: economia estimada por internalizar demandas + prova de uso
interno (nº de consultas já respondidas pelo Consultor IA na tabela
juridico_consultas).

Fonte de dados REAL:
  - juridico_escritorio_consultas (registro manual das demandas)
  - juridico_consultas            (histórico do Consultor IA)

TODA estimativa é ROTULADA como "referência configurável", nunca como fato
imutável. Se não houver registros, retorna 0 honesto (não fabrica dados).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# --- Referências CONFIGURÁVEIS (não são fatos imutáveis) -------------------
# Valor pago hoje pelo contrato mensal do escritório jurídico externo.
CUSTO_MENSAL_FIXO_REF = Decimal("3000.00")
# Custo de referência de uma consulta/parecer jurídico avulso no mercado.
# Usado apenas para ESTIMAR a economia de cada demanda internalizada.
CUSTO_CONSULTA_AVULSA_REF = Decimal("300.00")

_LABEL_FIXO = "referência configurável (contrato mensal atual do escritório externo)"
_LABEL_AVULSA = "referência configurável (valor de mercado de uma consulta jurídica avulsa)"

RESOLVIDO_POR_VALIDOS = ("interno", "escritorio")


def _f(v: Any) -> float:
    """Converte Decimal/None em float seguro."""
    if v is None:
        return 0.0
    return float(v)


async def registrar_consulta(
    db: AsyncSession,
    *,
    assunto: str,
    area: Optional[str] = None,
    resolvido_por: str = "interno",
    custo: float | Decimal | None = None,
    data_demanda: Optional[date] = None,
    observacao: Optional[str] = None,
) -> dict:
    """Registra uma demanda jurídica e quem a resolveu."""
    if resolvido_por not in RESOLVIDO_POR_VALIDOS:
        raise ValueError(
            f"resolvido_por deve ser um de {RESOLVIDO_POR_VALIDOS}, recebido '{resolvido_por}'"
        )
    if not assunto or not assunto.strip():
        raise ValueError("assunto é obrigatório")

    custo_val = Decimal("0") if custo is None else Decimal(str(custo))
    data_val = data_demanda or date.today()

    row = (
        await db.execute(
            text(
                """
                INSERT INTO juridico_escritorio_consultas
                    (area, assunto, resolvido_por, custo, data, observacao)
                VALUES
                    (:area, :assunto, :resolvido_por, :custo, :data, :observacao)
                RETURNING id, area, assunto, resolvido_por, custo, data, observacao, created_at
                """
            ),
            {
                "area": area,
                "assunto": assunto.strip(),
                "resolvido_por": resolvido_por,
                "custo": custo_val,
                "data": data_val,
                "observacao": observacao,
            },
        )
    ).mappings().first()
    await db.commit()
    return _serialize(row)


async def listar_consultas(
    db: AsyncSession,
    *,
    resolvido_por: Optional[str] = None,
    area: Optional[str] = None,
    data_inicio: Optional[date] = None,
    data_fim: Optional[date] = None,
    limit: int = 200,
) -> dict:
    """Lista demandas registradas, com filtros opcionais."""
    conds = []
    params: dict[str, Any] = {"limit": max(1, min(limit, 1000))}
    if resolvido_por:
        if resolvido_por not in RESOLVIDO_POR_VALIDOS:
            raise ValueError(f"resolvido_por inválido: {resolvido_por}")
        conds.append("resolvido_por = :resolvido_por")
        params["resolvido_por"] = resolvido_por
    if area:
        conds.append("area = :area")
        params["area"] = area
    if data_inicio:
        conds.append("data >= :data_inicio")
        params["data_inicio"] = data_inicio
    if data_fim:
        conds.append("data <= :data_fim")
        params["data_fim"] = data_fim

    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, area, assunto, resolvido_por, custo, data, observacao, created_at
                FROM juridico_escritorio_consultas
                {where}
                ORDER BY data DESC, created_at DESC
                LIMIT :limit
                """
            ),
            params,
        )
    ).mappings().all()
    itens = [_serialize(r) for r in rows]
    return {"total": len(itens), "consultas": itens}


async def roi_dashboard(db: AsyncSession, *, meses: int = 6) -> dict:
    """Dashboard de ROI REAL da internalização jurídica.

    Números vêm do banco. Estimativas de economia usam referências rotuladas.
    """
    # --- Totais gerais das demandas registradas ---------------------------
    tot = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*)                                              AS total,
                    COUNT(*) FILTER (WHERE resolvido_por = 'interno')     AS interno,
                    COUNT(*) FILTER (WHERE resolvido_por = 'escritorio')  AS escritorio,
                    COALESCE(SUM(custo) FILTER (WHERE resolvido_por = 'escritorio'), 0) AS custo_escritorio
                FROM juridico_escritorio_consultas
                """
            )
        )
    ).mappings().first()

    total = int(tot["total"] or 0)
    interno = int(tot["interno"] or 0)
    escritorio = int(tot["escritorio"] or 0)
    custo_variavel_escritorio = _f(tot["custo_escritorio"])

    pct_internalizacao = round((interno / total * 100.0), 1) if total > 0 else 0.0

    # --- Prova de uso interno: consultas já respondidas pelo Consultor IA --
    ia = (
        await db.execute(
            text("SELECT COUNT(*) AS n FROM juridico_consultas")
        )
    ).mappings().first()
    consultas_ia = int(ia["n"] or 0)

    # --- Economia estimada (referência configurável) ----------------------
    # Cada demanda internalizada teria custado ~CUSTO_CONSULTA_AVULSA_REF se
    # fosse enviada ao escritório como consulta avulsa.
    economia_estimada = round(interno * float(CUSTO_CONSULTA_AVULSA_REF), 2)

    # --- Série mensal (últimos N meses): interno vs escritório ------------
    serie_rows = (
        await db.execute(
            text(
                """
                SELECT
                    to_char(date_trunc('month', data), 'YYYY-MM')          AS mes,
                    COUNT(*) FILTER (WHERE resolvido_por = 'interno')       AS interno,
                    COUNT(*) FILTER (WHERE resolvido_por = 'escritorio')    AS escritorio,
                    COALESCE(SUM(custo) FILTER (WHERE resolvido_por = 'escritorio'), 0) AS custo_escritorio
                FROM juridico_escritorio_consultas
                WHERE data >= (date_trunc('month', CURRENT_DATE) - make_interval(months => :m1))
                GROUP BY 1
                ORDER BY 1
                """
            ),
            {"m1": max(0, meses - 1)},
        )
    ).mappings().all()

    serie_por_mes = {
        r["mes"]: {
            "interno": int(r["interno"] or 0),
            "escritorio": int(r["escritorio"] or 0),
            "custo_escritorio": _f(r["custo_escritorio"]),
        }
        for r in serie_rows
    }
    # Preenche todos os últimos N meses (inclusive os sem registro -> 0 honesto)
    serie_mensal = []
    hoje = date.today()
    base_ano, base_mes = hoje.year, hoje.month
    for i in range(meses - 1, -1, -1):
        m = base_mes - i
        y = base_ano
        while m <= 0:
            m += 12
            y -= 1
        chave = f"{y:04d}-{m:02d}"
        dados = serie_por_mes.get(chave, {"interno": 0, "escritorio": 0, "custo_escritorio": 0.0})
        serie_mensal.append({"mes": chave, **dados})

    return {
        "referencia": datetime.utcnow().isoformat() + "Z",
        "custo_mensal_fixo": {
            "valor": float(CUSTO_MENSAL_FIXO_REF),
            "rotulo": _LABEL_FIXO,
        },
        "custo_consulta_avulsa": {
            "valor": float(CUSTO_CONSULTA_AVULSA_REF),
            "rotulo": _LABEL_AVULSA,
        },
        "total_demandas": total,
        "resolvidas_interno": interno,
        "resolvidas_escritorio": escritorio,
        "pct_internalizacao": pct_internalizacao,
        "custo_variavel_escritorio": custo_variavel_escritorio,
        "economia_estimada": economia_estimada,
        "economia_estimada_metodo": (
            f"{interno} demanda(s) internalizada(s) × R$ "
            f"{float(CUSTO_CONSULTA_AVULSA_REF):.2f} ({_LABEL_AVULSA})"
        ),
        "consultas_ia_internas": consultas_ia,
        "consultas_ia_nota": (
            "COUNT real de juridico_consultas — consultas já respondidas pelo "
            "Consultor IA interno (prova de uso, não estimativa)."
        ),
        "serie_mensal": serie_mensal,
        "disclaimer": (
            "Valores R$ 3.000/mês (fixo) e R$ 300/consulta (avulsa) são "
            "REFERÊNCIAS CONFIGURÁVEIS para estimar ROI, não fatos imutáveis. "
            "Contagens de demandas e consultas IA são dados reais do banco."
        ),
    }


def _serialize(row: Any) -> dict:
    if row is None:
        return {}
    d = dict(row)
    if d.get("id") is not None:
        d["id"] = str(d["id"])
    if isinstance(d.get("custo"), Decimal):
        d["custo"] = float(d["custo"])
    if isinstance(d.get("data"), date):
        d["data"] = d["data"].isoformat()
    if isinstance(d.get("created_at"), datetime):
        d["created_at"] = d["created_at"].isoformat()
    return d
