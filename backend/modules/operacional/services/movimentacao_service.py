"""Movimentação — alocar/remover colaborador de uma vaga com motivo tipado (paridade DGX, F5).

A unidade operacional do DGX (`/Movimentacoes/IncluirMovimentacao`): tipo (alocar | remover),
motivo (7), data, origem → destino, quem pediu. Aqui a tabela é `employee_alocacoes` — a mesma
que o kit do GEDEON, o Hermes, a categorização do Inter, o "Sem alocação" do DP e o grid da
frente 04 já leem. Esta é a PRIMEIRA escrita do app nessa tabela (até 24/09/2026 só seed e
importação escreviam nela — `checar_alocacao_de_quem_saiu` documenta).

Uma linha = uma alocação (estado), não um evento: remover NÃO cria linha, encerra a existente
(`ativo=false`, `data_fim`, `tipo='remover'`, `motivo_encerramento`). Linha de evento duplicaria
a pessoa nos joins por competência (`financeiro.py` soma folha × alocação por mês).

`AllocationRepository` (tabela `allocations`, employee × post, 89 linhas) é OUTRA tabela — não
tem regra reaproveitável aqui; a duplicidade é conferida por SQL nesta.

Dois passos (U1, 24/09/2026): `pedir()` grava em `op_movimentacao_pedidos` (pendente) SEM tocar
em `employee_alocacoes`; `aprovar()` chama `alocar()` — o mesmo caminho do DP (encerra a anterior
em D−1, parede da restrição por cliente) — e liga `alocacao_id`; `recusar()` só marca. O pedido
NÃO mora em `employee_alocacoes` de propósito: 4 leitores (folha × alocação em `financeiro.py`,
custo por condomínio no DP) filtram só por data, sem `ativo` — uma linha pendente lá vazaria
para a folha do condomínio antes de alguém aprovar.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

TIPOS = ("alocar", "remover")
MOTIVOS = {
    "a_pedido_do_cliente": "A pedido do cliente",
    "a_pedido_do_supervisor": "A pedido do supervisor",
    "alocacao_de_vaga": "Alocação de vaga",
    "cobertura_de_afastamento": "Cobertura de afastamento",
    "cobertura_de_falta": "Cobertura de falta",
    "cobertura_de_ferias": "Cobertura de férias",
    "treinamento": "Treinamento",
}
SOLICITANTES = {"cliente": "Cliente", "supervisor": "Supervisor", "dp": "DP", "sistema": "Sistema"}
MOTIVOS_COM_COBERTO = ("cobertura_de_ferias", "cobertura_de_afastamento")
LIMITE_FUTURO_DIAS = 60
RETRO = "retroativo: migrado em 24/09/2026 sem motivo declarado"

_DDL = [
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS tipo varchar(10)",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS motivo varchar(40)",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS motivo_encerramento varchar(40)",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS posto_id uuid",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS alocacao_origem_id uuid",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS solicitado_por varchar(20)",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS solicitante_nome varchar(120)",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS aprovado_por uuid",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS aprovado_em timestamp",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS observacao text",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS coberto_employee_id uuid",
    "ALTER TABLE employee_alocacoes ADD COLUMN IF NOT EXISTS created_by uuid",
    # retroativo: só as colunas novas ainda nulas; nada das antigas muda
    f"UPDATE employee_alocacoes SET tipo='alocar', motivo='alocacao_de_vaga', observacao=coalesce(observacao, '{RETRO}') "
    "WHERE tipo IS NULL AND motivo IS NULL",
    # dgx u1 — pedido de movimentação (pendente → aprovada | recusada); tabela própria de propósito (ver docstring)
    "CREATE TABLE IF NOT EXISTS op_movimentacao_pedidos ("
    " id uuid PRIMARY KEY DEFAULT gen_random_uuid(), employee_id uuid NOT NULL, condominio_id uuid NOT NULL, posto_id uuid,"
    " funcao varchar(120) NOT NULL, data_inicio date NOT NULL, motivo varchar(40) NOT NULL, coberto_employee_id uuid,"
    " solicitado_por varchar(20), solicitante_nome varchar(120), observacao text,"
    " status varchar(12) NOT NULL DEFAULT 'pendente', pedido_por uuid,"
    " pedido_em timestamp DEFAULT (now() AT TIME ZONE 'America/Manaus'),"
    " decidido_por uuid, decidido_em timestamp, decisao_motivo text, alocacao_id uuid)",
    "CREATE INDEX IF NOT EXISTS ix_op_mov_pedidos_status ON op_movimentacao_pedidos (status, pedido_em)",
]
STATUS_PEDIDO = ("pendente", "aprovada", "recusada")


class MovimentacaoErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


def hoje_manaus() -> date:
    return datetime.now(ZoneInfo("America/Manaus")).date()


async def _ensure(db) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await db.commit()


def _data(v) -> date:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise MovimentacaoErro(400, f"Data inválida: {v!r} (use AAAA-MM-DD).") from None


async def _coberto_ausente_em(db, coberto_employee_id: str, motivo: str, dia: date) -> bool:
    """Mesmas fontes da coorte do ponto (`coorte_ponto.SQL_NAO_AUSENTE_HOJE`): férias APROVADAS
    em `hr_vacation_requests`, afastamento ativo em `sst_afastamentos`."""
    if motivo == "cobertura_de_ferias":
        sql = (
            "SELECT 1 FROM hr_vacation_requests v WHERE v.employee_id = CAST(:e AS uuid) "
            "AND upper(coalesce(v.status,'')) = 'APPROVED' AND :d BETWEEN v.start_date AND v.end_date LIMIT 1"
        )
    else:
        sql = (
            "SELECT 1 FROM sst_afastamentos a WHERE a.employee_id = CAST(:e AS uuid) "
            "AND lower(coalesce(a.status,'')) IN ('em_andamento','ativo') AND a.data_inicio <= :d "
            "AND (a.data_retorno IS NULL OR a.data_retorno >= :d) LIMIT 1"
        )
    return (await db.execute(text(sql), {"e": coberto_employee_id, "d": dia})).scalar() is not None


async def _checar_entrada(
    db, employee_id, condominio_id, funcao, data_inicio, motivo, solicitado_por, posto_id, coberto_employee_id
) -> tuple[date, str]:
    """Checagens de entrada comuns a `alocar` e `pedir` (400/422). Devolve (dia, função em maiúsculas)."""
    dia = _data(data_inicio)
    funcao = (funcao or "").strip().upper()
    if not employee_id or not condominio_id or not funcao:
        raise MovimentacaoErro(400, "Colaborador, condomínio e função são obrigatórios.")
    if motivo not in MOTIVOS:
        raise MovimentacaoErro(400, f"Motivo inválido: {motivo!r}. Use um de {', '.join(MOTIVOS)}.")
    if solicitado_por not in SOLICITANTES:
        raise MovimentacaoErro(400, f"Solicitado por: {', '.join(SOLICITANTES)}.")
    if dia > hoje_manaus() + timedelta(days=LIMITE_FUTURO_DIAS):
        raise MovimentacaoErro(422, f"Data de início mais de {LIMITE_FUTURO_DIAS} dias no futuro ({dia:%d/%m/%Y}).")
    if motivo in MOTIVOS_COM_COBERTO:
        if not coberto_employee_id:
            raise MovimentacaoErro(422, f"{MOTIVOS[motivo]} exige informar QUEM está sendo coberto.")
        if not await _coberto_ausente_em(db, coberto_employee_id, motivo, dia):
            raise MovimentacaoErro(
                422,
                f"O coberto não tem {'férias aprovadas' if motivo == 'cobertura_de_ferias' else 'afastamento ativo'} em {dia:%d/%m/%Y}.",
            )
    if posto_id:
        ok = (
            await db.execute(
                text(
                    "SELECT 1 FROM posts p JOIN condominios c ON c.client_id = p.client_id "
                    "WHERE p.id = CAST(:p AS uuid) AND c.id = CAST(:c AS uuid)"
                ),
                {"p": posto_id, "c": condominio_id},
            )
        ).scalar()
        if not ok:
            raise MovimentacaoErro(422, "O posto informado não pertence a esse condomínio.")
    return dia, funcao


async def alocar(
    db,
    *,
    employee_id: str,
    condominio_id: str,
    funcao: str,
    data_inicio,
    motivo: str,
    solicitado_por: str = "dp",
    posto_id: str | None = None,
    solicitante_nome: str | None = None,
    coberto_employee_id: str | None = None,
    observacao: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Aloca em nova vaga. Encerra a alocação ativa anterior do colaborador em `data_inicio − 1` e
    liga `alocacao_origem_id`. 409 se já houver ativa igual; 422 se cobertura sem coberto ausente."""
    await _ensure(db)
    dia, funcao = await _checar_entrada(
        db, employee_id, condominio_id, funcao, data_inicio, motivo, solicitado_por, posto_id, coberto_employee_id
    )
    from modules.operacional.services import restricao_cliente as _rc  # dgx t3 — restrição por cliente

    try:
        await _rc.exigir_livre(db, employee_id, post_id=posto_id, condominio_id=condominio_id)
    except _rc.RestricaoErro as exc:
        raise MovimentacaoErro(exc.status, str(exc)) from exc

    ativas = (
        await db.execute(
            text(
                "SELECT id::text, condominio_id::text, funcao, coalesce(posto_id::text,''), data_inicio FROM employee_alocacoes "
                "WHERE employee_id = CAST(:e AS uuid) AND ativo AND (data_fim IS NULL OR data_fim >= :d) ORDER BY data_inicio DESC"
            ),
            {"e": employee_id, "d": dia},
        )
    ).fetchall()
    for a in ativas:
        if a[1] == condominio_id and a[2] == funcao and a[3] == (posto_id or ""):
            raise MovimentacaoErro(409, f"Já existe alocação ativa igual (desde {a[4]:%d/%m/%Y}).")
        if a[4] >= dia:
            raise MovimentacaoErro(
                409, f"Há alocação ativa que começa em {a[4]:%d/%m/%Y}; a nova precisa começar depois."
            )
    origem = ativas[0][0] if ativas else None
    for a in ativas:  # encerra a(s) anterior(es) no dia anterior — nunca duas ativas
        await db.execute(
            text("UPDATE employee_alocacoes SET ativo=false, data_fim=:f WHERE id = CAST(:i AS uuid)"),
            {"f": dia - timedelta(days=1), "i": a[0]},
        )
    novo = (
        await db.execute(
            text(
                "INSERT INTO employee_alocacoes (id, employee_id, condominio_id, funcao, data_inicio, ativo, tipo, motivo, posto_id, "
                " alocacao_origem_id, solicitado_por, solicitante_nome, aprovado_por, aprovado_em, observacao, coberto_employee_id, created_by) "
                "VALUES (gen_random_uuid(), CAST(:e AS uuid), CAST(:c AS uuid), :f, :d, true, 'alocar', :m, CAST(:p AS uuid), "
                " CAST(:o AS uuid), :s, :sn, CAST(:u AS uuid), CASE WHEN CAST(:u AS uuid) IS NULL THEN NULL ELSE (now() AT TIME ZONE 'America/Manaus') END, :obs, CAST(:cob AS uuid), CAST(:u AS uuid)) "
                "RETURNING id::text"
            ),
            {
                "e": employee_id,
                "c": condominio_id,
                "f": funcao,
                "d": dia,
                "m": motivo,
                "p": posto_id or None,
                "o": origem,
                "s": solicitado_por,
                "sn": (solicitante_nome or "").strip() or None,
                "u": user_id or None,
                "obs": (observacao or "").strip() or None,
                "cob": coberto_employee_id or None,
            },
        )
    ).scalar()
    await db.commit()
    return {"id": novo, "encerrou": [a[0] for a in ativas], "data_inicio": dia.isoformat()}


async def remover(
    db, *, alocacao_id: str, data_fim, motivo: str, observacao: str | None = None, user_id: str | None = None
) -> dict:
    """Remove o colaborador da vaga atual: encerra a alocação (ativo=false) em `data_fim`."""
    await _ensure(db)
    fim = _data(data_fim)
    if motivo not in MOTIVOS:
        raise MovimentacaoErro(400, f"Motivo inválido: {motivo!r}.")
    if fim > hoje_manaus() + timedelta(days=LIMITE_FUTURO_DIAS):
        raise MovimentacaoErro(422, f"Data de fim mais de {LIMITE_FUTURO_DIAS} dias no futuro.")
    row = (
        await db.execute(
            text("SELECT data_inicio, ativo FROM employee_alocacoes WHERE id = CAST(:i AS uuid)"), {"i": alocacao_id}
        )
    ).fetchone()
    if not row:
        raise MovimentacaoErro(404, "Alocação não encontrada.")
    if not row[1]:
        raise MovimentacaoErro(409, "Essa alocação já está encerrada.")
    if fim < row[0]:
        raise MovimentacaoErro(422, f"Data de fim ({fim:%d/%m/%Y}) anterior ao início ({row[0]:%d/%m/%Y}).")
    await db.execute(
        text(
            "UPDATE employee_alocacoes SET ativo=false, data_fim=:f, tipo='remover', motivo_encerramento=:m, "
            " observacao = CASE WHEN CAST(:obs AS text) IS NULL THEN observacao ELSE concat_ws(' | ', observacao, CAST(:obs AS text)) END, "
            " aprovado_por = coalesce(CAST(:u AS uuid), aprovado_por), aprovado_em = CASE WHEN CAST(:u AS uuid) IS NULL THEN aprovado_em ELSE (now() AT TIME ZONE 'America/Manaus') END "
            "WHERE id = CAST(:i AS uuid)"
        ),
        {"f": fim, "m": motivo, "obs": (observacao or "").strip() or None, "u": user_id or None, "i": alocacao_id},
    )
    await db.commit()
    return {"id": alocacao_id, "data_fim": fim.isoformat()}


# ───────────────────────── dois passos (dgx u1) ─────────────────────────
_CAMPOS_PEDIDO = (
    "employee_id::text, condominio_id::text, posto_id::text, funcao, data_inicio, motivo, coberto_employee_id::text, "
    "solicitado_por, solicitante_nome, observacao, status"
)


async def pedir(
    db,
    *,
    employee_id: str,
    condominio_id: str,
    funcao: str,
    data_inicio,
    motivo: str,
    solicitado_por: str = "supervisor",
    posto_id: str | None = None,
    solicitante_nome: str | None = None,
    coberto_employee_id: str | None = None,
    observacao: str | None = None,
    user_id: str | None = None,
) -> dict:
    """Pedido de alocação: mesma checagem de entrada do `alocar`, mas NÃO toca em `employee_alocacoes`.
    A anterior continua ativa até alguém aprovar. 409 se já há pedido pendente igual."""
    await _ensure(db)
    dia, funcao = await _checar_entrada(
        db, employee_id, condominio_id, funcao, data_inicio, motivo, solicitado_por, posto_id, coberto_employee_id
    )
    dup = (
        await db.execute(
            text(
                "SELECT 1 FROM op_movimentacao_pedidos WHERE status='pendente' AND employee_id=CAST(:e AS uuid) "
                "AND condominio_id=CAST(:c AS uuid) AND funcao=:f AND coalesce(posto_id::text,'')=:p"
            ),
            {"e": employee_id, "c": condominio_id, "f": funcao, "p": posto_id or ""},
        )
    ).scalar()
    if dup:
        raise MovimentacaoErro(409, "Já existe pedido pendente igual para esse colaborador.")
    pid = (
        await db.execute(
            text(
                "INSERT INTO op_movimentacao_pedidos (employee_id, condominio_id, posto_id, funcao, data_inicio, motivo, "
                " coberto_employee_id, solicitado_por, solicitante_nome, observacao, pedido_por) "
                "VALUES (CAST(:e AS uuid), CAST(:c AS uuid), CAST(:p AS uuid), :f, :d, :m, CAST(:cob AS uuid), :s, :sn, :obs, "
                " CAST(:u AS uuid)) RETURNING id::text"
            ),
            {
                "e": employee_id,
                "c": condominio_id,
                "p": posto_id or None,
                "f": funcao,
                "d": dia,
                "m": motivo,
                "cob": coberto_employee_id or None,
                "s": solicitado_por,
                "sn": (solicitante_nome or "").strip() or None,
                "obs": (observacao or "").strip() or None,
                "u": user_id or None,
            },
        )
    ).scalar()
    await db.commit()
    return {"id": pid, "status": "pendente", "data_inicio": dia.isoformat()}


async def _pedido_pendente(db, pedido_id: str):
    row = (
        await db.execute(
            text(f"SELECT {_CAMPOS_PEDIDO} FROM op_movimentacao_pedidos WHERE id = CAST(:i AS uuid)"), {"i": pedido_id}
        )
    ).fetchone()
    if not row:
        raise MovimentacaoErro(404, "Pedido não encontrado.")
    if row[10] != "pendente":
        raise MovimentacaoErro(409, f"Esse pedido já está {row[10]}.")
    return row


async def aprovar(db, *, pedido_id: str, user_id: str | None) -> dict:
    """Aprova = `alocar()` de hoje (encerra a anterior em D−1, restrição por cliente, 409 de duplicada).
    Se `alocar` recusar, o pedido fica pendente — nada muda."""
    await _ensure(db)
    r = await _pedido_pendente(db, pedido_id)
    res = await alocar(  # commita
        db,
        employee_id=r[0],
        condominio_id=r[1],
        funcao=r[3],
        posto_id=r[2],
        data_inicio=r[4],
        motivo=r[5],
        solicitado_por=r[7] or "supervisor",
        solicitante_nome=r[8],
        coberto_employee_id=r[6],
        observacao=r[9],
        user_id=user_id,
    )
    await db.execute(
        text(
            "UPDATE op_movimentacao_pedidos SET status='aprovada', decidido_por=CAST(:u AS uuid), "
            "decidido_em=(now() AT TIME ZONE 'America/Manaus'), alocacao_id=CAST(:a AS uuid) WHERE id = CAST(:i AS uuid)"
        ),
        {"u": user_id or None, "a": res["id"], "i": pedido_id},
    )
    await db.commit()
    return {"pedido_id": pedido_id, **res}


async def recusar(db, *, pedido_id: str, motivo: str, user_id: str | None) -> dict:
    """Recusa o pedido: só marca. `employee_alocacoes` fica exatamente como estava."""
    await _ensure(db)
    await _pedido_pendente(db, pedido_id)
    motivo = (motivo or "").strip()
    if len(motivo) < 3:
        raise MovimentacaoErro(400, "Diga por que está recusando (mínimo 3 caracteres).")
    await db.execute(
        text(
            "UPDATE op_movimentacao_pedidos SET status='recusada', decidido_por=CAST(:u AS uuid), "
            "decidido_em=(now() AT TIME ZONE 'America/Manaus'), decisao_motivo=:m WHERE id = CAST(:i AS uuid)"
        ),
        {"u": user_id or None, "m": motivo, "i": pedido_id},
    )
    await db.commit()
    return {"pedido_id": pedido_id, "status": "recusada"}
