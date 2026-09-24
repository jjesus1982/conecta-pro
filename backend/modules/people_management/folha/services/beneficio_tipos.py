"""Tipos de Benefício com REGRA (DGX F3, 24/09/2026) — o tipo carrega o desconto, a integração com
o ponto, os limites de falta e o que remover (férias/afastados), em vez de constantes em código.

Três tabelas/colunas, todas idempotentes (`_ensure`):
- `beneficio_tipos`  — a regra (7 tipos de desconto, 8 modos de ponto, limites, meio período).
- `beneficio_linhas` — itinerários/linhas de VT por operadora (tarifa SÓ com `origem_regra`).
- `employee_benefits` + tipo/linha/quantidade/unitário/anular outras fontes/manual.

Seed = o que `calculo_service` e `beneficio_ponto` fazem HOJE, com `origem_regra` dizendo de onde
veio. A regra do seed NÃO muda número nenhum: o oráculo `test_oraculo_beneficio_regra_e_dado.py`
prova Σ|Δ| = 0 contra a conferência já calculada. Quem muda a regra na tela muda o PARALELO CEGO
(`folha_beneficio_conferencia`) — a folha continua lendo `calculo_service`, que ninguém tocou.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import text

TIPOS_PRIMITIVOS = (
    "VT",
    "VR",
    "cesta",
    "odonto",
    "seguro_vida",
    "assistencia_medica",
    "PLR",
    "premio",
    "SESMT",
    "cartao",
    "outro",
)
TIPOS_DESCONTO = {
    "fixo": "Fixo",
    "nenhum": "Nenhum",
    "percentual_valor_sobre_falta": "% do valor sobre falta",
    "percentual_sobre_salario": "% sobre salário",
    "percentual_sobre_valor": "% sobre valor",
    "unidade": "Unidade",
    "valor_por_dia": "Valor por dia",
}
INTEGRACAO_PONTO = {
    "cafe_da_manha": "Café da manhã",
    "descanso": "Descanso",
    "diaria": "Diária",
    "horas_em_missao": "Horas em missão",
    "minimo_de_horas": "Mínimo de horas",
    "missao_rodoviaria": "Missão rodoviária",
    "reembolso_jornada": "Reembolso jornada",
    "reembolso_por_dia": "Reembolso por dia",
}
MEIO_PERIODO = ("nenhum", "valor", "percentual")
TIPOS_PASSE = ("cartao", "papel")
#: tipo primitivo → `employee_benefits.type` (enum BenefitType) quando o individual nasce pela tela nova
TYPE_POR_PRIMITIVO = {
    "VT": "vale_transporte",
    "VR": "vale_refeicao",
    "odonto": "plano_odontologico",
    "seguro_vida": "seguro_vida",
    "assistencia_medica": "plano_saude",
    "cesta": "vale_alimentacao",
}

DDL = [
    """CREATE TABLE IF NOT EXISTS beneficio_tipos (
  id bigserial PRIMARY KEY,
  nome varchar(100) NOT NULL UNIQUE,
  tipo_primitivo varchar(20) NOT NULL CHECK (tipo_primitivo IN ('VT','VR','cesta','odonto','seguro_vida','assistencia_medica','PLR','premio','SESMT','cartao','outro')),
  mensal boolean NOT NULL DEFAULT false,
  prevalecer_individual boolean NOT NULL DEFAULT false,
  tipo_desconto varchar(32) NOT NULL DEFAULT 'nenhum' CHECK (tipo_desconto IN ('fixo','nenhum','percentual_valor_sobre_falta','percentual_sobre_salario','percentual_sobre_valor','unidade','valor_por_dia')),
  coeficiente_desconto numeric(12,4),
  rubrica_debito varchar(10),
  desconto_direto_dinheiro boolean NOT NULL DEFAULT false,
  integracao_ponto varchar(24) CHECK (integracao_ponto IS NULL OR integracao_ponto IN ('cafe_da_manha','descanso','diaria','horas_em_missao','minimo_de_horas','missao_rodoviaria','reembolso_jornada','reembolso_por_dia')),
  desconto_por_saldo boolean NOT NULL DEFAULT false,
  limite_faltas integer,
  limite_faltas_justificadas integer,
  dias_trabalhados_mes integer,
  meses_afastamento_permitido integer,
  remover_ferias boolean NOT NULL DEFAULT false,
  remover_afastados boolean NOT NULL DEFAULT false,
  remover_atrasados boolean NOT NULL DEFAULT false,
  meio_periodo_tipo varchar(12) NOT NULL DEFAULT 'nenhum' CHECK (meio_periodo_tipo IN ('nenhum','valor','percentual')),
  meio_periodo_horas numeric(6,2),
  meio_periodo_valor numeric(12,2),
  cct_beneficio_id uuid,
  ativo boolean NOT NULL DEFAULT true,
  origem_regra text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
)""",
    """CREATE TABLE IF NOT EXISTS beneficio_linhas (
  id bigserial PRIMARY KEY,
  operadora varchar(40) NOT NULL,
  codigo varchar(40),
  nome varchar(200) NOT NULL,
  valor numeric(12,2),
  tipo_passe varchar(10) NOT NULL DEFAULT 'cartao' CHECK (tipo_passe IN ('cartao','papel')),
  mensal boolean NOT NULL DEFAULT false,
  ativo boolean NOT NULL DEFAULT true,
  origem_regra text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (operadora, nome)
)""",
    "ALTER TABLE employee_benefits ADD COLUMN IF NOT EXISTS beneficio_tipo_id bigint",
    "ALTER TABLE employee_benefits ADD COLUMN IF NOT EXISTS linha_id bigint",
    "ALTER TABLE employee_benefits ADD COLUMN IF NOT EXISTS quantidade numeric(10,2)",
    "ALTER TABLE employee_benefits ADD COLUMN IF NOT EXISTS valor_unitario numeric(12,2)",
    "ALTER TABLE employee_benefits ADD COLUMN IF NOT EXISTS anular_outras_fontes boolean NOT NULL DEFAULT false",
    "ALTER TABLE employee_benefits ADD COLUMN IF NOT EXISTS manual boolean NOT NULL DEFAULT false",
    "CREATE INDEX IF NOT EXISTS ix_employee_benefits_beneficio_tipo ON employee_benefits (beneficio_tipo_id)",
]

_SEM_REGRA = {
    "tipo_desconto": "nenhum",
    "coeficiente_desconto": None,
    "rubrica_debito": None,
    "integracao_ponto": None,
    "desconto_por_saldo": False,
    "remover_ferias": False,
    "remover_afastados": False,
    "mensal": True,
}
#: A regra que o código aplica HOJE, por `cct_beneficios.tipo_beneficio`. Números vêm de
#: `calculo_service` (lidos na hora do seed, nunca copiados à mão) e a origem diz de onde.
_VTVR = {
    "integracao_ponto": "diaria",
    "desconto_por_saldo": True,
    "remover_ferias": True,
    "remover_afastados": True,
    "mensal": False,
}


def _seed() -> list[dict]:
    from modules.people_management.folha.services import calculo_service as cs

    ponto = (
        "beneficio_ponto: previsão = dias da escala (shifts) no vínculo, férias e afastados removidos, "
        "quantidade = previsão ± saldo do mês anterior (recebido × trabalhado), sem limite de faltas"
    )
    return [
        {
            "nome": "Vale Transporte",
            "tipo_primitivo": "VT",
            "cct": "vale_transporte",
            **_VTVR,
            "tipo_desconto": "percentual_sobre_salario",
            "coeficiente_desconto": cs.DESC_VT_PCT * 100,
            "rubrica_debito": "1010",
            "origem_regra": f"calculo_service.DESC_VT_PCT={cs.DESC_VT_PCT} sobre salário base (rubrica 1010); unitário R$/dia em cct_benefit_configs por operadora; {ponto}",
        },
        {
            "nome": "Vale Refeição",
            "tipo_primitivo": "VR",
            "cct": "vale_refeicao",
            **_VTVR,
            "tipo_desconto": "percentual_sobre_salario",
            "coeficiente_desconto": cs.DESC_VR_PCT * 100,
            "rubrica_debito": "1011",
            "origem_regra": f"calculo_service.DESC_VR_PCT={cs.DESC_VR_PCT} sobre salário base (rubrica 1011); unitário R$/dia em cct_benefit_configs (cai para cct_beneficios.valor_minimo); 44h sem VR no sábado; {ponto}",
        },
        {
            "nome": "Plano Odontológico",
            "tipo_primitivo": "odonto",
            "cct": "plano_odontologico",
            **_SEM_REGRA,
            "tipo_desconto": "fixo",
            "coeficiente_desconto": cs.DESC_ODONTO,
            "rubrica_debito": "1020",
            "origem_regra": f"calculo_service.DESC_ODONTO={cs.DESC_ODONTO} (R$ {cs.DESC_ODONTO_COM_DEPENDENTE} com dependente — Pyetra 09/09/2026, só quem está no Servdonto)",
        },
        {
            "nome": "Seguro de Vida",
            "tipo_primitivo": "seguro_vida",
            "cct": "seguro_vida",
            **_SEM_REGRA,
            "tipo_desconto": "fixo",
            "coeficiente_desconto": cs.DESC_SEGURO,
            "rubrica_debito": "1021",
            "origem_regra": f"calculo_service.DESC_SEGURO={cs.DESC_SEGURO} (rubrica 1021)",
        },
        {
            "nome": "Cesta Básica",
            "tipo_primitivo": "cesta",
            "cct": "cesta_basica",
            **_SEM_REGRA,
            "origem_regra": "cct_beneficios.cesta_basica — sem desconto em código (não lançado na folha hoje)",
        },
        {
            "nome": "Ajuda Medicamento",
            "tipo_primitivo": "outro",
            "cct": "ajuda_medicamento",
            **_SEM_REGRA,
            "origem_regra": "cct_beneficios.ajuda_medicamento — sem desconto em código",
        },
        {
            "nome": "Auxílio Funeral",
            "tipo_primitivo": "outro",
            "cct": "auxilio_funeral",
            **_SEM_REGRA,
            "origem_regra": "cct_beneficios.auxilio_funeral — sem desconto em código",
        },
        {
            "nome": "Empréstimo Consignado",
            "tipo_primitivo": "outro",
            "cct": "emprestimo_consignado",
            **_SEM_REGRA,
            "origem_regra": "cct_beneficios.emprestimo_consignado (margem 30%) — desconto vive em `descontos` recorrentes, não é benefício de folha",
        },
    ]


_INS_TIPO = text(
    "INSERT INTO beneficio_tipos (nome, tipo_primitivo, mensal, tipo_desconto, coeficiente_desconto, rubrica_debito, integracao_ponto, "
    " desconto_por_saldo, remover_ferias, remover_afastados, cct_beneficio_id, origem_regra) "
    "VALUES (:nome, :tipo_primitivo, :mensal, :tipo_desconto, :coeficiente_desconto, :rubrica_debito, :integracao_ponto, "
    " :desconto_por_saldo, :remover_ferias, :remover_afastados, "
    " (SELECT id FROM cct_beneficios WHERE tipo_beneficio = :cct AND is_active ORDER BY updated_at DESC LIMIT 1), :origem_regra) "
    "ON CONFLICT (nome) DO NOTHING"
)
#: cct_beneficios que o seed acima não conhece: nasce sem regra, com a origem dizendo isso
_INS_TIPO_CCT_RESTO = text(
    "INSERT INTO beneficio_tipos (nome, tipo_primitivo, mensal, tipo_desconto, cct_beneficio_id, origem_regra) "
    "SELECT initcap(replace(tipo_beneficio,'_',' ')), 'outro', true, 'nenhum', id, 'cct_beneficios.' || tipo_beneficio || ' — sem regra em código' "
    "FROM cct_beneficios WHERE is_active AND tipo_beneficio <> ALL(:conhecidos) ON CONFLICT (nome) DO NOTHING"
)
#: linhas de VT a partir da fonte que existe: R$/dia por operadora em cct_benefit_configs (nunca tarifa inventada)
_INS_LINHAS = text(
    "INSERT INTO beneficio_linhas (operadora, nome, valor, tipo_passe, origem_regra) "
    "SELECT upper(operadora), 'Vale-transporte ' || upper(operadora) || ' (R$/dia)', valor_empresa, 'cartao', "
    " 'cct_benefit_configs vale_transporte/' || upper(operadora) || ' vigente desde ' || to_char(vigencia_inicio,'DD/MM/YYYY') || ': ' || coalesce(observacoes,'sem observação') "
    "FROM cct_benefit_configs WHERE lower(tipo_beneficio) = 'vale_transporte' AND coalesce(ativo,true) AND coalesce(operadora,'') <> '' "
    "ON CONFLICT (operadora, nome) DO NOTHING"
)
#: só preenche colunas MINHAS que estão NULL — nunca altera dado que já existia
_BACKFILL_TIPO = text(
    "UPDATE employee_benefits b SET beneficio_tipo_id = t.id FROM beneficio_tipos t WHERE b.beneficio_tipo_id IS NULL AND t.ativo "
    "AND t.tipo_primitivo = CASE WHEN lower(b.type) IN ('vt','vale_transporte') THEN 'VT' WHEN lower(b.type) IN ('vr','vale_refeicao') THEN 'VR' "
    " WHEN b.type ILIKE '%odont%' THEN 'odonto' WHEN b.type ILIKE '%seguro%' THEN 'seguro_vida' END"
)
_BACKFILL_LINHA = text(
    "UPDATE employee_benefits b SET linha_id = l.id FROM employees e, beneficio_linhas l, beneficio_tipos t "
    "WHERE b.linha_id IS NULL AND b.employee_id = e.id AND t.id = b.beneficio_tipo_id AND t.tipo_primitivo = 'VT' "
    "AND l.ativo AND l.operadora = upper(e.vt_modalidade) "
    "AND (SELECT count(*) FROM beneficio_linhas x WHERE x.operadora = l.operadora AND x.ativo) = 1"
)


async def _ensure(db) -> None:
    for ddl in DDL:
        await db.execute(text(ddl))
    seed = _seed()
    for s in seed:
        await db.execute(_INS_TIPO, s)
    await db.execute(_INS_TIPO_CCT_RESTO, {"conhecidos": [s["cct"] for s in seed]})
    await db.execute(_INS_LINHAS)
    await db.execute(_BACKFILL_TIPO)
    await db.execute(_BACKFILL_LINHA)
    await db.commit()


CAMPOS_REGRA = (
    "tipo_desconto",
    "coeficiente_desconto",
    "rubrica_debito",
    "integracao_ponto",
    "desconto_por_saldo",
    "limite_faltas",
    "limite_faltas_justificadas",
    "dias_trabalhados_mes",
    "meses_afastamento_permitido",
    "remover_ferias",
    "remover_afastados",
    "remover_atrasados",
    "meio_periodo_tipo",
    "meio_periodo_horas",
    "meio_periodo_valor",
)


async def regras(db) -> dict[str, dict]:
    """A regra ativa por tipo primitivo (VT/VR é o que o motor lê). Mais de um ativo por primitivo → o
    de menor id (o do seed) vence e `_ambigua` marca — o oráculo acusa."""
    await _ensure(db)
    rows = (
        await db.execute(
            text(
                f"SELECT tipo_primitivo, id, nome, {', '.join(CAMPOS_REGRA)} FROM beneficio_tipos WHERE ativo ORDER BY tipo_primitivo, id"
            )
        )
    ).fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        prim = r[0]
        if prim in out:
            out[prim]["_ambigua"] = True
            continue
        out[prim] = {"id": r[1], "nome": r[2], **dict(zip(CAMPOS_REGRA, r[3:], strict=True)), "_ambigua": False}
    return out


# ───────────────────────── escrita (telas) ─────────────────────────


def _bool(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "sim", "s", "yes", "on")


def _num(v, campo: str) -> Decimal | None:
    s = str(v if v is not None else "").strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    try:
        return Decimal(s.replace(".", "").replace(",", ".") if "," in s else s)
    except InvalidOperation:
        raise ValueError(f"{campo}: número inválido ({v!r})")


def _int(v, campo: str) -> int | None:
    n = _num(v, campo)
    if n is None:
        return None
    if n != n.to_integral_value() or n < 0:
        raise ValueError(f"{campo}: inteiro ≥ 0 esperado ({v!r})")
    return int(n)


def _enum(v, opcoes, campo: str, obrigatorio: bool = True):
    s = str(v or "").strip()
    if not s:
        if obrigatorio:
            raise ValueError(f"{campo}: obrigatório")
        return None
    if s not in opcoes:
        raise ValueError(f"{campo}: {s!r} não é um de {list(opcoes)}")
    return s


async def salvar_tipo(db, payload: dict, tipo_id: int | None = None) -> int:
    """Insere ou atualiza um tipo. Regra com desconto ≠ nenhum exige coeficiente; toda regra exige origem."""
    d = {
        "nome": str(payload.get("nome") or "").strip()[:100],
        "tipo_primitivo": _enum(payload.get("tipo_primitivo"), TIPOS_PRIMITIVOS, "Tipo primitivo"),
        "mensal": _bool(payload.get("mensal")),
        "prevalecer_individual": _bool(payload.get("prevalecer_individual")),
        "tipo_desconto": _enum(payload.get("tipo_desconto"), TIPOS_DESCONTO, "Tipo de desconto"),
        "coeficiente_desconto": _num(payload.get("coeficiente_desconto"), "Coeficiente"),
        "rubrica_debito": (str(payload.get("rubrica_debito") or "").strip() or None),
        "desconto_direto_dinheiro": _bool(payload.get("desconto_direto_dinheiro")),
        "integracao_ponto": _enum(
            payload.get("integracao_ponto"), INTEGRACAO_PONTO, "Integração com ponto", obrigatorio=False
        ),
        "desconto_por_saldo": _bool(payload.get("desconto_por_saldo")),
        "limite_faltas": _int(payload.get("limite_faltas"), "Faltas"),
        "limite_faltas_justificadas": _int(payload.get("limite_faltas_justificadas"), "Faltas justificadas"),
        "dias_trabalhados_mes": _int(payload.get("dias_trabalhados_mes"), "Dias trabalhados no mês"),
        "meses_afastamento_permitido": _int(payload.get("meses_afastamento_permitido"), "Meses de afastamento"),
        "remover_ferias": _bool(payload.get("remover_ferias")),
        "remover_afastados": _bool(payload.get("remover_afastados")),
        "remover_atrasados": _bool(payload.get("remover_atrasados")),
        "meio_periodo_tipo": _enum(payload.get("meio_periodo_tipo") or "nenhum", MEIO_PERIODO, "Meio período"),
        "meio_periodo_horas": _num(payload.get("meio_periodo_horas"), "Horas meio período"),
        "meio_periodo_valor": _num(payload.get("meio_periodo_valor"), "Desconto meio período"),
        "origem_regra": str(payload.get("origem_regra") or "").strip(),
        "ativo": _bool(payload.get("ativo", True)),
    }
    if not d["nome"]:
        raise ValueError("Nome: obrigatório")
    if not d["origem_regra"]:
        raise ValueError(
            "Origem da regra: obrigatória (CCT, decisão da Pyetra, código…) — regra sem fonte é regra inventada"
        )
    if d["tipo_desconto"] != "nenhum" and d["coeficiente_desconto"] is None:
        raise ValueError("Coeficiente: obrigatório quando o tipo de desconto não é 'Nenhum'")
    if (
        d["rubrica_debito"]
        and not (
            await db.execute(text("SELECT 1 FROM rubricas_folha WHERE codigo = :c"), {"c": d["rubrica_debito"]})
        ).scalar()
    ):
        raise ValueError(f"Rubrica de débito {d['rubrica_debito']} não existe em rubricas_folha")
    cols = list(d)
    if tipo_id is None:
        rid = (
            await db.execute(
                text(
                    f"INSERT INTO beneficio_tipos ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) RETURNING id"
                ),
                d,
            )
        ).scalar()
    else:
        rid = (
            await db.execute(
                text(
                    f"UPDATE beneficio_tipos SET {', '.join(f'{c} = :{c}' for c in cols)}, updated_at = now() WHERE id = :id RETURNING id"
                ),
                {**d, "id": tipo_id},
            )
        ).scalar()
        if rid is None:
            raise ValueError(f"Tipo {tipo_id} não existe")
    await db.commit()
    return int(rid)


async def inativar_tipo(db, tipo_id: int, ativo: bool = False) -> None:
    n = (
        await db.execute(
            text("UPDATE beneficio_tipos SET ativo = :a, updated_at = now() WHERE id = :id"),
            {"a": ativo, "id": tipo_id},
        )
    ).rowcount
    if not n:
        raise ValueError(f"Tipo {tipo_id} não existe")
    await db.commit()


async def salvar_linha(db, payload: dict, linha_id: int | None = None) -> int:
    d = {
        "operadora": str(payload.get("operadora") or "").strip().upper()[:40],
        "codigo": (str(payload.get("codigo") or "").strip()[:40] or None),
        "nome": str(payload.get("nome") or "").strip()[:200],
        "valor": _num(payload.get("valor"), "Valor"),
        "tipo_passe": _enum(payload.get("tipo_passe") or "cartao", TIPOS_PASSE, "Tipo de passe"),
        "mensal": _bool(payload.get("mensal")),
        "ativo": _bool(payload.get("ativo", True)),
        "origem_regra": (str(payload.get("origem_regra") or "").strip() or None),
    }
    if not d["operadora"] or not d["nome"]:
        raise ValueError("Operadora e nome: obrigatórios")
    if d["valor"] is not None and not d["origem_regra"]:
        raise ValueError(
            "Tarifa informada sem origem (tabela da operadora, data, quem confirmou) — a linha pode nascer SEM valor, nunca com valor sem fonte"
        )
    cols = list(d)
    if linha_id is None:
        rid = (
            await db.execute(
                text(
                    f"INSERT INTO beneficio_linhas ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) RETURNING id"
                ),
                d,
            )
        ).scalar()
    else:
        rid = (
            await db.execute(
                text(
                    f"UPDATE beneficio_linhas SET {', '.join(f'{c} = :{c}' for c in cols)}, updated_at = now() WHERE id = :id RETURNING id"
                ),
                {**d, "id": linha_id},
            )
        ).scalar()
        if rid is None:
            raise ValueError(f"Linha {linha_id} não existe")
    await db.commit()
    return int(rid)


async def salvar_individual(db, payload: dict) -> str:
    """Benefício individual (DGX EmpregadoBeneficios): tipo + linha + quantidade + unitário + anular outras
    fontes, `manual = true`. Grava em `employee_benefits` com as colunas de sempre preenchidas também."""
    eid = str(payload.get("employee_id") or "").strip()
    if (
        not eid
        or not (await db.execute(text("SELECT 1 FROM employees WHERE id = CAST(:e AS uuid)"), {"e": eid})).scalar()
    ):
        raise ValueError("Colaborador: obrigatório")
    tipo_id = _int(payload.get("beneficio_tipo_id"), "Tipo de benefício")
    prim = None
    if tipo_id is not None:
        prim = (
            await db.execute(text("SELECT tipo_primitivo FROM beneficio_tipos WHERE id = :i AND ativo"), {"i": tipo_id})
        ).scalar()
        if prim is None:
            raise ValueError(f"Tipo de benefício {tipo_id} não existe ou está inativo")
    typ = str(payload.get("type") or "").strip() or TYPE_POR_PRIMITIVO.get(prim or "", "other")
    if tipo_id is None and not payload.get("type"):
        raise ValueError("Informe o tipo de benefício (com regra) ou ao menos o tipo simples")
    linha_id = _int(payload.get("linha_id"), "Linha")
    if (
        linha_id is not None
        and not (
            await db.execute(text("SELECT 1 FROM beneficio_linhas WHERE id = :i AND ativo"), {"i": linha_id})
        ).scalar()
    ):
        raise ValueError(f"Linha {linha_id} não existe ou está inativa")
    d = {
        "employee_id": eid,
        "type": typ,
        "provider": (str(payload.get("provider") or "").strip() or None),
        "plan_name": (str(payload.get("plan_name") or "").strip() or None),
        "employee_contribution": _num(payload.get("employee_contribution"), "Valor desconto"),
        "company_contribution": _num(payload.get("company_contribution"), "Valor empresa"),
        "start_date": (str(payload.get("start_date") or "").strip() or None),
        "end_date": (str(payload.get("end_date") or "").strip() or None),
        "notes": (str(payload.get("notes") or "").strip() or None),
        "beneficio_tipo_id": tipo_id,
        "linha_id": linha_id,
        "quantidade": _num(payload.get("quantidade"), "Quantidade"),
        "valor_unitario": _num(payload.get("valor_unitario"), "Valor unitário"),
        "anular_outras_fontes": _bool(payload.get("anular_outras_fontes")),
    }
    rid = (
        await db.execute(
            text(
                "INSERT INTO employee_benefits (id, employee_id, type, provider, plan_name, employee_contribution, company_contribution, start_date, end_date, "
                " status, notes, beneficio_tipo_id, linha_id, quantidade, valor_unitario, anular_outras_fontes, manual, created_at, updated_at) "
                "VALUES (gen_random_uuid(), CAST(:employee_id AS uuid), :type, :provider, :plan_name, :employee_contribution, :company_contribution, "
                " CAST(:start_date AS date), CAST(:end_date AS date), 'active', :notes, :beneficio_tipo_id, :linha_id, :quantidade, :valor_unitario, "
                " :anular_outras_fontes, true, now(), now()) RETURNING id::text"
            ),
            d,
        )
    ).scalar()
    await db.commit()
    return str(rid)


if __name__ == "__main__":  # checagem mínima das réguas de entrada (sem banco)
    assert _num("1.234,50", "x") == Decimal("1234.50") and _num("4", "x") == Decimal("4") and _num("", "x") is None
    assert _int("3", "x") == 3 and _bool("sim") and not _bool("nao")
    try:
        _int("2.5", "x")
        raise SystemExit("inteiro aceitou 2.5")
    except ValueError:
        pass
    print("ok réguas")
