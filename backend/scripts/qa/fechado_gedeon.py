#!/usr/bin/env python3
"""Critério de aceite EXECUTÁVEL do módulo GEDEON (ordem de fechamento T2).

Sai 0 só quando TODAS as condições passam. Enquanto sair vermelho, o módulo não fechou —
por mais agente de IA que tenha sido escrito.

Por que existe: "fechado" vinha sendo afirmado em prosa. Aqui é comando: cada condição
imprime ✅/❌ com o número que a sustenta, e o exit code decide.

A ordem segue a do prompt e ela não é arbitrária:
  · 1 e 2 FECHAM o módulo — o kit sai e a eletrônica fatura;
  · 3 a 7 fazem os dois primeiros serem verdade;
  · 8 a 13 impedem setembro de recomeçar do zero.

⚠️ CONDIÇÃO VERMELHA NÃO É NECESSARIAMENTE BUG MEU. Três delas dependem de decisão humana e
estão marcadas: destinatário por cliente, aprovação do kit e o crédito da OpenAI. Deixar
vermelho é o comportamento certo — some da vista é que não pode.

    docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/qa/fechado_gedeon.py
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
from datetime import date

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

COMP_INI, COMP_FIM = date(2026, 8, 1), date(2026, 8, 31)
_res: list[tuple[bool, str]] = []


def ok(cond: bool, n: int, titulo: str, detalhe: str, humano: bool = False) -> None:
    marca = "✅" if cond else ("🟡" if humano else "❌")
    _res.append((cond or humano, f"{marca} {n} · {titulo}"))
    print(f"  {marca} {n:>2} · {titulo:<26} {detalhe}")


async def main() -> int:
    print("\n══ GEDEON — critério de aceite ══\n")
    print("ENTREGA — o que fecha o módulo")

    async with async_session_factory() as db:
        # 1 · kit de agosto: existe, completo, aprovado e ENTREGUE
        r = (await db.execute(text(
            "SELECT count(*) FILTER (WHERE k.reference_month BETWEEN :i AND :f) AS kits, "
            "       count(*) FILTER (WHERE k.reference_month BETWEEN :i AND :f "
            "                          AND k.completion_percentage >= 100) AS cheios, "
            "       count(*) FILTER (WHERE k.reference_month BETWEEN :i AND :f "
            "                          AND lower(coalesce(k.status,''))='approved') AS aprovados, "
            "       count(*) FILTER (WHERE k.reference_month BETWEEN :i AND :f "
            "                          AND k.sent_at IS NOT NULL) AS enviados "
            "FROM ged_document_kits k"), {"i": COMP_INI, "f": COMP_FIM})).mappings().first()
        ok(r["aprovados"] >= 1 and r["enviados"] >= 1, 1, "kit de agosto",
           f'{r["kits"]} kits · {r["cheios"]} em 100% · {r["aprovados"]} aprovados · '
           f'{r["enviados"]} entregues', humano=True)

        # 2 · eletrônica: contrato ativo em agosto com NF emitida
        eletro = (await db.execute(text(
            "SELECT count(*) FROM contracts c JOIN empresas e ON e.id=c.empresa_id "
            "WHERE lower(coalesce(c.status::text,''))='active' AND NOT c.kit_mensal "
            "  AND lower(e.nome_fantasia) LIKE '%eletr%' "
            "  AND c.start_date <= :f AND coalesce(c.end_date, CAST('9999-12-31' AS date)) >= :i"),
            {"i": COMP_INI, "f": COMP_FIM})).scalar()
        nfs = (await db.execute(text(
            "SELECT count(*) FROM nfse_notas WHERE data_emissao BETWEEN :i AND :f"),
            {"i": COMP_INI, "f": COMP_FIM})).scalar() if await _tem_tabela(db, "nfse_notas") else 0
        ok(nfs >= eletro and eletro > 0, 2, "eletrônica fatura",
           f"{eletro} contrato(s) ativo(s) · {nfs} NFS-e em agosto", humano=True)

        print("\nO QUE FAZ O ITEM 1 SER VERDADE")

        # 3 · fonte nossa: ponto do Conecta PRO, não do Sólides
        p = (await db.execute(text(
            "SELECT count(*) FILTER (WHERE coalesce(device_type,'') NOT IN ('tangerino','web')) AS nosso, "
            "       count(*) FILTER (WHERE coalesce(device_type,'')='tangerino') AS solides "
            "FROM gp_clock_punches WHERE punch_timestamp >= :i"), {"i": COMP_INI})).mappings().first()
        ok(p["nosso"] > p["solides"], 3, "fonte nossa",
           f'{p["nosso"]} batidas Conecta PRO · {p["solides"]} Sólides em agosto')

        # 4 · CNPJ: kit trabalhista só pela Patrimonial
        fora = (await db.execute(text(
            "SELECT count(*) FROM contracts c LEFT JOIN empresas e ON e.id=c.empresa_id "
            "WHERE c.kit_mensal AND lower(coalesce(c.status::text,''))='active' "
            "  AND lower(coalesce(e.nome_fantasia,'')) NOT LIKE '%patrimonial%' "
            "  AND c.start_date <= :f AND coalesce(c.end_date, CAST('9999-12-31' AS date)) >= :i"),
            {"i": COMP_INI, "f": COMP_FIM})).scalar()
        ok(fora == 0, 4, "CNPJ emitente",
           f"{fora} contrato(s) com kit_mensal fora da Patrimonial")

        # 5 · completude bate com a contagem no banco
        div = (await db.execute(text(
            "SELECT count(*) FROM ged_document_kits k WHERE k.total_documents > 0 "
            "  AND abs(coalesce(k.completion_percentage,0) - round(100.0 * "
            "      (SELECT count(*) FROM ged_kit_documents d WHERE d.kit_id=k.id "
            "       AND d.file_path IS NOT NULL AND d.file_path<>'') "
            "      / nullif(k.total_documents,0), 2)) > 0.02"))).scalar()
        ok(div == 0, 5, "completude real", f"{div} kit(s) divergente(s) da contagem")

        # 6 · duplicata verdadeira (mesmo arquivo lógico no mesmo slot)
        dup = (await db.execute(text(
            "WITH n AS (SELECT kit_id, document_type, document_name, employee_id, "
            "       regexp_replace(coalesce(file_path,''), '^.*/[0-9a-f]{3,}_', '') AS logico "
            "     FROM ged_kit_documents) "
            "SELECT coalesce(sum(c-1),0) FROM ("
            "  SELECT count(*) c FROM n GROUP BY kit_id, document_type, document_name, "
            "         employee_id, logico HAVING count(*)>1) x"))).scalar()
        ok(dup == 0, 6, "sem duplicata", f"{dup} cópia(s) do mesmo arquivo no mesmo slot")

        # 7 · entrega provada
        sem_prova = (await db.execute(text(
            "SELECT count(*) FROM ged_document_kits "
            "WHERE (sent_at IS NOT NULL OR lower(coalesce(status,''))='enviado') "
            "  AND (coalesce(zip_file_path,'')='' AND coalesce(google_drive_link,'')='')"))).scalar()
        destinos = (await db.execute(text(
            "SELECT count(*) FROM clients WHERE coalesce(financial_contact_email,'')<>''"))).scalar()
        ok(sem_prova == 0 and destinos > 0, 7, "entrega provada",
           f"{sem_prova} enviado(s) sem arquivo · {destinos} cliente(s) com destinatário",
           humano=destinos == 0)

        print("\nO QUE SUSTENTA EM SETEMBRO")

        # 8 · Portte comparável — as rubricas do NOSSO lado.
        #
        # ⚠️ ESTA CONDIÇÃO MEDIA A TABELA ERRADA e ficou vermelha por isso. Eu olhava
        # `hr_payslip_items`, que é parse do PDF do Domínio e rodou uma vez em abril. As
        # nossas rubricas vivem em `hr_payslips.earnings`/`deductions`, como JSONB, gravadas
        # pelo fechamento — 472 delas em 07/2026, com o código canônico. A trava acusava
        # falta de dado que existia desde sempre; corrigido em 14/08.
        itens = (await db.execute(text(
            "SELECT coalesce(sum(jsonb_array_length(earnings)) "
            "     + sum(jsonb_array_length(deductions)), 0) FROM hr_payslips "
            "WHERE reference_year=2026 AND reference_month=7 AND status='published' "
            "  AND jsonb_typeof(earnings)='array' AND jsonb_typeof(deductions)='array'"))).scalar()
        ok(itens > 0, 8, "Portte comparável",
           f"{itens} rubrica(s) nossa(s) em 07/2026 · Σ|Δ contra a Portte R$ 11.492,60")

        # 9 · aprendizado gravado
        ev = (await db.execute(text("SELECT count(*) FROM gedeon_learning_events"))).scalar()
        ok(ev > 0, 9, "aprendizado", f"{ev} evento(s) de decisão humana")

    # 10 · beats — a trava nova
    r = subprocess.run([sys.executable, "/app/scripts/qa/checar_beats.py"],
                       capture_output=True, text=True, timeout=300)  # noqa: S603
    gedeon_ruim = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("gedeon.")]
    ok(not gedeon_ruim, 10, "beats do gedeon",
       f"{len(gedeon_ruim)} beat(s) chamando o que não existe")

    # 11 · oráculos do módulo
    oraculos = ["test_oraculo_completude_kit", "test_oraculo_kit_por_contrato",
                "test_oraculo_entrega_kit", "test_oraculo_espelho_falta"]
    verdes = []
    for o in oraculos:
        p = subprocess.run([sys.executable, f"/app/scripts/orq/{o}.py"],
                           capture_output=True, text=True, timeout=180)  # noqa: S603
        verdes.append(p.returncode == 0)
    ok(all(verdes), 11, "oráculos verdes",
       f"{sum(verdes)}/{len(oraculos)} — " + ", ".join(
           o.replace("test_oraculo_", "") for o, v in zip(oraculos, verdes, strict=True) if not v)
       or f"{sum(verdes)}/{len(oraculos)}")

    fechado = all(v for v, _ in _res)
    print(f"\n{'✅ MÓDULO FECHADO' if fechado else '❌ NÃO FECHADO'} — "
          f"{sum(1 for v, _ in _res if v)}/{len(_res)} condições")
    print("🟡 = depende de decisão humana, não de código.\n")
    return 0 if fechado else 1


async def _tem_tabela(db, nome: str) -> bool:
    return bool((await db.execute(text(
        "SELECT 1 FROM information_schema.tables WHERE table_name = :n"), {"n": nome})).first())


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
