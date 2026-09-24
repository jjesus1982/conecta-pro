"""Oráculo — SESMT (tipos de exame, médicos), Demandas (assuntos, atendimentos) e Comercial
(fontes pagadoras, regiões, postos por cliente) — DGX F12, 24/09/2026.

Por que existe: o DGX trata exame, médico, assunto, fonte pagadora e região como CADASTRO; aqui
isso vivia em texto solto (`gp_asos.medico` = 'Dr. Carlos Mendes' em 96 linhas, PCMSO em jsonb
lido por OCR) ou não existia. O pré-mortem listou cinco jeitos de a frente mentir: matriz de
exames que conta ASO vencido diferente da aba «Exames»/`asos_vencendo`; atendimento resolvido
antes de aberto; manifestação de ouvidoria migrada (duplicada) em vez de lida; CNPJ inválido
gravado como fonte pagadora; posto «alocado hoje» contado por tabela que não é a da grade.

O que afirma:
  1. `_dgx_f12_sesmt_demandas_comercial` importa; `saude_ocupacional.build`, `crm.build`,
     `departamento_pessoal.build` e `financeiro.build` chamam as telas (fiação).
  2. `_ensure` cria as 6 tabelas e as 3 colunas; seed: médico do PCMSO e ≥ 1 tipo de exame.
  3. Por função, «vencidos» da matriz == recontado por SQL próprio (último ASO do ativo < hoje ou
     sem ASO realizado) — mesma régua da aba Exames/`asos_vencendo`.
  4. Atendimento: resolvido_em ≥ aberto_em é CHECK do banco (inserção inválida falha); a regra
     pura `sla_vencido` acusa 5h com SLA 4h e libera 1h com SLA 4h; resolver grava resolvido_em.
  5. As manifestações de `ouvidoria_manifestacoes` e os chamados de `client_portal_tickets`
     aparecem em `listar_atendimentos` sem duplicar: total == dem_atendimentos + ouvidoria +
     portal; nenhuma linha de dem_atendimentos com ref_tipo ouvidoria/portal (leitura, não migração).
  6. Fonte pagadora: CNPJ inválido é recusado; válido (`validar_cnpj`) é gravado.
  7. Região sem supervisor aparece em `regioes_sem_supervisor`.
  8. Postos por cliente: contratado == posts.required_headcount e alocado hoje == count de
     `allocations` ativas (a fonte de `grade_do_posto`), posto a posto.

Estado medido no nascimento (sandbox 24/09/2026): módulo não existia → VERMELHO no item 1 e
sai. Fixtures marcadas 'FIXTURE DGX F12' e apagadas no fim.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import UTC, datetime, timedelta

FX = "FIXTURE DGX F12"

#: régua reescrita de propósito: último ASO do ativo (max data_validade) < hoje, ou sem ASO realizado.
SQL_VENCIDOS_POR_CARGO = """
SELECT e.id::text, e.cargo
FROM employees e
WHERE e.status='ativo'
  AND (
    NOT EXISTS (SELECT 1 FROM gp_asos a WHERE a.employee_id=e.id AND a.status='realizado')
    OR (SELECT max(a.data_validade) FROM gp_asos a WHERE a.employee_id=e.id AND a.data_validade IS NOT NULL)
       < (now() AT TIME ZONE 'America/Manaus')::date
  )
"""

SQL_ALOCADOS_POSTO = """
SELECT p.id::text, p.required_headcount,
       (SELECT count(*) FROM allocations a WHERE a.post_id=p.id AND a.status='active' AND a.is_active)
FROM posts p WHERE coalesce(p.is_active,true)
"""


async def _limpar(db, text) -> None:
    """Apaga só o que este oráculo criou (marcado FIXTURE DGX F12)."""
    await db.execute(text("DELETE FROM dem_atendimentos WHERE descricao=:d"), {"d": FX})
    await db.execute(text("DELETE FROM dem_assuntos WHERE nome=:d"), {"d": FX})
    await db.execute(text("DELETE FROM crm_fontes_pagadoras WHERE razao_social=:d"), {"d": FX})
    await db.execute(text("DELETE FROM crm_regioes WHERE nome=:d"), {"d": FX})
    await db.commit()


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    try:
        from modules.operacional.controllers.redesign_builders import _dgx_f12_sesmt_demandas_comercial as f12
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: builder _dgx_f12_sesmt_demandas_comercial não importa: {e}")
        print("TOTAL falhas: 1")
        return 1
    for mod, fn in (
        ("saude_ocupacional", "telas_sst"),
        ("crm", "telas_crm"),
        ("departamento_pessoal", "ligar_aso_form"),
        ("financeiro", "telas_fin"),
    ):
        try:
            m = __import__(f"modules.operacional.controllers.redesign_builders.{mod}", fromlist=["build"])
            if "f12" not in inspect.getsource(m.build):
                falhas.append(f"{mod}.build() não chama _dgx_f12.{fn} — tela sem porta")
        except Exception as e:  # noqa: BLE001
            falhas.append(f"{mod} não importa: {e}")

    # 4a) regra pura
    t0 = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)
    if not f12.sla_vencido(t0, 4, t0 + timedelta(hours=5)):
        falhas.append("sla_vencido(5h, SLA 4h) devolveu False")
    if f12.sla_vencido(t0, 4, t0 + timedelta(hours=1)):
        falhas.append("sla_vencido(1h, SLA 4h) devolveu True")

    async with async_session_factory() as db:
        await f12._ensure(db)
        await _limpar(db, text)  # sobra de rodada anterior que quebrou no meio
        # 2) tabelas e colunas
        for tb in (
            "sst_tipos_exame",
            "sst_medicos",
            "dem_assuntos",
            "dem_atendimentos",
            "crm_fontes_pagadoras",
            "crm_regioes",
        ):
            if not (await db.execute(text("SELECT to_regclass(:t)"), {"t": tb})).scalar():
                falhas.append(f"tabela {tb} não existe após _ensure")
        for tb, col in (("clients", "regiao_id"), ("posts", "regiao_id"), ("receivable_accounts", "fonte_pagadora_id")):
            n = (
                await db.execute(
                    text("SELECT count(*) FROM information_schema.columns WHERE table_name=:t AND column_name=:c"),
                    {"t": tb, "c": col},
                )
            ).scalar()
            if not n:
                falhas.append(f"coluna {tb}.{col} não existe após _ensure")
        n_med = (await db.execute(text("SELECT count(*) FROM sst_medicos WHERE responsavel_pcmso"))).scalar()
        n_pcmso = (
            await db.execute(text("SELECT count(*) FROM sst_pcmso WHERE medico_coordenador IS NOT NULL"))
        ).scalar()
        if n_pcmso and not n_med:
            falhas.append("PCMSO tem médico coordenador e sst_medicos não tem responsavel_pcmso")
        if not (await db.execute(text("SELECT count(*) FROM sst_tipos_exame"))).scalar():
            falhas.append("sst_tipos_exame vazia após seed")

        # 3) matriz × recontagem
        esperado: dict[str, set[str]] = {}
        for eid, cargo in (await db.execute(text(SQL_VENCIDOS_POR_CARGO))).all():
            esperado.setdefault(f12.norm(cargo), set()).add(eid)
        obtido = await f12.vencidos_por_funcao(db)
        for fn, ids in esperado.items():
            got = set(obtido.get(fn, {}).get("vencidos", []))
            if got != ids:
                falhas.append(f"função {fn}: matriz conta {len(got)} vencidos, SQL conta {len(ids)}")
        for fn, d in obtido.items():
            if fn not in esperado and d.get("vencidos"):
                falhas.append(f"função {fn}: matriz tem vencidos que o SQL não tem")

        # 4b) CHECK do banco + resolver
        aid = (
            await db.execute(
                text("INSERT INTO dem_assuntos (nome, area, sla_horas) VALUES (:n, 'operacional', 4) RETURNING id"),
                {"n": FX},
            )
        ).scalar()
        try:
            await db.execute(
                text(
                    "INSERT INTO dem_atendimentos (assunto_id, origem, descricao, status, aberto_em, resolvido_em) "
                    "VALUES (:a, 'telefone', :d, 'resolvido', now(), now() - interval '1 hour')"
                ),
                {"a": aid, "d": FX},
            )
            falhas.append("banco aceitou resolvido_em < aberto_em")
            await db.rollback()
        except Exception:  # noqa: BLE001
            await db.rollback()
        # rollback desfez o assunto também — recria
        aid = (
            await db.execute(
                text("INSERT INTO dem_assuntos (nome, area, sla_horas) VALUES (:n, 'operacional', 4) RETURNING id"),
                {"n": FX},
            )
        ).scalar()
        atid = (
            await db.execute(
                text(
                    "INSERT INTO dem_atendimentos (assunto_id, origem, descricao, status, aberto_em) "
                    "VALUES (:a, 'telefone', :d, 'aberto', now() - interval '5 hours') RETURNING id"
                ),
                {"a": aid, "d": FX},
            )
        ).scalar()
        await db.commit()
        await f12.resolver_atendimento(db, atid, "resolvido no oráculo", 5, "oraculo")
        row = (
            await db.execute(
                text("SELECT status, aberto_em, resolvido_em, satisfacao FROM dem_atendimentos WHERE id=:i"),
                {"i": atid},
            )
        ).first()
        if row[0] != "resolvido" or row[2] is None or row[2] < row[1] or row[3] != 5:
            falhas.append(f"resolver_atendimento não gravou como esperado: {row}")
        if not f12.sla_vencido(row[1], 4, row[2]):
            falhas.append("atendimento aberto há 5h com SLA 4h não acusou SLA vencido")

        # 5) ouvidoria: lida, não migrada
        n_ouv = (await db.execute(text("SELECT count(*) FROM ouvidoria_manifestacoes"))).scalar()
        n_por = (await db.execute(text("SELECT count(*) FROM client_portal_tickets"))).scalar()
        n_dem = (await db.execute(text("SELECT count(*) FROM dem_atendimentos"))).scalar()
        lista = await f12.listar_atendimentos(db)
        n_lista_ouv = sum(1 for x in lista if x["origem"] == "ouvidoria")
        n_lista_por = sum(1 for x in lista if x["origem"] == "portal" and x["id"] is None)
        if n_lista_ouv != n_ouv or n_lista_por != n_por or len(lista) != n_dem + n_ouv + n_por:
            falhas.append(
                f"atendimentos: lista {len(lista)} (ouvidoria {n_lista_ouv}, portal {n_lista_por}) "
                f"≠ dem {n_dem} + ouvidoria {n_ouv} + portal {n_por}"
            )
        if (
            await db.execute(text("SELECT count(*) FROM dem_atendimentos WHERE ref_tipo IN ('ouvidoria','portal')"))
        ).scalar():
            falhas.append("há manifestação de ouvidoria/portal MIGRADA para dem_atendimentos (devia ser só leitura)")

        # 6) fonte pagadora
        cli = (await db.execute(text("SELECT id::text FROM clients ORDER BY created_at LIMIT 1"))).scalar()
        try:
            await f12.salvar_fonte_pagadora(db, {"cliente_id": cli, "razao_social": FX, "cnpj": "11.111.111/1111-11"})
            falhas.append("fonte pagadora com CNPJ inválido foi aceita")
        except Exception:  # noqa: BLE001
            await db.rollback()
        fid = await f12.salvar_fonte_pagadora(db, {"cliente_id": cli, "razao_social": FX, "cnpj": "35.710.481/0001-03"})
        if not (
            await db.execute(
                text("SELECT count(*) FROM crm_fontes_pagadoras WHERE id=:i AND cnpj='35710481000103'"), {"i": fid}
            )
        ).scalar():
            falhas.append("fonte pagadora válida não gravada com CNPJ só dígitos")

        # 7) região sem supervisor
        rid = (
            await db.execute(
                text("INSERT INTO crm_regioes (nome, uf, municipios) VALUES (:n, 'AM', '[\"Manaus\"]') RETURNING id"),
                {"n": FX},
            )
        ).scalar()
        await db.commit()
        if rid not in {r["id"] for r in await f12.regioes_sem_supervisor(db)}:
            falhas.append("região sem supervisor não acusada")

        # 8) postos por cliente
        sql = {r[0]: (r[1] or 0, r[2]) for r in (await db.execute(text(SQL_ALOCADOS_POSTO))).all()}
        for p in await f12.postos_por_cliente(db):
            esp = sql.get(p["post_id"])
            if esp is None or (p["contratado"], p["alocado"]) != esp:
                falhas.append(f"posto {p['posto']}: tela {p['contratado']}×{p['alocado']} ≠ SQL {esp}")

        await _limpar(db, text)

    for f in falhas:
        print("FALHOU:", f)
    if not falhas:
        print(
            "OK: tipos de exame/médicos seedados do PCMSO e dos ASOs; matriz por função == SQL; "
            "atendimento com CHECK e SLA; ouvidoria lida sem migrar; CNPJ validado; região sem supervisor "
            "acusada; postos contratado×alocado == allocations"
        )
    print(f"TOTAL falhas: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
