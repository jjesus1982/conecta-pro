"""Importar apontamentos da folha em CSV — DGX V4 (24/09/2026), item 56 de `docs/dgx/lacunas/ponto.md`.

Na DGX, `/Apontamentos/Lote/{id}` tem **Importar** (CSV `Matrícula, Valor, Referência[, Evento]`).
Aqui havia o evento coletivo (F6) — que aplica UMA rubrica a um filtro de gente — e nada para o
caso oposto: a planilha com N linhas heterogêneas que o supervisor manda no fim do mês.

CAMINHO DE DINHEIRO — PARALELO CEGO. Este importador **não altera nenhum valor calculado**.
Cada linha válida vira um APONTAMENTO no holerite rascunho, exatamente como `folha-apontamento`
(`hr_payslips.contest_reason` + `contested_at`) e como o evento coletivo da F6, que também passa
por lá. Quem fecha a folha lê o apontamento e decide. Trocar isso por uma escrita direta em
rubrica exigiria um oráculo de igualdade contra o motor atual — não é esta frente.

Formato: `matricula;rubrica;referencia;valor;competencia` (cabeçalho opcional; aceita `;` ou `,`
e decimal com vírgula). Validações: matrícula de colaborador com vínculo vivo, rubrica ATIVA em
`rubricas_folha`, competência coerente e SEM folha publicada (409 — depois de publicada o
apontamento chega tarde, é a mesma parede da F6). Erro de linha vai para a fila
`dp_importacao_falhas` com origem `planilha` (chave origem+identificador+motivo: reimportar a
mesma planilha com os mesmos erros não duplica a fila).

Sessão SÍNCRONA do começo ao fim, porque `rd_action_folha_apontamento` roda sobre
`get_sync_db_dependency` — a função aqui é `async def` só para poder aguardá-la (mesma forma
da `aplicar_evento` da F6).
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import text

from modules.people_management.hr.services import importacao_falhas as falhas

logger = logging.getLogger(__name__)

CABECALHO = ("matricula", "rubrica", "referencia", "valor", "competencia")
ORIGEM = "planilha"


def _num(v: str) -> Decimal | None:
    s = re.sub(r"[^\d,.-]", "", str(v or "")).strip()
    if not s:
        return None
    # 1.234,56 (BR) e 1234.56 (ISO) — quem manda a planilha alterna entre os dois.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def competencia(v: str) -> date | None:
    """MM/AAAA, AAAA-MM ou MM-AAAA → 1º dia do mês."""
    d = re.findall(r"\d+", str(v or ""))
    if len(d) < 2:
        return None
    a, b = int(d[0]), int(d[1])
    mes, ano = (a, b) if a <= 12 and b > 12 else (b, a)
    if not (1 <= mes <= 12 and 2000 <= ano <= 2100):
        return None
    return date(ano, mes, 1)


def parse(conteudo: str) -> tuple[list[dict], list[dict]]:
    """→ (linhas lidas, erros de forma). Cada linha ganha `n` (número no arquivo, 1-based)."""
    amostra = conteudo[:4096]
    sep = ";" if amostra.count(";") >= amostra.count(",") else ","
    linhas, erros = [], []
    for n, campos in enumerate(csv.reader(io.StringIO(conteudo), delimiter=sep), start=1):
        campos = [c.strip() for c in campos if c is not None]
        if not any(campos):
            continue
        if n == 1 and campos and campos[0].strip().lower().lstrip("﻿").startswith("matr"):
            continue  # cabeçalho
        if len(campos) < 5:
            erros.append(
                {
                    "n": n,
                    "erro": f"linha com {len(campos)} coluna(s); esperado 5 ({';'.join(CABECALHO)})",
                    "bruto": (sep.join(campos))[:160],
                }
            )
            continue
        linhas.append(
            {
                "n": n,
                "matricula": campos[0],
                "rubrica": campos[1],
                "referencia": campos[2],
                "valor": campos[3],
                "competencia": campos[4],
                "bruto": sep.join(campos[:5])[:160],
            }
        )
    return linhas, erros


def _pessoas(sdb) -> dict[str, tuple[str, str]]:
    from modules.integrations.connectors.whatsapp.identidade import SEM_VINCULO

    rows = sdb.execute(
        text(
            "SELECT coalesce(matricula,''), CAST(id AS text), nome FROM employees "
            "WHERE coalesce(matricula,'') <> '' AND lower(coalesce(status,'')) <> ALL(:sem) "
            "AND lower(coalesce(status,'')) <> 'demitido' AND coalesce(is_homologacao,false) = false"
        ),
        {"sem": list(SEM_VINCULO)},
    ).fetchall()
    # A matrícula chega com e sem zeros à esquerda ("07" e "7" são a mesma pessoa na planilha).
    idx: dict[str, tuple[str, str]] = {}
    for mat, eid, nome in rows:
        for k in {mat.strip(), mat.strip().lstrip("0")}:
            if k:
                idx.setdefault(k, (eid, nome))
    return idx


def _rubricas(sdb) -> dict[str, str]:
    rows = sdb.execute(text("SELECT codigo, descricao FROM rubricas_folha WHERE ativo")).fetchall()
    idx: dict[str, str] = {}
    for cod, desc in rows:
        for k in {str(cod).strip(), str(cod).strip().lstrip("0")}:
            if k:
                idx.setdefault(k, desc or "")
    return idx


async def importar(sdb, conteudo: str, quem: str, arquivo: str = "", simular: bool = False, current_user=None) -> dict:
    """Valida tudo, e só então grava (a menos de `simular`). Devolve a prévia sempre.

    `async` com sessão SÍNCRONA: é a mesma forma de `_dgx_f6_dp.aplicar_evento`, porque a ação
    reusada (`rd_action_folha_apontamento`) é `async def` sobre `get_sync_db_dependency`."""
    falhas._ensure_sync(sdb)
    linhas, erros_forma = parse(conteudo)
    if not linhas and not erros_forma:
        raise HTTPException(status_code=400, detail="Arquivo sem linha nenhuma.")

    # Competência: a planilha inteira precisa falar de uma competência que ainda aceita apontamento.
    comps = {c for c in (competencia(li["competencia"]) for li in linhas) if c}
    for c in sorted(comps):
        publicadas = sdb.execute(
            text(
                "SELECT count(*) FROM hr_payslips WHERE reference_year = :a AND reference_month = :m "
                "AND status::text = 'published'"
            ),
            {"a": c.year, "m": c.month},
        ).scalar()
        if publicadas:
            raise HTTPException(
                status_code=409,
                detail=f"Competência {c.strftime('%m/%Y')} tem folha PUBLICADA ({publicadas} holerite(s)) — "
                "apontamento só antes de publicar. Reabra a folha ou use a competência aberta.",
            )

    pessoas, rubricas = _pessoas(sdb), _rubricas(sdb)
    validas: list[dict] = []
    recusadas: list[dict] = []

    def recusa(li: dict, motivo: str) -> None:
        recusadas.append({"n": li.get("n"), "motivo": motivo, "bruto": li.get("bruto", "")})

    for e in erros_forma:
        recusa(e, e["erro"])
    for li in linhas:
        mat = li["matricula"].strip()
        pessoa = pessoas.get(mat) or pessoas.get(mat.lstrip("0"))
        if not pessoa:
            recusa(li, f"matrícula {mat or '(vazia)'} sem colaborador com vínculo ativo")
            continue
        cod = li["rubrica"].strip()
        desc = rubricas.get(cod) if cod in rubricas else rubricas.get(cod.lstrip("0"))
        if desc is None:
            recusa(li, f"rubrica {cod or '(vazia)'} não existe ou está inativa em rubricas_folha")
            continue
        valor = _num(li["valor"])
        if valor is None:
            recusa(li, f"valor «{li['valor']}» não é número")
            continue
        comp = competencia(li["competencia"])
        if not comp:
            recusa(li, f"competência «{li['competencia']}» inválida (use MM/AAAA)")
            continue
        validas.append(
            dict(li, employee_id=pessoa[0], nome=pessoa[1], rubrica_desc=desc, valor_num=valor, comp=comp, codigo=cod)
        )

    # Agrupa por (pessoa, competência): um apontamento por holerite, com todas as rubricas da
    # planilha daquela pessoa. `contest_reason` é UM campo de texto — N chamadas sobrescreveriam.
    por_folha: dict[tuple[str, date], list[dict]] = {}
    for v in validas:
        por_folha.setdefault((v["employee_id"], v["comp"]), []).append(v)

    aplicados, sem_folha, ja_apontada = 0, [], []
    if not simular:
        from modules.operacional.controllers.redesign_builders.departamento_pessoal import (  # lazy: ciclo de import
            rd_action_folha_apontamento,
        )

        for (eid, comp), itens in por_folha.items():
            ps = sdb.execute(
                text(
                    "SELECT id::text, contest_reason FROM hr_payslips WHERE employee_id::text = :e "
                    "AND reference_year = :a AND reference_month = :m AND status::text = 'draft' "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"e": eid, "a": comp.year, "m": comp.month},
            ).first()
            nome = itens[0]["nome"]
            if not ps:
                sem_folha.append(nome)
                for it in itens:
                    falhas.registrar_sync(
                        sdb,
                        ORIGEM,
                        f"{arquivo or 'csv'}:{it['n']}",
                        f"{nome} não tem holerite RASCUNHO em {comp.strftime('%m/%Y')} — gere a folha antes",
                        nome=nome,
                        matricula=it["matricula"],
                        dados=it["bruto"] and {"linha": it["bruto"]},
                    )
                continue
            if ps[1]:
                ja_apontada.append(nome)
                for it in itens:
                    falhas.registrar_sync(
                        sdb,
                        ORIGEM,
                        f"{arquivo or 'csv'}:{it['n']}",
                        f"{nome}: holerite de {comp.strftime('%m/%Y')} já tem apontamento de outra origem "
                        "(não sobrescrevo o de ninguém)",
                        nome=nome,
                        matricula=it["matricula"],
                        dados=it["bruto"] and {"linha": it["bruto"]},
                    )
                continue
            detalhe = "; ".join(
                f"{it['codigo']} {it['rubrica_desc']}"
                + (f" ref {it['referencia']}" if it["referencia"] else "")
                + f" = {it['valor_num']}"
                for it in itens
            )
            motivo = f"[importação CSV {arquivo or 'planilha'}] {detalhe}"
            await rd_action_folha_apontamento(current_user, {"payslip_id": ps[0], "motivo": motivo}, sdb)
            aplicados += 1

    # «Só validar» NÃO escreve nada — nem na fila. Uma prévia que diz «nada gravado» e mesmo
    # assim deixa 2 pendências para alguém resolver é um verde cego (medido em 24/09, por HTTP).
    if not simular:
        for r in recusadas:
            falhas.registrar_sync(
                sdb,
                ORIGEM,
                f"{arquivo or 'csv'}:{r['n']}",
                r["motivo"],
                dados={"linha": r["bruto"]} if r["bruto"] else None,
            )
        sdb.commit()
    else:
        sdb.rollback()
    return {
        "simulacao": bool(simular),
        "arquivo": arquivo or "",
        "linhas": len(linhas) + len(erros_forma),
        "validas": len(validas),
        "recusadas": len(recusadas),
        "apontamentos": aplicados,
        "holerites_alvo": len(por_folha),
        "sem_folha_rascunho": sem_folha,
        "ja_apontada": ja_apontada,
        "erros": recusadas[:200],
        "quem": quem,
    }
