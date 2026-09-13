"""Oráculo — Mapa de férias por idade do período aquisitivo (frente 08, 12/09/2026).

Por que existe: o painel de risco de férias da DGX (faixas <12 · 12–16 · 17–19 · 20–22 · >22
meses) é o que mostra quem está perto de virar pagamento em DOBRA (art. 137 CLT). O pré-mortem
listou quatro jeitos de esse mapa mentir: âncora presa na admissão quando um afastamento
previdenciário > 6 meses reiniciou a contagem (art. 133 IV e §2º CLT); faixa `>22` vazia por não
ter sido calculada; `x or default` engolindo idade 0; e gente com menos de 12 meses de casa
contada como risco.

O que afirma:
  1. A tela `mapa-ferias` existe no builder do DP e está fiada no `build()`.
  2. Soma das faixas + "em aquisição" + "afastado > 6 meses" + "não calculado" == total de ativos
     COM VÍNCULO (régua: `identidade.SEM_VINCULO` + demitido, sem homologação, sem PJ), contado
     por SQL próprio deste oráculo — não pelo serviço.
  3. Nenhuma faixa nasce de default: idade 0 é "em aquisição", idade None é "não calculado", quem
     não tem admissão fica em "não calculado", e o fonte do serviço não tem `or <número>`.
  4. CONTRA-PROVA da âncora: (a) função pura com afastamento longo devolve o RETORNO, com
     afastamento curto devolve a admissão; (b) para cada pessoa do mapa, a âncora bate com a
     recalculada por SQL direto em `sst_afastamentos` — se o serviço deixar a âncora na
     admissão, este item acusa.

Estado medido no nascimento (staging, 12/09/2026): serviço e tela não existiam → VERMELHO em
tudo. No staging há um afastamento de fixture (EDWARD, doença 10/01/2025 → 20/08/2025,
observacoes = 'FIXTURE FRENTE 08') para o item 4b ter caso de banco.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import inspect
import re
import sys
from datetime import date

#: Mesma régua do serviço, escrita de novo aqui de propósito: o oráculo confere a régua, não a copia.
SQL_TOTAL_COM_VINCULO = """
SELECT count(*) FROM employees e
WHERE e.status <> ALL(:sem) AND e.status <> 'demitido'
  AND coalesce(e.is_homologacao,false) = false
  AND coalesce(e.tipo_contrato,'') NOT ILIKE '%pj%'
"""

#: Âncora recalculada por SQL: maior entre admissão e retorno de afastamento previdenciário
#: (doença/acidente) que durou mais de 6 meses. Independente do serviço.
SQL_ANCORA = """
SELECT e.id::text, e.data_admissao,
       (SELECT max(a.data_retorno) FROM sst_afastamentos a
         WHERE a.employee_id = e.id AND a.data_retorno IS NOT NULL
           AND (a.tipo ILIKE '%doenca%' OR a.tipo ILIKE '%acidente%')
           AND a.data_retorno > a.data_inicio + interval '6 months')
FROM employees e
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    # 1) serviço + tela + fiação
    try:
        from modules.people_management.hr.services import mapa_ferias as mf
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: serviço hr/services/mapa_ferias.py não importa: {e}")
        return 1
    try:
        from modules.operacional.controllers.redesign_builders import _frente_08 as f8
        from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: builder _frente_08 não importa: {e}")
        return 1
    if "_telas_08" not in inspect.getsource(dp.build):
        falhas.append("departamento_pessoal.build() não chama _frente_08.telas — a tela existe e ninguém a monta")

    # 3a) sem default — comportamento
    if mf.faixa(0) != mf.EM_AQUISICAO:
        falhas.append(f"faixa(0) devolveu {mf.faixa(0)!r} — idade 0 tem de ser 'em aquisição'")
    if mf.faixa(None) != mf.NAO_CALCULADO:
        falhas.append(f"faixa(None) devolveu {mf.faixa(None)!r} — sem idade é 'não calculado'")
    if mf.faixa(11) != mf.EM_AQUISICAO or mf.faixa(12) != "12–16" or mf.faixa(16) != "12–16" \
            or mf.faixa(17) != "17–19" or mf.faixa(19) != "17–19" or mf.faixa(20) != "20–22" \
            or mf.faixa(22) != "20–22" or mf.faixa(23) != mf.DOBRA:
        falhas.append("fronteiras das faixas não batem com a DGX (<12 · 12–16 · 17–19 · 20–22 · >22)")
    # 3b) sem default — fonte
    fonte = inspect.getsource(mf)
    for m in re.finditer(r"\bor\s+\d", fonte):
        falhas.append(f"fonte do serviço tem `{m.group(0)}` — número que pode ser 0 com default")

    # 4a) contra-prova pura
    adm = date(2024, 1, 10)
    longo = [("doenca", date(2024, 6, 1), date(2025, 3, 1), "encerrado")]
    curto = [("doenca", date(2024, 6, 1), date(2024, 8, 1), "encerrado")]
    if mf.ancora_periodo(adm, longo) != date(2025, 3, 1):
        falhas.append(f"âncora com afastamento > 6 meses ficou em {mf.ancora_periodo(adm, longo)} — tinha de ser o retorno 01/03/2025 (art. 133 §2º)")
    if mf.ancora_periodo(adm, curto) != adm:
        falhas.append("afastamento de 2 meses moveu a âncora — só acima de 6 meses reinicia")
    if mf.ancora_periodo(None, longo) is not None:
        falhas.append("sem admissão a âncora tem de ser None (não calculado), não o retorno")

    async with async_session_factory() as db:
        linhas = await mf.mapa(db)
        total = (await db.execute(
            text(SQL_TOTAL_COM_VINCULO), {"sem": list(mf.SEM_VINCULO)})).scalar()

        # 2) soma das faixas == total com vínculo
        contagem: dict[str, int] = {}
        for ln in linhas:
            contagem[ln["faixa"]] = contagem.get(ln["faixa"], 0) + 1
        desconhecidas = set(contagem) - set(mf.FAIXAS)
        if desconhecidas:
            falhas.append(f"faixa fora da legenda: {sorted(desconhecidas)}")
        if sum(contagem.values()) != total or len(linhas) != total:
            falhas.append(f"soma das faixas {sum(contagem.values())} ≠ ativos com vínculo {total}")

        # 3c) sem default — por linha
        for ln in linhas:
            if ln["ancora"] is None and ln["faixa"] != mf.NAO_CALCULADO:
                falhas.append(f"{ln['nome']}: sem admissão e faixa {ln['faixa']!r} — tinha de ser 'não calculado'")
            if ln["ancora"] is None and ln["idade_meses"] is not None:
                falhas.append(f"{ln['nome']}: sem âncora mas idade {ln['idade_meses']} — número inventado")
            if ln["ancora"] is not None and ln["faixa"] not in (mf.AFASTADO_LONGO,) and ln["idade_meses"] is None:
                falhas.append(f"{ln['nome']}: tem âncora e não tem idade")

        # 4b) contra-prova de banco: âncora do serviço == âncora recalculada por SQL
        esperado = {r[0]: (r[1], r[2]) for r in (await db.execute(text(SQL_ANCORA))).fetchall()}
        recalculadas = 0
        for ln in linhas:
            adm_sql, ret_sql = esperado.get(ln["employee_id"], (None, None))
            if adm_sql is None:
                continue
            anc = max(adm_sql, ret_sql) if ret_sql else adm_sql
            if ret_sql and anc != adm_sql:
                recalculadas += 1
            if ln["ancora"] != anc:
                falhas.append(f"{ln['nome']}: âncora do serviço {ln['ancora']} ≠ recalculada {anc} "
                              f"(admissão {adm_sql}, retorno longo {ret_sql})")

        # 4c) a tela monta e traz as mesmas pessoas
        telas = await f8.telas(db)
        scr = telas.get("mapa-ferias")
        if not scr:
            falhas.append("telas() não devolve 'mapa-ferias'")
        elif len(scr.get("rows") or []) != total:
            falhas.append(f"tela lista {len(scr.get('rows') or [])} pessoas e o mapa tem {total}")

    legenda = " · ".join(f"{f}: {contagem.get(f, 0)}" for f in mf.FAIXAS)
    print(f"ativos com vínculo: {total} · âncoras recalculadas por afastamento: {recalculadas}")
    print(f"legenda: {legenda}")
    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no mapa de férias")
    print("OK mapa de férias: tela fiada, soma fecha, sem default, âncora respeita o art. 133")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
