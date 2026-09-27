#!/usr/bin/env python3
"""Oráculo: o recibo de entrega da DCTFWeb é lido, prova a si mesmo, e chega às obrigações.

Regra, não fotografia:
  (a) TODO recibo do Onvio (categoria dctfweb_recibo) parseia como DCTFWEB_RECIBO, com o
      número do recibo e a competência IGUAIS aos que o próprio nome do arquivo carrega
      (`Recibo_<cnpj>_<MMAAAA>_40_<nº>`). Dois lugares do mesmo documento têm de concordar.
  (b) O documento se prova sozinho: TOTAL = soma das linhas, em débito e em saldo; e nenhum
      saldo a pagar é maior que o débito apurado.
  (c) Contrato do aplicador, a partir do corte contábil da empresa: INSS e IRRF da competência
      carregam `dctfweb_recibo=<nº>`, `valor_devido` = saldo a pagar do grupo, e saldo zero
      é `cumprida` (nada apurado, ou quitado na própria declaração).
  (d) Acessórias (DCTFWEB/ESOCIAL/EFD_REINF) da competência não ficam `pendente` com recibo
      de entrega em mãos.

Por que nasceu (27/09/2026): 17 recibos dormiam em `nao_classificados` porque o parser
procurava «Número do Recibo» e o recibo de entrega diz «Nº do recibo de entrega». INSS e IRRF
de 08/2026 estavam «SEM VALOR (prazo cego)» com o valor no PDF há duas semanas.

Roda:
    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/test_oraculo_fiscal_dctfweb_recibo.py
"""

from __future__ import annotations

import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from modules.fiscal_contabil.obrigacoes.guias_drive_service import (  # noqa: E402
    _TRIBUTOS_INSS,
    _db_sync,
    parse_pdf_guia,
)


def main() -> None:
    db = _db_sync()
    rows = db.execute(
        text(
            "SELECT d.nome_arquivo, d.caminho_local, e.id::text, coalesce(e.corte_contabil, DATE '2026-08-01') "
            "  FROM onvio_documents d LEFT JOIN empresas e "
            "    ON regexp_replace(e.cnpj, '[^0-9]', '', 'g') = substring(d.nome_arquivo from '_(\\d{14})_') "
            " WHERE d.categoria = 'dctfweb_recibo' AND d.caminho_local IS NOT NULL ORDER BY d.nome_arquivo"
        )
    ).all()
    assert rows, "nenhum recibo DCTFWeb no onvio_documents — o puxador do Onvio parou?"
    lidos = aplicados = 0
    for nome, caminho, emp, corte in rows:
        if not os.path.exists(caminho):
            continue
        g = parse_pdf_guia(caminho, nome)
        assert g.tipo == "DCTFWEB_RECIBO", f"{nome}: parseou como {g.tipo}"
        lidos += 1
        m = re.search(r"_(\d{6})_4\d_(\d+)\.pdf$", nome)
        if m:  # (a) o nome do arquivo e o conteúdo concordam
            assert g.numero_recibo == m.group(2).lstrip("0"), f"{nome}: recibo {g.numero_recibo} ≠ nome"
            assert (g.competencia_mes, g.competencia_ano) == (int(m.group(1)[:2]), int(m.group(1)[2:])), (
                f"{nome}: competência {g.competencia_mes}/{g.competencia_ano} ≠ nome"
            )
        trib = g.detalhe["tributos"]
        total = trib.get("TOTAL") or {}
        linhas = [v for k, v in trib.items() if k != "TOTAL"]
        assert total, f"{nome}: sem linha TOTAL"
        for chave in ("debito", "saldo"):  # (b)
            soma = round(sum(v[chave] for v in linhas), 2)
            assert abs(soma - total[chave]) < 0.01, f"{nome}: TOTAL {chave} {total[chave]} ≠ soma {soma}"
        for k, v in trib.items():
            assert v["saldo"] <= v["debito"] + 0.005, f"{nome}: {k} saldo {v['saldo']} > débito {v['debito']}"

        if not (emp and g.competencia_mes):
            continue
        mes, ano = g.competencia_mes, g.competencia_ano
        a, mm = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
        if date(a, mm, 20) < corte:
            continue
        grupos = {
            "INSS": round(sum((trib.get(n) or {}).get("saldo", 0) for n in _TRIBUTOS_INSS), 2),
            "IRRF": round((trib.get("IRRF") or {}).get("saldo", 0), 2),
        }
        for tipo, saldo in grupos.items():  # (c)
            r = db.execute(
                text(
                    "SELECT valor_devido, status, observacoes LIKE :marca FROM fiscal_obligations "
                    "WHERE empresa_id = CAST(:e AS uuid) AND tipo = :t AND competencia_mes = :m "
                    "AND competencia_ano = :a AND active ORDER BY created_at LIMIT 1"
                ),
                {"e": emp, "t": tipo, "m": mes, "a": ano, "marca": f"%dctfweb_recibo={g.numero_recibo}%"},
            ).first()
            if r is None:
                continue
            assert r[2], f"{nome}: {tipo} {mes:02d}/{ano} sem o marcador do recibo — aplicador não passou"
            assert abs(float(r[0] or 0) - saldo) < 0.01, f"{nome}: {tipo} valor_devido {r[0]} ≠ saldo {saldo}"
            if saldo == 0:
                assert r[1] == "cumprida", f"{nome}: {tipo} saldo zero e status {r[1]}"
            aplicados += 1
        pend = db.execute(  # (d)
            text(
                "SELECT string_agg(tipo, ',') FROM fiscal_obligations WHERE empresa_id = CAST(:e AS uuid) "
                "AND tipo IN ('DCTFWEB','ESOCIAL','EFD_REINF') AND competencia_mes = :m AND competencia_ano = :a "
                "AND active AND status <> 'cumprida'"
            ),
            {"e": emp, "m": mes, "a": ano},
        ).scalar()
        assert not pend, f"{nome}: acessórias {pend} pendentes com recibo de entrega {g.numero_recibo}"
    db.close()
    assert lidos, "nenhum recibo no disco"
    print(
        f"OK {lidos} recibo(s) lidos e coerentes com o nome e com o próprio TOTAL · {aplicados} linha(s) INSS/IRRF conferidas"
    )
    print("TEST oraculo_fiscal_dctfweb_recibo PASS")


if __name__ == "__main__":
    main()
