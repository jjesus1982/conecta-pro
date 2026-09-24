"""DGX F6 — DP complementos (24/09/2026): dependentes, vales, eventos coletivos, crachás em lote,
demissão em lote. Prefixo `_` = o discovery pula; `departamento_pessoal.py` chama `telas(db, out)`
ANTES de `montar_grupos` (as abas estão em `_dp_grupos.GRUPOS`) e inclui `router`.

Onde cada coisa mora (cavado, não suposto):
- Dependentes: `employees.dependentes` (JSONB) é o que a FOLHA lê — salário-família pela chave
  `menor_14` e IRRF por `len()` (`calculo_service.py` 782/833). `employee_dp.dependentes` tem
  0 linhas e ninguém lê. Gravo na fonte da folha; `menor_14` deriva da régua de
  `salario_familia_service.contar_elegiveis` (até 14 anos ou inválido); `employee_dp.
  quantidade_dependentes_sf` vai junto (upsert) como o brief pediu.
- Vale: `employee_deductions` com `tipo='vale'`. A folha já lê a tabela (bloco 1040 do
  `calculo_service`) entre `data_inicio` e `data_fim` — `data_fim` = fim da competência da última
  parcela, então N parcelas = N competências sem ninguém avançar contador. Quitar = ativo=false.
- Evento coletivo: tabela própria; "aplicar" grava UM apontamento por colaborador pelo MESMO
  caminho de `folha-apontamento` (`rd_action_folha_apontamento` → `hr_payslips.contest_reason`,
  só folha rascunho). Não altera valor de holerite (paralelo cego): quem fecha vê o apontamento.
- Crachá: `hr/services/cracha_pdf.py` (timbrado `pdf_branding`), link `doc` como o relatório de
  pagamento. Demissão em lote: `TerminationService.create_termination` (mesmo de `nova-rescisao`),
  status `initiated` = rascunho do fluxo; verbas por `clt_calculator.calcular_rescisao`.
"""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.database.session import get_sync_db_dependency
from modules.operacional.controllers.redesign_data_controller import _fmtdate, _helpers, b, brl, initials, t
from modules.people_management.hr.services import salario_familia_service as sf

_ND = "#0F1B3A"

GRAUS = ["Filho/a", "Cônjuge", "Pai/Mae", "Irmã(o)", "Neto/a", "Bisneto/a", "Genro/Nora", "Sogro/a"]
INSTRUCAO = [
    "Analfabeto",
    "Até o 5º ano incompleto do Ensino Fundamental",
    "5º ano completo do Ensino Fundamental",
    "Do 6º ao 9º ano do Ensino Fundamental incompleto",
    "Ensino Fundamental Completo",
    "Ensino Médio incompleto",
    "Ensino Médio completo",
    "Educação Superior incompleta",
    "Educação Superior completa",
    "Mestrado completo",
    "Doutorado completo",
]
TIPOS_EVENTO = {"inclusao": "Inclusão", "remocao": "Remoção", "substituicao": "Substituição"}
TIPOS_RESCISAO = [
    ("involuntary", "Dispensa sem justa causa"),
    ("voluntary", "Pedido de demissão"),
    ("just_cause", "Dispensa por justa causa"),
    ("mutual_agreement", "Acordo mútuo (comum acordo)"),
    ("contract_end", "Fim de contrato"),
    ("retirement", "Aposentadoria"),
]

DDL = (
    "ALTER TABLE employee_deductions ADD COLUMN IF NOT EXISTS motivo text",
    "ALTER TABLE employee_deductions ADD COLUMN IF NOT EXISTS data_ocorrencia date",
    "ALTER TABLE employee_deductions ADD COLUMN IF NOT EXISTS valor_pago numeric(12,2) DEFAULT 0",
    "ALTER TABLE employee_deductions ADD COLUMN IF NOT EXISTS vencimento date",
    # O CHECK de `tipo` (consignado|pensao_alimenticia|emprestimo|outros) não conhecia 'vale'.
    # Recriado UMA vez, só se ainda não tiver 'vale' — os 4 valores antigos ficam.
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'employee_deductions_tipo_check' "
    " AND pg_get_constraintdef(oid) NOT LIKE '%vale%') THEN "
    " ALTER TABLE employee_deductions DROP CONSTRAINT employee_deductions_tipo_check; "
    " ALTER TABLE employee_deductions ADD CONSTRAINT employee_deductions_tipo_check "
    "  CHECK (tipo IN ('consignado','pensao_alimenticia','emprestimo','outros','vale')); END IF; END $$",
    # 1040 é o código que `calculo_service` já usa para TODO desconto de employee_deductions
    # (consignado, pensão, vale) — a descrição do holerite vem da linha, não daqui.
    "INSERT INTO rubricas_folha (codigo, descricao, tipo, natureza, incide_inss, incide_irrf, incide_fgts, ativo) "
    "VALUES ('1040', 'Vale / adiantamento avulso (e demais descontos do colaborador: consignado, pensão)', "
    "'desconto', 'variavel', false, false, false, true) ON CONFLICT (codigo) DO NOTHING",
    "CREATE TABLE IF NOT EXISTS folha_eventos_coletivos ("
    " id serial PRIMARY KEY, tipo varchar(20) NOT NULL, rubrica_codigo varchar(10) NOT NULL,"
    " rubrica_sucessora_codigo varchar(10), competencia date NOT NULL, data_inicio date, data_fim date,"
    " referencia numeric(12,2), filtro jsonb NOT NULL DEFAULT '{}'::jsonb, quantidade_colaboradores integer DEFAULT 0,"
    " criado_por varchar(120), criado_em timestamptz DEFAULT now(), aplicado_em timestamptz, desfeito_em timestamptz,"
    " apontamento_ids jsonb DEFAULT '[]'::jsonb, status varchar(12) NOT NULL DEFAULT 'rascunho')",
    "CREATE INDEX IF NOT EXISTS ix_folha_eventos_coletivos_comp ON folha_eventos_coletivos (competencia, status)",
)
_ensured = False  # ponytail: DDL idempotente uma vez por processo — ALTER TABLE pega lock mesmo sem mudar nada


async def _ensure(db: AsyncSession) -> None:
    global _ensured
    if _ensured:
        return
    for s in DDL:
        await db.execute(text(s))
    await db.commit()
    _ensured = True


def _ensure_sync(db) -> None:
    global _ensured
    if _ensured:
        return
    for s in DDL:
        db.execute(text(s))
    db.commit()
    _ensured = True


def _gate_dp(current_user: CurrentActiveUser) -> None:
    from .departamento_pessoal import _require_modulo_dp  # lazy: departamento_pessoal importa este módulo

    _require_modulo_dp(current_user)


def _lista(v) -> list[str]:
    """multiselect do redesign chega como JSON em string; lista chega como lista."""
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return []
        try:
            v = json.loads(v)
        except ValueError:
            return [x.strip() for x in v.split(",") if x.strip()]
    return [str(x) for x in (v or []) if str(x).strip()]


def _dec(v, campo: str) -> Decimal:
    """Aceita '300', '300.50' e o formato brasileiro '1.300,50'."""
    s = str(v or "0").replace("R$", "").strip()
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        raise HTTPException(status_code=422, detail=f"{campo}: valor inválido.")


def _competencia(v: str) -> date:
    m = re.fullmatch(r"\s*(\d{2})/(\d{4})\s*", v or "")
    ano, mes = (m.group(2), m.group(1)) if m else (None, None)
    if not m:
        m = re.fullmatch(r"\s*(\d{4})-(\d{2})\s*", v or "")
        ano, mes = (m.group(1), m.group(2)) if m else (None, None)
    try:
        return date(int(ano), int(mes), 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Competência no formato MM/AAAA.")


def _autor(u) -> str:
    return getattr(u, "name", None) or getattr(u, "email", None) or str(getattr(u, "id", "?"))


# ───────────────────────── 1. DEPENDENTES ─────────────────────────
def cpf_valido(cpf: str) -> bool:
    """Dígitos verificadores (módulo 11). Não reusa `government_integrations.utils.validar_cpf`:
    aquela mistura duas fórmulas (`(soma*10) % 11` e depois `11 - resto`) e REPROVA CPF válido
    (52998224725) — registrado no relatório da F6 para o dono do módulo."""
    d = re.sub(r"\D", "", cpf or "")
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        r = sum(int(d[i]) * (n + 1 - i) for i in range(n)) % 11
        if int(d[n]) != (0 if r < 2 else 11 - r):
            return False
    return True


def normalizar_dependentes(deps: list | None, ref: date | None = None) -> list[dict]:
    """`menor_14` (o que a folha lê) derivado da MESMA régua do salário-família. Entrada sem data
    e sem invalidez (backfill Portte de 07/2026) fica como está — não fabrico nem apago direito."""
    out = []
    for d in deps or []:
        if not isinstance(d, dict):
            continue
        d = dict(d)
        if d.get("nascimento") or d.get("data_nascimento") or d.get("invalido") or d.get("invalidez"):
            d["menor_14"] = sf.contar_elegiveis([d], ref) == 1
        out.append(d)
    return out


def _cpf_fmt(v: str) -> str:
    d = re.sub(r"\D", "", v or "")
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else (v or "—")


def _irrf_hint(d: dict, ref: date) -> str:
    """Dica legal (IN RFB 1500/2014 art. 90): filho/enteado até 21 (24 se universitário), cônjuge,
    pais. A folha HOJE deduz todos (`len()`), então a coluna avisa onde conferir."""
    grau = (d.get("grau") or d.get("tipo") or "").lower()
    idade = sf._idade_anos(d.get("nascimento") or d.get("data_nascimento"), ref)
    if grau.startswith(("filho", "neto", "bisneto")):
        if idade is None:
            return "conferir idade"
        lim = 24 if "superior" in (d.get("instrucao") or "").lower() else 21
        return "sim" if idade <= lim or d.get("invalido") else "não (idade)"
    if grau.startswith(("cônjuge", "conjuge", "pai")):
        return "sim"
    return "conferir"


async def _deps(db: AsyncSession, eid: str) -> list:
    row = (await db.execute(text("SELECT dependentes FROM employees WHERE id::text=:e"), {"e": eid})).first()
    if not row:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    return list(row[0]) if isinstance(row[0], list) else []


async def _gravar_deps(db: AsyncSession, eid: str, deps: list) -> list[dict]:
    deps = normalizar_dependentes(deps)
    n = sf.contar_elegiveis(deps)
    await db.execute(
        text("UPDATE employees SET dependentes = CAST(:j AS jsonb) WHERE id::text=:e"),
        {"j": json.dumps(deps, ensure_ascii=False), "e": eid},
    )
    await db.execute(
        text(
            "INSERT INTO employee_dp (id, employee_id, quantidade_dependentes_sf, salario_familia) VALUES (gen_random_uuid(), CAST(:e AS uuid), :n, :sf) "
            "ON CONFLICT (employee_id) DO UPDATE SET quantidade_dependentes_sf = EXCLUDED.quantidade_dependentes_sf, "
            "salario_familia = EXCLUDED.salario_familia, updated_at = now()"
        ),
        {"e": eid, "n": n, "sf": n > 0},
    )
    await db.commit()
    return deps


async def salvar_dependente(db: AsyncSession, eid: str, dado: dict) -> list[dict]:
    await _ensure(db)
    nome = (dado.get("nome") or "").strip()
    if len(nome) < 3:
        raise HTTPException(status_code=422, detail="Nome do dependente é obrigatório.")
    nasc = (dado.get("nascimento") or "").strip()
    try:
        nasc_d = date.fromisoformat(nasc) if nasc else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Data de nascimento inválida (AAAA-MM-DD).")
    if nasc_d and nasc_d > date.today():
        raise HTTPException(status_code=422, detail="Data de nascimento no futuro.")
    grau = (dado.get("grau") or "").strip()
    if grau not in GRAUS:
        raise HTTPException(status_code=422, detail=f"Grau de dependência inválido. Use um de: {', '.join(GRAUS)}.")
    cpf = re.sub(r"\D", "", dado.get("cpf") or "")
    if cpf and not cpf_valido(cpf):
        raise HTTPException(status_code=422, detail="CPF do dependente inválido (dígito verificador).")
    deps = await _deps(db, eid)
    if cpf and any(isinstance(d, dict) and re.sub(r"\D", "", d.get("cpf") or "") == cpf for d in deps):
        raise HTTPException(status_code=409, detail="Já existe dependente com este CPF para o colaborador.")
    deps.append(
        {
            "id": uuid4().hex[:8],
            "nome": nome,
            "nascimento": nasc or None,
            "grau": grau,
            "tipo": "filho" if grau.startswith("Filho") else grau.lower(),
            "sexo": (dado.get("sexo") or "")[:1].upper() or None,
            "deficiente": str(dado.get("deficiente") or "").lower() in ("sim", "true", "1"),
            "tipo_deficiencia": (dado.get("tipo_deficiencia") or "").strip()[:50] or None,
            "cpf": cpf or None,
            "rg": (dado.get("rg") or "").strip()[:20] or None,
            "instrucao": (dado.get("instrucao") or "").strip() or None,
            "fonte": "dp_dependentes",
        }
    )
    return await _gravar_deps(db, eid, deps)


async def remover_dependente(db: AsyncSession, eid: str, idx: int | None, nome: str | None = None) -> list[dict]:
    await _ensure(db)
    deps = await _deps(db, eid)
    if idx is None or not (0 <= idx < len(deps)):
        raise HTTPException(status_code=404, detail="Dependente não encontrado.")
    if nome and (deps[idx].get("nome") or "") != nome:
        raise HTTPException(status_code=409, detail="A lista mudou desde que a tela foi aberta — recarregue.")
    deps.pop(idx)
    return await _gravar_deps(db, eid, deps)


# ───────────────────────── 2. VALES ─────────────────────────
async def criar_vale(
    db: AsyncSession,
    eid: str,
    *,
    motivo: str,
    valor_total: Decimal,
    parcelas: int,
    data_ocorrencia: date,
    vencimento: date | None = None,
) -> str:
    await _ensure(db)
    if valor_total <= 0:
        raise HTTPException(status_code=422, detail="Valor do vale tem de ser maior que zero.")
    if not (1 <= parcelas <= 24):
        raise HTTPException(status_code=422, detail="Parcelas entre 1 e 24.")
    parcela = (valor_total / parcelas).quantize(Decimal("0.01"))
    row = (
        await db.execute(
            text(
                "INSERT INTO employee_deductions (employee_id, tipo, descricao, valor, base_calculo, parcela_atual, total_parcelas, "
                " data_inicio, data_fim, ativo, motivo, data_ocorrencia, valor_pago, vencimento, observacao) "
                "SELECT CAST(:e AS uuid), 'vale', :d, :v, 'fixo', 1, :p, :di, "
                " (date_trunc('month', CAST(:di AS date)) + make_interval(months => :p) - interval '1 day')::date, true, :m, :di, 0, :venc, "
                " :obs FROM employees WHERE id = CAST(:e AS uuid) AND status='ativo' RETURNING id::text"
            ),
            {
                "e": eid,
                "d": f"Vale — {motivo}"[:200],
                "v": parcela,
                "p": parcelas,
                "di": data_ocorrencia,
                "m": motivo,
                "venc": vencimento,
                "obs": f"vale de {brl(float(valor_total))} em {parcelas}x",
            },
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Colaborador ativo não encontrado.")
    await db.commit()
    return row[0]


async def quitar_vale(db: AsyncSession, vid: str) -> None:
    await _ensure(db)
    # ativo=false é o que tira da folha (o bloco 1040 do calculo_service filtra `ativo=true`)
    r = await db.execute(
        text(
            "UPDATE employee_deductions SET ativo=false, data_fim=current_date, valor_pago = valor * coalesce(total_parcelas, 1), "
            " updated_at=now() WHERE id::text=:i AND tipo='vale' AND ativo"
        ),
        {"i": vid},
    )
    await db.commit()
    if getattr(r, "rowcount", 0) == 0:
        raise HTTPException(status_code=404, detail="Vale não encontrado ou já quitado.")


# ───────────────────────── 3. EVENTOS COLETIVOS ─────────────────────────
SQL_COLABS = (
    "SELECT DISTINCT e.id::text, e.nome FROM employees e WHERE e.status='ativo' AND coalesce(e.is_homologacao,false)=false "
    "AND coalesce(e.tipo_contrato,'') NOT ILIKE '%pj%' AND (CAST(:todos AS boolean)"
    " OR e.id::text = ANY(CAST(:ids AS text[])) OR e.cargo = ANY(CAST(:funcoes AS text[])) OR e.escala_padrao = ANY(CAST(:escalas AS text[]))"
    " OR EXISTS (SELECT 1 FROM employee_alocacoes a WHERE a.employee_id = e.id AND a.condominio_id::text = ANY(CAST(:conds AS text[]))"
    "            AND coalesce(a.ativo,true) AND (a.data_fim IS NULL OR a.data_fim >= current_date))) ORDER BY e.nome"
)


def _filtro_params(filtro: dict, todos: bool = False) -> dict:
    return {
        "todos": todos,
        "ids": _lista(filtro.get("employee_ids")),
        "funcoes": _lista(filtro.get("funcoes")),
        "escalas": _lista(filtro.get("escalas")),
        "conds": _lista(filtro.get("condominio_ids")),
    }


async def criar_evento(db: AsyncSession, dado: dict, criado_por: str) -> int:
    await _ensure(db)
    tipo = (dado.get("tipo") or "").strip()
    if tipo not in TIPOS_EVENTO:
        raise HTTPException(status_code=422, detail="Tipo: inclusão, remoção ou substituição.")
    cod = (dado.get("rubrica_codigo") or "").strip()
    suc = (dado.get("rubrica_sucessora_codigo") or "").strip() or None
    if tipo == "substituicao" and not suc:
        raise HTTPException(status_code=422, detail="Substituição precisa da rubrica sucessora.")
    for c in filter(None, (cod, suc)):
        if not (await db.execute(text("SELECT 1 FROM rubricas_folha WHERE codigo=:c AND ativo"), {"c": c})).first():
            raise HTTPException(status_code=422, detail=f"Rubrica {c} não existe ou está inativa.")
    comp = _competencia(dado.get("competencia") or "")
    # guardado com as chaves do FORM (employee_ids/funcoes/escalas/condominio_ids) — é o que `_filtro_params` relê ao aplicar
    filtro = {k: _lista(dado.get(k)) for k in ("employee_ids", "funcoes", "escalas", "condominio_ids")}
    if not any(filtro.values()):
        raise HTTPException(status_code=422, detail="Escolha ao menos um colaborador, função, escala ou condomínio.")
    pessoas = (await db.execute(text(SQL_COLABS), _filtro_params(filtro))).fetchall()
    if not pessoas:
        raise HTTPException(status_code=422, detail="O filtro não alcança nenhum colaborador ativo.")
    ref = _dec(dado.get("referencia"), "Referência") if str(dado.get("referencia") or "").strip() else None

    def _d(k):
        v = (dado.get(k) or "").strip()
        try:
            return date.fromisoformat(v) if v else None
        except ValueError:
            raise HTTPException(status_code=422, detail=f"{k}: data inválida.")

    eid = (
        await db.execute(
            text(
                "INSERT INTO folha_eventos_coletivos (tipo, rubrica_codigo, rubrica_sucessora_codigo, competencia, data_inicio, data_fim, "
                " referencia, filtro, quantidade_colaboradores, criado_por) VALUES (:t, :c, :s, :comp, :di, :df, :ref, CAST(:f AS jsonb), :n, :quem) "
                "RETURNING id"
            ),
            {
                "t": tipo,
                "c": cod,
                "s": suc,
                "comp": comp,
                "di": _d("data_inicio"),
                "df": _d("data_fim"),
                "ref": ref,
                "f": json.dumps(filtro),
                "n": len(pessoas),
                "quem": criado_por[:120],
            },
        )
    ).scalar()
    await db.commit()
    return int(eid)


def _descreve(ev) -> str:
    """ev: tipo, rubrica_codigo, rubrica_sucessora_codigo, competencia, data_inicio, data_fim, referencia."""
    tipo, cod, suc, comp, di, df, ref = ev
    s = f"{TIPOS_EVENTO.get(tipo, tipo)} da rubrica {cod}" + (f" → {suc}" if suc else "")
    if ref is not None:
        s += f" · referência {ref}"
    s += f" · competência {comp.strftime('%m/%Y')}"
    if di or df:
        s += f" · {_fmtdate(di) if di else '…'} a {_fmtdate(df) if df else '…'}"
    return s


async def aplicar_evento(sdb, evento_id: int, current_user) -> dict:
    """Um apontamento por colaborador pelo MESMO caminho de `folha-apontamento` (sessão SÍNCRONA,
    como aquela ação). Só folha RASCUNHO; competência com folha publicada é recusada; folha que
    já tem apontamento de outra origem é pulada (a função sobrescreve o texto — não apago o de ninguém)."""
    from .departamento_pessoal import rd_action_folha_apontamento  # lazy: ciclo de import

    _ensure_sync(sdb)
    ev = sdb.execute(
        text(
            "SELECT tipo, rubrica_codigo, rubrica_sucessora_codigo, competencia, data_inicio, data_fim, referencia, "
            "filtro, status FROM folha_eventos_coletivos WHERE id=:i"
        ),
        {"i": evento_id},
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evento coletivo não encontrado.")
    if ev[8] != "rascunho":
        raise HTTPException(status_code=409, detail=f"Evento já está '{ev[8]}'.")
    comp = ev[3]
    if sdb.execute(
        text(
            "SELECT count(*) FROM hr_payslips WHERE reference_year=:a AND reference_month=:m AND status::text='published'"
        ),
        {"a": comp.year, "m": comp.month},
    ).scalar():
        raise HTTPException(
            status_code=409,
            detail=f"Competência {comp.strftime('%m/%Y')} tem folha PUBLICADA — evento coletivo só antes de publicar.",
        )
    pessoas = sdb.execute(text(SQL_COLABS), _filtro_params(ev[7] or {})).fetchall()
    motivo = f"[evento coletivo #{evento_id}] {_descreve(ev[:7])}"
    ids, sem_folha, ja_apontada = [], [], []
    for pid, nome in pessoas:
        ps = sdb.execute(
            text(
                "SELECT id::text, contest_reason FROM hr_payslips WHERE employee_id::text=:e AND reference_year=:a "
                "AND reference_month=:m AND status::text='draft' ORDER BY created_at DESC LIMIT 1"
            ),
            {"e": pid, "a": comp.year, "m": comp.month},
        ).first()
        if not ps:
            sem_folha.append(nome)
            continue
        if ps[1]:
            ja_apontada.append(nome)
            continue
        await rd_action_folha_apontamento(current_user, {"payslip_id": ps[0], "motivo": motivo}, sdb)
        ids.append(ps[0])
    sdb.execute(
        text(
            "UPDATE folha_eventos_coletivos SET status='aplicado', aplicado_em=now(), apontamento_ids=CAST(:ids AS jsonb), "
            "quantidade_colaboradores=:n WHERE id=:i"
        ),
        {"ids": json.dumps(ids), "n": len(ids), "i": evento_id},
    )
    sdb.commit()
    return {
        "aplicados": len(ids),
        "sem_folha_rascunho": sem_folha,
        "ja_apontada": ja_apontada,
        "alcancados": len(pessoas),
    }


async def desfazer_evento(sdb, evento_id: int) -> dict:
    _ensure_sync(sdb)
    ev = sdb.execute(
        text("SELECT status, apontamento_ids FROM folha_eventos_coletivos WHERE id=:i"), {"i": evento_id}
    ).first()
    if not ev:
        raise HTTPException(status_code=404, detail="Evento coletivo não encontrado.")
    if ev[0] != "aplicado":
        raise HTTPException(status_code=409, detail=f"Evento está '{ev[0]}' — só se desfaz o aplicado.")
    r = sdb.execute(
        text(
            "UPDATE hr_payslips SET contest_reason=NULL, contested_at=NULL WHERE id::text = ANY(CAST(:ids AS text[])) "
            "AND contest_reason LIKE :marca AND status::text='draft'"
        ),
        {"ids": list(ev[1] or []), "marca": f"%[evento coletivo #{evento_id}]%"},
    )
    sdb.execute(
        text("UPDATE folha_eventos_coletivos SET status='desfeito', desfeito_em=now() WHERE id=:i"), {"i": evento_id}
    )
    sdb.commit()
    return {"removidos": getattr(r, "rowcount", 0), "esperados": len(ev[1] or [])}


# ───────────────────────── 4. CRACHÁS ─────────────────────────
async def pessoas_para_cracha(db: AsyncSession, filtro: dict, limite: int = 200) -> list[dict]:
    p = _filtro_params(filtro)
    p["todos"] = not any(
        v for k, v in p.items() if k != "todos"
    )  # sem filtro = todos os ativos (o form avisa a contagem)
    ids = [r[0] for r in (await db.execute(text(SQL_COLABS), p)).fetchall()][:limite]
    if not ids:
        return []
    rows = (
        await db.execute(
            text(
                "SELECT e.id::text, e.nome, e.nome_de_guerra, e.cargo, e.matricula, e.cpf, e.cnv, e.foto_url, em.slug "
                "FROM employees e LEFT JOIN empresas em ON em.id = e.empresa_id WHERE e.id::text = ANY(CAST(:ids AS text[])) ORDER BY e.nome"
            ),
            {"ids": ids},
        )
    ).fetchall()
    return [
        {
            "employee_id": r[0],
            "nome": r[1],
            "nome_de_guerra": r[2],
            "cargo": r[3],
            "matricula": r[4],
            "cpf": r[5],
            "cnv": r[6],
            "foto_url": r[7],
            "empresa_slug": r[8],
        }
        for r in rows
    ]


# ───────────────────────── 5. DEMISSÃO EM LOTE ─────────────────────────
async def preparar_demissao_lote(
    db: AsyncSession,
    employee_ids: list[str],
    *,
    data: date,
    tipo: str,
    notice_type: str | None,
    notice_period_days: int | None,
    reason: str | None,
    created_by_id,
) -> list[dict]:
    """N rescisões em `initiated` (rascunho do fluxo) pelo MESMO serviço de `nova-rescisao`. Nada
    efetivado: status do colaborador, eSocial e pagamento seguem o fluxo normal de cada rescisão."""
    from modules.people_management.common.utils.clt_calculator import calcular_rescisao
    from modules.people_management.hr.models.termination import TerminationType
    from modules.people_management.hr.services import mapa_ferias as mf
    from modules.people_management.hr.services.termination_service import TerminationService

    await _ensure(db)
    if tipo not in {v for v, _l in TIPOS_RESCISAO}:
        raise HTTPException(status_code=422, detail="Tipo de rescisão inválido.")
    if not employee_ids:
        raise HTTPException(status_code=422, detail="Selecione ao menos um colaborador.")
    ferias = {r["employee_id"]: r for r in await mf.mapa(db)}
    svc = TerminationService(db)
    itens = []
    for eid in employee_ids:
        e = (
            await db.execute(
                text("SELECT nome, salario_base, data_admissao, status FROM employees WHERE id::text=:e"), {"e": eid}
            )
        ).first()
        if not e or e[3] != "ativo":
            itens.append(
                {
                    "employee_id": eid,
                    "nome": e[0] if e else eid,
                    "rescisao_id": None,
                    "verbas_estimadas": None,
                    "pendencias": ["colaborador não está ativo — pulado"],
                }
            )
            continue
        term = await svc.create_termination(
            {
                "employee_id": eid,
                "type": TerminationType(tipo),
                "reason": reason or None,
                "notice_type": notice_type,
                "notice_period_days": notice_period_days,
                "notice_start_date": None,
                "last_working_day": data,
            },
            created_by_id=created_by_id,
        )
        pend = []
        fv = ferias.get(eid)
        if fv and fv.get("vencida"):
            pend.append(f"férias VENCIDAS (limite {_fmtdate(fv.get('limite'))}) — dobra")
        elif fv and fv.get("risco_dobra"):
            pend.append("período aquisitivo > 22 meses")
        if not (
            await db.execute(
                text(
                    "SELECT 1 FROM gp_asos WHERE employee_id::text=:e AND tipo='demissional' AND data_realizacao IS NOT NULL "
                    "AND coalesce(status,'') NOT ILIKE '%cancel%' LIMIT 1"
                ),
                {"e": eid},
            )
        ).first():
            pend.append("sem ASO demissional")
        n_epi = (
            await db.execute(
                text(
                    "SELECT count(*) FROM sst_uniforme_entregas WHERE employee_id::text=:e AND entregue_em IS NOT NULL "
                    "AND devolvido_em IS NULL"
                ),
                {"e": eid},
            )
        ).scalar() or 0
        if n_epi:
            pend.append(f"{n_epi} item(ns) de uniforme/EPI a devolver")
        n_arma = (
            await db.execute(
                text(
                    "SELECT count(*) FROM equipamentos_controlados_alocacoes WHERE employee_id::text=:e "
                    "AND devolvido_em IS NULL"
                ),
                {"e": eid},
            )
        ).scalar() or 0
        if n_arma:
            pend.append(f"{n_arma} arma/colete em posse")
        verbas = None
        if e[1] and e[2] and data >= e[2]:
            try:
                calc = calcular_rescisao(
                    Decimal(str(e[1])), tipo, e[2], data, ferias_vencidas_dias=30 if (fv and fv.get("vencida")) else 0
                )
                verbas = float(calc.get("total_liquido") or 0)
            except Exception as ex:  # noqa: BLE001 — estimativa é opcional; a rescisão já existe
                pend.append(f"verbas não estimadas: {ex}")
        else:
            pend.append("sem salário/admissão para estimar verbas")
        itens.append(
            {
                "employee_id": eid,
                "nome": e[0],
                "rescisao_id": str(term.id),
                "verbas_estimadas": verbas,
                "pendencias": pend,
            }
        )
    await db.commit()
    return itens


# ───────────────────────── TELAS ─────────────────────────
async def telas(db: AsyncSession, out: dict) -> None:
    await _ensure(db)
    mine, safe, tbl = _helpers(db)
    hoje = date.today()
    ativos = (
        await db.execute(
            text(
                "SELECT id::text, nome, cargo, escala_padrao FROM employees WHERE status='ativo' "
                "AND coalesce(is_homologacao,false)=false ORDER BY nome"
            )
        )
    ).fetchall()
    opt_emp = [{"value": r[0], "label": r[1] or "—"} for r in ativos]
    opt_func = [{"value": f, "label": f} for f in sorted({r[2] for r in ativos if r[2]})]
    opt_esc = [{"value": f, "label": f} for f in sorted({r[3] for r in ativos if r[3]})]
    conds = (
        await db.execute(text("SELECT id::text, nome FROM condominios WHERE coalesce(ativo,true) ORDER BY nome"))
    ).fetchall()
    opt_cond = [{"value": r[0], "label": r[1]} for r in conds]

    # 1) dependentes — lista de todos os dependentes dos ativos, a partir do JSONB que a folha lê
    rows = (
        await db.execute(
            text(
                "SELECT id::text, nome, dependentes FROM employees WHERE status='ativo' "
                "AND coalesce(is_homologacao,false)=false AND jsonb_array_length(coalesce(dependentes,'[]'::jsonb)) > 0 "
                "ORDER BY nome"
            )
        )
    ).fetchall()
    linhas, n_dep, n_sf, n_sem_data = [], 0, 0, 0
    for eid, nome, deps in rows:
        for idx, d in enumerate(deps or []):
            if not isinstance(d, dict):
                continue
            n_dep += 1
            nasc = d.get("nascimento") or d.get("data_nascimento")
            idade = sf._idade_anos(nasc, hoje)
            sf_ok = bool(d.get("menor_14"))
            n_sf += sf_ok
            n_sem_data += not nasc
            defic = "Não"
            if d.get("deficiente") or d.get("invalido"):
                defic = "Sim" + (f" ({d['tipo_deficiencia']})" if d.get("tipo_deficiencia") else "")
            if sf_ok:
                sf_cell = b("sim", "ok") if (nasc or d.get("invalido")) else b("sim (sem data)", "warn")
            else:
                sf_cell = b("não", "mut")
            try:
                nasc_txt = _fmtdate(date.fromisoformat(str(nasc)[:10])) if nasc else "—"
            except ValueError:
                nasc_txt = str(nasc)
            linhas.append(
                {
                    "cells": [
                        t(nome, 600, _ND, initials(nome or "")),
                        t(d.get("nome") or "(sem nome — backfill Portte)"),
                        t(nasc_txt),
                        t("—" if idade is None else str(idade)),
                        t(d.get("grau") or (d.get("tipo") or "—").capitalize()),
                        t(d.get("sexo") or "—"),
                        t(defic),
                        t(_cpf_fmt(d.get("cpf")) if d.get("cpf") else "—"),
                        t((d.get("instrucao") or "—")[:28]),
                        sf_cell,
                        b(_irrf_hint(d, hoje), "info"),
                    ],
                    "filtro": nome,
                    "actions": [
                        {
                            "title": f"Remover {d.get('nome') or 'dependente'} de {nome}",
                            "sub": "Sai do cadastro e o salário-família/IRRF da próxima folha é recalculado sem ele.",
                            "endpoint": f"/api/v1/redesign/action/dependente-remover?eid={eid}&idx={idx}",
                            "method": "POST",
                            "btnLabel": "Remover",
                            "submitLabel": "Remover dependente",
                            "btnStyle": "outline",
                            "okMsg": "Dependente removido.",
                            "fields": [],
                        }
                    ],
                }
            )
    mine["dependentes"] = {
        "title": "Dependentes",
        "sub": f"{n_dep} dependente(s) de {len(rows)} colaborador(es) ativo(s) · {n_sf} contam para o salário-família (até 14 anos ou inválido) · "
        f"{n_sem_data} sem data de nascimento (herdados da Portte em 07/2026 — a folha paga a cota sem prova; cadastre a data). "
        "Fonte: o mesmo cadastro que a folha lê. IRRF: a folha deduz todos — a coluna diz onde conferir.",
        "cta": "Novo dependente",
        "ctaTo": "dependente-novo",
        "type": "table",
        "searchHint": "Buscar colaborador ou dependente…",
        "grid": "1.6fr 1.4fr 0.8fr 0.4fr 0.8fr 0.4fr 0.7fr 0.9fr 1.2fr 0.7fr 0.7fr",
        "cols": [
            "Colaborador",
            "Dependente",
            "Nascimento",
            "Idade",
            "Grau",
            "Sexo",
            "Deficiente",
            "CPF",
            "Instrução",
            "Sal.-família",
            "IRRF",
        ],
        "rows": linhas,
    }
    mine["dependente-novo"] = {
        "title": "Novo dependente",
        "sub": "Grava no cadastro do colaborador (o que a folha lê). CPF é validado quando informado.",
        "cta": "Salvar dependente",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/dependente-salvar", "okMsg": "Dependente salvo."},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione",
                "options": opt_emp,
            },
            {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2"},
            {"key": "nascimento", "label": "Nascimento", "type": "date", "span": "span 1"},
            {
                "key": "grau",
                "label": "Grau*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": g, "label": g} for g in GRAUS],
            },
            {
                "key": "sexo",
                "label": "Sexo",
                "type": "select",
                "span": "span 1",
                "ph": "—",
                "options": [{"value": "F", "label": "Feminino"}, {"value": "M", "label": "Masculino"}],
            },
            {
                "key": "deficiente",
                "label": "Deficiente",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "nao", "label": "Não"}, {"value": "sim", "label": "Sim"}],
            },
            {
                "key": "tipo_deficiencia",
                "label": "Tipo de deficiência",
                "type": "text",
                "span": "span 1",
                "ph": "Se houver",
            },
            {"key": "cpf", "label": "CPF", "type": "text", "span": "span 1", "ph": "000.000.000-00"},
            {"key": "rg", "label": "RG", "type": "text", "span": "span 1"},
            {
                "key": "instrucao",
                "label": "Grau de instrução",
                "type": "select",
                "span": "span 1",
                "ph": "—",
                "options": [{"value": i, "label": i} for i in INSTRUCAO],
            },
        ],
    }

    # 2) vales
    n_vales = (
        await db.execute(text("SELECT count(*) FROM employee_deductions WHERE tipo='vale' AND ativo"))
    ).scalar() or 0
    await safe(
        "vales",
        tbl(
            "Vales (adiantamento avulso)",
            f"{n_vales} aberto(s). O desconto entra na folha pelo mesmo caminho dos descontos recorrentes (rubrica 1040), uma parcela por competência, "
            "da competência da ocorrência até a última parcela. Quitar fecha antes (pagou por fora ou descontou tudo).",
            "Novo vale",
            ["Colaborador", "Motivo", "Data", "Vencimento", "Valor", "Parcela/mês", "Parcelas", "Pago", "Situação"],
            "1.6fr 1.6fr 0.7fr 0.7fr 0.8fr 0.8fr 0.5fr 0.8fr 0.7fr",
            "SELECT d.id::text, coalesce(e.nome,'—'), d.motivo, d.data_ocorrencia, d.vencimento, d.valor * coalesce(d.total_parcelas,1), d.valor, "
            " coalesce(d.total_parcelas,1), coalesce(d.valor_pago,0), coalesce(d.ativo,false), d.data_fim "
            "FROM employee_deductions d LEFT JOIN employees e ON e.id = d.employee_id WHERE d.tipo='vale' "
            "ORDER BY coalesce(d.ativo,false) DESC, d.data_ocorrencia DESC NULLS LAST, e.nome LIMIT 300",
            lambda r: [
                t(r[1], 600, _ND, initials(r[1] or "")),
                t((r[2] or "—")[:40]),
                t(_fmtdate(r[3])),
                t(_fmtdate(r[4])),
                t(brl(float(r[5] or 0)), 600),
                t(brl(float(r[6] or 0))),
                t(str(r[7])),
                t(brl(float(r[8] or 0))),
                b("Aberto", "warn") if r[9] else b("Pago", "ok"),
            ],
            actionsfn=lambda r: (
                [
                    {
                        "title": f"Quitar o vale de {r[1]}",
                        "sub": "Marca como pago e tira das próximas folhas. A linha fica.",
                        "endpoint": f"/api/v1/redesign/action/vale-quitar?vid={r[0]}",
                        "method": "POST",
                        "btnLabel": "Quitar",
                        "submitLabel": "Quitar vale",
                        "btnStyle": "outline",
                        "okMsg": "Vale quitado.",
                        "fields": [],
                    }
                ]
                if r[9]
                else None
            ),
            filtrofn=lambda r: "Aberto" if r[9] else "Pago",
        ),
    )
    if mine.get("vales"):
        mine["vales"]["ctaTo"] = "vale-novo"
    mine["vale-novo"] = {
        "title": "Novo vale",
        "sub": "Adiantamento avulso descontado em folha. Valor total dividido em parcelas iguais.",
        "cta": "Lançar vale",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/vale-salvar",
            "okMsg": "Vale lançado.",
            "confirm": "Isto lança um DESCONTO na folha do colaborador. Confirma?",
        },
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione",
                "options": opt_emp,
            },
            {
                "key": "motivo",
                "label": "Motivo*",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: adiantamento para conserto do carro",
            },
            {"key": "data_ocorrencia", "label": "Data*", "type": "date", "span": "span 1"},
            {"key": "valor_total", "label": "Valor total (R$)*", "type": "text", "span": "span 1", "ph": "300,00"},
            {"key": "parcelas", "label": "Parcelas*", "type": "number", "span": "span 1", "ph": "1"},
            {"key": "vencimento", "label": "Vencimento", "type": "date", "span": "span 1"},
        ],
    }

    # 3) eventos coletivos
    rubs = (
        await db.execute(text("SELECT codigo, descricao, tipo FROM rubricas_folha WHERE ativo ORDER BY codigo"))
    ).fetchall()
    opt_rub = [{"value": r[0], "label": f"{r[0]} — {r[1]} ({r[2]})"} for r in rubs]
    _TONE = {"rascunho": "warn", "aplicado": "ok", "desfeito": "mut"}

    def _acts_ev(r):
        if r[8] == "rascunho":
            return [
                {
                    "title": f"Aplicar evento #{r[0]}",
                    "sub": "Grava um apontamento na folha RASCUNHO de cada colaborador alcançado. "
                    "Competência com folha publicada é recusada. Pode desfazer.",
                    "endpoint": f"/api/v1/redesign/action/evento-coletivo-aplicar?eid={r[0]}",
                    "method": "POST",
                    "btnLabel": "Aplicar",
                    "submitLabel": "Aplicar a todos",
                    "okMsg": "Evento aplicado.",
                    "fields": [],
                }
            ]
        if r[8] == "aplicado":
            return [
                {
                    "title": f"Desfazer evento #{r[0]}",
                    "sub": "Remove só os apontamentos que este evento criou.",
                    "endpoint": f"/api/v1/redesign/action/evento-coletivo-desfazer?eid={r[0]}",
                    "method": "POST",
                    "btnLabel": "Desfazer",
                    "submitLabel": "Desfazer",
                    "btnStyle": "outline",
                    "okMsg": "Evento desfeito.",
                    "fields": [],
                }
            ]
        return None

    await safe(
        "eventos-coletivos",
        tbl(
            "Eventos coletivos",
            "Um lançamento para N pessoas numa competência (DGX). Aplicar grava UM apontamento por colaborador na folha rascunho, pelo mesmo "
            "caminho de «Apontar» — quem fecha a folha vê e lança. Não altera valor de holerite sozinho.",
            "Novo evento",
            ["#", "Tipo", "Rubrica", "Sucessora", "Competência", "Período", "Ref.", "Colab.", "Situação", "Quem"],
            "0.3fr 0.8fr 1.6fr 0.8fr 0.7fr 1fr 0.5fr 0.5fr 0.7fr 1fr",
            "SELECT ev.id, ev.tipo, ev.rubrica_codigo || ' — ' || coalesce(r.descricao,''), coalesce(ev.rubrica_sucessora_codigo,'—'), "
            " to_char(ev.competencia,'MM/YYYY'), ev.data_inicio, ev.data_fim, ev.referencia, ev.status, ev.quantidade_colaboradores, "
            " coalesce(ev.criado_por,'—'), ev.aplicado_em FROM folha_eventos_coletivos ev LEFT JOIN rubricas_folha r ON r.codigo = ev.rubrica_codigo "
            "ORDER BY ev.id DESC LIMIT 200",
            lambda r: [
                t(str(r[0])),
                b(TIPOS_EVENTO.get(r[1], r[1]), "info"),
                t(r[2][:40], 600, _ND),
                t(r[3]),
                t(r[4]),
                t(f"{_fmtdate(r[5])} – {_fmtdate(r[6])}" if r[5] or r[6] else "—"),
                t(str(r[7]) if r[7] is not None else "—"),
                t(str(r[9])),
                b(r[8].capitalize(), _TONE.get(r[8], "info")),
                t(r[10][:24]),
            ],
            actionsfn=_acts_ev,
            filtrofn=lambda r: r[4],
        ),
    )
    if mine.get("eventos-coletivos"):
        mine["eventos-coletivos"]["ctaTo"] = "evento-coletivo-novo"
    mine["evento-coletivo-novo"] = {
        "title": "Novo evento coletivo",
        "sub": "Escolha a rubrica e quem alcança (colaboradores, função, escala ou condomínio — os filtros somam). Nasce em rascunho; "
        "«Aplicar» na lista grava os apontamentos.",
        "cta": "Salvar rascunho",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/evento-coletivo-salvar",
            "okMsg": "Evento salvo em rascunho.",
            "gated": True,
            "confirm": "Isto prepara um lançamento de FOLHA para várias pessoas. Confirma o rascunho?",
        },
        "fields": [
            {
                "key": "tipo",
                "label": "Tipo*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": k, "label": v} for k, v in TIPOS_EVENTO.items()],
            },
            {
                "key": "competencia",
                "label": "Competência (MM/AAAA)*",
                "type": "text",
                "span": "span 1",
                "ph": hoje.strftime("%m/%Y"),
            },
            {
                "key": "rubrica_codigo",
                "label": "Rubrica (evento)*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": opt_rub,
            },
            {
                "key": "rubrica_sucessora_codigo",
                "label": "Rubrica sucessora (substituição)",
                "type": "select",
                "span": "span 1",
                "ph": "—",
                "options": opt_rub,
            },
            {
                "key": "referencia",
                "label": "Referência / valor",
                "type": "text",
                "span": "span 1",
                "ph": "Ex.: 10 (horas) ou 150,00",
            },
            {"key": "data_inicio", "label": "Início", "type": "date", "span": "span 1"},
            {"key": "data_fim", "label": "Término", "type": "date", "span": "span 1"},
            {
                "key": "condominio_ids",
                "label": "Condomínios",
                "type": "multiselect",
                "span": "span 1",
                "options": opt_cond,
            },
            {"key": "funcoes", "label": "Funções", "type": "multiselect", "span": "span 1", "options": opt_func},
            {"key": "escalas", "label": "Escalas", "type": "multiselect", "span": "span 1", "options": opt_esc},
            {
                "key": "employee_ids",
                "label": "Colaboradores (lista)",
                "type": "multiselect",
                "span": "span 2",
                "options": opt_emp,
            },
        ],
    }

    # 4) crachás em lote
    n_sem_foto = (
        await db.execute(
            text(
                "SELECT count(*) FROM employees WHERE status='ativo' AND coalesce(is_homologacao,false)=false "
                "AND coalesce(foto_url,'')=''"
            )
        )
    ).scalar() or 0
    mine["crachas-lote"] = {
        "title": "Crachás em lote (PDF)",
        "sub": f"Um PDF timbrado, 8 crachás por folha A4 (85,6 × 54 mm). Sem filtro = todos os {len(ativos)} ativos. "
        f"{n_sem_foto} ativo(s) sem foto no cadastro saem com moldura vazia — a resposta diz quantos.",
        "cta": "Gerar PDF",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/crachas-pdf", "okMsg": "PDF gerado.", "showResult": True},
        "fields": [
            {
                "key": "modelo",
                "label": "Modelo",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "frente", "label": "Frente simples"}],
            },
            {
                "key": "condominio_ids",
                "label": "Condomínios",
                "type": "multiselect",
                "span": "span 1",
                "options": opt_cond,
            },
            {"key": "funcoes", "label": "Funções", "type": "multiselect", "span": "span 1", "options": opt_func},
            {
                "key": "employee_ids",
                "label": "Colaboradores (lista)",
                "type": "multiselect",
                "span": "span 2",
                "options": opt_emp,
            },
        ],
    }

    # 5) demissão em lote
    mine["demissao-lote"] = {
        "title": "Demissão em lote (preparar rescisões)",
        "sub": "Abre UMA rescisão em rascunho por colaborador, pelo mesmo caminho de «Nova rescisão», e devolve verbas estimadas e "
        "pendências (férias vencidas, ASO demissional, uniforme/EPI, arma/colete). Nada é efetivado: cada rescisão segue o fluxo normal.",
        "cta": "Preparar rescisões",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/demissao-lote-preparar",
            "okMsg": "Rescisões preparadas.",
            "gated": True,
            "showResult": True,
            "confirm": "Isto abre um processo FORMAL de rescisão (rascunho) para CADA colaborador selecionado. Confirma?",
        },
        "fields": [
            {
                "key": "employee_ids",
                "label": "Colaboradores*",
                "type": "multiselect",
                "span": "span 2",
                "options": opt_emp,
            },
            {"key": "data", "label": "Último dia trabalhado*", "type": "date", "span": "span 1"},
            {
                "key": "type",
                "label": "Tipo de rescisão*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": v, "label": l} for v, l in TIPOS_RESCISAO],
            },
            {
                "key": "notice_type",
                "label": "Aviso prévio",
                "type": "select",
                "span": "span 1",
                "ph": "—",
                "options": [
                    {"value": "trabalhado", "label": "Trabalhado"},
                    {"value": "indenizado", "label": "Indenizado"},
                ],
            },
            {"key": "notice_period_days", "label": "Dias de aviso", "type": "number", "span": "span 1", "ph": "30"},
            {
                "key": "reason",
                "label": "Motivo",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: encerramento do contrato do condomínio X",
            },
        ],
    }
    out.update(mine)


# ───────────────────────── AÇÕES ─────────────────────────
router = APIRouter()


@router.post("/action/dependente-salvar", dependencies=[Depends(_gate_dp)])
async def rd_dependente_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    eid = (payload.get("employee_id") or "").strip()
    if not eid:
        raise HTTPException(status_code=422, detail="Selecione o colaborador.")
    deps = await salvar_dependente(db, eid, payload)
    return {"ok": True, "message": f"Dependente salvo. {sf.contar_elegiveis(deps)} conta(m) para o salário-família."}


@router.post("/action/dependente-remover", dependencies=[Depends(_gate_dp)])
async def rd_dependente_remover(
    current_user: CurrentActiveUser, eid: str, idx: int, db: AsyncSession = Depends(get_db)
) -> dict:
    deps = await remover_dependente(db, eid, idx)
    return {"ok": True, "message": f"Dependente removido. Restam {len(deps)}."}


@router.post("/action/vale-salvar", dependencies=[Depends(_gate_dp)])
async def rd_vale_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    eid = (payload.get("employee_id") or "").strip()
    motivo = (payload.get("motivo") or "").strip()
    if not eid or len(motivo) < 3:
        raise HTTPException(status_code=422, detail="Colaborador e motivo são obrigatórios.")
    try:
        data_oc = date.fromisoformat((payload.get("data_ocorrencia") or "").strip())
        venc = date.fromisoformat(payload["vencimento"]) if (payload.get("vencimento") or "").strip() else None
        parcelas = int(payload.get("parcelas") or 1)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Data, vencimento ou parcelas inválidos.")
    vid = await criar_vale(
        db,
        eid,
        motivo=motivo,
        valor_total=_dec(payload.get("valor_total"), "Valor"),
        parcelas=parcelas,
        data_ocorrencia=data_oc,
        vencimento=venc,
    )
    return {
        "ok": True,
        "message": f"Vale lançado ({parcelas}x) — entra na folha de {data_oc.strftime('%m/%Y')}.",
        "id": vid,
    }


@router.post("/action/vale-quitar", dependencies=[Depends(_gate_dp)])
async def rd_vale_quitar(current_user: CurrentActiveUser, vid: str, db: AsyncSession = Depends(get_db)) -> dict:
    await quitar_vale(db, vid)
    return {"ok": True, "message": "Vale quitado — sai das próximas folhas."}


@router.post("/action/evento-coletivo-salvar", dependencies=[Depends(_gate_dp)])
async def rd_evento_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    eid = await criar_evento(db, payload, criado_por=_autor(current_user))
    n = (
        await db.execute(text("SELECT quantidade_colaboradores FROM folha_eventos_coletivos WHERE id=:i"), {"i": eid})
    ).scalar()
    return {"ok": True, "message": f"Evento #{eid} salvo em rascunho — alcança {n} colaborador(es). Aplique na lista."}


@router.post("/action/evento-coletivo-aplicar", dependencies=[Depends(_gate_dp)])
async def rd_evento_aplicar(current_user: CurrentActiveUser, eid: int, db=Depends(get_sync_db_dependency)) -> dict:
    r = await aplicar_evento(db, eid, current_user)
    msg = f"Evento #{eid} aplicado a {r['aplicados']} de {r['alcancados']} colaborador(es)."
    if r["sem_folha_rascunho"]:
        msg += f" Sem folha rascunho na competência: {', '.join(r['sem_folha_rascunho'][:8])}{'…' if len(r['sem_folha_rascunho']) > 8 else ''}."
    if r["ja_apontada"]:
        msg += f" Já tinham apontamento (pulados): {', '.join(r['ja_apontada'][:8])}."
    return {"ok": True, "message": msg}


@router.post("/action/evento-coletivo-desfazer", dependencies=[Depends(_gate_dp)])
async def rd_evento_desfazer(current_user: CurrentActiveUser, eid: int, db=Depends(get_sync_db_dependency)) -> dict:
    r = await desfazer_evento(db, eid)
    return {
        "ok": True,
        "message": f"Evento #{eid} desfeito — {r['removidos']} de {r['esperados']} apontamento(s) removido(s).",
    }


@router.post("/action/crachas-pdf", dependencies=[Depends(_gate_dp)])
async def rd_crachas_pdf(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    from modules.people_management.hr.services.cracha_pdf import foto_path

    pessoas = await pessoas_para_cracha(db, payload)
    if not pessoas:
        raise HTTPException(status_code=400, detail="O filtro não alcança nenhum colaborador ativo.")
    sem_foto = [p["nome"] for p in pessoas if not foto_path(p.get("foto_url"))]
    ids = ",".join(p["employee_id"] for p in pessoas)
    return {
        "ok": True,
        "message": f"{len(pessoas)} crachá(s) em {(len(pessoas) + 7) // 8} folha(s). {len(sem_foto)} sem foto (moldura vazia).",
        "crachas": len(pessoas),
        "sem_foto": len(sem_foto),
        "sem_foto_nomes": ", ".join(sem_foto[:20]) + ("…" if len(sem_foto) > 20 else ""),
        "doc": {
            "label": f"Crachás ({len(pessoas)})",
            "url": f"/api/v1/redesign/crachas/pdf?ids={ids}",
            "fmt": "pdf",
            "mode": "blob",
        },
    }


@router.get("/crachas/pdf", summary="Crachás em lote (PDF padrão-ouro)")
async def rd_crachas_pdf_get(current_user: CurrentActiveUser, ids: str, db: AsyncSession = Depends(get_db)):
    from modules.people_management.hr.services.cracha_pdf import montar_crachas

    pessoas = await pessoas_para_cracha(db, {"employee_ids": _lista(ids)})
    if not pessoas:
        raise HTTPException(status_code=404, detail="Nenhum colaborador ativo nos ids informados.")
    pdf = montar_crachas(pessoas)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="crachas-{date.today().isoformat()}.pdf"'},
    )


@router.post("/action/demissao-lote-preparar", dependencies=[Depends(_gate_dp)])
async def rd_demissao_lote(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    ids = _lista(payload.get("employee_ids"))
    try:
        data = date.fromisoformat((payload.get("data") or "").strip())
    except ValueError:
        raise HTTPException(status_code=422, detail="Informe o último dia trabalhado.")
    try:
        dias = int(payload["notice_period_days"]) if str(payload.get("notice_period_days") or "").strip() else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Dias de aviso inválidos.")
    itens = await preparar_demissao_lote(
        db,
        ids,
        data=data,
        tipo=(payload.get("type") or "").strip(),
        notice_type=(payload.get("notice_type") or "").strip() or None,
        notice_period_days=dias,
        reason=(payload.get("reason") or "").strip() or None,
        created_by_id=getattr(current_user, "id", None),
    )
    criadas = [i for i in itens if i["rescisao_id"]]
    res = {
        "ok": True,
        "message": f"{len(criadas)} rescisão(ões) em rascunho de {len(itens)} selecionado(s). Nada efetivado — "
        "cada uma segue em Desligamento → Rescisões.",
    }
    for i in itens:
        res[i["nome"]] = (
            f"rescisão {i['rescisao_id'][:8]} · verbas estimadas {brl(i['verbas_estimadas'])}"
            if i["rescisao_id"] and i["verbas_estimadas"] is not None
            else ("rescisão aberta · verbas não estimadas" if i["rescisao_id"] else "NÃO aberta")
        ) + (" · pendências: " + "; ".join(i["pendencias"]) if i["pendencias"] else " · sem pendências")
    return res
