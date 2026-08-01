"""Captura os eventos S-1010 (Tabela de Rubricas) do NOSSO CNPJ no eSocial.

Por que existe: os códigos legais das rubricas (natRubr / codIncCP / codIncIRRF /
codIncFGTS) são o gargalo para o S-1200. Eles estão registrados sob o nosso CNPJ no
governo e são acessíveis com o NOSSO certificado — não dependem de terceiros.

READ-ONLY: só consulta e salva a resposta crua. Não transmite, não grava no banco,
não interpreta. A interpretação é feita depois, com revisão.

Idempotente: ao ter sucesso grava um marcador e as execuções seguintes não fazem nada
(evita martelar o webservice do governo).

Uso: python3 esocial_captura_s1010.py [--forcar]
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

SAIDA = Path("/app/uploads/esocial_s1010")  # volume: host = /opt/conecta-pro/uploads/esocial_s1010
MARCADOR = SAIDA / "_CAPTURADO.json"
CNPJS = {
    "eletronica": "35710481000103",
    "patrimonial": "66014833000110",
}


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} {msg}", flush=True)


def main() -> int:
    SAIDA.mkdir(parents=True, exist_ok=True)
    if MARCADOR.exists() and "--forcar" not in sys.argv:
        return 0  # já capturado — silêncio para não poluir o cron

    sys.path.insert(0, "/app")
    from modules.government_integrations.core.esocial_eventos_client import ESocialEventosClient

    resultado: dict[str, dict] = {}
    algum_sucesso = False

    for nome, cnpj in CNPJS.items():
        try:
            cli = ESocialEventosClient()
            r = cli.consultar_identificadores_tabela(cnpj, "S-1010", dt_ini="2020-01", dt_fim="2026-12")
        except Exception as exc:  # noqa: BLE001 — governo fora/bloqueado: tenta de novo no próximo cron
            log(f"{nome}: indisponível — {type(exc).__name__}: {str(exc)[:120]}")
            resultado[nome] = {"erro": f"{type(exc).__name__}: {str(exc)[:200]}"}
            continue

        ids = list(getattr(r, "identificadores", None) or [])
        resultado[nome] = {
            "cd_resposta": r.cd_resposta,
            "desc_resposta": str(r.desc_resposta)[:300],
            "qtd_identificadores": len(ids),
            "identificadores": ids[:200],
        }
        # resposta crua — é dela que sairão natRubr/codIncCP/... na análise posterior
        (SAIDA / f"{nome}_raw.xml").write_text(getattr(r, "raw", "") or "", encoding="utf-8")
        log(f"{nome}: cd={r.cd_resposta} ids={len(ids)}")
        if r.cd_resposta and str(r.cd_resposta).startswith("2"):
            algum_sucesso = True

    (SAIDA / "resumo.json").write_text(
        json.dumps({"em": datetime.now(timezone.utc).isoformat(), "resultado": resultado},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if algum_sucesso:
        MARCADOR.write_text(json.dumps({"capturado_em": datetime.now(timezone.utc).isoformat()}), encoding="utf-8")
        log("CAPTURADO — cron não repete (use --forcar para recapturar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
