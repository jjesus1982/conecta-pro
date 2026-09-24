"""Entrega de benefício em LOTE com período de apuração — DGX `/EntregasBeneficios` (U5, 24/09/2026).

O que o DGX tem e o motor da frente 03 não tinha: a entrega é uma ENTIDADE com identidade —
benefício + referência (MM/AAAA) + período previsto + apuração (manual ou pelo apontamento, com
janela própria) + as duas entregas anteriores contra as quais se faz o acerto. Sem ela não dava para
dizer «a entrega de VT de outubro foi apurada de 16/09 a 15/10, gerou R$ X e o pedido saiu dia Y».

Regra do acerto (a mesma do motor, trocando "portal do mês anterior" por "entregas anteriores"):
  planejado  = dias previstos na janela de PREVISÃO (escala + regra do tipo: remover férias/afastados)
  trabalhado = dias T/E na janela de APURAÇÃO (só no modo apontamento)      direito = trabalhado
  recebido_anterior = Σ quantidade que a pessoa levou nas entregas anteriores 1 e 2
  ajuste_ponto = direito − recebido_anterior        quantidade = max(0, planejado + ajuste_ponto)
  total = quantidade × unitário (R$/dia de cct_benefit_configs, via beneficio_ponto.parametros)
O acerto só é feito quando a janela de apuração tem o MESMO número de dias que a soma das previsões
das entregas anteriores (é o que se está conferindo); senão o item fica `janela_divergente` com a
previsão pura — como "sem anterior" no motor, é ESTADO, nunca zero inventado.

Apuração por apontamento é DEFINITIVA se a competência de todo mundo estava fechada
(`ponto.fechamento.competencia_fechada`) em todos os meses da janela; senão «apuração provisória».

PARALELO CEGO: grava só em `beneficio_entregas` / `beneficio_entrega_itens`; o título a pagar
(`gerar_conta`) nasce pelo PayableService igual à tela «Registrar conta» e NÃO é pago aqui.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from modules.people_management.folha.services import beneficio_ponto as bp

STATUS = ("rascunho", "apurada", "aprovada", "enviada", "paga")
MODOS = ("manual", "apontamento")

DDL = (
    """CREATE TABLE IF NOT EXISTS beneficio_entregas (
  id bigserial PRIMARY KEY,
  beneficio_tipo_id bigint NOT NULL,
  referencia varchar(7) NOT NULL,
  previsao_inicio date NOT NULL, previsao_fim date NOT NULL,
  apuracao_modo varchar(12) NOT NULL DEFAULT 'manual' CHECK (apuracao_modo IN ('manual','apontamento')),
  apuracao_inicio date, apuracao_fim date,
  entrega_anterior_id bigint, entrega_anterior2_id bigint,
  status varchar(10) NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho','apurada','aprovada','enviada','paga')),
  apuracao_definitiva boolean,
  total numeric(12,2), quantidade_pessoas integer,
  arquivo_operador_path text, payable_id uuid,
  observacao text,
  criado_por varchar(120), aprovado_por varchar(120), aprovado_em timestamptz, apurado_em timestamptz,
  created_at timestamptz DEFAULT now(), updated_at timestamptz DEFAULT now()
)""",
    """CREATE TABLE IF NOT EXISTS beneficio_entrega_itens (
  id bigserial PRIMARY KEY,
  entrega_id bigint NOT NULL REFERENCES beneficio_entregas(id) ON DELETE CASCADE,
  employee_id uuid NOT NULL,
  operadora varchar(20),
  planejado integer, trabalhado integer, recebido_anterior integer, direito integer, ajuste_ponto integer,
  quantidade integer, unitario numeric(12,2), total numeric(12,2),
  estado varchar(24) NOT NULL, observacao text,
  UNIQUE (entrega_id, employee_id)
)""",
    "CREATE INDEX IF NOT EXISTS ix_beneficio_entregas_tipo_ref ON beneficio_entregas (beneficio_tipo_id, referencia)",
)


class EntregaTravadaError(Exception):
    """A entrega está aprovada/enviada: reapurar ou editar item é recusado (409 na tela)."""


async def _ensure(db) -> None:
    for stmt in DDL:
        await db.execute(text(stmt))
    await db.commit()


def _d(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if "/" in s:  # DD/MM/AAAA
        dd, mm, yy = s.split("/")
        return date(int(yy), int(mm), int(dd))
    return date.fromisoformat(s[:10])


# ───────────────────────── criação ─────────────────────────


async def criar(db, payload: dict, quem: str) -> int:
    await _ensure(db)
    try:
        tipo_id = int(payload.get("beneficio_tipo_id") or 0)
    except ValueError:
        tipo_id = 0
    prim = (
        await db.execute(text("SELECT tipo_primitivo FROM beneficio_tipos WHERE id = :i AND ativo"), {"i": tipo_id})
    ).scalar()
    if prim not in bp.BENEFICIOS:
        raise ValueError("Benefício: escolha um tipo ATIVO de VT ou VR — o motor só apura esses dois.")
    ref = str(payload.get("referencia") or "").strip()
    if not (len(ref) == 7 and ref[2] == "/" and ref[:2].isdigit() and ref[3:].isdigit() and 1 <= int(ref[:2]) <= 12):
        raise ValueError("Referência no formato MM/AAAA (ex.: 10/2026).")
    pi, pf = _d(payload.get("previsao_inicio")), _d(payload.get("previsao_fim"))
    if not pi or not pf or pf < pi:
        raise ValueError("Período de previsão: início e fim obrigatórios, fim ≥ início.")
    modo = str(payload.get("apuracao_modo") or "manual").strip().lower()
    if modo not in MODOS:
        raise ValueError("Apuração: manual ou apontamento.")
    ai, af = _d(payload.get("apuracao_inicio")), _d(payload.get("apuracao_fim"))
    if modo == "apontamento":
        if not ai or not af or af < ai:
            raise ValueError("Apuração por apontamento exige janela (início e fim, fim ≥ início).")
        if af > date.today():
            raise ValueError("Apuração por apontamento não pode terminar no futuro — o ponto ainda não aconteceu.")
    ants: list[int | None] = []
    for k in ("entrega_anterior_id", "entrega_anterior2_id"):
        v = payload.get(k)
        if v in (None, "", "0"):
            ants.append(None)
            continue
        row = (
            await db.execute(text("SELECT beneficio_tipo_id FROM beneficio_entregas WHERE id = :i"), {"i": int(v)})
        ).first()
        if not row:
            raise ValueError(f"Entrega anterior #{v} não existe.")
        if row[0] != tipo_id:
            raise ValueError(f"Entrega anterior #{v} é de outro benefício.")
        ants.append(int(v))
    if ants[0] and ants[0] == ants[1]:
        raise ValueError("As duas entregas anteriores são a mesma.")
    rid = (
        await db.execute(
            text(
                "INSERT INTO beneficio_entregas (beneficio_tipo_id, referencia, previsao_inicio, previsao_fim, apuracao_modo, "
                " apuracao_inicio, apuracao_fim, entrega_anterior_id, entrega_anterior2_id, observacao, criado_por) "
                "VALUES (:t, :r, :pi, :pf, :m, :ai, :af, :a1, :a2, :o, :q) RETURNING id"
            ),
            {
                "t": tipo_id,
                "r": ref,
                "pi": pi,
                "pf": pf,
                "m": modo,
                "ai": ai if modo == "apontamento" else None,
                "af": af if modo == "apontamento" else None,
                "a1": ants[0],
                "a2": ants[1],
                "o": (str(payload.get("observacao") or "").strip() or None),
                "q": quem[:120],
            },
        )
    ).scalar()
    await db.commit()
    return int(rid)


# ───────────────────────── apuração ─────────────────────────

_KEYS = (
    "id",
    "tipo_id",
    "ben",
    "tipo_nome",
    "referencia",
    "previsao_inicio",
    "previsao_fim",
    "modo",
    "apuracao_inicio",
    "apuracao_fim",
    "anterior_id",
    "anterior2_id",
    "status",
    "total",
    "payable_id",
    "arquivo",
    "definitiva",
    "pessoas",
)


async def _entrega(db, entrega_id: int) -> dict:
    r = (
        await db.execute(
            text(
                "SELECT e.id, e.beneficio_tipo_id, t.tipo_primitivo, t.nome, e.referencia, e.previsao_inicio, e.previsao_fim, "
                " e.apuracao_modo, e.apuracao_inicio, e.apuracao_fim, e.entrega_anterior_id, e.entrega_anterior2_id, e.status, "
                " e.total, e.payable_id::text, e.arquivo_operador_path, e.apuracao_definitiva, e.quantidade_pessoas "
                "FROM beneficio_entregas e JOIN beneficio_tipos t ON t.id = e.beneficio_tipo_id WHERE e.id = :i"
            ),
            {"i": entrega_id},
        )
    ).first()
    if not r:
        raise ValueError(f"Entrega #{entrega_id} não existe.")
    return dict(zip(_KEYS, r, strict=True))


def _previsao(m: dict, ben: str, regra: dict) -> int:
    """Mesma conta do motor (beneficio_ponto.calcular_competencia._previsao): a regra do tipo diz o que devolver."""
    return (
        m["previsao"][ben]
        + (0 if regra.get("remover_ferias") else m["removidos"]["V"][ben])
        + (0 if regra.get("remover_afastados") else m["removidos"]["A"][ben])
    )


async def apurar(db, entrega_id: int) -> dict:
    """Roda o motor da frente 03 nas janelas da entrega e (re)grava os itens. Idempotente: apaga e
    regrava os itens desta entrega — nunca duplica. Aprovada/enviada → EntregaTravadaError."""
    await _ensure(db)
    e = await _entrega(db, entrega_id)
    if e["status"] not in ("rascunho", "apurada"):
        raise EntregaTravadaError(f"Entrega #{entrega_id} está {e['status']} — os itens estão travados; não reapuro.")
    ben = e["ben"]
    par = await bp.parametros(db)
    regra = par.regras.get(ben)
    from modules.people_management.ponto.fechamento import competencia_fechada

    # entregas anteriores: o que cada pessoa levou + quantos dias de previsão elas somam
    ants = [a for a in (e["anterior_id"], e["anterior2_id"]) if a]
    recebido: dict[str, int] = {}
    dias_ant = 0
    for a in ants:
        ea = await _entrega(db, a)
        dias_ant += (ea["previsao_fim"] - ea["previsao_inicio"]).days + 1
        for eid, q in (
            await db.execute(
                text("SELECT employee_id::text, quantidade FROM beneficio_entrega_itens WHERE entrega_id = :a"),
                {"a": a},
            )
        ).fetchall():
            if q is not None:
                recebido[eid] = recebido.get(eid, 0) + int(q)
    apont = e["modo"] == "apontamento"
    dias_ap = (e["apuracao_fim"] - e["apuracao_inicio"]).days + 1 if apont else 0
    janela_ok = bool(ants) and apont and dias_ap == dias_ant

    pi, pf = e["previsao_inicio"], e["previsao_fim"]
    emps = (
        await db.execute(
            text(
                "SELECT e.id::text, e.nome, e.escala_padrao, e.data_admissao, coalesce(e.data_desligamento, e.data_demissao), "
                "upper(coalesce(e.vt_modalidade,'')) FROM employees e "
                "WHERE coalesce(e.is_homologacao,false) = false AND lower(coalesce(e.tipo_contrato,'')) <> 'pj' "
                "AND (e.data_admissao IS NULL OR e.data_admissao <= CAST(:f AS date)) "
                "AND (e.status = 'ativo' OR coalesce(e.data_desligamento, e.data_demissao) >= CAST(:i AS date)) ORDER BY e.nome"
            ),
            {"i": pi, "f": pf},
        )
    ).fetchall()
    meses_ap = bp._meses(e["apuracao_inicio"], e["apuracao_fim"]) if apont else []
    await db.execute(text("DELETE FROM beneficio_entrega_itens WHERE entrega_id = :i"), {"i": entrega_id})
    total, pessoas, estados, abertos = Decimal(0), 0, {}, 0
    for eid, _nome, escala, adm, dem, modalidade in emps:
        emp = {"escala_padrao": escala, "data_admissao": adm, "data_demissao": dem}
        prev = await bp.mapa_frequencia(db, eid, pi.year, pi.month, par.horas_minimas, emp, periodo=(pi, pf))
        operadora = "SOLIDES" if ben == "VR" else (modalidade or "")
        unit = par.unitario(ben, operadora) if operadora else None
        it = {
            "e": entrega_id,
            "emp": eid,
            "op": operadora or None,
            "plan": None,
            "trab": None,
            "rec": recebido.get(eid),
            "dir": None,
            "aj": None,
            "qtd": None,
            "unit": unit,
            "total": None,
            "obs": None,
        }
        if regra is None:
            estado = "sem_regra"
        elif ben == "VT" and not operadora:
            estado = "sem_modalidade"
        elif unit is None:
            estado = "sem_parametro"
        elif prev["fonte_escala"] == "sem_escala":
            estado = "sem_escala"
        else:
            it["plan"] = _previsao(prev, ben, regra)
            qtd = it["plan"]
            if not apont:
                estado = "manual"
            else:
                ap = await bp.mapa_frequencia(
                    db,
                    eid,
                    pi.year,
                    pi.month,
                    par.horas_minimas,
                    emp,
                    periodo=(e["apuracao_inicio"], e["apuracao_fim"]),
                )
                it["trab"] = it["dir"] = ap["trabalhado"][ben]
                if regra.get("limite_faltas") is not None and ap["contagem"]["F"] > regra["limite_faltas"]:
                    estado, qtd = "cortado_faltas", 0
                elif not ants or eid not in recebido:
                    estado = "sem_anterior"
                elif not janela_ok:
                    estado = "janela_divergente"
                    it["obs"] = (
                        f"janela de apuração tem {dias_ap} dias; previsões das entregas anteriores somam {dias_ant}"
                    )
                elif not ap["tem_ponto"]:
                    estado = "anterior_sem_ponto"
                else:
                    estado = "ok"
                    it["aj"] = it["dir"] - recebido[eid]
                    qtd = max(0, it["plan"] + it["aj"])
                abertos_emp = [
                    f"{m:02d}/{y}" for y, m in meses_ap if await competencia_fechada(db, eid, date(y, m, 1)) is None
                ]
                if abertos_emp:
                    abertos += 1
                    it["obs"] = (
                        ((it["obs"] + " · ") if it["obs"] else "")
                        + "apuração provisória — mês aberto: "
                        + ", ".join(abertos_emp)
                    )
            it["qtd"] = qtd
            it["total"] = Decimal(qtd) * unit
            total += it["total"]
            pessoas += 1
        it["estado"] = estado
        estados[estado] = estados.get(estado, 0) + 1
        await db.execute(
            text(
                "INSERT INTO beneficio_entrega_itens (entrega_id, employee_id, operadora, planejado, trabalhado, recebido_anterior, "
                " direito, ajuste_ponto, quantidade, unitario, total, estado, observacao) "
                "VALUES (:e, CAST(:emp AS uuid), :op, :plan, :trab, :rec, :dir, :aj, :qtd, :unit, :total, :estado, :obs)"
            ),
            it,
        )
    definitiva = (abertos == 0) if apont else None
    await db.execute(
        text(
            "UPDATE beneficio_entregas SET status = 'apurada', total = :t, quantidade_pessoas = :p, apuracao_definitiva = :d, "
            "apurado_em = now(), updated_at = now() WHERE id = :i"
        ),
        {"t": total, "p": pessoas, "d": definitiva, "i": entrega_id},
    )
    await db.commit()
    return {
        "entrega_id": entrega_id,
        "beneficio": ben,
        "referencia": e["referencia"],
        "pessoas": pessoas,
        "linhas": len(emps),
        "total": total,
        "estados": estados,
        "apuracao_definitiva": definitiva,
        "acerto_feito": janela_ok,
    }


async def editar_item(db, item_id: int, quantidade, observacao: str | None = None) -> dict:
    """Apuração manual de verdade: o DP corrige a quantidade de UMA pessoa. Só em rascunho/apurada."""
    r = (
        await db.execute(
            text(
                "SELECT i.entrega_id, e.status, i.unitario FROM beneficio_entrega_itens i "
                "JOIN beneficio_entregas e ON e.id = i.entrega_id WHERE i.id = :i"
            ),
            {"i": item_id},
        )
    ).first()
    if not r:
        raise ValueError(f"Item #{item_id} não existe.")
    if r[1] not in ("rascunho", "apurada"):
        raise EntregaTravadaError(f"Entrega #{r[0]} está {r[1]} — item travado.")
    if r[2] is None:
        raise ValueError("Item sem unitário (sem parâmetro/modalidade) — não há o que quantificar.")
    try:
        q = int(str(quantidade).strip())
        assert q >= 0
    except (ValueError, AssertionError):
        raise ValueError("Quantidade: inteiro ≥ 0.")
    await db.execute(
        text(
            "UPDATE beneficio_entrega_itens SET quantidade = :q, total = :q * unitario, "
            "observacao = coalesce(nullif(:o,''), observacao) WHERE id = :i"
        ),
        {"q": q, "o": (observacao or "").strip(), "i": item_id},
    )
    await db.execute(
        text(
            "UPDATE beneficio_entregas e SET total = s.t, quantidade_pessoas = s.n, updated_at = now() FROM ("
            " SELECT coalesce(sum(total),0) t, count(total) n FROM beneficio_entrega_itens WHERE entrega_id = :i) s WHERE e.id = :i"
        ),
        {"i": r[0]},
    )
    await db.commit()
    return {"item_id": item_id, "entrega_id": r[0], "quantidade": q}


# ───────────────────────── aprovação · arquivo · conta ─────────────────────────


async def aprovar(db, entrega_id: int, quem: str) -> dict:
    e = await _entrega(db, entrega_id)
    if e["status"] != "apurada":
        raise EntregaTravadaError(f"Entrega #{entrega_id} está {e['status']} — só se aprova entrega apurada.")
    if not e["total"] or Decimal(e["total"]) <= 0:
        raise ValueError("Entrega sem valor — nada a aprovar.")
    await db.execute(
        text(
            "UPDATE beneficio_entregas SET status = 'aprovada', aprovado_por = :q, aprovado_em = now(), updated_at = now() WHERE id = :i"
        ),
        {"q": quem[:120], "i": entrega_id},
    )
    await db.commit()
    return {"entrega_id": entrega_id, "status": "aprovada", "total": e["total"]}


def _dir_arquivos() -> Path:
    return Path(os.getenv("UPLOADS_DIR", "/app/uploads")) / "beneficio_entregas"


async def gerar_arquivo(db, entrega_id: int, origem: str, quem: str) -> tuple[str, str, list[str]]:
    """Arquivo do operador (mesmo gerador da frente 03) a partir dos ITENS da entrega aprovada.
    Grava em UPLOADS_DIR/beneficio_entregas/ e guarda o caminho; a entrega vira `enviada`."""
    from modules.people_management.folha.services.beneficios_importer import LinhaBeneficio

    e = await _entrega(db, entrega_id)
    if e["status"] not in ("aprovada", "enviada", "paga"):
        raise EntregaTravadaError(f"Entrega #{entrega_id} está {e['status']} — aprove antes de gerar o arquivo.")
    origem = origem.lower()
    if origem not in ("solides", "sinetram"):
        raise ValueError("Operadora: solides ou sinetram.")
    if e["ben"] == "VR" and origem != "solides":
        raise ValueError("VR só sai pelo Sólides.")
    rows = (
        await db.execute(
            text(
                "SELECT emp.nome, regexp_replace(coalesce(emp.cpf,''),'[^0-9]','','g'), i.total, i.estado, "
                " coalesce((SELECT x.portal_cartao FROM folha_beneficio_conferencia x WHERE x.employee_id = i.employee_id "
                "   AND nullif(x.portal_cartao,'') IS NOT NULL ORDER BY x.competencia DESC LIMIT 1), '') "
                "FROM beneficio_entrega_itens i JOIN employees emp ON emp.id = i.employee_id "
                "WHERE i.entrega_id = :i AND upper(coalesce(i.operadora,'')) = :op ORDER BY emp.nome"
            ),
            {"i": entrega_id, "op": origem.upper()},
        )
    ).fetchall()
    linhas, avisos = [], []
    for nome, cpf, total, estado, cartao in rows:
        if total is None or Decimal(total) <= 0:
            avisos.append(f"{nome}: {estado} / sem valor — fora do arquivo")
            continue
        if origem == "sinetram" and not cartao:
            avisos.append(f"{nome}: SINETRAM sem nº de cartão conhecido — fora do arquivo")
            continue
        ln = LinhaBeneficio(cpf=cpf, nome=nome, cartao=cartao)
        if e["ben"] == "VR":
            ln.alimentacao = Decimal(total)
        else:
            ln.mobilidade = Decimal(total)
        linhas.append(ln)
    if not linhas:
        raise ValueError(f"Nenhum item de {origem.upper()} com valor nesta entrega.")
    mm, yy = e["referencia"].split("/")
    texto = bp.montar_arquivo_operador(origem, linhas, f"{yy}-{mm}", quem)
    nome = f"{origem.upper()}_entrega{entrega_id}_{datetime.now().strftime('%Y%m%d%H%M')}_{len(linhas)}_ConectaMais.txt"
    d = _dir_arquivos()
    d.mkdir(parents=True, exist_ok=True)
    (d / nome).write_text(texto, encoding="utf-8")
    await db.execute(
        text(
            "UPDATE beneficio_entregas SET arquivo_operador_path = :p, status = CASE WHEN status = 'aprovada' THEN 'enviada' ELSE status END, "
            "updated_at = now() WHERE id = :i"
        ),
        {"p": str(d / nome), "i": entrega_id},
    )
    await db.commit()
    return nome, texto, avisos


async def gerar_conta(db, entrega_id: int, user_id) -> dict:
    """Título a pagar da entrega — PayableService, como a tela «Registrar conta». Idempotente por
    `payable_id` (segundo clique devolve o mesmo). NÃO paga."""
    import modules.clients.models  # noqa: F401 — fora do app (oráculo/script) o mapper precisa de `condominiums` para o FK
    from modules.financial.schemas.payable import PayableAccountCreate
    from modules.financial.services.contas_fixas import COND_EMPRESA
    from modules.financial.services.payable_service import PayableService

    e = await _entrega(db, entrega_id)
    if e["payable_id"]:
        return {"payable_id": e["payable_id"], "ja_existia": True, "valor": float(e["total"] or 0)}
    if e["status"] not in ("aprovada", "enviada"):
        raise EntregaTravadaError(f"Entrega #{entrega_id} está {e['status']} — a conta só nasce de entrega aprovada.")
    if not e["total"] or Decimal(e["total"]) <= 0:
        raise ValueError("Entrega sem valor — nada a registrar.")
    venc = max(e["previsao_inicio"], date.today())  # o benefício tem de estar na mão no 1º dia previsto
    mm, yy = e["referencia"].split("/")
    conta = await PayableService(db).create_account(
        PayableAccountCreate(
            condominio_id=COND_EMPRESA,
            description=f"{e['tipo_nome']} {mm}/{yy} — entrega #{entrega_id} ({e['pessoas'] or 0} pessoa(s))"[:500],
            gross_value=Decimal(str(e["total"])),
            due_date=venc,
            competence_date=date(int(yy), int(mm), 1),
            supplier_name=e["tipo_nome"][:200],
            notes=f"Entrega de benefício #{entrega_id} ({e['ben']} {e['referencia']}, previsão "
            f"{e['previsao_inicio']:%d/%m/%Y}–{e['previsao_fim']:%d/%m/%Y}) — gerada pela tela «Entregas → Conta». Não paga.",
        ),
        user_id,
    )
    pid = str(getattr(conta, "id", None) or (conta.get("id") if isinstance(conta, dict) else ""))
    await db.execute(
        text("UPDATE beneficio_entregas SET payable_id = CAST(:p AS uuid), updated_at = now() WHERE id = :i"),
        {"p": pid, "i": entrega_id},
    )
    await db.commit()
    return {"payable_id": pid, "ja_existia": False, "valor": float(e["total"]), "vencimento": venc.isoformat()}


if __name__ == "__main__":  # auto-checagem das réguas puras (sem banco)
    assert _d("16/09/2026") == date(2026, 9, 16) and _d("2026-10-15") == date(2026, 10, 15) and _d("") is None
    m = {"previsao": {"VT": 20}, "removidos": {"V": {"VT": 3}, "A": {"VT": 2}}}
    assert _previsao(m, "VT", {"remover_ferias": True, "remover_afastados": True}) == 20
    assert _previsao(m, "VT", {"remover_ferias": False, "remover_afastados": True}) == 23
    assert _previsao(m, "VT", {}) == 25
    print("ok beneficio_entregas")
