"""Supervisão planejada — realizado × planejado (paridade DGX, U1, 24/09/2026).

No DGX (`ContratoSetores` → planejamentos com frequência, `Frontend/periodicidade`) cada posto tem
"quantas vezes por período o supervisor tem que ir lá", e o mapa mostra planejado × realizado. Aqui
o checklist da F8 e o check-in do gerente já existiam, mas sem denominador: ninguém sabia se 3
visitas no mês eram 3 de 3 ou 3 de 20.

Modelo: `op_supervisao_planos` (posto OU condomínio × supervisor × checklist × frequência × vigência)
e `op_supervisao_ocorrencias` (1 linha por plano × dia devido; UNIQUE). `gerar_ocorrencias(db, dia)`
é idempotente (INSERT … ON CONFLICT DO NOTHING) — a tela chama ao abrir e uma beat diária 00:30
pode chamar (registro do beat é do orquestrador; ver relatório §5). `marcar_realizada()` é o hook
que os escritores chamam (`supervisao_service.executar` e a ação `gerente-checkin`): um checklist
ou um check-in no posto naquele dia fecha a ocorrência do dia.

Frequência: diaria (todo dia da vigência) · semanal (dias_semana ISO 1=seg…7=dom) · quinzenal (dias_semana
nas semanas pares contadas a partir da vigência) · mensal (mesmo dia do mês de `vigencia_inicio`;
mês mais curto → último dia). Status: planejada → realizada | atrasada (hoje, depois de `hora_fim`)
| nao_realizada (dia passou).
"""

from __future__ import annotations

import calendar
import json
import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text

FREQUENCIAS = {"diaria": "Diária", "semanal": "Semanal", "quinzenal": "Quinzenal", "mensal": "Mensal"}
STATUS = {
    "planejada": "planejada",
    "realizada": "realizada",
    "atrasada": "atrasada",
    "nao_realizada": "não realizada",
}
DIAS_SEMANA = {1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sáb", 7: "dom"}

_DDL = [
    "CREATE TABLE IF NOT EXISTS op_supervisao_planos ("
    " id uuid PRIMARY KEY DEFAULT gen_random_uuid(), posto_id uuid, condominio_id uuid, supervisor_employee_id uuid NOT NULL,"
    " checklist_template_id uuid, frequencia varchar(12) NOT NULL, dias_semana jsonb NOT NULL DEFAULT '[]'::jsonb,"
    " hora_inicio time, hora_fim time, vigencia_inicio date NOT NULL, vigencia_fim date, ativo boolean NOT NULL DEFAULT true,"
    " observacao text, created_by uuid, created_at timestamp DEFAULT (now() AT TIME ZONE 'America/Manaus'))",
    "CREATE TABLE IF NOT EXISTS op_supervisao_ocorrencias ("
    " id uuid PRIMARY KEY DEFAULT gen_random_uuid(), plano_id uuid NOT NULL REFERENCES op_supervisao_planos(id) ON DELETE CASCADE,"
    " data date NOT NULL, status varchar(16) NOT NULL DEFAULT 'planejada', checklist_preenchido_id uuid, checkin_visita_id uuid,"
    " realizada_em timestamp, realizado_por uuid, UNIQUE (plano_id, data))",
    "CREATE INDEX IF NOT EXISTS ix_op_sup_ocorr_data ON op_supervisao_ocorrencias (data, status)",
]

SQL_PLANOS_VIGENTES = """
SELECT id::text, frequencia, dias_semana, vigencia_inicio, vigencia_fim
FROM op_supervisao_planos WHERE ativo AND vigencia_inicio <= :d AND (vigencia_fim IS NULL OR vigencia_fim >= :d)
  AND (CAST(:pl AS uuid) IS NULL OR id = CAST(:pl AS uuid))  -- CAST no 1º uso: asyncpg não infere tipo de `$n IS NULL`
"""


class SupervisaoPlanejadaErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa
    def __init__(self, status: int, msg: str) -> None:
        super().__init__(msg)
        self.status = status


def agora_manaus() -> datetime:
    return datetime.now(ZoneInfo("America/Manaus")).replace(tzinfo=None)


def hoje_manaus() -> date:
    return agora_manaus().date()


def horizonte(dia: date | None = None) -> date:
    """Último dia do mês SEGUINTE.

    Por que existe: `gerar_ocorrencias` só sabia fazer UM dia, e todo mundo em produção chamava
    com «hoje» (beat 00:30, a tela ao abrir, `criar_plano`). Resultado: o denominador do mapa era
    sempre ≈ os dias já vividos, então a % de realizado dava ~100% e a pergunta que justificou a
    frente — «3 visitas no mês são 3 de 3 ou 3 de 20?» — continuava sem resposta. Medido em
    28/09/2026: plano semanal seg/qua vigente 01→30/09 (9 dias devidos) aparecia como
    «Planejadas: 1». O único lugar que gerava mais de um dia era o oráculo, que trazia o laço
    consigo.
    Do futuro, nunca do passado: gerar dia anterior ao de hoje marcaria `nao_realizada` uma visita
    que pode ter acontecido sem ocorrência para fechar — inventaria a falta.
    """
    d = dia or hoje_manaus()
    y, m = d.year + (d.month == 12), d.month % 12 + 1
    return date(y, m, calendar.monthrange(y, m)[1])


async def _ensure(db) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await db.commit()


def deve_ocorrer(frequencia: str, dias_semana, vigencia_inicio: date, dia: date) -> bool:
    """A regra de frequência, pura (o oráculo reconta por SQL; isto é o que a tela e o job usam)."""
    dias = (
        {int(x) for x in (dias_semana or [])}
        if not isinstance(dias_semana, str)
        else {int(x) for x in json.loads(dias_semana)}
    )
    if frequencia == "diaria":
        return True
    if frequencia == "semanal":
        return dia.isoweekday() in dias
    if frequencia == "quinzenal":
        return dia.isoweekday() in dias and ((dia - vigencia_inicio).days // 7) % 2 == 0
    if frequencia == "mensal":
        ultimo = calendar.monthrange(dia.year, dia.month)[1]
        return dia.day == min(vigencia_inicio.day, ultimo)
    return False


async def gerar_ocorrencias(
    db, dia: date | None = None, *, ate: date | None = None, plano_id: str | None = None
) -> dict:
    """Idempotente: cria a ocorrência de cada plano devido em cada dia de `dia`…`ate` (ON CONFLICT
    DO NOTHING) e fecha o status do passado: dia < hoje sem realização → nao_realizada; hoje depois
    de hora_fim → atrasada.

    `ate` (default = `dia`, um dia só) é o que dá denominador ao mapa: quem chama com
    `ate=horizonte()` pré-cria os dias devidos até o fim do mês seguinte, e só então «3 de 20» é
    dizível. `plano_id` restringe ao plano novo (criar/reativar não precisa varrer a casa)."""
    await _ensure(db)
    dia = dia or hoje_manaus()
    # ponytail: teto de 400 dias no laço; se um dia precisar de horizonte maior, vira INSERT…SELECT
    # sobre generate_series em vez de laço em Python.
    ate = min(ate or dia, dia + timedelta(days=400))
    criadas = 0
    devidos: list[str] = []
    d = dia
    while d <= ate:
        planos = (await db.execute(text(SQL_PLANOS_VIGENTES), {"d": d, "pl": plano_id})).fetchall()
        for p in planos:
            if not deve_ocorrer(p[1], p[2], p[3], d):
                continue
            devidos.append(p[0])
            r = await db.execute(
                text(
                    "INSERT INTO op_supervisao_ocorrencias (plano_id, data) VALUES (CAST(:p AS uuid), :d) "
                    "ON CONFLICT (plano_id, data) DO NOTHING RETURNING id"
                ),
                {"p": p[0], "d": d},
            )
            criadas += 1 if r.fetchone() else 0
        d += timedelta(days=1)
    agora = agora_manaus()
    await db.execute(
        text(
            "UPDATE op_supervisao_ocorrencias SET status='nao_realizada' WHERE status IN ('planejada','atrasada') AND data < :h"
        ),
        {"h": agora.date()},
    )
    await db.execute(
        text(
            "UPDATE op_supervisao_ocorrencias o SET status='atrasada' FROM op_supervisao_planos p "
            "WHERE o.plano_id = p.id AND o.status='planejada' AND o.data = :h AND p.hora_fim IS NOT NULL AND p.hora_fim < :t"
        ),
        {"h": agora.date(), "t": agora.time().replace(microsecond=0)},
    )
    await db.commit()
    return {"dia": dia.isoformat(), "ate": ate.isoformat(), "devidas": len(devidos), "criadas": criadas}


async def marcar_realizada(
    db,
    *,
    post_id: str,
    dia: date | None = None,
    checklist_preenchido_id: str | None = None,
    checkin_visita_id: str | None = None,
    employee_id: str | None = None,
    user_id: str | None = None,
) -> int:
    """Um checklist executado ou um check-in no posto fecha a(s) ocorrência(s) do dia dos planos
    daquele posto (ou do condomínio do posto). Se o executor é conhecido e tem plano próprio ali,
    só o dele; senão qualquer plano do posto. Devolve quantas marcou. Nunca levanta (é hook)."""
    await gerar_ocorrencias(db, dia)  # garante a ocorrência do dia mesmo antes da beat
    dia = dia or hoje_manaus()
    if employee_id is None and user_id:
        employee_id = (
            await db.execute(text("SELECT employee_id::text FROM users WHERE id = CAST(:u AS uuid)"), {"u": user_id})
        ).scalar()
    base = (
        "UPDATE op_supervisao_ocorrencias o SET status='realizada', realizada_em=:agora, realizado_por=CAST(:u AS uuid), "
        " checklist_preenchido_id=coalesce(o.checklist_preenchido_id, CAST(:chk AS uuid)), "
        " checkin_visita_id=coalesce(o.checkin_visita_id, CAST(:vis AS uuid)) "
        "FROM op_supervisao_planos p WHERE o.plano_id = p.id AND o.data = :d AND o.status <> 'realizada' "
        " AND (p.posto_id = CAST(:post AS uuid) OR p.condominio_id IN "
        "      (SELECT c.id FROM condominios c JOIN posts ps ON ps.client_id = c.client_id WHERE ps.id = CAST(:post AS uuid)))"
    )
    params = {
        "agora": agora_manaus(),
        "u": user_id or None,
        "chk": checklist_preenchido_id,
        "vis": checkin_visita_id,
        "d": dia,
        "post": post_id,
        "emp": employee_id,
    }
    n = 0
    if employee_id:
        n = (await db.execute(text(base + " AND p.supervisor_employee_id = CAST(:emp AS uuid)"), params)).rowcount
    if not n:
        n = (await db.execute(text(base), params)).rowcount
    await db.commit()
    return int(n or 0)


async def criar_plano(
    db,
    *,
    supervisor_employee_id: str,
    frequencia: str,
    posto_id: str | None = None,
    condominio_id: str | None = None,
    checklist_template_id: str | None = None,
    dias_semana=None,
    hora_inicio: str | None = None,
    hora_fim: str | None = None,
    vigencia_inicio=None,
    vigencia_fim=None,
    observacao: str | None = None,
    user_id: str | None = None,
) -> dict:
    await _ensure(db)
    if not supervisor_employee_id:
        raise SupervisaoPlanejadaErro(400, "Escolha o supervisor.")
    if not posto_id and not condominio_id:
        raise SupervisaoPlanejadaErro(400, "Escolha o posto ou o condomínio.")
    if frequencia not in FREQUENCIAS:
        raise SupervisaoPlanejadaErro(400, f"Frequência: {', '.join(FREQUENCIAS)}.")
    dias = [int(x) for x in (dias_semana or []) if str(x).strip()]
    if frequencia in ("semanal", "quinzenal") and not dias:
        raise SupervisaoPlanejadaErro(400, "Semanal/quinzenal exige ao menos um dia da semana.")
    if any(d < 1 or d > 7 for d in dias):
        raise SupervisaoPlanejadaErro(400, "Dia da semana fora de 1 (seg) … 7 (dom).")
    try:
        ini = date.fromisoformat(str(vigencia_inicio)[:10]) if vigencia_inicio else hoje_manaus()
        fim = date.fromisoformat(str(vigencia_fim)[:10]) if vigencia_fim else None
    except ValueError:
        raise SupervisaoPlanejadaErro(400, "Vigência inválida (use AAAA-MM-DD).") from None
    if fim and fim < ini:
        raise SupervisaoPlanejadaErro(422, "Fim da vigência antes do início.")
    try:  # asyncpg exige `time`, não str
        hora_inicio = time.fromisoformat(str(hora_inicio)[:5]) if hora_inicio else None
        hora_fim = time.fromisoformat(str(hora_fim)[:5]) if hora_fim else None
    except ValueError:
        raise SupervisaoPlanejadaErro(400, "Hora inválida (use HH:MM).") from None
    if (hora_inicio and hora_fim) and hora_fim <= hora_inicio:
        raise SupervisaoPlanejadaErro(422, "Hora fim antes da hora início.")
    pid = (
        await db.execute(
            text(
                "INSERT INTO op_supervisao_planos (posto_id, condominio_id, supervisor_employee_id, checklist_template_id, frequencia, "
                " dias_semana, hora_inicio, hora_fim, vigencia_inicio, vigencia_fim, observacao, created_by) "
                "VALUES (CAST(:p AS uuid), CAST(:c AS uuid), CAST(:s AS uuid), CAST(:t AS uuid), :f, CAST(:ds AS jsonb), "
                " CAST(:hi AS time), CAST(:hf AS time), :vi, :vf, :obs, CAST(:u AS uuid)) RETURNING id::text"
            ),
            {
                "p": posto_id or None,
                "c": condominio_id or None,
                "s": supervisor_employee_id,
                "t": checklist_template_id or None,
                "f": frequencia,
                "ds": json.dumps(sorted(set(dias))),
                "hi": hora_inicio or None,
                "hf": hora_fim or None,
                "vi": ini,
                "vf": fim,
                "obs": (observacao or "").strip() or None,
                "u": user_id or None,
            },
        )
    ).scalar()
    await db.commit()
    # o plano novo já aparece em "hoje" E com o resto do mês como "a vencer" (denominador do mapa).
    # O plano JÁ está commitado: se a geração falhar, 500 aqui faria o usuário achar que não salvou e
    # criar o plano de novo. O beat das 00:30 repõe as ocorrências; o plano é o que importa.
    try:
        await gerar_ocorrencias(db, ate=horizonte(), plano_id=pid)
    except Exception as exc:  # noqa: BLE001 — visível no log, nunca calado
        await db.rollback()
        logging.getLogger(__name__).error("supervisão planejada: gerar após criar_plano %s falhou: %s", pid, exc)
    return {"id": pid, "vigencia_inicio": ini.isoformat()}


async def ativar_plano(db, *, plano_id: str, ativo: bool) -> dict:
    await _ensure(db)
    n = (
        await db.execute(
            text("UPDATE op_supervisao_planos SET ativo=:a WHERE id = CAST(:i AS uuid) RETURNING id"),
            {"a": ativo, "i": plano_id},
        )
    ).rowcount
    if not n:
        raise SupervisaoPlanejadaErro(404, "Plano não encontrado.")
    if not ativo:  # planejadas futuras do plano desativado saem do mapa; o passado fica
        await db.execute(
            text(
                "DELETE FROM op_supervisao_ocorrencias WHERE plano_id = CAST(:i AS uuid) AND status='planejada' AND data > :h"
            ),
            {"i": plano_id, "h": hoje_manaus()},
        )
    await db.commit()
    if ativo:  # reativar tem de repor as planejadas que a desativação apagou
        await gerar_ocorrencias(db, ate=horizonte(), plano_id=plano_id)
    return {"id": plano_id, "ativo": ativo}
