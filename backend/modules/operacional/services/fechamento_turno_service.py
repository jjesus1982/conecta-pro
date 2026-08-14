"""Fecha o turno pelo ponto: scheduled → completed / partial.

Por que existe: em 14/08/2026 o ciclo de vida do turno não avançava. 3667 turnos e
o status era só `scheduled` (2015) ou `cancelled` (1652) — nenhum `completed`, e
`actual_start_time` NULL nos 3667. Como falta nasce de turno encerrado, e substituição
nasce de falta, TRÊS funções do módulo ficavam em zero (faltas, substituições, banco de
horas) por mais tela que se ligasse. Este serviço fecha o elo.

NÃO MEXE EM `status`. ESSA FOI A LIÇÃO CARA DE 14/08/2026.
    A primeira versão marcava scheduled → completed/partial. Parecia certo e quebrou
    dinheiro: `calculo_service.plantoes_noturnos` conta plantão com `s.status =
    'scheduled'` LITERAL, e as 321 mudanças de agosto tiraram 68 plantões noturnos de
    12 colaboradores da folha — ~476h de adicional noturno que sumiriam. O literal
    'scheduled' aparece em 12+ pontos (folha, grade, KPIs, triagem, cobertura), todos
    escritos quando shifts só tinha scheduled/cancelled. Introduzir um valor novo numa
    coluna compartilhada mudou o significado de todos eles em silêncio.
    A convenção certa já existia no próprio repo (grade_controller.py:442):
    turno que ACONTECEU é `scheduled` com `actual_start_time` preenchido.
    Então é isso que este serviço faz: preenche actual_start_time/actual_end_time/
    actual_hours e NÃO toca no status. Quem quiser saber se fechou, pergunta ao
    actual_start_time — que é o que `ausentes-hoje` e o grade já perguntavam.

O QUE ELE NÃO FAZ, DE PROPÓSITO — não marca falta.
    Falta marcada por máquina vira desconto indevido quando o relógio falhou e a pessoa
    trabalhou. Medido antes de escrever: a regra ingênua produzia 547 faltas em 1488
    turnos (37%), e ABRIL sozinho dava 180 faltas em 180 turnos — porque o relógio não
    tem uma única batida em abril. Ausência de dado virando ausência de pessoa.
    Turno sem batida fica `scheduled` e sai na lista de CANDIDATAS, para humano decidir.

FUSO — a batida está em hora de MANAUS, não em UTC.
    Cravado por evidência, não por suposição: na mesma linha, `created_at` (UTC) e
    `punch_timestamp` diferem exatamente 4h (12:03:31 vs 08:03:31). Converter UTC→Manaus
    subtraía 4h a mais e desalinhava tudo: com a conversão errada dava completed=704 /
    partial=237; com a hora crua, completed=876 / partial=74.

JANELA — o turno da noite cruza a meia-noite.
    1207 dos 3667 turnos têm `planned_end_time < planned_start_time` (33%). A janela soma
    1 dia ao fim nesses casos. Sem isso, todo 12x36 noturno perderia a saída.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Folga em volta do turno para aceitar quem bate adiantado/atrasado. 3h é generoso de
# propósito: errar para "completed" só perde uma falta (que humano acha na lista);
# errar para "sem batida" acusa alguém que trabalhou.
TOLERANCIA_HORAS = 3

# PISO: batida anterior a 01/08/2026 NÃO vale — decisão do Jordan em 14/08/2026.
# Até 11/08 a fonte da verdade do ponto era o Sólides/Tangerino e o Conecta era espelho
# com buracos conhecidos; a virada para 100% Conecta está sendo parametrizada agora.
# Fechar turno de julho com esse dado seria carimbar jornada sobre base que o próprio
# dono do processo declarou não confiável (eram 629 dos 954 turnos que fechei na
# primeira rodada). Turno anterior ao piso fica intocado — nem completed, nem candidato.
PISO_BATIDA = date(2026, 8, 1)

# Só mexe em turno que já ACABOU. Turno de hoje ainda pode receber batida.
_SQL_CANDIDATOS = """
WITH s AS (
    SELECT id, employee_id, shift_date, planned_start_time, planned_end_time,
           planned_hours, is_off_day,
           (shift_date + planned_start_time) AS ini,
           (shift_date + planned_end_time
            + CASE WHEN planned_end_time < planned_start_time
                   THEN interval '1 day' ELSE interval '0' END) AS fim
    FROM shifts
    WHERE status::text = 'scheduled'
      AND coalesce(is_active, true)
      AND employee_id IS NOT NULL
      AND shift_date <= :ate
      AND shift_date >= :piso
      AND actual_start_time IS NULL          -- idempotência: já fechado não volta
),
b AS (
    -- punch_timestamp JÁ está em hora de Manaus (ver docstring). Nada de converter.
    SELECT employee_id, punch_timestamp AS ts, punch_type
    FROM gp_clock_punches
    WHERE punch_timestamp >= :piso
)
SELECT s.id, s.employee_id, s.shift_date, s.is_off_day, s.planned_hours,
       min(b.ts) FILTER (WHERE b.punch_type = 'entrada') AS entrada,
       max(b.ts) FILTER (WHERE b.punch_type = 'saida')   AS saida,
       count(b.*)                                        AS n_batidas,
       -- Intervalo a descontar do VÃO real, derivado do próprio turno:
       -- é a diferença entre o vão planejado e as horas planejadas. Não dá para
       -- subtrair planned_break_minutes direto — em 12x36 o intervalo está DENTRO
       -- das 12h (vão 12h, planned_hours 12.0, break 60), enquanto num 07:00–16:00
       -- ele é deduzido (vão 9h, planned_hours 8.0). Descontar sempre inventaria
       -- hora a menos num caso e a mais no outro.
       greatest(0, EXTRACT(EPOCH FROM (s.fim - s.ini)) / 3600.0
                   - coalesce(s.planned_hours, EXTRACT(EPOCH FROM (s.fim - s.ini)) / 3600.0)
       ) AS desconto_intervalo
FROM s
LEFT JOIN b ON b.employee_id = s.employee_id
           AND b.ts BETWEEN s.ini - make_interval(hours => :tol)
                        AND s.fim + make_interval(hours => :tol)
GROUP BY s.id, s.employee_id, s.shift_date, s.is_off_day, s.planned_hours, s.ini, s.fim
"""


@dataclass
class Resultado:
    completed: int = 0
    partial: int = 0
    candidatas_falta: int = 0
    off_day: int = 0
    aplicado: bool = False
    exemplos_candidatas: list[dict] = field(default_factory=list)

    def resumo(self) -> str:
        modo = "APLICADO" if self.aplicado else "simulação (nada foi escrito)"
        return (f"{modo}: completed={self.completed} partial={self.partial} "
                f"off_day={self.off_day} candidatas_a_falta={self.candidatas_falta}")


async def fechar_turnos_por_ponto(
    db: AsyncSession,
    ate: date | None = None,
    aplicar: bool = False,
) -> Resultado:
    """Fecha turnos já encerrados com base nas batidas.

    `aplicar=False` (padrão) só mede — não escreve nada. É assim de propósito: quem
    chama tem que pedir a escrita explicitamente.

    Nunca toca em turno que não esteja `scheduled`: status posto por humano
    (cancelled, substituted, missed) é decisão que a máquina não desfaz. E é
    idempotente — só olha turno com `actual_start_time` NULL, então o que já fechou
    não é revisitado.
    """
    ate = ate or (date.today() - timedelta(days=1))
    linhas = (await db.execute(text(_SQL_CANDIDATOS),
                               {"ate": ate, "tol": TOLERANCIA_HORAS,
                                "piso": PISO_BATIDA})).fetchall()

    res = Resultado(aplicado=aplicar)
    fechar: list[tuple[str, object, object, float | None]] = []

    for sid, _emp, sdata, off_day, plan_h, entrada, saida, n, desconto in linhas:
        if off_day:
            res.off_day += 1
            continue
        if entrada and saida and saida > entrada:
            # LÍQUIDO, não o vão bruto: actual_hours tem que ser comparável a
            # planned_hours. Guardar o vão fabricava ~1h de hora extra por turno de
            # 8h — medido em 14/08: 535 turnos "com excedente" somando 409,5h viraram
            # 151 turnos somando 34,0h depois do desconto correto.
            horas = (saida - entrada).total_seconds() / 3600.0 - float(desconto or 0)
            if horas <= 0:
                # Par existe mas não sobra jornada nenhuma depois do intervalo. São
                # batidas curtas de meio-dia (medido: 5 casos de 12:06→13:01 num turno
                # de 07:00–16:00) — ida ao almoço lida como entrada/saída. Chamar isso
                # de turno concluído é mentira; `partial` é o que o enum já diz:
                # "saiu antes/chegou depois". Sem régua inventada: o corte é zero.
                res.partial += 1
                fechar.append((str(sid), entrada, saida, 0.0))
            else:
                res.completed += 1
                fechar.append((str(sid), entrada, saida, round(horas, 2)))
        elif n:
            res.partial += 1
            fechar.append((str(sid), entrada, saida, None))
        else:
            # NÃO vira missed aqui. Vira lista para humano.
            res.candidatas_falta += 1
            if len(res.exemplos_candidatas) < 20:
                res.exemplos_candidatas.append({"shift_id": str(sid), "data": str(sdata),
                                                "planejadas": float(plan_h or 0)})

    if not aplicar:
        return res

    for sid, entrada, saida, horas in fechar:
        # status FICA como está — ver o aviso no topo do módulo.
        await db.execute(text("""
            UPDATE shifts
               SET actual_start_time = coalesce(:ini, actual_start_time),
                   actual_end_time   = coalesce(:fim, actual_end_time),
                   actual_hours      = coalesce(:h, actual_hours),
                   updated_at        = now()
             WHERE id::text = :sid AND status::text = 'scheduled'
        """), {"ini": entrada, "fim": saida, "h": horas, "sid": sid})
    await db.commit()
    logger.info("fechamento de turno: %s", res.resumo())
    return res
