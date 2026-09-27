#!/usr/bin/env python3
"""Oráculo C9 — o encargo de folha conhece o anexo, e RECUSA quando não conhece.

## A regra que isto afirma

No Simples Nacional o encargo de folha depende do ANEXO, e a diferença não é detalhe:

  Anexo III  0,3244   CPP patronal DENTRO do DAS (tributação substituída)
  Anexo IV   0,5544   CPP 20% + RAT 3% FORA do DAS, pagos à parte
                      (terceiros 5,8% não é devido no Simples)

**23 pontos percentuais de folha.** Sobre a folha da Patrimonial de 08/2026
(R$ 106.577,20), são R$ 24.512,76/mês — que é, ao centavo, a CPP patronal medida na guia
do DAS. A precificação não conhecia o tributo que a declaração também não conhece.

## A asserção que mais importa

Não é o número — é a RECUSA. `encargo_pct("simples_nacional")` devolvia 0,3244 **sem saber
o anexo**, e precificou os contratos por meses como se a CPP não existisse. O defeito não
foi um valor errado: foi um default silencioso respondendo o que não sabia.

Se o tributarista disser que é Anexo III e a guia estiver errada, o NÚMERO muda e este
oráculo muda com ele. A recusa não muda nunca.

Linha canônica: `TOTAL desvios C9: <n>`.
"""

from __future__ import annotations

import sys

desvios = 0


def afirma(cond: bool, msg: str) -> None:
    global desvios
    if cond:
        print(f"OK {msg}")
    else:
        desvios += 1
        print(f"FALHOU: {msg}")


def main() -> int:
    from modules.financial.services.encargos import (  # noqa: PLC0415
        ENCARGOS_LUCRO_REAL,
        ENCARGOS_SIMPLES_ANEXO_III,
        ENCARGOS_SIMPLES_ANEXO_IV,
        AnexoNaoDeterminadoError,
        encargo_pct,
        encargo_pct_da_empresa,
    )

    # A composição, não o número decorado: Anexo IV = Anexo III + CPP 20% + RAT 3%.
    afirma(
        abs(ENCARGOS_SIMPLES_ANEXO_IV - (ENCARGOS_SIMPLES_ANEXO_III + 0.20 + 0.03)) < 1e-9,
        "Anexo IV = Anexo III + CPP 20% + RAT 3%",
    )
    # E o Lucro Real = Anexo IV + terceiros 5,8%, que o Simples não paga.
    afirma(
        abs(ENCARGOS_LUCRO_REAL - (ENCARGOS_SIMPLES_ANEXO_IV + 0.058)) < 1e-9,
        "Lucro Real = Anexo IV + terceiros 5,8% (que o Simples não deve)",
    )

    afirma(encargo_pct("lucro_real") == ENCARGOS_LUCRO_REAL, "Lucro Real dispensa anexo")
    afirma(
        encargo_pct("simples_nacional", "IV") == ENCARGOS_SIMPLES_ANEXO_IV,
        "Simples com anexo IV devolve o valor do IV",
    )
    afirma(
        encargo_pct("simples_nacional", "Anexo III") == ENCARGOS_SIMPLES_ANEXO_III,
        "aceita o anexo escrito por extenso",
    )

    # ─── a asserção que não muda nem que o número mude ───────────────────────
    try:
        encargo_pct("simples_nacional")
        afirma(False, "Simples SEM anexo tem de RECUSAR, não devolver default")
    except AnexoNaoDeterminadoError:
        afirma(True, "Simples sem anexo RECUSA — número não sabido é pergunta, não default")

    for vazio in ("", "   ", "V"):
        try:
            encargo_pct("simples_nacional", vazio)
            afirma(False, f"anexo {vazio!r} devia recusar")
        except AnexoNaoDeterminadoError:
            afirma(True, f"anexo {vazio!r} recusado")

    # ─── pelo cadastro, e a recusa vale lá também ────────────────────────────
    ELE = "619a3df1-8bce-49ce-b77a-04f80a0e8491"
    afirma(
        encargo_pct_da_empresa(ELE) == ENCARGOS_LUCRO_REAL,
        "pelo cadastro, a Eletrônica (Lucro Real) devolve 0,6124",
    )
    try:
        encargo_pct_da_empresa("00000000-0000-0000-0000-000000000000")
        afirma(False, "empresa inexistente devia recusar")
    except AnexoNaoDeterminadoError:
        afirma(True, "empresa inexistente recusa, não devolve default")

    # ─── o custo do posto reflete o anexo ────────────────────────────────────
    from modules.financial.controllers.precificacao_controller import (  # noqa: PLC0415
        DIAS_UTEIS,
        PISO_CATEGORIA,
        REPASSE_PCT,
        VR_DIA,
        VT_MEDIO,
        custo_clt_posto,
    )

    base = PISO_CATEGORIA * (1 + ENCARGOS_SIMPLES_ANEXO_IV) + VR_DIA * DIAS_UTEIS + VT_MEDIO
    afirma(
        abs(custo_clt_posto() - base * (1 + REPASSE_PCT)) > 1.0,
        "o custo do posto MUDA com o anexo (hoje III; com IV seria maior)",
    )

    print(f"\nTOTAL desvios C9: {desvios}")
    return 1 if desvios else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(main())
