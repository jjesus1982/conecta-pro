"""DGX Y4 (24/09/2026) — de qual CLIENTE é este colaborador.

## Por que existe

`employees.cliente_id` é **campo morto**. Medido em 24/09/2026 no sandbox (cópia de produção do
dia) e conferido igual em produção, sobre os **63 ativos**:

| `employees.cliente_id` | quantos |
|---|---|
| órfão — aponta para um `clients.id` que não existe | **37** |
| nulo | **14** |
| FK válida | **12** (todos o MESMO cliente) |

A coluna nasceu sem `ForeignKey` (`operacional/models/employee.py:128`; a tabela também não tem a
constraint) e tem **dois** escritores vivos no repositório inteiro: a aprovação do candidato
(`human_resources/controllers/candidatos_esteira_controller.py:788`, que copia de
`posts.client_id`) e o autocadastro de homologação. Nenhuma admissão, nenhum importador de CSV,
nenhum sync da Sólides, nenhum PATCH de cadastro e nenhum backfill escreve nela. Os 37 órfãos são
anteriores aos dois escritores — ninguém mantém esse campo.

A consequência medida: a cascata `condominios.client_id = employees.cliente_id`, que a F7
(`ponto/config_ponto.py`) e a X3 (`folha/services/feriado_conferencia.py`) usam para achar o
condomínio da pessoa, resolvia **0 de 61** colaboradores com batida em 09/2026 — e por isso
**feriado de CLIENTE não alcançava ninguém** (`config_ponto.SQL_FERIADOS`: `escopo='cliente'`
exige `f.condominio_id = :cond`).

A verdade viva é a **alocação**, não o cadastro. Esta casa já tinha decidido isso — o irmão
`restricao_cliente.py:9` diz, com estas palavras: *«O elo posto/condomínio → cliente é o da casa:
`posts.client_id` e `condominios.client_id`»* — e `ged/services/kit_eventos.py` e
`client_portal/services/portal_operacao_service.py` já resolvem por alocação, nunca por
`employees.cliente_id`. O que faltava era **um** resolvedor com precedência declarada, que os
leitores da cascata pudessem chamar.

Por isso este módulo **não preenche os 51 cadastros**. Preencher por inferência é decisão do dono
(§7 do relatório); o resolvedor existe justamente para não precisar disso.

## Precedência (declarada — do mais forte ao mais fraco)

| # | fonte | de onde | confiança |
|---|---|---|---|
| 1 | `manual` | `dp_vinculo_cliente_manual` viva — o humano resolveu na tela | alta |
| 2 | `alocacao_posto` | `allocations` vigente em `ref` → `posts.client_id` | alta |
| 3 | `alocacao_condominio` | `employee_alocacoes` vigente em `ref` → `condominios.client_id` | alta |
| 4 | `turno` | `shifts` nos 60 dias até `ref` → `posts.client_id` | média |
| 5 | `cadastro` | `employees.cliente_id`, só com FK válida | baixa |

`conflito` quando as duas fontes **de registro** (2 e 3) existem e discordam, ou quando uma fonte
sozinha devolve mais de um cliente. Aí `cliente_id` volta **None**: conflito é sinalizado, nunca
escolhido no escuro — quem resolve é o humano, pela tela `vinculo-cliente`. `turno` é log de
evento (registra cobertura e substituição), então **nunca** gera conflito sozinho: só responde
quando não há alocação nenhuma, e com confiança média.

`cadastro` é o último de propósito, por ser o campo que ninguém mantém. Isso **não muda verdade**:
medido em 24/09, para os 12 que têm FK válida o resolvedor devolve exatamente o mesmo cliente
(Σ divergências = 0), porque o escritor vivo da coluna copia de `posts.client_id` — a mesma fonte
do nível 2. O oráculo `y4_vinculo_cliente` afirma essa igualdade; se um dia ficar vermelho, é o
cadastro que passou a mentir contra a alocação viva, e alguém tem que olhar.

## Estado medido no nascimento (24/09/2026, 63 ativos)

`alocacao_posto` 58 · `conflito` 2 (MAURICIO ALVES CHAGAS, RILEM FERREIRA DE SOUZA — posto e
condomínio discordam) · `sem_fonte` 3 (ALAN VIEIRA DA SILVA, THIAGO DA SILVA MAQUINE e o
COLABORADOR TESTE HOMOLOGACAO) · Σ divergências contra o cadastro válido = 0 · condomínio
resolvido 0 → **46**.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import text

#: A tabela da EXCEÇÃO: o que o humano declarou quando o dado não disse. Não é a regra — a regra é
#: a alocação. Encerrar não apaga (fica o histórico de quem decidiu e por quê).
_DDL = (
    "CREATE TABLE IF NOT EXISTS dp_vinculo_cliente_manual ("
    " id uuid PRIMARY KEY DEFAULT gen_random_uuid(), employee_id uuid NOT NULL, client_id uuid NOT NULL,"
    " motivo text NOT NULL, definido_por varchar(120), ativo boolean NOT NULL DEFAULT true,"
    " definido_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'America/Manaus'), definido_por_id uuid)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_dp_vinculo_cliente_manual_vivo"
    " ON dp_vinculo_cliente_manual (employee_id) WHERE ativo",
)

#: Rótulo em PT-BR de cada fonte, para tela e relatório.
FONTES = {
    "manual": "definido por pessoa",
    "alocacao_posto": "alocação vigente (posto)",
    "alocacao_condominio": "alocação vigente (condomínio)",
    "turno": "turno dos últimos 60 dias",
    "cadastro": "cadastro (employees.cliente_id)",
    "conflito": "CONFLITO — fontes discordam",
    "sem_fonte": "sem fonte nenhuma",
}

#: Confiança por fonte. `conflito` e `sem_fonte` não devolvem cliente, então não têm confiança.
CONFIANCA = {
    "manual": "alta",
    "alocacao_posto": "alta",
    "alocacao_condominio": "alta",
    "turno": "média",
    "cadastro": "baixa",
    "conflito": "nenhuma",
    "sem_fonte": "nenhuma",
}

#: A janela do nível 4. Turno é log de evento: 60 dias é o que separa «trabalha lá» de «cobriu um
#: plantão em março». Não é regra de lei — é corte de leitura, e está aqui para ser achado.
JANELA_TURNO_DIAS = 60

#: UMA consulta, os cinco níveis. Batch por construção (a tela lista 63 pessoas e a X3 apura uma
#: competência inteira) — `cliente_do_colaborador` é o caso de uma pessoa da MESMA consulta, para
#: não existirem duas implementações da mesma regra.
#:
#: `condominios` é 1:1 com `clients` (medido: 11 condomínios, 11 clientes distintos), então o
#: condomínio do cliente resolvido é determinístico — é o que a cascata da F7/X3 precisa.
_SQL = """
WITH alvo AS (
  SELECT e.id, coalesce(e.nome, '?') AS nome, e.cargo, e.status
    FROM employees e
   WHERE (:todos OR e.id::text = ANY(CAST(:ids AS text[])))
     AND (:inativos OR e.status = 'ativo')
),
man AS (SELECT employee_id AS eid, array_agg(DISTINCT client_id) AS c
          FROM dp_vinculo_cliente_manual WHERE ativo GROUP BY 1),
posto AS (SELECT al.employee_id AS eid, array_agg(DISTINCT p.client_id) AS c
            FROM allocations al JOIN posts p ON p.id = al.post_id
           WHERE al.is_active AND al.status = 'active'
             AND al.start_date <= CAST(:ref AS date)
             AND (al.end_date IS NULL OR al.end_date >= CAST(:ref AS date))
           GROUP BY 1),
cond AS (SELECT a.employee_id AS eid, array_agg(DISTINCT cd.client_id) AS c
           FROM employee_alocacoes a JOIN condominios cd ON cd.id = a.condominio_id
          WHERE a.ativo AND a.data_inicio <= CAST(:ref AS date)
            AND (a.data_fim IS NULL OR a.data_fim >= CAST(:ref AS date))
          GROUP BY 1),
turno AS (SELECT s.employee_id AS eid, array_agg(DISTINCT p.client_id) AS c
            FROM shifts s JOIN posts p ON p.id = s.post_id
           WHERE s.shift_date BETWEEN CAST(:ref AS date) - CAST(:janela AS integer) AND CAST(:ref AS date)
           GROUP BY 1),
cad AS (SELECT e.id AS eid, ARRAY[e.cliente_id] AS c
          FROM employees e JOIN clients k ON k.id = e.cliente_id),
res AS (
  SELECT t.id, t.nome, t.cargo, t.status, cad.c[1] AS cadastro_id,
         CASE
           WHEN array_length(man.c, 1) = 1 THEN 'manual'
           WHEN array_length(man.c, 1) > 1 THEN 'conflito'
           WHEN posto.c IS NOT NULL AND cond.c IS NOT NULL
                AND NOT (posto.c @> cond.c AND cond.c @> posto.c) THEN 'conflito'
           WHEN array_length(posto.c, 1) > 1 OR array_length(cond.c, 1) > 1 THEN 'conflito'
           WHEN array_length(posto.c, 1) = 1 THEN 'alocacao_posto'
           WHEN array_length(cond.c, 1) = 1 THEN 'alocacao_condominio'
           WHEN array_length(turno.c, 1) = 1 THEN 'turno'
           WHEN array_length(turno.c, 1) > 1 THEN 'conflito'
           WHEN array_length(cad.c, 1) = 1 THEN 'cadastro'
           ELSE 'sem_fonte' END AS fonte,
         CASE
           WHEN array_length(man.c, 1) = 1 THEN man.c[1]
           WHEN array_length(man.c, 1) > 1 THEN NULL
           WHEN posto.c IS NOT NULL AND cond.c IS NOT NULL
                AND NOT (posto.c @> cond.c AND cond.c @> posto.c) THEN NULL
           WHEN array_length(posto.c, 1) > 1 OR array_length(cond.c, 1) > 1 THEN NULL
           WHEN array_length(posto.c, 1) = 1 THEN posto.c[1]
           WHEN array_length(cond.c, 1) = 1 THEN cond.c[1]
           WHEN array_length(turno.c, 1) = 1 THEN turno.c[1]
           WHEN array_length(turno.c, 1) > 1 THEN NULL
           WHEN array_length(cad.c, 1) = 1 THEN cad.c[1]
           ELSE NULL END AS cliente_id,
         man.c AS v_man, posto.c AS v_posto, cond.c AS v_cond, turno.c AS v_turno
    FROM alvo t
    LEFT JOIN man   ON man.eid   = t.id
    LEFT JOIN posto ON posto.eid = t.id
    LEFT JOIN cond  ON cond.eid  = t.id
    LEFT JOIN turno ON turno.eid = t.id
    LEFT JOIN cad   ON cad.eid   = t.id
)
SELECT r.id::text AS employee_id, r.nome, r.cargo, r.status, r.fonte,
       r.cliente_id::text AS cliente_id, cl.name AS cliente_nome,
       r.cadastro_id::text AS cadastro_id, cadcl.name AS cadastro_nome,
       cd.id::text AS condominio_id, cd.nome AS condominio_nome,
       (SELECT string_agg(DISTINCT x.rot, ' · ' ORDER BY x.rot) FROM (
            SELECT 'posto: '       || k.name AS rot FROM clients k WHERE k.id = ANY(r.v_posto)
  UNION ALL SELECT 'condomínio: '  || k.name       FROM clients k WHERE k.id = ANY(r.v_cond)
  UNION ALL SELECT 'turno: '       || k.name       FROM clients k WHERE k.id = ANY(r.v_turno)
  UNION ALL SELECT 'definido: '    || k.name       FROM clients k WHERE k.id = ANY(r.v_man)
       ) x) AS evidencia
  FROM res r
  LEFT JOIN clients cl     ON cl.id = r.cliente_id
  LEFT JOIN clients cadcl  ON cadcl.id = r.cadastro_id
  LEFT JOIN condominios cd ON cd.client_id = r.cliente_id
 ORDER BY r.nome
"""

_ENSURED = False


async def _ensure(db) -> None:
    global _ENSURED
    if _ENSURED:
        return
    for s in _DDL:
        await db.execute(text(s))
    await db.commit()
    _ENSURED = True


async def mapa_cliente(
    db,
    employee_ids: list[str] | None = None,
    ref: date | None = None,
    *,
    incluir_inativos: bool = False,
) -> dict[str, dict]:
    """`{employee_id: {cliente_id, cliente_nome, condominio_id, condominio_nome, fonte, confianca,
    evidencia, cadastro_id, nome, cargo, status}}` — a mesma regra de `cliente_do_colaborador`,
    para quem precisa de muitos de uma vez (a tela, a apuração da X3). `employee_ids=None` = todos.
    """
    await _ensure(db)
    ids = [str(i) for i in (employee_ids or [])]
    rows = (
        await db.execute(
            text(_SQL),
            {
                "todos": employee_ids is None,
                "ids": ids,
                "ref": ref or datetime.now().date(),
                "janela": JANELA_TURNO_DIAS,
                "inativos": bool(incluir_inativos) or employee_ids is not None,
            },
        )
    ).mappings()
    return {r["employee_id"]: {**dict(r), "confianca": CONFIANCA[r["fonte"]]} for r in rows}


async def cliente_do_colaborador(db, employee_id: str, ref: date | None = None) -> tuple[str | None, str, str]:
    """De qual cliente é esta pessoa em `ref` (hoje por padrão) → `(cliente_id, fonte, confianca)`.

    `cliente_id` vem **None** quando a fonte é `conflito` ou `sem_fonte` — o resolvedor não
    escolhe no escuro. A precedência está no cabeçalho do módulo.
    """
    if not employee_id:
        return (None, "sem_fonte", CONFIANCA["sem_fonte"])
    r = (await mapa_cliente(db, [str(employee_id)], ref)).get(str(employee_id))
    if not r:
        return (None, "sem_fonte", CONFIANCA["sem_fonte"])
    return (r["cliente_id"], r["fonte"], r["confianca"])


async def condominio_do_colaborador(db, employee_id: str, ref: date | None = None) -> str | None:
    """O condomínio do cliente resolvido — o que a cascata da F7/X3 precisa para o escopo do
    feriado e da regra de ponto. None quando não há cliente resolvido ou o cliente não tem
    condomínio (17 dos 63 ativos em 24/09: os da CONECTAMAIS, que não são condomínio)."""
    if not employee_id:
        return None
    r = (await mapa_cliente(db, [str(employee_id)], ref)).get(str(employee_id))
    return r["condominio_id"] if r else None


class VinculoErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa (RestricaoErro)
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


async def definir_cliente(
    db,
    *,
    employee_id: str,
    client_id: str,
    motivo: str,
    definido_por: str | None = None,
    user_id: str | None = None,
) -> dict:
    """A EXCEÇÃO: o humano declara o cliente quando o dado não diz (conflito ou sem fonte).

    Grava a declaração em `dp_vinculo_cliente_manual` (que é o que faz a fonte virar `manual`) e
    espelha em `employees.cliente_id`/`cliente_nome`, que é onde os leitores antigos olham. **Uma
    pessoa por vez, e sempre com motivo** — preencher 51 cadastros por inferência é decisão do
    dono, não desta tela.
    """
    await _ensure(db)
    motivo = (motivo or "").strip()
    if not employee_id or not client_id:
        raise VinculoErro(400, "Colaborador e cliente são obrigatórios.")
    if len(motivo) < 5:
        raise VinculoErro(400, "Descreva o motivo (mínimo 5 caracteres) — é o que o DP vai ler daqui a um ano.")
    nome_cli = (
        await db.execute(text("SELECT name FROM clients WHERE id = CAST(:c AS uuid)"), {"c": client_id})
    ).scalar()
    if not nome_cli:
        raise VinculoErro(404, "Cliente não encontrado.")
    antes = await cliente_do_colaborador(db, employee_id)
    await db.execute(
        text("UPDATE dp_vinculo_cliente_manual SET ativo = false WHERE ativo AND employee_id = CAST(:e AS uuid)"),
        {"e": employee_id},
    )
    await db.execute(
        text(
            "INSERT INTO dp_vinculo_cliente_manual (employee_id, client_id, motivo, definido_por, definido_por_id)"
            " VALUES (CAST(:e AS uuid), CAST(:c AS uuid), :m, :p, CAST(:u AS uuid))"
        ),
        {"e": employee_id, "c": client_id, "m": motivo, "p": (definido_por or "").strip() or None, "u": user_id},
    )
    await db.execute(
        text("UPDATE employees SET cliente_id = CAST(:c AS uuid), cliente_nome = :n WHERE id = CAST(:e AS uuid)"),
        {"c": client_id, "n": nome_cli[:255], "e": employee_id},
    )
    await db.commit()
    depois = await cliente_do_colaborador(db, employee_id)
    return {
        "employee_id": str(employee_id),
        "cliente_id": str(client_id),
        "cliente_nome": nome_cli,
        "fonte_antes": antes[1],
        "fonte_depois": depois[1],
        "mudou_cliente": antes[0] != depois[0],
    }


def demo() -> None:
    """Self-check da regra de precedência — puro, sem banco. A precedência e o conflito são a
    lógica não trivial deste módulo; o SQL as escreve uma vez, aqui elas são afirmadas."""

    def resolver(man=None, posto=None, cond=None, turno=None, cad=None):
        """Espelho em Python do CASE do `_SQL` — se os dois divergirem, um dos dois está errado."""
        if man and len(man) == 1:
            return (man[0], "manual")
        if man and len(man) > 1:
            return (None, "conflito")
        if posto and cond and set(posto) != set(cond):
            return (None, "conflito")
        if (posto and len(posto) > 1) or (cond and len(cond) > 1):
            return (None, "conflito")
        if posto:
            return (posto[0], "alocacao_posto")
        if cond:
            return (cond[0], "alocacao_condominio")
        if turno and len(turno) > 1:
            return (None, "conflito")
        if turno:
            return (turno[0], "turno")
        if cad:
            return (cad[0], "cadastro")
        return (None, "sem_fonte")

    # o humano vence tudo, inclusive a alocação
    assert resolver(man=["A"], posto=["B"], cond=["C"]) == ("A", "manual")
    # posto vence condomínio quando concordam; e vence o cadastro morto
    assert resolver(posto=["A"], cond=["A"], cad=["Z"]) == ("A", "alocacao_posto")
    assert resolver(posto=["A"], cad=["Z"]) == ("A", "alocacao_posto")
    # as duas fontes de REGISTRO discordando = conflito, nunca escolha no escuro
    assert resolver(posto=["A"], cond=["B"]) == (None, "conflito")
    # turno é log de evento: não gera conflito contra a alocação (cobertura/substituição é normal)
    assert resolver(posto=["A"], turno=["A", "B"]) == ("A", "alocacao_posto")
    # ...mas sozinho e ambíguo, também não escolhe
    assert resolver(turno=["A", "B"]) == (None, "conflito")
    assert resolver(turno=["A"]) == ("A", "turno")
    # uma fonte só, com dois clientes, é conflito
    assert resolver(posto=["A", "B"]) == (None, "conflito")
    # o cadastro é o último, e só responde quando não há mais nada
    assert resolver(cad=["Z"]) == ("Z", "cadastro")
    assert resolver() == (None, "sem_fonte")
    print("OK vinculo_cliente: precedência e conflito conferidos (10 casos).")


if __name__ == "__main__":
    demo()
