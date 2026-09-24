"""Oráculo — integração de batimentos (AFD de relógio → batidas) e fechamento como ATO
(DGX T2, 24/09/2026).

Por que existe: `POST /hr/rep/afd/import` gravava só `afd_records` — nenhuma marcação virava
batida do cartão; e o mês "fechado" (`time_sheets` / `gp_monthly_closings`) não travava ajuste,
lançamento manual nem importação. Duas coisas que precisam ser verdade juntas: o que entra pelo
relógio entra UMA vez, e não entra em mês fechado sem reabrir com motivo.

O que afirma (fixtures 'FIXTURE-DGX-T2', apagadas ao fim, mesmo em falha):
  a. parser: linha 671 (ISO ±HHMM, CPF) e linha 1510 (DDMMAAAA HHMM, PIS) → mesmo dicionário.
  b. «só validar» não grava nada e conta igual ao que gravaria.
  c. importar 4 marcações de uma pessoa real (mês 12/2019) → 4 batidas com chave afd:<origem>:<nsr>,
     entrada/saída alternadas por dia, device_type='relogio'; CPF desconhecido → sem_pessoa;
     NSR repetido no arquivo → duplicada; marcação em mês FECHADO de outra pessoa → mes_fechado, não grava.
  d. importar o MESMO arquivo de novo → 0 importadas (idempotência pela chave).
  e. `FONTES_MEDIDAS` do espelho contém 'relogio' e, fora das fixtures, há 0 batidas com esse
     device_type (o espelho já calculado é idêntico por construção).
  f. `competencia_fechada` responde para a pessoa/mês fechado e cala para mês aberto.
  g. reabrir exige motivo, desfaz o fechamento mensal da fixture, registra em `ponto_reaberturas`
     e recusa reabrir o que não está fechado.

Estado medido no nascimento (staging, 24/09/2026): `ponto.integracao_batimentos` e `ponto.fechamento`
não existiam → ImportError → VERMELHO. gp_monthly_closings: 50 fechados em 06/2026; time_sheets:
1 fechado em 07/2026; gp_clock_punches com device_type='relogio': 0.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

from sqlalchemy import text

ORIGEM = "FIXTURE-DGX-T2"
FIX = "FIXTURE DGX T2"


def _l671(nsr: int, tipo: str, iso: str, cpf: str) -> str:
    return f"{nsr:09d}{tipo}{iso}{cpf.zfill(12)}ABCD"


def _l1510(nsr: int, ddmmaaaa: str, hhmm: str, pis: str) -> str:
    return f"{nsr:09d}3{ddmmaaaa}{hhmm}{pis.zfill(12)}"


async def _limpar(db):
    await db.execute(text("DELETE FROM gp_clock_punches WHERE chave_idempotente LIKE :p"), {"p": f"afd:{ORIGEM}:%"})
    await db.execute(text("DELETE FROM ponto_integracoes_batimentos WHERE origem = :o"), {"o": ORIGEM})
    # DGX V4: desde 24/09 as marcações recusadas também entram na fila `dp_importacao_falhas`
    # (origem afd) — a fixture precisa sair de lá também, senão o painel de pendências do DP
    # nasce com duas falhas de teste que ninguém consegue resolver.
    await db.execute(
        text("DELETE FROM dp_importacao_falhas WHERE origem = 'afd' AND identificador_origem LIKE :p"),
        {"p": f"{ORIGEM}:%"},
    )
    await db.execute(text("DELETE FROM gp_monthly_closings WHERE employee_id = :e"), {"e": FIX})
    await db.execute(text("DELETE FROM ponto_reaberturas WHERE quem = :q"), {"q": FIX})
    await db.commit()


async def main() -> int:
    from core.database import async_session_factory
    from modules.people_management.hr.services import espelho_service
    from modules.people_management.ponto import fechamento
    from modules.people_management.ponto import integracao_batimentos as ib

    falhas: list[str] = []
    async with async_session_factory() as db:
        await ib._ensure(db)
        await fechamento._ensure(db)
        await _limpar(db)
        try:
            # ── a) parser ────────────────────────────────────────────────────────────────
            p1 = ib.parse_linha(_l671(1, "3", "2019-12-02T07:00:00-0400", "03527554238"))
            p2 = ib.parse_linha(_l1510(2, "02122019", "1900", "21226260340"))
            if not (
                p1
                and p1["doc"] == "03527554238"
                and p1["ts"].isoformat() == "2019-12-02T07:00:00"
                and p1["campo"] == "cpf"
            ):
                falhas.append(f"a) linha 671 mal lida: {p1}")
            if not (
                p2
                and p2["doc"] == "21226260340"
                and p2["ts"].isoformat() == "2019-12-02T19:00:00"
                and p2["campo"] == "pis"
            ):
                falhas.append(f"a) linha 1510 mal lida: {p2}")
            if ib.parse_linha("000000009900000010") is not None or "erro" not in (ib.parse_linha("abc") or {}):
                falhas.append("a) trailer devia ser ignorado e lixo devia dar erro")

            # pessoa real com CPF e PIS; outra pessoa com mês FECHADO
            emp = (
                await db.execute(
                    text(
                        "SELECT CAST(id AS text), regexp_replace(cpf,'\\D','','g'), regexp_replace(pis,'\\D','','g'), nome "
                        "FROM employees WHERE status='ativo' AND cpf IS NOT NULL AND cpf<>'' AND pis IS NOT NULL AND pis<>'' "
                        "ORDER BY nome LIMIT 1"
                    )
                )
            ).first()
            fech = (
                await db.execute(
                    text(
                        "SELECT CAST(e.id AS text), regexp_replace(e.cpf,'\\D','','g'), c.month, c.year FROM gp_monthly_closings c "
                        "JOIN employees e ON CAST(e.id AS text) = c.employee_id WHERE c.fechado IS TRUE AND e.cpf IS NOT NULL AND e.cpf<>'' "
                        "ORDER BY c.year DESC, c.month DESC LIMIT 1"
                    )
                )
            ).first()
            if not emp or not fech:
                falhas.append(f"pré-condição: pessoa com CPF/PIS ({bool(emp)}) e mês fechado ({bool(fech)})")
                raise RuntimeError("sem pré-condição")
            eid, cpf, pis, nome = emp
            feid, fcpf, fm, fy = fech
            arq = "\n".join(
                [
                    "0000000001" + "1" * 90,  # cabeçalho (ignorado)
                    _l671(10, "3", "2019-12-02T07:00:00-0400", cpf),
                    _l1510(11, "02122019", "1900", pis),
                    _l671(12, "7", "2019-12-04T07:00:00-0400", cpf),
                    _l671(13, "3", "2019-12-04T19:00:00-0400", cpf),
                    _l671(14, "3", "2019-12-06T07:00:00-0400", "00000000000"),  # sem pessoa
                    _l671(12, "7", "2019-12-04T07:00:00-0400", cpf),  # NSR repetido no arquivo
                    _l671(15, "3", f"{fy:04d}-{fm:02d}-15T07:00:00-0400", fcpf),  # mês fechado de outra pessoa
                    "000000016" + "9" + "000000016",
                ]
            )
            # ── b) só validar ────────────────────────────────────────────────────────────
            s = await ib.importar(db, arq, ORIGEM, FIX, simular=True, arquivo="oraculo.txt")
            n0 = (
                await db.execute(
                    text("SELECT count(*) FROM gp_clock_punches WHERE chave_idempotente LIKE :p"),
                    {"p": f"afd:{ORIGEM}:%"},
                )
            ).scalar()
            if n0 != 0 or s["importadas"] != 4 or s["sem_pessoa"] != 1 or s["duplicadas"] != 1 or s["mes_fechado"] != 1:
                falhas.append(f"b) simulação: gravou {n0}, resumo {s}")
            # ── c) importar ──────────────────────────────────────────────────────────────
            r = await ib.importar(db, arq, ORIGEM, FIX, arquivo="oraculo.txt")
            rows = (
                await db.execute(
                    text(
                        "SELECT punch_timestamp, punch_type, device_type, CAST(employee_id AS text) FROM gp_clock_punches "
                        "WHERE chave_idempotente LIKE :p ORDER BY punch_timestamp"
                    ),
                    {"p": f"afd:{ORIGEM}:%"},
                )
            ).fetchall()
            tipos = [x[1] for x in rows]
            if r["importadas"] != 4 or len(rows) != 4:
                falhas.append(f"c) importadas {r['importadas']} / gravadas {len(rows)}")
            if tipos != ["entrada", "saida", "entrada", "saida"]:
                falhas.append(f"c) tipos alternados esperados, veio {tipos}")
            if any(x[2] != "relogio" or x[3] != eid for x in rows):
                falhas.append("c) device_type/employee errados")
            if r["sem_pessoa"] != 1 or r["duplicadas"] != 1 or r["mes_fechado"] != 1:
                falhas.append(f"c) contagem: {r}")
            if (
                await db.execute(
                    text(
                        "SELECT count(*) FROM gp_clock_punches WHERE CAST(employee_id AS text)=:e AND punch_timestamp::date = :d"
                    ),
                    {"e": feid, "d": date(fy, fm, 15)},
                )
            ).scalar() and any(str(x[3]) == feid for x in rows):
                falhas.append("c) gravou batida em mês fechado")
            # ── d) de novo = nada ────────────────────────────────────────────────────────
            r2 = await ib.importar(db, arq, ORIGEM, FIX, arquivo="oraculo.txt")
            n2 = (
                await db.execute(
                    text("SELECT count(*) FROM gp_clock_punches WHERE chave_idempotente LIKE :p"),
                    {"p": f"afd:{ORIGEM}:%"},
                )
            ).scalar()
            if r2["importadas"] != 0 or n2 != 4 or r2["duplicadas"] != 5:
                falhas.append(
                    f"d) reimportação: importadas {r2['importadas']}, duplicadas {r2['duplicadas']}, total {n2}"
                )
            # ── e) espelho ───────────────────────────────────────────────────────────────
            if "relogio" not in espelho_service.FONTES_MEDIDAS:
                falhas.append("e) 'relogio' não é fonte medida no espelho")
            n_rel = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM gp_clock_punches WHERE device_type='relogio' AND coalesce(chave_idempotente,'') NOT LIKE :p"
                    ),
                    {"p": f"afd:{ORIGEM}:%"},
                )
            ).scalar()
            if n_rel != 0:
                falhas.append(
                    f"e) {n_rel} batida(s) 'relogio' fora da fixture — o espelho anterior não é mais idêntico por construção"
                )
            # ── f) trava ─────────────────────────────────────────────────────────────────
            if not await fechamento.competencia_fechada(db, feid, date(fy, fm, 10)):
                falhas.append(f"f) {fm:02d}/{fy} de {feid} devia estar FECHADO")
            if await fechamento.competencia_fechada(db, eid, date(2019, 12, 15)):
                falhas.append("f) 12/2019 devia estar aberto")
            # ── g) reabrir ───────────────────────────────────────────────────────────────
            await db.execute(
                text(
                    "INSERT INTO gp_monthly_closings (employee_id, month, year, fechado, fechado_por, fechado_em, created_at) "
                    "VALUES (:e, 12, 2019, true, :q, now(), now())"
                ),
                {"e": FIX, "q": FIX},
            )
            await db.commit()
            try:
                await fechamento.reabrir(db, FIX, 12, 2019, "x", FIX)
                falhas.append("g) aceitou motivo curto")
            except ValueError:
                await db.rollback()
            g = await fechamento.reabrir(db, FIX, 12, 2019, "oráculo: reabertura de fixture", FIX)
            ainda = (
                await db.execute(
                    text("SELECT count(*) FROM gp_monthly_closings WHERE employee_id=:e AND fechado IS TRUE"),
                    {"e": FIX},
                )
            ).scalar()
            reg = (
                await db.execute(
                    text("SELECT count(*) FROM ponto_reaberturas WHERE quem=:q AND employee_id=:e"),
                    {"q": FIX, "e": FIX},
                )
            ).scalar()
            if g["fechamentos"] != 1 or ainda != 0 or reg != 1:
                falhas.append(f"g) reabrir: {g}, ainda fechados {ainda}, registros {reg}")
            try:
                await fechamento.reabrir(db, FIX, 12, 2019, "de novo, sem nada fechado", FIX)
                falhas.append("g) reabriu o que não estava fechado")
            except ValueError:
                await db.rollback()
            print(
                f"pessoa: {nome} · fechado: {fm:02d}/{fy} · importadas {r['importadas']} · reimportação {r2['importadas']} · reabertura #{g['id']}"
            )
        except RuntimeError:
            pass
        finally:
            await db.rollback()
            await _limpar(db)

    for f in falhas:
        print("DESVIO:", f)
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        return 1
    print("OK integração de batimentos: parser 1510/671, idempotente, mês fechado trava, reabrir é ato com motivo")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
