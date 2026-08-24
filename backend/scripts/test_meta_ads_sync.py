#!/usr/bin/env python3
"""Prova que a sincronia do Meta Ads grava certo — ANTES de existir token.

Por que existe: o token de Ads está travado na verificação por SMS da Meta. Sem
teste, o dia em que ele chegar vira dia de descobrir bug. E havia um de verdade:
`ON CONFLICT (external_id)` estourava na PRIMEIRA campanha, porque o índice
único é PARCIAL e o Postgres não infere índice parcial sem repetir o predicado.
Estrutura certa não é comportamento certo — este script roda o SQL de verdade
contra o banco de verdade, com a Graph API simulada no lugar da rede.

O que verifica:
  1. grava campanha nova, com orçamento convertido de centavos para reais
  2. rodar de novo NÃO duplica (idempotente por external_id) e atualiza o gasto
  3. `utm_campaign` preenchida à mão SOBREVIVE à sincronia — é a chave de junção
     com `leads`, e gravar o id numérico da Meta ali quebraria o CAC para sempre
  4. o CSV do Gerenciador de Anúncios cai NAS MESMAS linhas — importar por CSV
     hoje e ligar a API amanhã atualiza, não duplica (vírgula decimal e BOM)
  5. CAC sai None (não 0) quando não há lead atribuído — vazio real é
     "aguardando dado"; zero afirma que a aquisição foi de graça

Limpa o que criou, sempre. Rode:  docker exec conecta-pro-backend python3 scripts/test_meta_ads_sync.py
"""

import asyncio
import os
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.integrations.connectors.meta import ads  # noqa: E402

EXT = ("ZZADS_1", "ZZADS_2")  # external_id de teste — apagados no fim

# Resposta que a Graph API devolveria. daily_budget vem em CENTAVOS, string.
_CAMPANHAS = {"data": [
    {"id": EXT[0], "name": "Vigilância Manaus", "status": "ACTIVE",
     "daily_budget": "5000", "start_time": "2026-08-01T00:00:00-0400"},
    {"id": EXT[1], "name": "Portaria Remota", "status": "PAUSED",
     "lifetime_budget": "120000", "start_time": "2026-07-15T00:00:00-0400"},
]}
_INSIGHTS = {"data": [
    {"campaign_id": EXT[0], "spend": "137.42", "impressions": "9100", "clicks": "212"},
]}
_INSIGHTS_2 = {"data": [
    {"campaign_id": EXT[0], "spend": "289.90", "impressions": "18000", "clicks": "410"},
]}


def _falso_get(insights):
    async def _g(_sessao, caminho, _params):
        return insights if "insights" in caminho else _CAMPANHAS
    return _g


async def _limpar(db):
    await db.execute(text("DELETE FROM marketing_campaigns WHERE external_id = ANY(:e)"),
                     {"e": list(EXT)})
    await db.commit()


async def main() -> int:
    os.environ["META_ADS_TOKEN"] = "token-de-teste"
    os.environ["META_AD_ACCOUNT_ID"] = "act_27813105738300215"
    original = ads._get
    falhas = []

    async with async_session_factory() as db:
        await _limpar(db)
        try:
            # 1 ─ primeira sincronia
            ads._get = _falso_get(_INSIGHTS)
            r = await ads.sincronizar_campanhas(db, dias=30)
            if not (r.get("ok") and r.get("gravadas") == 2):
                falhas.append(f"1) sincronia não gravou as 2 campanhas: {r}")

            linhas = (await db.execute(text(
                "SELECT external_id, name, budget, spent, status, utm_campaign"
                "  FROM marketing_campaigns WHERE external_id = ANY(:e) ORDER BY external_id"
            ), {"e": list(EXT)})).mappings().all()
            if len(linhas) != 2:
                falhas.append(f"1) esperava 2 linhas, achei {len(linhas)}")
            else:
                a, b = linhas
                if float(a["budget"]) != 50.0:
                    falhas.append(f"1) centavos→reais errado: 5000 virou {a['budget']}, esperado 50.00")
                if float(b["budget"]) != 1200.0:
                    falhas.append(f"1) lifetime_budget errado: {b['budget']}, esperado 1200.00")
                if float(a["spent"]) != 137.42:
                    falhas.append(f"1) gasto errado: {a['spent']}, esperado 137.42")
                if float(b["spent"]) != 0.0:
                    falhas.append(f"1) campanha sem insight devia ter gasto 0, veio {b['spent']}")

            # 2 ─ marketing preenche o slug à mão; a sincronia NÃO pode apagá-lo
            await db.execute(text(
                "UPDATE marketing_campaigns SET utm_campaign = 'lote2' WHERE external_id = :e"
            ), {"e": EXT[0]})
            await db.commit()

            # 3 ─ segunda sincronia, gasto maior: atualiza sem duplicar
            ads._get = _falso_get(_INSIGHTS_2)
            r2 = await ads.sincronizar_campanhas(db, dias=30)
            if not r2.get("ok"):
                falhas.append(f"3) segunda sincronia falhou: {r2}")

            total = (await db.execute(text(
                "SELECT count(*) FROM marketing_campaigns WHERE external_id = ANY(:e)"
            ), {"e": list(EXT)})).scalar()
            if total != 2:
                falhas.append(f"3) DUPLICOU: {total} linhas para 2 campanhas")

            depois = (await db.execute(text(
                "SELECT spent, utm_campaign FROM marketing_campaigns WHERE external_id = :e"
            ), {"e": EXT[0]})).mappings().one()
            if float(depois["spent"]) != 289.90:
                falhas.append(f"3) gasto não atualizou: {depois['spent']}, esperado 289.90")
            if depois["utm_campaign"] != "lote2":
                falhas.append(
                    f"3) SINCRONIA PISOU NO utm_campaign: virou {depois['utm_campaign']!r}, "
                    "era 'lote2' — isso quebraria a junção com leads e o CAC inteiro"
                )

            # 4 ─ CSV do Gerenciador de Anúncios: mesma tabela, mesmas linhas.
            # Escrito no formato pt-BR real: BOM, ponto-e-vírgula, vírgula decimal.
            csv_path = "/tmp/zz_ads_export.csv"
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                f.write("Identificação da campanha;Nome da campanha;Valor gasto (BRL);"
                        "Início dos relatórios;Término dos relatórios\n")
                f.write(f"{EXT[0]};Vigilância Manaus;1.402,75;2026-08-01;2026-08-10\n")
                f.write(f"{EXT[1]};Portaria Remota;89,90;2026-07-15;2026-08-10\n")
            rc = await ads.importar_csv(db, csv_path)
            if not (rc.get("ok") and rc.get("campanhas") == 2 and rc.get("por_id")):
                falhas.append(f"4) importação de CSV falhou: {rc}")

            total_csv = (await db.execute(text(
                "SELECT count(*) FROM marketing_campaigns WHERE external_id = ANY(:e)"
            ), {"e": list(EXT)})).scalar()
            if total_csv != 2:
                falhas.append(
                    f"4) CSV DUPLICOU sobre a sincronia por API: {total_csv} linhas para 2 "
                    "campanhas — importar hoje e ligar a API amanhã criaria campanha fantasma"
                )

            pos_csv = (await db.execute(text(
                "SELECT spent, utm_campaign FROM marketing_campaigns WHERE external_id = :e"
            ), {"e": EXT[0]})).mappings().one()
            if float(pos_csv["spent"]) != 1402.75:
                falhas.append(
                    f"4) vírgula decimal lida errado: '1.402,75' virou {pos_csv['spent']}, "
                    "esperado 1402.75"
                )
            if pos_csv["utm_campaign"] != "lote2":
                falhas.append(
                    f"4) CSV PISOU no utm_campaign: virou {pos_csv['utm_campaign']!r}, era 'lote2'"
                )
            os.remove(csv_path)

            # 5 ─ REGRA DA CASA: vazio real é "aguardando dado", NUNCA zero.
            #     Zero é uma afirmação — diz "não custou nada para adquirir este
            #     lead". None diz "não sei quantos leads vieram desta campanha",
            #     que é a verdade quando ninguém preencheu utm_campaign.
            #     Se alguém "limpar" isto para `or 0`, o painel passa a mentir
            #     com cara de número bom. Este assert existe para impedir isso.
            cac = {c["campanha"]: c for c in await ads.cac_por_campanha(db, dias=30)}
            pr = cac.get("Portaria Remota")
            if pr is None:
                falhas.append("5) cac_por_campanha não devolveu a campanha de teste")
            elif pr["cac"] is not None and pr["leads"] == 0:
                falhas.append(f"5) CAC devia ser None sem lead, veio {pr['cac']}")
        finally:
            ads._get = original
            await _limpar(db)

    for f in falhas:
        print(f"  FALHA: {f}")
    print("\n" + ("TODAS AS VERIFICAÇÕES PASSARAM" if not falhas else f"{len(falhas)} FALHA(S)"))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
