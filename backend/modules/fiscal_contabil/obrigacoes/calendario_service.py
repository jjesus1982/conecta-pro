"""Calendário de obrigações fiscais que se sustenta sozinho.

O problema, medido em 11/08/2026: o único código que criava `fiscal_obligations` era o sync
de guias do Drive — ele lê o PDF da guia e cadastra a obrigação a partir dele. As guias
pararam de chegar (FGTS em 12.2025, INSS em 11.2025), então o calendário parou junto:

  2026-01  7 obrigações      2026-04  NÃO EXISTE
  2026-02  7 obrigações      2026-05  NÃO EXISTE
  2026-03  7 obrigações      2026-07  NÃO EXISTE
  2026-06  8 obrigações

No sistema inteiro havia UMA obrigação vencendo nos 30 dias seguintes. A competência 07
vencia dia 20 — nove dias depois — e ninguém era avisado.

A inversão que este serviço faz: **a obrigação existe por lei, não porque o PDF chegou.**
DCTFWeb vence dia 15 tendo guia ou não. Esperar o documento para lembrar do prazo é lembrar
depois do prazo.

O que ele NÃO faz, de propósito:
- **não inventa valor.** `valor_devido` fica nulo: o quanto sai da apuração, não do
  calendário. O que se cadastra é o PRAZO, que é o que faz falta.
- **não inventa quais obrigações a empresa tem.** O conjunto recorrente é lido da própria
  história dela (`_recorrentes`): repetir o que a empresa vem declarando é evidência;
  deduzir da legislação seria eu decidindo o enquadramento dela.

Idempotente por (empresa, tipo, competência) — rodar de novo não duplica.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from datetime import date

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Quantas competências fechadas olhar para trás ao descobrir o conjunto recorrente.
_JANELA_HISTORICO = 6

#: Tipo precisa ter aparecido em pelo menos tantas competências para contar como recorrente.
#: Com 2, um cadastro avulso de um mês só não vira obrigação mensal eterna.
_MIN_OCORRENCIAS = 2

_SQL_RECORRENTES = """
    SELECT o.tipo,
           max(o.nome)                                          AS nome,
           mode() WITHIN GROUP (ORDER BY extract(day FROM o.data_vencimento)::int) AS dia,
           count(DISTINCT (o.competencia_ano, o.competencia_mes))                  AS meses
      FROM fiscal_obligations o
     WHERE o.empresa_id = :emp
       AND o.competencia_mes BETWEEN 1 AND 12
       AND (o.competencia_ano * 12 + o.competencia_mes) >= :desde
     GROUP BY o.tipo
    HAVING count(DISTINCT (o.competencia_ano, o.competencia_mes)) >= :minimo
"""


def _venc(ano: int, mes: int, dia: int) -> date:
    """Vencimento = dia tal do mês SEGUINTE à competência (defasagem de 1, medida na base).

    `monthrange` porque dia 30 não existe em fevereiro — e um vencimento inválido
    derrubaria a geração inteira do mês.
    """
    a, m = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return date(a, m, min(dia, monthrange(a, m)[1]))


async def recorrentes(db, empresa_id: str, ate_ano: int, ate_mes: int) -> list[dict]:
    """Conjunto de obrigações que ESTA empresa vem declarando, com o dia de cada uma."""
    desde = (ate_ano * 12 + ate_mes) - _JANELA_HISTORICO
    rows = (await db.execute(text(_SQL_RECORRENTES),
                             {"emp": empresa_id, "desde": desde, "minimo": _MIN_OCORRENCIAS})).fetchall()
    return [{"tipo": r[0], "nome": r[1], "dia": int(r[2] or 20), "meses": r[3]} for r in rows]


async def primeira_atividade(db, empresa_id: str) -> int | None:
    """Índice (ano*12+mês) da primeira competência em que a empresa OPEROU.

    Sem isto o calendário retrocede alegremente para antes da empresa existir: no ensaio de
    11/08/2026 ele quis criar DAS de janeiro a maio para a Patrimonial, que só emitiu a
    primeira nota em 06/2026. Tributo de mês sem operação é obrigação inventada — o oposto
    do que este serviço existe para fazer.

    Evidência: nota emitida ou obrigação já declarada, o que vier primeiro.
    """
    r = (await db.execute(text(
        "SELECT least("
        "  coalesce((SELECT min(extract(year from data_emissao)*12 + extract(month from data_emissao))"
        "            FROM nfse_emitidas_nacional WHERE empresa_id = :e), 999999),"
        "  coalesce((SELECT min(competencia_ano*12 + competencia_mes) FROM fiscal_obligations"
        "            WHERE empresa_id = :e AND competencia_mes BETWEEN 1 AND 12), 999999))"),
        {"e": empresa_id})).scalar()
    return None if r is None or int(r) >= 999999 else int(r)


async def garantir_competencia(db, empresa_id: str, ano: int, mes: int,
                               aplicar: bool = False) -> dict:
    """Cria o que falta para uma competência. Devolve o que fez (ou faria)."""
    inicio = await primeira_atividade(db, empresa_id)
    if inicio is None or (ano * 12 + mes) < inicio:
        return {"empresa_id": empresa_id, "competencia": f"{mes:02d}/{ano}", "criadas": 0,
                "motivo": "competência anterior à primeira atividade da empresa"}
    tipos = await recorrentes(db, empresa_id, ano, mes)
    if not tipos:
        return {"empresa_id": empresa_id, "competencia": f"{mes:02d}/{ano}",
                "criadas": 0, "motivo": "empresa sem histórico recorrente — nada a repetir"}

    cond = (await db.execute(text(
        "SELECT condominio_id::text FROM fiscal_obligations WHERE empresa_id = :e "
        "ORDER BY created_at DESC LIMIT 1"), {"e": empresa_id})).scalar()
    if not cond:
        return {"empresa_id": empresa_id, "competencia": f"{mes:02d}/{ano}",
                "criadas": 0, "motivo": "sem condominio_id de referência"}

    criadas = []
    for t in tipos:
        ja = (await db.execute(text(
            "SELECT 1 FROM fiscal_obligations WHERE empresa_id = :e AND tipo = :t "
            "AND competencia_ano = :a AND competencia_mes = :m LIMIT 1"),
            {"e": empresa_id, "t": t["tipo"], "a": ano, "m": mes})).first()
        if ja:
            continue
        venc = _venc(ano, mes, t["dia"])
        if aplicar:
            await db.execute(text(
                "INSERT INTO fiscal_obligations "
                "(id, condominio_id, empresa_id, tipo, nome, descricao, status, "
                " competencia_mes, competencia_ano, data_vencimento, observacoes, active, "
                " created_at, updated_at) "
                "VALUES (gen_random_uuid(), :cond, :emp, :tipo, :nome, :desc, 'pendente', "
                "        :mes, :ano, :venc, :obs, true, NOW(), NOW())"),
                {"cond": cond, "emp": empresa_id, "tipo": t["tipo"], "nome": t["nome"],
                 "desc": f"Competência {mes:02d}/{ano}",
                 "mes": mes, "ano": ano, "venc": venc,
                 "obs": (f"Prazo gerado pelo calendário recorrente (a empresa declarou este "
                         f"tributo em {t['meses']} das últimas competências). VALOR NAO "
                         f"PREENCHIDO: sai da apuração, não do calendário.")})
        criadas.append({"tipo": t["tipo"], "vencimento": venc.isoformat()})
    return {"empresa_id": empresa_id, "competencia": f"{mes:02d}/{ano}",
            "criadas": len(criadas), "detalhe": criadas}


async def garantir_ate_hoje(db, hoje: date, meses_atras: int = 6,
                            aplicar: bool = False) -> dict:
    """Fecha o calendário de todas as empresas até a última competência ENCERRADA.

    A competência do mês corrente não entra: ela ainda não fechou, e criar obrigação de mês
    aberto encheria a tela de prazo que ainda não existe.
    """
    empresas = [r[0] for r in (await db.execute(text(
        "SELECT id::text FROM empresas ORDER BY coalesce(nome_fantasia, razao_social)"))).fetchall()]
    ult_ano, ult_mes = (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)
    base = ult_ano * 12 + ult_mes

    resultados, total = [], 0
    for emp in empresas:
        for passo in range(meses_atras):
            idx = base - passo
            ano, mes = divmod(idx - 1, 12)
            mes += 1
            r = await garantir_competencia(db, emp, ano, mes, aplicar=aplicar)
            total += r["criadas"]
            if r["criadas"]:
                resultados.append(r)
    if aplicar:
        await db.commit()
    logger.info("[calendario] %s obrigação(ões) %s", total, "criadas" if aplicar else "faltando")
    return {"total": total, "aplicado": aplicar, "competencias": resultados}


if __name__ == "__main__":
    # Self-check sem banco: a data de vencimento é onde um erro passa despercebido.
    assert _venc(2026, 7, 20) == date(2026, 8, 20), "competência 07 vence em agosto"
    assert _venc(2026, 12, 15) == date(2027, 1, 15), "dezembro vira janeiro do ano seguinte"
    assert _venc(2026, 1, 31) == date(2026, 2, 28), "dia 31 em fevereiro cai no último dia"
    assert _venc(2028, 1, 31) == date(2028, 2, 29), "ano bissexto"
    print("self-check OK")
