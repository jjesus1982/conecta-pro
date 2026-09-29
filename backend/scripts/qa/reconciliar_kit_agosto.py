"""CLI da reconciliação de kits. ENSAIO por padrão.

    python3 reconciliar_kit_agosto.py                  # ensaio, competência = mês anterior
    python3 reconciliar_kit_agosto.py 08/2026          # ensaio de uma competência
    python3 reconciliar_kit_agosto.py 08/2026 --aplicar

⭐ 29/09/2026 — ESTE ARQUIVO NÃO TEM MAIS REGRA NEM `DELETE`. Tudo mora em
`modules/people_management/ged/services/kit_roster_service.py`, que serve também a tela
«Conferir kits do mês» da Pyetra.

POR QUÊ: havia um bloco de apagar aqui e outro na ação da tela. **Duas cópias de um `DELETE`
divergem na primeira correção, e a que fica atrás é a que apaga errado.** Este arquivo existe
agora só para quem está no terminal — a Pyetra faz o mesmo pela tela, e os dois caminhos dão o
mesmo resultado porque executam o mesmo código.

O que o serviço garante e não se repete aqui: backup antes de remover, aborto se o backup vier
menor que o alvo, trilha em `gp_audit_logs`, prova por leitura posterior, e a regra de que quem
está apenas SEM RESOLUÇÃO nunca é removido — ignorância do sistema não vira ato sobre documento.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from core.database.session import get_sync_db  # noqa: E402
from modules.people_management.ged.services.kit_roster_service import (  # noqa: E402
    aplicar_reconciliacao,
    plano_reconciliacao,
)


def _competencia() -> date:
    """MM/AAAA ou MM.AAAA no argv; sem argumento, o mês ANTERIOR (o kit entregue agora)."""
    for a in sys.argv[1:]:
        if a.startswith("--"):
            continue
        mes, ano = (int(x) for x in a.replace(".", "/").split("/", 1))
        return date(ano, mes, 1)
    return (date.today().replace(day=1) - timedelta(days=1)).replace(day=1)


def main() -> None:
    aplicar = "--aplicar" in sys.argv
    comp = _competencia()
    quem = os.environ.get("USER") or "terminal"

    with get_sync_db() as db:
        plano = aplicar_reconciliacao(db, comp, quem) if aplicar else plano_reconciliacao(db, comp)

    r = plano["resumo"]
    por_cond: dict[str, list[dict]] = {}
    for ln in plano["linhas"]:
        por_cond.setdefault(ln["condominio"], []).append(ln)

    print(f"{'APLICADO' if aplicar else 'ENSAIO'} · competência {r['competencia']}\n")
    for cond in sorted(por_cond):
        print(f"{cond}")
        for ln in por_cond[cond]:
            marca = {"remover": "−", "pendente": "·", "kit_sem_roster": "⚠"}.get(ln.get("tipo"), "?")
            print(f"  {marca} {ln['pessoa']:<34} {ln['acao']}")
            print(f"      {ln['motivo']}")
        print()

    if plano["sem_condominio"]:
        print(
            f"SEM CONDOMÍNIO ({len(plano['sem_condominio'])}) — resolva na tela "
            "«Definir condomínio de quem ficou sem»:"
        )
        for x in plano["sem_condominio"]:
            print(f"  ? {x['pessoa']} — {x['batidas']} batida(s) no mês, nenhuma gravou o posto")
        print()

    print(
        f"{r['kits']} kit(s) de cliente · {r['pessoas_no_roster']} pessoa(s) no roster · "
        f"{r['a_remover']} a remover · {r['kits_sem_roster']} kit(s) sem roster · "
        f"{r.get('pendentes_no_kit', 0)} pendente(s) no kit · {r['sem_condominio']} sem condomínio"
    )
    if aplicar:
        n = plano.get("aplicado") or 0
        print(
            f"REMOVIDAS {n} linha(s) de documento"
            + (f", reversível em `{plano['backup']}`" if plano.get("backup") else "")
            + " · conferido por leitura posterior."
        )
    else:
        print("Nada foi escrito. Use --aplicar para efetivar.")


if __name__ == "__main__":
    main()
