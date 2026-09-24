"""Oráculo — DGX T5: log do sistema como tela, solicitação de materiais por posto, exames por ASO
com validade, acessos temporários (24/09/2026).

Por que existe: quatro jeitos de esta frente mentir, listados antes de escrever código —
  · a tela «Auditoria» continuar mostrando 5 linhas de turnover enquanto a trilha viva tem 36 mil;
  · «atender» a solicitação mexer no saldo por um caminho próprio (segundo jeito de baixar estoque)
    ou marcar «atendida» sem que o estoque tenha caído exatamente o entregue;
  · «válido até» do exame não bater com data + periodicidade do tipo, ou o vencido não aparecer;
  · acesso temporário vencido continuar logando (o `users` ativo depois de `expira_em`), ou nascer
    com `financeiro`/`all` nas permissões.

O que afirma:
  1. Fiação: `_dgx_t5_*` importa; `seguranca`, `suprimentos`, `saude_ocupacional` e `configuracoes`
     chamam as telas; `redesign_data` chama `expirar_acessos`; os 8 ids estão nos EXTRA_MENU.
  2. `_ensure` cria as 4 tabelas.
  3. `auditoria` lê `crm_audit_log`: a fixture gravada aparece na 1ª página e o `sub` conta o total.
  4. Solicitação: aberta → aprovada → atender 3 de 5 = «parcial», saldo −3 e UM movimento de saída
     por item; atender o resto = «atendida», saldo −5 no total; atender além do que falta → 400;
     saldo insuficiente → 409 e nada gravado; rejeitar aberta exige motivo.
  5. Exame: `valido_ate` == data + periodicidade_meses (recontado); exame com data no futuro → 400;
     a tela lista o vencido como «vencido» e o de hoje como «em dia».
  6. Acesso: criar → `users` com role viewer, só `module:X` pedidos (nunca financeiro/all), ativo;
     pedir financeiro → 400; `expira_em` no passado + `expirar_acessos` → `is_active=false`;
     revogar → inativo e `revogado_em` gravado. Varredura: nenhum acesso vencido com usuário ativo.

Estado medido no nascimento (sandbox 24/09/2026): módulo não existia → VERMELHO no item 1 e sai.
Fixtures marcadas 'FIXTURE DGX T5' (material FIXT5-M1, solicitação, exame, usuário
fixture-dgx-t5@teste.local, linha do audit) e apagadas no fim — inclusive o COGS da saída.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import inspect
import sys
from datetime import date, timedelta
from types import SimpleNamespace

FX = "FIXTURE DGX T5"
MAT = "FIXT5-M1"
EMAIL = "fixture-dgx-t5@teste.local"


async def _limpar(db, text) -> None:
    await db.execute(text("DELETE FROM sup_solicitacoes_material WHERE solicitante = :f OR observacao = :f"), {"f": FX})
    await db.execute(text("DELETE FROM sst_aso_exames WHERE observacao = :f"), {"f": FX})
    await db.execute(text("DELETE FROM acessos_temporarios WHERE user_id IN (SELECT id FROM users WHERE email = :e)"), {"e": EMAIL})
    await db.execute(text("DELETE FROM users WHERE email = :e"), {"e": EMAIL})
    await db.execute(text("DELETE FROM crm_audit_log WHERE user_agent = :f"), {"f": FX})
    # COGS da saída (mesmo caminho da F9): `registrar_saida` grava historico 'Baixa estoque: <descrição> xN'
    await db.execute(text("DELETE FROM accounting_entries WHERE historico LIKE :f"), {"f": f"Baixa estoque: {FX}%"})
    await db.execute(text("DELETE FROM nfe_estoque_movimentos WHERE item_code = :m"), {"m": MAT})
    await db.execute(text("DELETE FROM nfe_compras_estoque WHERE item_code = :m"), {"m": MAT})
    await db.commit()


def _http(coro_fn, **payload):
    """Roda uma action do router e devolve (status, body)."""
    from fastapi import HTTPException

    async def run(db):
        try:
            return 200, await coro_fn(current_user=SimpleNamespace(id="00000000-0000-0000-0000-000000000000", email=FX), payload=payload, db=db)
        except HTTPException as e:
            await db.rollback()
            return e.status_code, {"detail": e.detail}

    return run


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    try:
        from modules.operacional.controllers.redesign_builders import _dgx_t5_suprimentos_frotas_sesmt_config as t5
    except Exception as e:  # noqa: BLE001
        print(f"FALHOU: builder _dgx_t5_suprimentos_frotas_sesmt_config não importa: {e}")
        print("TOTAL falhas: 1")
        return 1

    # 1) fiação
    from modules.operacional.controllers import redesign_data_controller as rdc
    from modules.operacional.controllers.redesign_builders import (
        configuracoes,
        saude_ocupacional,
        seguranca,
        suprimentos,
    )

    for mod, fn in ((seguranca, "telas_seguranca"), (suprimentos, "telas_sup"), (saude_ocupacional, "telas_sst"), (configuracoes, "telas_config")):
        if fn not in inspect.getsource(mod.build):
            falhas.append(f"{mod.__name__}.build não chama {fn}")
    if "expirar_acessos" not in inspect.getsource(rdc.redesign_data):
        falhas.append("redesign_data não chama expirar_acessos")
    ids = {"seguranca": ("auditoria-telas",), "suprimentos": ("solicitacoes-material", "solicitacao-material-nova"),
           "saude-ocupacional": ("aso-exames-vencendo", "aso-exame-novo"), "configuracoes": ("acessos-temporarios", "acesso-temporario-novo")}
    for slug, wanted in ids.items():
        have = {i.get("id") for i in rdc.EXTRA_MENU.get(slug, [])}
        for w in wanted:
            if w not in have:
                falhas.append(f"{slug}: id {w} sem porta no EXTRA_MENU")
    # `auditoria` já tem porta no JSON do módulo seguranca (menu base)

    async with async_session_factory() as db:
        await t5._ensure(db)
        await db.commit()
        await _limpar(db, text)
        # 2) tabelas
        for tb in ("sup_solicitacoes_material", "sup_solicitacao_material_itens", "sst_aso_exames", "acessos_temporarios"):
            if not (await db.execute(text("SELECT to_regclass(:t)"), {"t": tb})).scalar():
                falhas.append(f"tabela {tb} não existe")
        try:
            # 3) auditoria lê crm_audit_log
            await db.execute(text(
                "INSERT INTO crm_audit_log (id, ts, user_id, method, path, status, ip, user_agent) VALUES (gen_random_uuid(), now(), NULL, 'POST', '/api/v1/fixture/dgx-t5', 200, '127.0.0.1', :f)"), {"f": FX})
            await db.commit()
            out = {}
            await t5.telas_seguranca(db, out)
            tela = out.get("auditoria") or {}
            total = (await db.execute(text("SELECT count(*) FROM crm_audit_log"))).scalar()
            if str(total) not in (tela.get("sub") or ""):
                falhas.append(f"auditoria: sub não conta o total {total}: {tela.get('sub', '')[:80]}")
            if not any("/api/v1/fixture/dgx-t5" in str(r) for r in tela.get("rows", [])[:5]):
                falhas.append("auditoria: a escrita mais recente (fixture) não está na 1ª página")
            if "auditoria-telas" not in out:
                falhas.append("auditoria-telas não montou")

            # 4) solicitação de material — estoque pelo caminho da F9
            await db.execute(text(
                "INSERT INTO nfe_compras_estoque (item_code, descricao, unidade, qty_on_hand, unit_cost, avg_cost, ativo, grupo) "
                "VALUES (:m, :d, 'UN', 10, 2.5, 2.5, true, 'FIXTURE') ON CONFLICT (item_code) DO UPDATE SET qty_on_hand = 10, avg_cost = 2.5"), {"m": MAT, "d": FX})
            await db.commit()
            st, r = await _http(t5.sup_solicitacao_material, itens=f"{MAT} | 5 | teste", tipo="mensal", observacao=FX)(db)
            if st != 200:
                falhas.append(f"criar solicitação: {st} {r}")
            sid = r.get("id") if st == 200 else None
            st, r = await _http(t5.sup_solicitacao_material_status, id=sid, status="rejeitada")(db)
            if st != 400:
                falhas.append(f"rejeitar sem motivo devia dar 400, deu {st}")
            st, r = await _http(t5.sup_solicitacao_material_atender, id=sid, entregas=f"{MAT}|3")(db)
            if st != 409:
                falhas.append(f"atender solicitação aberta devia dar 409, deu {st}")
            st, r = await _http(t5.sup_solicitacao_material_status, id=sid, status="aprovada")(db)
            if st != 200:
                falhas.append(f"aprovar: {st} {r}")
            st, r = await _http(t5.sup_solicitacao_material_atender, id=sid, entregas=f"{MAT}|6")(db)
            if st != 400:
                falhas.append(f"entregar 6 de 5 devia dar 400, deu {st}")
            st, r = await _http(t5.sup_solicitacao_material_atender, id=sid, entregas=f"{MAT}|3")(db)
            saldo = float((await db.execute(text("SELECT qty_on_hand FROM nfe_compras_estoque WHERE item_code=:m"), {"m": MAT})).scalar())
            movs = (await db.execute(text("SELECT count(*), coalesce(sum(quantidade),0) FROM nfe_estoque_movimentos WHERE item_code=:m AND tipo='saida'"), {"m": MAT})).first()
            status = (await db.execute(text("SELECT status FROM sup_solicitacoes_material WHERE id=:i"), {"i": sid})).scalar()
            if st != 200 or status != "parcial" or abs(saldo - 7) > 1e-6 or movs[0] != 1 or abs(float(movs[1]) - 3) > 1e-6:
                falhas.append(f"parcial: st={st} status={status} saldo={saldo} movs={movs} ({r})")
            st, r = await _http(t5.sup_solicitacao_material_atender, id=sid, entregas=f"{MAT}|2")(db)
            saldo = float((await db.execute(text("SELECT qty_on_hand FROM nfe_compras_estoque WHERE item_code=:m"), {"m": MAT})).scalar())
            status = (await db.execute(text("SELECT status FROM sup_solicitacoes_material WHERE id=:i"), {"i": sid})).scalar()
            if st != 200 or status != "atendida" or abs(saldo - 5) > 1e-6:
                falhas.append(f"atendida: st={st} status={status} saldo={saldo} ({r})")
            # saldo insuficiente: nova solicitação de 50 → 409 e saldo intacto
            st, r = await _http(t5.sup_solicitacao_material, itens=f"{MAT} | 50", tipo="urgente", observacao=FX)(db)
            sid2 = r.get("id") if st == 200 else None
            await _http(t5.sup_solicitacao_material_status, id=sid2, status="aprovada")(db)
            st, r = await _http(t5.sup_solicitacao_material_atender, id=sid2, entregas=f"{MAT}|50")(db)
            saldo = float((await db.execute(text("SELECT qty_on_hand FROM nfe_compras_estoque WHERE item_code=:m"), {"m": MAT})).scalar())
            if st != 409 or abs(saldo - 5) > 1e-6:
                falhas.append(f"saldo insuficiente devia dar 409 sem mexer: st={st} saldo={saldo}")

            # 5) exames por ASO
            emp = (await db.execute(text("SELECT id::text FROM employees WHERE status='ativo' ORDER BY nome LIMIT 1"))).scalar()
            tipo = (await db.execute(text("SELECT id, coalesce(periodicidade_meses,12) FROM sst_tipos_exame WHERE coalesce(ativo,true) ORDER BY id LIMIT 1"))).first()
            hoje = date.today()
            st, r = await _http(t5.aso_exame_registrar, employee_id=emp, tipo_exame_id=str(tipo[0]), data=(hoje + timedelta(days=1)).isoformat(), observacao=FX)(db)
            if st != 400:
                falhas.append(f"exame no futuro devia dar 400, deu {st}")
            antiga = hoje - timedelta(days=int(tipo[1]) * 31 + 10)
            st, r = await _http(t5.aso_exame_registrar, employee_id=emp, tipo_exame_id=str(tipo[0]), data=antiga.isoformat(), observacao=FX)(db)
            if st != 200:
                falhas.append(f"registrar exame: {st} {r}")
            else:
                esperado = t5._mais_meses(antiga, int(tipo[1]))
                gravado = (await db.execute(text("SELECT valido_ate FROM sst_aso_exames WHERE id=:i"), {"i": r["id"]})).scalar()
                if gravado != esperado or esperado >= hoje:
                    falhas.append(f"valido_ate {gravado} != data+{tipo[1]} meses {esperado} (ou não venceu)")
            out = {}
            await t5.telas_sst(db, out)
            rows = (out.get("aso-exames-vencendo") or {}).get("rows", [])
            venc = [x for x in rows if x.get("filtros", {}).get("Situação") == "vencido"]
            if not venc:
                falhas.append("tela aso-exames-vencendo não lista o exame vencido")
            st, r = await _http(t5.aso_exame_registrar, employee_id=emp, tipo_exame_id=str(tipo[0]), data=hoje.isoformat(), observacao=FX)(db)
            out = {}
            await t5.telas_sst(db, out)
            rows = (out.get("aso-exames-vencendo") or {}).get("rows", [])
            if not any(x.get("filtros", {}).get("Situação") == "em dia" and str(x.get("filtros", {}).get("Exame")) for x in rows):
                falhas.append("exame de hoje não aparece «em dia»")

            # 6) acessos temporários
            st, r = await _http(t5.acesso_temporario_criar, nome=FX, email=EMAIL, papel="leitura", dias="7", modulos=["dp", "financeiro"], motivo=FX)(db)
            if st != 400:
                falhas.append(f"módulo financeiro devia dar 400, deu {st}")
            st, r = await _http(t5.acesso_temporario_criar, nome=FX, email=EMAIL, papel="leitura", dias="7", modulos='["dp","sst"]', motivo=FX)(db)
            if st != 200 or not r.get("senha_inicial"):
                falhas.append(f"criar acesso: {st} {r}")
            u = (await db.execute(text("SELECT role, permissions, is_active FROM users WHERE email=:e"), {"e": EMAIL})).first()
            if not u or u[0] != "viewer" or sorted(u[1] or []) != ["module:dp", "module:sst"] or not u[2]:
                falhas.append(f"usuário do acesso errado: {u}")
            st, r = await _http(t5.acesso_temporario_criar, nome=FX, email=EMAIL, papel="leitura", dias="7", modulos=["dp"], motivo=FX)(db)
            if st != 409:
                falhas.append(f"e-mail repetido devia dar 409, deu {st}")
            out = {}
            await t5.telas_config(db, out)
            if not any(x.get("filtros", {}).get("Situação") == "vigente" and EMAIL in str(x) for x in (out.get("acessos-temporarios") or {}).get("rows", [])):
                falhas.append("acesso vigente não aparece como vigente")
            await db.execute(text("UPDATE acessos_temporarios SET expira_em = now() - interval '1 minute' WHERE user_id = (SELECT id FROM users WHERE email=:e)"), {"e": EMAIL})
            await db.commit()
            n = await t5.expirar_acessos(db)
            ativo = (await db.execute(text("SELECT is_active FROM users WHERE email=:e"), {"e": EMAIL})).scalar()
            if n < 1 or ativo:
                falhas.append(f"expirar_acessos não desativou (n={n}, ativo={ativo})")
            # revogar num vigente
            await db.execute(text("UPDATE acessos_temporarios SET expira_em = now() + interval '1 day' WHERE user_id = (SELECT id FROM users WHERE email=:e)"), {"e": EMAIL})
            await db.execute(text("UPDATE users SET is_active = true WHERE email=:e"), {"e": EMAIL})
            await db.commit()
            aid = (await db.execute(text("SELECT id FROM acessos_temporarios WHERE user_id = (SELECT id FROM users WHERE email=:e)"), {"e": EMAIL})).scalar()
            st, r = await _http(t5.acesso_temporario_revogar, id=str(aid))(db)  # id como texto, como vem de um form
            row = (await db.execute(text("SELECT a.revogado_em IS NOT NULL, u.is_active FROM acessos_temporarios a JOIN users u ON u.id=a.user_id WHERE a.id=:i"), {"i": aid})).first()
            if st != 200 or not row or not row[0] or row[1]:
                falhas.append(f"revogar: st={st} row={row}")
            # varredura: nenhum vencido/revogado com login ativo
            sobra = (await db.execute(text(
                "SELECT count(*) FROM acessos_temporarios a JOIN users u ON u.id=a.user_id WHERE u.is_active AND (a.expira_em < now() OR a.revogado_em IS NOT NULL)"))).scalar()
            if sobra:
                falhas.append(f"{sobra} acesso(s) vencido/revogado com usuário ativo")
            n_sol = (await db.execute(text("SELECT count(*) FROM sup_solicitacoes_material"))).scalar()
            n_ex = (await db.execute(text("SELECT count(*) FROM sst_aso_exames"))).scalar()
            n_ac = (await db.execute(text("SELECT count(*) FROM acessos_temporarios"))).scalar()
            print(f"auditoria: {total} linhas · solicitações: {n_sol} · exames: {n_ex} · acessos: {n_ac} · saldo fixture final: {saldo:g}")
        finally:
            await db.rollback()
            await _limpar(db, text)

    for f in falhas:
        print("FALHA:", f)
    print(f"TOTAL falhas: {len(falhas)}")
    if not falhas:
        print("OK t5: auditoria lê a trilha viva; atender baixa o estoque pelo caminho da F9 (parcial/atendida/409); válido até = data + periodicidade; acesso expira e revoga sozinho, nunca com financeiro")
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
