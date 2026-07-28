"""SUITE-ORÁCULO da Fase 5.5 (memória que aprende / memória curada) — prova
formal, executável e MUTAÇÃO-TESTADA de que as garantias da memória curada
seguram, e de que a suite MORDE (falha) se alguém regredir. Molde:
`test_oraculos_acoes_5_4.py` (padrão standalone, sem pytest, `sys.exit(!=0)`
em falha crítica, mutação embutida).

Doutrina (mesma da 5.3/5.4): a fronteira provada é o DADO/EFEITO no banco
(status/expiração real em `consultor_memorias`, destinatário real da
notificação, linha real em `audit_logs`), NUNCA a prosa do LLM. Cada
inviolável = 1 oráculo, provado por assert direto no retorno/estado, não por
alegação.

Os 6 oráculos (Task 7 do plano 2026-07-28-fase5.5-memoria-que-aprende.md):
  1. Fabricação numérica barrada — `curar()` com um fato cujo número NÃO está
     em `fonte_conversa` (panorama) → status='pendente_revisao' (nunca 'ativo').
  2. Entidade inventada barrada — `curar()` com um CNPJ que não existe em
     `clients`/`empresas` → 'pendente_revisao' + `veredito.checks.entidades.faltando != []`.
  3. Contexto só lê 'ativo' não-expirado — 3 memórias inseridas direto no banco
     (ativa válida, pendente_revisao, ativa EXPIRADA) → `contexto_compartilhado`
     traz SÓ a 1ª; as outras duas NUNCA vazam pro prompt dos consultores.
  4. Feedback de não-diretoria não vira memória permanente — `registrar_feedback`
     com `user_role` != admin + correção → `virou_memoria=False` e ZERO linha
     nova em `consultor_memorias` (o 👍/👎 simples grava, a memória não).
  5. Audit de todo write-back — a correção da DIRETORIA (`user_role='admin'`)
     GRAVA memória (`virou_memoria=True`, status 'ativo' via `autor_confiavel`)
     E gera ≥1 linha em `audit_logs` (mesmo pacote `agent_audit`, ação
     'agent_response'/'agent' — via `registrar_acao_agente`, não
     `registrar_proposta_acao` da 5.4, que é outra função/outro `action`).
  6. Fila de revisão RBAC — uma memória 'pendente_revisao' é avisada (sino)
     SÓ para quem tem role admin (`_avisar_pendente_revisao`); um usuário
     não-admin real NUNCA aparece entre os destinatários; `aprovar_memoria`
     transiciona o status para 'ativo'.

MUTAÇÃO-TESTE (prova que a suite morde; molde 5.3/5.4):
  M1 — curator morto: uma função `curar` que SEMPRE devolve status='ativo'
       (fabricação passa) → oráculos 1 e 2 devem FALHAR.
  M2 — filtro morto: uma `contexto_compartilhado` que lê QUALQUER status (sem
       filtrar 'ativo'/expiração) → oráculo 3 deve FALHAR (pendente/expirada vazam).
Se uma mutação NÃO derrubar o oráculo certo, o oráculo é fraco (a doutrina do
brief: "fortaleça o oráculo").

Bancada: container já vivo `conecta-pro-backend` (rede
`conecta-pro_conecta-pro-network`), `DATABASE_URL` já presente no ambiente do
container (postgresql+asyncpg://…@postgres:5432/conecta_pro) — NUNCA
reconstruído via POSTGRES_HOST (vazio no container real). NUNCA roda contra
green:8080 (OOM). Escreve no DB REAL — todo seed carrega o sentinel
`__TESTE_5.5__`; limpeza cirúrgica por id + sentinel literal (`strpos`, nunca
`LIKE`, pois o sentinel contém `_`) no finally — 0 remanescentes, NUNCA apaga
as 36 memórias reais nem qualquer dado real. Imprime PASS/FAIL por oráculo +
resultado das 2 mutações; exit 0 só se os 6 oráculos PASS E as 2 mutações
MORDEREM.
"""
from __future__ import annotations

import asyncio
import os
import traceback
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# ── Unidades sob prova ──
from modules.ai.conversation.services import consultor_hub
from modules.ai.conversation.services.garantia.memoria_curator import curar
from modules.notifications.proativo import entrega

MARK = "__TESTE_5.5__"  # sentinel: todo seed carrega isto (limpeza + nunca-real)


def _mk(*parts: str) -> str:
    return " ".join((MARK, *parts, uuid.uuid4().hex[:8]))


async def main() -> int:  # noqa: C901 (suite única e linear, como o molde 5.4)
    results: list[tuple[str, str, bool, str]] = []

    def record(n, desc: str, ok: bool, detail: str = "") -> None:
        results.append((n, desc, ok, detail))
        tag = "PASS" if ok else "FAIL"
        rot = f"ORACULO {n}" if isinstance(n, int) else str(n)
        print(f"{rot} {desc} ... {tag}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"])
    Session = async_sessionmaker(eng, expire_on_commit=False)

    # ids/conteúdos criados (limpeza cirúrgica por id + sentinel no finally)
    mem_ids: list[int] = []
    consulta_ids: list[int] = []

    async with Session() as db:
        try:
            # ── identidades REAIS (mesmo helper das Fases 5.3/5.4) ──
            admins = await entrega.resolver_usuarios_por_roles(db, ("admin",))
            assert len(admins) >= 2, (
                f"esperado >=2 admins reais p/ o oráculo 6, veio {len(admins)}")
            admins_set = {str(a) for a in admins}

            nao_admin_row = (await db.execute(text(
                "SELECT id::text, role FROM users "
                "WHERE coalesce(is_active,true) AND lower(coalesce(role,'')) <> 'admin' "
                "LIMIT 1"))).first()
            assert nao_admin_row, "esperado >=1 usuário real NÃO-admin p/ o RBAC"
            nao_admin_id, nao_admin_role = nao_admin_row[0], nao_admin_row[1]

            # CNPJ garantidamente inexistente (verificado EM TEMPO DE EXECUÇÃO
            # contra o banco real — nunca hardcoded sem checar, senão um cliente
            # real com esses dígitos daria falso-positivo).
            cnpj_falso = "00.000.000/0001-00"
            dig_falso = "00000000000100"
            colide = (await db.execute(text(
                "SELECT 1 FROM clients WHERE regexp_replace(coalesce(document_number,''),'\\D','','g')=:d "
                "UNION SELECT 1 FROM empresas WHERE regexp_replace(coalesce(cnpj,''),'\\D','','g')=:d LIMIT 1"),
                {"d": dig_falso})).first()
            assert colide is None, (
                f"fixture ruim: CNPJ falso {cnpj_falso!r} existe de verdade na bancada")

            fonte_conversa = {"saldo": "R$ 9.125,56", "postos": 7}

            async def _scalar(sql: str, params: dict | None = None) -> int:
                return int((await db.execute(text(sql), params or {})).scalar() or 0)

            # ════════════════ ORÁCULO 1 — FABRICAÇÃO NUMÉRICA BARRADA ══════════
            try:
                await _oraculo_1(db, curar, fonte_conversa)
                record(1, "curar(): número FORA do panorama → pendente_revisao (nunca ativo)",
                       True, "numeros.ok=False ⇒ status=pendente_revisao")
            except Exception as exc:
                record(1, "curar(): número FORA do panorama → pendente_revisao", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 2 — ENTIDADE INVENTADA BARRADA ═══════════
            try:
                await _oraculo_2(db, curar, fonte_conversa, cnpj_falso)
                record(2, "curar(): CNPJ inexistente → pendente_revisao + faltando != []",
                       True, "entidades.ok=False, faltando não-vazio")
            except Exception as exc:
                record(2, "curar(): CNPJ inexistente → pendente_revisao + faltando != []", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 3 — CONTEXTO SÓ ATIVO NÃO-EXPIRADO ═══════
            cont_ativo = _mk("FATO-ATIVO-VALIDO")
            cont_pendente = _mk("FATO-PENDENTE-REVISAO")
            cont_expirada = _mk("FATO-ATIVO-EXPIRADO")
            try:
                mid_a = (await db.execute(text(
                    "INSERT INTO consultor_memorias (origem, conteudo, fonte, status, confidence, autor, expira_em) "
                    "VALUES ('cfo', :c, 'llm_destilado', 'ativo', 0.9, 'teste', now() + interval '90 days') "
                    "RETURNING id"), {"c": cont_ativo})).scalar()
                mid_p = (await db.execute(text(
                    "INSERT INTO consultor_memorias (origem, conteudo, fonte, status, confidence, autor, expira_em) "
                    "VALUES ('cfo', :c, 'llm_destilado', 'pendente_revisao', 0.3, 'teste', now() + interval '90 days') "
                    "RETURNING id"), {"c": cont_pendente})).scalar()
                mid_e = (await db.execute(text(
                    "INSERT INTO consultor_memorias (origem, conteudo, fonte, status, confidence, autor, expira_em) "
                    "VALUES ('cfo', :c, 'llm_destilado', 'ativo', 0.9, 'teste', now() - interval '1 day') "
                    "RETURNING id"), {"c": cont_expirada})).scalar()
                await db.commit()
                mem_ids += [mid_a, mid_p, mid_e]

                await _oraculo_3(consultor_hub.contexto_compartilhado, db,
                                  cont_ativo, cont_pendente, cont_expirada)
                record(3, "contexto_compartilhado: só 'ativo' não-expirado passa (pendente/expirada não vazam)",
                       True, f"ativo(id={mid_a}) presente; pendente(id={mid_p})/expirada(id={mid_e}) ausentes")
            except Exception as exc:
                await db.rollback()
                record(3, "contexto_compartilhado: só 'ativo' não-expirado passa", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 4 — FEEDBACK NÃO-DIRETORIA NÃO VIRA MEMÓRIA
            try:
                pergunta_4 = _mk("pergunta-o4")
                resposta_4 = _mk("resposta-o4")
                correcao_4 = _mk("correcao-nao-diretoria")
                cid4 = (await db.execute(text(
                    "INSERT INTO financial_cfo_consultas (area, pergunta, resposta, disclaimer, contexto_usado, created_by) "
                    "VALUES ('cfo', :p, :r, 'teste', '{}'::jsonb, :cb) RETURNING id"),
                    {"p": pergunta_4, "r": resposta_4, "cb": MARK})).scalar()
                await db.commit()
                consulta_ids.append(cid4)

                mem_antes = await _scalar(
                    "SELECT count(*) FROM consultor_memorias WHERE strpos(conteudo, :m) > 0", {"m": correcao_4})
                r4 = await consultor_hub.registrar_feedback(
                    db, origem="cfo", consulta_id=cid4, util=False,
                    correcao=correcao_4, user_role=nao_admin_role)
                assert r4.get("ok") is True, f"registrar_feedback falhou: {r4}"
                assert r4.get("virou_memoria") is False, (
                    f"feedback de não-diretoria (role={nao_admin_role!r}) virou memória: {r4}")
                mem_depois = await _scalar(
                    "SELECT count(*) FROM consultor_memorias WHERE strpos(conteudo, :m) > 0", {"m": correcao_4})
                assert mem_depois == mem_antes == 0, (
                    f"correção de não-diretoria gravou {mem_depois - mem_antes} linha(s) em consultor_memorias")
                record(4, "registrar_feedback(user_role não-admin): virou_memoria=False, 0 linha nova",
                       True, f"role={nao_admin_role!r} → ok={r4['ok']} virou_memoria={r4['virou_memoria']}")
            except Exception as exc:
                await db.rollback()
                record(4, "registrar_feedback(user_role não-admin) não vira memória", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 5 — AUDIT DE TODO WRITE-BACK ══════════════
            try:
                pergunta_5 = _mk("pergunta-o5")
                resposta_5 = _mk("resposta-o5")
                correcao_5 = _mk("correcao-diretoria")
                cid5 = (await db.execute(text(
                    "INSERT INTO financial_cfo_consultas (area, pergunta, resposta, disclaimer, contexto_usado, created_by) "
                    "VALUES ('cfo', :p, :r, 'teste', '{}'::jsonb, :cb) RETURNING id"),
                    {"p": pergunta_5, "r": resposta_5, "cb": MARK})).scalar()
                await db.commit()
                consulta_ids.append(cid5)

                n_audit_antes = await _scalar(
                    "SELECT count(*) FROM audit_logs WHERE strpos(coalesce(details->>'resposta',''), :m) > 0",
                    {"m": correcao_5})
                r5 = await consultor_hub.registrar_feedback(
                    db, origem="cfo", consulta_id=cid5, util=True,
                    correcao=correcao_5, user_role="admin", autor="teste-suite-5.5")
                assert r5.get("ok") is True, f"registrar_feedback (diretoria) falhou: {r5}"
                assert r5.get("virou_memoria") is True, f"correção da diretoria NÃO virou memória: {r5}"

                mem_row = (await db.execute(text(
                    "SELECT id, status FROM consultor_memorias WHERE strpos(conteudo, :m) > 0 "
                    "ORDER BY id DESC LIMIT 1"), {"m": correcao_5})).first()
                assert mem_row is not None, "memória da correção da diretoria não encontrada"
                mem_id_5, status_5 = mem_row[0], mem_row[1]
                mem_ids.append(mem_id_5)
                assert status_5 == "ativo", (
                    f"correção de diretoria (autor_confiavel) deveria entrar 'ativo', veio {status_5!r}")

                n_audit_depois = await _scalar(
                    "SELECT count(*) FROM audit_logs WHERE strpos(coalesce(details->>'resposta',''), :m) > 0",
                    {"m": correcao_5})
                assert n_audit_antes == 0, f"contaminação: já existia audit com o marcador antes do teste"
                assert n_audit_depois >= 1, (
                    f"write-back (registrar_feedback diretoria) não gerou linha em audit_logs")
                record(5, "write-back de diretoria: memória 'ativo' + >=1 linha em audit_logs",
                       True, f"memoria id={mem_id_5} status=ativo; audit +{n_audit_depois}")
            except Exception as exc:
                await db.rollback()
                record(5, "audit de todo write-back (registrar_feedback diretoria)", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 6 — FILA DE REVISÃO RBAC ══════════════════
            try:
                conteudo_6 = _mk("FATO-PENDENTE-RBAC")
                mid6 = (await db.execute(text(
                    "INSERT INTO consultor_memorias (origem, conteudo, fonte, status, confidence, autor, expira_em) "
                    "VALUES ('cfo', :c, 'llm_destilado', 'pendente_revisao', 0.3, 'teste', now() + interval '90 days') "
                    "RETURNING id"), {"c": conteudo_6})).scalar()
                await db.commit()
                mem_ids.append(mid6)

                await consultor_hub._avisar_pendente_revisao(
                    db, memoria_id=mid6, origem="cfo", conteudo=conteudo_6)

                destinatarios = {str(r[0]) for r in (await db.execute(text(
                    "SELECT user_id::text FROM communication_notifications "
                    "WHERE strpos(coalesce(body,''), :m) > 0"), {"m": conteudo_6})).all()}
                assert destinatarios, "nenhuma notificação de revisão foi criada"
                assert destinatarios == admins_set, (
                    f"destinatários {destinatarios} != conjunto de admins {admins_set}")
                assert nao_admin_id not in destinatarios, (
                    f"usuário NÃO-admin (role={nao_admin_role!r}) recebeu aviso de revisão de memória")

                r6 = await consultor_hub.aprovar_memoria(db, mid6, autor="teste-suite-5.5")
                assert r6.get("ok") is True, f"aprovar_memoria falhou: {r6}"
                assert r6.get("status") == "ativo", f"aprovar_memoria não pôs 'ativo': {r6}"
                status_pos = (await db.execute(text(
                    "SELECT status FROM consultor_memorias WHERE id=:i"), {"i": mid6})).scalar()
                assert status_pos == "ativo", f"status no banco != ativo após aprovar: {status_pos}"
                record(6, "fila de revisão: aviso SÓ para admin (RBAC) + aprovar_memoria → ativo",
                       True, f"{len(destinatarios)} admin(s) avisados, não-admin excluído; id={mid6}→ativo")
            except Exception as exc:
                await db.rollback()
                record(6, "fila de revisão RBAC + aprovar_memoria", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ MUTAÇÃO-TESTE — a suite MORDE? ════════════════════
            # M1: curator SEMPRE 'ativo' → oráculos 1 e 2 devem FALHAR (fabricação passa).
            m1a_ok, m1a_det = await _expect_bite(
                lambda: _oraculo_1(db, _curar_MUT_sempre_ativo, fonte_conversa))
            m1b_ok, m1b_det = await _expect_bite(
                lambda: _oraculo_2(db, _curar_MUT_sempre_ativo, fonte_conversa, cnpj_falso))
            m1_ok = m1a_ok and m1b_ok
            record("MUTAÇÃO M1", "curator morto (sempre 'ativo') → oráculo 1 e 2", m1_ok,
                   f"oraculo1: {m1a_det}; oraculo2: {m1b_det}")

            # M2: contexto_compartilhado SEM filtro de status/expiração → oráculo 3 deve FALHAR.
            m2_ok, m2_det = await _expect_bite(
                lambda: _oraculo_3(_contexto_MUT_sem_filtro, db, cont_ativo, cont_pendente, cont_expirada))
            record("MUTAÇÃO M2", "filtro morto (contexto lê status qualquer) → oráculo 3", m2_ok, m2_det)

        finally:
            # ══════════════ LIMPEZA — 0 remanescentes (por id + sentinel) ══════════
            await db.rollback()
            M = {"m": MARK}
            if mem_ids:
                await db.execute(text("DELETE FROM consultor_memorias WHERE id = ANY(:i)"),
                                  {"i": [int(x) for x in mem_ids if x is not None]})
            await db.execute(text(
                "DELETE FROM consultor_memorias WHERE strpos(coalesce(conteudo,''), :m) > 0"), M)
            await db.execute(text(
                "DELETE FROM audit_logs WHERE strpos(coalesce(details->>'resposta',''), :m) > 0"), M)
            await db.execute(text(
                "DELETE FROM communication_notifications WHERE strpos(coalesce(body,''), :m) > 0"), M)
            if consulta_ids:
                await db.execute(text("DELETE FROM financial_cfo_consultas WHERE id = ANY(:i)"),
                                  {"i": [int(x) for x in consulta_ids if x is not None]})
            await db.execute(text(
                "DELETE FROM financial_cfo_consultas WHERE strpos(coalesce(pergunta,''), :m) > 0 "
                "OR strpos(coalesce(resposta,''), :m) > 0 OR strpos(coalesce(correcao,''), :m) > 0"), M)
            await db.commit()

            # PROVA de limpeza: 0 remanescentes por sentinel LITERAL (query independente)
            async def _rem(sql: str) -> int:
                return int((await db.execute(text(sql), M)).scalar() or 0)

            rem = {}
            rem["consultor_memorias"] = await _rem(
                "SELECT count(*) FROM consultor_memorias WHERE strpos(coalesce(conteudo,''), :m) > 0")
            rem["audit_logs"] = await _rem(
                "SELECT count(*) FROM audit_logs WHERE strpos(coalesce(details->>'resposta',''), :m) > 0")
            rem["notificacoes"] = await _rem(
                "SELECT count(*) FROM communication_notifications WHERE strpos(coalesce(body,''), :m) > 0")
            rem["financial_cfo_consultas"] = await _rem(
                "SELECT count(*) FROM financial_cfo_consultas WHERE strpos(coalesce(pergunta,''), :m) > 0 "
                "OR strpos(coalesce(resposta,''), :m) > 0 OR strpos(coalesce(correcao,''), :m) > 0")
            total_rem = sum(rem.values())
            if total_rem == 0:
                print(f"\nLIMPEZA OK — 0 remanescentes ({', '.join(f'{k}={v}' for k, v in rem.items())})")
            else:
                print(f"\nLIMPEZA FALHOU — remanescentes: {rem}")
            record("LIMPEZA", "0 remanescentes do que a suite criou", total_rem == 0,
                   f"total={total_rem}")

    await eng.dispose()

    # ══════════════ RESUMO ══════════════
    oraculos = [r for r in results if isinstance(r[0], int)]
    mutacoes = [r for r in results if isinstance(r[0], str) and r[0].startswith("MUTAÇÃO")]
    limpeza = [r for r in results if r[0] == "LIMPEZA"]
    n_pass = sum(1 for r in oraculos if r[2])
    n_bite = sum(1 for r in mutacoes if r[2])
    print("\n" + "═" * 68)
    print(f"RESUMO: {n_pass}/{len(oraculos)} oráculos PASS  |  "
          f"{n_bite}/{len(mutacoes)} mutações MORDERAM  |  "
          f"limpeza {'OK' if limpeza and limpeza[0][2] else 'FALHOU'}")
    falhas = [r for r in results if not r[2]]
    if falhas:
        print("FALHAS (findings — é o gate mordendo, NÃO ajustar o teste):")
        for n, desc, _ok, det in falhas:
            print(f"  ✗ {n} {desc} — {det}")
        print("═" * 68)
        print("GATE: BLOQUEADO.")
        return 1
    print("═" * 68)
    print(f"OK suite 5.5 ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


# ───────────────────────── oráculos reutilizáveis (p/ mutação) ──────────────

async def _oraculo_1(db, curar_fn, fonte_conversa: dict) -> None:
    """Fato com número FORA da fonte (panorama) → 'pendente_revisao', nunca 'ativo'.
    Testado contra `curar_fn` (real = memoria_curator.curar; mutado = sempre
    'ativo' → deve derrubar este oráculo — fabricação passaria)."""
    fato = _mk("O saldo da conta é R$ 50.000,00 conforme relatório.")
    r = await curar_fn(
        db, fato=fato, origem="cfo", fonte="llm_destilado",
        autor_role="", fonte_conversa=fonte_conversa,
    )
    assert r["status"] == "pendente_revisao", (
        f"número fabricado (fora do panorama) deveria ficar pendente_revisao, veio {r}")
    assert r["veredito"]["checks"]["numeros"]["ok"] is False, r


async def _oraculo_2(db, curar_fn, fonte_conversa: dict, cnpj_falso: str) -> None:
    """CNPJ inexistente em clients/empresas → 'pendente_revisao' + faltando != [].
    Testado contra `curar_fn` (real; mutado = sempre 'ativo' → deve derrubar)."""
    fato = _mk(f"A empresa cliente é o CNPJ {cnpj_falso}.")
    r = await curar_fn(
        db, fato=fato, origem="cfo", fonte="llm_destilado",
        autor_role="", fonte_conversa=fonte_conversa,
    )
    assert r["status"] == "pendente_revisao", (
        f"CNPJ inexistente deveria ficar pendente_revisao, veio {r}")
    assert r["veredito"]["checks"]["entidades"]["ok"] is False, r
    assert r["veredito"]["checks"]["entidades"]["faltando"] != [], (
        f"entidade inventada deveria aparecer em 'faltando', veio {r}")


async def _oraculo_3(contexto_fn, db, cont_ativo: str, cont_pendente: str, cont_expirada: str) -> None:
    """`contexto_compartilhado` só traz memória 'ativo' + não-expirada. Testado
    contra `contexto_fn` (real; mutado = sem filtro de status/expiração →
    deve derrubar este oráculo por vazamento)."""
    texto = await contexto_fn(db, origem_atual="juridico", pergunta=None, max_memorias=1000)
    assert cont_ativo in texto, (
        f"memória ATIVA não-expirada deveria aparecer no contexto compartilhado: {texto[:300]}")
    assert cont_pendente not in texto, (
        "memória 'pendente_revisao' VAZOU pro contexto compartilhado dos consultores")
    assert cont_expirada not in texto, (
        "memória 'ativo' EXPIRADA VAZOU pro contexto compartilhado dos consultores")


async def _curar_MUT_sempre_ativo(db, **_kw) -> dict:
    """MUTAÇÃO M1: curator morto — SEMPRE devolve 'ativo' (fabricação passa sem
    barreira nenhuma), independente do fato/fonte/entidade."""
    return {"status": "ativo", "confidence": 1.0, "veredito": {
        "checks": {"numeros": {"ok": True, "suspeitos": []},
                   "entidades": {"ok": True, "faltando": []}},
        "confidence": 1.0,
    }}


async def _contexto_MUT_sem_filtro(
    db, origem_atual: str, pergunta: str | None = None, *, max_memorias: int = 30,
) -> str:
    """MUTAÇÃO M2: `contexto_compartilhado` sem o filtro `status='ativo' AND
    (expira_em IS NULL OR expira_em > now())` — lê QUALQUER status/expiração
    (vazamento de pendente/expirada pro prompt dos consultores)."""
    rows = (await db.execute(text(
        "SELECT origem, conteudo FROM consultor_memorias ORDER BY created_at DESC LIMIT :lim"),
        {"lim": max_memorias})).fetchall()
    return "\n".join(f"- [{r.origem}] {r.conteudo}" for r in rows)


# ───────────────────────── helpers de mutação ──────────────────────────────

async def _expect_bite(coro_factory):
    """A mutação MORDE se o oráculo (async) FALHA sob ela."""
    try:
        await coro_factory()
    except AssertionError as exc:
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    return False, "NÃO mordeu — oráculo passou sob mutação (oráculo FRACO!)"


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
