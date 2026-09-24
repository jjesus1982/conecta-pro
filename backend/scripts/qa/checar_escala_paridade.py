#!/usr/bin/env python3
"""Escala de 12x36 lançada na PARIDADE ERRADA — a grade nos ímpares, a vida nos pares.

Origem: 24/09/2026, frente DGX V1 (`auditoria/frentes/DGX_V1_plantao_um_dia.md` §1, nota ¹).
Ao medir o plantão noturno, quatro pessoas sobraram com resíduo que NÃO era do motor:
RILEM FERREIRA tinha `shifts` nos dias ÍMPARES de 08/2026 (18:00–06:00) e batia nos PARES —
15 plantões reais, ZERO dentro da janela lançada. ADEILSON, DANIEL e MAURÍCIO, o mesmo
desencontro em parte do mês. Num 12x36 a escala alterna dia sim, dia não: lançar o ciclo
começando um dia adiantado (ou atrasado) produz uma grade inteira em contrafase, e nada no
sistema reclama — cada turno isolado parece plausível.

O estrago é silencioso e diário:
  - o mapa de ponto chama o posto de DESCOBERTO todo dia, e a pessoa de FORA DE ESCALA;
  - a substituição/cobertura mede buraco onde há gente trabalhando;
  - o motor de benefício conta o dia como `E` (trabalhou fora da escala) — certo no total,
    ilegível na conferência;
  - e o oposto: 15 turnos lançados no mês inteiro sem uma batida sequer, que ninguém apura.

A régua (a classe, não o caso): dentro de um mês, para quem tem 12x36 NOTURNO lançado,
  ≥ 70% das batidas caem FORA de toda janela de turno   E
  ≥ 70% dos turnos lançados terminam SEM nenhuma batida.
As duas metades juntas descrevem contrafase e só ela — quem faltou muito falha só a segunda,
quem fez hora extra falha só a primeira. Janela do turno = [início−1h, fim+1h], a mesma
tolerância de `horas_service.TOLERANCIA_TURNO_H`, e o noturno vai até o dia seguinte.

    python3 backend/scripts/qa/checar_escala_paridade.py
    CP_BANCO=conecta_pro_staging CP_PG=conecta-pro-postgres-staging python3 ...  # sandbox

Linha canônica: `TOTAL escalas na paridade errada: <n>`. Exit 1 quando há achado.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date

#: Caminho absoluto: ruff S607 recusa executável parcial.
DOCKER = "/usr/bin/docker"  # nosec B607

#: Fração das batidas fora de toda janela / dos turnos sem batida que caracteriza contrafase.
#: 70% e não 100% porque a grade costuma estar certa na virada do mês (a contrafase começa
#: num dia) e porque dobra e substituição sempre deixam um resto legítimo.
LIMIAR = 0.70

#: Piso de amostra. Com 2 turnos e 2 batidas qualquer coincidência bate 100% — e o mês de
#: quem entrou no dia 27 não é contrafase, é mês curto.
#: ponytail: constante; vira parâmetro se entrar escala com ciclo diferente do 12x36.
MIN_TURNOS = 5
MIN_BATIDAS = 5

#: Quantos meses para trás olhar (inclui o mês corrente).
MESES = 3

SQL = """
WITH turno AS (
    SELECT CAST(s.employee_id AS TEXT) AS eid,
           coalesce(e.nome, '?')       AS nome,
           date_trunc('month', s.shift_date)::date AS comp,
           s.shift_date,
           (s.shift_date + s.planned_start_time) - interval '1 hour' AS j0,
           (s.shift_date
              + CASE WHEN s.planned_end_time < s.planned_start_time
                     THEN interval '1 day' ELSE interval '0' END
              + s.planned_end_time) + interval '1 hour' AS j1
      FROM shifts s
      JOIN employees e ON CAST(e.id AS TEXT) = CAST(s.employee_id AS TEXT)
     WHERE s.shift_date >= :ini AND s.shift_date < :fim
       AND lower(coalesce(s.status, '')) <> 'cancelled'
       AND NOT coalesce(s.is_off_day, false)
       -- 12x36 NOTURNO: o turno termina antes de começar (o mesmo que is_night_shift marca)
       AND s.planned_start_time > s.planned_end_time
       AND lower(coalesce(e.status, '')) NOT IN ('demitido', 'inativo')
       AND coalesce(e.is_homologacao, false) = false
), batida AS (
    SELECT CAST(p.employee_id AS TEXT) AS eid,
           date_trunc('month', p.punch_timestamp)::date AS comp,
           p.punch_timestamp AS ts
      FROM gp_clock_punches p
     WHERE p.punch_timestamp >= :ini AND p.punch_timestamp < :fim
), turno_m AS (
    SELECT eid, nome, comp, shift_date,
           EXISTS (SELECT 1 FROM batida b
                    WHERE b.eid = t.eid AND b.ts BETWEEN t.j0 AND t.j1) AS tem_batida
      FROM turno t
), batida_m AS (
    SELECT b.eid, b.comp,
           EXISTS (SELECT 1 FROM turno t
                    WHERE t.eid = b.eid AND b.ts BETWEEN t.j0 AND t.j1) AS tem_turno
      FROM batida b
     WHERE EXISTS (SELECT 1 FROM turno t WHERE t.eid = b.eid AND t.comp = b.comp)
), agg AS (
    SELECT t.eid, max(t.nome) AS nome, t.comp,
           count(*)                                  AS turnos,
           count(*) FILTER (WHERE NOT t.tem_batida)  AS turnos_vazios,
           (SELECT count(*) FROM batida_m m WHERE m.eid = t.eid AND m.comp = t.comp) AS batidas,
           (SELECT count(*) FROM batida_m m
             WHERE m.eid = t.eid AND m.comp = t.comp AND NOT m.tem_turno)            AS batidas_fora
      FROM turno_m t
     GROUP BY t.eid, t.comp
)
SELECT nome || '|' || to_char(comp, 'MM/YYYY') || '|' || turnos || '|' || turnos_vazios
       || '|' || batidas || '|' || batidas_fora
  FROM agg
 WHERE turnos >= {min_turnos} AND batidas >= {min_batidas}
   AND turnos_vazios::numeric / turnos  >= {limiar}
   AND batidas_fora::numeric / batidas  >= {limiar}
 ORDER BY comp DESC, nome
"""


def _janela(hoje: date) -> tuple[str, str]:
    """Primeiro dia do mês MESES-1 atrás → primeiro dia do mês seguinte ao corrente."""
    ano, mes = hoje.year, hoje.month - (MESES - 1)
    while mes <= 0:
        ano, mes = ano - 1, mes + 12
    fim_a, fim_m = (hoje.year + (hoje.month == 12)), (hoje.month % 12) + 1
    return f"{ano}-{mes:02d}-01", f"{fim_a}-{fim_m:02d}-01"


def main() -> int:
    ini, fim = _janela(date.today())
    sql = SQL.format(min_turnos=MIN_TURNOS, min_batidas=MIN_BATIDAS, limiar=LIMIAR)
    sql = sql.replace(":ini", f"'{ini}'").replace(":fim", f"'{fim}'")
    saida = subprocess.run(  # noqa: S603  # nosec B603 - argv fixo, sem shell
        [
            DOCKER,
            "exec",
            os.environ.get("CP_PG", "conecta-pro-postgres"),
            "psql",
            "-U",
            "postgres",
            "-d",
            os.environ.get("CP_BANCO", "conecta_pro"),
            "-tA",
            "-c",
            sql,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if saida.returncode != 0:
        print(f"FALHOU: não deu para consultar o banco: {saida.stderr.strip()[:200]}")
        print("TOTAL escalas na paridade errada: 1")
        return 1

    achados = [linha for linha in saida.stdout.splitlines() if linha.strip()]
    for linha in achados:
        nome, comp, turnos, vazios, batidas, fora = (linha.split("|") + [""] * 6)[:6]
        print(
            f"  ✗ {nome[:28]:<28} {comp}  {vazios}/{turnos} turnos sem batida · "
            f"{fora}/{batidas} batidas fora de toda janela"
        )
    if achados:
        print(f"  (janela {ini} → {fim}; a grade alterna dia sim/dia não — quem corrige é a operação)")
    print(f"TOTAL escalas na paridade errada: {len(achados)}")
    return 1 if achados else 0


if __name__ == "__main__":
    sys.exit(main())
