"""Fila de falhas de importação do DP — DGX V4 (24/09/2026), lacuna #8 de `docs/dgx/lacunas/dp_rh.md`.

Por que existe: os quatro importadores do DP devolviam o erro SÓ no JSON da resposta HTTP
(`import-cadastro`: no máximo 20 CPFs «não encontrados»; `sync-solides`: `erros[]`; a folha
analítica da Portte: `sem_cadastro[]`; o AFD de relógio: `erros` num log que ninguém abre).
Quem fecha a aba perde a lista — e a linha que não entrou fica sem dono. Na DGX isso é uma
TELA (`/view/falhasImportacaoEmpregados`), com Não resolvido / Resolvido (incluído manualmente).

O padrão de log por importação é o do T2 (`ponto_integracoes_batimentos`): resumo por execução
com `erros jsonb`. Aqui é o complemento: uma linha por FALHA, com dono, estado e ação.

Idempotência: chave (origem, identificador_origem, motivo). Rerodar a mesma importação com o
mesmo problema atualiza `executada_em` e NÃO cria linha nova — senão a fila viraria um diário
de 500 linhas iguais e ninguém a leria (foi o que aconteceu com o log de batimentos ad hoc).
Resolver/ignorar NÃO apaga: a chave continua lá, e um problema que voltou depois de resolvido
reaparece como `nao_resolvido` (o UPDATE do ON CONFLICT reabre) — é a informação que importa.

Sessão síncrona: `registrar_sync`/`_ensure_sync` existem porque o caminho da folha
(`rd_action_folha_apontamento`, eventos coletivos) roda em sessão SÍNCRONA. Mesmo SQL,
montado uma vez em `_insert()`.
"""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy import text

logger = logging.getLogger(__name__)

ORIGENS = ("solides", "portte", "planilha", "afd", "outro")
STATUS = ("nao_resolvido", "resolvido_manual", "ignorado")

_DDL = (
    "CREATE TABLE IF NOT EXISTS dp_importacao_falhas ("
    " id serial PRIMARY KEY,"
    " origem varchar(20) NOT NULL,"
    " executada_em timestamptz NOT NULL DEFAULT now(),"
    " identificador_origem varchar(160) NOT NULL DEFAULT '',"
    " nome varchar(200), matricula varchar(40), cpf varchar(20),"
    " motivo text NOT NULL,"
    " dados jsonb,"
    " status varchar(20) NOT NULL DEFAULT 'nao_resolvido',"
    " resolvido_por varchar(120), resolvido_em timestamptz,"
    " employee_id uuid,"
    " created_at timestamptz NOT NULL DEFAULT now())",
    # A chave da idempotência. `motivo` é text (pode passar de 2704 bytes no índice btree),
    # então entra por md5 — o ON CONFLICT abaixo repete a MESMA expressão.
    "CREATE UNIQUE INDEX IF NOT EXISTS dp_importacao_falhas_chave "
    "ON dp_importacao_falhas (origem, identificador_origem, md5(motivo))",
    "CREATE INDEX IF NOT EXISTS dp_importacao_falhas_status ON dp_importacao_falhas (status, origem)",
)

_SQL_INSERT = (
    "INSERT INTO dp_importacao_falhas (origem, identificador_origem, nome, matricula, cpf, motivo, dados, executada_em) "
    "VALUES (:origem, :ident, :nome, :matricula, :cpf, :motivo, CAST(:dados AS jsonb), now()) "
    "ON CONFLICT (origem, identificador_origem, md5(motivo)) DO UPDATE SET "
    " executada_em = now(), "
    " nome = coalesce(EXCLUDED.nome, dp_importacao_falhas.nome), "
    " matricula = coalesce(EXCLUDED.matricula, dp_importacao_falhas.matricula), "
    " cpf = coalesce(EXCLUDED.cpf, dp_importacao_falhas.cpf), "
    " dados = coalesce(EXCLUDED.dados, dp_importacao_falhas.dados), "
    # Voltou a falhar depois de alguém marcar resolvido? Então não estava resolvido.
    " status = CASE WHEN dp_importacao_falhas.status = 'ignorado' THEN 'ignorado' ELSE 'nao_resolvido' END "
    "RETURNING id"
)

_ensured = False


def _params(origem: str, identificador, motivo: str, nome=None, matricula=None, cpf=None, dados=None) -> dict:
    o = (origem or "outro").strip().lower()
    return {
        "origem": o if o in ORIGENS else "outro",
        "ident": str(identificador or "")[:160],
        "nome": (str(nome)[:200] if nome else None),
        "matricula": (str(matricula)[:40] if matricula else None),
        "cpf": (re.sub(r"\D", "", str(cpf))[:20] or None if cpf else None),
        "motivo": (str(motivo or "sem motivo informado").strip())[:2000],
        "dados": (json.dumps(dados, ensure_ascii=False, default=str) if dados else None),
    }


async def _ensure(db) -> None:
    global _ensured  # noqa: PLW0603
    if _ensured:
        return
    for stmt in _DDL:
        await db.execute(text(stmt))
    await db.commit()
    _ensured = True


def _ensure_sync(sdb) -> None:
    global _ensured  # noqa: PLW0603
    if _ensured:
        return
    for stmt in _DDL:
        sdb.execute(text(stmt))
    sdb.commit()
    _ensured = True


async def registrar(db, origem: str, identificador, motivo: str, **kw) -> int | None:
    """Grava (ou reabre) UMA falha. NÃO commita — quem chama já commita o resto da importação.

    Nunca levanta: uma falha de LOG não pode derrubar a importação que ela estava registrando.
    """
    try:
        await _ensure(db)
        return (await db.execute(text(_SQL_INSERT), _params(origem, identificador, motivo, **kw))).scalar()
    except Exception as exc:  # noqa: BLE001
        logger.warning("dp_importacao_falhas: não gravei a falha %s/%s: %s", origem, identificador, exc)
        return None


def registrar_sync(sdb, origem: str, identificador, motivo: str, **kw) -> int | None:
    """Versão de sessão SÍNCRONA (caminho da folha)."""
    try:
        _ensure_sync(sdb)
        return sdb.execute(text(_SQL_INSERT), _params(origem, identificador, motivo, **kw)).scalar()
    except Exception as exc:  # noqa: BLE001
        logger.warning("dp_importacao_falhas: não gravei a falha %s/%s: %s", origem, identificador, exc)
        return None


async def resolver(db, falha_id: int, quem: str, employee_id: str | None = None) -> dict:
    """Resolve: liga a um colaborador existente OU marca «incluído manualmente» (sem id).

    O `employee_id` só é aceito se existir de verdade em `employees` — ligar a fila a um id
    inventado seria pior que deixá-la aberta.
    """
    if employee_id:
        ok = (
            await db.execute(text("SELECT 1 FROM employees WHERE CAST(id AS text) = :e"), {"e": str(employee_id)})
        ).first()
        if not ok:
            raise ValueError("Colaborador não encontrado — escolha um da lista ou resolva sem ligar.")
    r = (
        await db.execute(
            text(
                "UPDATE dp_importacao_falhas SET status = 'resolvido_manual', resolvido_por = :q, resolvido_em = now(), "
                "employee_id = CASE WHEN :e = '' THEN employee_id ELSE CAST(:e AS uuid) END "
                "WHERE id = :i RETURNING origem, identificador_origem, coalesce(nome,'')"
            ),
            {"i": int(falha_id), "q": (quem or "")[:120], "e": str(employee_id or "")},
        )
    ).first()
    if not r:
        raise ValueError("Falha não encontrada.")
    await db.commit()
    return {
        "id": int(falha_id),
        "origem": r[0],
        "identificador": r[1],
        "nome": r[2],
        "employee_id": employee_id or None,
    }


async def ignorar(db, falha_id: int, motivo: str, quem: str) -> dict:
    """Ignora com motivo (mín. 5 caracteres) — o motivo fica em `dados.ignorado_porque`."""
    motivo = (motivo or "").strip()
    if len(motivo) < 5:
        raise ValueError("Diga por que está ignorando (mín. 5 caracteres) — fila sem motivo vira lixo.")
    r = (
        await db.execute(
            text(
                "UPDATE dp_importacao_falhas SET status = 'ignorado', resolvido_por = :q, resolvido_em = now(), "
                "dados = coalesce(dados, '{}'::jsonb) || jsonb_build_object('ignorado_porque', CAST(:m AS text)) "
                "WHERE id = :i RETURNING origem, identificador_origem"
            ),
            {"i": int(falha_id), "q": (quem or "")[:120], "m": motivo[:500]},
        )
    ).first()
    if not r:
        raise ValueError("Falha não encontrada.")
    await db.commit()
    return {"id": int(falha_id), "origem": r[0], "identificador": r[1], "motivo": motivo}
