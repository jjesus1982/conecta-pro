"""Oráculo — o espelho LEGAL na régua única (DGX Y1, 24/09/2026).

Por que existe: o espelho de ponto é o documento que o colaborador ASSINA, que vira PDF, entra
no kit do GEDEON e vai à homologação. Até a Y1 ele tinha régua PRÓPRIA para dizer a que dia um
turno pertence — agrupava pares por gap < 180 min e datava o turno na 1ª entrada, sem olhar a
janela de `shifts`. A folha (`horas_reais_ponto`), o fechamento (`PunchService.fechar_mes`) e a
tela do DP (`TimeRecordService`) já falavam a régua única desde a V1/W1/X4
(`ponto/services/horas_service.dia_do_plantao`).

O risco que justifica a frente: o documento assinado podia dizer uma coisa e a folha outra. E
não é hipótese — medido no staging em 24/09: ADAILSON SERRA ALVES tinha em 09/2026 **3 dias de
falta injustificada** no espelho, sendo que um deles era um plantão que ele TRABALHOU: a
primeira batida do turno caiu depois da meia-noite, o espelho datou o turno no dia seguinte e o
dia da escala ficou "sem batida". Uma folha de ponto trabalhista acusando falta em dia
trabalhado é prova contra a empresa e contra o funcionário.

A regra que este oráculo afirma (regra, não fotografia):
  (a) um plantão 12x36 noturno com intervalo é UM dia nos QUATRO caminhos — folha, fechamento,
      espelho LEGAL e tela do DP — com as MESMAS horas. DUAS fixtures, e a segunda é a que
      prova: com intervalo CURTO (19:00→02:00 · 03:00→07:00) o gap é de 1h e a régua anterior
      do espelho já agrupava sozinha; com intervalo de 3h30 (19:00→23:00 · 02:30→07:00) o gap
      passa dos 180 min, a régua anterior partia o plantão em dois turnos e datava o segundo no
      dia seguinte. Escrever só a primeira daria um verde cego.
  (b) todo turno que o espelho produz sobre dado REAL está datado no DIA DO PLANTÃO — e o
      oráculo reconta esse dia por conta própria (janelas de `shifts` montadas aqui, cópia
      deliberada da régua), sem perguntar ao serviço medido.
  (c) espelho já ASSINADO / HOMOLOGADO / FECHADO não é reescrito. Os protegidos são relidos
      campo a campo ANTES e DEPOIS de um `calcular_espelho(force=True)` em cada um: 0 alterados.
  (d) a FOLHA não muda um centavo. Paralelo cego (régua Y1 × a anterior, no mesmo processo)
      sobre os holerites gravados de 07+08+09/2026, verba a verba e líquido a líquido —
      **com os espelhos abertos recalculados dos dois lados**, porque `calculo_service` lê
      `time_sheets.unjustified_absent_days` / `dsr_lost_days` e emite as verbas 1051/1053:
      este é caminho de DINHEIRO e o A/B tem de exercê-lo, não contorná-lo.
  (e) trava estrutural: `espelho_service` usa as primitivas de `horas_service` e não tem mais
      corte de gap próprio. Se alguém reintroduzir uma régua local no espelho, fica vermelho.

Estado medido no nascimento (staging = cópia de produção de 24/09/2026):
  ANTES  — (a) fixture de gap longo: espelho 6 dias para 3 plantões (folha, fechamento e tela
           já davam 3); (b) 5 turnos fora do dia do plantão; (c) 19 protegidos, 0 reescritos (a
           proteção já existia — é ela que a frente confirma); (d) R$ 0,00 (é isso que libera a
           correção); (e) vermelho (o espelho tinha `INTRA_SHIFT_GAP_MAX` próprio).
  DEPOIS — (a) 3/3/3/3 nas duas fixtures; (b) 0; (c) 19 · 0; (d) R$ 0,00 em 167 holerites;
           (e) verde.

Como roda (container efêmero contra o sandbox, PYTHONPATH=/app):
  ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \\
    | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\\n' ' ')
  docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \\
    --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \\
    -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \\
    -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
    conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_y1_espelho_regua.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

MARCA = "FIXTURE DGX Y1"

#: intervalo de 1h: o gap fica abaixo dos 180 min e a régua ANTERIOR do espelho já agrupava —
#: esta fixture fica verde nos dois lados e por isso não basta como prova.
FIX_CURTO = "55555555-d6c1-4f11-9e11-dc5000000001"
#: intervalo de 3h30: o gap passa dos 180 min. Era AQUI que o espelho partia o plantão em dois
#: turnos e datava o segundo no dia seguinte — dois dias trabalhados num plantão só, e o dia da
#: escala virando falta.
FIX_LONGO = "55555555-d6c1-4f11-9e11-dc5000000002"

FIX_ANO, FIX_MES = 2026, 9
FIX_DIAS = (date(2026, 9, 2), date(2026, 9, 4), date(2026, 9, 6))
FIX_HORAS_CURTO = 33.0  # 3 × (19:00→02:00 + 03:00→07:00) = 3 × 11h
FIX_HORAS_LONGO = 25.5  # 3 × (19:00→23:00 + 02:30→07:00) = 3 × 8,5h

COMPETENCIAS = ((2026, 7), (2026, 8), (2026, 9))

ESPELHO_PY = pathlib.Path("/app/modules/people_management/hr/services/espelho_service.py")


# ───────────────────────────── fixture ─────────────────────────────


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM gp_monthly_closings WHERE CAST(employee_id AS TEXT) IN (:e1, :e2)"),
        {"e1": FIX_CURTO, "e2": FIX_LONGO},
    )
    await db.execute(
        text("DELETE FROM time_sheets WHERE CAST(employee_id AS TEXT) IN (:e1, :e2)"),
        {"e1": FIX_CURTO, "e2": FIX_LONGO},
    )
    await db.execute(text("DELETE FROM gp_clock_punches WHERE posto_nome = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM shifts WHERE notes = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM employees WHERE nome LIKE :m"), {"m": f"{MARCA}%"})
    await db.commit()


async def _semear(db) -> None:
    from sqlalchemy import text

    await _limpar(db)
    ref = (await db.execute(text("SELECT scale_id::text, post_id::text FROM shifts LIMIT 1"))).first()
    if ref is None:
        raise RuntimeError("sandbox sem nenhum shift — não há scale_id/post_id para a fixture")
    for fid, sufixo, batidas in (
        (
            FIX_CURTO,
            "NOTURNO-GAP-CURTO",
            ((0, "19:00", "entrada"), (1, "02:00", "saida"), (1, "03:00", "entrada"), (1, "07:00", "saida")),
        ),
        (
            FIX_LONGO,
            "NOTURNO-GAP-LONGO",
            ((0, "19:00", "entrada"), (0, "23:00", "saida"), (1, "02:30", "entrada"), (1, "07:00", "saida")),
        ),
    ):
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
            for n, (dd, hhmm, tipo) in enumerate(batidas):
                ts = datetime.combine(d + timedelta(days=dd), datetime.strptime(hhmm, "%H:%M").time())
                await db.execute(
                    text(
                        "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, punch_timestamp, "
                        "status, device_type, posto_nome) "
                        "VALUES (:pid, CAST(:e AS uuid), :t, :ts, 'approved', 'mobile', :m)"
                    ),
                    {"pid": f"fixy1-{sufixo}-{d.isoformat()}-{n}", "e": fid, "t": tipo, "ts": ts, "m": MARCA},
                )
    await db.commit()


# ─────────────── a régua, recontada pelo oráculo (sem perguntar ao código medido) ───────────────


def _turnos_do_espelho(esp_svc, pares, janelas):
    """Chama `_agrupar_turnos` aceitando as DUAS assinaturas.

    Na árvore-base ele não recebe janelas — e o oráculo precisa rodar VERMELHO lá para valer
    alguma coisa. Um TypeError na medição não é um desvio medido, é um oráculo que não rodou.
    """
    try:
        return esp_svc._agrupar_turnos(pares, janelas)
    except TypeError:
        return esp_svc._agrupar_turnos(pares)


def _janelas_proprias(rows) -> list[tuple[datetime, datetime, date]]:
    """Cópia deliberada de `janelas_de_turno`: tolerância de 1h nas duas pontas; noturno é o
    turno que termina antes de começar, e a janela vai até o dia seguinte."""
    tol = timedelta(hours=1)
    out = []
    for dia, i0, i1 in rows:
        d0 = datetime.combine(dia, i0)
        d1 = datetime.combine(dia + timedelta(days=1) if i1 < i0 else dia, i1)
        out.append((d0 - tol, d1 + tol, dia))
    return out


def _dia_esperado(entrada: datetime, janelas: list, ultimo: tuple | None) -> date:
    """A régua recontada: janela que começou por ÚLTIMO vence; senão continuidade (≤3h, do
    outro lado da meia-noite); senão o dia civil."""
    achado = None
    for j0, j1, dia in janelas:
        if j0 <= entrada <= j1:
            achado = dia
    if achado is not None:
        return achado
    if ultimo is not None:
        saida_ant, dia_ant = ultimo
        gap = (entrada - saida_ant).total_seconds()
        if dia_ant != entrada.date() and 0 <= gap <= 3 * 3600:
            return dia_ant
    return entrada.date()


# ───────────── (d) o paralelo cego do dinheiro ─────────────


def _verbas(lista) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for v in lista or []:
        out[f"{v.get('codigo')}|{v.get('descricao')}"] += float(v.get("valor") or 0)
    return out


def _regua_anterior(pares: list[dict], janelas: list | None = None) -> list[dict]:
    """O `_agrupar_turnos` que existia ANTES da Y1: gap < 180 min agrupa; o turno é datado na
    data civil da 1ª entrada. Neutralizar a Y1 é exatamente isto — desfazer a frente."""
    turnos: list[dict] = []
    atual: list[dict] = []

    def _fecha(grp):
        brk = sum((grp[i]["entrada"] - grp[i - 1]["saida"]).total_seconds() / 60.0 for i in range(1, len(grp)))
        return {
            "date": grp[0]["entrada"].date(),
            "entrada": grp[0]["entrada"],
            "saida": grp[-1]["saida"],
            "pares": grp,
            "worked_min": sum(p["dur_min"] for p in grp),
            "break_min": brk,
        }

    for p in pares:
        if not atual:
            atual = [p]
            continue
        if 0 <= (p["entrada"] - atual[-1]["saida"]).total_seconds() / 60.0 < 180:
            atual.append(p)
        else:
            turnos.append(_fecha(atual))
            atual = [p]
    if atual:
        turnos.append(_fecha(atual))
    return turnos


def _folha_ab() -> tuple[float, int, list[str]]:
    """(Σ|Δ| verba a verba, holerites comparados, desvios) entre a régua Y1 e a anterior.

    Os espelhos ABERTOS são RECALCULADOS dos dois lados antes de cada volta da folha: é assim
    que o A/B exercita de verdade as verbas 1051/1053, que saem de `time_sheets`. Tudo em
    transação com ROLLBACK — nada é gravado. Se um centavo se mover, a frente tem de parar.
    """
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.people_management.folha.services import calculo_service
    from modules.people_management.hr.services import espelho_service as esp_svc  # noqa: N812

    regua_nova = esp_svc._agrupar_turnos
    db = SyncSessionLocal()
    try:
        alvos = [
            (eid, mes, ano)
            for ano, mes in COMPETENCIAS
            for (eid,) in db.execute(
                text(
                    "SELECT CAST(employee_id AS TEXT) FROM hr_payslips WHERE reference_year=:a "
                    "AND reference_month=:m AND status::text <> 'cancelled'"
                ),
                {"a": ano, "m": mes},
            ).fetchall()
        ]
        protegidos = {
            (r[0], int(r[1]), int(r[2]))
            for r in db.execute(
                text(
                    "SELECT CAST(employee_id AS TEXT), reference_month, reference_year, status, "
                    "closed_at IS NOT NULL, COALESCE(approved_by_employee,false) "
                    "FROM time_sheets WHERE is_deleted=false"
                )
            ).fetchall()
            if (r[3] or "") in esp_svc.STATUS_FECHADO_SET or r[4] or r[5]
        }

        def _uma_volta(regua):
            esp_svc._agrupar_turnos = regua
            out = {}
            try:
                for ano, mes in COMPETENCIAS:
                    for eid in esp_svc._employees_com_batida(db, mes, ano):
                        if (eid, mes, ano) in protegidos or eid in (FIX_CURTO, FIX_LONGO):
                            continue
                        try:
                            esp_svc.calcular_espelho(db, eid, mes, ano)
                        except Exception:  # noqa: BLE001, S110
                            pass  # espelho que não calcula hoje também não calcula do outro lado
                db.flush()
                for eid, mes, ano in alvos:
                    h = calculo_service.calcular_folha_colaborador(db, eid, mes, ano, historico=True)
                    if h.get("error"):
                        continue
                    v = _verbas(h.get("proventos"))
                    v.update({f"-{k}": x for k, x in _verbas(h.get("descontos")).items()})
                    out[(eid, mes, ano)] = (dict(v), float(h.get("liquido") or 0))
            finally:
                esp_svc._agrupar_turnos = regua_nova
                db.rollback()
            return out

        antes = _uma_volta(_regua_anterior)
        depois = _uma_volta(regua_nova)
    finally:
        esp_svc._agrupar_turnos = regua_nova
        db.close()

    soma, desvios = 0.0, []
    for k in set(antes) | set(depois):
        a, b = antes.get(k), depois.get(k)
        if a is None or b is None:
            desvios.append(f"(d) {k}: holerite só existe num dos lados do paralelo")
            continue
        for rub in set(a[0]) | set(b[0]):
            d = abs(a[0].get(rub, 0.0) - b[0].get(rub, 0.0))
            if d > 0.005:
                soma += d
                desvios.append(f"(d) {k[1]:02d}/{k[2]} {rub}: R$ {a[0].get(rub, 0):.2f} → R$ {b[0].get(rub, 0):.2f}")
        if abs(a[1] - b[1]) > 0.005:
            soma += abs(a[1] - b[1])
            desvios.append(f"(d) {k} LÍQUIDO: R$ {a[1]:.2f} → R$ {b[1]:.2f}")
    return soma, len(antes), desvios


# ───────────── (c) espelho protegido é imutável ─────────────

COLS_ESPELHO = (
    "status, hours_worked_minutes, hours_expected_minutes, hours_balance_minutes, "
    "overtime_50_minutes, overtime_100_minutes, overtime_total_minutes, night_hours_minutes, "
    "late_minutes, late_count, early_departure_minutes, break_actual_minutes, work_days_worked, "
    "absent_days, unjustified_absent_days, dsr_entitled, dsr_lost_days, total_entries, "
    "anomaly_count, anomaly_resolved_count, has_pending_issues, "
    "CAST(pending_issues AS TEXT), CAST(daily_summary AS TEXT), CAST(extra_metadata AS TEXT), "
    "CAST(last_calculated_at AS TEXT), CAST(approved_by_employee AS TEXT), CAST(closed_at AS TEXT)"
)


def _protegidos_imutaveis() -> tuple[int, int, list[str]]:
    """Relê TODOS os espelhos protegidos, roda `calcular_espelho(force=True)` em cada um e
    relê de novo. (protegidos, reescritos, desvios)."""
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.people_management.hr.services.espelho_service import (
        STATUS_FECHADO_SET,
        calcular_espelho,
    )

    db = SyncSessionLocal()
    desvios: list[str] = []
    try:
        alvos = [
            (r[0], int(r[1]), int(r[2]))
            for r in db.execute(
                text(
                    "SELECT CAST(employee_id AS TEXT), reference_month, reference_year, status, "
                    "closed_at IS NOT NULL, COALESCE(approved_by_employee,false) "
                    "FROM time_sheets WHERE is_deleted=false"
                )
            ).fetchall()
            if (r[3] or "") in STATUS_FECHADO_SET or r[4] or r[5]
        ]

        def _foto():
            return {
                (r[0], int(r[1]), int(r[2])): tuple(r[3:])
                for r in db.execute(
                    text(
                        f"SELECT CAST(employee_id AS TEXT), reference_month, reference_year, {COLS_ESPELHO} "  # noqa: S608
                        "FROM time_sheets WHERE is_deleted=false"
                    )
                ).fetchall()
            }

        antes = _foto()
        for eid, mes, ano in alvos:
            try:
                calcular_espelho(db, eid, mes, ano, force=True)
            except Exception as exc:  # noqa: BLE001
                desvios.append(f"(c) {eid} {mes:02d}/{ano}: calcular_espelho(force=True) explodiu: {exc}")
        db.flush()
        depois = _foto()
        reescritos = 0
        for k in alvos:
            if antes.get(k) != depois.get(k):
                reescritos += 1
                desvios.append(f"(c) espelho PROTEGIDO reescrito: {k}")
        return len(alvos), reescritos, desvios
    finally:
        db.rollback()
        db.close()


# ───────────────────────────── main ─────────────────────────────


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory
    from core.database.session import SyncSessionLocal
    from modules.people_management.hr.services import espelho_service as esp_svc  # noqa: N812
    from modules.people_management.hr.services.time_record_service import TimeRecordService
    from modules.people_management.ponto.services import horas_service as hs
    from modules.people_management.ponto.services.punch_service import PunchService

    falhas: list[str] = []
    resumo: list[str] = []

    async with async_session_factory() as db:
        try:
            await _semear(db)
            svc = TimeRecordService(db)
            sdb = SyncSessionLocal()

            # ───── (a) o mesmo plantão nos QUATRO caminhos ─────
            for fid, rotulo, horas_alvo in (
                (FIX_CURTO, "intervalo de 1h (gap < 180 min — a régua anterior já agrupava)", FIX_HORAS_CURTO),
                (FIX_LONGO, "intervalo de 3h30 (gap > 180 min — a régua anterior partia o plantão)", FIX_HORAS_LONGO),
            ):
                p = hs.params_batidas(fid, FIX_MES, FIX_ANO)
                rows = (
                    await db.execute(hs.SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")})
                ).fetchall()
                turnos = (await db.execute(hs.SQL_TURNOS_JANELA, hs.params_turnos(p))).fetchall()
                folha = hs.parear_batidas(rows, p["_ini_mes"], p["_fim_mes"], hs.janelas_de_turno(turnos))
                fech = await PunchService(db).fechar_mes(fid, FIX_MES, FIX_ANO, "oraculo-y1")
                await db.commit()
                tela = await svc._calculate_summary_from_punches(fid, FIX_MES, FIX_ANO)

                esp = esp_svc.calcular_espelho(sdb, fid, FIX_MES, FIX_ANO)
                # a régua anterior, no mesmo dado, para a linha de resumo dizer o que mudou
                _nova = esp_svc._agrupar_turnos
                esp_svc._agrupar_turnos = _regua_anterior
                try:
                    sdb.rollback()
                    esp_antes = esp_svc.calcular_espelho(sdb, fid, FIX_MES, FIX_ANO)
                finally:
                    esp_svc._agrupar_turnos = _nova
                    sdb.rollback()

                d_folha = folha["dias_trabalhados"]
                d_fech = int(fech.get("total_dias_trabalhados") or fech.get("dias_trabalhados") or 0)
                d_esp = int(esp["work_days_worked"])
                d_tela = tela["total_worked_days"]
                h_folha = folha["horas_trabalhadas"]
                h_fech = float(fech.get("total_horas_trabalhadas") or fech.get("horas_trabalhadas") or 0)
                h_esp = round(esp["hours_worked_minutes"] / 60.0, 2)
                h_tela = round(tela["total_hours_worked_minutes"] / 60.0, 2)
                resumo.append(
                    f"(a) 3 plantões noturnos, {rotulo} — dias: folha {d_folha} · fechamento {d_fech} · "
                    f"espelho {d_esp} (régua anterior daria {esp_antes['work_days_worked']}) · tela do DP "
                    f"{d_tela} · horas: {h_folha} / {h_fech} / {h_esp} / {h_tela}"
                )
                if not (d_folha == d_fech == d_esp == d_tela == len(FIX_DIAS)):
                    falhas.append(
                        f"(a) {rotulo}: os quatro caminhos não contam o mesmo plantão — folha {d_folha}, "
                        f"fechamento {d_fech}, espelho {d_esp}, tela {d_tela}, esperado {len(FIX_DIAS)}"
                    )
                if not all(abs(h - horas_alvo) < 0.02 for h in (h_folha, h_fech, h_esp, h_tela)):
                    falhas.append(
                        f"(a) {rotulo}: as horas divergem — folha {h_folha}, fechamento {h_fech}, "
                        f"espelho {h_esp}, tela {h_tela} (esperado {horas_alvo})"
                    )

            # ───── (b) sobre dado REAL: todo turno do espelho no dia do plantão ─────
            emps = (
                await db.execute(
                    text(
                        "SELECT CAST(id AS TEXT), nome FROM employees "
                        "WHERE coalesce(is_homologacao,false)=false AND nome NOT LIKE :m ORDER BY nome"
                    ),
                    {"m": f"{MARCA}%"},
                )
            ).fetchall()
            pop = 0
            fora = 0
            exemplos: list[str] = []
            for ano, mes in COMPETENCIAS:
                ini, fim = esp_svc._mes_bounds(mes, ano)
                margem = timedelta(hours=esp_svc.SPILL_MARGIN_H)
                for eid, nome in emps:
                    batidas = esp_svc._carregar_batidas(sdb, eid, mes, ano)
                    if not batidas:
                        continue
                    pop += 1
                    jrows = (
                        await db.execute(hs.SQL_TURNOS_JANELA, {"e": eid, "ini": ini - margem, "fim": fim + margem})
                    ).fetchall()
                    jan = _janelas_proprias(jrows)
                    pares, _ = esp_svc._parear(batidas)
                    turnos_esp = [
                        t
                        for t in _turnos_do_espelho(esp_svc, pares, hs.janelas_de_turno(jrows))
                        if ini <= t["date"] < fim
                    ]
                    # a referência: reconta o dia de cada par com a régua do ORÁCULO
                    ultimo = None
                    esperado_por_entrada: dict[datetime, date] = {}
                    for pr in pares:
                        d = _dia_esperado(pr["entrada"], jan, ultimo)
                        ultimo = (pr["saida"], d)
                        esperado_por_entrada[pr["entrada"]] = d
                    for t in turnos_esp:
                        alvo = esperado_por_entrada.get(t["entrada"])
                        if alvo is not None and alvo != t["date"]:
                            fora += 1
                            if len(exemplos) < 8:
                                exemplos.append(
                                    f"    (b) {nome} {mes:02d}/{ano}: turno datado {t['date']} "
                                    f"(entrada {t['entrada']:%d/%m %H:%M}) devia ser {alvo}"
                                )
            resumo.append(
                f"(b) pessoa×competência com batida em 07+08+09/2026: {pop} · turnos do espelho "
                f"fora do dia do plantão: {fora}"
            )
            resumo.extend(exemplos)
            if fora:
                falhas.append(f"(b) {fora} turno(s) do espelho fora do dia do plantão")

            sdb.close()

            # ───── (c) espelho protegido é imutável ─────
            n_prot, reescritos, dv_c = _protegidos_imutaveis()
            resumo.append(f"(c) espelhos protegidos (assinado/homologado/fechado): {n_prot} · reescritos: {reescritos}")
            falhas.extend(dv_c)

            # ───── (d) a folha não muda um centavo ─────
            soma, n_hol, dv_d = _folha_ab()
            resumo.append(
                f"(d) folha 07+08+09/2026 régua Y1 × anterior (com os espelhos abertos recalculados "
                f"dos dois lados): {n_hol} holerites gravados · Σ|Δ| verba a verba R$ {soma:.2f}"
            )
            falhas.extend(dv_d)

            # ───── (e) trava estrutural: a régua do espelho é a única da casa ─────
            fonte = ESPELHO_PY.read_text(encoding="utf-8") if ESPELHO_PY.exists() else ""
            usa_primitivas = "dia_do_plantao" in fonte and "janelas_de_turno" in fonte
            tem_regua_propria = "INTRA_SHIFT_GAP_MAX" in fonte.replace("antigo `INTRA_SHIFT_GAP_MAX`", "")
            resumo.append(
                f"(e) espelho_service usa as primitivas da régua única: {usa_primitivas} · "
                f"tem corte de gap próprio: {tem_regua_propria}"
            )
            if not usa_primitivas:
                falhas.append("(e) espelho_service deixou de usar dia_do_plantao/janelas_de_turno da régua única")
            if tem_regua_propria:
                falhas.append("(e) espelho_service voltou a ter um corte de gap próprio (INTRA_SHIFT_GAP_MAX)")
        finally:
            await _limpar(db)

    for linha in resumo:
        print(linha)
    for f in falhas:
        print(f"FALHOU: {f}")
    print(f"TOTAL desvios: {len(falhas)}")
    if not falhas:
        print(
            "OK espelho na régua única: o plantão é UM dia na folha, no fechamento, no espelho "
            "LEGAL e na tela do DP; assinado intacto; folha R$ 0,00"
        )
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
