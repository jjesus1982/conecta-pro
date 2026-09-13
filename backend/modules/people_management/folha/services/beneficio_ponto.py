"""Benefício ligado ao ponto — VT/VR pela escala e pelas batidas, em PARALELO CEGO (frente 03, 12/09/2026).

O que a DGX faz e nós não fazíamos: o pedido de benefício do mês é a PREVISÃO (dias que a escala
diz que a pessoa vai trabalhar) corrigida pelo que aconteceu no mês ANTERIOR (recebeu por N dias,
trabalhou M → crédito ou débito). As colunas são as dela, por pessoa × competência × benefício:
  planejado_ant · trabalhado_ant · recebido_ant · direito_ant · saldo_ant · previsão · +ponto ·
  −ponto · crédito/débito · quantidade · unitário · total — com o MAPA DE FREQUÊNCIA dia a dia.

Decisões do pré-mortem (12/09) que este arquivo obedece — não reabrir:
- PARALELO CEGO: grava só em `folha_beneficio_conferencia`. NÃO escreve em folha, holerite,
  pagamento nem pedido de portal. A tela mostra calculado × concedido (folha) × portal.
- "Sem anterior" é ESTADO (`estado='sem_anterior'`), nunca 0: sem o anterior a quantidade é a
  previsão pura e o crédito/débito fica NULL.
- Constante de negócio vem do BANCO: unitário do VR/VT e horas mínimas do dia em
  `cct_benefit_configs` (VR cai para `cct_beneficios.valor_minimo` se não houver config). Sem
  parâmetro o estado é `sem_parametro` — nunca um número.
- NENHUM repasse automático: `abrir_pedido_reajuste` cria RASCUNHO na Central (criar_rascunho),
  sem executor registrado — aprovar não muda preço; preço muda por aditivo assinado.

Fatos medidos que moldam o cálculo:
- `gp_clock_punches.punch_timestamp` guarda HORA LOCAL de Manaus (created_at = punch + 4h,
  medido em 11/09/2026); o dia do turno é o dia da ENTRADA, como em horas_service.
- `shifts` tem linhas 'cancelled' duplicando datas 'scheduled' — conta-se DATA DISTINTA não cancelada.
- Antes do ponto próprio (14/08/2026) muita gente não tem batida nenhuma no mês: aí trabalhado é
  `sem_ponto`, não zero, e o anterior não gera ajuste (`anterior_sem_ponto`).
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import text

logger = logging.getLogger(__name__)

BENEFICIOS = ("VR", "VT")
MESES_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro",
            "Outubro", "Novembro", "Dezembro"]
#: legenda do mapa de frequência (um caractere por dia)
LEGENDA = {"T": "trabalhou", "E": "trabalhou fora da escala", "F": "falta", "I": "ponto insuficiente (< horas mínimas)",
           "S": "sem ponto no mês", "O": "folga", "V": "férias", "A": "afastado", "X": "fora do vínculo",
           "?": "escala não cadastrada no dia"}

#: Staging recebe por aqui (IF NOT EXISTS); produção recebe pelo integrador — DDL no relatório da frente.
DDL = """
CREATE TABLE IF NOT EXISTS folha_beneficio_conferencia (
  id bigserial PRIMARY KEY,
  employee_id uuid NOT NULL,
  competencia date NOT NULL,
  beneficio varchar(4) NOT NULL,
  operadora varchar(20),
  estado varchar(24) NOT NULL,
  planejado_anterior integer, trabalhado_anterior integer, recebido_anterior numeric(12,2),
  direito_anterior integer, saldo_anterior integer,
  previsao integer, mais_ponto integer, menos_ponto integer, credito_debito integer, quantidade integer,
  unitario numeric(12,2), total numeric(12,2),
  concedido_folha numeric(12,2),
  portal_valor numeric(12,2), portal_pedido varchar(40), portal_cartao varchar(40),
  mapa jsonb,
  fonte_escala varchar(30),
  calculado_em timestamptz DEFAULT now(),
  UNIQUE (employee_id, competencia, beneficio)
)
"""


@dataclass
class Parametros:
    #: ('VR','SOLIDES') / ('VT','SOLIDES') / ('VT','SINETRAM') → valor por dia
    por_operadora: dict[tuple[str, str], Decimal] = field(default_factory=dict)
    horas_minimas: Decimal | None = None
    fonte: dict = field(default_factory=dict)

    @property
    def unitarios(self) -> dict[str, set[Decimal]]:
        out: dict[str, set[Decimal]] = {}
        for (b, _op), v in self.por_operadora.items():
            out.setdefault(b, set()).add(v)
        return out

    def unitario(self, beneficio: str, operadora: str) -> Decimal | None:
        return self.por_operadora.get((beneficio, operadora)) or (
            self.por_operadora.get((beneficio, "")) if beneficio == "VR" else None)


async def parametros(db) -> Parametros:
    """Unitários e horas mínimas do banco. VR sem config cai para o piso da CCT (cct_beneficios)."""
    p = Parametros()
    rows = (await db.execute(text(
        "SELECT lower(tipo_beneficio), upper(coalesce(operadora,'')), valor_empresa FROM cct_benefit_configs "
        "WHERE coalesce(ativo,true) AND (vigencia_inicio IS NULL OR vigencia_inicio <= current_date) "
        "AND (vigencia_fim IS NULL OR vigencia_fim >= current_date)"))).fetchall()
    for tipo, op, valor in rows:
        if valor is None:
            continue
        if tipo == "vale_refeicao":
            p.por_operadora[("VR", op or "SOLIDES")] = Decimal(valor)
            p.por_operadora.setdefault(("VR", ""), Decimal(valor))
            p.fonte["VR"] = "cct_benefit_configs"
        elif tipo == "vale_transporte" and op:
            p.por_operadora[("VT", op)] = Decimal(valor)
            p.fonte[f"VT/{op}"] = "cct_benefit_configs"
        elif tipo == "beneficio_horas_minimas_dia":
            p.horas_minimas = Decimal(valor)
            p.fonte["horas_minimas"] = "cct_benefit_configs"
    if ("VR", "") not in p.por_operadora:
        v = (await db.execute(text(
            "SELECT valor_minimo FROM cct_beneficios WHERE tipo_beneficio='vale_refeicao' AND is_active "
            "AND valor_minimo IS NOT NULL ORDER BY updated_at DESC LIMIT 1"))).scalar()
        if v is not None:
            p.por_operadora[("VR", "")] = Decimal(v)
            p.por_operadora[("VR", "SOLIDES")] = Decimal(v)
            p.fonte["VR"] = "cct_beneficios.valor_minimo"
    return p


# ───────────────────────── mapa de frequência ─────────────────────────

def _dias_do_mes(ano: int, mes: int) -> list[date]:
    return [date(ano, mes, d) for d in range(1, calendar.monthrange(ano, mes)[1] + 1)]


def _comp(ano: int, mes: int) -> tuple[date, date]:
    return date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])


def _anterior(ano: int, mes: int) -> tuple[int, int]:
    return (ano - 1, 12) if mes == 1 else (ano, mes - 1)


async def _horas_por_dia(db, employee_id: str, ano: int, mes: int) -> dict[date, float]:
    """Horas trabalhadas por dia (dia da ENTRADA), pareando como horas_service — mesma régua."""
    from modules.people_management.ponto.services.horas_service import MAX_TURNO_H, SQL_BATIDAS, params_batidas

    p = params_batidas(employee_id, mes, ano)
    rows = (await db.execute(SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")})).fetchall()
    ini, fim = p["_ini_mes"], p["_fim_mes"]
    horas: dict[date, float] = {}
    i = 0
    while i < len(rows) - 1:
        entrada, saida = rows[i][1], rows[i + 1][1]
        dur = (saida - entrada).total_seconds() / 3600.0
        if not (0 < dur <= MAX_TURNO_H):
            i += 1
            continue
        i += 2
        if ini <= entrada < fim:
            horas[entrada.date()] = horas.get(entrada.date(), 0.0) + dur
    # batida solitária no dia ainda é presença registrada (hora desconhecida) — marca 0h
    for _t, ts in rows:
        if ini <= ts < fim:
            horas.setdefault(ts.date(), 0.0)
    return horas


async def mapa_frequencia(db, employee_id: str, ano: int, mes: int, horas_minimas: Decimal | None,
                          emp: dict | None = None) -> dict:
    """Dia a dia da competência: T/E/F/I/S/O/V/A/X/? (ver LEGENDA). Nunca inventa escala."""
    ini, fim = _comp(ano, mes)
    if emp is None:
        r = (await db.execute(text(
            "SELECT escala_padrao, data_admissao, coalesce(data_desligamento, data_demissao) "
            "FROM employees WHERE id = CAST(:e AS uuid)"), {"e": employee_id})).first()
        emp = {"escala_padrao": r[0], "data_admissao": r[1], "data_demissao": r[2]} if r else {}
    escala = (emp.get("escala_padrao") or "").strip()

    planejados = {r[0] for r in (await db.execute(text(
        "SELECT DISTINCT shift_date FROM shifts WHERE employee_id = CAST(:e AS uuid) "
        "AND shift_date BETWEEN CAST(:i AS date) AND CAST(:f AS date) "
        "AND lower(coalesce(status,'')) <> 'cancelled' AND NOT coalesce(is_off_day,false)"),
        {"e": employee_id, "i": ini, "f": fim})).fetchall()}
    fonte_escala = "shifts"
    if not planejados:
        if escala == "44h":
            planejados = {d for d in _dias_do_mes(ano, mes) if d.weekday() < 6}  # seg–sáb
            fonte_escala = "escala_padrao"
        elif escala:
            fonte_escala = "escala_padrao_sem_dias"  # 12x36 sem escala lançada: sabe quantos, não quais
        else:
            fonte_escala = "sem_escala"

    ferias = [(r[0], r[1]) for r in (await db.execute(text(
        "SELECT start_date, end_date FROM hr_vacation_requests WHERE employee_id = CAST(:e AS uuid) "
        "AND upper(coalesce(status,'')) = 'APPROVED' AND start_date <= CAST(:f AS date) AND end_date >= CAST(:i AS date)"),
        {"e": employee_id, "i": ini, "f": fim})).fetchall()]
    # mesma régua da coorte do ponto: em curso = status em_andamento/ativo sem data_retorno
    afast = [(r[0], r[1]) for r in (await db.execute(text(
        "SELECT data_inicio, CASE WHEN lower(coalesce(status,'')) IN ('em_andamento','ativo') AND data_retorno IS NULL "
        "THEN NULL ELSE coalesce(data_retorno, data_fim_prevista) END "
        "FROM sst_afastamentos WHERE employee_id = CAST(:e AS uuid) AND lower(coalesce(status,'')) NOT IN ('cancelado','cancelled') "
        "AND data_inicio <= CAST(:f AS date) AND (data_retorno IS NULL OR data_retorno >= CAST(:i AS date))"),
        {"e": employee_id, "i": ini, "f": fim})).fetchall()]
    horas = await _horas_por_dia(db, employee_id, ano, mes)
    tem_ponto = bool(horas)
    adm, dem = emp.get("data_admissao"), emp.get("data_demissao")

    mapa: dict[str, str] = {}
    for d in _dias_do_mes(ano, mes):
        if (adm and d < adm) or (dem and d > dem):
            cod = "X"
        elif any(a <= d <= b for a, b in ferias):
            cod = "V"
        elif any(a <= d and (b is None or d <= b) for a, b in afast):
            cod = "A"
        elif d in horas:
            h = horas[d]
            if horas_minimas is not None and Decimal(str(h)) < horas_minimas:
                cod = "I"
            else:
                cod = "T" if (d in planejados or fonte_escala == "escala_padrao_sem_dias") else "E"
        elif fonte_escala in ("sem_escala", "escala_padrao_sem_dias"):
            cod = "?"
        elif d in planejados:
            cod = "F" if tem_ponto else "S"
        else:
            cod = "O"
        mapa[d.isoformat()] = cod

    cont = {k: sum(1 for v in mapa.values() if v == k) for k in LEGENDA}
    # previsão: dias planejados dentro do vínculo e fora de férias/afastamento
    if fonte_escala == "escala_padrao_sem_dias":
        from modules.people_management.folha.services.calculo_service import dias_vt_vr
        prev_vt, prev_vr = dias_vt_vr(escala, mes, ano)
        ocupados = cont["V"] + cont["A"] + cont["X"]
        prev_vt, prev_vr = max(0, prev_vt - ocupados), max(0, prev_vr - ocupados)
    else:
        uteis = [date.fromisoformat(k) for k, v in mapa.items() if v in ("T", "F", "S", "I") and date.fromisoformat(k) in planejados]
        prev_vt = len(uteis)
        prev_vr = len([d for d in uteis if d.weekday() < 5]) if escala == "44h" else prev_vt  # 44h: sábado sem VR
    trab = [date.fromisoformat(k) for k, v in mapa.items() if v in ("T", "E")]
    return {
        "mapa": mapa, "legenda": LEGENDA, "contagem": cont, "fonte_escala": fonte_escala, "escala": escala,
        "tem_ponto": tem_ponto, "planejados": len(planejados),
        "previsao": {"VT": prev_vt, "VR": prev_vr},
        "trabalhado": {"VT": len(trab), "VR": len([d for d in trab if d.weekday() < 5]) if escala == "44h" else len(trab)},
        "horas": {k.isoformat(): round(v, 2) for k, v in horas.items()},
    }


# ───────────────────────── cálculo por competência ─────────────────────────

async def _garantir_tabela(db) -> None:
    await db.execute(text(DDL))


async def calcular_competencia(db, ano: int, mes: int, employee_ids: list[str] | None = None) -> dict:
    """Calcula VR e VT de todo mundo com vínculo na competência e grava na conferência.

    Não toca em folha/holerite/pagamento. Idempotente: recalcular sobrescreve o cálculo e
    preserva as colunas `portal_*` (que vêm de `importar_portal`)."""
    await _garantir_tabela(db)
    par = await parametros(db)
    ini, fim = _comp(ano, mes)
    aa, ma = _anterior(ano, mes)
    ini_a, _fim_a = _comp(aa, ma)
    where_ids = "AND e.id = ANY(CAST(:ids AS uuid[]))" if employee_ids else ""
    emps = (await db.execute(text(
        "SELECT e.id::text, e.nome, e.escala_padrao, e.data_admissao, coalesce(e.data_desligamento, e.data_demissao), "
        "upper(coalesce(e.vt_modalidade,'')) FROM employees e "
        "WHERE coalesce(e.is_homologacao,false) = false AND lower(coalesce(e.tipo_contrato,'')) <> 'pj' "
        "AND (e.data_admissao IS NULL OR e.data_admissao <= CAST(:f AS date)) "
        "AND (e.status = 'ativo' OR coalesce(e.data_desligamento, e.data_demissao) >= CAST(:i AS date)) "
        f"{where_ids} ORDER BY e.nome"),
        {"i": ini, "f": fim, **({"ids": employee_ids} if employee_ids else {})})).fetchall()

    from modules.people_management.folha.services.calculo_service import VR_DIA, VT_DIA, dias_vt_vr

    resumo = {"competencia": f"{ano}-{mes:02d}", "pessoas": 0, "linhas": 0, "estados": {}, "sem_parametro": []}
    for eid, nome, escala, adm, dem, modalidade in emps:
        emp = {"escala_padrao": escala, "data_admissao": adm, "data_demissao": dem}
        atual = await mapa_frequencia(db, eid, ano, mes, par.horas_minimas, emp)
        ant = await mapa_frequencia(db, eid, aa, ma, par.horas_minimas, emp)
        # o que o portal pagou no anterior (importado) — chave do crédito/débito
        rec = {r[0]: (r[1], r[2]) for r in (await db.execute(text(
            "SELECT beneficio, portal_valor, unitario FROM folha_beneficio_conferencia "
            "WHERE employee_id = CAST(:e AS uuid) AND competencia = CAST(:c AS date)"),
            {"e": eid, "c": ini_a})).fetchall()}
        try:
            d_vt, d_vr = dias_vt_vr(escala or "12x36", mes, ano)
            concedido = {"VT": Decimal(VT_DIA) * d_vt, "VR": Decimal(VR_DIA) * d_vr}
        except Exception:  # noqa: BLE001
            concedido = {"VT": None, "VR": None}
        resumo["pessoas"] += 1
        for ben in BENEFICIOS:
            operadora = "SOLIDES" if ben == "VR" else (modalidade or "")
            unit = par.unitario(ben, operadora) if operadora else None
            previsao = atual["previsao"][ben]
            linha = {
                "e": eid, "c": ini, "b": ben, "op": operadora or None, "fonte": atual["fonte_escala"],
                "prev": previsao, "unit": unit, "conc": concedido[ben],
                "mapa": {"dias": atual["mapa"], "legenda": LEGENDA, "contagem": atual["contagem"],
                         "anterior": {"competencia": f"{aa}-{ma:02d}", "dias": ant["mapa"], "contagem": ant["contagem"]},
                         "horas": atual["horas"], "escala": atual["escala"]},
                "pa": None, "ta": None, "ra": None, "da": None, "sa": None, "mp": None, "mn": None, "cd": None,
            }
            if ben == "VT" and not operadora:
                estado = "sem_modalidade"
            elif unit is None:
                estado = "sem_parametro"
            elif atual["fonte_escala"] == "sem_escala":
                estado = "sem_escala"
            else:
                estado = "ok"
            qtd = previsao
            if estado == "ok":
                linha["pa"] = ant["previsao"][ben]
                if ben not in rec or rec[ben][0] is None:
                    estado = "sem_anterior"
                elif not ant["tem_ponto"]:
                    estado = "anterior_sem_ponto"
                    linha["ra"] = Decimal(rec[ben][0])
                else:
                    recebido, unit_ant = Decimal(rec[ben][0]), rec[ben][1]
                    unit_ant = Decimal(unit_ant) if unit_ant else unit
                    dias_rec = recebido / unit_ant
                    if dias_rec != dias_rec.to_integral_value():
                        estado = "anterior_nao_integral"  # R$ pago não é múltiplo do unitário: humano decide
                        linha["ra"] = recebido
                    else:
                        ta = ant["trabalhado"][ben]
                        dr = int(dias_rec)
                        mp, mn = max(0, ta - dr), max(0, dr - ta)
                        linha.update({"ta": ta, "ra": recebido, "da": ta, "sa": dr - ta, "mp": mp, "mn": mn, "cd": mp - mn})
                        qtd = max(0, previsao + mp - mn)
            linha["estado"] = estado
            linha["qtd"] = qtd if estado not in ("sem_parametro", "sem_modalidade", "sem_escala") else None
            linha["total"] = (Decimal(qtd) * unit) if (unit is not None and linha["qtd"] is not None) else None
            if estado == "sem_parametro":
                resumo["sem_parametro"].append(f"{nome} {ben}/{operadora}")
            resumo["estados"][estado] = resumo["estados"].get(estado, 0) + 1
            resumo["linhas"] += 1
            import json as _json

            await db.execute(text(
                "INSERT INTO folha_beneficio_conferencia (employee_id, competencia, beneficio, operadora, estado, "
                " planejado_anterior, trabalhado_anterior, recebido_anterior, direito_anterior, saldo_anterior, "
                " previsao, mais_ponto, menos_ponto, credito_debito, quantidade, unitario, total, concedido_folha, mapa, fonte_escala, calculado_em) "
                "VALUES (CAST(:e AS uuid), CAST(:c AS date), :b, :op, :estado, :pa, :ta, :ra, :da, :sa, :prev, :mp, :mn, :cd, :qtd, "
                " :unit, :total, :conc, CAST(:mapa AS jsonb), :fonte, now()) "
                "ON CONFLICT (employee_id, competencia, beneficio) DO UPDATE SET operadora=EXCLUDED.operadora, estado=EXCLUDED.estado, "
                " planejado_anterior=EXCLUDED.planejado_anterior, trabalhado_anterior=EXCLUDED.trabalhado_anterior, "
                " recebido_anterior=EXCLUDED.recebido_anterior, direito_anterior=EXCLUDED.direito_anterior, saldo_anterior=EXCLUDED.saldo_anterior, "
                " previsao=EXCLUDED.previsao, mais_ponto=EXCLUDED.mais_ponto, menos_ponto=EXCLUDED.menos_ponto, credito_debito=EXCLUDED.credito_debito, "
                " quantidade=EXCLUDED.quantidade, unitario=EXCLUDED.unitario, total=EXCLUDED.total, concedido_folha=EXCLUDED.concedido_folha, "
                " mapa=EXCLUDED.mapa, fonte_escala=EXCLUDED.fonte_escala, calculado_em=now()"),
                {**{k: v for k, v in linha.items() if k != "mapa"}, "mapa": _json.dumps(linha["mapa"], default=str)})
    await db.commit()
    logger.info("benefício ponto %s: %s", resumo["competencia"], {k: v for k, v in resumo.items() if k != "sem_parametro"})
    return resumo


async def importar_portal(db, caminhos: list[str]) -> dict:
    """Lê os relatórios dos portais e grava SÓ as colunas portal_* da conferência (por CPF)."""
    from modules.people_management.folha.services.beneficios_importer import ler_pedidos_em

    await _garantir_tabela(db)
    out = {"pedidos": [], "gravados": 0, "sem_cadastro": [], "sem_competencia": []}

    # ⚠️ 13/09/2026 — ACUMULAR ANTES DE GRAVAR, por (pessoa, competência, benefício).
    # A versão anterior gravava dentro do laço com `DO UPDATE SET portal_valor = EXCLUDED...`:
    # com DOIS pedidos DISTINTOS do mesmo mês (o portal parte o mês quando há complementar),
    # o segundo apagava o primeiro em vez de somar.
    #
    # ⚠️ E o que NÃO é isto: a duplicata que o oráculo acusou em produção era de ARQUIVO, não de
    # pedido — o MESMO pedido 332373 em dois caminhos. Somar ali daria o DOBRO, que é erro de
    # dinheiro na direção contrária. A dedução por número de pedido mora em
    # `beneficios_importer.ler_pedidos_em`, régua única para este motor e para o oráculo.
    #
    # Somar no INSERT (`portal_valor = tabela + EXCLUDED`) seria pior de todo jeito: reimportar
    # dobraria em silêncio. Aqui a soma é em memória e a gravação continua sobrescrita
    # idempotente — reimportar os mesmos arquivos dá exatamente o mesmo número.
    acc: dict[tuple, dict] = {}
    for p in ler_pedidos_em(caminhos):
        if not p.competencia:
            out["sem_competencia"].append(p.arquivo)
            continue
        comp = date.fromisoformat(p.competencia + "-01")
        out["pedidos"].append({"origem": p.origem, "numero": p.numero, "competencia": p.competencia, "linhas": len(p.linhas)})
        for ln in p.linhas:
            eid = (await db.execute(text(
                "SELECT id::text FROM employees WHERE regexp_replace(coalesce(cpf,''),'[^0-9]','','g') = :c "
                "ORDER BY (status='ativo') DESC, updated_at DESC LIMIT 1"), {"c": ln.cpf})).scalar()
            if not eid:
                out["sem_cadastro"].append(f"{ln.nome} (CPF …{ln.cpf[-4:]})")
                continue
            for ben, valor in (("VR", ln.alimentacao), ("VT", ln.mobilidade)):
                if not valor:
                    continue
                a = acc.setdefault((eid, comp, ben), {"op": p.origem.upper(), "v": Decimal("0"),
                                                      "pedidos": [], "cartao": ""})
                a["v"] += Decimal(str(valor))
                if p.numero and p.numero not in a["pedidos"]:
                    a["pedidos"].append(p.numero)
                a["cartao"] = a["cartao"] or (ln.cartao or "")

    for (eid, comp, ben), a in acc.items():
        # `portal_pedido` guarda TODOS os pedidos que compõem o valor: sem isso, conferir de onde
        # veio o número depois vira arqueologia.
        await db.execute(text(
            "INSERT INTO folha_beneficio_conferencia (employee_id, competencia, beneficio, operadora, estado, portal_valor, portal_pedido, portal_cartao) "
            "VALUES (CAST(:e AS uuid), CAST(:c AS date), :b, :op, 'so_portal', :v, :n, :k) "
            "ON CONFLICT (employee_id, competencia, beneficio) DO UPDATE SET portal_valor = EXCLUDED.portal_valor, "
            " portal_pedido = EXCLUDED.portal_pedido, portal_cartao = coalesce(nullif(EXCLUDED.portal_cartao,''), folha_beneficio_conferencia.portal_cartao)"),
            {"e": eid, "c": comp, "b": ben, "op": a["op"], "v": a["v"],
             "n": "+".join(a["pedidos"])[:40], "k": a["cartao"][:40]})
        out["gravados"] += 1
    await db.commit()
    return out


# ───────────────────────── arquivo do operador ─────────────────────────

_RE_CARTAO = r"^\d{2}\.\d{2}\.\d{8}-\d$"


def _br(v: Decimal) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def montar_arquivo_operador(origem: str, linhas, competencia: str, gerado_por: str) -> str:
    """Texto do pedido para o operador, com EXATAMENTE as colunas do relatório dele.

    ⚠️ Layout OFICIAL de importação do Sólides e do SINETRAM não está documentado em casa: este
    arquivo espelha o relatório que eles emitem (colunas idênticas), e é relido pelo nosso parser
    (oráculo de ida e volta). Confirmar com o portal antes de subir — está no relatório da frente.
    SINETRAM sem nº de cartão é recusado: crédito sem cartão é crédito no cartão de ninguém."""
    import re

    ano, mes = competencia.split("-")
    quando = datetime.now().strftime("%d/%m/%Y %H:%M")
    n = len(linhas)
    if origem == "solides":
        total = sum((ln.alimentacao + ln.mobilidade for ln in linhas), Decimal(0))
        cab = [
            "CONECTA MAIS REDES E SEGURANCA",
            "CNPJ: 35.710.481/0001-03",
            "Relatório de Benefícios — PEDIDO GERADO PELO CONECTA PRO (layout oficial a confirmar com o portal)",
            f"Gerado por: {gerado_por}   Data: {quando}   Competência: {competencia}   Colaboradores: {n}   Pagamento: PIX",
            f"Valor Total do Pedido R$ {total:.2f}",
            "",
            f"{'NOME DO COLABORADOR':<45} {'CPF':<12} {'EMPRESA / UNIDADE':<26} {'ALIMENTAÇÃO':>12} {'MOBILIDADE':>12}",
        ]
        corpo = [f"{ln.nome[:44]:<45} {ln.cpf:<12} {'CONECTA MAIS PATRIMONIAL':<26} {ln.alimentacao:>12.2f} {ln.mobilidade:>12.2f}"
                 for ln in linhas]
        rod = ["", f"Relatório de {n} colaboradores ({MESES_PT[int(mes)]}/{ano})"]
        return "\n".join(cab + corpo + rod) + "\n"
    if origem == "sinetram":
        for ln in linhas:
            if not re.match(_RE_CARTAO, ln.cartao or ""):
                raise ValueError(f"SINETRAM: {ln.nome} sem nº de cartão válido ({ln.cartao!r}) — não gero crédito sem cartão")
        total = sum((ln.mobilidade for ln in linhas), Decimal(0))
        cab = [
            "PEDIDO DE VALE TRANSPORTE — SINETRAM — GERADO PELO CONECTA PRO (layout oficial a confirmar com o portal)",
            f"Gerado por: {gerado_por}   Data: {quando}   Competência {competencia}   Colaboradores: {n}   Pagamento: boleto",
            f"VALOR DO PEDIDO (SEM TAXAS/ENCARGOS)   R$ {_br(total)}",
            f"TOTAL REGISTROS   {n}",
            "",
            f"{'Código':>6} {'CPF':<14} {'Nome':<45} {'Nº Cartão':<18} {'Valor':>14}  Produto",
        ]
        corpo = []
        for i, ln in enumerate(linhas, 1):
            cpf = f"{ln.cpf[:3]}.{ln.cpf[3:6]}.{ln.cpf[6:9]}-{ln.cpf[9:]}"
            corpo.append(f"{i:>6} {cpf:<14} {ln.nome[:44]:<45} {ln.cartao:<18} R$ {_br(ln.mobilidade):>11}  VALE TRANSPORTE")
        return "\n".join(cab + corpo) + "\n"
    raise ValueError(f"operadora desconhecida: {origem!r}")


async def gerar_arquivo_operador(db, ano: int, mes: int, origem: str, gerado_por: str) -> tuple[str, str, list[str]]:
    """Arquivo do operador a partir da CONFERÊNCIA (o que o motor calculou). Devolve (nome, texto, avisos).

    Só linhas em estado calculável; quem está sem parâmetro/escala/modalidade vai para os avisos."""
    from modules.people_management.folha.services.beneficios_importer import LinhaBeneficio

    ini = date(ano, mes, 1)
    rows = (await db.execute(text(
        # o cartão é da PESSOA, não da competência: cai para o último conhecido em qualquer mês
        "SELECT e.nome, regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g'), c.beneficio, c.estado, c.total, "
        " coalesce(nullif(c.portal_cartao,''), (SELECT x.portal_cartao FROM folha_beneficio_conferencia x "
        "   WHERE x.employee_id = c.employee_id AND nullif(x.portal_cartao,'') IS NOT NULL "
        "   ORDER BY x.competencia DESC LIMIT 1), '') "
        "FROM folha_beneficio_conferencia c JOIN employees e ON e.id = c.employee_id "
        "WHERE c.competencia = CAST(:c AS date) AND upper(coalesce(c.operadora,'')) = :op ORDER BY e.nome, c.beneficio"),
        {"c": ini, "op": origem.upper()})).fetchall()
    por_cpf: dict[str, LinhaBeneficio] = {}
    avisos: list[str] = []
    for nome, cpf, ben, estado, total, cartao in rows:
        if total is None:
            avisos.append(f"{nome} {ben}: {estado} — fora do arquivo")
            continue
        ln = por_cpf.setdefault(cpf, LinhaBeneficio(cpf=cpf, nome=nome, cartao=cartao))
        if ben == "VR":
            ln.alimentacao = Decimal(total)
        else:
            ln.mobilidade = Decimal(total)
            ln.cartao = ln.cartao or cartao
    linhas = list(por_cpf.values())
    if origem.lower() == "sinetram":
        sem = [ln for ln in linhas if not ln.cartao]
        for ln in sem:
            avisos.append(f"{ln.nome}: SINETRAM sem nº de cartão conhecido — fora do arquivo")
        linhas = [ln for ln in linhas if ln.cartao]
    texto = montar_arquivo_operador(origem.lower(), linhas, f"{ano}-{mes:02d}", gerado_por)
    nome = f"{origem.upper()}_{datetime.now().strftime('%Y%m%d%H%M')}_{len(linhas)}_ConectaMais.txt"
    return nome, texto, avisos


# ───────────────────────── reajuste com repasse (PEDIDO, nunca ação) ─────────────────────────

async def simular_reajuste(db, beneficio: str, novo_unitario: Decimal, ano: int, mes: int) -> dict:
    """R$ Contrato / R$ Unitário / R$ Repasse por contrato × função. Só leitura.

    Beneficiário = ativo alocado em posto; o posto liga ao contrato por `posts.contract_id` ou,
    na falta, pelo cliente (`posts.client_id = contracts.client_id`, contrato ativo). Cliente com
    mais de um contrato ativo fica AMBÍGUO — não se divide dinheiro por chute."""
    beneficio = beneficio.upper()
    if beneficio not in BENEFICIOS:
        raise ValueError("benefício deve ser VR ou VT")
    par = await parametros(db)
    ini = date(ano, mes, 1)
    rows = (await db.execute(text(
        "SELECT e.id::text, e.nome, coalesce(e.cargo,'—'), e.escala_padrao, upper(coalesce(e.vt_modalidade,'')), p.name, "
        " p.contract_id::text, p.client_id::text, "
        " (SELECT count(*) FROM contracts c WHERE c.client_id = p.client_id AND c.status::text = 'active') "
        "FROM allocations a JOIN posts p ON p.id = a.post_id JOIN employees e ON e.id = a.employee_id "
        "WHERE coalesce(a.is_active,true) AND (a.end_date IS NULL OR a.end_date >= current_date) "
        "AND e.status = 'ativo' AND coalesce(e.is_homologacao,false) = false AND lower(coalesce(e.tipo_contrato,'')) <> 'pj'"))).fetchall()
    contratos = {r[0]: r for r in (await db.execute(text(
        "SELECT id::text, contract_number, coalesce(name,''), monthly_value, client_id::text FROM contracts WHERE status::text = 'active'"))).fetchall()}
    por_cliente: dict[str, list] = {}
    for c in contratos.values():
        por_cliente.setdefault(c[4], []).append(c)
    prev = {(r[0], r[1]): r[2] for r in (await db.execute(text(
        "SELECT employee_id::text, beneficio, previsao FROM folha_beneficio_conferencia WHERE competencia = CAST(:c AS date)"),
        {"c": ini})).fetchall()}
    from modules.people_management.folha.services.calculo_service import dias_vt_vr

    grupos: dict[tuple, dict] = {}
    avisos: list[str] = []
    for eid, nome, cargo, escala, modalidade, posto, ctr_id, cli_id, n_ctr in rows:
        c = contratos.get(ctr_id) if ctr_id else None
        if c is None and cli_id in por_cliente and len(por_cliente[cli_id]) == 1:
            c = por_cliente[cli_id][0]
        if c is None:
            chave_ctr = ("AMBÍGUO: " + " / ".join(x[1] for x in por_cliente.get(cli_id, [])) if n_ctr and n_ctr > 1
                         else f"sem contrato ativo ({posto})")
            ctr_num, ctr_val = chave_ctr, None
        else:
            ctr_num, ctr_val = f"{c[1]} · {c[2]}"[:60], c[3]
        operadora = "SOLIDES" if beneficio == "VR" else modalidade
        atual = par.unitario(beneficio, operadora) if operadora else None
        if atual is None:
            avisos.append(f"{nome}: sem unitário atual de {beneficio}/{operadora or 'sem modalidade'} — fora da simulação")
            continue
        dias = prev.get((eid, beneficio))
        fonte = "conferência"
        if dias is None:
            if not escala:
                avisos.append(f"{nome}: sem escala e sem conferência — fora da simulação")
                continue
            d_vt, d_vr = dias_vt_vr(escala, mes, ano)
            dias, fonte = (d_vt if beneficio == "VT" else d_vr), "escala_padrao"
        g = grupos.setdefault((ctr_num, cargo, operadora), {
            "contrato": ctr_num, "funcao": cargo, "operadora": operadora, "beneficiarios": 0, "dias": 0,
            "unitario_atual": atual, "unitario_novo": novo_unitario, "valor_contrato": ctr_val, "fontes": set()})
        g["beneficiarios"] += 1
        g["dias"] += int(dias)
        g["fontes"].add(fonte)
    linhas = []
    for g in grupos.values():
        rep = Decimal(g["dias"]) * (g["unitario_novo"] - g["unitario_atual"])
        linhas.append({**g, "fontes": sorted(g["fontes"]), "repasse_mes": rep,
                       "valor_contrato_novo": (Decimal(g["valor_contrato"]) + rep) if g["valor_contrato"] is not None else None})
    linhas.sort(key=lambda x: (x["contrato"], x["funcao"]))
    return {"beneficio": beneficio, "competencia": f"{ano}-{mes:02d}", "novo_unitario": novo_unitario,
            "linhas": linhas, "repasse_total_mes": sum((x["repasse_mes"] for x in linhas), Decimal(0)),
            "beneficiarios": sum(x["beneficiarios"] for x in linhas), "avisos": avisos}


async def abrir_pedido_reajuste(db, user, beneficio: str, novo_unitario: Decimal, ano: int, mes: int,
                                justificativa: str = "") -> dict:
    """Abre o PEDIDO de reajuste com repasse na Central de Aprovações. Não muda unitário nem contrato.

    Não há executor registrado para `reajuste_beneficio_repasse`: aprovar o rascunho não executa
    nada — é o registro de que a diretoria concorda em levar o repasse a cada contrato por ADITIVO
    (contract_addendums, tipo 'adjustment', assinado). O caçador checar_repasse_sem_aditivo vigia."""
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    sim = await simular_reajuste(db, beneficio, novo_unitario, ano, mes)
    if not sim["linhas"]:
        return {"ok": False, "erro": "nenhum beneficiário simulável — veja os avisos", "simulacao": sim}
    n_ctr = len({x["contrato"] for x in sim["linhas"]})
    titulo = (f"Reajuste {sim['beneficio']} → R$ {novo_unitario:.2f}/dia: repasse R$ {sim['repasse_total_mes']:.2f}/mês "
              f"em {n_ctr} contrato(s), {sim['beneficiarios']} beneficiário(s)")
    corpo = "\n".join(
        f"- {x['contrato']} · {x['funcao']} ({x['operadora']}): {x['beneficiarios']} pessoa(s) × {x['dias']} dias · "
        f"R$ {x['unitario_atual']:.2f} → R$ {x['unitario_novo']:.2f} · R$ Contrato "
        f"{('%.2f' % x['valor_contrato']) if x['valor_contrato'] is not None else 'sem dado'} · R$ Repasse {x['repasse_mes']:.2f}/mês"
        for x in sim["linhas"])
    resumo = (f"Benefício {sim['beneficio']}, competência {sim['competencia']}.\n\n{corpo}\n\n"
              f"Repasse total: R$ {sim['repasse_total_mes']:.2f}/mês.\n"
              + (f"Justificativa: {justificativa}\n" if justificativa else "")
              + ("Avisos: " + "; ".join(sim["avisos"]) + "\n" if sim["avisos"] else "")
              + "\n⚠️ Aprovar aqui NÃO altera contrato nem unitário. O preço muda por aditivo assinado, contrato a contrato.")
    payload = {"beneficio": sim["beneficio"], "competencia": sim["competencia"], "novo_unitario": str(novo_unitario),
               "repasse_total_mes": str(sim["repasse_total_mes"]),
               "contratos": [{k: (str(v) if isinstance(v, Decimal) else v) for k, v in x.items()} for x in sim["linhas"]],
               "avisos": sim["avisos"], "nao_executa": "só vira preço por aditivo assinado (contract_addendums.signed)"}
    r = await criar_rascunho(
        db, user, tipo="reajuste_beneficio_repasse", modulo="folha", titulo=titulo[:180], resumo=resumo,
        payload=payload, gate="🔴", requires_otp=False, roles_aprovador=("admin",),
        idempotency_key=f"reajuste_beneficio:{sim['beneficio']}:{novo_unitario}:{sim['competencia']}")
    return {"ok": not (isinstance(r, dict) and r.get("erro")), "rascunho": r, "simulacao": sim}


if __name__ == "__main__":  # python3 -m modules.people_management.folha.services.beneficio_ponto 2026 8 [/pasta/pdfs]
    import asyncio
    import glob
    import sys

    async def _main():
        from core.database import get_db

        gen = get_db()
        db = await gen.__anext__()
        ano, mes = int(sys.argv[1]), int(sys.argv[2])
        if len(sys.argv) > 3:
            print("portal:", await importar_portal(db, sorted(glob.glob(sys.argv[3] + "/**/*.pdf", recursive=True))))
        print("motor:", await calcular_competencia(db, ano, mes))

    asyncio.run(_main())
