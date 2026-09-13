"""Oráculo — frota: toda vistoria de SAÍDA compara com a CHEGADA do mesmo carro, mesma OS, mesmo
condutor, mesma janela — ou diz "aguardando checklist" (frente 10, 12/09/2026).

Pré-mortem da frente 10: *"a vistoria chegada×saída vai comparar fotos de dias diferentes. Sem
amarrar as duas pontas pela mesma OS e pelo mesmo condutor, 'houve diferenças' acusa o motorista
errado — e isso é acusação sobre pessoa."*

Estado medido no nascimento (staging, 12/09): não existia tabela de veículo, leitura ou vistoria
(`pg_stat_user_tables` sem nada que case com veic|vehic|frota|fleet|vistoria). VERMELHO por
ausência do mecanismo — não há como afirmar o par.

Afirmações (re-derivadas dos dados, não lidas do status):
  1. Saída com `par_id` aponta para uma CHEGADA do mesmo veículo, mesma `os_ref`, mesmo
     `condutor_id`, anterior à saída e dentro da janela (`_frente_10.JANELA_VISTORIA_HORAS`).
  2. Saída sem par tem `status_saida = 'aguardando_checklist'` — nunca "sem diferenças" nem
     "houve diferenças" sem a outra ponta.
  3. Saída com par tem veredito ('sem_diferencas' | 'houve_diferencas'), e nenhuma chegada é par
     de duas saídas.

Roda no container (PYTHONPATH=/app). Sai 0 = verde; 1 = vermelho.
"""
from __future__ import annotations

import asyncio
import sys


async def main() -> int:
    from sqlalchemy import text

    from core.database import get_db

    falhas: list[str] = []
    try:
        from modules.operacional.controllers.redesign_builders._frente_10 import JANELA_VISTORIA_HORAS
    except ImportError as e:
        print(f"FALHOU: regra de pareamento não existe ({e})")
        raise AssertionError("mecanismo de vistoria ausente") from e

    gen = get_db()
    db = await gen.__anext__()
    try:
        if not (await db.execute(text("SELECT to_regclass('public.frota_vistorias')"))).scalar():
            print("FALHOU: tabela frota_vistorias não existe — vistoria de saída não tem com que comparar")
            raise AssertionError("mecanismo de vistoria ausente")

        saidas = (await db.execute(text(
            "SELECT s.id, s.veiculo_id, s.os_ref, s.condutor_id::text, s.criado_em, s.par_id, s.status_saida, "
            "c.veiculo_id, c.os_ref, c.condutor_id::text, c.criado_em, c.tipo "
            "FROM frota_vistorias s LEFT JOIN frota_vistorias c ON c.id = s.par_id "
            "WHERE s.tipo = 'saida' ORDER BY s.id"
        ))).fetchall()
        pares_usados: dict[int, int] = {}
        for sid, sv, sos, scond, sq, par, status, cv, cos, ccond, cq, ctipo in saidas:
            if par is None:
                if status != "aguardando_checklist":
                    falhas.append(f"saída #{sid}: sem chegada e status '{status}' — veredito sem a outra ponta")
                continue
            if ctipo != "chegada":
                falhas.append(f"saída #{sid}: par #{par} não é chegada ({ctipo})")
            if (cv, cos, ccond) != (sv, sos, scond):
                falhas.append(f"saída #{sid}: par #{par} é de outro carro/OS/condutor "
                              f"({cv},{cos},{ccond}) ≠ ({sv},{sos},{scond})")
            if cq is None or sq is None or cq >= sq:
                falhas.append(f"saída #{sid}: chegada #{par} não é anterior à saída")
            elif (sq - cq).total_seconds() > JANELA_VISTORIA_HORAS * 3600:
                falhas.append(f"saída #{sid}: chegada #{par} fora da janela de {JANELA_VISTORIA_HORAS}h")
            if status not in ("sem_diferencas", "houve_diferencas"):
                falhas.append(f"saída #{sid}: tem par e status '{status}' (esperado veredito)")
            if par in pares_usados:
                falhas.append(f"chegada #{par} é par de duas saídas (#{pares_usados[par]} e #{sid})")
            pares_usados[par] = sid

        print(f"vistorias de saída: {len(saidas)} · com par: {len(pares_usados)} · "
              f"aguardando checklist: {sum(1 for s in saidas if s[5] is None)}")
    finally:
        try:
            await gen.aclose()
        except Exception:  # noqa: BLE001
            pass

    for f in falhas:
        print("FALHOU:", f)
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) no par chegada×saída")
    print("OK vistoria_par: toda saída compara com a chegada certa ou espera o checklist")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print("VERMELHO:", e)
        sys.exit(1)
