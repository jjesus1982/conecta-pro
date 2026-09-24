"""Oráculo — a direção da batida medida, não escolhida (DGX Y2, 24/09/2026).

Por que existe: `DGX_X4_pareador_unico.md` §7.1 deixou aberta a divergência que SOBRA entre os
pareadores de batida da casa — não a do DIA (essa a X4 fechou: Σ|Δ| de 162 dias caiu para 2), a
do PAR. Duas réguas discordam sobre **se o tipo da batida manda**:

  · **régua A**, cronológica (`horas_service.parear_batidas`) — a da FOLHA e do FECHAMENTO.
    Ignora `punch_type` de propósito: batida de noturno vem tipada errada com frequência e
    confiar no tipo fazia o turno inteiro sumir, levando o adicional noturno junto.
  · **régua B**, com direção (`time_record_service._pair_punches`) — a da TELA DE PONTO do DP.
    «saída não abre turno», regra que nasceu do defeito real do commit 5e0bbc1f (sem ela,
    `[saída de ontem, entrada de hoje]` viravam 12 h de trabalho sobre o DESCANSO).

Escolher uma muda `horas_trabalhadas`/`horas_noturnas`, de onde saem HE 50% e adicional
noturno: é dinheiro. **A frente Y2 não escolhe — mede, explica e prepara a escolha**, gravando
em `ponto_divergencia_regua`. Este oráculo é a trava dessa medição.

A regra que ele afirma (regra, não fotografia):
  (a) **fixture determinística**: um 12x36 noturno em que a pessoa bateu «saída» ao VOLTAR do
      intervalo (19:00 entrada · 00:00 saída · 01:00 SAÍDA · 07:00 saída). A régua A pareia
      (19:00→00:00) e (01:00→07:00) = 11 h; a régua B recusa a de 01:00 e fica com 5 h. A
      apuração tem de gravar esse dia com Δ = 6 h e causa `tipo_errado_no_aparelho`. Uma
      segunda fixture (batida duplicada a 1 min) tem de sair como `batida_duplicada`.
  (b) **apurar 2× não duplica**: mesma contagem de linhas, mesmas chaves, mesmo Σ|Δ|. A chave
      é (competência, employee_id, dia) e existe índice único.
  (c) **a soma das horas por causa == o total**, recontado por SQL PRÓPRIO do oráculo sobre a
      tabela — não pelo dicionário que `apurar` devolve. Toda linha tem causa da lista fechada.
  (d) **nenhum `indeterminado` sem as duas réguas terem rodado**: uma linha só pode confessar
      ignorância se houver batida crua registrada E pelo menos uma das réguas tiver produzido
      par ou órfã naquele dia. `indeterminado` com `batidas` vazio é medição que não aconteceu.
  (e) **paralelo cego: Σ|Δ| contra `hr_payslips` = R$ 0,00** — e os espelhos de `time_sheets`
      intactos. Fotografia de proventos/descontos/líquido de TODO holerite e de dias/horas de
      TODO espelho antes e depois de rodar `apurar` nas três competências.

Estado medido no nascimento (staging, cópia de produção de 24/09/2026):
  ANTES (árvore-base, sem a frente): o módulo `divergencia_regua` não existe e a tabela
  `ponto_divergencia_regua` não existe — (a)…(d) vermelhos por ausência de medição.
  DEPOIS: (a) verde nas duas fixtures (Δ 6,00 h e 7,00 h, causas certas); (b) 36 linhas de
  09/2026 nas duas passadas, mesmas 36 chaves, mesmo Σ|Δ|; (c) 65 pessoa×dia · Σ|Δ| 172,27 h
  COM as 6 linhas de fixture — tipo_errado_no_aparelho 51/115,16 h · batida_duplicada
  11/44,52 h · virada_de_meia_noite 1/12,53 h · batida_faltando 2/0,06 h · indeterminado 0;
  sem as fixtures, o dado REAL de 07+08+09/2026 é **59 pessoa×dia, 28 pessoas, Σ|Δ| 133,27 h**;
  (d) 0 indeterminados, nenhum sem régua rodada; (e) R$ 0,00 em 793 holerites, 0 dos 285
  espelhos reescritos; (§7) ambas_erram 50 · régua A 6 · régua B 3 · empate 2 · sem turno 4.

Os números de (c) e (§7) são FOTOGRAFIA e vão mudar quando o DP corrigir batida — o oráculo não
os afirma. O que ele afirma é a REGRA: a fixture, a idempotência, o fechamento da soma por causa,
o `indeterminado` honesto e o R$ 0,00.

Como roda (container efêmero contra o sandbox, PYTHONPATH=/app):
  ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \\
    | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\\n' ' ')
  docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \\
    --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \\
    -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \\
    -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
    conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_y2_direcao_batida.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date, datetime, timedelta

MARCA = "FIXTURE DGX Y2"

#: bateu «saída» ao VOLTAR do intervalo — o arquétipo da §7.1
FIX_TIPO = "77777777-d6c1-4f11-9e11-dc2000000001"
#: toque duplo no aparelho na entrada
FIX_DUP = "77777777-d6c1-4f11-9e11-dc2000000002"

FIX_ANO, FIX_MES = 2026, 9
FIX_COMP = f"{FIX_ANO:04d}-{FIX_MES:02d}"
FIX_DIAS = (date(2026, 9, 2), date(2026, 9, 4), date(2026, 9, 6))

COMPETENCIAS = ("2026-07", "2026-08", "2026-09")

#: (dia+, hora, tipo) por fixture. A régua A pareia cronologicamente; a régua B recusa «saida»
#: como abertura de turno.
BATIDAS = {
    # A: (19:00→00:00)=5h + (01:00→07:00)=6h = 11h · B: 5h (recusa a de 01:00) → Δ = 6h
    FIX_TIPO: ((0, "19:00", "entrada"), (1, "00:00", "saida"), (1, "01:00", "saida"), (1, "07:00", "saida")),
    # A: (19:00→19:01)=0,02h + (00:00→07:00)=7h · B: funde? não — 19:01 entrada, gap 4h59 > 3h.
    # O que importa é a CAUSA: duas batidas a 1 min uma da outra.
    FIX_DUP: ((0, "19:00", "entrada"), (0, "19:01", "entrada"), (1, "00:00", "saida"), (1, "07:00", "saida")),
}

CAUSA_ESPERADA = {FIX_TIPO: "tipo_errado_no_aparelho", FIX_DUP: "batida_duplicada"}


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.execute(text("DELETE FROM gp_clock_punches WHERE posto_nome = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM shifts WHERE notes = :m"), {"m": MARCA})
    await db.execute(
        text("DELETE FROM ponto_divergencia_regua WHERE employee_id IN (:a, :b)"),
        {"a": FIX_TIPO, "b": FIX_DUP},
    )
    await db.execute(text("DELETE FROM employees WHERE nome LIKE :m"), {"m": f"{MARCA}%"})
    await db.commit()


async def _semear(db) -> None:
    from sqlalchemy import text

    await _limpar(db)
    ref = (await db.execute(text("SELECT scale_id::text, post_id::text FROM shifts LIMIT 1"))).first()
    if ref is None:
        raise RuntimeError("sandbox sem nenhum shift — não há scale_id/post_id para a fixture")
    for fid, sufixo in ((FIX_TIPO, "SAIDA-AO-VOLTAR"), (FIX_DUP, "TOQUE-DUPLO")):
        await db.execute(
            text(
                "INSERT INTO employees (id, nome, status, escala_padrao, data_admissao, is_homologacao) "
                "VALUES (CAST(:id AS uuid), :nome, 'ativo', '12x36', CAST(:adm AS date), false)"
            ),
            {"id": fid, "nome": f"{MARCA} {sufixo}", "adm": date(2026, 6, 1)},
        )
        for d in FIX_DIAS:
            await db.execute(
                text(
                    "INSERT INTO shifts (id, scale_id, post_id, employee_id, status, shift_date, "
                    "planned_start_time, planned_end_time, is_night_shift, notes) "
                    "VALUES (gen_random_uuid(), CAST(:sc AS uuid), CAST(:po AS uuid), CAST(:e AS uuid), "
                    "'scheduled', CAST(:d AS date), TIME '19:00', TIME '07:00', true, :m)"
                ),
                {"sc": ref[0], "po": ref[1], "e": fid, "d": d, "m": MARCA},
            )
            for n, (dd, hhmm, tipo) in enumerate(BATIDAS[fid]):
                ts = datetime.combine(d + timedelta(days=dd), datetime.strptime(hhmm, "%H:%M").time())
                await db.execute(
                    text(
                        "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, punch_timestamp, "
                        "status, device_type, posto_nome) "
                        "VALUES (:pid, CAST(:e AS uuid), :t, :ts, 'approved', 'mobile', :m)"
                    ),
                    {"pid": f"fixy2-{sufixo}-{d.isoformat()}-{n}", "e": fid, "t": tipo, "ts": ts, "m": MARCA},
                )
    await db.commit()


# ─────────────────── (e) a fotografia do dinheiro, antes e depois ───────────────────


async def _foto_dinheiro(db) -> tuple[dict, dict]:
    """(holerites, espelhos) — o que NÃO pode se mexer quando a apuração roda."""
    from sqlalchemy import text

    hol = {
        str(r[0]): (float(r[1] or 0), float(r[2] or 0), float(r[3] or 0))
        for r in (
            await db.execute(
                text(
                    "SELECT id::text, coalesce(total_earnings,0), coalesce(total_deductions,0), "
                    "coalesce(net_salary,0) FROM hr_payslips WHERE status::text <> 'cancelled'"
                )
            )
        ).fetchall()
    }
    esp = {
        str(r[0]): (int(r[1] or 0), int(r[2] or 0))
        for r in (
            await db.execute(
                text(
                    "SELECT id::text, coalesce(work_days_worked,0), coalesce(hours_worked_minutes,0) "
                    "FROM time_sheets WHERE is_deleted = false"
                )
            )
        ).fetchall()
    }
    return hol, esp


# ───────────────────────────── main ─────────────────────────────


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory

    falhas: list[str] = []
    resumo: list[str] = []

    try:
        from modules.people_management.ponto.services import divergencia_regua as dr
    except ImportError as exc:
        print(f"FALHOU: (a-e) o serviço da frente Y2 não existe — {exc}")
        print("TOTAL desvios: 1")
        return 1

    async with async_session_factory() as db:
        # a tabela de conferência tem de existir ANTES do `_limpar` — é a DDL idempotente da
        # própria frente que a cria, e sem ela o primeiro DELETE aborta a transação inteira.
        await dr._ensure(db)
        try:
            hol_antes, esp_antes = await _foto_dinheiro(db)
            await _semear(db)

            # ───── (b) idempotência + (a) fixture ─────
            r1 = await dr.apurar(db, FIX_COMP)
            chaves1 = {
                (a, str(b))
                for a, b in (
                    await db.execute(
                        text("SELECT employee_id, dia FROM ponto_divergencia_regua WHERE competencia = :c"),
                        {"c": FIX_COMP},
                    )
                ).fetchall()
            }
            r2 = await dr.apurar(db, FIX_COMP)
            chaves2 = {
                (a, str(b))
                for a, b in (
                    await db.execute(
                        text("SELECT employee_id, dia FROM ponto_divergencia_regua WHERE competencia = :c"),
                        {"c": FIX_COMP},
                    )
                ).fetchall()
            }
            resumo.append(
                f"(b) apurar 2× em {FIX_COMP}: {r1['linhas']} → {r2['linhas']} linha(s) · "
                f"chaves {len(chaves1)} → {len(chaves2)} · Σ|Δ| {r1['soma_abs_horas']} → {r2['soma_abs_horas']} h"
            )
            if r1["linhas"] != r2["linhas"] or chaves1 != chaves2:
                falhas.append(
                    f"(b) apurar 2× mudou a apuração: {r1['linhas']}→{r2['linhas']} linhas, "
                    f"{len(chaves1)}→{len(chaves2)} chaves"
                )
            if abs(r1["soma_abs_horas"] - r2["soma_abs_horas"]) > 0.001:
                falhas.append(f"(b) Σ|Δ| mudou entre as duas passadas: {r1['soma_abs_horas']} → {r2['soma_abs_horas']}")

            for fid, causa_esperada in CAUSA_ESPERADA.items():
                linhas = (
                    await db.execute(
                        text(
                            "SELECT dia, horas_a, horas_b, delta_h, causa, quem_acerta "
                            "FROM ponto_divergencia_regua WHERE employee_id = :e ORDER BY dia"
                        ),
                        {"e": fid},
                    )
                ).fetchall()
                causas = {x[4] for x in linhas}
                deltas = sorted({round(abs(float(x[3])), 2) for x in linhas})
                resumo.append(
                    f"(a) fixture {fid[-1]} ({causa_esperada}): {len(linhas)} dia(s) divergente(s) de "
                    f"{len(FIX_DIAS)} plantões · Δ {deltas} h · causa(s) {sorted(causas) or ['—']} · "
                    f"quem acerta {sorted({x[5] for x in linhas}) or ['—']}"
                )
                if len(linhas) != len(FIX_DIAS):
                    falhas.append(
                        f"(a) fixture {causa_esperada}: {len(linhas)} dia(s) divergente(s), "
                        f"esperado {len(FIX_DIAS)} — a divergência plantada não foi medida"
                    )
                if causas != {causa_esperada}:
                    falhas.append(f"(a) fixture {causa_esperada}: causa(s) apurada(s) {sorted(causas)}")
            # o Δ da fixture do tipo é exato: 11 h (régua A) − 5 h (régua B)
            d_tipo = (
                await db.execute(
                    text(
                        "SELECT round(horas_a,2), round(horas_b,2), round(delta_h,2) "
                        "FROM ponto_divergencia_regua WHERE employee_id = :e ORDER BY dia LIMIT 1"
                    ),
                    {"e": FIX_TIPO},
                )
            ).first()
            if d_tipo and (float(d_tipo[0]) != 11.0 or float(d_tipo[1]) != 5.0 or float(d_tipo[2]) != 6.0):
                falhas.append(
                    f"(a) fixture «saída ao voltar»: régua A {d_tipo[0]} h / régua B {d_tipo[1]} h / "
                    f"Δ {d_tipo[2]} h — esperado 11,00 / 5,00 / 6,00"
                )
            elif d_tipo:
                resumo.append(
                    "(a) fixture «saída ao voltar»: régua A 11,00 h × régua B 5,00 h, Δ 6,00 h "
                    "(a batida de 01:00 tipada «saída» abre turno numa e não na outra)"
                )

            # ───── as três competências reais ─────
            for comp in COMPETENCIAS:
                await dr.apurar(db, comp)

            # ───── (c) soma por causa == total, recontado por SQL próprio ─────
            por_causa = (
                await db.execute(
                    text(
                        "SELECT causa, count(*), round(sum(abs(delta_h)), 2) "
                        "FROM ponto_divergencia_regua GROUP BY causa ORDER BY 3 DESC"
                    )
                )
            ).fetchall()
            tot_dias, tot_h = (
                await db.execute(
                    text("SELECT count(*), coalesce(round(sum(abs(delta_h)), 2), 0) FROM ponto_divergencia_regua")
                )
            ).first()
            soma_causas = round(sum(float(x[2] or 0) for x in por_causa), 2)
            dias_causas = sum(int(x[1]) for x in por_causa)
            resumo.append(
                f"(c) {tot_dias} pessoa×dia divergentes · Σ|Δ| {float(tot_h):.2f} h · por causa: "
                + " · ".join(f"{x[0]} {x[1]}/{float(x[2] or 0):.2f} h" for x in por_causa)
            )
            if dias_causas != int(tot_dias) or abs(soma_causas - float(tot_h)) > 0.02:
                falhas.append(
                    f"(c) a soma por causa não fecha com o total: {dias_causas} dias/{soma_causas} h "
                    f"× {tot_dias} dias/{float(tot_h):.2f} h"
                )
            desconhecidas = [x[0] for x in por_causa if x[0] not in dr.CAUSAS]
            if desconhecidas:
                falhas.append(f"(c) causa(s) fora da lista fechada: {desconhecidas}")

            # ───── (d) indeterminado só com as duas réguas rodadas ─────
            n_ind, n_ind_cego = (
                await db.execute(
                    text(
                        "SELECT count(*), count(*) FILTER ("
                        "  WHERE jsonb_array_length(batidas) = 0 OR (pares_a = 0 AND pares_b = 0)) "
                        "FROM ponto_divergencia_regua WHERE causa = 'indeterminado'"
                    )
                )
            ).first()
            resumo.append(f"(d) linhas «indeterminado»: {n_ind} · sem as duas réguas terem rodado: {n_ind_cego}")
            if int(n_ind_cego):
                falhas.append(
                    f"(d) {n_ind_cego} divergência(s) classificada(s) como «indeterminado» sem batida crua "
                    "nem par de nenhuma das duas réguas — é medição que não aconteceu, não ignorância honesta"
                )

            # ───── (e) paralelo cego do dinheiro ─────
            hol_depois, esp_depois = await _foto_dinheiro(db)
            soma_rs = 0.0
            for k in set(hol_antes) | set(hol_depois):
                a, bb = hol_antes.get(k), hol_depois.get(k)
                if a is None or bb is None:
                    falhas.append(f"(e) holerite {k[:8]} só existe num dos lados do paralelo")
                    continue
                d = sum(abs(x - y) for x, y in zip(a, bb, strict=True))
                if d > 0.005:
                    soma_rs += d
                    falhas.append(f"(e) holerite {k[:8]} mudou: {a} → {bb}")
            esp_mexidos = sum(1 for k in set(esp_antes) | set(esp_depois) if esp_antes.get(k) != esp_depois.get(k))
            resumo.append(
                f"(e) paralelo cego: {len(hol_antes)} holerite(s) e {len(esp_antes)} espelho(s) fotografados "
                f"antes e depois da apuração · Σ|Δ| R$ {soma_rs:.2f} · espelhos reescritos: {esp_mexidos}"
            )
            if esp_mexidos:
                falhas.append(f"(e) {esp_mexidos} espelho(s) de time_sheets mudaram com a apuração")

            quem = (
                await db.execute(
                    text("SELECT quem_acerta, count(*) FROM ponto_divergencia_regua GROUP BY 1 ORDER BY 2 DESC")
                )
            ).fetchall()
            perto = (
                await db.execute(
                    text(
                        "SELECT count(*) FILTER (WHERE mais_perto='A'), count(*) FILTER (WHERE mais_perto='B') "
                        "FROM ponto_divergencia_regua"
                    )
                )
            ).first()
            resumo.append(
                "(§7) quem bate com a jornada planejada: "
                + " · ".join(f"{x[0]} {x[1]}" for x in quem)
                + f" · desempate fraco (só mais perto): régua A {perto[0]}, régua B {perto[1]}"
            )
        finally:
            await _limpar(db)

    for lin in resumo:
        print(lin)
    for f in falhas:
        print(f"FALHOU: {f}")
    print(f"TOTAL desvios: {len(falhas)}")
    if not falhas:
        print(
            "OK direção da batida: as duas réguas medidas lado a lado, causa por causa, "
            "idempotente — e a folha intacta em R$ 0,00"
        )
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
