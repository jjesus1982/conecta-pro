"""Configuração de ponto POR ESCOPO e feriados COM ESCOPO — a cascata abaixo do parâmetro global.

DGX F7 (24/09/2026). A DGX tem "Configurações de Ponto" aplicáveis a pessoa / contrato / vaga /
colaborador / função / modelo de escala / escala, com o flag "aplicado". Aqui a tabela
`ponto_configuracoes` guarda UMA linha por (escopo, escopo_id) e o resolvedor devolve o valor
mais específico:

    colaborador > escala > função > posto > condomínio > empresa > default do código

O default do código é o que os motores usam hoje (`coorte_ponto.TOLERANCIA_ENTRADA_MIN = 15`,
`presence_controller.TOLERANCIA_ATRASO = 15 min`, `mapa_de_ponto` raio 150 m). A linha-semente
`escopo=empresa` repete exatamente esses valores, então trocar a constante pelo resolvedor NÃO
muda nenhum estado do mapa de ponto — é o que `test_oraculo_ponto_configuravel.py` (c) prova.

`geofence_zones.entry_tolerance_minutes` do posto (dado que já existia) continua vencendo tudo
quando preenchido: é a regra que o mapa de ponto e a triagem já obedeciam.

Feriados: `cct_feriados` ganha `escopo` (nacional | estadual | municipal | cliente), `uf`,
`municipio`, `condominio_id`, `recorrente`. `feriados_do_periodo`/`feriados_do_dia` é a leitura
única: feriado de cliente vale SÓ para aquele condomínio; estadual/municipal valem para o
condomínio cuja UF/cidade batem (ou para todos quando não há condomínio na pergunta).

DDL idempotente em `_ensure(db)` (padrão da casa; `alembic/versions/` é zona proibida).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import text

#: O que o código usa hoje sem nenhuma linha no banco. Os cinco últimos campos são guardados
#: e resolvidos, mas NENHUM motor os lê ainda (ver relatório DGX_F7 §5) — origem diz isso.
DEFAULT: dict[str, Any] = {
    "tolerancia_entrada_min": 15,
    "tolerancia_saida_min": 15,
    "raio_metros": 150,
    "facial_obrigatoria": False,
    "arredondamento_min": 0,
    "intervalo_minimo_min": 0,
    "permitir_fora_do_raio": True,
}
CAMPOS = tuple(DEFAULT)
#: do menos ao mais específico — o último que fala, vence
ESCOPOS = ("empresa", "condominio", "posto", "funcao", "escala", "colaborador")

DDL = [
    """CREATE TABLE IF NOT EXISTS ponto_configuracoes (
  id serial PRIMARY KEY,
  escopo varchar(20) NOT NULL CHECK (escopo IN ('empresa','condominio','posto','funcao','escala','colaborador')),
  escopo_id text NOT NULL DEFAULT '',
  tolerancia_entrada_min integer CHECK (tolerancia_entrada_min >= 0),
  tolerancia_saida_min integer CHECK (tolerancia_saida_min >= 0),
  raio_metros integer CHECK (raio_metros > 0),
  facial_obrigatoria boolean,
  arredondamento_min integer CHECK (arredondamento_min >= 0),
  intervalo_minimo_min integer CHECK (intervalo_minimo_min >= 0),
  permitir_fora_do_raio boolean,
  aplicado boolean NOT NULL DEFAULT true,
  vigencia_inicio date, vigencia_fim date,
  origem_regra text, criado_por varchar(120),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now())""",
    "CREATE INDEX IF NOT EXISTS ix_ponto_configuracoes_escopo ON ponto_configuracoes (escopo, escopo_id) WHERE aplicado",
    "ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS escopo varchar(20) NOT NULL DEFAULT 'nacional'",
    "ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS uf varchar(2)",
    "ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS municipio varchar(80)",
    "ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS condominio_id uuid",
    "ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS recorrente boolean NOT NULL DEFAULT false",
    "ALTER TABLE cct_feriados ADD COLUMN IF NOT EXISTS observacao text",
    # semente: a empresa com os valores que o código usa hoje — comportamento idêntico ao de antes
    """INSERT INTO ponto_configuracoes (escopo, escopo_id, tolerancia_entrada_min, tolerancia_saida_min, raio_metros,
        origem_regra, criado_por)
 SELECT 'empresa', '', 15, 15, 150,
        'seed DGX F7 24/09/2026: coorte_ponto.TOLERANCIA_ENTRADA_MIN / presence_controller.TOLERANCIA_ATRASO = 15 min; mapa_de_ponto default 150 m',
        'dgx-f7'
  WHERE NOT EXISTS (SELECT 1 FROM ponto_configuracoes WHERE escopo = 'empresa')""",
    # os 16 feriados existentes: `tipo` já dizia nacional/estadual/municipal; o escopo repete o tipo.
    # Só corre UMA vez (depois escopo = tipo e a cláusula não casa mais). Empresa de Manaus/AM.
    """UPDATE cct_feriados
    SET escopo = tipo,
        uf = 'AM',
        municipio = CASE WHEN tipo = 'municipal' THEN 'Manaus' END,
        observacao = coalesce(observacao, 'escopo derivado de tipo (DGX F7, 24/09/2026): estadual→AM, municipal→Manaus')
  WHERE tipo IN ('estadual', 'municipal') AND escopo = 'nacional'""",
]

_ENSURED = False


async def _ensure(db) -> None:
    """DDL + semente, uma vez por processo (cada statement separado: asyncpg não aceita lote)."""
    global _ENSURED
    if _ENSURED:
        return
    for stmt in DDL:
        await db.execute(text(stmt))
    await db.commit()
    _ENSURED = True


# ───────────────────────────────────── regras ─────────────────────────────────────
_SQL_REGRAS = """
SELECT id, escopo, escopo_id, tolerancia_entrada_min, tolerancia_saida_min, raio_metros, facial_obrigatoria,
       arredondamento_min, intervalo_minimo_min, permitir_fora_do_raio, vigencia_inicio, vigencia_fim, origem_regra
  FROM ponto_configuracoes
 WHERE aplicado
   AND (vigencia_inicio IS NULL OR vigencia_inicio <= CAST(:ref AS date))
   AND (vigencia_fim IS NULL OR vigencia_fim >= CAST(:ref AS date))
 ORDER BY created_at, id
"""

#: DGX Y4 (24/09/2026): a coluna `condominio_id` daqui saía de `condominios.client_id =
#: e.cliente_id` e resolvia **0 dos 63 ativos** — `employees.cliente_id` é campo morto (órfão em
#: 37, nulo em 14; ver `operacional/services/vinculo_cliente.py`). Quem de fato resolve o
#: condomínio nesta função é o `_SQL_CTX_POSTO` logo abaixo, por `posto_atual_id → posts.client_id`
#: — 48 dos 63 —, que é a mesma fonte do nível 2 do resolvedor. A linha morta saiu: no único
#: registro do banco em que ela devolvia algo (um candidato), o caminho vivo devolve o MESMO
#: condomínio, então isto é deleção, não mudança de comportamento.
_SQL_CTX_EMPREGADO = """
SELECT e.cargo AS funcao, e.escala_padrao AS escala, e.posto_atual_id::text AS post_id
  FROM employees e WHERE e.id::text = :e
"""
_SQL_CTX_POSTO = """
SELECT (SELECT c.id::text FROM condominios c WHERE c.client_id = p.client_id ORDER BY c.ativo DESC LIMIT 1) AS condominio_id
  FROM posts p WHERE p.id::text = :p
"""


async def carregar_regras(db, ref: date | None = None) -> list[dict]:
    """Todas as regras aplicadas e vigentes em `ref` (hoje por padrão). Uma leitura; resolver é puro."""
    await _ensure(db)
    ref = ref or datetime.now().date()
    return [dict(r) for r in (await db.execute(text(_SQL_REGRAS), {"ref": ref})).mappings().all()]


def _casa(regra: dict, ctx: dict[str, str | None]) -> bool:
    esc = regra["escopo"]
    if esc == "empresa":
        return True
    alvo = ctx.get(esc)
    if not alvo:
        return False
    a, b = str(regra["escopo_id"] or "").strip(), str(alvo).strip()
    return a == b or (esc in ("funcao", "escala") and a.casefold() == b.casefold())


def resolver(regras: list[dict], **ctx: str | None) -> dict[str, Any]:
    """Pura. ctx: colaborador=, escala=, funcao=, posto=, condominio=. Devolve os CAMPOS +
    `origem` {campo: 'escopo:id' | 'default do código'}. Do menos ao mais específico; dentro do
    mesmo escopo, a linha mais recente vence (ordem de created_at da consulta)."""
    out: dict[str, Any] = dict(DEFAULT)
    origem = dict.fromkeys(CAMPOS, "default do código")
    for esc in ESCOPOS:
        for r in regras:
            if r["escopo"] != esc or not _casa(r, ctx):
                continue
            for c in CAMPOS:
                if r.get(c) is not None:
                    out[c] = r[c]
                    origem[c] = f"{esc}:{r['escopo_id'] or '—'}"
    out["origem"] = origem
    return out


async def config_ponto(
    db,
    employee_id: str | None = None,
    post_id: str | None = None,
    condominio_id: str | None = None,
    funcao: str | None = None,
    ref: date | None = None,
) -> dict[str, Any]:
    """A configuração de ponto que vale para esta pessoa/posto/condomínio/função em `ref`.

    O que faltar no pedido é completado pelo cadastro (função, escala e condomínio da pessoa;
    condomínio do posto). O mais específico vence; sem linha nenhuma, vale DEFAULT (15 min / 150 m).
    """
    escala = None
    if employee_id:
        r = (await db.execute(text(_SQL_CTX_EMPREGADO), {"e": str(employee_id)})).mappings().first()
        if r:
            funcao = funcao or r["funcao"]
            escala = r["escala"]
            post_id = post_id or r["post_id"]
    if post_id and not condominio_id:
        condominio_id = (await db.execute(text(_SQL_CTX_POSTO), {"p": str(post_id)})).scalar()
    regras = await carregar_regras(db, ref)
    return resolver(
        regras,
        colaborador=employee_id and str(employee_id),
        escala=escala,
        funcao=funcao,
        posto=post_id and str(post_id),
        condominio=condominio_id and str(condominio_id),
    )


# ───────────────────────────────────── feriados ─────────────────────────────────────
#: Um texto para o mundo async (asyncpg) e o sync (psycopg2): `text()` traduz os dois.
SQL_FERIADOS = """
SELECT f.id::text AS id, f.data_feriado, f.nome, f.tipo, coalesce(f.escopo, 'nacional') AS escopo, f.uf, f.municipio,
       f.condominio_id::text AS condominio_id, coalesce(f.recorrente, false) AS recorrente
  FROM cct_feriados f
  LEFT JOIN condominios co ON co.id = CAST(:cond AS uuid)
 WHERE coalesce(f.is_active, true)
   AND (coalesce(f.recorrente, false) OR f.data_feriado BETWEEN CAST(:de AS date) AND CAST(:ate AS date))
   AND (
        coalesce(f.escopo, 'nacional') = 'nacional'
     OR (f.escopo = 'estadual'  AND (f.uf IS NULL OR co.estado IS NULL OR upper(f.uf) = upper(co.estado)))
     OR (f.escopo = 'municipal' AND (f.municipio IS NULL OR co.cidade IS NULL OR lower(f.municipio) = lower(co.cidade)))
     OR (f.escopo = 'cliente'   AND f.condominio_id IS NOT NULL AND f.condominio_id = CAST(:cond AS uuid))
   )
 ORDER BY f.data_feriado, f.nome
"""


def _expandir(rows: list[dict], de: date, ate: date) -> dict[date, list[dict]]:
    """Recorrente = dia/mês fixo em todo ano do intervalo; os outros, só a data cadastrada."""
    out: dict[date, list[dict]] = {}
    for r in rows:
        d0: date = r["data_feriado"]
        anos = range(de.year, ate.year + 1) if r["recorrente"] else [d0.year]
        for y in anos:
            try:
                d = d0.replace(year=y)
            except ValueError:  # 29/02 em ano não bissexto
                continue
            if de <= d <= ate:
                out.setdefault(d, []).append(dict(r, data=d))
    return out


async def feriados_do_periodo(db, de: date, ate: date, condominio_id: str | None = None) -> dict[date, list[dict]]:
    """{data: [feriados]} válidos para o condomínio (None = só o que vale para todos: nacional,
    estadual e municipal sem restrição de UF/cidade; feriado de CLIENTE nunca entra sem condomínio)."""
    await _ensure(db)
    rows = (await db.execute(text(SQL_FERIADOS), {"de": de, "ate": ate, "cond": condominio_id})).mappings().all()
    return _expandir([dict(r) for r in rows], de, ate)


def feriados_do_periodo_sync(db, de: date, ate: date, condominio_id: str | None = None) -> dict[date, list[dict]]:
    """Mesma leitura para Session síncrona (espelho de ponto roda em rota `def`). Sem `_ensure`:
    a coluna `escopo` pode ainda não existir num processo que nunca abriu a tela → cai para a
    leitura antiga (todo feriado ativo), que é o comportamento de antes desta frente."""
    try:
        rows = db.execute(text(SQL_FERIADOS), {"de": de, "ate": ate, "cond": condominio_id}).mappings().all()
        rows = [dict(r) for r in rows]
    except Exception:  # noqa: BLE001 — tabela sem as colunas novas ainda
        db.rollback()
        rows = [
            dict(r, escopo="nacional", uf=None, municipio=None, condominio_id=None, recorrente=False)
            for r in db.execute(
                text(
                    "SELECT id::text AS id, data_feriado, nome, tipo FROM cct_feriados "
                    "WHERE coalesce(is_active,true) AND data_feriado BETWEEN :de AND :ate"
                ),
                {"de": de, "ate": ate},
            )
            .mappings()
            .all()
        ]
    return _expandir(rows, de, ate)


async def feriados_do_dia(db, data: date, condominio_id: str | None = None) -> list[dict]:
    return (await feriados_do_periodo(db, data, data, condominio_id)).get(data, [])
