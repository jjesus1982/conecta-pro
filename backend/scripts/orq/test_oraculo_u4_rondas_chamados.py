"""Oráculo — DGX U4: modelos de ronda com pontos, alertas idempotentes, pânico e chamado com setor
(24/09/2026).

Por que existe: o DGX (APP Vigilância / Q-Watcher) tem modelo de ronda com locais, alerta de ronda
que não roda, botão de pânico com aceite e chamado por setor que avisa o responsável. Aqui a ronda
da frente 06 sabia foto e offline, mas não sabia dizer "pulou o ponto 2", "atrasou 40 min" nem
"apertou o pânico"; e o chamado da F8 não avisava ninguém. O jeito mais fácil de isso mentir é o
motor disparar o MESMO alerta a cada rodada (spam), ou o pânico gravar o disparo sem a ocorrência.

O que afirma (recontado por SQL próprio, não pelo serviço):
  1. Esquema: ronda_modelos, ronda_alertas, ronda_alertas_disparados (+ índice ÚNICO alerta×ronda),
     inspection_rounds.modelo_id, op_setores, op_chamados.setor_id/notificado/solicitante_contato.
  2. Ronda CONCLUÍDA com 1 de 2 pontos batidos → o motor gera EXATAMENTE 1 disparo `ponto_pulado`,
     e rodar o motor de novo NÃO gera outro (idempotência), com o ponto pulado nomeado no detalhe.
  3. Ronda AGENDADA há mais tempo que a tolerância e não iniciada → 1 disparo `ronda_atrasada`
     (e só 1 na segunda rodada). Ronda dentro da tolerância → nenhum.
  4. Pânico: 1 disparo `panico` cujo occurrence_id aponta para uma ocorrência que EXISTE, é
     `grave`, no posto certo, e cujo `notificado` registra os destinatários (simulados no sandbox).
  5. Chamado aberto com setor → `notificado` tem o e-mail do responsável (status simulado/enviado);
     resolver com contato do solicitante → `notificado` ganha o item da resolução.
  6. Régua única de "ponto batido": `ponto_do_checkpoint` casa por nome, por posto e por GPS dentro
     do raio — e NÃO casa fora do raio.

Estado medido no nascimento (staging, 24/09/2026): nenhuma das tabelas existia, o serviço não
existia → VERMELHO em tudo. Fixtures marcadas 'FIXTURE DGX U4' e apagadas ao fim.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL ...: N`.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime, timedelta

FIX = "FIXTURE DGX U4"
TENANT = "00000000-0000-0000-0000-000000000000"


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.rollback()
    for sql in [
        "DELETE FROM ronda_alertas_disparados WHERE modelo_id IN (SELECT id FROM ronda_modelos WHERE nome LIKE :f) "
        "OR mensagem LIKE :f OR employee_nome LIKE :f",
        "DELETE FROM occurrence_comments WHERE occurrence_id IN (SELECT id FROM occurrences WHERE title LIKE :f OR description LIKE :f)",
        "DELETE FROM occurrences WHERE title LIKE :f OR description LIKE :f",
        "DELETE FROM inspection_checkpoints WHERE inspection_round_id IN (SELECT id FROM inspection_rounds WHERE observations LIKE :f)",
        "DELETE FROM inspection_rounds WHERE observations LIKE :f",
        "DELETE FROM ronda_alertas WHERE modelo_id IN (SELECT id FROM ronda_modelos WHERE nome LIKE :f)",
        "DELETE FROM ronda_modelos WHERE nome LIKE :f",
        "DELETE FROM op_chamados WHERE descricao LIKE :f",
        "DELETE FROM op_setores WHERE nome LIKE :f",
    ]:
        try:
            await db.execute(text(sql), {"f": f"%{FIX}%"})
            await db.commit()
        except Exception:  # noqa: BLE001 — tabela pode não existir na rodada vermelha
            await db.rollback()


async def main() -> int:
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []

    def ok(cond: bool, msg: str) -> None:
        print(("  ✓ " if cond else "  ✗ ") + msg)
        if not cond:
            falhas.append(msg)

    async with async_session_factory() as db:
        try:
            try:
                from modules.operacional.services import ronda_alertas as ra
                from modules.operacional.services import supervisao_service as ss
            except Exception as exc:  # noqa: BLE001
                ok(False, f"serviço ronda_alertas importa: {exc}")
                print(f"TOTAL falhas DGX U4: {len(falhas)}")
                return 1
            await _limpar(db)
            await ra._ensure(db)
            await ss._ensure(db)

            # ── 1. esquema
            cols = {
                (r[0], r[1])
                for r in (
                    await db.execute(
                        text(
                            "SELECT table_name, column_name FROM information_schema.columns WHERE table_name IN "
                            "('ronda_modelos','ronda_alertas','ronda_alertas_disparados','inspection_rounds','op_setores','op_chamados')"
                        )
                    )
                ).fetchall()
            }
            for tb, c in [
                ("ronda_modelos", "pontos"),
                ("ronda_alertas", "destinatarios"),
                ("ronda_alertas_disparados", "notificado"),
                ("inspection_rounds", "modelo_id"),
                ("op_setores", "email"),
                ("op_chamados", "setor_id"),
                ("op_chamados", "notificado"),
                ("op_chamados", "solicitante_contato"),
            ]:
                ok((tb, c) in cols, f"esquema: {tb}.{c} existe")
            uniq = (
                await db.execute(text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ux_ronda_disp_alerta_ronda'"))
            ).scalar() or ""
            ok(
                "UNIQUE" in uniq.upper() and "alerta_id" in uniq and "ronda_id" in uniq,
                "esquema: índice ÚNICO (alerta_id, ronda_id) — a trava da idempotência",
            )

            # ── fixtures
            posto = (
                await db.execute(
                    text("SELECT id::text, client_id::text, name FROM posts WHERE is_active ORDER BY name LIMIT 1")
                )
            ).fetchone()
            user = (
                await db.execute(text("SELECT id::text, name FROM users WHERE email = 'jjesus@conectamais.pro'"))
            ).fetchone()
            emp = (
                await db.execute(
                    text(
                        "SELECT id::text, nome FROM employees WHERE status='ativo' AND coalesce(celular,'')<>'' LIMIT 1"
                    )
                )
            ).fetchone()
            ok(bool(posto and user), "fixtures: há posto ativo e usuário do Jordan no sandbox")
            if not (posto and user):
                print(f"TOTAL falhas DGX U4: {len(falhas)}")
                return 1
            pontos = [
                {"nome": "Portaria", "lat": -3.1019, "lng": -60.0250, "raio_m": 40},
                {"nome": "Garagem", "lat": -3.1100, "lng": -60.0300, "raio_m": 40},
            ]
            m = await ra.criar_modelo(
                db,
                nome=f"{FIX} modelo",
                post_id=posto[0],
                client_id=None,
                pontos=pontos,
                intervalo_min=30,
                tolerancia_min=10,
                user_id=user[0],
            )
            dest_emails = ["jjesus@conectamais.pro", "sindico@externo.invalid"]
            a_pul = await ra.criar_alerta(
                db, modelo_id=m["id"], tipo="ponto_pulado", minutos=None, emails=dest_emails, whatsapp_employee_ids=[]
            )
            a_atr = await ra.criar_alerta(
                db, modelo_id=m["id"], tipo="ronda_atrasada", minutos=None, emails=dest_emails, whatsapp_employee_ids=[]
            )
            await ra.criar_alerta(
                db,
                modelo_id=m["id"],
                tipo="panico",
                minutos=None,
                emails=dest_emails,
                whatsapp_employee_ids=[emp[0]] if emp else [],
            )
            agora = datetime.utcnow()

            async def ronda(code: str, status: str, sched_manaus: datetime, started, completed) -> str:
                return (
                    await db.execute(
                        text(
                            "INSERT INTO inspection_rounds (code, tenant_id, inspector_id, inspector_name, status, scheduled_date, started_at, "
                            "completed_at, posts_to_visit, posts_visited, modelo_id, observations) VALUES (:c, CAST(:t AS uuid), CAST(:u AS uuid), "
                            ":n, :s, :sd, :st, :co, CAST(:pv AS jsonb), '[]', CAST(:m AS uuid), :o) RETURNING id::text"
                        ),
                        {
                            "c": code,
                            "t": TENANT,
                            "u": user[0],
                            "n": user[1] or "Jordan",
                            "s": status,
                            "sd": sched_manaus,
                            "st": started,
                            "co": completed,
                            "pv": json.dumps([posto[0]]),
                            "m": m["id"],
                            "o": FIX,
                        },
                    )
                ).scalar()

            r1 = await ronda(
                "RON-U4-00001",
                "concluida",
                agora - timedelta(hours=5),
                agora - timedelta(hours=1),
                agora - timedelta(minutes=30),
            )
            await db.execute(
                text(
                    "INSERT INTO inspection_checkpoints (inspection_round_id, post_id, checkpoint_type, status, latitude, longitude, extra_data, sequence) "
                    "VALUES (CAST(:r AS uuid), CAST(:p AS uuid), 'verificacao_posto', 'conforme', -3.10191, -60.02501, '{}', 1)"
                ),
                {"r": r1, "p": posto[0]},
            )  # bate «Portaria» por GPS (≈1 m); «Garagem» fica sem checkpoint
            r2 = await ronda(
                "RON-U4-00002", "agendada", agora - ra._MANAUS_UTC - timedelta(minutes=45), None, None
            )  # 45 min atrás, tol 10
            r3 = await ronda(
                "RON-U4-00003", "agendada", agora - ra._MANAUS_UTC - timedelta(minutes=5), None, None
            )  # dentro da tolerância
            await db.commit()

            # ── 2/3. motor duas vezes
            n1 = await ra.avaliar_rondas(db, agora, simular=True)
            n2 = await ra.avaliar_rondas(db, agora, simular=True)
            disp = (
                await db.execute(
                    text(
                        "SELECT alerta_id::text, ronda_id::text, tipo, detalhe, notificado FROM ronda_alertas_disparados WHERE modelo_id = CAST(:m AS uuid)"
                    ),
                    {"m": m["id"]},
                )
            ).fetchall()
            pul = [d for d in disp if d[2] == "ponto_pulado"]
            atr = [d for d in disp if d[2] == "ronda_atrasada"]
            ok(
                len(n1) == 2 and len(n2) == 0,
                f"motor: 1ª rodada gerou {len(n1)} (esperado 2), 2ª rodada gerou {len(n2)} (esperado 0)",
            )
            ok(
                len(pul) == 1 and pul[0][0] == a_pul["id"] and pul[0][1] == r1,
                "ponto_pulado: exatamente 1 disparo, para a ronda concluída",
            )
            det = (pul[0][3] if isinstance(pul[0][3], dict) else json.loads(pul[0][3] or "{}")) if pul else {}
            ok(
                det.get("pulados") == ["Garagem"],
                f"ponto_pulado: detalhe nomeia o ponto pulado (Garagem) — veio {det.get('pulados')}",
            )
            ok(
                len(atr) == 1 and atr[0][0] == a_atr["id"] and atr[0][1] == r2,
                "ronda_atrasada: exatamente 1 disparo, para a ronda 45 min atrasada; a de 5 min não",
            )
            ok(not any(d[1] == r3 for d in disp), "ronda dentro da tolerância não dispara")
            notif = (pul[0][4] if isinstance(pul[0][4], list) else json.loads(pul[0][4] or "[]")) if pul else []
            ok(
                # oráculo roda na varredura DENTRO da produção: com simular=True nada sai, em
                # qualquer ambiente. Antes desta parede o dono recebia e-mail da fixture toda noite.
                len(notif) == 2 and all(n["status"] == "simulado" for n in notif),
                f"notificação: 2 destinos registrados e TODOS simulados — veio {[(n.get('para'), n.get('status')) for n in notif]}",
            )
            n_dup = (
                await db.execute(
                    text(
                        "SELECT count(*) - count(DISTINCT (alerta_id, ronda_id)) FROM ronda_alertas_disparados WHERE alerta_id IS NOT NULL"
                    )
                )
            ).scalar()
            ok(n_dup == 0, "idempotência global: nenhum (alerta, ronda) repetido na tabela")

            # ── 4. pânico
            p = await ra.disparar_panico(
                db,
                user_id=user[0],
                employee_id=emp[0] if emp else None,
                employee_nome=f"{FIX} colaborador",
                lat=-3.1,
                lng=-60.02,
                post_id=posto[0],
                ronda_id=None,
                mensagem=f"{FIX} teste de pânico",
                simular=True,  # oráculo roda na varredura DENTRO da produção: nunca notifica de verdade
            )
            row = (
                await db.execute(
                    text(
                        "SELECT d.tipo, d.status, o.severity, o.status, o.post_id::text, d.notificado FROM ronda_alertas_disparados d "
                        "JOIN occurrences o ON o.id = d.occurrence_id WHERE d.id = CAST(:i AS uuid)"
                    ),
                    {"i": p["id"]},
                )
            ).fetchone()
            ok(bool(row) and row[0] == "panico" and row[1] == "aberto", "pânico: disparo tipo panico aberto")
            ok(
                bool(row) and row[2] == "grave" and row[3] in ("aberta", "open") and row[4] == posto[0],
                f"pânico: ocorrência GRAVE aberta no posto — veio {row[2:5] if row else None}",
            )
            pn = (row[5] if isinstance(row[5], list) else json.loads(row[5] or "[]")) if row else []
            ok(
                len(pn) >= 2 and all(n["status"] == "simulado" for n in pn),
                f"pânico: destinatários do alerta panico notificados — {[(n.get('canal'), n.get('status')) for n in pn]}",
            )
            sem_occ = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM ronda_alertas_disparados WHERE tipo = 'panico' AND occurrence_id IS NULL"
                    )
                )
            ).scalar()
            ok(sem_occ == 0, "pânico: nenhum disparo panico sem ocorrência (na tabela inteira)")
            rec = await ra.mudar_status_disparo(db, disparo_id=p["id"], novo="reconhecido", user_id=user[0])
            ok(rec["status"] == "reconhecido", "pânico: Reconhecer muda o status")

            # ── 5. chamado com setor
            s = await ra.criar_setor(
                db,
                nome=f"{FIX} setor",
                client_id=posto[1],
                contract_id=None,
                responsavel="Zelador",
                email="zelador@externo.invalid",
                whatsapp=None,
            )
            ch = await ss.abrir_chamado(
                db,
                descricao=f"{FIX} chamado com setor para testar aviso",
                post_id=posto[0],
                aberto_por="cliente",
                solicitante_nome="Síndico",
                prioridade="alta",
                user_id=user[0],
                setor_id=s["id"],
                solicitante_contato="sindico@externo.invalid",
            )
            nt = (
                await db.execute(
                    text("SELECT setor_id::text, notificado FROM op_chamados WHERE id = CAST(:i AS uuid)"),
                    {"i": ch["id"]},
                )
            ).fetchone()
            nl = nt[1] if isinstance(nt[1], list) else json.loads(nt[1] or "[]")
            ok(nt[0] == s["id"], "chamado: setor_id gravado")
            ok(
                any(n["para"] == "zelador@externo.invalid" and n["status"] in ("simulado", "enviado") for n in nl),
                f"chamado: responsável do setor avisado — {[(n.get('para'), n.get('status')) for n in nl]}",
            )
            await ss.resolver_chamado(db, chamado_id=ch["id"], resolucao="Resolvido no teste U4")
            nl2 = (
                await db.execute(
                    text("SELECT notificado FROM op_chamados WHERE id = CAST(:i AS uuid)"), {"i": ch["id"]}
                )
            ).scalar()
            nl2 = nl2 if isinstance(nl2, list) else json.loads(nl2 or "[]")
            ok(
                any(n.get("evento") == "resolucao" and n["para"] == "sindico@externo.invalid" for n in nl2),
                "chamado: resolver avisou o solicitante (item evento=resolucao)",
            )

            # ── 6. régua do ponto batido
            ok(ra.ponto_do_checkpoint(pontos, {"ponto": "garagem"}) == 1, "régua: casa por nome (case-insensitive)")
            ok(
                ra.ponto_do_checkpoint(pontos, {"lat": -3.10195, "lng": -60.02505}) == 0,
                "régua: casa por GPS dentro do raio",
            )
            ok(
                ra.ponto_do_checkpoint(pontos, {"lat": -3.1040, "lng": -60.0250}) is None,
                "régua: NÃO casa a 230 m do ponto (raio 40)",
            )
        finally:
            await _limpar(db)
            try:
                sobra = (
                    await db.execute(text("SELECT count(*) FROM ronda_modelos WHERE nome LIKE :f"), {"f": f"%{FIX}%"})
                ).scalar()
            except Exception:  # noqa: BLE001 — rodada vermelha: a tabela não existe
                await db.rollback()
                sobra = "tabela inexistente"
            print(f"  fixtures apagadas (sobra: {sobra})")

    print(f"TOTAL falhas DGX U4: {len(falhas)}")
    return 1 if falhas else 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except SystemExit as e:
        print("TOTAL falhas DGX U4: 1" if e.code else "")
        sys.exit(e.code)
