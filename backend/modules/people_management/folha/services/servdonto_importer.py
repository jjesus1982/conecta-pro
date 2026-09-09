"""Relatório Servdonto (plano odontológico) → cadastro do desconto em folha (09/09/2026).

Regra da Pyetra: "Plano odontológico é descontado R$ 8,50; R$ 17,00 se houver dependente. Posso lhe enviar o
relatório de funcionários que têm o desconto pelo plano odontológico."

O relatório (.xls) lista um bloco por TITULAR: linha de cabeçalho "<CPF> - <NOME>", depois uma linha por pessoa do
plano com o parentesco (TITULAR, FILHO, CONJUGE/COMPANHEIRO, AGREGADOS/OUTROS). Medido no arquivo de 26/08/2026:
37 titulares, 43 pessoas, 4 titulares com dependente.

O que grava:
    employees.plano_odonto_ativo        = está no plano (o relatório É a lista de quem paga)
    employees.plano_odonto_dependentes  = nº de pessoas do plano além do titular → o motor desconta 17,00
    Quem NÃO está no relatório fica com ativo=false e não tem desconto nenhum. Medido em 09/09: descontávamos de
    todos os 53 CLT ativos, e o plano tem 37 titulares — 16 pessoas levavam um desconto que não existe.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

RE_TITULAR = re.compile(r"^(\d{3}\.\d{3}\.\d{3}-\d{2})\s*-\s*(.+)$")


def _dig(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


@dataclass
class TitularOdonto:
    cpf: str
    nome: str
    dependentes: list[tuple[str, str]] = field(default_factory=list)  # (parentesco, nome)


def ler_relatorio(caminho: str) -> list[TitularOdonto]:
    """Aceita .xls (xlrd), .xlsx (openpyxl) e .csv — o container não tem xlrd, então o .xls antigo é convertido
    para CSV antes (o próprio importador faz isso quando roda no host; ver scripts/importar_servdonto.sh)."""
    import pandas as pd

    if caminho.lower().endswith(".csv"):
        df = pd.read_csv(caminho, header=None, dtype=str, keep_default_na=False)
    else:
        df = pd.read_excel(caminho, header=None)
    out: list[TitularOdonto] = []
    atual: TitularOdonto | None = None
    for _, r in df.iterrows():
        col0 = str(r[0]) if r[0] == r[0] and r[0] is not None else ""
        m = RE_TITULAR.match(col0.strip())
        if m:
            atual = TitularOdonto(cpf=_dig(m.group(1)), nome=m.group(2).strip())
            out.append(atual)
            continue
        parentesco = str(r[2]).strip() if len(r) > 2 and r[2] == r[2] and r[2] is not None else ""
        if atual and parentesco and parentesco.upper() not in ("PARENTESCO", "TITULAR", "NAN"):
            atual.dependentes.append((parentesco, col0.strip()))
    return out


async def importar(db, caminho: str, aplicar: bool = False, zerar_ausentes: bool = True) -> dict:
    """Casa por CPF. `zerar_ausentes`: quem não está no relatório perde o desconto (é o que o relatório significa)."""
    from sqlalchemy import text as sql

    titulares = ler_relatorio(caminho)
    rel: dict = {"no_relatorio": len(titulares), "com_dependente": sum(1 for t in titulares if t.dependentes),
                 "casados": 0, "sem_cadastro": [], "mudancas": [], "zerados": [], "aplicado": aplicar}
    cpfs_no_relatorio: list[str] = []
    for t in titulares:
        row = (await db.execute(sql(
            "SELECT id::text, nome, coalesce(plano_odonto_dependentes, 0), coalesce(plano_odonto_ativo, false) FROM employees "
            "WHERE regexp_replace(coalesce(cpf,''),'[^0-9]','','g') = :c LIMIT 1"), {"c": t.cpf})).first()
        if not row:
            rel["sem_cadastro"].append(f"{t.nome} (CPF …{t.cpf[-4:]})")
            continue
        rel["casados"] += 1
        cpfs_no_relatorio.append(t.cpf)
        n = len(t.dependentes)
        if int(row[2] or 0) != n or not bool(row[3]):
            rel["mudancas"].append(f"{row[1]}: {int(row[2] or 0)} → {n} dependente(s) — desconto R$ {'17,00' if n else '8,50'}")
            if aplicar:
                await db.execute(sql("UPDATE employees SET plano_odonto_dependentes = :n, plano_odonto_ativo = true, "
                                     "updated_at = now() WHERE id = CAST(:e AS uuid)"), {"n": n, "e": row[0]})
    if zerar_ausentes and cpfs_no_relatorio:
        fora = (await db.execute(sql(
            "SELECT id::text, nome FROM employees WHERE (coalesce(plano_odonto_dependentes,0) > 0 OR coalesce(plano_odonto_ativo,false)) "
            "AND regexp_replace(coalesce(cpf,''),'[^0-9]','','g') <> ALL(:c)"), {"c": cpfs_no_relatorio})).fetchall()
        for eid, nome in fora:
            rel["zerados"].append(nome)
            if aplicar:
                await db.execute(sql("UPDATE employees SET plano_odonto_dependentes = 0, plano_odonto_ativo = false, "
                                     "updated_at = now() WHERE id = CAST(:e AS uuid)"), {"e": eid})
    if aplicar:
        await db.commit()
    logger.info("Servdonto: %s", {k: (len(v) if isinstance(v, list) else v) for k, v in rel.items()})
    return rel
