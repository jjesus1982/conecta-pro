"""DGX F2 — CCT como DADO: Sindicato → Funções (cct_cargos) → Eventos por função → Benefícios por
função → Municípios. DDL idempotente + seed derivado das constantes que hoje vivem em Python
(`calculo_service`, `modules/cct`), cada linha com `origem_regra` dizendo de onde veio.

PARALELO CEGO: nada aqui muda o holerite. `calculo_service` continua lendo `employees.*_percentual`
e `cct_cargos.piso_salarial`; estas tabelas são a régua declarada — o oráculo
`test_oraculo_cct_como_dado.py` compara a régua com o holerite publicado e acusa a diferença.

Códigos: `rubrica_codigo` é o de `rubricas_folha` (0051 periculosidade, 0050 insalubridade,
0040 ronda 15%, 0020 noturno, 0010 HE 50%…). O holerite do `calculo_service` emite OUTROS
(0015/0016/0018/0040=HE) — de-para em `HOLERITE_PARA_RUBRICA`, e a colisão está no relatório.
"""

from __future__ import annotations

from sqlalchemy import text

#: holerite (`calculo_service`) → `rubricas_folha`. Só os adicionais que a CCT declara por função.
HOLERITE_PARA_RUBRICA = {"0015": "0051", "0016": "0050", "0018": "0040", "0020": "0020"}

DDL = """
CREATE TABLE IF NOT EXISTS cct_sindicatos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    nome varchar(200) NOT NULL UNIQUE,
    sigla varchar(40), cnpj varchar(20), uf char(2), data_base varchar(5),
    categoria varchar(160), site varchar(200), contato text,
    tipo varchar(10) NOT NULL DEFAULT 'laboral',
    ativo boolean NOT NULL DEFAULT true, origem_regra text,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE cct_convencoes ADD COLUMN IF NOT EXISTS sindicato_id uuid;
CREATE TABLE IF NOT EXISTS cct_funcao_eventos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cct_cargo_id uuid NOT NULL, rubrica_codigo varchar(10) NOT NULL,
    razao numeric(6,2), razao_noturna numeric(6,2),
    obrigatorio boolean NOT NULL DEFAULT false, observacao text, origem_regra text,
    ativo boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (cct_cargo_id, rubrica_codigo));
CREATE INDEX IF NOT EXISTS ix_cct_funcao_eventos_cargo ON cct_funcao_eventos (cct_cargo_id);
CREATE TABLE IF NOT EXISTS cct_funcao_beneficios (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cct_cargo_id uuid NOT NULL, cct_beneficio_id uuid NOT NULL,
    valor numeric(10,2), desconto_percentual numeric(5,2),
    obrigatorio boolean NOT NULL DEFAULT true, observacao text, origem_regra text,
    ativo boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (cct_cargo_id, cct_beneficio_id));
CREATE INDEX IF NOT EXISTS ix_cct_funcao_beneficios_cargo ON cct_funcao_beneficios (cct_cargo_id);
CREATE TABLE IF NOT EXISTS cct_municipios (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    convencao_id uuid NOT NULL, municipio varchar(120) NOT NULL, uf char(2) NOT NULL, ibge varchar(7),
    origem_regra text, created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (convencao_id, municipio, uf));
"""

_ORIG_CARGO = (
    "cct_cargos.adicional_tipo={tipo} (modules/cct/models/salary_table.CargoAdditional) → rubricas_folha {rub}"
)
#: eventos que valem para TODA função. (razão, razão noturna, origem)
_TODAS = [
    (
        "0020",
        "cct_cargos.adicional_noturno_percentual",
        None,
        "calculo_service 0020: 20% por hora noturna, pago pela ESCALA (plantões 22h–05h); depende do turno do funcionário, não do cargo",
    ),
    (
        "0021",
        None,
        None,
        "calculo_service 0021: 1h fictícia por plantão noturno (52'30''), fator (1 + 0,20 + ronda) × 1,5 — medido na Portte (96 obs.)",
    ),
    (
        "0010",
        "cct_cargos.horas_extras_percentual",
        None,
        "calculo_service: horas acima da jornada × 1,5 (CCT / modules/cct/models/schedule.ADICIONAIS.hora_extra_normal_percentual)",
    ),
    (
        "0011",
        "cct_cargos.horas_extras_noturnas_percentual",
        None,
        "cct_cargos.horas_extras_noturnas_percentual (feriado/100% — schedule.ADICIONAIS.hora_extra_feriado_percentual)",
    ),
    (
        "0030",
        "50",
        "50",
        "calculo_service 0030/0031: intrajornada não concedida, 1h por plantão × 1,5, só para quem tem employees.recebe_intrajornada (21/21 na Portte)",
    ),
    (
        "0090",
        None,
        None,
        "calculo_service 0090: DSR só sobre HORA EXTRA (Súm. 60/172 TST; medido 101/101 na Portte com noturno e sem HE = zero)",
    ),
    (
        "0051",
        "cct_cargos.adicional_periculosidade_percentual",
        None,
        "calculo_service 0015: periculosidade POR FUNCIONÁRIO (employees.periculosidade_percentual, NR-16); obrigatória só onde cct_cargos.adicional_tipo diz",
    ),
    (
        "0050",
        "cct_cargos.adicional_insalubridade_percentual",
        None,
        "calculo_service 0016: insalubridade POR FUNCIONÁRIO (employees.insalubridade_percentual, NR-15); schedule.ADICIONAIS.insalubridade_minimo_percentual=10",
    ),
    (
        "0040",
        "15",
        None,
        "calculo_service 0018: ronda 15% POR FUNCIONÁRIO (CCT cl. 23ª; employees.adicional_ronda_percentual; schedule.ADICIONAIS.ronda_permanente_percentual)",
    ),
]


async def ensure(db) -> None:
    """DDL + seed idempotentes (ON CONFLICT DO NOTHING). Chamada por `telas()` e por cada ação."""
    for stmt in DDL.split(";"):
        if stmt.strip():
            await db.execute(text(stmt))
    conv = (
        await db.execute(
            text(
                "SELECT id::text, sindicato_trabalhadores, sindicato_trabalhadores_cnpj, uf, data_base, municipio "
                "FROM cct_convencoes WHERE is_vigente AND is_active ORDER BY data_inicio DESC LIMIT 1"
            )
        )
    ).first()
    if not conv:
        await db.commit()
        return
    cid, nome, cnpj, uf, data_base, municipio = conv
    await db.execute(
        text(
            "INSERT INTO cct_sindicatos (nome, sigla, cnpj, uf, data_base, categoria, tipo, origem_regra) "
            "VALUES (:n, :n, :c, :uf, :db, :cat, 'laboral', "
            " 'seed F2: cct_convencoes vigente (sindicato_trabalhadores/cnpj/uf/data_base) + modules/cct/models/cct_metadata.CCT_METADATA') "
            "ON CONFLICT (nome) DO NOTHING"
        ),
        {
            "n": nome,
            "c": cnpj,
            "uf": uf,
            "db": data_base,
            "cat": "Empregados em condomínios e empresas de prestação de serviços (agentes de portaria)",
        },
    )
    # FK lógica: só preenche onde está NULL — nunca troca um vínculo já feito à mão.
    await db.execute(
        text(
            "UPDATE cct_convencoes c SET sindicato_id = s.id FROM cct_sindicatos s "
            "WHERE c.sindicato_id IS NULL AND s.nome = c.sindicato_trabalhadores"
        )
    )
    if municipio and uf:
        await db.execute(
            text(
                "INSERT INTO cct_municipios (convencao_id, municipio, uf, ibge, origem_regra) VALUES (:c, :m, :uf, :ibge, "
                " 'seed F2: cct_convencoes.municipio/uf da convenção vigente (abrangência declarada na CCT AM000613/2025)') "
                "ON CONFLICT (convencao_id, municipio, uf) DO NOTHING"
            ),
            {"c": cid, "m": municipio, "uf": uf, "ibge": "1302603" if municipio.strip().lower() == "manaus" else None},
        )

    cargos = (
        await db.execute(
            text(
                "SELECT id::text, adicional_tipo, adicional_noturno_percentual, adicional_periculosidade_percentual, "
                " adicional_insalubridade_percentual, horas_extras_percentual, horas_extras_noturnas_percentual "
                "FROM cct_cargos WHERE convencao_id = :c AND is_active"
            ),
            {"c": cid},
        )
    ).all()
    ins = text(
        "INSERT INTO cct_funcao_eventos (cct_cargo_id, rubrica_codigo, razao, razao_noturna, obrigatorio, origem_regra) "
        "VALUES (:cargo, :rub, :razao, :rn, :obrig, :orig) ON CONFLICT (cct_cargo_id, rubrica_codigo) DO NOTHING"
    )
    for cargo_id, tipo, not_pct, per_pct, ins_pct, he_pct, hen_pct in cargos:
        col = {
            "cct_cargos.adicional_noturno_percentual": not_pct,
            "cct_cargos.adicional_periculosidade_percentual": per_pct,
            "cct_cargos.adicional_insalubridade_percentual": ins_pct,
            "cct_cargos.horas_extras_percentual": he_pct,
            "cct_cargos.horas_extras_noturnas_percentual": hen_pct,
        }
        # cargo-level: o que cct_cargos.adicional_tipo declara vira OBRIGATÓRIO com a razão da própria linha
        if tipo == "periculosidade_30":
            await db.execute(
                ins,
                {
                    "cargo": cargo_id,
                    "rub": "0051",
                    "razao": per_pct or 30,
                    "rn": None,
                    "obrig": True,
                    "orig": _ORIG_CARGO.format(tipo=tipo, rub="0051"),
                },
            )
        elif tipo == "insalubridade_10":
            await db.execute(
                ins,
                {
                    "cargo": cargo_id,
                    "rub": "0050",
                    "razao": ins_pct or 10,
                    "rn": None,
                    "obrig": True,
                    "orig": _ORIG_CARGO.format(tipo=tipo, rub="0050"),
                },
            )
        # `adicional_10` (CARPINTEIROS E PEDREIROS) não tem rubrica em rubricas_folha — fica no relatório, não inventa código.
        for rub, razao_src, rn, orig in _TODAS:
            razao = col.get(razao_src, razao_src) if razao_src else None
            # zero na linha do cargo (peric/insal onde não é do cargo) → razão da constante da CCT (30/10)
            if rub == "0051" and not razao:
                razao = 30
            if rub == "0050" and not razao:
                razao = 10
            await db.execute(
                ins,
                {"cargo": cargo_id, "rub": rub, "razao": razao, "rn": rn, "obrig": False, "orig": "seed F2: " + orig},
            )

    await db.execute(
        text(
            "INSERT INTO cct_funcao_beneficios (cct_cargo_id, cct_beneficio_id, valor, desconto_percentual, obrigatorio, origem_regra) "
            "SELECT c.id, b.id, coalesce(b.valor_minimo, b.valor_empresa), "
            "       coalesce(b.desconto_percentual_sobre_salario, b.desconto_maximo_percentual), b.obrigatorio, "
            "       'seed F2: cct_beneficios.' || b.tipo_beneficio || ' (CCT vigente) — vale para toda função; obrigatorio/valor/desconto da própria linha' "
            "FROM cct_cargos c CROSS JOIN cct_beneficios b "
            "WHERE c.convencao_id = :c AND c.is_active AND b.convencao_id = :c AND b.is_active "
            "ON CONFLICT (cct_cargo_id, cct_beneficio_id) DO NOTHING"
        ),
        {"c": cid},
    )
    await db.commit()


async def funcoes_sem_evento(db) -> tuple[list[str], list[str]]:
    """(ativos cuja função não tem nenhum evento ativo, ativos sem função da CCT) — para a tela cct-conformidade."""
    ativo = (
        "lower(coalesce(e.status,''))='ativo' AND coalesce(e.is_homologacao,false)=false "
        "AND coalesce(e.tipo_contrato::text,'') NOT ILIKE '%pj%'"
    )
    sem_ev = (
        (
            await db.execute(
                text(
                    f"SELECT e.nome || ' — ' || c.cargo_nome FROM employees e JOIN cct_cargos c ON c.id=e.cct_cargo_id WHERE {ativo} "
                    "AND NOT EXISTS (SELECT 1 FROM cct_funcao_eventos x WHERE x.cct_cargo_id=c.id AND x.ativo) ORDER BY 1"
                )
            )
        )
        .scalars()
        .all()
    )
    sem_cct = (
        (
            await db.execute(
                text(
                    f"SELECT e.nome || ' — ' || coalesce(e.cargo,'sem cargo') FROM employees e WHERE {ativo} AND e.cct_cargo_id IS NULL ORDER BY 1"
                )
            )
        )
        .scalars()
        .all()
    )
    return list(sem_ev), list(sem_cct)
