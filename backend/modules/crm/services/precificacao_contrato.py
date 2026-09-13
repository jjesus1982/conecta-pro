"""Simulação de custo por contrato e relatório calculado × faturado (frente 7 — 12/09/2026).

SIMULAÇÃO, não preço: nada aqui grava em `contracts`. A divergência entre o que o custo diz e
o que se fatura é RELATÓRIO para o dono — mudar preço de contrato vigente é aditivo, não rotina.

De onde vem cada número:
- custo por pessoa: o motor CCT já existente (`pricing_cct.calcular_funcao`, lê `crm_pricing_params`
  e `crm_pricing_funcoes`) — uma régua só; duas cópias divergem e a que diverge cala.
- efetivo: `posts` do contrato (por `contract_id`; se não houver, pelos postos do mesmo cliente —
  e isso sai como hipótese no resultado).
- reserva técnica · PLR sindicato · taxa admin: `crm_pricing_params` com vigência e origem.
  Sem linha, fora da vigência ou sem confirmação do dono → componente `None` e motivo. Nunca 0.
- feriados (modos 5x2/6x1/SDF): `cct_feriados` do ano da competência.
- faturado: NFS-e autorizadas do tomador (CNPJ do cliente) na competência; sem NFS-e, o valor
  mensal do contrato, com `fonte_faturado='contrato'` dito na cara.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.crm.services.precificacao_modos import (
    MODOS,
    ParametroAusente,
    aplicar_encargos_contrato,
    calcular_modo,
)

CHAVES = ("reserva_tecnica_pct", "plr_sindicato_pct", "taxa_admin_pct")


# ─────────────────────────────────────────────── parâmetros com vigência ──
def resolver_parametro(row: dict | None, ref: date) -> dict:
    """A linha do armazém → {valor, origem, vigência, aplicavel, motivo}. Função pura.

    `aplicavel` só quando vigente na data de referência E confirmado pelo dono. O valor
    viaja mesmo quando não aplicável — para a tela mostrar o que está esperando confirmação.
    """
    if not row:
        return {"valor": None, "origem": None, "vigencia_inicio": None, "vigencia_fim": None,
                "confirmado_por": None, "confirmado_em": None, "aplicavel": False,
                "motivo": "parâmetro não cadastrado em crm_pricing_params"}
    ini, fim = row.get("vigencia_inicio"), row.get("vigencia_fim")
    conf = row.get("confirmado_em")
    out = {
        "valor": None if row.get("valor") is None else float(row["valor"]),
        "origem": row.get("origem"),
        "vigencia_inicio": ini.isoformat() if isinstance(ini, date) else ini,
        "vigencia_fim": fim.isoformat() if isinstance(fim, date) else fim,
        "confirmado_por": row.get("confirmado_por"),
        "confirmado_em": conf.isoformat() if isinstance(conf, (date, datetime)) else conf,
        "aplicavel": False, "motivo": None,
    }
    if not ini:
        out["motivo"] = "sem vigência cadastrada"
    elif ini > ref or (fim and fim < ref):
        out["motivo"] = f"fora da vigência ({out['vigencia_inicio']} → {out['vigencia_fim'] or 'aberta'}) em {ref.isoformat()}"
    elif not conf:
        out["motivo"] = "aguardando confirmação do dono (confirmado_em vazio) — não entra no custo"
    else:
        out["aplicavel"] = True
    return out


async def carregar_parametros_contrato(db: AsyncSession, ref: date) -> dict[str, dict]:
    rs = (await db.execute(text(
        "SELECT chave, valor, vigencia_inicio, vigencia_fim, origem, confirmado_por, confirmado_em "
        "  FROM crm_pricing_params WHERE chave = ANY(:c)"), {"c": list(CHAVES)})).mappings().all()
    por = {r["chave"]: dict(r) for r in rs}
    return {c: resolver_parametro(por.get(c), ref) for c in CHAVES}


async def carregar_feriados(db: AsyncSession, ano: int) -> frozenset[date]:
    rs = (await db.execute(text(
        "SELECT data_feriado FROM cct_feriados WHERE is_active AND ano = :a"), {"a": ano})).scalars().all()
    return frozenset(rs)


# ───────────────────────────────────────────────────── efetivo e custo ──
_SQL_POSTOS = """
SELECT code, shift_type, shift_start_time, shift_end_time, coalesce(required_headcount, 0) AS hc
  FROM posts WHERE is_active AND {onde} ORDER BY code
"""


async def _postos(db: AsyncSession, contrato: dict) -> tuple[list[dict], list[str]]:
    hip: list[str] = []
    rs = (await db.execute(text(_SQL_POSTOS.format(onde="contract_id = :id")), {"id": contrato["id"]})).mappings().all()
    if not rs:
        rs = (await db.execute(text(_SQL_POSTOS.format(onde="client_id = :id")), {"id": contrato["client_id"]})).mappings().all()
        if rs:
            hip.append("postos ligados pelo CLIENTE (posts.contract_id vazio) — confira se são deste contrato")
    return [dict(r) for r in rs], hip


def _divide_turnos(p: dict) -> tuple[int, int, str | None]:
    """(diurno, noturno, hipótese) a partir do posto. 12x36 sem horário → metade/metade."""
    hc = int(p["hc"] or 0)
    ini = p.get("shift_start_time")
    if ini is not None:
        return (0, hc, None) if ini.hour >= 18 or ini.hour < 5 else (hc, 0, None)
    if (p.get("shift_type") or "").lower() == "12x36":
        return hc - hc // 2, hc // 2, f"posto {p['code']}: 12x36 sem horário cadastrado — assumido {hc - hc // 2} dia / {hc // 2} noite"
    return hc, 0, None


async def custo_mao_de_obra(db: AsyncSession, contrato: dict) -> dict:
    """Σ efetivo × custo CCT por função (motor existente). Sem posto = sem cálculo, com motivo."""
    from modules.crm.services.pricing_cct import calcular_funcao

    postos, hip = await _postos(db, contrato)
    if not postos:
        return {"efetivo": 0, "custo_mao_de_obra": None, "preco_motor": None, "divisor": None,
                "hipoteses": hip, "motivo_sem_calculo": "nenhum posto ativo ligado ao contrato nem ao cliente"}
    funcs = {}
    for turno, nome in (("diurno", "AGP P1 Diurno"), ("noturno", "AGP P1 Noturno")):
        row = (await db.execute(text("SELECT * FROM crm_pricing_funcoes WHERE nome ILIKE :n AND ativo"), {"n": nome})).mappings().first()
        if not row:
            return {"efetivo": 0, "custo_mao_de_obra": None, "preco_motor": None, "divisor": None,
                    "hipoteses": hip, "motivo_sem_calculo": f"função '{nome}' não cadastrada em crm_pricing_funcoes"}
        funcs[turno] = await calcular_funcao(db, dict(row))
    dia = noite = 0
    for p in postos:
        d, n, h = _divide_turnos(p)
        dia, noite = dia + d, noite + n
        if h:
            hip.append(h)
    efetivo = dia + noite
    if efetivo <= 0:
        return {"efetivo": 0, "custo_mao_de_obra": None, "preco_motor": None, "divisor": None,
                "hipoteses": hip, "motivo_sem_calculo": "postos sem efetivo (required_headcount = 0)"}
    custo = dia * funcs["diurno"]["custo_total"] + noite * funcs["noturno"]["custo_total"]
    preco = dia * funcs["diurno"]["preco"] + noite * funcs["noturno"]["preco"]
    return {
        "efetivo": efetivo, "efetivo_diurno": dia, "efetivo_noturno": noite,
        "custo_por_pessoa_diurno": funcs["diurno"]["custo_total"],
        "custo_por_pessoa_noturno": funcs["noturno"]["custo_total"],
        "custo_mao_de_obra": round(custo, 2), "preco_motor": round(preco, 2),
        "divisor": funcs["diurno"]["divisor"], "hipoteses": hip, "motivo_sem_calculo": None,
    }


# ─────────────────────────────────────────────────────────── simulação ──
async def _contrato(db: AsyncSession, contract_id: str) -> dict | None:
    r = (await db.execute(text("""
        SELECT c.id::text AS id, c.contract_number, c.client_id::text AS client_id, c.status,
               c.monthly_value::float AS monthly_value, cl.name AS cliente,
               regexp_replace(coalesce(cl.document_number,''),'[^0-9]','','g') AS cnpj
          FROM contracts c JOIN clients cl ON cl.id = c.client_id
         WHERE c.id::text = :id OR c.contract_number = :id"""), {"id": contract_id})).mappings().first()
    return dict(r) if r else None


def _ref(competencia: str | None) -> date:
    if not competencia:
        return date.today().replace(day=1)
    try:
        return datetime.strptime(competencia[:7], "%Y-%m").date()
    except ValueError as e:
        raise ParametroAusente(f"competência inválida: {competencia!r} (use AAAA-MM)") from e


async def simular_contrato(db: AsyncSession, contract_id: str, competencia: str | None = None,
                           modo: str | None = None, entradas: dict | None = None) -> dict:
    """Custo calculado do contrato na competência. NÃO grava nada.

    `modo` + `entradas` (opcional): total pelo modo de cálculo da ficha (montante, hora, dias
    fixos…) — vira `preco_calculado`; sem modo, o preço é o do motor CCT (custo ÷ divisor).
    """
    ctr = await _contrato(db, contract_id)
    if not ctr:
        raise ParametroAusente(f"contrato {contract_id!r} não encontrado")
    ref = _ref(competencia)
    params = await carregar_parametros_contrato(db, ref)
    mo = await custo_mao_de_obra(db, ctr)
    out: dict = {
        "contrato": ctr["contract_number"], "cliente": ctr["cliente"], "status": ctr["status"],
        "competencia": ref.strftime("%Y-%m"), "valor_contrato": ctr["monthly_value"],
        "efetivo": mo["efetivo"], "custo_mao_de_obra": mo["custo_mao_de_obra"],
        "parametros": params, "hipoteses": list(mo["hipoteses"]), "avisos": [],
        "componentes": {"reserva_tecnica": None, "plr_sindicato": None, "taxa_admin": None},
        "custo_calculado": None, "preco_calculado": None, "modo": None,
        "motivo_sem_calculo": mo["motivo_sem_calculo"],
        "simulacao": True, "gravou": False,
    }
    for c, p in params.items():
        if not p["aplicavel"]:
            out["avisos"].append(f"{c}: {p['motivo']}")
    if mo["custo_mao_de_obra"] is not None:
        pct = {c: (p["valor"] if p["aplicavel"] else None) for c, p in params.items()}
        enc = aplicar_encargos_contrato(mo["custo_mao_de_obra"], reserva_tecnica_pct=pct["reserva_tecnica_pct"],
                                        plr_sindicato_pct=pct["plr_sindicato_pct"], taxa_admin_pct=pct["taxa_admin_pct"])
        out["componentes"] = {k: enc[k] for k in ("reserva_tecnica", "plr_sindicato", "taxa_admin")}
        out["custo_calculado"] = enc["custo_calculado"]
        # preço pela MESMA regra do motor: custo ÷ (1 − tributos − margem)
        out["preco_calculado"] = round(enc["custo_calculado"] / mo["divisor"], 2) if mo["divisor"] else None
        out["custo_por_pessoa"] = {"diurno": mo["custo_por_pessoa_diurno"], "noturno": mo["custo_por_pessoa_noturno"]}
        out["efetivo_por_turno"] = {"diurno": mo["efetivo_diurno"], "noturno": mo["efetivo_noturno"]}
    if modo:
        if modo not in MODOS:
            raise ParametroAusente(f"modo desconhecido: {modo!r}")
        e = {k: v for k, v in (entradas or {}).items() if v not in (None, "")}
        e = {k: (int(v) if k == "postos" else float(v)) for k, v in e.items()}
        feriados = await carregar_feriados(db, ref.year)
        if modo.startswith("dias_fixos_") and not feriados:
            out["avisos"].append(f"cct_feriados sem feriado ativo em {ref.year} — 5x2/6x1/SDF contam só o calendário")
        r = calcular_modo(modo, competencia=ref, feriados=feriados, **e)
        r["feriados_no_ano"] = len(feriados)
        out["modo"] = r
        out["preco_calculado"] = r["total"]
    return out


# ───────────────────────────────────────────────── calculado × faturado ──
async def faturado_na_competencia(db: AsyncSession, cnpj: str, ref: date) -> float | None:
    if not cnpj:
        return None
    v = (await db.execute(text("""
        SELECT sum(valor_servicos)::float FROM nfses
         WHERE active AND status = 'autorizada'
           AND regexp_replace(coalesce(tomador_cpf_cnpj,''),'[^0-9]','','g') = :c
           AND date_trunc('month', data_competencia) = CAST(:m AS date)"""),
        {"c": cnpj, "m": ref})).scalar()
    return None if v is None else round(float(v), 2)


async def relatorio_calculado_vs_faturado(db: AsyncSession, competencia: str | None = None) -> list[dict]:
    """Uma linha por contrato ativo. Só lê."""
    ref = _ref(competencia)
    ids = (await db.execute(text(
        "SELECT id::text FROM contracts WHERE status = 'active' ORDER BY monthly_value DESC, contract_number"))).scalars().all()
    # cliente com mais de um contrato ativo: postos (por client_id) e NFS-e (por CNPJ) são do
    # CLIENTE — a soma repete nos dois contratos. Medido no staging: Mirante das Flores (00010 e
    # 00016) e Villa dos Pássaros (00009 e 00018). Sem posts.contract_id não há como separar.
    repetidos = dict((await db.execute(text(
        "SELECT client_id::text, count(*) FROM contracts WHERE status = 'active' GROUP BY 1 HAVING count(*) > 1"))).all())
    linhas: list[dict] = []
    for cid in ids:
        s = await simular_contrato(db, cid, ref.strftime("%Y-%m"))
        ctr = await _contrato(db, cid)
        fat = await faturado_na_competencia(db, ctr["cnpj"], ref)
        if ctr["client_id"] in repetidos:
            s["hipoteses"].append(f"cliente com {repetidos[ctr['client_id']]} contratos ativos: efetivo e NFS-e são do "
                                  "cliente e se repetem entre eles — separar exige posts.contract_id")
        fonte, motivo_fat = "nfse", None
        if fat is None:
            if ctr["monthly_value"] and ctr["monthly_value"] > 0:
                fat, fonte = ctr["monthly_value"], "contrato"
            else:
                fonte, motivo_fat = None, f"sem NFS-e em {ref.strftime('%Y-%m')} e valor mensal do contrato vazio"
        calc = s["preco_calculado"]
        linha = {
            "contract_number": s["contrato"], "cliente": s["cliente"], "efetivo": s["efetivo"],
            "custo_calculado": s["custo_calculado"], "preco_calculado": calc,
            "faturado": fat, "fonte_faturado": fonte, "motivo_sem_faturado": motivo_fat,
            "motivo_sem_calculo": s["motivo_sem_calculo"],
            "divergencia_reais": None, "divergencia_pct": None,
            "parametros_ausentes": [c for c, p in s["parametros"].items() if not p["aplicavel"]],
            "hipoteses": s["hipoteses"],
        }
        if isinstance(calc, (int, float)) and isinstance(fat, (int, float)):
            linha["divergencia_reais"] = round(fat - calc, 2)
            linha["divergencia_pct"] = round((fat - calc) / calc * 100, 2) if calc else None
        linhas.append(linha)
    return linhas
