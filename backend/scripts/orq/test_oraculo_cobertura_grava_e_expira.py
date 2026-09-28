"""Oráculo — aprovar `cobertura_posto` GRAVA em `substitutions`, e o rascunho EXPIRA em 2 dias.

🔴 O QUE ESTE ARQUIVO MEDE, e por que ele não é irmão do que já existe.

`test_oraculo_cobertura_e_hora_informada.py` (27/09/2026) prova que a CAPTURA recusa o que não
pode afirmar — nome ambíguo, nome inventado, quem tem batida — e que o tipo `cobertura_posto`
tem executor registrado. Tudo verdade, e `substitutions` continuava com **ZERO linhas**.

⭐ É o oráculo cúmplice de novo: só a RECUSA tinha irmã. Nada media o caminho feliz — se
aprovar na Central de fato ESCREVE. Registro que ninguém prova gravar é `registrar ≠ aplicar`.

## ⭐ E medindo o caminho feliz apareceu o defeito que faltava: o rascunho tem PAVIO.

`registrar_falta` (falta_substituto_controller.py:190-192) recusa com **422** qualquer turno que
não seja de HOJE ou de ONTEM — regra certa, é operação do dia, não correção de histórico. Mas o
rascunho da Central **não expira junto**. Um `cobertura_posto` criado em 27/09 e não decidido até
28/09 vira, em 29/09, um botão "Aprovar" que responde 500 e marca o rascunho como `falha`.

Medido em 28/09/2026: os 2 rascunhos de `cobertura_posto` da casa (THAYNA em 27/09, FERNANDO em
27/09) estavam vivos, com sino entregue e NÃO LIDO aos 3 aprovadores reais desde o dia anterior —
no último dia em que ainda podiam ser aprovados.

## As quatro invariantes

1. CAMINHO FELIZ: rascunho dentro da janela → aprovar pela ROTA grava linha em `substitutions`
   (`status='pending'`) e o turno vira `missed`. Se isto quebrar, a capacidade voltou a ser casca.
2. PAVIO: rascunho fora da janela → a rota recusa e o rascunho termina `falha` com o motivo
   GRAVADO (nunca 200 mentindo sucesso, nunca `erro_execucao` NULL).
3. ⭐ REGRA DO DIA A DIA: nenhum `cobertura_posto` com status `rascunho` pode estar fora da
   janela. Rascunho vivo fora da janela é botão que falha na mão do Orlailson.
4. APROVADOR REAL: existe pelo menos um `users.role` ATIVO em `roles_aprovador`. A casa já teve
   `e.status='ativo'` devolvendo zero aprovadores porque os reais eram `pj_ativo` — aqui se mede
   o papel de verdade, não o que o código declara.

⚠️ O que este oráculo escreve, ele apaga, e PROVA a limpeza por leitura. O turno de fixture usa
posto INATIVO + colaborador DEMITIDO justamente para não aparecer no quadro de ninguém no
intervalo de segundos em que existe.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

MARCA = "__ORACULO_COBERTURA_GRAVA__"
falhas: list[str] = []


def checar(cond: bool, titulo: str, detalhe: str = "") -> None:
    print(f"  {'OK   ' if cond else 'FALHA'} · {titulo}{(' — ' + detalhe) if detalhe else ''}")
    if not cond:
        falhas.append(titulo)


async def _contar(db, sql: str, params: dict | None = None) -> int:
    from sqlalchemy import text
    return (await db.execute(text(sql), params or {})).scalar() or 0


async def main() -> None:  # noqa: C901, PLR0915
    import httpx
    from sqlalchemy import select, text

    from core.auth.jwt import create_access_token
    from core.database import async_session_factory
    from core.models.user import User

    fixt_shift = str(uuid.uuid4())
    draft_ok = str(uuid.uuid4())
    draft_velho = str(uuid.uuid4())

    async with async_session_factory() as db:
        # ── 4. aprovador REAL (mede users.role, não o que o módulo declara) ───────────
        from modules.operacional.cobertura_posto import registrar  # noqa: F401  (existência)
        papeis = ("admin", "gerente_operacional")
        aprovadores = (await db.execute(text(
            "SELECT count(*) FROM users WHERE lower(role) = ANY(:r) AND is_active"),
            {"r": list(papeis)})).scalar() or 0
        checar(aprovadores > 0,
               "existe aprovador ATIVO com um dos roles_aprovador declarados",
               f"{aprovadores} usuário(s) em {papeis}")

        # ── 3. ⭐ nenhum rascunho VIVO fora da janela do executor ─────────────────────
        vencidos = (await db.execute(text(
            "SELECT id::text, titulo, payload->>'dia' FROM agent_drafts "
            " WHERE tipo = 'cobertura_posto' AND status = 'rascunho' "
            "   AND (payload->>'dia')::date "
            "       < ((now() AT TIME ZONE 'America/Manaus')::date - 1)"))).all()
        if vencidos:
            falhas.append(
                f"{len(vencidos)} rascunho(s) de cobertura VIVOS fora da janela de hoje/ontem "
                f"(ex.: {vencidos[0][1][:60]!r}, dia {vencidos[0][2]}) — o botão Aprovar vai "
                f"responder 500 e o registro da cobertura morre com o rascunho")
            print(f"  FALHA · ⭐ {len(vencidos)} rascunho(s) de cobertura já passaram da janela")
        else:
            vivos = await _contar(db, "SELECT count(*) FROM agent_drafts "
                                      "WHERE tipo='cobertura_posto' AND status='rascunho'")
            print(f"  OK    · ⭐ nenhum rascunho de cobertura fora da janela ({vivos} vivo(s))")

        base_subs = await _contar(db, "SELECT count(*) FROM substitutions")
        print(f"  ·       linha(s) em substitutions antes do teste: {base_subs}")

        # ── fixture: turno de HOJE em posto INATIVO com colaborador DEMITIDO ──────────
        alvo = (await db.execute(text(
            "SELECT (SELECT id::text FROM posts WHERE NOT is_active ORDER BY id LIMIT 1), "
            "       (SELECT id::text FROM employees WHERE status <> 'ativo' ORDER BY id LIMIT 1), "
            "       (SELECT scale_id::text FROM shifts WHERE is_active LIMIT 1)"))).first()
        post_id, emp_id, scale_id = alvo
        if not (post_id and emp_id and scale_id):
            print("  ⛔ sem posto inativo / colaborador demitido / escala para a fixture")
            sys.exit(1)

        await db.execute(text("""
            INSERT INTO shifts (id, scale_id, employee_id, post_id, shift_date,
                planned_start_time, planned_end_time, planned_break_minutes, status,
                is_holiday, is_night_shift, is_overtime, is_off_day, needs_substitution,
                planned_hours, actual_hours, overtime_hours, night_hours, base_pay,
                overtime_pay, night_bonus, holiday_bonus, total_pay, notes, is_active,
                created_at, updated_at)
            VALUES (CAST(:id AS uuid), CAST(:sc AS uuid), CAST(:e AS uuid), CAST(:p AS uuid),
                (now() AT TIME ZONE 'America/Manaus')::date,
                '07:00', '19:00', 60, 'scheduled',
                false, false, false, false, false, 12, 0,0,0,0,0,0,0,0, :marca, true,
                now(), now())"""),
            {"id": fixt_shift, "sc": scale_id, "e": emp_id, "p": post_id, "marca": MARCA})

        # turno ANTIGO de verdade, só para leitura: a recusa acontece ANTES de qualquer
        # escrita (422 na janela), então apontar para ele não muda dado de ninguém.
        shift_velho = (await db.execute(text(
            "SELECT id::text FROM shifts WHERE is_active AND NOT is_off_day "
            "  AND status = 'scheduled' "
            "  AND shift_date < ((now() AT TIME ZONE 'America/Manaus')::date - 5) "
            "ORDER BY shift_date DESC LIMIT 1"))).scalar()

        dono = (await db.execute(select(User).where(
            User.email == "jjesus@conectamais.pro"))).scalars().first()
        if dono is None:
            print("  ⛔ usuário aprovador não encontrado")
            sys.exit(1)
        dono_id = str(dono.id)  # valor simples: o objeto expira no commit abaixo

        for did, sid, dia_sql in (
            (draft_ok, fixt_shift, "(now() AT TIME ZONE 'America/Manaus')::date"),
            (draft_velho, shift_velho, "((now() AT TIME ZONE 'America/Manaus')::date - 6)"),
        ):
            if not sid:
                continue
            await db.execute(text(f"""
                INSERT INTO agent_drafts (id, tipo, modulo, titulo, resumo, payload, status,
                    gate, requires_otp, roles_aprovador, solicitado_por)
                VALUES (CAST(:i AS uuid), 'cobertura_posto', 'operacional',
                    CAST(:ti AS text), CAST(:marca AS text),
                    jsonb_build_object('shift_id', CAST(:sh AS text),
                        'post_id', CAST(:p AS text), 'motivo', 'falta',
                        'relato', CAST(:marca AS text),
                        'original_employee_id', CAST(:e AS text),
                        'substitute_employee_id', NULL,
                        'dia', {dia_sql}::text),
                    'rascunho', '🟡', false, ARRAY['admin']::text[], :u)"""),
                {"i": did, "ti": f"{MARCA} {did[:8]}", "marca": MARCA, "sh": sid,
                 "p": post_id, "e": emp_id, "u": dono_id})
        await db.commit()

    token = create_access_token(dono_id)
    try:
        async with httpx.AsyncClient(base_url="http://localhost:8080", timeout=90) as cli:
            # ── 5. ⭐ A TELA DIZ O PRAZO, e não oferece botão que vai falhar ──────────
            # Sem isto o aprovador vê "Aprovar" num rascunho vencido, clica, leva 500 e o
            # registro da cobertura morre em `falha`. Botão que existe e não pode funcionar
            # é a mesma família do sucesso vazio, do outro lado.
            tela = (await cli.get("/api/v1/redesign/data/aprovacoes",
                                  headers={"Authorization": f"Bearer {token}"})).json()
            # o título do rascunho de fixture carrega os 8 primeiros dígitos do id, e ele
            # sobrevive no `title` das ações — é por ele que a linha se identifica na tela.
            botoes: dict[str, list[str]] = {}
            for linha in tela["screens"]["pendentes"]["rows"]:
                acoes = linha.get("actions") or []
                titulos = " ".join((a.get("title") or "") for a in acoes)
                for did in (draft_ok, draft_velho):
                    if did[:8] in titulos:
                        botoes[did] = [a.get("btnLabel") for a in acoes]
            checar("Aprovar" in (botoes.get(draft_ok) or []),
                   "rascunho DENTRO da janela oferece Aprovar",
                   str(botoes.get(draft_ok)))
            # ⭐ o prazo tem de estar no SUBTÍTULO, que é a primeira linha que a pessoa lê. O
            # sino não dá conta: 1834 não lidas na conta do Orlailson, 3187 delas com o título
            # genérico "⚠ Cobertura de posto" do vigia de atraso. Entregue ≠ visto.
            sub = tela["screens"]["pendentes"]["sub"]
            print(f"  ·       subtítulo da Central: {sub[:100]}")
            if shift_velho:
                checar("venceu" in sub or "VENCE" in sub,
                       "⭐ o subtítulo da Central conta o prazo (vence hoje / venceu)", sub[:70])
            if shift_velho:
                # ⚠️ a REGRA é "não oferece Aprovar", não a lista exata: o dispatcher injeta
                # um "Ver" em toda linha, e travar a fotografia `== ['Arquivar']` deixaria o
                # oráculo vermelho por um botão de leitura que não decide nada.
                velho = botoes.get(draft_velho)
                checar(velho is not None and "Aprovar" not in velho and "Arquivar" in velho,
                       "⭐ rascunho VENCIDO não oferece Aprovar (só arquivar)", str(velho))

            # ── 1. CAMINHO FELIZ ─────────────────────────────────────────────────────
            r = await cli.post("/api/v1/redesign/action/aprovar-rascunho",
                               params={"draft_id": draft_ok}, json={},
                               headers={"Authorization": f"Bearer {token}"})
            print(f"  ·       aprovar dentro da janela → HTTP {r.status_code} {r.text[:110]}")
            checar(r.status_code == 200, "⭐ aprovar dentro da janela responde 200",
                   f"HTTP {r.status_code}: {r.text[:90]}")

            async with async_session_factory() as db:
                linha = (await db.execute(text(
                    "SELECT id::text, status, reason, original_employee_id::text "
                    "  FROM substitutions WHERE shift_id = CAST(:s AS uuid)"),
                    {"s": fixt_shift})).first()
                st_shift = (await db.execute(text(
                    "SELECT status, needs_substitution FROM shifts WHERE id = CAST(:s AS uuid)"),
                    {"s": fixt_shift})).first()
                st_draft = (await db.execute(text(
                    "SELECT status FROM agent_drafts WHERE id = CAST(:i AS uuid)"),
                    {"i": draft_ok})).scalar()
            checar(linha is not None,
                   "⭐ a aprovação GRAVOU linha em substitutions (lida DEPOIS da escrita)",
                   f"substitution={linha[0][:8] if linha else None} status={linha[1] if linha else None}")
            if linha:
                checar(linha[1] == "pending" and linha[2] == "no_show",
                       "a linha nasce 'pending' com o motivo traduzido para o enum",
                       f"status={linha[1]!r} reason={linha[2]!r}")
            checar(bool(st_shift) and st_shift[0] == "missed" and st_shift[1] is True,
                   "o turno virou 'missed' + needs_substitution",
                   f"status={st_shift[0] if st_shift else None}")
            checar(st_draft == "executado", "o rascunho fechou como 'executado'",
                   f"status={st_draft!r}")

            # ── 2. PAVIO: fora da janela recusa, e o motivo sobrevive ────────────────
            if shift_velho:
                r2 = await cli.post("/api/v1/redesign/action/aprovar-rascunho",
                                    params={"draft_id": draft_velho}, json={},
                                    headers={"Authorization": f"Bearer {token}"})
                print(f"  ·       aprovar fora da janela → HTTP {r2.status_code}")
                checar(r2.status_code >= 400,
                       "⭐ turno fora da janela NÃO é aprovado (nunca 200 mentindo)",
                       f"HTTP {r2.status_code}")
                async with async_session_factory() as db:
                    row = (await db.execute(text(
                        "SELECT status, erro_execucao FROM agent_drafts "
                        " WHERE id = CAST(:i AS uuid)"), {"i": draft_velho})).first()
                    subs_velho = await _contar(
                        db, "SELECT count(*) FROM substitutions WHERE shift_id = CAST(:s AS uuid)",
                        {"s": shift_velho})
                stv, errv = (row or (None, None))
                checar(stv == "falha", "o rascunho vencido termina 'falha'", f"status={stv!r}")
                checar("hoje ou de ontem" in (errv or ""),
                       "o motivo GRAVADO nomeia a janela de hoje/ontem",
                       (errv or "")[:90])
                checar(subs_velho == 0,
                       "controle: a recusa não escreveu nada no turno antigo real",
                       f"{subs_velho} linha(s)")
            else:
                print("  ·       sem turno antigo real disponível para o teste do pavio")
    finally:
        # ── limpeza + PROVA por leitura posterior ────────────────────────────────────
        async with async_session_factory() as db:
            await db.execute(text(
                "DELETE FROM substitutions WHERE shift_id = CAST(:s AS uuid)"), {"s": fixt_shift})
            await db.execute(text(
                "DELETE FROM shifts WHERE id = CAST(:s AS uuid)"), {"s": fixt_shift})
            await db.execute(text(
                "DELETE FROM communication_notifications WHERE title LIKE :m"),
                {"m": f"{MARCA}%"})
            await db.execute(text(
                "DELETE FROM agent_drafts WHERE titulo LIKE :m"), {"m": f"{MARCA}%"})
            await db.commit()
            sobrou_d = await _contar(
                db, "SELECT count(*) FROM agent_drafts WHERE titulo LIKE :m", {"m": f"{MARCA}%"})
            sobrou_s = await _contar(
                db, "SELECT count(*) FROM shifts WHERE notes LIKE :m", {"m": f"%{MARCA}%"})
            total_subs = await _contar(db, "SELECT count(*) FROM substitutions")
        checar(sobrou_d == 0 and sobrou_s == 0,
               "limpeza PROVADA por leitura (0 rascunho e 0 turno de fixture)",
               f"drafts={sobrou_d} shifts={sobrou_s}")
        print(f"  ·       linha(s) em substitutions depois da limpeza: {total_subs}")

    if falhas:
        print(f"\nTEST cobertura_grava_e_expira FAIL ({len(falhas)})")
        for f in falhas:
            print(f"  ❌ {f}")
        sys.exit(1)
    print("\nTEST cobertura_grava_e_expira PASS")


if __name__ == "__main__":
    asyncio.run(main())
