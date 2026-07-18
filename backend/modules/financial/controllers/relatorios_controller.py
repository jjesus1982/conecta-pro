"""Controller de Relatórios Financeiros — DRE, Balancete, Orçamento, Custeio."""
# pylint: disable=too-many-arguments,too-many-positional-arguments

import logging
from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_user
from core.database import get_session
from modules.financial.services.balance_sheet_service import BalanceSheetService
from modules.financial.services.budget_service import BudgetPeriodType, BudgetService
from modules.financial.services.cost_by_type_service import CostByTypeService
from modules.financial.services.dre_service import DREService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/relatorios", tags=["Financial - Relatórios"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TIPOS_SERVICO = ["portaria", "limpeza", "jardinagem", "seguranca_eletronica", "portaria_remota"]


def _first_day(year: int, month: int) -> date:
    return date(year, month, 1)


def _last_day(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


# ---------------------------------------------------------------------------
# Orçamento — armazenamento REAL no servidor (substitui o localStorage do front)
# ---------------------------------------------------------------------------

from pydantic import BaseModel  # noqa: E402
from sqlalchemy import text as _sql  # noqa: E402


class OrcamentoKV(BaseModel):
    chave: str
    valor: float


async def _ensure_orcamentos(db: AsyncSession) -> None:
    await db.execute(_sql("""
        CREATE TABLE IF NOT EXISTS financial_orcamentos (
            chave       TEXT PRIMARY KEY,
            valor       NUMERIC(15,2) NOT NULL DEFAULT 0,
            updated_by  VARCHAR(64),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    await db.commit()


@router.get("/orcamentos-kv")
async def orcamentos_kv_listar(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Retorna o orçamento salvo no servidor (mapa chave→valor). Substitui o localStorage:
    orçamento agora é multiusuário e persistente (Jordan e Pyetra veem o mesmo)."""
    await _ensure_orcamentos(db)
    rows = (await db.execute(_sql("SELECT chave, valor FROM financial_orcamentos"))).fetchall()
    return {"budgets": {r[0]: float(r[1]) for r in rows}}


@router.put("/orcamentos-kv")
async def orcamentos_kv_salvar(
    payload: OrcamentoKV,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Salva/atualiza um valor de orçamento no servidor."""
    await _ensure_orcamentos(db)
    uid = str(getattr(current_user, "id", "") or getattr(current_user, "email", ""))[:64]
    await db.execute(
        _sql("""INSERT INTO financial_orcamentos (chave, valor, updated_by, updated_at)
                VALUES (:c, :v, :u, now())
                ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor,
                    updated_by=EXCLUDED.updated_by, updated_at=now()"""),
        {"c": payload.chave, "v": payload.valor, "u": uid},
    )
    await db.commit()
    return {"ok": True, "chave": payload.chave, "valor": payload.valor}


# ---------------------------------------------------------------------------
# Liminares (base legal de PIS/COFINS/INSS zerados) — nativo, persistente
# ---------------------------------------------------------------------------


class LiminarIn(BaseModel):
    tipo: str
    descricao: str
    status: str = "a_solicitar"  # a_solicitar | solicitada | deferida | indeferida | vigente
    processo: str | None = None
    tributo: str | None = None
    empresa: str | None = None
    observacao: str | None = None


async def _ensure_liminares(db: AsyncSession) -> None:
    await db.execute(_sql("""
        CREATE TABLE IF NOT EXISTS fiscal_liminares (
            id          BIGSERIAL PRIMARY KEY,
            tipo        VARCHAR(60) NOT NULL,
            descricao   TEXT NOT NULL,
            status      VARCHAR(20) NOT NULL DEFAULT 'a_solicitar',
            processo    VARCHAR(80),
            tributo     VARCHAR(40),
            empresa     VARCHAR(80),
            observacao  TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    # seed as 2 liminares do negócio (uma vez), como ponto de partida real.
    # STATUS = 'a_solicitar' (consistente com a tabela 'liminares' do módulo empresas): as liminares
    # do CNPJ2 (em abertura) ainda NÃO foram concedidas — 'vigente' era otimista/incorreto.
    if not (await db.execute(_sql("SELECT 1 FROM fiscal_liminares LIMIT 1"))).first():
        await db.execute(_sql("""
            INSERT INTO fiscal_liminares (tipo, descricao, status, tributo) VALUES
            ('PIS/COFINS zerados', 'Não cobrança de PIS e COFINS nas notas de serviço', 'a_solicitar', 'PIS/COFINS'),
            ('INSS não retido', 'Não retenção de INSS (11%) na cessão de mão de obra', 'a_solicitar', 'INSS')
        """))
    await db.commit()


@router.get("/liminares")
async def liminares_listar(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    await _ensure_liminares(db)
    rows = (await db.execute(_sql("SELECT * FROM fiscal_liminares ORDER BY created_at"))).mappings().all()
    return {"liminares": [dict(r) for r in rows]}


@router.post("/liminares", status_code=201)
async def liminar_criar(
    body: LiminarIn,
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    await _ensure_liminares(db)
    r = await db.execute(_sql("""
        INSERT INTO fiscal_liminares (tipo, descricao, status, processo, tributo, empresa, observacao)
        VALUES (:t,:d,:s,:p,:tr,:e,:o) RETURNING id
    """), {"t": body.tipo, "d": body.descricao, "s": body.status, "p": body.processo,
           "tr": body.tributo, "e": body.empresa, "o": body.observacao})
    await db.commit()
    return {"ok": True, "id": int(r.scalar())}


@router.put("/liminares/{lid}/status")
async def liminar_status(
    lid: int, status: str = Query(...),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    await _ensure_liminares(db)
    await db.execute(_sql("UPDATE fiscal_liminares SET status=:s, updated_at=now() WHERE id=:id"), {"s": status, "id": lid})
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Parcelamentos governamentais + Guias do mês (nativo — substitui Onvio/Portte)
# ---------------------------------------------------------------------------


async def _ensure_parcelamentos(db: AsyncSession) -> None:
    await db.execute(_sql("""
        CREATE TABLE IF NOT EXISTS fiscal_parcelamentos (
            id             BIGSERIAL PRIMARY KEY,
            orgao          VARCHAR(40) NOT NULL,   -- RFB | PGFN | SEFAZ_AM | PREFEITURA_MANAUS | INSS | FGTS | OUTRO
            numero_acordo  VARCHAR(60),
            descricao      TEXT NOT NULL,
            valor_total    NUMERIC(14,2),
            num_parcelas   INT NOT NULL,
            parcela_valor  NUMERIC(14,2) NOT NULL,
            dia_vencimento INT NOT NULL DEFAULT 20,
            competencia_inicio VARCHAR(7) NOT NULL,   -- MM/AAAA da 1ª parcela
            parcelas_pagas INT NOT NULL DEFAULT 0,
            status         VARCHAR(20) NOT NULL DEFAULT 'ativo',  -- ativo | quitado | cancelado
            observacao     TEXT,
            fonte          VARCHAR(30) DEFAULT 'manual',  -- manual | ecac | sefaz | prefeitura | robo
            created_by     VARCHAR(64),
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    await db.commit()


ORGAO_LABEL = {
    "RFB": "Receita Federal", "PGFN": "PGFN (Dívida Ativa)", "SEFAZ_AM": "SEFAZ-AM (ICMS)",
    "PREFEITURA_MANAUS": "Prefeitura de Manaus (ISS)", "INSS": "INSS/Previdência",
    "FGTS": "FGTS (Caixa)", "OUTRO": "Outro órgão",
}


class ParcelamentoIn(BaseModel):
    orgao: str
    descricao: str
    num_parcelas: int
    parcela_valor: float
    competencia_inicio: str  # MM/AAAA
    dia_vencimento: int = 20
    numero_acordo: str | None = None
    valor_total: float | None = None
    parcelas_pagas: int = 0
    observacao: str | None = None


def _comp_add(competencia: str, meses: int) -> tuple[int, int]:
    mm, aaaa = competencia.split("/")
    idx = (int(aaaa) * 12 + (int(mm) - 1)) + meses
    return (idx // 12, (idx % 12) + 1)  # (ano, mes)


@router.get("/parcelamentos")
async def parcelamentos_listar(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Lista os parcelamentos/acordos com órgãos governamentais (nativo, sem Onvio)."""
    await _ensure_parcelamentos(db)
    rows = (await db.execute(_sql(
        "SELECT * FROM fiscal_parcelamentos WHERE status='ativo' ORDER BY orgao, created_at"))).mappings().all()
    out = []
    for r in rows:
        restantes = max(0, int(r["num_parcelas"]) - int(r["parcelas_pagas"]))
        out.append({
            "id": r["id"], "orgao": r["orgao"], "orgao_label": ORGAO_LABEL.get(r["orgao"], r["orgao"]),
            "numero_acordo": r["numero_acordo"], "descricao": r["descricao"],
            "valor_total": float(r["valor_total"]) if r["valor_total"] is not None else None,
            "num_parcelas": r["num_parcelas"], "parcela_valor": float(r["parcela_valor"]),
            "parcelas_pagas": r["parcelas_pagas"], "parcelas_restantes": restantes,
            "saldo_devedor": round(float(r["parcela_valor"]) * restantes, 2),
            "dia_vencimento": r["dia_vencimento"], "competencia_inicio": r["competencia_inicio"],
            "status": r["status"], "fonte": r["fonte"], "observacao": r["observacao"],
        })
    return {"parcelamentos": out,
            "total_parcela_mensal": round(sum(p["parcela_valor"] for p in out), 2),
            "saldo_devedor_total": round(sum(p["saldo_devedor"] for p in out), 2)}


@router.post("/parcelamentos", status_code=201)
async def parcelamento_criar(
    body: ParcelamentoIn,
    db: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Registra um parcelamento (acordo com órgão). Até termos o robô que puxa do e-CAC/SEFAZ/
    prefeitura, o Jordan cadastra o acordo aqui e o sistema gera as guias mensais por competência."""
    await _ensure_parcelamentos(db)
    uid = str(getattr(current_user, "id", "") or getattr(current_user, "email", ""))[:64]
    r = await db.execute(_sql("""
        INSERT INTO fiscal_parcelamentos
          (orgao, numero_acordo, descricao, valor_total, num_parcelas, parcela_valor,
           dia_vencimento, competencia_inicio, parcelas_pagas, observacao, created_by)
        VALUES (:o,:na,:d,:vt,:np,:pv,:dv,:ci,:pp,:obs,:u) RETURNING id
    """), {"o": body.orgao.upper(), "na": body.numero_acordo, "d": body.descricao,
           "vt": body.valor_total, "np": body.num_parcelas, "pv": body.parcela_valor,
           "dv": body.dia_vencimento, "ci": body.competencia_inicio, "pp": body.parcelas_pagas,
           "obs": body.observacao, "u": uid})
    await db.commit()
    return {"ok": True, "id": int(r.scalar())}


@router.delete("/parcelamentos/{parc_id}")
async def parcelamento_remover(
    parc_id: int,
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    await _ensure_parcelamentos(db)
    await db.execute(_sql("UPDATE fiscal_parcelamentos SET status='cancelado', updated_at=now() WHERE id=:id"), {"id": parc_id})
    await db.commit()
    return {"ok": True}


@router.get("/guias-do-mes")
async def guias_do_mes(
    competencia: str = Query(..., description="MM/AAAA"),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """GUIAS A PAGAR DO MÊS (nativo, substitui o Onvio): as PARCELAS dos parcelamentos que vencem
    nesta competência + as GUIAS MENSAIS de tributos (das obrigações fiscais). Tudo por competência."""
    await _ensure_parcelamentos(db)
    try:
        mm, aaaa = competencia.split("/")
        mes, ano = int(mm), int(aaaa)
    except Exception as exc:
        raise HTTPException(422, detail="competencia deve ser MM/AAAA") from exc

    guias = []

    # 1) Parcelas dos parcelamentos que caem nesta competência
    parc = (await db.execute(_sql("SELECT * FROM fiscal_parcelamentos WHERE status='ativo'"))).mappings().all()
    alvo = ano * 12 + (mes - 1)
    for p in parc:
        try:
            ci_m, ci_a = p["competencia_inicio"].split("/")
            inicio = int(ci_a) * 12 + (int(ci_m) - 1)
        except Exception:  # noqa: BLE001
            continue
        n_parcela = alvo - inicio + 1  # qual parcela vence neste mês
        if 1 <= n_parcela <= int(p["num_parcelas"]):
            paga = n_parcela <= int(p["parcelas_pagas"])
            guias.append({
                "tipo": "parcelamento",
                "descricao": f"{ORGAO_LABEL.get(p['orgao'], p['orgao'])} — parcela {n_parcela}/{p['num_parcelas']}"
                             + (f" (acordo {p['numero_acordo']})" if p["numero_acordo"] else ""),
                "orgao": p["orgao"], "competencia": competencia,
                "valor": float(p["parcela_valor"]),
                "vencimento": f"{ano:04d}-{mes:02d}-{min(p['dia_vencimento'],28):02d}",
                "status": "pago" if paga else "a_pagar", "parcelamento_id": p["id"],
            })

    # 2) Guias mensais de tributos (das obrigações fiscais da competência)
    obr = (await db.execute(_sql("""
        SELECT id, tipo, nome, COALESCE(valor_devido,0) valor, data_vencimento, status, observacoes
        FROM fiscal_obligations
        WHERE competencia_mes=:m AND competencia_ano=:a AND COALESCE(valor_devido,0) > 0
        ORDER BY data_vencimento
    """), {"m": mes, "a": ano})).mappings().all()
    for o in obr:
        tem_pdf = bool(o["observacoes"] and "drive_file_id" in o["observacoes"])
        guias.append({
            "tipo": "mensal",
            "descricao": f"{o['tipo']} — {o['nome'] or 'guia mensal'}",
            "orgao": o["tipo"], "competencia": competencia,
            "valor": float(o["valor"]),
            "vencimento": o["data_vencimento"].isoformat() if o["data_vencimento"] else None,
            "status": "pago" if (o["status"] or "").lower() == "cumprida" else "a_pagar",
            "obrigacao_id": str(o["id"]),
            "pdf_disponivel": tem_pdf,
            "pdf_url": f"/api/v1/fiscal/guias-drive/pdf/{o['id']}" if tem_pdf else None,
        })

    total = round(sum(g["valor"] for g in guias), 2)
    a_pagar = round(sum(g["valor"] for g in guias if g["status"] == "a_pagar"), 2)
    return {"competencia": competencia, "guias": guias, "total": total, "total_a_pagar": a_pagar,
            "qtd": len(guias),
            "observacao": "Parcelas de acordos + guias mensais de tributos. Cadastre os parcelamentos em /parcelamentos "
                          "(ou, no futuro, o robô puxa do e-CAC/SEFAZ/prefeitura)."}


# ---------------------------------------------------------------------------
# Balancete real (a partir dos lançamentos reais em accounting_entries)
# ---------------------------------------------------------------------------


@router.get("/balancete-real")
async def balancete_real(
    ano: int = Query(2026, ge=2020, le=2100),
    mes: int | None = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Balancete a partir dos LANÇAMENTOS REAIS (accounting_entries). Por conta: soma dos débitos e
    créditos e o saldo. Comprova que fecha (Σ débitos = Σ créditos). Junta o nome do plano de contas."""
    filtro = "WHERE EXTRACT(YEAR FROM data_lancamento) = :ano"
    params = {"ano": ano}
    if mes:
        filtro += " AND EXTRACT(MONTH FROM data_lancamento) = :mes"
        params["mes"] = mes

    deb = (await db.execute(_sql(
        f"SELECT conta_debito conta, SUM(valor) v FROM accounting_entries {filtro} GROUP BY 1"), params)).fetchall()
    cred = (await db.execute(_sql(
        f"SELECT conta_credito conta, SUM(valor) v FROM accounting_entries {filtro} GROUP BY 1"), params)).fetchall()
    nomes = {r[0]: r[1] for r in (await db.execute(_sql(
        "SELECT code, name FROM fin_accounting_accounts"))).fetchall()}

    contas: dict[str, dict] = {}
    for c, v in deb:
        contas.setdefault(c, {"debito": 0.0, "credito": 0.0})["debito"] += float(v)
    for c, v in cred:
        contas.setdefault(c, {"debito": 0.0, "credito": 0.0})["credito"] += float(v)

    linhas = []
    tot_deb = tot_cred = 0.0
    for code in sorted(contas):
        d = contas[code]["debito"]
        c = contas[code]["credito"]
        tot_deb += d
        tot_cred += c
        linhas.append({"conta": code, "nome": nomes.get(code, "(conta não mapeada no plano)"),
                       "debito": round(d, 2), "credito": round(c, 2), "saldo": round(d - c, 2)})
    return {
        "ano": ano, "mes": mes, "linhas": linhas,
        "total_debito": round(tot_deb, 2), "total_credito": round(tot_cred, 2),
        "diferenca": round(tot_deb - tot_cred, 2),
        "fecha": abs(tot_deb - tot_cred) < 0.01,
        "fonte": "accounting_entries (lançamentos reais de NFS-e emitida + extrato Inter)",
        "observacao": "Plano de contas em consolidação (2 numerações coexistem); contas não mapeadas ficam marcadas.",
    }


# ---------------------------------------------------------------------------
# Painel Fiscal — raio-x fiscal consolidado (dado real)
# ---------------------------------------------------------------------------


@router.get("/painel-fiscal")
async def painel_fiscal(
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Raio-X fiscal: obrigações (prazos/status), certidões (validade), notas emitidas/tomadas,
    tributos do ano e empresas. Tudo dado REAL — nada estimado sem aviso."""
    async def _rows(sql, params=None):
        return (await db.execute(_sql(sql), params or {})).mappings().all()

    # Obrigações
    obr = await _rows("""
        SELECT tipo, nome, competencia_mes, competencia_ano, data_vencimento,
               COALESCE(valor_devido,0) valor, status
        FROM fiscal_obligations WHERE COALESCE(active,true)
        ORDER BY data_vencimento
    """)
    hoje_obr = []
    for r in obr:
        venc = r["data_vencimento"]
        st = (r["status"] or "").lower()
        atrasada = st in ("pendente", "pendent") and venc is not None and venc < date.today()
        hoje_obr.append({
            "tipo": r["tipo"], "nome": r["nome"],
            "competencia": f"{r['competencia_mes'] or 0:02d}/{r['competencia_ano'] or ''}",
            "vencimento": venc.isoformat() if venc else None,
            "valor": float(r["valor"]), "status": "atrasada" if atrasada else st,
        })
    cumpridas = sum(1 for o in hoje_obr if o["status"] == "cumprida")
    pendentes = sum(1 for o in hoje_obr if o["status"] in ("pendente", "pendent"))
    atrasadas = sum(1 for o in hoje_obr if o["status"] == "atrasada")

    # Certidões (validade) — fonte real: ged_certidoes (o Painel de Certidões). Situação derivada
    # da data de validade: vencida / a_vencer (≤30 dias) / em_dia.
    cert = await _rows("SELECT name, document_type, issuing_body, expiry_date FROM ged_certidoes ORDER BY expiry_date NULLS LAST")
    certidoes = []
    venc_cert = a_vencer_cert = 0
    for r in cert:
        val = r["expiry_date"]
        dias = (val - date.today()).days if val else None
        if dias is not None and dias < 0:
            sit = "vencida"; venc_cert += 1
        elif dias is not None and dias <= 30:
            sit = "a_vencer"; a_vencer_cert += 1
        else:
            sit = "em_dia"
        certidoes.append({"tipo": r["name"], "orgao": r["issuing_body"], "status": sit,
                          "validade": val.isoformat() if val else None, "dias_para_vencer": dias})

    # Notas — emitidas e tomadas. FONTE REAL: portal nacional (só cStat 100, todos os meses).
    # Emitidas -> nfse_emitidas_nacional; tomadas -> nfse_tomadas_nacional (competencia é VARCHAR
    # 'YYYY-MM', filtra o ano corrente). NÃO usar as tabelas velhas 'nfses'/'nfse_entrada' (só jan-fev).
    ano_corrente = date.today().year

    async def _one(sql, params=None):
        return (await db.execute(_sql(sql), params or {})).first()
    nfse_e = await _one(
        "SELECT COUNT(*), COALESCE(SUM(valor_servicos),0), MIN(data_emissao), MAX(data_emissao) "
        "FROM nfse_emitidas_nacional WHERE competencia LIKE :ano",
        {"ano": f"{ano_corrente}-%"},
    )
    nfse_t = await _one(
        "SELECT COUNT(*), COALESCE(SUM(valor_servicos),0) "
        "FROM nfse_tomadas_nacional WHERE competencia LIKE :ano",
        {"ano": f"{ano_corrente}-%"},
    )
    nfe_t = await _one("SELECT COUNT(*), COALESCE(SUM(valor_total),0) FROM nfe_entradas")

    # Tributos do ano (reusa a rota real: ISS por NFS-e; FGTS 8% do razão; INSS patronal=0/liminar)
    trib = await tributos_consolidados(ano=date.today().year, db=db, _user=_user)  # type: ignore
    tributos_ano = dict(trib.get("totais", {}))

    # RECONCILIAÇÃO INSS/FGTS com as GUIAS REAIS (fiscal_obligations) — para o painel não se
    # contradizer (obrigações mostravam INSS 'cumprida' enquanto tributos_ano.inss=0). Fonte única:
    # as guias efetivamente lançadas em fiscal_obligations do ano corrente.
    guias = await _one("""
        SELECT COALESCE(SUM(CASE WHEN tipo='INSS' THEN COALESCE(valor_devido,0) ELSE 0 END),0),
               COALESCE(SUM(CASE WHEN tipo='FGTS' THEN COALESCE(valor_devido,0) ELSE 0 END),0)
        FROM fiscal_obligations
        WHERE COALESCE(active,true) AND competencia_ano = :ano
    """, {"ano": ano_corrente})
    inss_guias = float(guias[0] or 0)
    fgts_guias = float(guias[1] or 0)
    # INSS: a liminar de 'INSS não retido' está a_solicitar (não concedida) → INSS das guias é devido/
    # real. Usamos o valor das guias (fonte única), não 0. FGTS idem: valor das guias efetivas.
    tributos_ano["inss"] = round(inss_guias, 2)
    tributos_ano["fgts"] = round(fgts_guias, 2)
    tributos_ano["total"] = round(
        float(tributos_ano.get("iss", 0)) + fgts_guias + inss_guias
        + float(tributos_ano.get("pis", 0)) + float(tributos_ano.get("cofins", 0)), 2)
    tributos_ano["fonte_inss_fgts"] = "fiscal_obligations (guias reais lançadas); INSS liminar a_solicitar (devido)"

    # Empresas
    emp = await _rows("SELECT razao_social, cnpj, regime_tributario, is_principal FROM empresas ORDER BY is_principal DESC")

    return {
        "obrigacoes": {
            "lista": hoje_obr, "cumpridas": cumpridas, "pendentes": pendentes, "atrasadas": atrasadas,
            "total_pendente": round(sum(o["valor"] for o in hoje_obr if o["status"] in ("pendente", "atrasada")), 2),
        },
        "certidoes": {"lista": certidoes, "vencidas": venc_cert, "a_vencer": a_vencer_cert, "total": len(certidoes)},
        "notas": {
            "emitidas": {"qtd": int(nfse_e[0]), "total": float(nfse_e[1]),
                         "de": str(nfse_e[2]) if nfse_e[2] else None, "ate": str(nfse_e[3]) if nfse_e[3] else None},
            "tomadas_nfse": {"qtd": int(nfse_t[0]), "total": float(nfse_t[1])},
            "tomadas_nfe": {"qtd": int(nfe_t[0]), "total": float(nfe_t[1])},
        },
        "tributos_ano": tributos_ano,
        "empresas": [{"razao_social": r["razao_social"], "cnpj": r["cnpj"] or "(em abertura)",
                      "regime": r["regime_tributario"], "principal": bool(r["is_principal"])} for r in emp],
    }


# ---------------------------------------------------------------------------
# Tributos consolidados por competência (dado real)
# ---------------------------------------------------------------------------


@router.get("/tributos")
async def tributos_consolidados(
    ano: int = Query(2026, ge=2020, le=2100),
    db: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Tributos por competência a partir de DADO REAL: ISS (NFS-e emitidas nacional), FGTS (encargo
    patronal 8% do razão, por competência). INSS patronal = 0 (sem dado real; hr_payslips.inss_value
    é INSS RETIDO do empregado, não patronal). Onde não há dado no mês, mostra 0 (honesto).
    PIS/COFINS zerados por liminar."""
    # ISS por mês — FONTE REAL: nfse_emitidas_nacional (portal nacional, só cStat 100, todos meses)
    iss_rows = (await db.execute(_sql("""
        SELECT CAST(substr(competencia,6,2) AS int) m,
               COALESCE(SUM(iss_valor),0) iss, COALESCE(SUM(valor_servicos),0) base
        FROM nfse_emitidas_nacional
        WHERE CAST(LEFT(competencia,4) AS int) = :ano
        GROUP BY 1
    """), {"ano": ano})).fetchall()
    iss_por_mes = {int(r[0]): (float(r[1]), float(r[2])) for r in iss_rows}

    # FGTS por mês — FONTE REAL: razão (accounting_entries), encargo patronal 8% reconstruído por
    # competência p/ TODOS os meses. NÃO usar hr_payslips (só tem março → 1 mês reportado como ano).
    fgts_rows = (await db.execute(_sql("""
        SELECT CAST(substr(periodo_competencia,6,2) AS int) m, COALESCE(SUM(valor),0) fgts
        FROM accounting_entries
        WHERE conta_debito = '4.1.2.01' AND historico ILIKE 'FGTS%'
              AND LEFT(periodo_competencia,4) = :ano
        GROUP BY 1
    """), {"ano": str(ano)})).fetchall()
    fgts_por_mes = {int(r[0]): float(r[1]) for r in fgts_rows}
    # INSS PATRONAL: NÃO há dado real no sistema (razão tem 0; hr_payslips.inss_value é o INSS RETIDO
    # do empregado, não o patronal). Mostrar 0 (honesto) em vez de rotular o retido como patronal.
    # Além disso a empresa tem liminar de INSS não retido/não recolhido (a_solicitar).
    inss_por_mes: dict[int, float] = {}

    meses = []
    tot_iss = tot_fgts = tot_inss = 0.0
    for m in range(1, 13):
        iss, base = iss_por_mes.get(m, (0.0, 0.0))
        fgts = fgts_por_mes.get(m, 0.0)
        inss = inss_por_mes.get(m, 0.0)
        tot_iss += iss
        tot_fgts += fgts
        tot_inss += inss
        tem = iss > 0 or fgts > 0 or inss > 0
        meses.append({
            "mes": m, "competencia": f"{m:02d}/{ano}",
            "iss": round(iss, 2), "iss_base": round(base, 2),
            "fgts": round(fgts, 2), "inss": round(inss, 2),
            "pis": 0.0, "cofins": 0.0,  # zerados por liminar
            "total": round(iss + fgts + inss, 2),
            "sem_dado": not tem,
        })
    return {
        "ano": ano,
        "meses": meses,
        "totais": {
            "iss": round(tot_iss, 2), "fgts": round(tot_fgts, 2), "inss": round(tot_inss, 2),
            "pis": 0.0, "cofins": 0.0, "total": round(tot_iss + tot_fgts + tot_inss, 2),
        },
        "fonte": "ISS = NFS-e emitidas nacional (iss_valor); FGTS = encargo patronal 8% do razão "
                 "(accounting_entries, por competência); INSS patronal sem dado real (=0). "
                 "PIS/COFINS zerados por liminar.",
        "observacao": "Meses sem NFS-e ou sem folha lançada aparecem zerados (dado real parcial, "
                      "nada estimado). INSS patronal não é rastreado no sistema hoje (liminar de INSS "
                      "não retido a solicitar); não é o INSS retido do empregado.",
    }


@router.get("/fluxo-caixa")
async def fluxo_caixa_mensal(ano: int = Query(2026), _user: dict = Depends(get_current_user)) -> dict:
    """DFC mensal REAL: entradas (créditos Inter), saídas por categoria justificada, saldo."""
    from modules.financial.services.fluxo_caixa_service import FluxoCaixaService
    return FluxoCaixaService().dfc_mensal(ano)


@router.get("/contas-receber")
async def contas_a_receber_ep(ano: int = Query(2026), _user: dict = Depends(get_current_user)) -> dict:
    """A Receber REAL = NFS-e emitidas (cStat 100) − recebimentos de cliente no caixa."""
    from modules.financial.services.fluxo_caixa_service import FluxoCaixaService
    return FluxoCaixaService().contas_a_receber(ano)


@router.get("/contas-pagar")
async def contas_a_pagar_ep(ano: int = Query(2026), _user: dict = Depends(get_current_user)) -> dict:
    """A Pagar REAL = NFS-e tomadas (fornecedores) + folha, por competência."""
    from modules.financial.services.fluxo_caixa_service import FluxoCaixaService
    return FluxoCaixaService().contas_a_pagar(ano)


@router.get("/fornecedores")
async def fornecedores_ep(ano: int = Query(2026), _user: dict = Depends(get_current_user)) -> dict:
    """Fornecedores REAIS consolidados das NFS-e tomadas (serviços comprados)."""
    from modules.financial.services.fluxo_caixa_service import FluxoCaixaService
    return FluxoCaixaService().fornecedores(ano)


@router.get("/apuracao-lucro-real")
async def apuracao_lucro_real(
    ano: int = Query(2026, ge=2020, le=2100),
    trimestre: int | None = Query(None, ge=1, le=4, description="1-4; vazio = ano inteiro"),
    empresa_id: str | None = Query(None, description="default: CNPJ principal (Lucro Real)"),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Apuração IRPJ/CSLL REAL sobre o lucro do razão (não presunção 32%). Base = resultado
    de accounting_entries do período, isolado por empresa. Lucro Real trimestral."""
    from modules.financial.services.apuracao_lucro_real_service import (
        EMPRESA_PRINCIPAL_ID,
        ApuracaoLucroRealService,
    )

    try:
        return ApuracaoLucroRealService().apurar(
            ano=ano, trimestre=trimestre, empresa_id=empresa_id or EMPRESA_PRINCIPAL_ID
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Erro na apuração Lucro Real: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------------------------------------------------------------------------
# DRE
# ---------------------------------------------------------------------------


@router.get("/dre")
async def get_dre(
    ano: int = Query(..., ge=2020, le=2100, description="Ano do DRE"),
    mes_inicio: int = Query(1, ge=1, le=12, description="Mês inicial"),
    mes_fim: int = Query(12, ge=1, le=12, description="Mês final"),
    comparativo: bool = Query(True, description="Incluir período anterior"),
    condominio_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Gera DRE para o período especificado.

    - **ano**: Ano do relatório (ex: 2026)
    - **mes_inicio/mes_fim**: Range de meses (padrão: ano completo)
    - **comparativo**: Incluir período anterior para análise AH
    """
    if mes_inicio > mes_fim:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="mes_inicio deve ser <= mes_fim",
        )

    start_date = _first_day(ano, mes_inicio)
    end_date = _last_day(ano, mes_fim)

    try:
        svc = DREService(db)
        report = await svc.generate_dre(
            condominio_id=condominio_id or UUID("00000000-0000-0000-0000-000000000001"),
            start_date=start_date,
            end_date=end_date,
            include_previous=comparativo,
        )
        result = report.to_dict()
        # Se veio vazio, usar fallback
        if not any(line.get("current_value", 0) != 0 for line in result.get("lines", [])):
            raise ValueError("DRE vazio")  # noqa: TRY301
        return result
    except Exception as e:
        logger.warning("Erro ao gerar DRE, usando fallback: %s", e)
        await db.rollback()
        return await _dre_simplificado(ano, mes_inicio, mes_fim, db)


@router.get("/dre/mensal")
async def get_dre_mensal(
    ano: int = Query(..., ge=2020, le=2100),
    condominio_id: UUID | None = Query(None),  # noqa: ARG001 (mantido p/ compat de rota)
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Comparativo DRE mês a mês, agregado do RAZÃO REAL (accounting_entries) por
    periodo_competencia — mesma fonte de /relatorios/dre e /accounting/dre. NÃO usa
    fin_journal_entries (ledger vazio) nem condominio_id fixo."""
    try:
        rows = (await db.execute(_sql("""
            SELECT periodo_competencia,
                   SUM(CASE WHEN conta_credito LIKE '3.1.1%' THEN valor ELSE 0 END)::float AS receita_bruta,
                   SUM(CASE WHEN conta_debito  LIKE '3.1.2%' THEN valor ELSE 0 END)::float AS deducoes,
                   SUM(CASE WHEN conta_debito  LIKE '4.1.1%' THEN valor ELSE 0 END)::float AS pessoal,
                   SUM(CASE WHEN conta_debito  LIKE '4.1.2%' THEN valor ELSE 0 END)::float AS encargos,
                   SUM(CASE WHEN conta_debito  LIKE '4%' OR conta_debito LIKE '3.2%'
                            THEN valor ELSE 0 END)::float AS despesas_op
            FROM accounting_entries
            WHERE status = 'confirmado' AND LEFT(periodo_competencia, 4) = :ano
            GROUP BY periodo_competencia
            ORDER BY periodo_competencia
        """), {"ano": str(ano)})).mappings().all()

        by_comp = {r["periodo_competencia"]: r for r in rows}
        comparison: dict[str, list] = {
            "months": [], "receita_bruta": [], "custos": [],
            "lucro_bruto": [], "despesas": [], "lucro_liquido": [],
        }
        for m in range(1, 13):
            comp = f"{ano}-{m:02d}"
            r = by_comp.get(comp)
            if not r:
                continue
            receita = float(r["receita_bruta"] or 0)
            deducoes = float(r["deducoes"] or 0)
            # Custo dos serviços = folha (4.1.1) + encargos (4.1.2)
            custos = float(r["pessoal"] or 0) + float(r["encargos"] or 0)
            receita_liquida = receita - deducoes
            lucro_bruto = receita_liquida - custos
            # Demais despesas 4.x/3.2 fora de pessoal/encargos
            despesas = float(r["despesas_op"] or 0) - custos
            if despesas < 0:
                despesas = 0.0
            lucro_liquido = lucro_bruto - despesas
            comparison["months"].append(comp)
            comparison["receita_bruta"].append(round(receita, 2))
            comparison["custos"].append(round(custos, 2))
            comparison["lucro_bruto"].append(round(lucro_bruto, 2))
            comparison["despesas"].append(round(despesas, 2))
            comparison["lucro_liquido"].append(round(lucro_liquido, 2))

        return {
            "ano": ano,
            "meses": comparison,
            "fonte": "accounting_entries (razão real, por periodo_competencia)",
        }
    except Exception as e:
        logger.warning("Erro DRE mensal: %s", e)
        return {"ano": ano, "meses": {}, "aviso": "Sem lançamentos contábeis para o período"}


# ---------------------------------------------------------------------------
# Balancete / Balanço Patrimonial
# ---------------------------------------------------------------------------


@router.get("/balancete")
async def get_balancete(
    ano: int = Query(..., ge=2020, le=2100),
    mes: int = Query(..., ge=1, le=12),
    incluir_zerados: bool = Query(False),
    condominio_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Gera balancete de verificação para o mês/ano."""
    start_date = _first_day(ano, mes)
    end_date = _last_day(ano, mes)
    try:
        svc = BalanceSheetService(db)
        report = await svc.generate_trial_balance(
            condominio_id=condominio_id or UUID("00000000-0000-0000-0000-000000000001"),
            start_date=start_date,
            end_date=end_date,
            include_zero_balance=incluir_zerados,
        )
        return (
            report.to_dict()
            if hasattr(report, "to_dict")
            else {
                "periodo": {"inicio": start_date.isoformat(), "fim": end_date.isoformat()},
                "itens": [i.to_dict() if hasattr(i, "to_dict") else vars(i) for i in report.items],
                "total_debito": float(report.total_debit),
                "total_credito": float(report.total_credit),
                "diferenca": float(report.total_debit - report.total_credit),
            }
        )
    except Exception as e:
        logger.warning("Erro ao gerar balancete: %s", e)
        return {
            "periodo": {"inicio": start_date.isoformat(), "fim": end_date.isoformat()},
            "itens": [],
            "total_debito": 0.0,
            "total_credito": 0.0,
            "diferenca": 0.0,
            "aviso": "Sem lançamentos contábeis para o período",
        }


@router.get("/balanco-patrimonial")
async def get_balanco_patrimonial(
    data_referencia: date = Query(..., description="Data de referência (ex: 2026-03-31)"),
    condominio_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Gera Balanço Patrimonial na data especificada."""
    try:
        svc = BalanceSheetService(db)
        start_date = date(data_referencia.year, 1, 1)
        report = await svc.generate_balance_sheet(
            condominio_id=condominio_id or UUID("00000000-0000-0000-0000-000000000001"),
            start_date=start_date,
            end_date=data_referencia,
        )
        if hasattr(report, "to_dict"):
            return report.to_dict()
        return {
            "data_referencia": data_referencia.isoformat(),
            "ativo_total": float(getattr(report, "total_assets", 0)),
            "passivo_total": float(getattr(report, "total_liabilities", 0)),
            "patrimonio_liquido": float(getattr(report, "total_equity", 0)),
            "grupos": [],
        }
    except Exception as e:
        logger.warning("Erro ao gerar balanço patrimonial: %s", e)
        return {
            "data_referencia": data_referencia.isoformat(),
            "ativo_total": 0.0,
            "passivo_total": 0.0,
            "patrimonio_liquido": 0.0,
            "grupos": [],
            "aviso": "Sem dados contábeis para a data especificada",
        }


# ---------------------------------------------------------------------------
# Orçamento
# ---------------------------------------------------------------------------


@router.get("/orcamentos")
async def get_orcamento(
    ano: int = Query(..., ge=2020, le=2100),
    condominio_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Retorna orçamento anual. Cria automaticamente se não existir."""
    try:
        svc = BudgetService(db)
        report = await svc.create_budget(
            condominio_id=condominio_id or UUID("00000000-0000-0000-0000-000000000001"),
            year=ano,
            period_type=BudgetPeriodType.ANNUAL,
            base_on_previous=True,
        )
        return {
            "ano": ano,
            "status": report.status.value if hasattr(report.status, "value") else str(report.status),
            "periodo": report.period_type.value if hasattr(report.period_type, "value") else str(report.period_type),
            "total_orcado": float(getattr(report, "total_budgeted", 0)),
            "linhas": [
                {
                    "conta_codigo": item.account_code,
                    "conta_nome": item.account_name,
                    "total_orcado": float(item.total_budgeted),
                    "jan": float(item.jan),
                    "fev": float(item.feb),
                    "mar": float(item.mar),
                    "abr": float(item.apr),
                    "mai": float(item.may),
                    "jun": float(item.jun),
                    "jul": float(item.jul),
                    "ago": float(item.aug),
                    "set": float(item.sep),
                    "out": float(item.oct),
                    "nov": float(item.nov),
                    "dez": float(item.dec),
                }
                for item in getattr(report, "items", [])
            ],
        }
    except Exception as e:
        logger.warning("Erro ao criar/buscar orçamento: %s", e)
        return {
            "ano": ano,
            "status": "sem_dados",
            "linhas": [],
            "total_orcado": 0.0,
            "aviso": "Sem lançamentos do ano anterior para projetar orçamento",
        }


@router.get("/orcamentos/execucao")
async def get_orcamento_execucao(
    ano: int = Query(..., ge=2020, le=2100),
    mes: int = Query(..., ge=1, le=12),
    condominio_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Execução orçamentária: orçado vs realizado até o mês especificado."""
    try:
        svc = BudgetService(db)
        report = await svc.get_budget_execution(
            condominio_id=condominio_id or UUID("00000000-0000-0000-0000-000000000001"),
            year=ano,
            month=mes,
        )
        if hasattr(report, "to_dict"):
            return report.to_dict()
        linhas = []
        for item in getattr(report, "items", []):
            linhas.append(
                {
                    "conta_codigo": getattr(item, "account_code", ""),
                    "conta_nome": getattr(item, "account_name", ""),
                    "orcado": float(getattr(item, "budgeted", 0)),
                    "realizado": float(getattr(item, "realized", 0)),
                    "variacao": float(getattr(item, "variance", 0)),
                    "variacao_pct": float(getattr(item, "variance_pct", 0)),
                    "tipo_variacao": getattr(item, "variance_type", ""),
                }
            )
        return {
            "ano": ano,
            "mes": mes,
            "total_orcado": float(getattr(report, "total_budgeted", 0)),
            "total_realizado": float(getattr(report, "total_realized", 0)),
            "variacao_total": float(getattr(report, "total_variance", 0)),
            "linhas": linhas,
        }
    except Exception as e:
        logger.warning("Erro execução orçamentária: %s", e)
        return {
            "ano": ano,
            "mes": mes,
            "total_orcado": 0.0,
            "total_realizado": 0.0,
            "variacao_total": 0.0,
            "linhas": [],
            "aviso": "Sem dados orçamentários para o período",
        }


@router.get("/orcamentos/ytd")
async def get_orcamento_ytd(
    ano: int = Query(..., ge=2020, le=2100),
    condominio_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Execução YTD (Year-To-Date) do orçamento."""
    mes_atual = date.today().month
    try:
        svc = BudgetService(db)
        report = await svc.get_ytd_execution(
            condominio_id=condominio_id or UUID("00000000-0000-0000-0000-000000000001"),
            year=ano,
        )
        if hasattr(report, "to_dict"):
            return report.to_dict()
        return {
            "ano": ano,
            "mes_referencia": mes_atual,
            "total_orcado_ytd": float(getattr(report, "total_budgeted_ytd", 0)),
            "total_realizado_ytd": float(getattr(report, "total_realized_ytd", 0)),
            "variacao_ytd": float(getattr(report, "total_variance_ytd", 0)),
            "linhas": [],
        }
    except Exception as e:
        logger.warning("Erro YTD orçamento: %s", e)
        return {
            "ano": ano,
            "mes_referencia": mes_atual,
            "total_orcado_ytd": 0.0,
            "total_realizado_ytd": 0.0,
            "variacao_ytd": 0.0,
            "linhas": [],
            "aviso": "Sem dados orçamentários",
        }


# ---------------------------------------------------------------------------
# Custeio por Tipo de Serviço
# ---------------------------------------------------------------------------


@router.get("/custeio/resumo")
async def get_custeio_resumo(
    mes: date = Query(..., description="Mês de referência (ex: 2026-03-01)"),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Resumo de custos por tipo de serviço para o mês especificado."""
    svc = CostByTypeService(db)
    tipos = []
    for tipo in TIPOS_SERVICO:
        try:
            dados = await svc.calcular_custo_estimado(tipo=tipo, contrato_id=None, mes=mes)
            tipos.append(dados)
        except Exception as e:
            logger.debug("Custeio %s: %s", tipo, e)
            tipos.append({"tipo": tipo, "custo_total": 0.0, "erro": str(e)})
    total_geral = sum(t.get("custo_total", 0) for t in tipos)
    return {
        "mes": mes.isoformat(),
        "total_geral": total_geral,
        "tipos": tipos,
    }


@router.post("/custeio/calcular", status_code=201)
async def calcular_custo(
    tipo: str,
    mes: date,
    contrato_id: int | None = None,
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Calcula custo estimado para um tipo de serviço específico."""
    svc = CostByTypeService(db)
    return await svc.calcular_custo_estimado(tipo=tipo, contrato_id=contrato_id, mes=mes)


@router.get("/custeio/margem-por-tipo")
async def get_margem_por_tipo(
    mes: date = Query(..., description="Mês de referência (ex: 2026-03-01)"),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Margem de contribuição por tipo de serviço."""
    svc = CostByTypeService(db)
    try:
        resumo = await svc.get_resumo_margem_por_tipo(mes=mes)
        return {"mes": mes.isoformat(), "tipos": resumo}
    except Exception as e:
        logger.warning("Erro margem por tipo: %s", e)
        return {"mes": mes.isoformat(), "tipos": [], "aviso": str(e)}


@router.get("/custeio/listar")
async def listar_custos(
    tipo: str | None = Query(None),
    mes: date | None = Query(None),
    contrato_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Lista custos registrados por tipo."""
    svc = CostByTypeService(db)
    try:
        itens = await svc.listar_custos_por_tipo(
            tipo=tipo,
            mes=mes,
            contrato_id=contrato_id,
            skip=skip,
            limit=limit,
        )
        return {"total": len(itens), "itens": itens}
    except Exception as e:
        logger.warning("Erro listar custos: %s", e)
        return {"total": 0, "itens": [], "aviso": str(e)}


@router.post("/custeio/registrar", status_code=201)
async def registrar_custo(
    payload: dict,
    db: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> dict:
    """Registra custo real para um tipo de serviço/contrato."""
    svc = CostByTypeService(db)
    try:
        resultado = await svc.registrar_custo(**payload)
        return {"sucesso": True, "dados": resultado}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )


# ---------------------------------------------------------------------------
# DRE simplificado (fallback quando não há dados contábeis)
# ---------------------------------------------------------------------------


async def _dre_simplificado(ano: int, mes_inicio: int, mes_fim: int, db: AsyncSession) -> dict:
    """Gera DRE usando NFS-e e payables reais como fallback."""
    from sqlalchemy import text

    start_dt = date(ano, mes_inicio, 1)
    end_dt = _last_day(ano, mes_fim)

    # Receita: NFS-e no periodo — FONTE REAL nfse_emitidas_nacional (portal nacional, cStat 100)
    r = await db.execute(
        text(
            "SELECT COALESCE(SUM(valor_servicos), 0) as receita, "
            "COALESCE(SUM(iss_valor), 0) as iss "
            "FROM nfse_emitidas_nacional WHERE data_emissao >= :s AND data_emissao <= :e"
        ),
        {"s": start_dt, "e": end_dt},
    )
    row = r.fetchone()
    receita_bruta = float(row[0]) if row else 0.0
    iss = float(row[1]) if row else 0.0

    # Se nao tem NFS-e no periodo, ESTIMAR por MRR dos contratos ativos (marcado como estimativa)
    receita_estimada = False
    if receita_bruta == 0:
        r2 = await db.execute(
            text("SELECT COALESCE(SUM(monthly_value), 0) FROM client_contracts WHERE lower(status::text) IN ('ativo','active')")
        )
        mrr = float(r2.scalar() or 0)
        n_meses = mes_fim - mes_inicio + 1
        receita_bruta = mrr * n_meses
        iss = receita_bruta * 0.05
        receita_estimada = receita_bruta > 0

    receita_liquida = receita_bruta - iss

    # CUSTO/FOLHA E DESPESAS — FONTE REAL: razão (accounting_entries), MESMA base do /accounting/dre.
    # A folha própria (CCT, 6 meses ~R$535k) está lançada em 4.1.1 (pessoal) e encargos em 4.1.2, por
    # competência. NÃO usamos hr_payslips (só tem 2026-03 populado → 1 mês reportado como o ano todo,
    # inflava o EBITDA). Onde não há lançamento no mês, entra 0 (honesto).
    ci = f"{ano:04d}-{mes_inicio:02d}"
    cf = f"{ano:04d}-{mes_fim:02d}"
    rz = await db.execute(
        text(
            "SELECT "
            "  SUM(CASE WHEN conta_debito LIKE '4.1.1%' THEN valor ELSE 0 END)::float AS pessoal, "
            "  SUM(CASE WHEN conta_debito LIKE '4.1.2%' THEN valor ELSE 0 END)::float AS encargos, "
            "  SUM(CASE WHEN conta_debito LIKE '4%' OR conta_debito LIKE '3.2%' THEN valor ELSE 0 END)::float AS total_desp, "
            "  COUNT(DISTINCT periodo_competencia) FILTER (WHERE conta_debito LIKE '4.1.1%') AS meses_folha "
            "FROM accounting_entries "
            "WHERE status = 'confirmado' AND periodo_competencia BETWEEN :ci AND :cf"
        ),
        {"ci": ci, "cf": cf},
    )
    rowf = rz.fetchone()
    folha = float(rowf[0] or 0)
    encargos_raz = float(rowf[1] or 0)
    total_desp_raz = float(rowf[2] or 0)
    meses_com_folha = int(rowf[3] or 0)
    # Encargos patronais lançados no razão (4.1.2) — exibidos como linha do custo.
    fgts = encargos_raz
    n_meses_periodo = mes_fim - mes_inicio + 1
    cpv = folha + encargos_raz  # custo dos serviços = pessoal + encargos patronais
    # Despesas operacionais = demais lançamentos 4.x/3.2 do razão fora de pessoal+encargos
    desp_op = max(total_desp_raz - cpv, 0)

    lucro_bruto = receita_liquida - cpv
    ebitda = lucro_bruto - desp_op

    # IR + CSLL (Lucro Real: 15% IR + 10% adicional + 9% CSLL)
    ir = max(ebitda * 0.15, 0) + max((ebitda - 20000) * 0.10, 0)
    csll = max(ebitda * 0.09, 0)
    lucro_liquido = ebitda - ir - csll

    mb = (lucro_bruto / receita_bruta * 100) if receita_bruta > 0 else 0
    mo = (ebitda / receita_bruta * 100) if receita_bruta > 0 else 0
    ml = (lucro_liquido / receita_bruta * 100) if receita_bruta > 0 else 0

    grupos = [
        {
            "grupo": "receita_bruta",
            "nome": "Receita Bruta de Servicos",
            "valor": receita_bruta,
            "itens": [
                {"nome": "NFS-e Emitidas" if not receita_estimada else "Estimativa por contratos ativos (sem NFS-e no período)", "valor": receita_bruta},
            ],
        },
        {
            "grupo": "deducoes",
            "nome": "(−) Deducoes da Receita",
            "valor": -iss,
            "itens": [
                {"nome": "ISS 5% (Manaus)", "valor": -iss},
            ],
        },
        {"grupo": "receita_liquida", "nome": "Receita Liquida", "valor": receita_liquida, "is_total": True},
        {
            "grupo": "custo_servicos",
            "nome": "(−) Custos dos Servicos Prestados",
            "valor": -cpv,
            "itens": [
                {"nome": "Folha de Pagamento (razão 4.1.1)", "valor": -folha},
                {"nome": "Encargos patronais (razão 4.1.2)", "valor": -fgts},
            ],
        },
        {"grupo": "lucro_bruto", "nome": "Lucro Bruto", "valor": lucro_bruto, "is_total": True},
        {
            "grupo": "despesas_operacionais",
            "nome": "(−) Despesas Operacionais",
            "valor": -desp_op,
            "itens": [
                {"nome": "Fornecedores e outras despesas (payables)", "valor": -desp_op},
            ],
        },
        {"grupo": "despesas_administrativas", "nome": "(−) Despesas Administrativas", "valor": 0.0, "itens": []},
        {"grupo": "despesas_financeiras", "nome": "(±) Resultado Financeiro", "valor": 0.0, "itens": []},
        {"grupo": "lucro_operacional", "nome": "EBITDA", "valor": ebitda, "is_total": True},
        {
            "grupo": "ir_csll",
            "nome": "(−) IRPJ + CSLL (Lucro Real)",
            "valor": -(ir + csll),
            "itens": [
                {"nome": "IRPJ 15% + adicional", "valor": -ir},
                {"nome": "CSLL 9%", "valor": -csll},
            ],
        },
        {"grupo": "lucro_liquido", "nome": "Lucro Liquido do Exercicio", "valor": lucro_liquido, "is_total": True},
    ]

    return {
        "periodo": {
            "ano": ano,
            "mes_inicio": mes_inicio,
            "mes_fim": mes_fim,
            "inicio": start_dt.isoformat(),
            "fim": end_dt.isoformat(),
        },
        "grupos": grupos,
        "margem_bruta_pct": round(mb, 1),
        "margem_operacional_pct": round(mo, 1),
        "margem_liquida_pct": round(ml, 1),
        "regime": "Lucro Real",
        "fonte": "dados reais (NFS-e emitidas nacional + folha/encargos/despesas do razão accounting_entries)",
        "veracidade": {
            "receita_estimada": receita_estimada,
            "meses_no_periodo": n_meses_periodo,
            "meses_com_folha_lancada": meses_com_folha,
            "folha_completa": meses_com_folha >= n_meses_periodo and folha > 0,
            "aviso": (
                None if (meses_com_folha >= n_meses_periodo and folha > 0 and not receita_estimada)
                else "Dados parciais: "
                + ("; ".join(filter(None, [
                    "receita estimada por contratos (sem NFS-e)" if receita_estimada else None,
                    f"folha lançada em {meses_com_folha} de {n_meses_periodo} mês(es)" if meses_com_folha < n_meses_periodo else None,
                    "sem folha lançada no período" if folha == 0 else None,
                ])))
            ),
        },
    }
