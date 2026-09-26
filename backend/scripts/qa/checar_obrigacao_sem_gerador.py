#!/usr/bin/env python3
"""Obrigação que o regime EXIGE e que o sistema não sabe produzir.

## A regra que isto afirma

Quem cuida das obrigações fiscais hoje é a Portte Contábil, e o Jordan quer rescindir com
ela. No dia da rescisão, toda obrigação que a Portte produzia e o sistema não produz vira
**exposição legal com data marcada** — não uma tarefa pendente, uma multa com calendário.

Esta trava conta quantas são. Ela não pergunta «está entregue?»: pergunta **«este sistema
é capaz de gerar o arquivo?»**. As duas coisas são diferentes, e a segunda é a que decide
se dá para rescindir.

## Como mede, e por que não confia numa lista minha

A lista do que o regime exige NÃO é escrita aqui: vem de `ObligationsMonitorAgent`, que é
quem o calendário do ERP já usa. Duas listas da mesma coisa garantem que uma envelhece —
foi assim que o calendário passou meses devolvendo `previstos_pelo_regime: 0`.

O lado do «sabe produzir» é medido nas **rotas registradas no app**, não num inventário à
mão: se existe rota que gera o arquivo, ela está no `app.routes`. É por isso que esta trava
importa `main_production` em vez de ler `/openapi.json`, que seria mais leve — em produção
aquele caminho devolve 404 de propósito. Cada obrigação declara em
`PRODUTOR` o pedaço de caminho que a produz. Obrigação sem token declarado sai como
**«sem produtor declarado»** e conta como buraco — nunca como verde por omissão.

Medido em 26/09/2026, com a Eletrônica no Lucro Real e a Patrimonial no Simples:

    ECD                SPED Contábil        gera  POST /government/sped-contabil/gerar
    EFD_ICMS_IPI       SPED Fiscal          gera  POST /government/sped-fiscal/gerar
    EFD_CONTRIBUICOES  PIS/COFINS           NÃO   nenhuma rota
    ECF                Escrit. Fiscal       NÃO   nenhuma rota
    DIRF / RAIS                             NÃO   nenhuma rota
    PGDAS_D            Simples              NÃO   nenhuma rota
    DCTF                                    NÃO   só GET /dctfweb/status — consultar
                                                  não é produzir

São **6**, e a DCTF é a que quase escapou: a primeira versão desta trava aceitava
qualquer rota que contivesse o token, e `GET /dctfweb/status` a fazia parecer coberta.

## O que ele NÃO faz

Não gera nada e não diz que a obrigação está atrasada — isso é o calendário
(`GET /empresas/obrigacoes/calendario/grupo`). Aqui só se mede capacidade.

E uma capacidade que existe pode estar errada: o gerador da EFD ICMS/IPI existia e
declarava NOTA DE SERVIÇO como mercadoria até 25/09/2026. Quem afirma que o conteúdo está
certo é o oráculo (C4 para a ECD, C6 para a EFD ICMS/IPI); esta trava afirma só que existe
por onde produzir.

## Obrigação que ACABOU não é buraco

O ano entra na conta. Em 26/09/2026, montando esta lista, apareceram TRÊS declarações que
o molde do regime ainda mandava perseguir e que não existem mais para fatos de 2026 —
DIRF, RAIS e DCTF. Obrigação fantasma é pior que obrigação faltando: consome a atenção
que deveria ir para a que existe. Elas ficam DECLARADAS em
`ObligationsMonitorAgent.OBRIGACOES_EXTINTAS`, com a norma, e esta trava as imprime como
«fora da conta» em vez de sumir com elas em silêncio.

Linha canônica: `TOTAL: <n> obrigação(ões) exigida(s) sem gerador no sistema`.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import date

#: Como cada obrigação é PRODUZIDA. Chave = o `tipo` do `ObligationsMonitorAgent`.
#:
#:   "token"  → é arquivo/declaração que o sistema tem de produzir, e a prova é uma rota
#:              PRODUTORA (POST, ou caminho com gerar/transmitir/emitir/enviar) contendo
#:              o token. `GET .../status` NÃO conta: consultar não é produzir, e contar
#:              consulta como capacidade foi o primeiro erro desta trava — ela dava a
#:              DCTF como coberta por causa de `GET /dctfweb/status`.
#:   None     → não é arquivo que este sistema produz. Cada uma diz POR QUÊ, porque
#:              isenção sem motivo escrito é o mesmo que buraco escondido.
#:
#: Obrigação ausente deste mapa sai como «sem produtor declarado» e conta como buraco.
PRODUTOR: dict[str, str | None] = {
    "ECD": "sped-contabil",
    "EFD_ICMS_IPI": "sped-fiscal",
    "EFD_CONTRIBUICOES": "sped-contribuicoes",
    "ECF": "sped-ecf",
    "DCTF": "dctf",
    "DIRF": "dirf",
    "RAIS": "rais",
}

#: As que não são arquivo — com o motivo, que é o que separa isenção de omissão.
NAO_E_ARQUIVO = {
    "PGDAS_D": "declaração feita no portal do Simples Nacional; não há arquivo a gerar."
               " O que o sistema deve ao contribuinte é a RECEITA BRUTA por competência,"
               " para quem preenche o portal — e isso o DRE já dá",
    "IRPJ_CSLL_ESTIMATIVA": "DARF calculado e pago; não há arquivo a transmitir",
    "INSS_GPS": "guia paga no banco; o fato declaratório vai pelo eSocial/DCTFWeb",
    "ISS_AVULSO": "guia da prefeitura, emitida no portal da SEMEF",
    "DAS": "guia gerada no portal do Simples a partir do PGDAS-D",
    "FGTS_GUIA": "a DAE nasce no FGTS Digital a partir do eSocial; o dever do sistema é"
    " transmitir o evento, não gerar a guia",
}

#: O que faz de uma rota uma rota PRODUTORA.
_VERBOS_QUE_PRODUZEM = ("gerar", "transmitir", "emitir", "enviar", "exportar")


async def main() -> int:
    try:
        from sqlalchemy import text  # noqa: PLC0415

        from core.database import async_session_factory  # noqa: PLC0415
        from main_production import app  # noqa: PLC0415
        from modules.empresas.agents.obligations_monitor import (  # noqa: PLC0415
            ObligationsMonitorAgent as Ag,
        )
    except ModuleNotFoundError as e:
        print(f"RECUSO: roda DENTRO do container (precisa do app e do banco) — {e}")
        return 2

    caminhos = {getattr(r, "path", "") for r in app.routes}

    async with async_session_factory() as db:
        empresas = (
            await db.execute(
                text("SELECT razao_social, regime_tributario::text FROM empresas WHERE status = 'ativa' ORDER BY 1")
            )
        ).all()

    # O ANO importa: obrigação extinta não é buraco, é obrigação que acabou. A lista de
    # extintas mora no próprio monitor, com a norma — aqui só se respeita.
    ano = date.today().year
    por_regime = {
        "lucro_real": [
            x for x in (
                list(Ag.OBRIGACOES_LUCRO_REAL)
                + [(t, d, f, "anual", None) for t, d, _m, _dia, f in Ag.OBRIGACOES_LUCRO_REAL_ANUAIS]
            ) if not Ag.extinta_em(x[0], ano)
        ],
        "simples_nacional": [x for x in Ag.OBRIGACOES_SIMPLES if not Ag.extinta_em(x[0], ano)],
    }
    extintas = [
        (t, *Ag.extinta_em(t, ano))
        for t in sorted(Ag.OBRIGACOES_EXTINTAS)
        if Ag.extinta_em(t, ano)
    ]

    def produz(tipo: str) -> tuple[bool, str]:
        if tipo in NAO_E_ARQUIVO:
            return True, NAO_E_ARQUIVO[tipo]
        if tipo not in PRODUTOR:
            return False, "sem produtor declarado nesta trava"
        token = PRODUTOR[tipo]
        com_token = sorted(p for p in caminhos if token in p)
        produtoras = [p for p in com_token if any(v in p for v in _VERBOS_QUE_PRODUZEM)]
        if produtoras:
            return True, produtoras[0]
        if com_token:
            return False, f"só consulta: {com_token[0]} — consultar não é produzir"
        return False, f"nenhuma rota com «{token}»"

    buracos = []
    print(f"rotas registradas no app: {len(caminhos)}")
    # Dizer o que SAIU da conta é tão importante quanto o que ficou: sem isto, um total
    # que cai parece progresso e pode ser apenas a régua encolhendo.
    for t, norma, subst in extintas:
        print(f"   fora da conta: {t:<8} {norma} → {subst}")
    print()
    for razao, regime in empresas:
        lista = por_regime.get((regime or "").lower())
        if lista is None:
            print(f"{razao} — regime «{regime}» sem molde conhecido, NÃO medido")
            buracos.append((razao, "(regime)", f"regime «{regime}» sem molde"))
            continue
        print(f"{razao} · {regime} — {len(lista)} obrigação(ões) exigida(s):")
        for tipo, desc, *_r in lista:
            ok, onde = produz(tipo)
            print(f"   {'gera ' if ok else 'NÃO  '} {tipo:<22} {desc[:44]:<44} {onde}")
            if not ok:
                buracos.append((razao, tipo, desc))
        print()

    if buracos:
        print(f"SEM GERADOR — {len(buracos)}:")
        for razao, tipo, desc in buracos:
            print(f"   {razao[:28]:<28} {tipo:<22} {desc[:50]}")
        print()
        print("   → No dia da rescisão com a Portte, cada uma destas vira exposição legal")
        print("     com data marcada. Existir rota não garante conteúdo certo: o gerador da")
        print("     EFD ICMS/IPI existia e declarava nota de SERVIÇO como mercadoria até")
        print("     25/09/2026. Quem afirma o conteúdo é o oráculo, não esta trava.")

    print(f"\nTOTAL: {len(buracos)} obrigação(ões) exigida(s) sem gerador no sistema")
    return 1 if buracos else 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    raise SystemExit(asyncio.run(main()))
