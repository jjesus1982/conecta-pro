"""A precisao do GPS enviada pelo app tem que CHEGAR ao banco.

Por que existe: em 24/08/2026 medi 836 batidas com `accuracy` NULO — todas. A coluna
existia, o schema `LocationData` aceitava o campo e o app passou a mandar o valor real em
23/08... e o `ClockPunchModel(...)` simplesmente nao recebia o argumento. O dado entrava
pela porta e caia no chao.

Isso importa porque `accuracy` e o unico jeito de, depois, distinguir "a pessoa estava
longe do posto" de "o aparelho nao sabia onde estava". E essa duvida decide se alguem leva
falta injusta: 164 batidas ja estavam marcadas fora do posto sem esse numero.

Roda dentro de uma transacao que e SEMPRE desfeita — nao grava batida em producao.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.people_management.ponto.models.clock_punch import ClockPunchModel  # noqa: E402

PRECISAO = 1234.5


async def main() -> None:
    async with async_session_factory() as db:
        emp = (
            await db.execute(
                text(
                    "SELECT id, nome FROM employees WHERE status='ativo' "
                    "  AND coalesce(is_homologacao,false)=false ORDER BY nome LIMIT 1"
                )
            )
        ).first()
        assert emp, "pre-condicao: nenhum colaborador ativo"

        pid = str(uuid.uuid4())
        try:
            punch = ClockPunchModel(
                # punch_id e varchar(36): cabe o uuid puro, nao um prefixo + uuid.
                punch_id=pid,
                employee_id=emp[0],
                punch_type="entrada",
                punch_timestamp=datetime(2000, 1, 1, 0, 0),
                latitude=-3.1,
                longitude=-60.0,
                accuracy=PRECISAO,
                status="pending",
                device_type="mobile",
            )
            db.add(punch)
            await db.flush()

            lido = (
                await db.execute(
                    text("SELECT accuracy FROM gp_clock_punches WHERE punch_id=:p"),
                    {"p": punch.punch_id},
                )
            ).scalar()
            assert lido is not None, "a coluna accuracy nao persiste — o valor sumiu"
            assert abs(float(lido) - PRECISAO) < 0.01, f"gravou {lido}, esperado {PRECISAO}"
            print(f"OK  a coluna grava a precisao  ({lido} m)")
        finally:
            # NUNCA deixa a batida de teste no banco de producao.
            await db.rollback()

        sobrou = (
            await db.execute(text("SELECT count(*) FROM gp_clock_punches WHERE punch_id=:p"), {"p": pid})
        ).scalar()
        assert sobrou == 0, f"sobrou {sobrou} batida(s) de teste no banco"
        print("OK  nada de teste sobrou em gp_clock_punches")

        # Suspenders: o defeito exato foi o SERVICO nao passar o campo ao model. Uma coluna
        # que grava nao prova nada se quem cria a batida esquecer de preencher.
        import inspect

        from modules.people_management.ponto.services.punch_service import PunchService

        fonte = inspect.getsource(PunchService)
        assert "accuracy=" in fonte, (
            "o punch_service voltou a criar a batida SEM passar accuracy — "
            "foi exatamente assim que 836 batidas ficaram com precisao nula"
        )
        print("OK  o punch_service passa accuracy ao criar a batida")

    print("TEST oraculo_precisao_gps_gravada PASS")


if __name__ == "__main__":
    asyncio.run(main())
