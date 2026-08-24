"""Corrigir o tipo de uma batida exige tipo válido, autor identificado e auditoria.

🔴 POR QUE ESTA ROTA EXISTE. A auditoria de 23/08/2026 achou 142 erros de sequência no
ponto, quase todos vindos de dois defeitos do app: a contagem por data zerava o turno
noturno à meia-noite (33 "entradas" de quem já trabalhava há horas) e a sequência não sabia
a hora (18 "saídas para o almoço" às 18h — a Lívia bateu uma porque o app pediu).

Corrigi 24 por SQL, com a batida do Sólides no mesmo minuto como fonte. Para as 39
restantes não há fonte externa, e o DP NÃO TINHA FERRAMENTA: o PATCH aceitava só `status` e
`justification`. Dava para justificar uma batida errada, não para consertá-la.

⚠️ ISTO EDITA DOCUMENTO TRABALHISTA. Este oráculo trava as três garantias, porque a
tentação de afrouxar qualquer uma delas aparece no primeiro chamado urgente:
  1. só os 4 tipos válidos entram — correção não inventa vocabulário;
  2. sem autor identificado, recusa — alteração anônima em ponto não existe;
  3. a auditoria é obrigatória e NÃO engole exceção — sem rastro, sem correção.

Afirma a REGRA, com casos sintéticos criados e removidos aqui. Não depende de nenhuma
batida real nem de quem errou o ponto em agosto.
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402
from modules.people_management.hr.services.time_record_service import (  # noqa: E402
    _TIPOS_BATIDA_VALIDOS,
    TimeRecordService,
)

# ZZ FIXO: ordena no fim de qualquer listagem, então batida sintética que escapar aparece
# agrupada no rodapé em vez de escondida no meio do ponto real.
_PREFIXO = "ZZORQ-CORRIGE-"
#: A marca anterior, varrida junto — trocar de prefixo sem varrer o antigo cria órfão novo.
_PREFIXOS_ANTIGOS = ("ORQ-CORRIGE-",)


async def main() -> None:
    assert {"entrada", "saida", "saida_almoco", "retorno_almoco"} == _TIPOS_BATIDA_VALIDOS, (
        f"vocabulário de tipos mudou: {sorted(_TIPOS_BATIDA_VALIDOS)} — se for de propósito, "
        "o espelho de ponto e a máquina de estados precisam saber junto"
    )

    async with async_session_factory() as db:
        emp = (
            await db.execute(text("SELECT id::text FROM employees WHERE lower(coalesce(status,'')) = 'ativo' LIMIT 1"))
        ).scalar()
        assert emp, "sem funcionário ativo — pré-condição do oráculo"

        falhas: list[str] = []
        try:
            for _pfx in (_PREFIXO, *_PREFIXOS_ANTIGOS):
                await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id LIKE :p"),
                                 {"p": f"{_pfx}%"})
            await db.execute(
                text(
                    "INSERT INTO gp_clock_punches (punch_id, employee_id, punch_type, "
                    "  punch_timestamp, status, device_type) "
                    "VALUES (:pid, CAST(:e AS uuid), 'entrada', now() - interval '2 hours', "
                    "  'approved', 'mobile')"
                ),
                {"pid": f"{_PREFIXO}1", "e": emp},
            )
            await db.flush()
            svc = TimeRecordService(db)

            async def tenta(data, quem):
                try:
                    await svc.update_record(f"{_PREFIXO}1", data, updated_by=quem)
                    return "aceita"
                except ValueError:
                    return "recusa"

            if await tenta({"punch_type": "almoco_inventado"}, "dp") != "recusa":
                falhas.append("tipo fora do vocabulário foi ACEITO")
            if await tenta({"punch_type": "saida"}, None) != "recusa":
                falhas.append("correção ANÔNIMA foi aceita — ponto sem autor")
            if await tenta({"punch_type": "saida", "motivo": "oráculo"}, "dp-oraculo") != "aceita":
                falhas.append("correção legítima foi recusada")

            tipo = (
                await db.execute(
                    text("SELECT punch_type FROM gp_clock_punches WHERE punch_id = :p"),
                    {"p": f"{_PREFIXO}1"},
                )
            ).scalar()
            if tipo != "saida":
                falhas.append(f"tipo não foi corrigido: ficou {tipo!r}")

            auditoria = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM gp_audit_logs  WHERE action = 'ponto.tipo_corrigido' AND entity_id = :p"
                    ),
                    {"p": f"{_PREFIXO}1"},
                )
            ).scalar()
            if auditoria != 1:
                falhas.append(f"auditoria não gravada ({auditoria} registros) — correção sem rastro")
        finally:
            for _pfx in (_PREFIXO, *_PREFIXOS_ANTIGOS):
                await db.execute(text("DELETE FROM gp_clock_punches WHERE punch_id LIKE :p"),
                                 {"p": f"{_pfx}%"})
            await db.execute(text("DELETE FROM gp_audit_logs WHERE entity_id LIKE :p"), {"p": f"{_PREFIXO}%"})
            await db.commit()

        assert not falhas, f"{len(falhas)} garantia(s) quebrada(s) — " + " ; ".join(falhas)

    print("OK só os 4 tipos válidos entram")
    print("OK correção sem autor identificado é recusada")
    print("OK correção legítima aplica E grava auditoria com de/para")
    print("TEST oraculo_correcao_batida_auditada PASS")


if __name__ == "__main__":
    asyncio.run(main())
