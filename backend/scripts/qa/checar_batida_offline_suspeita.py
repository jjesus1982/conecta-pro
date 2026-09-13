"""Caçador — batida OFFLINE suspeita: relógio fora do limite, duplicata por chave, taxa perfeita.

Frente 2 (13/09/2026). Três suspeitas, e cada uma tem um precedente medido nesta casa:

1. **Relógio divergente.** `divergencia_relogio_seg` acima do parâmetro
   `ponto.offline.divergencia_relogio_max_seg`. Relógio de celular é editável; a batida não é
   apagada nem corrigida — ela é CONTADA, e o DP decide.
2. **Duplicata na janela.** Mesma pessoa, mesmo tipo, duas batidas offline dentro da janela de
   idempotência. A chave única impede a retentativa idêntica; o que este caçador pega é a
   retentativa que conseguiu gerar chave NOVA — exatamente o mecanismo que produziu 1.375
   jornadas duplicadas no importador do Tangerino em 11/09/2026.
3. **Taxa facial 100% no dia.** Um dia com >= 10 batidas offline e nenhuma falha de
   reconhecimento não é um dia bom: é o sinal de que a reconferência não está acontecendo. O
   inverso do buraco em que a ERIKA aparecia com zero falhas registradas em 32 tentativas.

Sem batida offline no banco, a resposta é 0 — e 0 aqui significa "não há suspeita", não "não há
dado". A afirmação de que o mecanismo funciona é do oráculo `test_oraculo_batida_offline`, não
deste contador.

Linha canônica: `TOTAL batidas offline suspeitas: N`. Sai 1 se N > 0.
Roda no container: `docker exec -e PYTHONPATH=/app <backend> python3 /app/scripts/qa/checar_batida_offline_suspeita.py`
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

#: Usados quando `system_configs` não tem a chave. Iguais aos de `reconferencia_facial`.
DIVERGENCIA_MAX_SEG = 300
JANELA_MIN = 20
MIN_BATIDAS_DIA = 10

SQL_PARAM = """
SELECT chave, nullif(trim(valor),'') FROM system_configs
WHERE chave IN ('ponto.offline.divergencia_relogio_max_seg','ponto.offline.janela_idempotencia_min')
  AND ativo
"""

SQL_RELOGIO = """
SELECT p.punch_id, e.nome, p.punch_timestamp, p.divergencia_relogio_seg, p.device_id
FROM gp_clock_punches p JOIN employees e ON e.id = p.employee_id
WHERE p.is_offline AND abs(coalesce(p.divergencia_relogio_seg, 0)) > :lim
ORDER BY abs(p.divergencia_relogio_seg) DESC
"""

SQL_DUPLICATA = """
SELECT a.punch_id, b.punch_id, e.nome, a.punch_type, a.punch_timestamp, b.punch_timestamp
FROM gp_clock_punches a
JOIN gp_clock_punches b ON b.employee_id = a.employee_id AND b.punch_type = a.punch_type
 AND b.id > a.id
 AND b.punch_timestamp BETWEEN a.punch_timestamp AND a.punch_timestamp + (:jan || ' minutes')::interval
JOIN employees e ON e.id = a.employee_id
WHERE a.is_offline AND b.is_offline
ORDER BY a.punch_timestamp
"""

SQL_TAXA = """
SELECT punch_timestamp::date d, count(*) n
FROM gp_clock_punches
WHERE is_offline
GROUP BY 1
HAVING count(*) >= :min AND count(*) = count(*) FILTER (WHERE facial_match)
ORDER BY 1
"""

#: Batida pendente que ninguém conferiu há mais de um dia não é suspeita de fraude — é suspeita
#: de esquecimento, e vale o mesmo alarme: quem está esperando é uma pessoa que trabalhou.
SQL_PENDENTE_VELHA = """
SELECT p.punch_id, e.nome, p.punch_timestamp
FROM gp_clock_punches p JOIN employees e ON e.id = p.employee_id
WHERE p.status = 'pendente_de_conferencia'
  AND p.server_timestamp < (now() AT TIME ZONE 'America/Manaus') - interval '24 hours'
ORDER BY p.punch_timestamp
"""


async def main() -> int:
    from core.database import get_db

    gen = get_db()
    db = await gen.__anext__()
    linhas: list[str] = []
    try:
        lim, jan = DIVERGENCIA_MAX_SEG, JANELA_MIN
        for chave, valor in (await db.execute(text(SQL_PARAM))).fetchall():
            if valor is None:
                continue
            try:
                if chave.endswith("divergencia_relogio_max_seg"):
                    lim = int(float(valor))
                else:
                    jan = int(float(valor))
            except (TypeError, ValueError):
                pass

        for pid, nome, ts, dv, dev in (await db.execute(text(SQL_RELOGIO), {"lim": lim})).fetchall():
            linhas.append(
                f"  relógio: {nome} {ts:%d/%m %H:%M} no aparelho {dev or '?'} — "
                f"{dv}s de diferença para o servidor (limite {lim}s) · punch {pid}"
            )
        for pa, pb, nome, tipo, ta, tb in (
            await db.execute(text(SQL_DUPLICATA), {"jan": str(jan)})
        ).fetchall():
            linhas.append(
                f"  duplicata: {nome} {tipo} {ta:%d/%m %H:%M:%S} e {tb:%H:%M:%S} "
                f"(dentro de {jan} min) · punch {pa} / {pb}"
            )
        for d, n in (await db.execute(text(SQL_TAXA), {"min": MIN_BATIDAS_DIA})).fetchall():
            linhas.append(
                f"  taxa perfeita: {d:%d/%m/%Y} com {n} batidas offline e NENHUMA falha facial — "
                f"a reconferência não está acontecendo"
            )
        for pid, nome, ts in (await db.execute(text(SQL_PENDENTE_VELHA))).fetchall():
            linhas.append(
                f"  esquecida: {nome} {ts:%d/%m %H:%M} pendente de conferência há mais de 24h "
                f"· punch {pid}"
            )
    finally:
        await gen.aclose()

    for linha in linhas[:40]:
        print(linha)
    if len(linhas) > 40:
        print(f"  (+{len(linhas) - 40} não listadas)")
    print(f"TOTAL batidas offline suspeitas: {len(linhas)}")
    return 1 if linhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
