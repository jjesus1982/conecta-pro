"""Prova que a casa nunca mais manda ninguém instalar app de ponto.

🔴 O QUE ACONTECEU EM 26/09/2026: o José Luís disse ao Wisley, contratado no dia anterior,
*"É o Tangerino, Wisley. No iPhone não precisa de link — abre a App Store e busca Tangerino"*.
O Tangerino está DESLIGADO desde 13/09 — medido: 223 batidas até aquele dia, ZERO depois. O
rapaz ia baixar um app morto e continuar sem registrar hora.

⭐ E A CAUSA NÃO FOI O MODELO: foi o que a casa REPETIA. O lembrete diário dizia *"Bata o ponto
pelo app do Conecta PRO"* — saindo para todo mundo, todos os dias. Jordan: *"não usamos app
ainda, usamos o link do sistema do portal do funcionário no navegador"*. Sem um fato melhor no
contexto, o modelo completou a lacuna com o único app de ponto do histórico.

**Faltar informação não produz silêncio no modelo — produz invenção plausível.** Por isso este
oráculo afirma DUAS coisas, e a segunda é a que faltava:

  1. os textos automáticos não prometem app                    (a mentira que ensinava)
  2. o contexto do agente traz a NEGATIVA EXPLÍCITA            (a lacuna que ele preenchia)

⚠️ Afirma a REGRA, não a fotografia: não fixa o texto do guia nem o nome do app morto numa
lista. Verifica que existe UMA fonte (`guia_primeiro_acesso`) e que ela chega ao agente.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

falhas: list[str] = []


async def main() -> None:
    from modules.people_management.ponto.guia_primeiro_acesso import (
        COMO_BATER_CURTO,
        NUNCA_DIZER,
        URL_PORTAL,
        guia,
    )

    # 1 — a fonte única existe e aponta para NAVEGADOR, não loja de app
    if "erp.conectamais.pro" not in URL_PORTAL:
        falhas.append(f"URL_PORTAL não aponta para o portal: {URL_PORTAL!r}")
    g = guia("FULANO DE TAL", "fulano@exemplo.com")
    for exigido, o_que in (("navegador", "o caminho real"),
                           ("Localização", "a permissão de GPS, sem ela a batida não fecha"),
                           ("Câmera", "a permissão de foto, sem ela a batida não fecha"),
                           # 🔴 26/09/2026 — o passo do ROSTO. A THAYNÁ perguntou sozinha
                           # ("tenho que cadastrar meu rosto?") e a medição fechou o caso: das 25
                           # batidas `mobile` daquele dia, 25 com `facial_match` e ZERO sem. É
                           # obrigatório, e 7 ativos estavam sem `face_enrolled_at` — três com 18
                           # turnos futuros. Sem esta linha o guia leva a pessoa até a última
                           # tela e a deixa lá.
                           ("Cadastrar meu rosto", "o cadastro facial, sem ele a batida não passa"),
                           ("fulano@exemplo.com", "o e-mail da pessoa")):
        if exigido.lower() not in g.lower():
            falhas.append(f"o guia não menciona {o_que} ({exigido!r})")
    if "fulano de tal" in g.lower():
        falhas.append("o guia usa o nome inteiro em vez do primeiro nome — soa a robô")

    # ⚠️ A ORDEM É PARTE DA CORREÇÃO, não enfeite: permissão → rosto → batida. Minha primeira
    # versão punha "bater o ponto" ANTES do cadastro do rosto, e a pessoa chegava na batida sem
    # poder concluir. Passo fora de ordem é passo que trava, e um teste que só procura palavras
    # passaria verde com a ordem errada.
    pos_rosto = g.find("Cadastrar meu rosto")
    pos_bater = g.find("*6. Bater o ponto*")
    if pos_rosto < 0 or pos_bater < 0:
        falhas.append("não achei os passos de rosto e de batida para conferir a ORDEM")
    elif pos_rosto > pos_bater:
        falhas.append("o guia manda BATER antes de cadastrar o rosto — a pessoa trava na última "
                      "tela sem entender por quê")
    else:
        print("  ok  ordem certa: permissões → rosto → batida")
    if not falhas:
        print(f"  ok  guia com {len(g.splitlines())} linhas: navegador, login, permissões")

    # 2 — os textos AUTOMÁTICOS de ponto não prometem app. Este é o texto que sai 1.500 vezes.
    from modules.operacional.lembrete_ponto import ETAPAS

    for delta, txt in ETAPAS.items():
        t = txt.lower()
        if "pelo app" in t or "baixe o app" in t or "app store" in t or "play store" in t:
            falhas.append(f"lembrete de ponto (delta={delta}) promete APP: {txt[:70]!r}")
    if not any("pelo app" in v.lower() for v in ETAPAS.values()):
        print(f"  ok  {len(ETAPAS)} etapa(s) de lembrete, nenhuma prometendo app")

    # 3 — ⭐ A NEGATIVA CHEGA AO AGENTE. É a asserção que o episódio do Tangerino pede: sem ela
    #     o modelo preenche a lacuna sozinho, e preencheu.
    from modules.integrations.connectors.whatsapp import agent_service as _ag

    class _Ident:
        nome = "ORACULO TESTE"
        tratamento = None
        cargo = "AGENTE DE PORTARIA"
        posto = "Prime Arena"
        condominio = None
        employee_id = None
        tipo = "funcionario"

    ctx = await _ag._contexto_funcionario(_Ident())
    if NUNCA_DIZER[:40] not in ctx:
        falhas.append("o contexto do agente NÃO traz a proibição de recomendar app — a lacuna "
                      "que produziu o conselho do Tangerino está aberta de novo")
    elif COMO_BATER_CURTO not in ctx:
        falhas.append("o contexto proíbe o app mas não diz o caminho CERTO — proibição sem "
                      "alternativa deixa o modelo sem resposta para dar")
    else:
        print("  ok  o contexto do agente traz a proibição E o caminho certo")

    # 4 — CONTROLE: a régua PEGA o texto errado? Sem isto ela pode estar sempre verde.
    if "pelo app do conecta pro" in COMO_BATER_CURTO.lower():
        falhas.append("controle falhou: a própria fonte única promete app")
    else:
        print("  ok  controle: a régua reprovaria 'pelo app do Conecta PRO' se voltasse")

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"\nTEST guia_ponto_sem_app FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST guia_ponto_sem_app PASS")


if __name__ == "__main__":
    asyncio.run(main())
