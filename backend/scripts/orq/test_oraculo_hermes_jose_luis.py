"""A ponte Hermes↔José Luís está viva, cai de pé quando o Hermes some, e não abriu buraco.

Por que existe. Em 25/09/2026 o dono ordenou integração total do Hermes ao José Luís, e a
medição achou o que a ordem não podia saber: **o gateway do Hermes ignora o campo `tools`**.
Então a ponte NÃO é uma troca de cliente de LLM — é (1) casos com desfecho, (2) lições só do
que deu certo, (3) o Hermes como socorro do turno que morreu. Três coisas que falham em
silêncio de três jeitos diferentes, e nenhuma delas quebra nada visível ao falhar:

  · o socorro pode ser movido para DEPOIS dos filtros de saída — e aí vira uma porta de saída
    sem parede, que é pior que não existir;
  · o `direction='cas'` pode não caber na coluna (`varchar(3)`), e daí NADA grava, para sempre,
    sem um erro que alguém leia;
  · o interruptor pode ficar decorativo, e o agente passa a ser influenciado por uma base que
    o dono acha que está desligada.

⭐ Afirma a REGRA, não a fotografia:

- não fixa quantos casos existem (a base começa vazia e cresce) — afirma que base vazia
  devolve `None` e que só `resolveu` alimenta few-shot;
- não fixa o modelo que o Hermes usa (é o `default` do config dele) — afirma que ele RESPONDE;
- não fixa a posição em linha do socorro — afirma a ORDEM dele contra os filtros, que é o que
  importa.

⚠️ Toda recusa aqui tem a irmã de caminho feliz, senão é meia trava e vira o oráculo cúmplice:
`off` recusa **com o Hermes de pé** (prova que o interruptor manda, não a rede), e o socorro
responde **no mesmo processo** (prova que a recusa não era incapacidade). O fallback mede as
duas direções: com o Hermes fora, `perguntar_hermes` LEVANTA e `socorro` devolve `None` —
se só o segundo fosse testado, um `return None` no topo da função passaria verde.

Como rodar (contêiner EFÊMERO — nunca `docker cp` no backend com campanha no ar):

    IMG=$(docker inspect -f '{{.Image}}' conecta-pro-backend)
    DBU=$(docker exec conecta-pro-backend printenv DATABASE_URL)   # o .env aponta localhost
    docker run --rm --entrypoint python3 --network conecta-pro_conecta-pro-network \
      --env-file /opt/conecta-pro/.env -e "DATABASE_URL=$DBU" \
      -v /opt/conecta-pro/backend/modules:/app/modules:ro \
      -v /opt/conecta-pro/backend/scripts:/app/scripts:ro \
      -e PYTHONPATH=/app "$IMG" /app/scripts/orq/test_oraculo_hermes_jose_luis.py

⚠️ `DATABASE_URL` tem de vir do CONTÊINER, não do `.env` do repositório: o do repositório diz
`localhost`, que dentro do efêmero é o próprio efêmero, e o oráculo morre em "Connect call
failed" parecendo defeito do código. Efêmero não herda a rede nem os volumes de produção.

⚠️ O que este oráculo NÃO prova, e é honesto dizer: o INSERT do caso não é executado (proibido
escrever no banco de produção). O que se prova é que as colunas existem e que os valores CABEM
nelas — que é o defeito que mataria a gravação inteira. A primeira gravação real só acontece
quando alguém puser `JOSE_LUIS_VIA_HERMES=aprender`.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

#: O padrão do produto é OFF. Fixado ANTES de qualquer import para o estado default ser o
#: medido, e não o que o `.env` do contêiner por acaso tiver.
os.environ.pop("JOSE_LUIS_VIA_HERMES", None)

_ROWS = [
    ("in", "Bom dia, preciso de portaria 24h para um condomínio de 47 unidades na Ponta Negra"),
    ("out", "Bom dia! Sou o José Luís, da Conecta Mais."),
    ("in", "Oi"),
]


async def main() -> None:
    # ── (a) o sistema SOBE com a ponte dentro ─────────────────────────────────
    import main_production  # noqa: PLC0415

    rotas = len(main_production.app.routes)
    assert rotas > 1500, f"só {rotas} rotas — algum import quebrou e o backend subiu manco"
    print(f"OK import main_production ({rotas} rotas)")

    from modules.integrations.connectors.whatsapp import agent_service as ag  # noqa: PLC0415
    from modules.integrations.connectors.whatsapp import hermes_ponte as hp  # noqa: PLC0415

    # a lógica pura (desfecho, relevância, interruptor) tem a checagem no próprio módulo
    hp.demo()
    os.environ.pop("JOSE_LUIS_VIA_HERMES", None)

    # ── PADRÃO É INERTE ───────────────────────────────────────────────────────
    assert hp.modo() == "off" and not hp.grava() and not hp.influencia(), (
        "sem JOSE_LUIS_VIA_HERMES o padrão TEM de ser inerte — o dono não pediu para o "
        "agente mudar de comportamento no próximo restart")
    assert await hp.licoes(1, _ROWS) is None, "modo off injetou lição no prompt"
    assert await hp.socorro(1, _ROWS) is None, "modo off chamou o Hermes"
    await hp.registrar_caso(1, _ROWS, "resposta qualquer")  # não deve nem tocar no banco
    print("OK padrão off é inerte (lições, socorro e gravação todos calados)")

    # ── (d) NENHUMA PAREDE REMOVIDA ───────────────────────────────────────────
    # ⚠️ procura a CHAMADA (`nome(`), não a menção: a 1ª versão disto achou o nome do filtro
    # dentro do meu próprio comentário, 3 linhas ACIMA da chamada, e acusou o socorro de rodar
    # depois da parede. Lógica certa, observação errada — a trava mediu o texto, não o código.
    fonte = inspect.getsource(ag.gerar_resposta)
    i_socorro = fonte.find("hermes_ponte.socorro(")
    assert i_socorro > 0, "o socorro do Hermes desapareceu de gerar_resposta"
    for parede in ("_tirar_puxa_saco(", "_sem_fabricar_acao(", "_rascunho_nao_e_envio("):
        i_parede = fonte.find(parede)
        assert i_parede > 0, f"filtro mecânico de saída {parede} SUMIU de gerar_resposta"
        assert i_socorro < i_parede, (
            f"o socorro do Hermes passou a rodar DEPOIS de {parede}: o texto do Hermes deixou "
            f"de passar pela parede e virou porta de saída sem trava")
    print("OK socorro do Hermes roda ANTES dos 3 filtros mecânicos de saída")

    # gate de grupo: `observar` = o agente NÃO é chamado (parede no webhook, não no prompt)
    from modules.integrations.connectors.whatsapp import grupos as grp  # noqa: PLC0415

    assert "observar" in grp.MODOS and callable(grp.deve_calar), \
        "o gate de grupo (modo observar / deve_calar) não está mais no lugar"
    # a conferência de chave PIX continua no contexto do funcionário (caminho de dinheiro)
    assert "CONFERÊNCIA DE CHAVE PIX" in inspect.getsource(ag._contexto_funcionario), \
        "o bloco CONFERÊNCIA DE CHAVE PIX saiu de _contexto_funcionario"
    # e a ponte não é um caminho de dinheiro: nada de PIX/pagamento no módulo novo
    fonte_ponte = inspect.getsource(hp)
    assert not re.search(r"(ordem_pagamento|pix_confirma|integrations\.(banking|inter))", fonte_ponte), \
        "a ponte tocou em caminho de dinheiro — ela não tem o que fazer lá"
    print("OK paredes no lugar (gate de grupo, PIX do funcionário, ponte fora do dinheiro)")

    # ── A COLUNA CABE O VALOR (o defeito que mataria a gravação em silêncio) ──
    from core.database import async_session_factory  # noqa: PLC0415
    from sqlalchemy import text  # noqa: PLC0415

    async with async_session_factory() as db:
        tipos = dict(
            (
                await db.execute(
                    text(
                        "SELECT column_name, coalesce(character_maximum_length, 0) "
                        "FROM information_schema.columns WHERE table_name='cwi_message_log'"
                    )
                )
            ).all()
        )
        for col in ("direction", "status", "content", "phone_canonical", "chatwoot_conversation_id"):
            assert col in tipos, f"cwi_message_log não tem a coluna {col} — o INSERT do caso falharia"
        assert tipos["direction"] >= len("cas"), \
            f"direction é varchar({tipos['direction']}): 'cas' não cabe e NADA gravaria"
        maior = max(("resolveu", "falhou", "humano_assumiu", "seguiu", "indefinido"), key=len)
        assert tipos["status"] >= len(maior), \
            f"status é varchar({tipos['status']}) e o desfecho {maior!r} não cabe"
        print(f"OK cwi_message_log aceita direction='cas' (varchar {tipos['direction']}) "
              f"e desfecho {maior!r} (status varchar {tipos['status']})")

        # o molde que a ponte reusa está VIVO (mem/drf/gld/trf): se ninguém mais usasse,
        # reusar o molde seria copiar um costume morto
        usados = dict((await db.execute(text(
            "SELECT direction, count(*) FROM cwi_message_log GROUP BY 1"))).all())
        assert {"mem", "drf"} <= set(usados), (
            f"o molde direction=<estado de agente> não está mais em uso ({sorted(usados)}) — "
            f"reveja se 'cas' ainda é o lugar certo do caso")
        print(f"OK molde reusado está vivo: { {k: v for k, v in usados.items() if k not in ('in', 'out')} }")

    # nenhuma consulta do backend exclui direction por negação (é o que faz 'cas' ser seguro),
    # e o CONTROLE: a consulta do prompt filtra por lista branca — se este grep não achasse
    # NADA, ele estaria medindo a si mesmo e não o código
    raiz = "/app/modules"
    negativos, brancas = [], 0
    for base, _, arqs in os.walk(raiz):
        for a in arqs:
            if not a.endswith(".py"):
                continue
            p = os.path.join(base, a)
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    src = fh.read()
            except OSError:
                continue
            if re.search(r"direction\s*(!=|<>)\s*'|direction\s+NOT\s+IN", src, re.IGNORECASE):
                negativos.append(p)
            brancas += len(re.findall(r"direction\s+IN\s*\(", src, re.IGNORECASE))
    assert brancas > 0, "o grep não achou nenhum `direction IN (...)` — ele está medindo o regex, não o código"
    assert not negativos, (
        f"apareceu filtro NEGATIVO de direction em {negativos} — um valor novo ('cas') passa "
        f"a ser incluído onde ninguém revisou")
    print(f"OK {brancas} filtros de direction são lista BRANCA e 0 são por negação")

    # ── (b) O CAMINHO VIA HERMES RESPONDE ─────────────────────────────────────
    from modules.ai.conversation.services import hermes_client as hc  # noqa: PLC0415

    url_boa = hc.HERMES_URL
    hc._cache_disponivel, hc._cache_ts = None, 0.0
    de_pe = await hc.hermes_disponivel()
    assert de_pe, f"Hermes não respondeu em {url_boa} — sem ele não há o que provar aqui"

    # a IRMÃ da recusa: com o Hermes DE PÉ, `off` continua calado. Se passasse, a recusa
    # anterior era falta de rede, não o interruptor.
    assert await hp.socorro(1, _ROWS) is None, \
        "com o Hermes de pé o modo off respondeu — o interruptor é decorativo"

    os.environ["JOSE_LUIS_VIA_HERMES"] = "on"
    resp = await hp.socorro(1, _ROWS, timeout=120.0)
    assert resp and len(resp.strip()) > 20, f"socorro via Hermes não respondeu: {resp!r}"
    assert "system prompt" not in resp.lower() and "REGRAS QUE NÃO" not in resp, \
        "o Hermes vazou as instruções internas na resposta"
    print(f"OK socorro via Hermes respondeu {len(resp)} chars: {resp[:110]!r}")

    # modo `aprender` grava mas NÃO influencia — é a promessa feita ao dono
    os.environ["JOSE_LUIS_VIA_HERMES"] = "aprender"
    assert await hp.socorro(1, _ROWS) is None and await hp.licoes(1, _ROWS) is None, \
        "modo aprender mudou a resposta — ele foi feito para encher a base com risco ZERO"
    print("OK modo aprender grava e NÃO influencia a resposta")

    # ── (c) FALLBACK: Hermes fora do ar → o José Luís NÃO fica mudo ───────────
    os.environ["JOSE_LUIS_VIA_HERMES"] = "on"
    hc.HERMES_URL = "http://127.0.0.1:9/nada"  # porta 9 (discard): conexão recusada na hora
    hc._cache_disponivel, hc._cache_ts = None, 0.0
    try:
        assert await hc.hermes_disponivel() is False, "a saúde do Hermes deu OK apontando para o vazio"
        # direção 1: o cliente LEVANTA (senão o None abaixo não prova nada)
        levantou = False
        try:
            await hc.perguntar_hermes([{"role": "user", "content": "oi"}], "teste", timeout=3.0)
        except hc.HermesIndisponivel:
            levantou = True
        assert levantou, "perguntar_hermes não levantou com o Hermes fora — a falha passaria calada"
        # direção 2: a ponte ENGOLE e devolve None, e o agente segue no caminho de hoje
        assert await hp.socorro(1, _ROWS, timeout=3.0) is None, \
            "socorro não degradou para None com o Hermes fora — o turno morreria na exceção"
        print("OK Hermes fora do ar: perguntar_hermes LEVANTA, a ponte devolve None, "
              "o agente cai no caminho atual")
    finally:
        hc.HERMES_URL = url_boa
        hc._cache_disponivel, hc._cache_ts = None, 0.0
        os.environ.pop("JOSE_LUIS_VIA_HERMES", None)

    # e a gravação nunca derruba o turno, mesmo com o banco impossível
    os.environ["JOSE_LUIS_VIA_HERMES"] = "aprender"
    import core.database as cdb  # noqa: PLC0415

    real = cdb.async_session_factory

    def _explode(*_a, **_k):
        raise RuntimeError("banco fora (simulado)")

    try:
        cdb.async_session_factory = _explode
        await hp.registrar_caso(99999999, _ROWS, "resposta do agente")  # não pode levantar
        print("OK registrar_caso engole falha de banco (o cliente recebe a resposta de qualquer jeito)")
    finally:
        cdb.async_session_factory = real
        os.environ.pop("JOSE_LUIS_VIA_HERMES", None)

    print("TEST oraculo_hermes_jose_luis PASS")


if __name__ == "__main__":
    asyncio.run(main())
