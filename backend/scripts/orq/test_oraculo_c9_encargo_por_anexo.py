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
    from modules.financial.controllers.precificacao_controller import (  # noqa: PLC0415  # noqa: PLC0415
        DIAS_UTEIS,
        EMPRESA_MAO_DE_OBRA,
        PISO_CATEGORIA,
        REPASSE_PCT,
        VR_DIA,
        VT_MEDIO,
        custo_clt_posto,
    )

    # Esta asserção foi REESCRITA em 27/09/2026. A versão original dizia «o custo difere da
    # conta do Anexo IV (hoje III; com IV seria maior)» — ela codificava o ESTADO do cadastro,
    # não a regra. Quando o cadastro da Patrimonial foi corrigido de III para IV (a guia do
    # DAS de 08/2026 não tem o código 1006, logo a CPP está fora do DAS, logo é Anexo IV), o
    # oráculo passou a REPROVAR o estado certo. Régua que envelhece com o dado não é régua.
    #
    # A regra que o autor queria: o custo do posto ACOMPANHA o anexo real da empresa, seja
    # ele qual for. É isso que pega o defeito de verdade — uma constante cravada que ignora
    # o cadastro. Se um dia o anexo mudar de novo, esta linha continua certa sozinha.
    from modules.financial.services.encargos import encargo_pct_da_empresa as _pct  # noqa: PLC0415

    esperado = (PISO_CATEGORIA * (1 + _pct(EMPRESA_MAO_DE_OBRA)) + VR_DIA * DIAS_UTEIS + VT_MEDIO) * (1 + REPASSE_PCT)
    afirma(
        abs(custo_clt_posto() - esperado) < 0.01,
        f"o custo do posto segue o anexo do cadastro: R$ {custo_clt_posto():,.2f} "
        f"= R$ {esperado:,.2f} (encargo {_pct(EMPRESA_MAO_DE_OBRA):.2%})",
    )
    # E a diferença entre os dois anexos não é decorativa: são 23 pontos de encargo sobre o
    # piso. Se algum dia der zero, alguém igualou as constantes e apagou a distinção.
    delta = PISO_CATEGORIA * (ENCARGOS_SIMPLES_ANEXO_IV - ENCARGOS_SIMPLES_ANEXO_III)
    afirma(delta > 300.0, f"trocar III por IV move R$ {delta:,.2f} por posto/mês")

    # ─── a cotação CCT diz em voz alta quando os parâmetros não são dela ────
    #
    # `pricing_cct` soma os sete encargos de `crm_pricing_params`, que é UMA tabela para as
    # DUAS empresas e guarda o conjunto de Lucro Real (0,6124). A empresa que emprega os
    # agentes é Simples Anexo IV (0,5544). Medido em 27/09 num AGP de piso R$ 1.670: a
    # cotação sai R$ 5.820,81 onde os parâmetros certos dariam R$ 5.294,95 — 9,0% acima.
    #
    # O número NÃO foi corrigido (a metade dos tributos depende do RBT12, que está nulo e
    # cujas guias discordam). O que não pode voltar é o SILÊNCIO: enquanto a tabela
    # divergir, a ficha tem de dizer isso. Se um dia a tabela passar a bater, o aviso some
    # sozinho — e esta asserção continua certa, porque afirma a condicional inteira.
    import asyncio  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415
    from modules.crm.services.pricing_cct import carregar_params  # noqa: PLC0415

    async def _ficha():
        async with async_session_factory() as db:
            return await carregar_params(db)

    prm = asyncio.run(_ficha())
    # Desde 27/09 (tarde) o encargo JÁ vem da empresa; o que decide o aviso são os TRIBUTOS:
    # sem `empresas.rbt12`, `resolver()` recusa, `_tributos_empresa` é None e a ficha avisa;
    # com RBT12 em dia, tudo é da empresa e o aviso é None. A asserção afirma a condicional
    # inteira — no dia em que o PGDAS-D preencher o RBT12, ela continua certa sem edição.
    falta_algo = prm.get("_encargo_empresa") is None or prm.get("_tributos_empresa") is None
    aviso = prm.get("_regime_aviso") or ""
    afirma(
        (falta_algo == bool(aviso)) or ("atualizado em" in aviso),
        f"a cotação avisa exatamente quando algum parâmetro não é da empresa "
        f"(encargo={prm.get('_encargo_empresa')}, tributos={prm.get('_tributos_empresa')}, avisa={bool(aviso)})",
    )
    # E com os tributos da empresa em mãos, o motor os USA: com alíquota efetiva 9,19% o AGP
    # de piso tem de dar o número da conta feita à mão em 27/09.
    from modules.crm.services.pricing_cct import calcular  # noqa: PLC0415

    sim = dict(prm)
    sim.update({"_encargo_empresa": 0.5544, "_tributos_empresa": 0.0919, "_regime_aviso": None})
    r = calcular(1670.0, 30, {"margem": 0.15}, sim)
    afirma(
        abs(r["preco"] - 5294.95) < 0.02,
        f"com RBT12 (efetiva 9,19%) o AGP de piso sai R$ {r['preco']:,.2f} (esperado 5.294,95)",
    )
    afirma(r["regime_aviso"] is None, "e a ficha sai sem aviso quando tudo é da empresa")

    print(f"\nTOTAL desvios C9: {desvios}")
    return 1 if desvios else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(main())
