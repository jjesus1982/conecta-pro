"""Oráculo — DP complementos da paridade DGX, frente F6 (24/09/2026).

Por que existe: cinco capacidades do DGX que o DP não tinha — dependentes com grau/instrução,
vale (adiantamento avulso descontado em folha), evento coletivo (um lançamento para N pessoas
numa competência), crachá em lote e demissão em lote. Todas mexem perto de dinheiro (salário-
família, IRRF, desconto em folha, rescisão) e o jeito mais fácil de cada uma mentir é: gravar
num lugar que a folha não lê, ou "aplicar" e não deixar rastro que se possa desfazer.

O que afirma (cada bloco reconta por SQL próprio, não pelo serviço):
  1. DEPENDENTES — a fonte que a folha lê é `employees.dependentes` (chave `menor_14`,
     `calculo_service` linhas 782/833). Para toda entrada com data de nascimento, `menor_14` ==
     régua do salário-família (`contar_elegiveis`: até 14 anos ou inválido); e
     `employee_dp.quantidade_dependentes_sf` == `contar_elegiveis(employees.dependentes)`.
     Prova de ida e volta com fixture: salvar → aparece com a flag certa → remover → some.
  2. VALE — vale aberto (fixture) aparece na prévia de folha do colaborador
     (`calcular_folha_colaborador`, código 1040, sem tocar em `calculo_service.py`) e SOME ao
     quitar. Rubrica 1040 existe em `rubricas_folha` como desconto.
  3. EVENTO COLETIVO — aplicado → N apontamentos em `hr_payslips.contest_reason` com a marca do
     evento (N == quantidade_colaboradores == len(apontamento_ids)); desfeito → 0. Competência
     com folha publicada é RECUSADA.
  4. CRACHÁ — 8 pessoas → PDF de 1 página com o nome de cada uma, matrícula e CNPJ; 9 → 2 páginas.
  5. DEMISSÃO EM LOTE — 2 pessoas → 2 `termination_processes` em `initiated` (rascunho do fluxo),
     nenhuma efetivada: `employees.status` continua 'ativo' e sem data de demissão.

Estado medido no nascimento (sandbox, 24/09/2026): módulo `_dgx_f6_dp` não existia → VERMELHO.
Fixtures: marcadas com 'FIXTURE DGX F6' e apagadas ao fim (só linhas que este oráculo criou).

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

FIX = "FIXTURE DGX F6"

SQL_ATIVO_COM_FOLHA = """
SELECT e.id::text, e.nome FROM employees e
WHERE e.status='ativo' AND coalesce(e.is_homologacao,false)=false
  AND coalesce(e.tipo_contrato,'') NOT ILIKE '%pj%' AND e.salario_base > 0
  AND e.data_admissao IS NOT NULL AND e.escala_padrao IS NOT NULL
  AND jsonb_array_length(coalesce(e.dependentes,'[]'::jsonb)) = 0
  AND NOT EXISTS (SELECT 1 FROM employee_deductions d WHERE d.employee_id = e.id AND d.ativo)
ORDER BY e.nome LIMIT 1
"""


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory
    from core.database.session import SyncSessionLocal
    from modules.people_management.hr.services import salario_familia_service as sf

    falhas: list[str] = []
    try:
        # ordem de produção (não alfabética, de propósito): o dispatcher importa o builder do DP,
        # que importa a frente. Importar a frente primeiro fecha o ciclo com `router` parcial.
        from modules.operacional.controllers.redesign_builders import departamento_pessoal as dp  # noqa: I001
        from modules.operacional.controllers.redesign_builders import _dgx_f6_dp as f6
        from modules.operacional.controllers.redesign_builders._dp_grupos import GRUPOS
        from modules.people_management.hr.services import cracha_pdf
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: frente F6 não importa: {e}")
        print("TOTAL dp complementos: 1 falha")
        return 1

    # 0) fiação — tela sem porta não existe
    if "_telas_f6" not in inspect.getsource(dp.build):
        falhas.append("departamento_pessoal.build() não chama _dgx_f6_dp.telas")
    abas = {tid: gid for gid, _t, _s, tabs in GRUPOS for tid, _l in tabs}
    for tid, gid in [
        ("dependentes", "g-admissao"),
        ("dependente-novo", "g-admissao"),
        ("crachas-lote", "g-admissao"),
        ("vales", "g-folha"),
        ("vale-novo", "g-folha"),
        ("eventos-coletivos", "g-folha"),
        ("evento-coletivo-novo", "g-folha"),
        ("demissao-lote", "g-desligamento"),
    ]:
        if abas.get(tid) != gid:
            falhas.append(f"aba {tid} não está no grupo {gid} de _dp_grupos.GRUPOS")

    # 1a) dependentes — régua pura: menor_14 deriva da MESMA régua do salário-família
    deps = f6.normalizar_dependentes(
        [
            {"nome": "a", "nascimento": "2020-01-01"},
            {"nome": "b", "nascimento": "1990-01-01"},
            {"nome": "c", "invalido": True},
            {"tipo": "filho", "menor_14": True},
        ]
    )
    flags = [d.get("menor_14") for d in deps]
    if flags != [True, False, True, True]:
        falhas.append(
            f"normalizar_dependentes: flags {flags} ≠ [True, False, True, True] (≤14 · adulto · inválido · backfill intocado)"
        )
    if sum(1 for d in deps if d.get("menor_14")) - 1 != sf.contar_elegiveis(deps):
        falhas.append("contagem de menor_14 (fora o backfill sem data) ≠ contar_elegiveis")
    if f6.cpf_valido("111.111.111-11") or not f6.cpf_valido("529.982.247-25"):
        falhas.append("validação de CPF errada (11111111111 passou ou 52998224725 falhou)")

    hoje = date.today()
    async with async_session_factory() as db:
        # 1b) banco — toda entrada com data: menor_14 == régua; employee_dp bate com a régua
        rows = (
            await db.execute(
                text(
                    "SELECT e.id::text, e.nome, e.dependentes, d.quantidade_dependentes_sf "
                    "FROM employees e LEFT JOIN employee_dp d ON d.employee_id = e.id "
                    "WHERE jsonb_array_length(coalesce(e.dependentes,'[]'::jsonb)) > 0"
                )
            )
        ).fetchall()
        sem_data = 0
        for _eid, nome, dd, qtd_dp in rows:
            for d in dd or []:
                if not isinstance(d, dict):
                    continue
                if not (d.get("nascimento") or d.get("data_nascimento") or d.get("invalido") or d.get("invalidez")):
                    sem_data += 1
                    continue
                if bool(d.get("menor_14")) != (sf.contar_elegiveis([d], hoje) == 1):
                    falhas.append(
                        f"{nome}: dependente {d.get('nome')!r} menor_14={d.get('menor_14')} ≠ régua do salário-família"
                    )
            if qtd_dp is not None and qtd_dp != sf.contar_elegiveis(dd, hoje):
                falhas.append(
                    f"{nome}: employee_dp.quantidade_dependentes_sf={qtd_dp} ≠ contar_elegiveis={sf.contar_elegiveis(dd, hoje)}"
                )

        alvo = (await db.execute(text(SQL_ATIVO_COM_FOLHA))).first()
        if not alvo:
            falhas.append("nenhum ativo sem dependentes e sem desconto para servir de fixture")
            eid = nome_alvo = None
        else:
            eid, nome_alvo = alvo
        if eid:
            # 1c) ida e volta (o upsert em employee_dp cria linha se não houver — apagada ao fim se foi este oráculo que criou)
            tinha_dp = (
                await db.execute(text("SELECT 1 FROM employee_dp WHERE employee_id::text=:e"), {"e": eid})
            ).first() is not None
            deps = await f6.salvar_dependente(
                db, eid, {"nome": f"{FIX} filho", "nascimento": "2019-05-05", "grau": "Filho/a", "sexo": "M"}
            )
            dd, qtd = (
                await db.execute(
                    text(
                        "SELECT e.dependentes, d.quantidade_dependentes_sf FROM employees e "
                        "LEFT JOIN employee_dp d ON d.employee_id=e.id WHERE e.id::text=:e"
                    ),
                    {"e": eid},
                )
            ).first()
            if not any(
                isinstance(d, dict) and d.get("nome", "").startswith(FIX) and d.get("menor_14") is True
                for d in dd or []
            ):
                falhas.append("dependente salvo não está em employees.dependentes com menor_14=true")
            if qtd != 1:
                falhas.append(f"após salvar filho de 7 anos, employee_dp.quantidade_dependentes_sf={qtd} (esperado 1)")
            idx = next(
                (i for i, d in enumerate(dd or []) if isinstance(d, dict) and d.get("nome", "").startswith(FIX)), None
            )
            await f6.remover_dependente(db, eid, idx, nome=f"{FIX} filho")
            dd, qtd = (
                await db.execute(
                    text(
                        "SELECT e.dependentes, d.quantidade_dependentes_sf FROM employees e "
                        "LEFT JOIN employee_dp d ON d.employee_id=e.id WHERE e.id::text=:e"
                    ),
                    {"e": eid},
                )
            ).first()
            if any(isinstance(d, dict) and d.get("nome", "").startswith(FIX) for d in dd or []) or qtd != 0:
                falhas.append(f"após remover, dependente ainda existe ou quantidade_dependentes_sf={qtd}")
            if not tinha_dp:
                await db.execute(
                    text(
                        "DELETE FROM employee_dp WHERE employee_id::text=:e AND coalesce(quantidade_dependentes_sf,0)=0"
                    ),
                    {"e": eid},
                )
                await db.commit()

            # 2) vale — entra na prévia de folha e some ao quitar
            vid = await f6.criar_vale(db, eid, motivo=FIX, valor_total=Decimal("300"), parcelas=3, data_ocorrencia=hoje)
            rub = (await db.execute(text("SELECT tipo, ativo FROM rubricas_folha WHERE codigo='1040'"))).first()
            if not rub or rub[0] != "desconto" or not rub[1]:
                falhas.append("rubrica 1040 (vale) não existe em rubricas_folha como desconto ativo")

            from modules.people_management.folha.services.calculo_service import calcular_folha_colaborador

            def _linha_vale():
                sdb = SyncSessionLocal()
                try:
                    h = calcular_folha_colaborador(sdb, eid, hoje.month, hoje.year)
                finally:
                    sdb.close()
                return [
                    x for x in h.get("descontos", []) if x.get("codigo") == "1040" and FIX in (x.get("descricao") or "")
                ]

            antes = _linha_vale()
            if len(antes) != 1 or abs(float(antes[0]["valor"]) - 100.0) > 0.01:
                falhas.append(f"vale aberto não aparece na prévia de folha como 1040 de R$ 100,00 (achado: {antes})")
            await f6.quitar_vale(db, vid)
            st = (
                await db.execute(
                    text("SELECT ativo, valor_pago FROM employee_deductions WHERE id::text=:i"), {"i": vid}
                )
            ).first()
            if not st or st[0] or float(st[1] or 0) != 300.0:
                falhas.append(f"quitar não fechou o vale (ativo/valor_pago = {st})")
            if _linha_vale():
                falhas.append("vale quitado continua na prévia de folha")
            await db.execute(
                text("DELETE FROM employee_deductions WHERE id::text=:i AND motivo=:m"), {"i": vid, "m": FIX}
            )
            await db.commit()

        # 3) evento coletivo — competência só com rascunho, 2 pessoas com folha rascunho sem apontamento
        comp = (
            await db.execute(
                text(
                    "SELECT reference_year, reference_month FROM hr_payslips GROUP BY 1,2 "
                    "HAVING count(*) FILTER (WHERE status::text='published') = 0 "
                    "AND count(*) FILTER (WHERE status::text='draft' AND contest_reason IS NULL) >= 2 "
                    "ORDER BY 1 DESC, 2 DESC LIMIT 1"
                )
            )
        ).first()
        pub = (
            await db.execute(
                text(
                    "SELECT reference_year, reference_month FROM hr_payslips WHERE status::text='published' "
                    "ORDER BY 1 DESC, 2 DESC LIMIT 1"
                )
            )
        ).first()
        if not comp:
            falhas.append("nenhuma competência só-rascunho com 2 folhas para o evento coletivo")
        else:
            ano, mes = comp
            pes = (
                await db.execute(
                    text(
                        "SELECT DISTINCT p.employee_id::text FROM hr_payslips p JOIN employees e ON e.id=p.employee_id "
                        "WHERE p.reference_year=:a AND p.reference_month=:m AND p.status::text='draft' AND p.contest_reason IS NULL "
                        "AND e.status='ativo' AND coalesce(e.is_homologacao,false)=false LIMIT 2"
                    ),
                    {"a": ano, "m": mes},
                )
            ).fetchall()
            ids = [r[0] for r in pes]
            if len(ids) < 2:
                falhas.append("menos de 2 pessoas ativas com folha rascunho sem apontamento")
            else:
                ev = await f6.criar_evento(
                    db,
                    {
                        "tipo": "inclusao",
                        "rubrica_codigo": "0010",
                        "competencia": f"{mes:02d}/{ano}",
                        "referencia": "10",
                        "employee_ids": ids,
                    },
                    criado_por=FIX,
                )
                autor = SimpleNamespace(name=FIX, email=None, id="0")
                sdb = SyncSessionLocal()
                try:
                    res = await f6.aplicar_evento(sdb, ev, autor)
                    if pub:
                        ev_pub = await f6.criar_evento(
                            db,
                            {
                                "tipo": "inclusao",
                                "rubrica_codigo": "0010",
                                "competencia": f"{pub[1]:02d}/{pub[0]}",
                                "referencia": "1",
                                "employee_ids": ids,
                            },
                            criado_por=FIX,
                        )
                        try:
                            await f6.aplicar_evento(sdb, ev_pub, autor)
                            falhas.append(
                                f"evento na competência PUBLICADA {pub[1]:02d}/{pub[0]} foi aplicado — tinha de recusar"
                            )
                        except Exception:  # noqa: BLE001 — recusa é o esperado
                            pass
                    marca = f"%[evento coletivo #{ev}]%"
                    n_sql = (
                        await db.execute(
                            text("SELECT count(*) FROM hr_payslips WHERE contest_reason LIKE :m"), {"m": marca}
                        )
                    ).scalar()
                    st, qtd, aids = (
                        await db.execute(
                            text(
                                "SELECT status, quantidade_colaboradores, apontamento_ids "
                                "FROM folha_eventos_coletivos WHERE id=:i"
                            ),
                            {"i": ev},
                        )
                    ).first()
                    if not (n_sql == 2 == qtd == len(aids or []) and st == "aplicado"):
                        falhas.append(
                            f"evento aplicado: apontamentos por SQL={n_sql}, quantidade={qtd}, ids={len(aids or [])}, status={st} (esperado 2/2/2/aplicado; res={res})"
                        )
                    await f6.desfazer_evento(sdb, ev)
                    n_sql = (
                        await db.execute(
                            text("SELECT count(*) FROM hr_payslips WHERE contest_reason LIKE :m"), {"m": marca}
                        )
                    ).scalar()
                    st = (
                        await db.execute(text("SELECT status FROM folha_eventos_coletivos WHERE id=:i"), {"i": ev})
                    ).scalar()
                    if n_sql != 0 or st != "desfeito":
                        falhas.append(f"evento desfeito: ainda {n_sql} apontamento(s), status={st}")
                finally:
                    sdb.close()
                await db.execute(text("DELETE FROM folha_eventos_coletivos WHERE criado_por=:c"), {"c": FIX})
                await db.commit()

        # 4) crachá — 8 pessoas = 1 página; 9 = 2
        pessoas = await f6.pessoas_para_cracha(db, {"employee_ids": []}, limite=9)
        if len(pessoas) < 9:
            falhas.append(f"só {len(pessoas)} ativos para o teste do crachá (precisa 9)")
        else:
            try:
                from PyPDF2 import PdfReader
            except Exception:  # noqa: BLE001
                from pypdf import PdfReader  # type: ignore
            pdf8 = cracha_pdf.montar_crachas(pessoas[:8])
            r8 = PdfReader(BytesIO(pdf8))
            txt = "\n".join((p.extract_text() or "") for p in r8.pages)
            if len(r8.pages) != 1:
                falhas.append(f"8 crachás geraram {len(r8.pages)} página(s), esperado 1")
            for p in pessoas[:8]:
                primeiro = (p["nome"] or "").split()[0].upper()
                if primeiro not in txt.upper():
                    falhas.append(f"crachá sem o nome {primeiro}")
                if p.get("matricula") and str(p["matricula"]) not in txt:
                    falhas.append(f"crachá sem a matrícula {p['matricula']}")
            if "CNPJ" not in txt:
                falhas.append("crachá sem CNPJ da empresa")
            if len(PdfReader(BytesIO(cracha_pdf.montar_crachas(pessoas[:9]))).pages) != 2:
                falhas.append("9 crachás não geraram 2 páginas")

        # 5) demissão em lote — 2 rescisões initiated, ninguém efetivado
        dois = (
            await db.execute(
                text(
                    "SELECT id::text FROM employees WHERE status='ativo' AND coalesce(is_homologacao,false)=false "
                    "AND salario_base > 0 AND data_admissao IS NOT NULL ORDER BY nome LIMIT 2"
                )
            )
        ).fetchall()
        dois = [r[0] for r in dois]
        itens = await f6.preparar_demissao_lote(
            db,
            dois,
            data=hoje,
            tipo="involuntary",
            notice_type="indenizado",
            notice_period_days=30,
            reason=FIX,
            created_by_id=None,
        )
        n_tp = (
            await db.execute(
                text("SELECT count(*) FROM termination_processes WHERE reason=:r AND status='initiated'"), {"r": FIX}
            )
        ).scalar()
        n_ef = (
            await db.execute(
                text(
                    "SELECT count(*) FROM employees WHERE id::text = ANY(:ids) AND (status <> 'ativo' "
                    "OR data_demissao IS NOT NULL OR data_desligamento IS NOT NULL)"
                ),
                {"ids": dois},
            )
        ).scalar()
        if n_tp != 2 or len(itens) != 2:
            falhas.append(
                f"demissão em lote: {n_tp} rescisão(ões) initiated no banco, {len(itens)} item(ns) devolvidos (esperado 2/2)"
            )
        if n_ef:
            falhas.append(f"demissão em lote EFETIVOU {n_ef} pessoa(s) — tinha de ficar em rascunho")
        if any(not it.get("verbas_estimadas") for it in itens):
            falhas.append(
                f"item sem verbas estimadas: {[it.get('nome') for it in itens if not it.get('verbas_estimadas')]}"
            )
        await db.execute(text("DELETE FROM termination_processes WHERE reason=:r"), {"r": FIX})
        await db.commit()

    print(
        f"dependentes: {len(rows)} pessoa(s) com dependentes · {sem_data} entrada(s) sem data de nascimento (backfill Portte, fora da régua) · "
        f"fixture em {nome_alvo}"
    )
    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL dp complementos: {len(falhas)} falha(s)")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na frente F6")
    print(
        "OK dp complementos: dependentes na fonte da folha, vale entra e sai da prévia, evento coletivo aplica/desfaz, "
        "crachá 8/página, demissão em lote só rascunho"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
