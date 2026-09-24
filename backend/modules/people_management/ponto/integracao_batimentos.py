"""Integração de batimentos — arquivo AFD de relógio (REP-C/REP-A/terceiro) → `gp_clock_punches`
(DGX T2, 24/09/2026).

Por que existe: `POST /hr/rep/afd/import` gravava só `afd_records` (arquivo fiscal) — nenhuma
marcação virava batida, logo nada entrava no espelho. O único caminho de relógio de terceiro
era importador ad hoc (Tangerino: 6.621 batidas, 1.375 jornadas duplicadas em 11/09). Na DGX o
arquivo do aparelho entra por `arquivosrelogioponto/upload` e cada marcação vira batida do cartão.

Aqui: parser dos DOIS leiautes (Portaria 1510: `NSR(9) tipo(1) DDMMAAAA HHMM PIS(12)`; Portaria
671 v004: `NSR(9) tipo(1) ISO-8601±HHMM(24) CPF(12)`), tipos 3 (REP-C/A) e 7 (REP-P); pessoa por
CPF ou PIS; `chave_idempotente = afd:<origem>:<nsr>` (índice único da tabela) — importar duas
vezes não duplica; entrada/saída alternadas por pessoa-dia contando o que já existe no dia;
competência fechada recusa (fechamento.py); `device_type='relogio'` = fonte MEDIDA no espelho.
Modo «só validar» não grava batida, só o log.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import text

from modules.people_management.ponto import fechamento

TZ = ZoneInfo("America/Manaus")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4}$")
_TIPOS_MARCACAO = ("3", "7")
DEVICE_TYPE = "relogio"

_DDL = (
    "CREATE TABLE IF NOT EXISTS ponto_integracoes_batimentos ("
    " id serial PRIMARY KEY, origem varchar(80) NOT NULL, arquivo varchar(200), simulacao boolean NOT NULL DEFAULT false,"
    " linhas integer NOT NULL DEFAULT 0, marcacoes integer NOT NULL DEFAULT 0, importadas integer NOT NULL DEFAULT 0,"
    " duplicadas integer NOT NULL DEFAULT 0, sem_pessoa integer NOT NULL DEFAULT 0, mes_fechado integer NOT NULL DEFAULT 0,"
    " invalidas integer NOT NULL DEFAULT 0, erros jsonb, quem varchar(120), created_at timestamptz DEFAULT now())",
)
_ensured = False


async def _ensure(db) -> None:
    global _ensured  # noqa: PLW0603
    if _ensured:
        return
    for stmt in _DDL:
        await db.execute(text(stmt))
    await db.commit()
    _ensured = True


def _digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def parse_linha(linha: str) -> dict | None:
    """Uma linha do AFD → {nsr, tipo, ts (naive Manaus), doc, leiaute} ou {erro}. None = não é marcação."""
    linha = linha.rstrip("\r\n")
    if len(linha) < 10 or not linha[:9].isdigit():
        return {"erro": "NSR inválido", "linha": linha[:40]}
    tipo = linha[9]
    if tipo not in _TIPOS_MARCACAO:
        return None
    nsr = int(linha[:9])
    try:
        if len(linha) >= 46 and _ISO.match(linha[10:34]):
            ts = datetime.strptime(linha[10:34], "%Y-%m-%dT%H:%M:%S%z").astimezone(TZ).replace(tzinfo=None)
            doc = _digitos(linha[34:46])
            return {"nsr": nsr, "tipo": tipo, "ts": ts, "doc": doc[-11:], "leiaute": "671", "campo": "cpf"}
        if len(linha) >= 34 and linha[10:22].isdigit():
            ts = datetime.strptime(linha[10:22], "%d%m%Y%H%M")
            return {
                "nsr": nsr,
                "tipo": tipo,
                "ts": ts,
                "doc": _digitos(linha[22:34])[-11:],  # PIS: 12 posições no arquivo, 11 dígitos no cadastro
                "leiaute": "1510",
                "campo": "pis",
            }
    except ValueError as exc:
        return {"erro": f"data/hora inválida ({exc})", "nsr": nsr}
    return {"erro": "leiaute não reconhecido (nem 1510 nem 671)", "nsr": nsr}


def parse_arquivo(conteudo: str) -> tuple[list[dict], list[dict], int]:
    """→ (marcações válidas, erros de parse, total de linhas não vazias)."""
    ok, erros, n = [], [], 0
    for linha in conteudo.splitlines():
        if not linha.strip():
            continue
        n += 1
        r = parse_linha(linha)
        if r is None:
            continue
        (erros if "erro" in r else ok).append(r)
    return ok, erros, n


async def _pessoas(db) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    rows = (
        await db.execute(
            text("SELECT CAST(id AS text), coalesce(cpf,''), coalesce(pis,''), coalesce(nome,'') FROM employees")
        )
    ).fetchall()
    por_cpf: dict[str, tuple[str, str]] = {}
    por_pis: dict[str, tuple[str, str]] = {}
    for eid, cpf, pis, nome in rows:
        if _digitos(cpf):
            por_cpf[_digitos(cpf)[-11:]] = (eid, nome)
        if _digitos(pis):
            por_pis[_digitos(pis)[-11:]] = (eid, nome)
    return por_cpf, por_pis


async def importar(db, conteudo: str, origem: str, quem: str, simular: bool = False, arquivo: str = "") -> dict:
    """Importa (ou só valida) o AFD. Devolve o resumo gravado em `ponto_integracoes_batimentos`."""
    await _ensure(db)
    origem = re.sub(r"[^A-Za-z0-9_.:-]", "_", (origem or "").strip())[:60]
    if not origem:
        raise ValueError("Informe a origem (identificação do relógio) — ela entra na chave de idempotência.")
    marc, erros, n_linhas = parse_arquivo(conteudo)
    n_invalidas = len(erros)
    por_cpf, por_pis = await _pessoas(db)
    chaves = [f"afd:{origem}:{m['nsr']}" for m in marc]
    existentes: set[str] = set()
    if chaves:
        existentes = {
            r[0]
            for r in (
                await db.execute(
                    text("SELECT chave_idempotente FROM gp_clock_punches WHERE chave_idempotente = ANY(:c)"),
                    {"c": chaves},
                )
            ).fetchall()
        }
    contagem = {"importadas": 0, "duplicadas": 0, "sem_pessoa": 0, "mes_fechado": 0}
    fechado_cache: dict[tuple[str, int, int], str | None] = {}
    vistos: set[str] = set()
    a_inserir: list[dict] = []
    for m in sorted(marc, key=lambda x: (x["doc"], x["ts"], x["nsr"])):
        chave = f"afd:{origem}:{m['nsr']}"
        if chave in existentes or chave in vistos:
            contagem["duplicadas"] += 1
            continue
        vistos.add(chave)
        pessoa = por_cpf.get(m["doc"]) if m["campo"] == "cpf" else por_pis.get(m["doc"])
        if not pessoa:
            contagem["sem_pessoa"] += 1
            erros.append({"nsr": m["nsr"], "erro": f"{m['campo'].upper()} {m['doc']} sem colaborador"})
            continue
        eid, nome = pessoa
        k = (eid, m["ts"].year, m["ts"].month)
        if k not in fechado_cache:
            fechado_cache[k] = await fechamento.competencia_fechada(db, eid, m["ts"].date())
        if fechado_cache[k]:
            contagem["mes_fechado"] += 1
            erros.append({"nsr": m["nsr"], "erro": f"{nome}: {fechado_cache[k]}"})
            continue
        a_inserir.append(dict(m, chave=chave, eid=eid, nome=nome))
    # entrada/saída alternadas por pessoa-dia: conta o que já existe no dia e segue a sequência
    por_dia: dict[tuple[str, date], list[dict]] = defaultdict(list)
    for m in a_inserir:
        por_dia[(m["eid"], m["ts"].date())].append(m)
    agora = datetime.now()
    for (eid, dia), itens in por_dia.items():
        ja = (
            await db.execute(
                text(
                    "SELECT count(*) FROM gp_clock_punches WHERE CAST(employee_id AS text)=:e "
                    "AND punch_timestamp::date = :d AND coalesce(status,'') <> 'facial_reprovado'"
                ),
                {"e": eid, "d": dia},
            )
        ).scalar() or 0
        for i, m in enumerate(sorted(itens, key=lambda x: x["ts"])):
            m["punch_type"] = "entrada" if (int(ja) + i) % 2 == 0 else "saida"
    if not simular:
        for m in a_inserir:
            r = await db.execute(
                text(
                    "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, punch_timestamp, server_timestamp, "
                    "status, device_type, device_id, chave_idempotente, is_offline, sync_attempts, created_at, created_by) "
                    "VALUES (:pid, CAST(:e AS uuid), :pt, :ts, :now, 'normal', :dev, :did, :chave, false, 0, :now, :quem) "
                    "ON CONFLICT (chave_idempotente) DO NOTHING"
                ),
                {
                    "pid": str(uuid4()),
                    "e": m["eid"],
                    "pt": m["punch_type"],
                    "ts": m["ts"],
                    "now": agora,
                    "dev": DEVICE_TYPE,
                    "did": origem[:64],
                    "chave": m["chave"],
                    "quem": (quem or "")[:36],
                },
            )
            if r.rowcount:
                contagem["importadas"] += 1
            else:
                contagem["duplicadas"] += 1
    else:
        contagem["importadas"] = len(a_inserir)
    resumo = dict(
        contagem,
        origem=origem,
        arquivo=(arquivo or "")[:200],
        simulacao=bool(simular),
        linhas=n_linhas,
        marcacoes=len(marc),
        invalidas=n_invalidas,
        erros=erros[:200],
        quem=(quem or "")[:120],
    )
    rid = (
        await db.execute(
            text(
                "INSERT INTO ponto_integracoes_batimentos (origem, arquivo, simulacao, linhas, marcacoes, importadas, "
                "duplicadas, sem_pessoa, mes_fechado, invalidas, erros, quem) VALUES (:origem, :arquivo, :simulacao, "
                ":linhas, :marcacoes, :importadas, :duplicadas, :sem_pessoa, :mes_fechado, :invalidas, CAST(:erros AS jsonb), :quem) "
                "RETURNING id"
            ),
            dict(resumo, erros=json.dumps(resumo["erros"], ensure_ascii=False, default=str)),
        )
    ).scalar()
    # DGX V4: cada marcação recusada também vira pendência COM DONO na fila do DP
    # (`dp_importacao_falhas`, origem afd). O log acima é o resumo da execução; a fila é a
    # lista de trabalho — PIS/CPF sem colaborador é cadastro faltando, não ruído de arquivo.
    from modules.people_management.hr.services import importacao_falhas as _falhas

    for e in resumo["erros"]:
        await _falhas.registrar(
            db,
            "afd",
            f"{origem}:{e.get('nsr', e.get('linha', ''))}",
            str(e.get("erro", "erro não descrito")),
            dados={"arquivo": resumo["arquivo"], "importacao": rid},
        )
    await db.commit()
    resumo["id"] = rid
    resumo["pessoas"] = sorted({m["nome"] for m in a_inserir})
    return resumo
