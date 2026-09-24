"""VA e VT por CONTRATO/competência — a dedução da base do INSS, com procedência (DGX AA6, 24/09/2026).

Por que existe
--------------
Decisão do dono em 24/09/2026: *«vamos deduzir vale-alimentação e vale-transporte antes de aplicar
os 11% em todas as notas que tiver cessão de mão de obra»* — e cessão de mão de obra é, por
decisão dele, **toda nota da CONECTAMAIS PATRIMONIAL**. A retenção do Art. 31 da Lei 9.711/98 passa
a incidir sobre `bruto − (VA + VT)`. Em agosto as cinco notas da Patrimonial retiveram 11% do
bruto, sem dedução: só nas três linhas de setembro que já deduzem, a diferença é R$ 1.431,98.

A dedução só se sustenta com **VA e VT discriminados na própria nota** — daí `texto_discriminacao`.

O que este módulo NÃO faz, e por quê
------------------------------------
- **Nunca** usa `folha_verba_espelho` códigos 1010/1011 («Desconto VT» / «Desconto VR»). Aquilo é o
  desconto DO EMPREGADO (4% e 1% do salário base), não o custo do benefício pago pela empresa;
  deduzir por ali daria um número MENOR que o devido e o dono pagaria MAIS INSS — o oposto do
  pedido. Medido em 24/09: 1010 = R$ 22.565,23 em 354 linhas, 1011 = R$ 5.897,71 em 351 linhas.
- **Nunca** devolve um número plausível quando o efetivo do contrato está divergente. Base de
  imposto errada custa o imposto E a multa. `sabe=False` é resposta válida; chute não é.
- Não escreve em folha, holerite, alocação nem pagamento. Lê a apuração por pessoa que o motor da
  frente 03 já grava em `folha_beneficio_conferencia` (paralelo cego) e soma por cliente.

A régua do VALOR — medida contra as três linhas reais do cronograma (24/09/2026)
--------------------------------------------------------------------------------
O dono: *«tem muita rotatividade, não só lá mas em todos os condomínios, sempre fica defasado»*.
Contagem de cabeças em tabela de alocação é exatamente o dado que apodrece com rotatividade — e
seria a base de um número de imposto. Por isso a apuração aqui **não parte de um efetivo**: parte
de PESSOA × DIAS DE ESCALA NAQUELE POSTO, e o número de pessoas é CONSEQUÊNCIA da soma.

Três réguas medidas em 08/2026 contra o que o dono escreveu na nota (VA · VT):

    cliente                cronograma      escala (dias)     ponto (batida no posto)
    Laranjeiras Village   2.552 · 1.136   2.486 · 1.130     1.958 ·   890
    Ideal Flores          4.488 · 2.160   4.356 · 2.130     2.332 · 1.130
    Prime Arena           1.804 ·   880   2.288 · 1.140     1.496 ·   730

**A escala vence.** No Laranjeiras erra 0,5% no VT e 2,6% no VA; no Ideal Flores 1,4% e 2,9%. E
acerta o efetivo do Laranjeiras na mosca (8 = 8), excluindo sozinha tanto quem está alocado sem
trabalhar (ELEN XAVIER, 0 turnos) quanto quem foi desligado e ficou alocado (JONATHAN MENDES,
desligado 22/07/2026 e ainda com 16 turnos lançados em agosto).

**O ponto perde, e por um motivo medido:** 48% das batidas de 08/2026 não têm `posto_id`
(1.794 de 3.420). O ponto é a melhor evidência de PRESENÇA, mas hoje não sabe dizer ONDE em
metade dos casos — por isso entra como conferência, não como base.

Prime Arena é a exceção e é achado, não ruído: a escala dá 114 dias de VT e o dono escreveu 88.
114 − 88 = 26 = exatamente o mês inteiro de UM dos dois 44h do posto (GRACIENE ou MALAQUIAS), e
o Prime Arena tem uma SEGUNDA nota no cronograma — «manutenção de piscina e jardinagem»,
R$ 3.879,60, emitida pela ELETRÔNICA. A hipótese que a aritmética sustenta é que um dos dois ASG
é faturado por aquela nota e não entra na dedução da nota da Patrimonial. Decisão do dono.

O efetivo — medido em 24/09/2026, produção
------------------------------------------
Três tabelas dizem quem está em qual cliente e **as três discordam**, e nenhuma bate com o
cronograma do dono (que ele confirmou ser o certo: *«o erro é de alocação no sistema, no físico
está tudo certo»*). Em 08/2026:

    cliente              allocations  employee_alocacoes  escala(shifts)  ponto  required  cronograma
    Ideal Flores              14              13               11           13      12         12
    Laranjeiras Village       10               9                9            9       9          8
    Prime Arena                4               7                6            5       6          8

Por isso a régua aqui é o CONJUNTO DE NOMES das três fontes, não a contagem: quando elas
divergem o contrato devolve `sabe=False` e a lista nome a nome, para o dono resolver.

A atribuição pessoa → cliente é pela ESCALA do mês (dias de turno por cliente), rateada quando a
pessoa serviu mais de um cliente — a escala é a única fonte que sabe ONDE a pessoa esteve em cada
dia. `allocations` põe RILEM FERREIRA no Ideal Flores e a escala mostra os 16 plantões dele no
Prime Arena. Sem escala no mês, cai para `employee_alocacoes` e depois `allocations`, e a fonte
usada volta em `fonte_atribuicao`.

Como roda
---------
    from modules.people_management.folha.services import va_vt_contrato as vv
    await vv.apurar(db, 2026, 8)                 # todos os clientes
    await vv.apurar(db, 2026, 8, cnpj="47405340000166")
    vv.texto_discriminacao(...)                  # a frase que vai na nota
"""

from __future__ import annotations

import calendar
import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: alíquota do Art. 31 da Lei 9.711/98 — cessão de mão de obra
INSS_ALIQUOTA = Decimal("0.11")

#: rubricas que são DESCONTO DO EMPREGADO e nunca podem virar custo de benefício (ver docstring)
RUBRICAS_PROIBIDAS = ("1010", "1011")

DDL = """
CREATE TABLE IF NOT EXISTS va_vt_contrato_decisao (
  id bigserial PRIMARY KEY,
  client_id uuid NOT NULL,
  competencia date NOT NULL,
  pessoas integer,
  va numeric(12,2),
  vt numeric(12,2),
  justificativa text NOT NULL,
  decidido_por varchar(120),
  decidido_em timestamptz NOT NULL DEFAULT now(),
  UNIQUE (client_id, competencia)
)
"""

MESES_PT = [
    "",
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


async def _ensure(db) -> None:
    await db.execute(text(DDL))


def _c(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def reais(v) -> str:
    """R$ 1.234,56 — formato brasileiro."""
    s = f"{_c(v):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    return f"R$ {s}"


def inss_de(base) -> Decimal:
    return _c(Decimal(str(base)) * INSS_ALIQUOTA)


# ───────────────────────── efetivo: quem está em qual cliente ─────────────────────────

_SQL_ALLOC = """
SELECT c.id::text, c.name, e.id::text, e.nome
  FROM allocations a JOIN posts p ON p.id = a.post_id JOIN clients c ON c.id = p.client_id
  JOIN employees e ON e.id = a.employee_id
 WHERE a.status = 'active' AND coalesce(a.is_active, true)
   AND a.start_date <= :fim AND (a.end_date IS NULL OR a.end_date >= :ini)
"""

_SQL_EMPALOC = """
SELECT c.id::text, c.name, e.id::text, e.nome
  FROM employee_alocacoes a JOIN condominios co ON co.id = a.condominio_id
  JOIN clients c ON c.id = co.client_id JOIN employees e ON e.id = a.employee_id
 WHERE a.data_inicio <= :fim AND (a.data_fim IS NULL OR a.data_fim >= :ini)
"""

#: a escala também devolve QUANTOS dias em cada cliente — é o que rateia quem serviu dois
_SQL_ESCALA = """
SELECT c.id::text, c.name, e.id::text, e.nome, count(DISTINCT s.shift_date)::int
  FROM shifts s JOIN posts p ON p.id = s.post_id JOIN clients c ON c.id = p.client_id
  JOIN employees e ON e.id = s.employee_id
 WHERE s.shift_date BETWEEN :ini AND :fim
   AND lower(coalesce(s.status, '')) <> 'cancelled' AND NOT coalesce(s.is_off_day, false)
 GROUP BY 1, 2, 3, 4
"""

_SQL_PONTO = """
SELECT c.id::text, c.name, e.id::text, e.nome, count(DISTINCT pu.punch_timestamp::date)::int
  FROM gp_clock_punches pu JOIN posts p ON p.id::text = pu.posto_id JOIN clients c ON c.id = p.client_id
  JOIN employees e ON e.id = pu.employee_id
 WHERE pu.punch_timestamp >= :ini AND pu.punch_timestamp < (CAST(:fim AS date) + 1)
 GROUP BY 1, 2, 3, 4
"""


async def _fontes(db, ini: date, fim: date) -> dict[str, dict]:
    """{client_id: {nome, fontes:{fonte: {employee_id: (nome, dias|None)}}}} nas quatro fontes."""
    out: dict[str, dict] = {}

    def _put(cid, cnome, fonte, eid, enome, dias=None):
        c = out.setdefault(cid, {"client_id": cid, "cliente": cnome, "fontes": {}})
        c["fontes"].setdefault(fonte, {})[eid] = (enome, dias)

    p = {"ini": ini, "fim": fim}
    for cid, cnome, eid, enome in (await db.execute(text(_SQL_ALLOC), p)).fetchall():
        _put(cid, cnome, "allocations", eid, enome)
    for cid, cnome, eid, enome in (await db.execute(text(_SQL_EMPALOC), p)).fetchall():
        _put(cid, cnome, "employee_alocacoes", eid, enome)
    for cid, cnome, eid, enome, d in (await db.execute(text(_SQL_ESCALA), p)).fetchall():
        _put(cid, cnome, "escala", eid, enome, d)
    for cid, cnome, eid, enome, d in (await db.execute(text(_SQL_PONTO), p)).fetchall():
        _put(cid, cnome, "ponto", eid, enome, d)
    return out


async def efetivo(db, ano: int, mes: int) -> list[dict]:
    """Efetivo por cliente na competência, nas quatro fontes, com a divergência nome a nome.

    `conciliado` é o efetivo quando `allocations`, `employee_alocacoes` e `escala` concordam no
    CONJUNTO de pessoas; senão é None e `divergencias` traz cada nome e quem o vê. `ponto` entra
    como evidência (quem bateu no posto esteve lá), mas não decide sozinho: 48% das batidas de
    08/2026 não têm `posto_id` — medido em 24/09.
    """
    ini, fim = date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])
    fontes = await _fontes(db, ini, fim)
    req = {
        r[0]: (r[1] or 0)
        for r in (
            await db.execute(
                text(
                    "SELECT client_id::text, sum(required_headcount)::int FROM posts "
                    "WHERE client_id IS NOT NULL AND coalesce(is_active,true) GROUP BY 1"
                )
            )
        ).fetchall()
    }
    saida = (
        await db.execute(
            text(
                "SELECT id::text, nome, status, coalesce(data_desligamento, data_demissao), data_admissao "
                "FROM employees"
            )
        )
    ).fetchall()
    emp = {r[0]: {"nome": r[1], "status": r[2], "demissao": r[3], "admissao": r[4]} for r in saida}

    linhas = []
    for cid, c in sorted(fontes.items(), key=lambda kv: kv[1]["cliente"]):
        f = c["fontes"]
        conj = {k: set(v) for k, v in f.items()}
        decisivas = ("allocations", "employee_alocacoes", "escala")
        todos = set().union(*(conj.get(k, set()) for k in decisivas)) | conj.get("ponto", set())
        acordo = all(conj.get(k, set()) == conj.get(decisivas[0], set()) for k in decisivas)
        divs = []
        for eid in sorted(todos, key=lambda x: emp.get(x, {}).get("nome") or ""):
            onde = [k for k in ("allocations", "employee_alocacoes", "escala", "ponto") if eid in conj.get(k, set())]
            if set(onde) & set(decisivas) == set(decisivas):
                continue
            e = emp.get(eid, {})
            causa = "—"
            if e.get("demissao") and e["demissao"] <= fim and "allocations" in onde:
                causa = f"desligado em {e['demissao'].strftime('%d/%m/%Y')} e ainda alocado — encerrar a alocação"
            elif "escala" in onde and "allocations" not in onde:
                causa = "trabalhou aqui pela escala mas não tem alocação neste cliente — transferência sem encerrar a anterior?"
            elif "allocations" in onde and "escala" not in onde:
                causa = "alocado aqui mas sem nenhum turno no mês — alocação parada?"
            elif "employee_alocacoes" in onde and "allocations" not in onde:
                causa = "só na alocação antiga (employee_alocacoes) — alocação nova não criada"
            divs.append(
                {
                    "employee_id": eid,
                    "nome": e.get("nome") or eid,
                    "status": e.get("status"),
                    "demissao": e.get("demissao"),
                    "fontes": onde,
                    "causa": causa,
                }
            )
        linhas.append(
            {
                "client_id": cid,
                "cliente": c["cliente"],
                "allocations": len(conj.get("allocations", ())),
                "employee_alocacoes": len(conj.get("employee_alocacoes", ())),
                "escala": len(conj.get("escala", ())),
                "ponto": len(conj.get("ponto", ())),
                "required_headcount": req.get(cid),
                "conciliado": len(conj.get(decisivas[0], ())) if acordo else None,
                "divergencias": divs,
            }
        )
    return linhas


# ───────────────────────── apuração de VA e VT por contrato ─────────────────────────


_SQL_DIAS_ESCALA = """
SELECT c.id::text AS client_id, c.name AS cliente, e.id::text AS employee_id, e.nome,
       coalesce(e.escala_padrao, '') AS escala, e.cargo,
       count(DISTINCT s.shift_date)::int AS dias_vt,
       count(DISTINCT s.shift_date) FILTER (
         WHERE coalesce(e.escala_padrao,'') <> '44h' OR extract(dow from s.shift_date) BETWEEN 1 AND 5
       )::int AS dias_vr
  FROM shifts s JOIN posts p ON p.id = s.post_id JOIN clients c ON c.id = p.client_id
  JOIN employees e ON e.id = s.employee_id
 WHERE s.shift_date BETWEEN :ini AND :fim
   AND lower(coalesce(s.status, '')) <> 'cancelled' AND NOT coalesce(s.is_off_day, false)
   AND (e.data_admissao IS NULL OR e.data_admissao <= :fim)
   AND (coalesce(e.data_desligamento, e.data_demissao) IS NULL
        OR coalesce(e.data_desligamento, e.data_demissao) >= :ini)
 GROUP BY 1, 2, 3, 4, 5, 6
"""

#: mesma pergunta, feita ao PONTO — conferência, não base (48% das batidas sem posto_id)
_SQL_DIAS_PONTO = """
SELECT c.id::text, e.id::text,
       count(DISTINCT pu.punch_timestamp::date)::int,
       count(DISTINCT pu.punch_timestamp::date) FILTER (
         WHERE coalesce(e.escala_padrao,'') <> '44h' OR extract(dow from pu.punch_timestamp) BETWEEN 1 AND 5
       )::int
  FROM gp_clock_punches pu JOIN posts p ON p.id::text = pu.posto_id JOIN clients c ON c.id = p.client_id
  JOIN employees e ON e.id = pu.employee_id
 WHERE pu.punch_timestamp >= :ini AND pu.punch_timestamp < (CAST(:fim AS date) + 1)
 GROUP BY 1, 2
"""


async def unitarios(db) -> dict:
    """R$/dia de VR e de VT, do banco. Sem parâmetro não há número — não há constante de reserva.

    O VT tem uma OPERADORA por pessoa (`employees.vt_modalidade`) e 40 dos 50 ativos estão sem
    ela (medido 24/09). Isso NÃO impede saber o valor: as duas operadoras configuradas custam o
    mesmo R$ 10,00/dia, e a operadora decide qual cartão, não quanto. Enquanto todas as linhas
    ativas de VT concordarem no valor, o unitário é conhecido para todo mundo; no dia em que
    discordarem, quem estiver sem modalidade vira «não sei» — e isso está afirmado no oráculo.
    """
    rows = (
        await db.execute(
            text(
                "SELECT lower(tipo_beneficio), upper(coalesce(operadora,'')), valor_empresa "
                "  FROM cct_benefit_configs "
                " WHERE coalesce(ativo,true) AND (vigencia_inicio IS NULL OR vigencia_inicio <= current_date) "
                "   AND (vigencia_fim IS NULL OR vigencia_fim >= current_date)"
            )
        )
    ).fetchall()
    vr = {Decimal(str(v)) for tipo, _op, v in rows if tipo == "vale_refeicao" and v is not None}
    vt = {Decimal(str(v)) for tipo, _op, v in rows if tipo == "vale_transporte" and v is not None}
    if not vr:
        v = (
            await db.execute(
                text(
                    "SELECT valor_minimo FROM cct_beneficios WHERE tipo_beneficio='vale_refeicao' AND is_active "
                    "AND valor_minimo IS NOT NULL ORDER BY updated_at DESC LIMIT 1"
                )
            )
        ).scalar()
        if v is not None:
            vr = {Decimal(str(v))}
    return {
        "VR": next(iter(vr)) if len(vr) == 1 else None,
        "VT": next(iter(vt)) if len(vt) == 1 else None,
        "VR_fonte": "cct_benefit_configs (vale_refeicao)" if len(vr) == 1 else f"{len(vr)} valores distintos",
        "VT_fonte": "cct_benefit_configs (vale_transporte, mesmo valor nas operadoras)"
        if len(vt) == 1
        else f"{len(vt)} valores distintos",
    }


async def apurar(db, ano: int, mes: int, client_id: str | None = None, cnpj: str | None = None) -> list[dict]:
    """VA e VT do mês por cliente — pessoa × dias de escala naquele posto × unitário da CCT.

    O número de pessoas é CONSEQUÊNCIA da soma, não premissa dela (ver docstring do módulo).
    Devolve `sabe` (bool), os valores quando sabe, a procedência completa (cada pessoa, seus dias,
    o unitário e a fonte) e `motivos` quando não sabe. Decisão do dono gravada em
    `va_vt_contrato_decisao` vence a apuração.
    """
    await _ensure(db)
    ini, fim = date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])
    un = await unitarios(db)
    ef = {e["client_id"]: e for e in await efetivo(db, ano, mes)}

    alvo = None
    if cnpj:
        alvo = (
            await db.execute(
                text("SELECT id::text FROM clients WHERE regexp_replace(document_number,'\\D','','g') = :d"),
                {"d": "".join(ch for ch in cnpj if ch.isdigit())},
            )
        ).scalar()
        if alvo is None:
            return []
    elif client_id:
        alvo = client_id

    vinc_ok, nomes = set(), {}
    for eid, nome, adm, dem in (
        await db.execute(
            text("SELECT id::text, nome, data_admissao, coalesce(data_desligamento, data_demissao) FROM employees")
        )
    ).fetchall():
        nomes[eid] = nome
        if (adm is None or adm <= fim) and (dem is None or dem >= ini):
            vinc_ok.add(eid)

    dias = (await db.execute(text(_SQL_DIAS_ESCALA), {"ini": ini, "fim": fim})).fetchall()
    ponto: dict[tuple[str, str], tuple[int, int]] = {
        (r[0], r[1]): (r[2], r[3])
        for r in (await db.execute(text(_SQL_DIAS_PONTO), {"ini": ini, "fim": fim})).fetchall()
    }
    # o motor da frente 03 (previsão + saldo do mês anterior) entra como CONFERÊNCIA
    conf = {
        (r[0], r[1]): r[2]
        for r in (
            await db.execute(
                text(
                    "SELECT employee_id::text, beneficio, total FROM folha_beneficio_conferencia WHERE competencia = :c"
                ),
                {"c": ini},
            )
        ).fetchall()
    }

    por_cliente: dict[str, dict] = {}
    for cid, cnome, eid, nome, escala, cargo, d_vt, d_vr in dias:
        c = por_cliente.setdefault(cid, {"cliente": cnome, "pessoas": []})
        pvt, pvr = ponto.get((cid, eid), (None, None))
        c["pessoas"].append(
            {
                "employee_id": eid,
                "nome": nome,
                "escala": escala or "—",
                "cargo": cargo,
                "dias_vt": d_vt,
                "dias_vr": d_vr,
                "dias_vt_ponto": pvt,
                "dias_vr_ponto": pvr,
                "va": float(_c(Decimal(d_vr) * un["VR"])) if un["VR"] is not None else None,
                "vt": float(_c(Decimal(d_vt) * un["VT"])) if un["VT"] is not None else None,
                "va_conferencia": float(conf[(eid, "VR")]) if conf.get((eid, "VR")) is not None else None,
                "vt_conferencia": float(conf[(eid, "VT")]) if conf.get((eid, "VT")) is not None else None,
            }
        )

    decisoes = {
        r[0]: {"pessoas": r[1], "va": r[2], "vt": r[3], "justificativa": r[4], "por": r[5], "em": r[6]}
        for r in (
            await db.execute(
                text(
                    "SELECT client_id::text, pessoas, va, vt, justificativa, decidido_por, decidido_em "
                    "FROM va_vt_contrato_decisao WHERE competencia = :c"
                ),
                {"c": ini},
            )
        ).fetchall()
    }

    saida = []
    for cid in sorted(
        set(por_cliente) | set(ef), key=lambda k: (por_cliente.get(k) or ef.get(k, {})).get("cliente") or ""
    ):
        if alvo and cid != alvo:
            continue
        c = por_cliente.get(cid) or {"cliente": (ef.get(cid) or {}).get("cliente") or cid, "pessoas": []}
        gente = sorted(c["pessoas"], key=lambda x: x["nome"])
        motivos: list[str] = []
        if not gente:
            motivos.append(
                f"nenhum turno lançado na escala em {mes:02d}/{ano} — sem escala não há dia, e sem dia não há benefício"
            )
        if un["VR"] is None:
            motivos.append(f"vale-refeição sem unitário único em cct_benefit_configs ({un['VR_fonte']})")
        if un["VT"] is None:
            motivos.append(f"vale-transporte sem unitário único em cct_benefit_configs ({un['VT_fonte']})")
        va = _c(sum(Decimal(str(g["va"] or 0)) for g in gente)) if un["VR"] is not None else None
        vt = _c(sum(Decimal(str(g["vt"] or 0)) for g in gente)) if un["VT"] is not None else None

        e = ef.get(cid) or {"divergencias": [], "conciliado": None}
        # alocado no cliente e SEM nenhum turno no mês: não entra no valor, mas tem de aparecer
        na_escala = {g["employee_id"] for g in gente}
        sem_escala = [
            d for d in e.get("divergencias", []) if d["employee_id"] not in na_escala and "escala" not in d["fontes"]
        ]

        # A CONTAGEM é outra pergunta que o VALOR, e só uma delas a escala responde sozinha.
        # O dono (24/09): «tem muita rotatividade (…) sempre fica defasado». Medido: no Ideal
        # Flores a escala tem 11, `allocations` 14, `employee_alocacoes` 12 e o efetivo real que
        # ele confirmou é 13 — nenhuma fonte acerta. O VALOR pela escala erra 1,4% no VT; a
        # CONTAGEM erra em 2 pessoas. Então: o valor sai apurado, a contagem sai `None` quando as
        # fontes discordam — e quem assina a nota digita o número. «QUANTIDADE DE FUNCIONÁRIOS NO
        # CONTRATO» é declaração legal na nota, não estatística.
        # PRESENTES = quem esteve fisicamente no posto no mês: escala ∪ ponto, dentro do vínculo.
        # Medido em 08/2026: essa união dá 13 no Ideal Flores — exatamente o efetivo que o dono
        # confirmou («ideal flores são 13 pessoas alocadas»), que NENHUMA das duas tabelas de
        # alocação acerta (14 e 12) e que a escala sozinha também erra (11: NAILSON e RILEM
        # bateram ponto lá e não têm turno lançado).
        presentes = sorted(
            {g["employee_id"] for g in gente} | {eid for (cc, eid) in ponto if cc == cid and eid in vinc_ok},
            key=lambda x: nomes.get(x, x),
        )
        # a contagem só é confiável quando os presentes batem com ALGUMA fonte de alocação —
        # senão é o caso do Prime Arena (presentes 6 · alocação 4 · alocação antiga 7) e quem
        # assina digita o número.
        pessoas_conf = len(presentes) in (e.get("allocations"), e.get("employee_alocacoes"))
        linha = {
            "client_id": cid,
            "cliente": c["cliente"],
            "competencia": f"{mes:02d}/{ano}",
            "pessoas": len(presentes) if pessoas_conf else None,
            "pessoas_escala": len(gente),
            "pessoas_presentes": len(presentes),
            "presentes": [nomes.get(x, x) for x in presentes],
            "pessoas_confiavel": pessoas_conf,
            "pessoas_motivo": (
                None
                if pessoas_conf
                else (
                    f"presentes no posto (escala ∪ ponto) {len(presentes)} · alocação {e.get('allocations')} · "
                    f"alocação antiga {e.get('employee_alocacoes')} — nenhuma bate; confirme a quantidade"
                )
            ),
            "dias_va": sum(g["dias_vr"] for g in gente),
            "dias_vt": sum(g["dias_vt"] for g in gente),
            "unitario_va": float(un["VR"]) if un["VR"] is not None else None,
            "unitario_vt": float(un["VT"]) if un["VT"] is not None else None,
            "va": float(va) if (va is not None and not motivos) else None,
            "vt": float(vt) if (vt is not None and not motivos) else None,
            "va_apurado": float(va) if va is not None else None,
            "vt_apurado": float(vt) if vt is not None else None,
            "va_conferencia": float(_c(sum(Decimal(str(g["va_conferencia"] or 0)) for g in gente))),
            "va_ponto": (
                float(_c(sum(Decimal(str(g["dias_vr_ponto"] or 0)) for g in gente) * un["VR"]))
                if un["VR"] is not None
                else None
            ),
            "vt_ponto": (
                float(_c(sum(Decimal(str(g["dias_vt_ponto"] or 0)) for g in gente) * un["VT"]))
                if un["VT"] is not None
                else None
            ),
            "sabe": not motivos,
            "motivos": motivos,
            "fonte": (
                f"escala do mês × {reais(un['VR'])}/dia (VA) e {reais(un['VT'])}/dia (VT) — "
                f"{un['VR_fonte']} · {un['VT_fonte']}"
                if not motivos
                else "—"
            ),
            "detalhe": gente,
            "alocado_sem_escala": [{"nome": d["nome"], "causa": d["causa"]} for d in sem_escala],
            "efetivo": e,
        }
        dec = decisoes.get(cid)
        if dec:
            linha.update(
                {
                    "va": float(_c(dec["va"])) if dec["va"] is not None else linha["va"],
                    "vt": float(_c(dec["vt"])) if dec["vt"] is not None else linha["vt"],
                    "pessoas": dec["pessoas"] if dec["pessoas"] is not None else linha["pessoas"],
                    "pessoas_confiavel": dec["pessoas"] is not None or linha["pessoas_confiavel"],
                    "sabe": dec["va"] is not None and dec["vt"] is not None,
                    "fonte": f"decisão do dono em {dec['em']:%d/%m/%Y} — {dec['justificativa']}",
                    "decisao": dec,
                }
            )
        saida.append(linha)
    return saida


async def para_nota(db, ano: int, mes: int, cnpj_tomador: str) -> dict:
    """O que a emissão (AA4) pergunta: «quanto foi de VA e VT no contrato X na competência Y».

    Devolve DUAS certezas separadas, porque são perguntas diferentes:
      `sabe`              — o VALOR de VA e VT (a escala responde; erra 0,5%–2,9% contra a nota real);
      `pessoas_confiavel` — a CONTAGEM de funcionários do contrato (a escala NÃO responde sozinha:
                            no Ideal Flores dá 11, as duas tabelas de alocação dão 14 e 12, e o
                            efetivo real que o dono confirmou é 13).
    `pessoas` volta None quando não é confiável — a emissão pede ao humano, que é quem assina.
    """
    linhas = await apurar(db, ano, mes, cnpj=cnpj_tomador)
    if not linhas:
        return {
            "sabe": False,
            "va": None,
            "vt": None,
            "pessoas": None,
            "motivos": ["tomador sem contrato/posto no sistema"],
        }
    ln = linhas[0]
    return {
        "sabe": ln["sabe"],
        "va": ln["va"],
        "vt": ln["vt"],
        "pessoas": ln["pessoas"],
        "pessoas_escala": ln["pessoas_escala"],
        "pessoas_presentes": ln["pessoas_presentes"],
        "pessoas_confiavel": ln["pessoas_confiavel"],
        "pessoas_motivo": ln["pessoas_motivo"],
        "dias_va": ln["dias_va"],
        "dias_vt": ln["dias_vt"],
        "unitario_va": ln["unitario_va"],
        "unitario_vt": ln["unitario_vt"],
        "competencia": ln["competencia"],
        "fonte": ln["fonte"],
        "motivos": ln["motivos"],
        "cliente": ln["cliente"],
    }


def texto_discriminacao(bruto, va, vt, pessoas: int, competencia: str, aliquota=INSS_ALIQUOTA) -> str:
    """A frase que vai na nota, no formato que o dono já usa na planilha.

    Sem isso escrito na nota a dedução é GLOSÁVEL — é a condição legal, não enfeite.
    `competencia` no formato MM/AAAA (a do BENEFÍCIO: uma nota de 09/2026 discrimina o VA de 08/2026).
    """
    bruto, va, vt = _c(bruto), _c(va), _c(vt)
    deducao = _c(va + vt)
    base = _c(bruto - deducao)
    inss = _c(base * Decimal(str(aliquota)))
    pct = (Decimal(str(aliquota)) * 100).normalize()
    return (
        f"DEDUÇÕES DA BASE DE CÁLCULO: {reais(deducao)} | "
        f"QUANTIDADE DE FUNCIONÁRIOS NO CONTRATO: {pessoas:02d} | "
        f"Vale Alimentação {competencia}: {reais(va)} | "
        f"Vale Transporte {competencia}: {reais(vt)} | "
        f"BASE DE CÁLCULO PARA RETENÇÃO DE INSS: {reais(base)} | "
        f"Aplicada retenção do INSS ({pct:f}%) conforme o Art. 31 da Lei n. 9.711/98. "
        f"VALOR DA RETENÇÃO DE INSS ({pct:f}%): {reais(inss)}"
    )


async def registrar_decisao(db, client_id: str, ano: int, mes: int, payload: dict, quem: str) -> dict:
    """O dono sobrescreve VA/VT/pessoas do contrato, com justificativa. Ele é quem assina."""
    await _ensure(db)
    just = (payload.get("justificativa") or "").strip()
    if not just:
        raise ValueError("justificativa é obrigatória — número em base de imposto sem motivo registrado, não.")

    def _v(k):
        v = (payload.get(k) or "").strip() if isinstance(payload.get(k), str) else payload.get(k)
        if v in (None, ""):
            return None
        return _c(str(v).replace(".", "").replace(",", ".") if isinstance(v, str) else v)

    va, vt = _v("va"), _v("vt")
    pessoas = payload.get("pessoas")
    pessoas = int(pessoas) if str(pessoas or "").strip().isdigit() else None
    await db.execute(
        text(
            "INSERT INTO va_vt_contrato_decisao (client_id, competencia, pessoas, va, vt, justificativa, decidido_por) "
            "VALUES (CAST(:c AS uuid), CAST(:k AS date), :p, :va, :vt, :j, :q) "
            "ON CONFLICT (client_id, competencia) DO UPDATE SET pessoas = EXCLUDED.pessoas, va = EXCLUDED.va, "
            "  vt = EXCLUDED.vt, justificativa = EXCLUDED.justificativa, decidido_por = EXCLUDED.decidido_por, "
            "  decidido_em = now()"
        ),
        {"c": client_id, "k": date(ano, mes, 1), "p": pessoas, "va": va, "vt": vt, "j": just, "q": quem},
    )
    await db.commit()
    return {"va": float(va) if va is not None else None, "vt": float(vt) if vt is not None else None}
