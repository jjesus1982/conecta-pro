"""Oráculo — Transferência de colaborador entre as empresas do grupo (paridade DGX, frente W4).

Por que existe: a casa tem DUAS empresas (Conecta Mais Eletrônica, CNPJ 35.710.481/0001-03, e
Conecta Mais Patrimonial, 66.014.833/0001-10) e o sistema não tinha NENHUM fluxo de transferência
entre elas. Em 30/06/2026 o GEILSON RODRIGUES DE ANDRADE foi transferido para a Patrimonial e isso
apareceu só no espelho do eSocial (S-2299 com mtvDeslig=11): o DP descobriu consultando o governo.
Sem fluxo, a única forma de "transferir" alguém aqui era demitir e readmitir — o que zera data de
admissão, período aquisitivo de férias e histórico, e é ERRADO: no eSocial transferência é
S-2299 (mtvDeslig 10/11) na origem + S-2200 (tpAdmissao 2/3 com sucessaoVinc) no destino, com o
vínculo CONTINUANDO.

O que afirma (recontado por SQL próprio, nunca pelo serviço):
  a. `dp_transferencias` existe com as colunas do contrato e o serviço importa.
  b. `simular` diz o que muda (empresa, cargo, salário) e o que NÃO muda (admissão, período
     aquisitivo, banco de horas, dependentes, documentos) — sem escrever nada.
  c. `efetivar` mantém a DATA DE ADMISSÃO, o período aquisitivo de férias (nº de períodos e a
     data-âncora do mais antigo) e os dependentes — os três recontados por SQL antes e depois —
     e troca a empresa do colaborador.
  d. `efetivar` cria EXATAMENTE 2 rascunhos de eSocial (`esocial_transmissao_propostas`, status
     'proposto') e NENHUM transmitido: zero linha com status <> 'proposto', zero evento novo em
     `eventos_esocial` e zero em `esocial_eventos_espelho`. Transmitir é ato humano, fora daqui.
  e. Alocações: a da origem fica encerrada em D−1 e a nova aberta em D — sem buraco (fim+1 =
     início) e sem sobreposição (exatamente uma ativa).
  f. `cancelar` um rascunho não muda NADA: empresa, alocação ativa e nº de rascunhos eSocial
     iguais antes e depois.
  g. A régua de conferência acha quem está transferido no GOVERNO e não tem transferência aqui
     (é o caso do GEILSON, CPF 029.969.132-21) e NÃO acusa quem está casado (fixture com S-2299
     no espelho E transferência efetivada não aparece em nenhuma das duas listas).
  h. Transferência não gera rescisão nem admissão: `termination_processes` e `admission_processes`
     com a MESMA contagem antes e depois.
  i. Fixtures ('FIXTURE DGX W4') apagadas ao fim.

Estado medido no nascimento (sandbox `conecta_pro_staging`, 24/09/2026): tabela `dp_transferencias`
não existia, serviço não existia → (a)…(f), (h) VERMELHOS. (g) media 1 pessoa só no governo
(GEILSON, S-2299 de 30/06/2026 mtvDeslig=11, `employees.status='ativo'`) e zero régua para vê-la.
Baseline: `termination_processes` = 3, `admission_processes` = 1, employees = 104.

Como roda (container efêmero contra o sandbox — ver docs/dgx/CONTRATO_AGENTE.md):
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" -e PYTHONPATH=/app \
      -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_w4_transferencia.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, timedelta

FIX = "FIXTURE DGX W4"
CPF_GEILSON = "02996913221"
CNPJ_ELETRONICA = "35.710.481/0001-03"
CNPJ_PATRIMONIAL = "66.014.833/0001-10"

SQL_COLUNAS = """
SELECT string_agg(column_name, ',' ORDER BY column_name) FROM information_schema.columns
WHERE table_name = 'dp_transferencias'
"""
COLUNAS_CONTRATO = [
    "employee_id",
    "empresa_origem_cnpj",
    "empresa_destino_cnpj",
    "data",
    "motivo",
    "mantem_admissao",
    "novo_cargo_id",
    "novo_salario",
    "observacao",
    "status",
    "esocial_s2299_id",
    "esocial_s2200_id",
    "efetivada_por",
    "efetivada_em",
]

SQL_LIMPA = [
    "DELETE FROM esocial_transmissao_propostas WHERE employee_id IN (SELECT id FROM employees WHERE nome LIKE :f)",
    "DELETE FROM esocial_eventos_espelho WHERE id_evento LIKE :f",
    "DELETE FROM dp_transferencias WHERE observacao LIKE :f",
    "DELETE FROM employee_alocacoes WHERE observacao LIKE :f "
    "   OR employee_id IN (SELECT id FROM employees WHERE nome LIKE :f)",
    "DELETE FROM hr_vacation_periods WHERE employee_id IN (SELECT id FROM employees WHERE nome LIKE :f)",
    "DELETE FROM employee_dp WHERE employee_id IN (SELECT id FROM employees WHERE nome LIKE :f)",
    "DELETE FROM employees WHERE nome LIKE :f",
]

# ---- recontagens independentes do serviço -----------------------------------
SQL_FOTO_EMP = """
SELECT e.data_admissao, em.cnpj, e.cargo, e.salario_base, e.status, e.data_demissao
FROM employees e LEFT JOIN empresas em ON em.id = e.empresa_id WHERE e.id = CAST(:e AS uuid)
"""
SQL_PERIODOS = (
    "SELECT count(*), min(start_date)::text, coalesce(sum(days_remaining),0) FROM hr_vacation_periods "
    "WHERE employee_id = CAST(:e AS uuid)"
)
SQL_DEPS = (
    "SELECT coalesce(jsonb_array_length(coalesce(dependentes,'[]'::jsonb)),0) FROM employee_dp "
    "WHERE employee_id = CAST(:e AS uuid)"
)
SQL_ALOC = (
    "SELECT id::text, data_inicio, data_fim, ativo, condominio_id::text, funcao FROM employee_alocacoes "
    "WHERE employee_id = CAST(:e AS uuid) ORDER BY data_inicio, coalesce(data_fim, '9999-12-31')"
)
SQL_PROPOSTAS = (
    "SELECT tipo_evento, status FROM esocial_transmissao_propostas WHERE referencia = :r ORDER BY tipo_evento"
)
SQL_CONT = "SELECT (SELECT count(*) FROM termination_processes), (SELECT count(*) FROM admission_processes)"
SQL_EVENTOS_GOV = "SELECT (SELECT count(*) FROM eventos_esocial), (SELECT count(*) FROM esocial_eventos_espelho)"


async def main() -> int:  # noqa: C901, PLR0912, PLR0915 — um oráculo, uma leitura de cima a baixo
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    async with async_session_factory() as db:
        # a. tabela + serviço
        cols = (await db.execute(text(SQL_COLUNAS))).scalar() or ""
        faltam = [c for c in COLUNAS_CONTRATO if c not in cols.split(",")]
        try:
            from modules.people_management.hr.services import transferencia as tr
        except Exception as exc:  # noqa: BLE001
            tr = None
            ok(False, f"(a) serviço transferencia não importa: {type(exc).__name__}: {exc}")
        if tr is not None:
            await tr._ensure(db)
            cols = (await db.execute(text(SQL_COLUNAS))).scalar() or ""
            faltam = [c for c in COLUNAS_CONTRATO if c not in cols.split(",")]
            ok(not faltam, f"(a) dp_transferencias com as colunas do contrato (faltam: {faltam or 'nenhuma'})")
        else:
            ok(False, f"(a) dp_transferencias: colunas faltando {faltam}")
            print(f"TOTAL falhas transferência W4: {len(falhas)}")
            return 1

        for sql in SQL_LIMPA:
            await db.execute(text(sql), {"f": FIX + "%"})
        await db.commit()

        # fixture: colaborador CLT da Eletrônica, admitido há 2 anos, 2 períodos de férias,
        # 2 dependentes e 1 alocação ativa num condomínio real.
        cond = (await db.execute(text("SELECT id::text FROM condominios ORDER BY nome LIMIT 1"))).scalar()
        cargo_novo = (
            await db.execute(
                text(
                    "SELECT id::text, cargo_nome, piso_salarial FROM cct_cargos WHERE is_active ORDER BY cargo_nome LIMIT 1"
                )
            )
        ).first()
        eletronica = (
            await db.execute(text("SELECT id::text FROM empresas WHERE slug = 'conecta_eletronica'"))
        ).scalar()
        if not cond or not cargo_novo or not eletronica:
            ok(False, "(fixture) sem condomínio / cargo CCT / empresa Eletrônica no sandbox")
            print(f"TOTAL falhas transferência W4: {len(falhas)}")
            return 1

        hoje = date.today()
        admissao = hoje - timedelta(days=730)
        emp = (
            await db.execute(
                text(
                    "INSERT INTO employees (id, nome, cpf, status, data_admissao, cargo, salario_base, empresa_id, matricula) "
                    "VALUES (gen_random_uuid(), :n, :c, 'ativo', :a, 'AGENTE DE PORTARIA', 1670.00, CAST(:em AS uuid), :m) "
                    "RETURNING id::text"
                ),
                {"n": f"{FIX} COLABORADOR", "c": "11144477735", "a": admissao, "em": eletronica, "m": "W4FIX"},
            )
        ).scalar()
        await db.execute(
            text(
                "INSERT INTO employee_dp (id, employee_id, dependentes) VALUES (gen_random_uuid(), CAST(:e AS uuid), "
                "CAST(:d AS jsonb))"
            ),
            {"e": emp, "d": '[{"nome": "FIXTURE DGX W4 FILHO 1"}, {"nome": "FIXTURE DGX W4 FILHO 2"}]'},
        )
        for i in (1, 2):
            ini = admissao + timedelta(days=365 * (i - 1))
            await db.execute(
                text(
                    "INSERT INTO hr_vacation_periods (id, condominio_id, employee_id, start_date, end_date, "
                    " period_number, limit_date) VALUES (gen_random_uuid(), CAST(:c AS uuid), CAST(:e AS uuid), :s, :f, :n, :l)"
                ),
                {"c": cond, "e": emp, "s": ini, "f": ini + timedelta(days=364), "n": i, "l": ini + timedelta(days=729)},
            )
        await db.execute(
            text(
                "INSERT INTO employee_alocacoes (id, employee_id, condominio_id, funcao, data_inicio, ativo, tipo, motivo, observacao) "
                "VALUES (gen_random_uuid(), CAST(:e AS uuid), CAST(:c AS uuid), 'AGENTE DE PORTARIA', :d, true, 'alocar', "
                "'alocacao_de_vaga', :o)"
            ),
            {"e": emp, "c": cond, "d": admissao, "o": f"{FIX} alocação de origem"},
        )
        await db.commit()

        antes_emp = (await db.execute(text(SQL_FOTO_EMP), {"e": emp})).first()
        antes_per = (await db.execute(text(SQL_PERIODOS), {"e": emp})).first()
        antes_dep = (await db.execute(text(SQL_DEPS), {"e": emp})).scalar()
        antes_cont = (await db.execute(text(SQL_CONT))).first()
        antes_gov = (await db.execute(text(SQL_EVENTOS_GOV))).first()

        # b. simular não escreve e mostra os dois lados
        sim = await tr.simular(
            db,
            employee_id=emp,
            empresa_destino_cnpj=CNPJ_PATRIMONIAL,
            data=hoje,
            novo_cargo_id=cargo_novo[0],
            novo_salario="2500.00",
        )
        muda = {k.lower() for k in (sim.get("muda") or {})}
        nao = {k.lower() for k in (sim.get("nao_muda") or {})}
        ok(
            {"empresa", "cargo", "salario"} <= muda,
            f"(b) simular lista empresa/cargo/salário no que MUDA: {sorted(muda)}",
        )
        ok(
            {"data_de_admissao", "periodo_aquisitivo_de_ferias", "dependentes"} <= nao,
            f"(b) simular lista admissão/período aquisitivo/dependentes no que NÃO muda: {sorted(nao)}",
        )
        depois_sim = (await db.execute(text(SQL_FOTO_EMP), {"e": emp})).first()
        ok(tuple(depois_sim) == tuple(antes_emp), "(b) simular não escreveu nada no colaborador")

        # c/d/e. efetivar
        t1 = await tr.criar(
            db,
            employee_id=emp,
            empresa_destino_cnpj=CNPJ_PATRIMONIAL,
            data=hoje,
            motivo="10",
            novo_cargo_id=cargo_novo[0],
            novo_salario="2500.00",
            observacao=f"{FIX} transferência 1",
        )
        await tr.efetivar(db, transferencia_id=t1["id"])

        depois_emp = (await db.execute(text(SQL_FOTO_EMP), {"e": emp})).first()
        depois_per = (await db.execute(text(SQL_PERIODOS), {"e": emp})).first()
        depois_dep = (await db.execute(text(SQL_DEPS), {"e": emp})).scalar()
        ok(depois_emp[0] == antes_emp[0], f"(c) data de admissão intacta: {antes_emp[0]} → {depois_emp[0]}")
        ok(
            tuple(depois_per) == tuple(antes_per),
            f"(c) período aquisitivo intacto (nº, âncora, saldo): {tuple(antes_per)} → {tuple(depois_per)}",
        )
        ok(depois_dep == antes_dep, f"(c) dependentes intactos: {antes_dep} → {depois_dep}")
        ok(depois_emp[4] == "ativo" and depois_emp[5] is None, "(c) continua ATIVO e sem data de demissão")
        ok(
            (antes_emp[1] or "").endswith("0001-03") and (depois_emp[1] or "").endswith("0001-10"),
            f"(c) empresa trocou: {antes_emp[1]} → {depois_emp[1]}",
        )
        ok(str(depois_emp[3]) == "2500.00", f"(c) novo salário aplicado: {depois_emp[3]}")

        props = (await db.execute(text(SQL_PROPOSTAS), {"r": f"transferencia:{t1['id']}"})).fetchall()
        ok(len(props) == 2, f"(d) exatamente 2 rascunhos de eSocial: {len(props)}")
        ok(
            {p[0] for p in props} == {"S-2200", "S-2299"},
            f"(d) os dois eventos certos: {sorted(p[0] for p in props)}",
        )
        ok(
            all(p[1] == "proposto" for p in props),
            f"(d) nenhum transmitido — todos 'proposto': {sorted({p[1] for p in props})}",
        )
        depois_gov = (await db.execute(text(SQL_EVENTOS_GOV))).first()
        ok(
            tuple(depois_gov) == tuple(antes_gov),
            f"(d) nada foi ao governo: eventos_esocial/espelho {tuple(antes_gov)} → {tuple(depois_gov)}",
        )

        aloc = (await db.execute(text(SQL_ALOC), {"e": emp})).fetchall()
        antiga = [a for a in aloc if not a[3]]
        nova = [a for a in aloc if a[3]]
        ok(len(nova) == 1, f"(e) exatamente uma alocação ativa depois: {len(nova)}")
        ok(
            len(antiga) == 1 and antiga[0][2] == hoje - timedelta(days=1),
            f"(e) a da origem encerrada em D−1: {antiga and antiga[0][2]}",
        )
        ok(bool(nova) and nova[0][1] == hoje, f"(e) a nova começa em D: {nova and nova[0][1]}")
        ok(
            bool(nova) and bool(antiga) and antiga[0][2] + timedelta(days=1) == nova[0][1],
            "(e) sem buraco e sem sobreposição entre a de origem e a nova",
        )

        depois_cont = (await db.execute(text(SQL_CONT))).first()
        ok(
            tuple(depois_cont) == tuple(antes_cont),
            f"(h) sem rescisão nem admissão nova: termination/admission {tuple(antes_cont)} → {tuple(depois_cont)}",
        )

        # f. cancelar rascunho não muda nada
        t2 = await tr.criar(
            db,
            employee_id=emp,
            empresa_destino_cnpj=CNPJ_ELETRONICA,
            data=hoje + timedelta(days=1),
            motivo="11",
            observacao=f"{FIX} transferência 2 (cancelada)",
        )
        foto_a = (await db.execute(text(SQL_FOTO_EMP), {"e": emp})).first()
        aloc_a = (await db.execute(text(SQL_ALOC), {"e": emp})).fetchall()
        n_prop_a = (
            await db.execute(
                text("SELECT count(*) FROM esocial_transmissao_propostas WHERE referencia LIKE :f"),
                {"f": "transferencia:%"},
            )
        ).scalar()
        await tr.cancelar(db, transferencia_id=t2["id"])
        foto_b = (await db.execute(text(SQL_FOTO_EMP), {"e": emp})).first()
        aloc_b = (await db.execute(text(SQL_ALOC), {"e": emp})).fetchall()
        n_prop_b = (
            await db.execute(
                text("SELECT count(*) FROM esocial_transmissao_propostas WHERE referencia LIKE :f"),
                {"f": "transferencia:%"},
            )
        ).scalar()
        ok(tuple(foto_a) == tuple(foto_b), "(f) cancelar não mexeu no colaborador")
        ok([tuple(r) for r in aloc_a] == [tuple(r) for r in aloc_b], "(f) cancelar não mexeu nas alocações")
        ok(n_prop_a == n_prop_b, f"(f) cancelar não criou rascunho de eSocial: {n_prop_a} → {n_prop_b}")
        st = (
            await db.execute(text("SELECT status FROM dp_transferencias WHERE id = CAST(:i AS uuid)"), {"i": t2["id"]})
        ).scalar()
        ok(st == "cancelada", f"(f) o rascunho ficou 'cancelada': {st}")

        # g. régua de conferência
        # g1 — o real: GEILSON tem S-2299 mtvDeslig=11 no espelho e nenhuma transferência aqui.
        r = await tr.regua(db)
        cpfs_gov = {x["cpf"] for x in r["so_no_governo"]}
        tem_geilson = (
            await db.execute(
                text(
                    "SELECT count(*) FROM esocial_eventos_espelho WHERE tipo='S-2299' AND cpf_trabalhador = :c "
                    "AND (regexp_match(xml_completo,'<[^>]*mtvDeslig>([^<]+)<'))[1] IN ('10','11')"
                ),
                {"c": CPF_GEILSON},
            )
        ).scalar()
        if tem_geilson:
            ok(
                CPF_GEILSON in cpfs_gov,
                f"(g) a régua acha quem está transferido só no governo (GEILSON): {sorted(cpfs_gov)}",
            )
        else:
            ok(False, "(g) o espelho do sandbox não tem mais o S-2299 10/11 do GEILSON — refazer a medição")

        # g2 — o fixture está CASADO (espelho + transferência efetivada): não pode aparecer em lado nenhum.
        await db.execute(
            text(
                "INSERT INTO esocial_eventos_espelho (id_evento, tipo, cpf_trabalhador, dt_evento, download_status, xml_completo, baixado_em) "
                "VALUES (:i, 'S-2299', :c, :d, 'ok', :x, now())"
            ),
            {
                "i": f"{FIX}-S2299-01",
                "c": "11144477735",
                "d": hoje,
                "x": "<eSocial><evtDeslig><infoDeslig><mtvDeslig>10</mtvDeslig></infoDeslig></evtDeslig></eSocial>",
            },
        )
        await db.commit()
        r2 = await tr.regua(db)
        ok(
            "11144477735" not in {x["cpf"] for x in r2["so_no_governo"]},
            "(g) quem está casado (governo + sistema) NÃO aparece como 'só no governo'",
        )
        ok(
            "11144477735" not in {x["cpf"] for x in r2["so_no_sistema"]},
            "(g) quem está casado NÃO aparece como 'só no sistema'",
        )
        ok(
            any(x["cpf"] == "11144477735" for x in r2["casados"]),
            "(g) quem está casado aparece na lista de conferidos",
        )

        # i. limpeza
        for sql in SQL_LIMPA:
            await db.execute(text(sql), {"f": FIX + "%"})
        await db.commit()
        sobrou = (
            await db.execute(
                text(
                    "SELECT (SELECT count(*) FROM employees WHERE nome LIKE :f) "
                    "     + (SELECT count(*) FROM dp_transferencias WHERE observacao LIKE :f) "
                    "     + (SELECT count(*) FROM esocial_eventos_espelho WHERE id_evento LIKE :f) "
                    "     + (SELECT count(*) FROM esocial_transmissao_propostas WHERE referencia = ANY(:r))"
                ),
                {"f": FIX + "%", "r": [f"transferencia:{t1['id']}", f"transferencia:{t2['id']}"]},
            )
        ).scalar()
        ok(sobrou == 0, f"(i) fixtures apagadas ao fim: {sobrou} sobrando")
        fim_cont = (await db.execute(text(SQL_CONT))).first()
        ok(tuple(fim_cont) == tuple(antes_cont), f"(h) termination/admission no fim: {tuple(fim_cont)}")

    print(f"TOTAL falhas transferência W4: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
