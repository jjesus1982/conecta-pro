"""Oráculo — os três caminhos do ponto contam o MESMO plantão (DGX X4, 24/09/2026).

Por que existe: a casa tinha TRÊS implementações de pareamento de batidas. A frente V1 criou a
régua única em `horas_service` («um plantão é UM dia»: o dia de um turno noturno é a data de
INÍCIO em `shifts`, e toda batida entre início−tolerância e fim+tolerância é dele). A W1 levou
essa régua ao pareador canônico `parear_batidas`, de onde a FOLHA e o FECHAMENTO leem. O
terceiro — `time_record_service._pair_punches`, que alimenta a tela de ponto do DP e o resumo
mensal — ficou com a régua velha: datava cada par no dia CIVIL da entrada.

Medido no staging em 24/09/2026, ANTES da correção, sobre 155 pessoa×competência com batida em
07, 08 e 09/2026: Σ|Δ| de 57 + 41 + 64 = **162 dias** entre o que o espelho dizia e o que a
régua única diz. ADAILSON SERRA ALVES aparecia com 17 dias em 07/2026 para 15 plantões;
ANILSON JOSE SEIXAS NEVES com 21 para 16 em 08/2026. DEPOIS: 0 + 1 + 1 = **2**, e os 2 que
sobram não são de dia — são de PAR (item (f) explica e o oráculo os classifica).

O risco que justifica a frente: o espelho é o documento que o colaborador assina e que vai à
homologação. Se ele conta um plantão noturno como dois dias, o documento assinado diz uma coisa
e a folha diz outra.

A regra que este oráculo afirma (regra, não fotografia):
  (a) um plantão 12x36 noturno com intervalo é UM dia nos TRÊS caminhos — folha
      (`horas_reais_ponto`), fechamento (`PunchService.fechar_mes`) e espelho
      (`TimeRecordService._calculate_summary_from_punches`) — com as MESMAS horas. DUAS
      fixtures, e a segunda é a que importa: com intervalo CURTO (19:00→02:00 · 03:00→07:00)
      o `_pair_punches` já funde os dois pares num registro só e acerta sozinho; com intervalo
      longo e 14h brutas (19:00→02:00 · 03:30→09:00) a fusão não acontece — e era aí que o
      segmento pós-meia-noite virava um segundo dia.
  (b) todo registro que o espelho produz sobre dado REAL está datado no DIA DO PLANTÃO, e o
      oráculo reconta esse dia por conta própria (janelas de `shifts` montadas aqui), sem
      perguntar ao serviço medido.
  (c) espelho já ASSINADO/HOMOLOGADO/FECHADO não é reescrito: `get_summary` devolve o que está
      gravado em `time_sheets` (não recalcula) e `calcular_espelho(force=True)` sai sem tocar
      um campo. 19 espelhos protegidos em 24/09.
  (d) a FOLHA não muda um centavo: Σ|Δ| verba a verba = R$ 0,00 no paralelo cego (régua X4 ×
      régua anterior, no mesmo processo) sobre os holerites gravados de 07+08+09/2026. E a
      prova estrutural: a folha calcula normalmente com `_pair_punches` MINADO para explodir —
      ela não passa por aqui.
  (e) varredura estática: quem mais pareia batidas em `backend/modules`. Não são três nem
      quatro — são OITO, e a lista está em `PAREADORES_CONHECIDOS` com o papel de cada um.
      Um NONO é desvio e tem de ser declarado antes de entrar.
  (f) HORAS iguais ⟹ DIAS iguais. Quando os dois caminhos chegam às mesmas horas é porque
      formaram os mesmos pares; então só o DIA pode separá-los, e é o dia que esta frente
      unifica. Onde as HORAS diferem, a divergência é de PAR — batida tipada 'saida' abrindo
      turno: `_pair_punches` recusa, `parear_batidas` ignora o tipo — e fica REGISTRADA, não é
      falha: escolher entre as duas direções muda a hora da folha, e é decisão do dono (§7).

Estado medido no nascimento (staging, 24/09/2026, ANTES): (a) espelho 6 dias para 3 plantões
(folha e fechamento já davam 3) na fixture de intervalo longo; (b) 162 registros fora do dia
do plantão; (c) verde (a proteção
já existia, e é ela que a frente confirma); (d) R$ 0,00 — e é isso que libera a correção; (e) 8;
(f) 12 pessoa×mês com as MESMAS horas e dias diferentes. DEPOIS: (a) 3/3/3 nas duas fixtures (33h e 37,5h);
(b) 0; (c) 19 protegidos, 0 reescritos; (d) R$ 0,00 em 167 holerites; (e) 8, 0 não declarados;
(f) 0 com as mesmas horas · 2 com horas diferentes (ADEILSON DINIZ DEODATO 08 e 09/2026).

Como roda (container efêmero contra o sandbox, PYTHONPATH=/app):
  ENVS=$(docker inspect conecta-pro-backend-staging --format '{{range .Config.Env}}{{println .}}{{end}}' \
    | grep -E '^(DATABASE_URL|REDIS_URL)=' | sed 's/^/-e /' | tr '\\n' ' ')
  docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \\
    --tmpfs /app/logs:rw,mode=1777 --tmpfs /app/uploads:rw,uid=999,gid=999 \\
    -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \\
    -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
    conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_x4_pareador_unico.py
Sai 0 = verde; 1 = vermelho. Linha final `TOTAL desvios: N`.
"""

from __future__ import annotations

import asyncio
import pathlib
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta

MARCA = "FIXTURE DGX X4"
#: intervalo CURTO (1h): os dois segmentos se fundem num registro só — o `_pair_punches` já
#: acertava este caso sozinho, e é por isso que ele não basta como prova.
FIX_NOT = "44444444-d6c1-4f11-9e11-dc4000000001"
#: intervalo LONGO e plantão de 14h brutas: a fusão NÃO acontece (o teto é 13h) e o segmento
#: pós-meia-noite vira um registro à parte. É AQUI que a régua velha contava dois dias.
FIX_LONGO = "44444444-d6c1-4f11-9e11-dc4000000002"
FIX_ANO, FIX_MES = 2026, 9
FIX_DIAS = (date(2026, 9, 2), date(2026, 9, 4), date(2026, 9, 6))
FIX_HORAS = 33.0  # 3 plantões de 11h líquidas (19:00→02:00 + 03:00→07:00)
FIX_HORAS_LONGO = 37.5  # 3 plantões de 12,5h líquidas (19:00→02:00 + 03:30→09:00)

COMPETENCIAS = ((2026, 7), (2026, 8), (2026, 9))

#: Todo lugar de `backend/modules` que pareia batidas por conta própria, MEDIDO em 24/09/2026.
#: A varredura do item (e) recorta assim: o arquivo consulta `gp_clock_punches` E calcula a
#: duração de um par (saída − entrada). Não são três pareadores: são OITO. Os quatro últimos
#: estão declarados aqui e explicados no §7 do relatório da X4 — esta frente NÃO os corrigiu.
#: Um NONO arquivo que pareie batidas deixa este item vermelho: declare antes de entrar.
PAREADORES_CONHECIDOS = {
    # a régua única e quem já a usa
    "modules/people_management/ponto/services/horas_service.py",  # CANÔNICO (V1/W1)
    "modules/people_management/folha/services/beneficio_ponto.py",  # usa `dia_do_plantao` (V1)
    "modules/people_management/hr/services/time_record_service.py",  # a tela do DP — esta frente
    # os que continuam com régua própria (§7 do relatório — decisão do dono)
    "modules/people_management/hr/services/espelho_service.py",  # o espelho LEGAL (time_sheets/PDF)
    "modules/people_management/ponto/services/dashboard_service.py",  # banco de horas por escala
    "modules/people_management/hr/services/time_tracking_service.py",  # folha de ponto antiga do RH
    "modules/operacional/services/fechamento_turno_service.py",  # fecha TURNO (entrada/saída do shift)
    "modules/operacional/controllers/redesign_builders/departamento_pessoal.py",  # linha do dia na tela
}

#: Assinatura de "pareia batida por conta própria": consulta `gp_clock_punches` E mede a
#: duração de um par. O recorte largo (qualquer menção a entrada/saída) acusava 21 arquivos,
#: a maioria só montando texto de tela — régua que reprova o certo não serve de trava.
PADRAO_PAREIA = re.compile(r"gp_clock_punches", re.I)
PADRAO_PAR = re.compile(
    r"\((?:sai[a-z]*|s|b|ts|fim|out[a-z]*)\s*-\s*(?:ent[a-z]*|e|a|ini|in[a-z]*|aberta)[^)]*\)\.total_seconds\(\)"
    r"|_calc_minutes_between\(",
    re.I,
)


# ───────────────────────────── fixture ─────────────────────────────


async def _semear(db) -> None:
    from sqlalchemy import text

    await _limpar(db)
    ref = (await db.execute(text("SELECT scale_id::text, post_id::text FROM shifts LIMIT 1"))).first()
    if ref is None:
        raise RuntimeError("sandbox sem nenhum shift — não há scale_id/post_id para a fixture")
    for fid, sufixo, batidas in (
        (
            FIX_NOT,
            "NOTURNO-CURTO",
            ((0, "19:00", "entrada"), (1, "02:00", "saida"), (1, "03:00", "entrada"), (1, "07:00", "saida")),
        ),
        (
            FIX_LONGO,
            "NOTURNO-LONGO",
            ((0, "19:00", "entrada"), (1, "02:00", "saida"), (1, "03:30", "entrada"), (1, "09:00", "saida")),
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
                    {"pid": f"fixx4-{sufixo}-{d.isoformat()}-{n}", "e": fid, "t": tipo, "ts": ts, "m": MARCA},
                )
    await db.commit()


async def _limpar(db) -> None:
    from sqlalchemy import text

    await db.execute(
        text("DELETE FROM gp_monthly_closings WHERE CAST(employee_id AS TEXT) IN (:e1, :e2)"),
        {"e1": FIX_NOT, "e2": FIX_LONGO},
    )
    await db.execute(text("DELETE FROM gp_clock_punches WHERE posto_nome = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM shifts WHERE notes = :m"), {"m": MARCA})
    await db.execute(text("DELETE FROM employees WHERE nome LIKE :m"), {"m": f"{MARCA}%"})
    await db.commit()


# ─────────────────── a referência, recontada pelo oráculo ───────────────────


async def _janelas_proprias(db, eid: str, ini: date, fim: date) -> list[tuple[datetime, datetime, date]]:
    """As janelas de turno montadas AQUI — o oráculo não pede a régua ao código medido.

    Cópia deliberada de `janelas_de_turno` (tolerância de 1h nas duas pontas, noturno é o que
    termina antes de começar): num oráculo a referência tem de ser independente.
    """
    from sqlalchemy import text

    rows = (
        await db.execute(
            text(
                "SELECT shift_date, planned_start_time, planned_end_time FROM shifts "
                "WHERE CAST(employee_id AS TEXT) = :e AND shift_date BETWEEN :ini AND :fim "
                "AND lower(coalesce(status,'')) <> 'cancelled' AND NOT coalesce(is_off_day,false) "
                "ORDER BY shift_date, planned_start_time"
            ),
            {"e": eid, "ini": ini, "fim": fim},
        )
    ).fetchall()
    tol = timedelta(hours=1)
    out = []
    for dia, i0, i1 in rows:
        d0 = datetime.combine(dia, i0)
        d1 = datetime.combine(dia + timedelta(days=1) if i1 < i0 else dia, i1)
        out.append((d0 - tol, d1 + tol, dia))
    return out


def _dia_esperado(entrada: datetime, janelas: list, ultimo: tuple | None) -> date:
    """A régua, recontada: janela que começou por ÚLTIMO vence; senão continuidade (≤3h); senão
    o dia civil."""
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


# ───────────────────── (d) o paralelo cego do dinheiro ─────────────────────


def _verbas(lista) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for v in lista or []:
        out[f"{v.get('codigo')}|{v.get('descricao')}"] += float(v.get("valor") or 0)
    return out


def _folha_ab() -> tuple[float, int, list[str]]:
    """(Σ|Δ| verba a verba, holerites comparados, desvios) entre a régua X4 e a anterior.

    A régua X4 é `dia_do_plantao` chegando ao `_pair_punches`; neutralizá-la (dia civil da
    entrada) é exatamente desfazer a frente. Se algum centavo se mover, o número passou a ser
    usado em DINHEIRO e a correção tem de parar.
    """
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.people_management.folha.services import calculo_service
    from modules.people_management.ponto.services import horas_service

    nova = horas_service.dia_do_plantao

    def _volta(db, alvos):
        out = {}
        for eid, ano, mes in alvos:
            h = calculo_service.calcular_folha_colaborador(db, eid, mes, ano, historico=True)
            if h.get("error"):
                continue
            v = _verbas(h.get("proventos"))
            v.update({f"-{k}": x for k, x in _verbas(h.get("descontos")).items()})
            out[(eid, ano, mes)] = (dict(v), float(h.get("liquido") or 0))
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
        antes = _volta(db, alvos)
        horas_service.dia_do_plantao = nova
        depois = _volta(db, alvos)
    finally:
        horas_service.dia_do_plantao = nova
        db.close()

    soma, desvios = 0.0, []
    for k in set(antes) | set(depois):
        a, b = antes.get(k), depois.get(k)
        if a is None or b is None:
            desvios.append(f"(d) {k}: holerite só existe num dos lados do paralelo")
            continue
        for rub in set(a[0]) | set(b[0]):
            dl = abs(a[0].get(rub, 0.0) - b[0].get(rub, 0.0))
            if dl > 0.005:
                soma += dl
                desvios.append(f"(d) {k[1]}/{k[2]} {rub}: R$ {a[0].get(rub, 0):.2f} → R$ {b[0].get(rub, 0):.2f}")
        if abs(a[1] - b[1]) > 0.005:
            soma += abs(a[1] - b[1])
            desvios.append(f"(d) {k} LÍQUIDO: R$ {a[1]:.2f} → R$ {b[1]:.2f}")
    return soma, len(antes), desvios


def _folha_nao_passa_pelo_pareador() -> str:
    """Prova estrutural: minando `_pair_punches`, a folha ainda calcula.

    É o que autoriza mexer no pareador da tela sem medo do holerite — não é leitura de código,
    é o caminho de dinheiro rodando com o pareador da tela quebrado de propósito.
    """
    from sqlalchemy import text

    from core.database.session import SyncSessionLocal
    from modules.people_management.folha.services import calculo_service
    from modules.people_management.hr.services.time_record_service import TimeRecordService

    original = TimeRecordService._pair_punches

    def _mina(*_a, **_k):
        raise AssertionError("a folha chamou _pair_punches")

    db = SyncSessionLocal()
    try:
        TimeRecordService._pair_punches = _mina
        alvo = db.execute(
            text(
                "SELECT CAST(employee_id AS TEXT) FROM hr_payslips WHERE reference_year=2026 "
                "AND reference_month=9 AND status::text <> 'cancelled' LIMIT 1"
            )
        ).scalar()
        if not alvo:
            return "sem holerite de 09/2026 no sandbox — prova estrutural pulada"
        h = calculo_service.calcular_folha_colaborador(db, alvo, 9, 2026, historico=True)
        return f"folha de 09/2026 calculou com `_pair_punches` minado: líquido R$ {float(h.get('liquido') or 0):.2f}"
    finally:
        TimeRecordService._pair_punches = original
        db.close()


# ───────────────────── (e) a varredura estática ─────────────────────


def _quintos_pareadores() -> list[str]:
    """Arquivos de `backend/modules` que parecem parear batidas por conta própria."""
    raiz = pathlib.Path("/app/modules")
    achados = []
    for f in raiz.rglob("*.py"):
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not PADRAO_PAREIA.search(txt) or not PADRAO_PAR.search(txt):
            continue
        rel = str(f.relative_to("/app"))
        if rel not in PAREADORES_CONHECIDOS:
            achados.append(rel)
    return sorted(achados)


# ───────────────────────────── main ─────────────────────────────


async def main() -> int:  # noqa: C901, PLR0912, PLR0915
    from sqlalchemy import text

    from core.database import async_session_factory
    from modules.people_management.hr.services.time_record_service import TimeRecordService
    from modules.people_management.ponto.services import horas_service as hs
    from modules.people_management.ponto.services.punch_service import PunchService

    falhas: list[str] = []
    resumo: list[str] = []

    async with async_session_factory() as db:
        try:
            await _semear(db)
            svc = TimeRecordService(db)

            # ───── (a) o mesmo plantão nos três caminhos ─────
            for fid, rotulo, horas_alvo in (
                (FIX_NOT, "intervalo CURTO (1h, os pares se fundem)", FIX_HORAS),
                (FIX_LONGO, "intervalo longo + 14h brutas (os pares NÃO se fundem)", FIX_HORAS_LONGO),
            ):
                p = hs.params_batidas(fid, FIX_MES, FIX_ANO)
                rows = (
                    await db.execute(hs.SQL_BATIDAS, {k: v for k, v in p.items() if not k.startswith("_")})
                ).fetchall()
                turnos = (await db.execute(hs.SQL_TURNOS_JANELA, hs.params_turnos(p))).fetchall()
                folha = hs.parear_batidas(rows, p["_ini_mes"], p["_fim_mes"], hs.janelas_de_turno(turnos))
                fech = await PunchService(db).fechar_mes(fid, FIX_MES, FIX_ANO, "oraculo-x4")
                await db.commit()
                esp = await svc._calculate_summary_from_punches(fid, FIX_MES, FIX_ANO)

                d_folha = folha["dias_trabalhados"]
                d_fech = int(fech.get("total_dias_trabalhados") or fech.get("dias_trabalhados") or 0)
                d_esp = esp["total_worked_days"]
                h_folha = folha["horas_trabalhadas"]
                h_fech = float(fech.get("total_horas_trabalhadas") or fech.get("horas_trabalhadas") or 0)
                h_esp = round(esp["total_hours_worked_minutes"] / 60.0, 2)
                resumo.append(
                    f"(a) 3 plantões noturnos, {rotulo} — dias: folha {d_folha} · fechamento {d_fech} · "
                    f"espelho {d_esp} (régua anterior daria 6) · horas: {h_folha} / {h_fech} / {h_esp}"
                )
                if not (d_folha == d_fech == d_esp == len(FIX_DIAS)):
                    falhas.append(
                        f"(a) {rotulo}: os três caminhos não contam o mesmo plantão — folha {d_folha}, "
                        f"fechamento {d_fech}, espelho {d_esp}, esperado {len(FIX_DIAS)}"
                    )
                if not (
                    abs(h_folha - horas_alvo) < 0.02
                    and abs(h_esp - horas_alvo) < 0.02
                    and abs(h_fech - horas_alvo) < 0.02
                ):
                    falhas.append(
                        f"(a) {rotulo}: as horas divergem — folha {h_folha}, fechamento {h_fech}, espelho {h_esp}"
                    )

            # ───── (b) e (f) sobre dado REAL ─────
            emps = (
                await db.execute(
                    text(
                        "SELECT CAST(id AS TEXT), nome FROM employees "
                        "WHERE coalesce(is_homologacao,false)=false AND nome NOT LIKE :m ORDER BY nome"
                    ),
                    {"m": f"{MARCA}%"},
                )
            ).fetchall()
            fora_da_regua = 0
            exemplos_b: list[str] = []
            pop = 0
            dias_dif_pares_iguais: list[str] = []
            dias_dif_pares_dif = 0
            for ano, mes in COMPETENCIAS:
                for eid, nome in emps:
                    pp = hs.params_batidas(eid, mes, ano)
                    br = (
                        await db.execute(hs.SQL_BATIDAS, {k: v for k, v in pp.items() if not k.startswith("_")})
                    ).fetchall()
                    if not br:
                        continue
                    pop += 1
                    jan = await _janelas_proprias(db, eid, pp["ini"].date(), pp["fim"].date())
                    regs = await svc._calculate_summary_from_punches(eid, mes, ano)

                    # (b) cada registro do espelho no dia do PLANTÃO — sem circularidade: a
                    # entrada REAL vem de `gp_clock_punches` pelo punch_id que o registro
                    # carrega em `id`, e a janela é a que o oráculo montou por conta própria.
                    # Só se afirma onde HÁ turno lançado cobrindo a entrada: ali a régua é
                    # exata; sem turno ela cai na continuidade, que é heurística.
                    ids = [str(r["id"]) for r in regs["records"] if r.get("clock_in") and r.get("id")]
                    ts_por_id: dict[str, datetime] = {}
                    if ids:
                        ts_por_id = {
                            str(a): b
                            for a, b in (
                                await db.execute(
                                    text(
                                        "SELECT punch_id, punch_timestamp FROM gp_clock_punches "
                                        "WHERE punch_id = ANY(:ids)"
                                    ),
                                    {"ids": ids},
                                )
                            ).fetchall()
                        }
                    for r in regs["records"]:
                        ent = ts_por_id.get(str(r.get("id") or ""))
                        if ent is None:
                            continue
                        cobre = [d for j0, j1, d in jan if j0 <= ent <= j1]
                        if not cobre:
                            continue  # sem turno lançado a régua cai na continuidade (heurística)
                        esperado = cobre[-1]  # a janela que começou por ÚLTIMO vence
                        if str(esperado) != r["record_date"]:
                            fora_da_regua += 1
                            if len(exemplos_b) < 5:
                                exemplos_b.append(
                                    f"{nome[:26]} {mes:02d}/{ano} registro {r['record_date']} "
                                    f"(entrada {ent:%d/%m %H:%M}) devia ser {esperado}"
                                )

                    # (f) HORAS iguais ⟹ DIAS iguais. Se os dois caminhos chegam às mesmas
                    # horas é porque formaram os mesmos pares; então só o DIA pode separá-los,
                    # e é justamente o dia que esta frente unifica. Horas diferentes = pares
                    # diferentes (o tipo da batida decide a direção num lado e não no outro),
                    # outro assunto — §7 do relatório, não falha aqui.
                    turnos_r = (await db.execute(hs.SQL_TURNOS_JANELA, hs.params_turnos(pp))).fetchall()
                    ref = hs.parear_batidas(br, pp["_ini_mes"], pp["_fim_mes"], hs.janelas_de_turno(turnos_r))
                    if ref["dias_trabalhados"] == regs["total_worked_days"]:
                        continue
                    if abs(ref["horas_trabalhadas"] - regs["total_hours_worked_minutes"] / 60.0) < 0.02:
                        dias_dif_pares_iguais.append(
                            f"{nome[:26]} {mes:02d}/{ano}: régua {ref['dias_trabalhados']} × espelho "
                            f"{regs['total_worked_days']} com as MESMAS {ref['horas_trabalhadas']}h"
                        )
                    else:
                        dias_dif_pares_dif += 1

            resumo.append(
                f"(b) pessoa×competência com batida em 07+08+09/2026: {pop} · registros do espelho "
                f"com turno cobrindo a entrada e data FORA do dia do plantão: {fora_da_regua}"
            )
            resumo.append(
                f"(f) dias diferentes com as MESMAS horas: {len(dias_dif_pares_iguais)} · "
                f"com horas diferentes (é do tipo da batida, não do dia — §7): {dias_dif_pares_dif}"
            )
            for e in exemplos_b:
                resumo.append(f"    (b) {e}")
            if fora_da_regua:
                falhas.append(f"(b) {fora_da_regua} registro(s) do espelho fora do dia do plantão")
            for lin in dias_dif_pares_iguais:
                falhas.append(f"(f) {lin}")

            # ───── (c) espelho assinado / homologado / fechado não muda ─────
            prot = (
                await db.execute(
                    text(
                        "SELECT CAST(employee_id AS TEXT) e, reference_month m, reference_year a, "
                        " coalesce(work_days_worked,0) d, coalesce(hours_worked_minutes,0) h, status "
                        "FROM time_sheets WHERE is_deleted=false AND ("
                        " lower(coalesce(status,'')) IN ('fechado','aprovado','revisado','enviado_folha') "
                        " OR closed_at IS NOT NULL OR coalesce(approved_by_employee,false)=true)"
                    )
                )
            ).fetchall()
            mexidos = 0
            for r in prot:
                s = await svc.get_summary(r.e, r.m, r.a)
                if s["total_worked_days"] != r.d or s["total_hours_worked_minutes"] != r.h:
                    mexidos += 1
                    falhas.append(
                        f"(c) espelho protegido {r.m:02d}/{r.a} {r.e[:8]} ({r.status}): gravado "
                        f"{r.d}d/{r.h}min, lido {s['total_worked_days']}d/{s['total_hours_worked_minutes']}min"
                    )
            resumo.append(f"(c) espelhos protegidos (assinado/homologado/fechado): {len(prot)} · reescritos: {mexidos}")

            # ───── (d) a folha ─────
            soma, n_hol, desvios_d = _folha_ab()
            estrutural = _folha_nao_passa_pelo_pareador()
            resumo.append(
                f"(d) folha 07+08+09/2026 régua X4 × anterior: {n_hol} holerites gravados · "
                f"Σ|Δ| verba a verba R$ {soma:.2f}"
            )
            resumo.append(f"    (d) prova estrutural: {estrutural}")
            falhas.extend(desvios_d)

            # ───── (e) varredura estática ─────
            quintos = _quintos_pareadores()
            resumo.append(
                f"(e) pareadores de batida em backend/modules: {len(PAREADORES_CONHECIDOS)} declarados "
                f"(3 na régua única + 5 com régua própria, §7) · NÃO declarados: {len(quintos)}"
            )
            for q in quintos:
                falhas.append(f"(e) pareador de batida NÃO declarado: {q}")

        finally:
            await _limpar(db)

    for lin in resumo:
        print(lin)
    for f in falhas:
        print(f"FALHOU: {f}")
    print(f"TOTAL desvios: {len(falhas)}")
    if not falhas:
        print(
            "OK pareador único: o plantão é UM dia na folha, no fechamento e no espelho; assinado intacto; folha R$ 0,00"
        )
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
