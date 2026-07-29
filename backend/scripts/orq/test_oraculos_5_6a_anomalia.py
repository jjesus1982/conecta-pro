"""SUITE-ORÁCULO da Fase 5.6a (moonshot anomalia de pagamento) — prova formal,
executável e MUTAÇÃO-TESTADA de que as invioláveis do detector+beat+sino+CFO+
revisão seguram, e de que a suite MORDE se alguém regredir. Molde:
`test_oraculos_5_5.py` (padrão standalone, sem pytest, `sys.exit(!=0)` em
falha crítica, mutação embutida via monkeypatch de função real).

Componentes sob prova (LT1 commit 69ddb3bc, LT2 commits eacd09a7/3cc8c25e):
  - `services/anomalia_pagamentos.py::detectar_anomalias_pagamentos` — detector
    async, read-only sobre `inter_payments`, só INSERT em `fraud_alerts`.
  - `tasks.py::_varrer` — roda o detector + avisa a diretoria (sino) p/
    alertas HIGH/CRITICAL, via `entrega.resolver_usuarios_por_roles(('admin',))`.
  - `cfo_service.panorama/_formatar_contexto_financeiro` — injeta bloco de
    alertas abertos rotulado suspeita no contexto do CFO IA.
  - `controllers/anomalia_controller.py` — `require_diretoria` (gate RBAC),
    `listar_pendentes`, `confirmar_anomalia`, `descartar_anomalia` (ações
    HUMANAS, NUNCA automáticas).

Os 6 oráculos:
  1. Read-only sobre dinheiro — `inter_payments` (status/valor/updated_at)
     idêntico ANTES do 1º pagamento sentinela inserido e DEPOIS de todo o
     ciclo (detecção + sino + CFO + revisão humana).
  2. Suspeita-não-fato — o alerta NASCE `status='pending'` (nunca
     'confirmed'/'false_positive' automaticamente) e o `summary` rotula
     explicitamente "NÃO é fraude confirmada" + "SUSPEITA".
  3. RBAC diretoria — `require_diretoria` barra (403) usuário não-admin e
     deixa passar admin. Ação de confirmar/descartar só existe atrás do gate.
  4. Sino só admin — `_varrer` avisa SOMENTE quem `resolver_usuarios_por_roles
     (('admin',))` resolve; destinatários reais ⊆ admins reais, nunca vaza
     pra outro papel.
  5. Rótulo suspeita — o contexto do CFO IA carrega o alerta com o mesmo
     rótulo ("NÃO são fatos confirmados", "NUNCA afirme que houve fraude
     confirmada").
  6. Nunca fabricar — um pagamento SEM sinal real (dentro do baseline do
     próprio beneficiário, horário comercial) gera ZERO alertas: o detector
     não inventa suspeita quando não há sinal.

MUTAÇÃO-TESTE (prova que a suite morde; molde 5.5):
  M1 — gate morto: `require_diretoria` substituído por uma função que SEMPRE
       deixa passar (sem checar role) → oráculo 3 (RBAC) deve FALHAR.
  M2 — resolver vazado: `entrega.resolver_usuarios_por_roles` substituído por
       uma função que devolve TODOS os usuários ativos (ignora o filtro de
       role) → oráculo 4 (sino só admin) deve FALHAR (vaza pra não-admin).
Se uma mutação NÃO derrubar o oráculo certo, o oráculo é fraco.

Bancada: container THROWAWAY (imagem conecta-pro-backend) anexado à rede
`conecta-pro_conecta-pro-network`, `DATABASE_URL` apontando pro Postgres real
via nome do container (`conecta-pro-postgres`) — NUNCA o backend
vivo/green:8080. Escreve no DB REAL — todo pagamento/alerta sentinela carrega
o marcador `__TESTE_5.6a__` no destinatário; limpeza cirúrgica por id (diff
pré/pós) no finally — 0 remanescentes, NUNCA apaga pagamento/alerta REAL.
Imprime PASS/FAIL por oráculo + resultado das 2 mutações; exit 0 só se os 6
oráculos PASS E as 2 mutações MORDEREM.
"""
from __future__ import annotations

import asyncio
import os
import sys
import traceback
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

TZ_MANAUS = ZoneInfo("America/Manaus")
MARK = "__TESTE_5.6a__"  # sentinel: todo pagamento/alerta sentinela carrega isto


class FakeUser:
    """Objeto mínimo p/ exercitar os gates do controller (role/id/email) sem
    depender de sessão HTTP — mesmo padrão de `bench_5_6a_lt2.py` (LT2)."""

    def __init__(self, id_: str, role: str, email: str) -> None:
        self.id = id_
        self.role = role
        self.email = email


async def main() -> int:  # noqa: C901 (suite única e linear, como o molde 5.5)
    results: list[tuple[object, str, bool, str]] = []

    def record(n, desc: str, ok: bool, detail: str = "") -> None:
        results.append((n, desc, ok, detail))
        tag = "PASS" if ok else "FAIL"
        rot = f"ORACULO {n}" if isinstance(n, int) else str(n)
        print(f"{rot} {desc} ... {tag}{(' — ' + detail) if detail else ''}")

    eng = create_async_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    payment_ids: list[uuid.UUID] = []  # TODOS os pagamentos sentinela (p/ limpeza)
    pre_alert_ids: set[str] = set()
    pre_notif_ids: set[str] = set()
    pre_audit_ids: set[str] = set()

    async with Session() as db:
        try:
            # ── identidades REAIS (mesmo padrão 5.5/LT2) ─────────────────
            admins = (await db.execute(text(
                "SELECT id::text FROM users WHERE lower(coalesce(role,''))='admin' "
                "AND coalesce(is_active,true)=true"))).scalars().all()
            assert admins, "esperado >=1 admin real p/ o oráculo 3/4"
            admins_set = set(admins)
            prepared_by = admins[0]

            nao_admin_reais = (await db.execute(text(
                "SELECT id::text FROM users WHERE lower(coalesce(role,''))<>'admin' "
                "AND coalesce(is_active,true)=true"))).scalars().all()
            assert nao_admin_reais, "esperado >=1 usuário real NÃO-admin p/ o oráculo 4 morder"

            admin_user = FakeUser(admins[0], "admin", "sentinela-admin@teste.local")
            nao_admin_user = FakeUser(str(uuid.uuid4()), "operator", "sentinela-operador@teste.local")

            # ── snapshot pré-teste (diff pre/pós p/ limpeza cirúrgica) ───
            pre_alert_ids = set((await db.execute(text(
                "SELECT id::text FROM fraud_alerts"))).scalars().all())
            pre_notif_ids = set((await db.execute(text(
                "SELECT id::text FROM communication_notifications"))).scalars().all())
            pre_audit_ids = set((await db.execute(text(
                "SELECT id::text FROM audit_logs"))).scalars().all())

            # ═══════════════ SETUP: grupos de pagamento sentinela ═══════════
            async def _montar_grupo(tag: str, hist_valor: float, valor_anomalo: float | None,
                                     *, weekend_madrugada: bool) -> tuple[list[uuid.UUID], uuid.UUID | None]:
                """Baseline de 6 pagamentos ao mesmo beneficiário + (opcional) 1
                pagamento em análise. `weekend_madrugada=True` empilha os 3
                sinais (valor+teto+velocity+horário, minutos entre si) p/
                severidade HIGH/CRITICAL confiável; `False` = baseline
                ESPAÇADO EM DIAS + horário comercial (isola TODOS os sinais em
                zero p/ testar "nunca fabricar" quando não há anomalia real —
                minutos entre si criaria velocity_alta de verdade, o que não
                seria fabricação, mas invalidaria o oráculo 6)."""
                chave = f"{MARK}_{tag}"
                if weekend_madrugada:
                    base_dt = datetime(2026, 7, 25, 3, 0, tzinfo=TZ_MANAUS)  # sábado, madrugada
                else:
                    base_dt = datetime(2026, 7, 21, 14, 0, tzinfo=TZ_MANAUS)  # terça, comercial
                ids: list[uuid.UUID] = []
                for i, delta in enumerate((60, 50, 40, 30, 20, 10)):
                    pid = uuid.uuid4()
                    ids.append(pid)
                    dt = base_dt - (timedelta(minutes=delta) if weekend_madrugada else timedelta(days=delta))
                    valor = hist_valor + i * 10
                    await db.execute(text(
                        "INSERT INTO inter_payments (id, payment_type, destinatario, valor, "
                        " data_pagamento, status, prepared_by, created_at, updated_at) VALUES "
                        "(:id, 'pix', CAST(:dest AS jsonb), :valor, CAST(:dt AS date), 'confirmado', "
                        " :prepared_by, :dt, :dt)"),
                        {"id": pid, "dest": (
                            '{"chave": "%s", "nome_recebedor": "%s SENTINELA %s"}' % (chave, MARK, tag)
                        ), "valor": valor, "dt": dt, "prepared_by": prepared_by})
                pid_analise = None
                if valor_anomalo is not None:
                    pid_analise = uuid.uuid4()
                    ids.append(pid_analise)
                    await db.execute(text(
                        "INSERT INTO inter_payments (id, payment_type, destinatario, valor, "
                        " data_pagamento, status, prepared_by, created_at, updated_at) VALUES "
                        "(:id, 'pix', CAST(:dest AS jsonb), :valor, CAST(:dt AS date), 'confirmado', "
                        " :prepared_by, :dt, :dt)"),
                        {"id": pid_analise, "dest": (
                            '{"chave": "%s", "nome_recebedor": "%s SENTINELA %s"}' % (chave, MARK, tag)
                        ), "valor": valor_anomalo, "dt": base_dt, "prepared_by": prepared_by})
                await db.commit()
                return ids, pid_analise

            hist_a, anomalo_a = await _montar_grupo("A", 1000.0, 300000.0, weekend_madrugada=True)
            hist_b, anomalo_b = await _montar_grupo("B", 1200.0, 400000.0, weekend_madrugada=True)
            hist_c, anomalo_c = await _montar_grupo("C", 900.0, 350000.0, weekend_madrugada=True)
            hist_n, pid_normal = await _montar_grupo(
                "N", 500.0, 520.0, weekend_madrugada=False)  # R$520 ~ baseline R$500-550, dias/comercial

            payment_ids = [*hist_a, anomalo_a, *hist_b, anomalo_b, *hist_c, anomalo_c, *hist_n]
            if pid_normal:
                payment_ids.append(pid_normal)

            # snapshot ANTES de qualquer detecção (prova de read-only, oráculo 1)
            snapshot_antes = {
                str(r["id"]): dict(r)
                for r in (await db.execute(text(
                    "SELECT id, status, valor, updated_at FROM inter_payments "
                    "WHERE id = ANY(:ids)"), {"ids": payment_ids})).mappings().all()
            }

            from modules.ai.fraud_detection.controllers import anomalia_controller as ctrl
            from modules.ai.fraud_detection.services.anomalia_pagamentos import (
                detectar_anomalias_pagamentos,
            )
            from modules.ai.fraud_detection.tasks import _varrer
            from modules.financial import cfo_service
            from modules.notifications.proativo import entrega

            # ── grupo A: roda o beat (detecção + sino) UMA VEZ — o alerta fica
            # 'pending' até a revisão humana logo abaixo. Todos os oráculos que
            # dependem do estado 'pending' (2, 4, 5) são checados AGORA, antes
            # de consumir o alerta com confirmar/descartar.
            res_a = await _varrer(db, apenas_pagamento_ids=[anomalo_a])
            assert res_a["alertas_criados"] == 1, res_a
            alerta_a = (await db.execute(text(
                "SELECT id::text, alert_number, status, summary FROM fraud_alerts "
                "WHERE transaction_id = :t"), {"t": anomalo_a})).mappings().first()
            assert alerta_a, "alerta sentinela A não foi criado"

            # ════════════════ ORÁCULO 2 — SUSPEITA-NÃO-FATO ═════════════════
            try:
                await _oraculo_2_suspeita_nao_fato(db, anomalo_a)
                record(2, "alerta nasce 'pending' (suspeita) — nunca 'confirmed' automático",
                       True, f"{alerta_a['alert_number']} status=pending, summary rotulado")
            except Exception as exc:
                record(2, "suspeita-não-fato (alerta nasce 'pending', rotulado)", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 3 — RBAC DIRETORIA ════════════════════
            try:
                await _oraculo_3_rbac(ctrl.require_diretoria, admin_user, nao_admin_user)
                record(3, "require_diretoria: 403 p/ não-admin, passa p/ admin",
                       True, "gate real bloqueia operator, deixa passar admin")
            except Exception as exc:
                record(3, "RBAC diretoria (gate require_diretoria)", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 4 — SINO SÓ ADMIN ═════════════════════
            try:
                destinatarios_a = await _checar_destinatarios_admin(
                    db, alerta_id=alerta_a["id"], admins_set=admins_set)
                assert destinatarios_a.isdisjoint(set(nao_admin_reais)), \
                    f"vazou p/ não-admin real: {destinatarios_a & set(nao_admin_reais)}"
                record(4, "sino: destinatários ⊆ admins reais, disjunto de não-admin",
                       True, f"{len(destinatarios_a)} admin(s) avisado(s) p/ alerta {alerta_a['alert_number']}")
            except Exception as exc:
                record(4, "sino só admin (_varrer avisa só resolver_usuarios_por_roles(admin))", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 5 — RÓTULO SUSPEITA (CFO IA) ══════════
            # checado AGORA (alerta_a ainda 'pending' — vira 'confirmed' logo abaixo).
            try:
                await _oraculo_5_rotulo_suspeita(cfo_service, db, alerta_a["alert_number"])
                record(5, "CFO IA: alerta aberto rotulado 'suspeita/pendente', nunca fato",
                       True, f"{alerta_a['alert_number']} presente no contexto, rótulo confirmado")
            except Exception as exc:
                record(5, "rótulo suspeita no contexto do CFO IA", False,
                       f"{type(exc).__name__}: {exc}")

            # ════════════════ ORÁCULO 6 — NUNCA FABRICAR ════════════════════
            try:
                await _oraculo_6_nunca_fabricar(detectar_anomalias_pagamentos, db, pid_normal)
                record(6, "pagamento dentro do baseline (sem sinal real) → 0 alertas",
                       True, "detector não fabricou suspeita sem sinal estatístico")
            except Exception as exc:
                record(6, "nunca fabricar (pagamento normal não gera alerta)", False,
                       f"{type(exc).__name__}: {exc}")

            # ── AGORA sim consome o alerta A (ação humana explícita, gated) ──
            r_confirmar = await ctrl.confirmar_anomalia(
                alerta_id=uuid.UUID(alerta_a["id"]), user=admin_user, db=db)
            assert r_confirmar["status"] == "confirmed"
            # 409 se tentar revisar de novo — reforça "só ação humana explícita muda o status"
            conflito = False
            try:
                await ctrl.confirmar_anomalia(alerta_id=uuid.UUID(alerta_a["id"]), user=admin_user, db=db)
            except HTTPException as exc:
                conflito = exc.status_code == 409
            assert conflito, "revisar alerta já revisado deveria dar 409"

            # ── grupo B: detecção + descartar (outra ação humana) ──
            res_b = await _varrer(db, apenas_pagamento_ids=[anomalo_b])
            assert res_b["alertas_criados"] == 1, res_b
            alerta_b = (await db.execute(text(
                "SELECT id::text, alert_number FROM fraud_alerts WHERE transaction_id = :t"),
                {"t": anomalo_b})).mappings().first()
            r_descartar = await ctrl.descartar_anomalia(
                alerta_id=uuid.UUID(alerta_b["id"]),
                body=ctrl.DescartarIn(motivo=f"{MARK} falso positivo de teste"),
                user=admin_user, db=db)
            assert r_descartar["status"] == "false_positive"

            # ════════════════ MUTAÇÃO-TESTE — a suite MORDE? ════════════════
            # M1: gate morto (sempre permite) → oráculo 3 deve FALHAR.
            async def _gate_MUT_sempre_permite(user=None, **_kw):
                return user

            m1_ok, m1_det = await _expect_bite(
                lambda: _oraculo_3_rbac(_gate_MUT_sempre_permite, admin_user, nao_admin_user))
            record("MUTAÇÃO M1", "gate morto (require_diretoria sempre permite) → oráculo 3", m1_ok, m1_det)

            # M2: resolver vazado (ignora role, devolve todo mundo ativo) →
            # oráculo 4 deve FALHAR (vaza pra não-admin). Aplicado em cópia da
            # REFERÊNCIA do módulo (monkeypatch), nunca no arquivo real; restaurado
            # no finally do teste (bloco try/finally interno).
            async def _resolver_MUT_todos_ativos(_db, _roles):
                return (await _db.execute(text(
                    "SELECT id::text FROM users WHERE coalesce(is_active,true)=true"))).scalars().all()

            original_resolver = entrega.resolver_usuarios_por_roles
            entrega.resolver_usuarios_por_roles = _resolver_MUT_todos_ativos
            try:
                res_c = await _varrer(db, apenas_pagamento_ids=[anomalo_c])
                assert res_c["alertas_criados"] == 1, res_c  # grupo C é usado só aqui — nunca alertado antes
                alerta_c_id = (await db.execute(text(
                    "SELECT id::text FROM fraud_alerts WHERE transaction_id = :t"),
                    {"t": anomalo_c})).scalar()
                m2_ok, m2_det = await _expect_bite(
                    lambda: _checar_destinatarios_admin(db, alerta_id=alerta_c_id, admins_set=admins_set))
            finally:
                entrega.resolver_usuarios_por_roles = original_resolver
            record("MUTAÇÃO M2", "resolver vazado (sino avisa todo mundo ativo) → oráculo 4", m2_ok, m2_det)

            # ════════════════ ORÁCULO 1 — READ-ONLY SOBRE DINHEIRO ══════════
            # checado por ÚLTIMO: cobre TODO o ciclo (detecção A/B/C, sino,
            # CFO, confirmar/descartar, mutações M1/M2) — inter_payments nunca
            # é tocado em nenhum ponto, do início ao fim.
            try:
                snapshot_final = {
                    str(r["id"]): dict(r)
                    for r in (await db.execute(text(
                        "SELECT id, status, valor, updated_at FROM inter_payments "
                        "WHERE id = ANY(:ids)"), {"ids": payment_ids})).mappings().all()
                }
                assert snapshot_antes == snapshot_final, "inter_payments MUDOU durante o ciclo"
                record(1, "inter_payments intocado (status/valor/updated_at) em todo o ciclo",
                       True, f"{len(snapshot_antes)} pagamentos sentinela comparados, 0 diffs")
            except Exception as exc:
                record(1, "read-only sobre dinheiro (inter_payments intocado)", False,
                       f"{type(exc).__name__}: {exc}")

        finally:
            # ══════════════ LIMPEZA — 0 remanescentes (diff pré/pós) ══════════
            await db.rollback()
            if payment_ids:
                await db.execute(text(
                    "DELETE FROM fraud_alerts WHERE transaction_id = ANY(:ids)"), {"ids": payment_ids})
                await db.execute(text(
                    "DELETE FROM inter_payments WHERE id = ANY(:ids)"), {"ids": payment_ids})
            await db.execute(text(
                "DELETE FROM communication_notifications WHERE id::text <> ALL(:pre) "
                "AND extra_data->>'correlation_id' LIKE 'anomalia:%'"),
                {"pre": list(pre_notif_ids) or [""]})
            await db.execute(text(
                "DELETE FROM audit_logs WHERE id::text <> ALL(:pre) "
                "AND details->>'origem' = 'anomalia_pagamentos'"),
                {"pre": list(pre_audit_ids) or [""]})
            # rede de segurança: qualquer alerta/pagamento marcado com o sentinel
            # literal que tenha escapado da lista de ids acima (nunca por LIKE
            # em dado real — o marcador é literal e único).
            await db.execute(text(
                "DELETE FROM fraud_alerts WHERE strpos(coalesce(entity_name,''), :m) > 0"), {"m": MARK})
            await db.execute(text(
                "DELETE FROM inter_payments WHERE strpos(coalesce(destinatario->>'nome_recebedor',''), :m) > 0"),
                {"m": MARK})
            await db.commit()

            async def _rem(sql: str, params: dict | None = None) -> int:
                return int((await db.execute(text(sql), params or {})).scalar() or 0)

            rem = {
                "inter_payments": await _rem(
                    "SELECT count(*) FROM inter_payments WHERE strpos(coalesce(destinatario->>'nome_recebedor',''), :m) > 0",
                    {"m": MARK}),
                "fraud_alerts": await _rem(
                    "SELECT count(*) FROM fraud_alerts WHERE strpos(coalesce(entity_name,''), :m) > 0",
                    {"m": MARK}),
                "communication_notifications": await _rem(
                    "SELECT count(*) FROM communication_notifications WHERE id::text <> ALL(:pre) "
                    "AND extra_data->>'correlation_id' LIKE 'anomalia:%'", {"pre": list(pre_notif_ids) or [""]}),
                "audit_logs": await _rem(
                    "SELECT count(*) FROM audit_logs WHERE id::text <> ALL(:pre) "
                    "AND details->>'origem' = 'anomalia_pagamentos'", {"pre": list(pre_audit_ids) or [""]}),
            }
            total_rem = sum(rem.values())
            if total_rem == 0:
                print(f"\nLIMPEZA OK — 0 remanescentes ({', '.join(f'{k}={v}' for k, v in rem.items())})")
            else:
                print(f"\nLIMPEZA FALHOU — remanescentes: {rem}")
            record("LIMPEZA", "0 remanescentes do que a suite criou", total_rem == 0, f"total={total_rem}")

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
    print(f"OK suite 5.6a ({n_pass}/{len(oraculos)} oráculos + {n_bite}/{len(mutacoes)} mutações) — GATE LIBERADO.")
    return 0


# ───────────────────────── oráculos reutilizáveis (p/ mutação) ──────────────

async def _oraculo_2_suspeita_nao_fato(db, transaction_id) -> None:
    row = (await db.execute(text(
        "SELECT status, summary FROM fraud_alerts WHERE transaction_id = :t"),
        {"t": transaction_id})).mappings().first()
    assert row, "alerta sentinela não encontrado"
    assert row["status"] == "pending", (
        f"alerta deveria nascer 'pending' (suspeita), veio {row['status']!r}")
    assert "NÃO é fraude confirmada" in row["summary"], row["summary"]
    assert "SUSPEITA" in row["summary"], row["summary"]


async def _oraculo_3_rbac(gate_fn, admin_user, nao_admin_user) -> None:
    """RBAC diretoria. Testado contra `gate_fn` (real = ctrl.require_diretoria;
    mutado = sempre permite → deve derrubar este oráculo)."""
    bloqueado = False
    try:
        await gate_fn(user=nao_admin_user)
    except HTTPException as exc:
        bloqueado = exc.status_code == 403
    assert bloqueado, "não-admin deveria receber 403 no gate de diretoria (RBAC)"
    passou = await gate_fn(user=admin_user)
    assert passou is admin_user, "admin deveria passar no gate de diretoria"


async def _checar_destinatarios_admin(db, *, alerta_id: str, admins_set: set[str]) -> set[str]:
    """Sino só admin. Recebe o `alerta_id` de um alerta JÁ criado por
    `_varrer` (o beat chama `entrega.resolver_usuarios_por_roles` — import
    local, resolvido em tempo de chamada — mutado via monkeypatch do atributo
    do módulo `entrega` em M2/`main()` → deve derrubar este oráculo, vazando
    pra não-admin)."""
    destinatarios = set((await db.execute(text(
        "SELECT user_id::text FROM communication_notifications "
        "WHERE extra_data->>'correlation_id' = :c"), {"c": f"anomalia:{alerta_id}"})).scalars().all())
    assert destinatarios, "nenhuma notificação criada pro alerta sentinela"
    assert destinatarios.issubset(admins_set), (
        f"sino vazou p/ não-admin: {destinatarios - admins_set}")
    return destinatarios


async def _oraculo_5_rotulo_suspeita(cfo_service_mod, db, alert_number: str) -> None:
    pano = await cfo_service_mod.panorama(db)
    contexto = cfo_service_mod._formatar_contexto_financeiro(pano)
    assert alert_number in contexto, (
        f"alerta não apareceu no contexto do CFO IA: {contexto[:1500]}")
    assert "ALERTAS DE ANOMALIA ABERTOS" in contexto
    assert "NÃO são fatos confirmados" in contexto
    assert "NUNCA afirme que houve fraude confirmada" in contexto


async def _oraculo_6_nunca_fabricar(detectar_fn, db, payment_id_normal) -> None:
    alertas = await detectar_fn(db, apenas_pagamento_ids=[payment_id_normal])
    assert alertas == [], (
        f"pagamento dentro do baseline (sem sinal real) gerou alerta fabricado: {alertas}")


# ───────────────────────── helper de mutação ────────────────────────────────

async def _expect_bite(coro_factory):
    """A mutação MORDE se o oráculo (async) FALHA sob ela."""
    try:
        await coro_factory()
    except AssertionError as exc:
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    except Exception as exc:  # noqa: BLE001 — qualquer exceção sob mutação também conta como mordida
        return True, f"mordeu ({type(exc).__name__}: {exc})"
    return False, "NÃO mordeu — oráculo passou sob mutação (oráculo FRACO!)"


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        traceback.print_exc()
        code = 2
    raise SystemExit(code)
