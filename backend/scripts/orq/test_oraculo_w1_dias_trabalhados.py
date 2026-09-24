"""Oráculo — o gêmeo do plantão noturno: `parear_batidas['dias_trabalhados']` (DGX W1, 24/09/2026).

Por que existe: a frente V1 consertou a régua «um plantão é UM dia» no motor de benefício
(`beneficio_ponto._horas_por_dia`) e deixou registrado, no §7.3 do relatório dela, que o
pareador canônico `horas_service.parear_batidas` tinha o MESMO defeito — contava o dia civil
da entrada de cada par. No 12x36 noturno com intervalo (19:00 → 02:00 · 03:00 → 07:00) o
segmento depois da meia-noite virava um SEGUNDO dia trabalhado. Medido no staging em 24/09,
antes da correção: Σ|Δ| de 84 dias em 08/2026 e 52 em 09/2026 na coorte de 12x36 noturna —
ADAILSON SERRA ALVES com 31 dias para 15 plantões, ANDREA com 31 para 15, ANILSON 29 para 16.

Esse número alimenta DOIS leitores, os dois informativos (medido, não suposto):
  - `calculo_service` linha 1052 → `hr_payslips.informative.dias_trabalhados` (campo de leitura
    do holerite; nenhuma verba usa `dias_reais`, que só existe nas linhas 419 e 1052);
  - `punch_service.fechar_mes_ponto` → `gp_monthly_closings.total_dias_trabalhados`, lido pela
    tela de fechamento, pelo `gestao_de_pessoas` e pelo `juridico/context_engine`.
Nenhum caminho de DINHEIRO passa por ele — as horas extras vêm de `horas_trabalhadas` e o
adicional noturno de `horas_noturnas`/`plantoes_noturnos`, e nenhum dos dois mudou.

A regra que este oráculo afirma (regra, não fotografia): o dia de um turno noturno é a data de
INÍCIO (`shifts.shift_date`); toda batida entre início−tolerância e fim+tolerância pertence a
ele. `dias_trabalhados` conta PLANTÕES, não datas civis de entrada. E a correção não pode
mover um centavo de holerite nem uma hora de quem trabalha de dia.

O que afirma:
  (a) fixture sintética ('FIXTURE DGX W1', apagada ao fim): 12x36 noturno com 3 plantões
      19:00–07:00 e batidas 19:00 / 02:00 / 03:00 / 07:00 → `dias_trabalhados` == 3 (e não 6),
      com `horas_trabalhadas` e `dias_com_par` intactos. Sem a escala lançada, idem, pela
      continuidade.
  (b) paralelo cego do DIURNO: para todo ativo que, pelas batidas, não cruza a meia-noite em
      08 ou 09/2026, `dias_trabalhados` é idêntico ao da régua anterior (dia civil da entrada),
      recomputada aqui por conta própria — Σ|Δ| = 0.
  (c) paralelo cego do DINHEIRO: a folha de 07, 08 e 09/2026 recalculada com a régua NOVA ×
      com a régua ANTIGA (neutralizando `dia_do_plantao` no mesmo processo), verba a verba,
      sobre os holerites GRAVADOS em `hr_payslips` — Σ|Δ| = R$ 0,00. Se der diferente, o número
      ERA usado em dinheiro e a correção tem de parar.
  (d) o caçador `checar_escala_paridade.py` acha a fixture de 12x36 com a escala nos ímpares e
      as batidas nos pares, e NÃO acha a fixture cuja escala bate com a vida.

Estado medido no nascimento (staging, 24/09/2026, ANTES da correção): (a) 6 ≠ 3; (b) verde
(o diurno nunca esteve errado); (c) R$ 0,00 — e é isso que libera a correção; (d) o caçador não
existia. DEPOIS: (a) 3, (b) verde, (c) R$ 0,00 em 167 holerites, 25 com o informativo mudado,
(d) acha 1 e não acha o outro.

Como roda (container efêmero contra o sandbox, PYTHONPATH=/app):
  ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\\n' ' ')
  docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \\
    --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \\
    -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \\
    -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
    conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_w1_dias_trabalhados.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

MARCA = "FIXTURE DGX W1"
FIX_NOT = "22222222-d6c1-4f11-9e11-dc1000000001"  # 12x36 noturno com intervalo
FIX_TORTO = "22222222-d6c1-4f11-9e11-dc1000000002"  # escala nos ímpares, batida nos pares
FIX_CERTO = "22222222-d6c1-4f11-9e11-dc1000000003"  # escala e batida no mesmo dia
FIX_ANO, FIX_MES = 2026, 9
FIX_DIAS = (date(2026, 9, 2), date(2026, 9, 4), date(2026, 9, 6))

#: Fim da janela noturna da CLT (22:00–05:00): batida antes disso é gente de plantão noturno.
FIM_NOITE_H = 5

#: Competências com holerite gravado que o item (c) percorre.
COMPETENCIAS = ((2026, 7), (2026, 8), (2026, 9))

SQL_ATIVOS = """
SELECT id::text, nome FROM employees
 WHERE lower(coalesce(status,'')) = 'ativo' AND coalesce(is_homologacao,false) = false ORDER BY nome
"""


def _cacador():
    """O caçador, importado por caminho — `scripts/qa` não é pacote."""
    spec = importlib.util.spec_from_file_location("_cac_w1", "/app/scripts/qa/checar_escala_paridade.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _batidas_e_turnos(db, eid: str, ano: int, mes: int):
    from modules.people_management.ponto.services import horas_service as hs

    p = hs.params_batidas(eid, mes, ano)
    rows = (await db.execute(hs.SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")})).fetchall()
    # `params_turnos` nasceu com a correção: na árvore-base o oráculo monta os params sozinho,
    # senão ele nem IMPORTA no vermelho — e oráculo que não roda não é vermelho, é ausente.
    pt = getattr(hs, "params_turnos", None)
    args = pt(p) if pt else {"e": p["e"], "ini": p["ini"].date(), "fim": p["fim"].date()}
    turnos = (await db.execute(hs.SQL_TURNOS_JANELA, args)).fetchall()
    return p, rows, turnos


def _parear(rows, ini, fim, janelas=None):
    """`parear_batidas` com as janelas quando ela as aceita — a base só aceita três argumentos."""
    from modules.people_management.ponto.services.horas_service import parear_batidas

    try:
        return parear_batidas(rows, ini, fim, janelas)
    except TypeError:
        return parear_batidas(rows, ini, fim)


def _dias_regua_anterior(rows, ini_mes, fim_mes) -> tuple[int, bool]:
    """A régua ANTERIOR, recomputada aqui: o par conta no dia civil da ENTRADA.

    Cópia deliberada do laço de `parear_batidas` da árvore-base (98961d795) — num oráculo a
    referência tem de ser independente do código medido, senão os dois erram junto. Devolve
    também se a pessoa CRUZA A MEIA-NOITE no mês, que é a população que a correção pode mexer.
    """
    from modules.people_management.ponto.services.horas_service import MAX_TURNO_H

    dias, i = set(), 0
    noturno = any(ini_mes <= ts < fim_mes and ts.hour < FIM_NOITE_H for _t, ts in rows)
    while i < len(rows) - 1:
        entrada, saida = rows[i][1], rows[i + 1][1]
        dur = (saida - entrada).total_seconds() / 60.0
        if not (0 < dur <= MAX_TURNO_H * 60):
            i += 1
            continue
        i += 2
        if ini_mes <= entrada < fim_mes:
            dias.add(entrada.date())
            noturno = noturno or entrada.date() != saida.date()
    return len(dias), noturno


# ───────────────────────────── fixtures ─────────────────────────────


async def _semear(db) -> None:
    from sqlalchemy import text

    await _limpar(db)
    ref = (await db.execute(text("SELECT scale_id::text, post_id::text FROM shifts LIMIT 1"))).first()
    if ref is None:
        raise RuntimeError("sandbox sem nenhum shift — não há scale_id/post_id para a fixture")

    async def _pessoa(fid: str, sufixo: str) -> None:
        await db.execute(
            text(
                "INSERT INTO employees (id, nome, status, escala_padrao, data_admissao, is_homologacao) "
                "VALUES (CAST(:id AS uuid), :nome, 'ativo', '12x36', CAST(:adm AS date), false)"
            ),
            {"id": fid, "nome": f"{MARCA} {sufixo}", "adm": date(2026, 6, 1)},
        )

    async def _turno(fid: str, d: date) -> None:
        await db.execute(
            text(
                "INSERT INTO shifts (id, scale_id, post_id, employee_id, status, shift_date, "
                "planned_start_time, planned_end_time, is_night_shift, notes) "
                "VALUES (gen_random_uuid(), CAST(:sc AS uuid), CAST(:po AS uuid), CAST(:e AS uuid), "
                "'scheduled', CAST(:d AS date), TIME '19:00', TIME '07:00', true, :m)"
            ),
            {"sc": ref[0], "po": ref[1], "e": fid, "d": d, "m": MARCA},
        )

    async def _plantao(fid: str, d: date, tag: str) -> None:
        """As 4 batidas de um 12x36 noturno com intervalo: 19:00 · 02:00 · 03:00 · 07:00."""
        for n, (delta_d, hhmm, tipo) in enumerate(
            ((0, "19:00", "entrada"), (1, "02:00", "saida"), (1, "03:00", "entrada"), (1, "07:00", "saida"))
        ):
            ts = datetime.combine(d + timedelta(days=delta_d), datetime.strptime(hhmm, "%H:%M").time())
            await db.execute(
                text(
                    "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, punch_timestamp, "
                    "status, posto_nome) VALUES (:pid, CAST(:e AS uuid), :t, :ts, 'approved', :m)"
                ),
                {"pid": f"fixw1-{tag}-{d.isoformat()}-{n}", "e": fid, "t": tipo, "ts": ts, "m": MARCA},
            )

    # (a) noturno com intervalo: 3 plantões, escala lançada no dia certo
    await _pessoa(FIX_NOT, "NOTURNO")
    for d in FIX_DIAS:
        await _turno(FIX_NOT, d)
        await _plantao(FIX_NOT, d, "not")

    # (d) contrafase: escala nos ÍMPARES de 09/2026, batidas nos PARES — a classe RILEM
    await _pessoa(FIX_TORTO, "CONTRAFASE")
    for dia in range(1, 16, 2):
        await _turno(FIX_TORTO, date(2026, 9, dia))
    for dia in range(2, 17, 2):
        await _plantao(FIX_TORTO, date(2026, 9, dia), "torto")

    # (d) o contraexemplo: escala e vida no MESMO dia — o caçador não pode acusar
    await _pessoa(FIX_CERTO, "ALINHADO")
    for dia in range(1, 16, 2):
        await _turno(FIX_CERTO, date(2026, 9, dia))
        await _plantao(FIX_CERTO, date(2026, 9, dia), "certo")
    await db.commit()


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.execute(text("DELETE FROM gp_clock_punches WHERE posto_nome = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM shifts WHERE notes = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM employees WHERE nome LIKE :m"), {"m": f"{MARCA}%"})
    await db.commit()


# ───────────────────────── (c) o paralelo do dinheiro ─────────────────────────


def _verbas(lista) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for v in lista or []:
        out[f"{v.get('codigo')}|{v.get('descricao')}"] += float(v.get("valor") or 0)
    return out


def _folha_ab() -> tuple[float, int, int, list[str]]:
    """(Σ|Δ| verba a verba, holerites comparados, quantos mudaram o informativo, desvios)."""
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.people_management.folha.services import calculo_service
    from modules.people_management.ponto.services import horas_service

    regua_nova = horas_service.dia_do_plantao

    def _uma_volta(db, alvos):
        out = {}
        for eid, ano, mes in alvos:
            h = calculo_service.calcular_folha_colaborador(db, eid, mes, ano, historico=True)
            if h.get("error"):
                continue
            v = _verbas(h.get("proventos"))
            v.update({f"-{k}": x for k, x in _verbas(h.get("descontos")).items()})
            out[(eid, ano, mes)] = (dict(v), float(h.get("liquido") or 0), h.get("dias_trabalhados"))
        return out

    db = SyncSessionLocal()
    try:
        alvos = [
            (eid, ano, mes)
            for ano, mes in COMPETENCIAS
            for (eid,) in db.execute(
                text(
                    "SELECT CAST(employee_id AS TEXT) FROM hr_payslips WHERE reference_year=:a "
                    "AND reference_month=:m AND status::text <> 'cancelled'"
                ),
                {"a": ano, "m": mes},
            ).fetchall()
        ]
        horas_service.dia_do_plantao = lambda entrada, _j, _u=None: entrada.date()
        antes = _uma_volta(db, alvos)
        horas_service.dia_do_plantao = regua_nova
        depois = _uma_volta(db, alvos)
    finally:
        horas_service.dia_do_plantao = regua_nova
        db.close()

    soma, desvios, mudou = 0.0, [], 0
    for k in set(antes) | set(depois):
        a, b = antes.get(k), depois.get(k)
        if a is None or b is None:
            desvios.append(f"(c) {k}: holerite só existe num dos lados do paralelo")
            continue
        for rub in set(a[0]) | set(b[0]):
            d = abs(a[0].get(rub, 0.0) - b[0].get(rub, 0.0))
            if d > 0.005:
                soma += d
                desvios.append(f"(c) {k[1]}/{k[2]} {rub}: R$ {a[0].get(rub, 0):.2f} → R$ {b[0].get(rub, 0):.2f}")
        if abs(a[1] - b[1]) > 0.005:
            soma += abs(a[1] - b[1])
            desvios.append(f"(c) {k} LÍQUIDO: R$ {a[1]:.2f} → R$ {b[1]:.2f}")
        mudou += a[2] != b[2]
    return soma, len(antes), mudou, desvios


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.people_management.ponto.services.horas_service import janelas_de_turno

    falhas: list[str] = []
    resumo: list[str] = []
    async with async_session_factory() as db:
        try:
            await _semear(db)

            # ───────── (a) 3 plantões noturnos com intervalo = 3 dias trabalhados ─────────
            p, rows, turnos = await _batidas_e_turnos(db, FIX_NOT, FIX_ANO, FIX_MES)
            r = _parear(rows, p["_ini_mes"], p["_fim_mes"], janelas_de_turno(turnos))
            anterior, _ = _dias_regua_anterior(rows, p["_ini_mes"], p["_fim_mes"])
            resumo.append(
                f"(a) fixture 3 plantões noturnos: dias_trabalhados {r['dias_trabalhados']} "
                f"(régua anterior daria {anterior}) · dias_com_par {r['dias_com_par']} · "
                f"horas {r['horas_trabalhadas']}"
            )
            if r["dias_trabalhados"] != len(FIX_DIAS):
                falhas.append(
                    f"(a) 3 plantões com intervalo deram {r['dias_trabalhados']} dias trabalhados — "
                    "o plantão virou 2 dias"
                )
            if r["dias_com_par"] != 2 * len(FIX_DIAS) or r["horas_trabalhadas"] != 33.0:
                falhas.append(f"(a) as horas mudaram junto com o dia: {r}")
            sem_escala = _parear(rows, p["_ini_mes"], p["_fim_mes"], [])
            if sem_escala["dias_trabalhados"] != len(FIX_DIAS):
                falhas.append(
                    f"(a) sem escala lançada o gêmeo voltou: {sem_escala['dias_trabalhados']} dias para 3 plantões"
                )

            # ───────── (d) o caçador acha a contrafase e não acha quem está certo ─────────
            cac = _cacador()
            sql = cac.SQL.format(min_turnos=cac.MIN_TURNOS, min_batidas=cac.MIN_BATIDAS, limiar=cac.LIMIAR)
            ini, fim = cac._janela(date.today())
            acusados = {
                lin[0]
                for lin in (
                    await db.execute(text(sql.replace(":ini", f"'{ini}'").replace(":fim", f"'{fim}'")))
                ).fetchall()
            }
            achou_torto = any(f"{MARCA} CONTRAFASE" in a for a in acusados)
            achou_certo = any(f"{MARCA} ALINHADO" in a for a in acusados)
            resumo.append(
                f"(d) caçador de paridade: {len(acusados)} acusado(s) na janela {ini}→{fim} · "
                f"contrafase achada: {achou_torto} · alinhado acusado: {achou_certo}"
            )
            if not achou_torto:
                falhas.append("(d) o caçador NÃO achou a escala em contrafase — a régua não pega a classe RILEM")
            if achou_certo:
                falhas.append("(d) o caçador acusou quem tem a escala CERTA — falso positivo")
        finally:
            await _limpar(db)

        # ───────── (b) paralelo cego do DIURNO ─────────
        ativos = (await db.execute(text(SQL_ATIVOS))).fetchall()
        comparados = pulados = 0
        soma = 0
        for ano, mes in ((2026, 8), (2026, 9)):
            for eid, nome in ativos:
                p, rows, turnos = await _batidas_e_turnos(db, eid, ano, mes)
                anterior, noturno = _dias_regua_anterior(rows, p["_ini_mes"], p["_fim_mes"])
                if noturno:  # é exatamente a população que a correção existe para mexer
                    pulados += 1
                    continue
                depois = _parear(rows, p["_ini_mes"], p["_fim_mes"], janelas_de_turno(turnos))["dias_trabalhados"]
                comparados += 1
                if depois != anterior:
                    soma += abs(depois - anterior)
                    falhas.append(f"(b) {nome} {mes:02d}/{ano}: {anterior} → {depois} dias em quem não vira o dia")
        resumo.append(
            f"(b) pessoa×mês que não cruzam a meia-noite: {comparados} · Σ|Δ| dias: {soma} "
            f"· pessoa×mês noturnas (fora da conta, é o alvo): {pulados}"
        )
        await db.rollback()

    # ───────── (c) paralelo cego do DINHEIRO ─────────
    delta, holerites, mudou, desvios = _folha_ab()
    falhas.extend(desvios)
    resumo.append(
        f"(c) folha 07+08+09/2026 régua antiga × nova: {holerites} holerites gravados · "
        f"Σ|Δ| verba a verba R$ {delta:.2f} · informativo dias_trabalhados mudou em {mudou}"
    )

    for lin in resumo:
        print(lin)
    for f in falhas[:40]:
        print("FALHOU:", f)
    if len(falhas) > 40:
        print(f"... e mais {len(falhas) - 40} desvio(s)")
    print(f"TOTAL desvios: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) — o gêmeo do plantão noturno não está curado")
    print("OK gêmeo curado: plantão noturno conta 1 dia, diurno intacto, folha sem um centavo de diferença")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(str(e))
        sys.exit(1)
