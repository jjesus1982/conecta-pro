"""Prova que o vigia de postos AVISA o problema novo e CALA no repetido.

POR QUE EXISTE — 26/09/2026. O Jordan, às 07:07 de um sábado, teve que marcar o José Luís para
saber quem havia batido. Palavras dele: *"preciso saber assim que houver um problema pra eu
resolver, e não depois de ele ter acontecido"*. O diagnóstico existia (dez veredictos em
`situacao_do_turno`); faltava OLHO automático — e o único que havia era o relatório das 08:30,
depois das trocas de 06h e 07h.

Este oráculo afirma as cinco coisas que, se quebrarem, matam o vigia em SILÊNCIO. Cada parede
vem com a irmã de caminho feliz, porque trava que só sabe recusar fica 100% verde sobre
capacidade morta — foi o defeito do oráculo cúmplice que eu escrevi em agosto.

  1. o beat existe E aponta para fila que EXISTE  ← matou o espelho do eSocial por 3 meses
  2. carência: quem entrou agora não é problema · quem entrou há 1h é    (par)
  3. turno noturno em curso NÃO é futuro                                 (o erro que eu repeti)
  4. veredito repetido não gera 2ª mensagem · veredito novo gera         (par)
  5. dry run NÃO grava — gravar sem publicar QUEIMA o aviso para sempre

⚠️ Afirma a REGRA, não a fotografia: nenhum número de postos, nenhuma pessoa, nenhum veredito
de hoje. A escala muda toda semana e o Euler vai sair do AUSENTE_PROLONGADO quando o DP lançar
o afastamento — um oráculo preso ao retrato de hoje fica vermelho por mudança legítima.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.integrations.connectors.whatsapp import vigia  # noqa: E402

falhas: list[str] = []


def _ok(msg: str) -> None:
    print(f"  ok  {msg}")


def _erro(msg: str) -> None:
    falhas.append(msg)
    print(f"  ❌ {msg}")


def _1_beat_e_fila() -> None:
    """O beat está agendado e a fila dele EXISTE.

    ⭐ O defeito que este teste impede não é teórico: o beat `esocial-espelho-sync` ficou
    agendado 3 meses para uma task que não existia, e o de `drenar_mensagens_agendadas` nasceu
    apontando para a fila `whatsapp`, que nunca existiu. Nos dois casos o Celery aceita calado.
    """
    from celery_app import app

    beats = {v["task"] for v in app.conf.beat_schedule.values()}
    if "whatsapp.vigiar_postos" not in beats:
        return _erro("beat do vigia NÃO está no beat_schedule — ninguém vai olhar os postos")

    filas = {q.name for q in app.conf.task_queues}
    destino = (app.conf.task_routes or {}).get("whatsapp.vigiar_postos", {}).get("queue")
    if not destino:
        return _erro("`whatsapp.vigiar_postos` sem roteamento — vai para a fila default")
    if destino not in filas:
        return _erro(f"vigia roteado para fila '{destino}' que NÃO EXISTE "
                     f"(filas reais: {sorted(filas)}) — worker responderia NotRegistered")
    # ⚠️ NÃO basta olhar `app.tasks` num import nu: `include=` carrega PREGUIÇOSAMENTE, e
    # `turno_fechar_cobertura` e `drenar_mensagens_agendadas` — que eu vi EXECUTANDO no worker —
    # também aparecem ausentes. Minha primeira versão desta asserção reprovava código que
    # funciona: lógica certa, OBSERVAÇÃO errada, a família de defeito que mais reincide aqui.
    #
    # O que o worker faz de verdade é importar o módulo de `include=` e aí registrar o nome.
    # Então a pergunta certa tem duas partes: o módulo está em `include=`, e importá-lo
    # REGISTRA o nome?
    mod = "modules.integrations.connectors.whatsapp.tasks"
    if mod not in (app.conf.include or ()):
        return _erro(f"'{mod}' fora de `include=` — o worker nunca carrega a task")
    __import__(mod)
    if "whatsapp.vigiar_postos" not in app.tasks:
        return _erro("importar o módulo NÃO registra `whatsapp.vigiar_postos` — o beat "
                     "enfileira e o worker responde NotRegistered num log que ninguém lê")
    _ok(f"beat agendado, fila '{destino}' existe, import registra a task")

    # CONTROLE de caminho feliz: se este teste passasse com qualquer nome, não valeria nada.
    if (app.conf.task_routes or {}).get("whatsapp.nome_que_nao_existe"):
        _erro("controle falhou: roteamento responde para task inventada")


def _2_carencia() -> None:
    """Quem acabou de entrar não é problema do dono; quem entrou há 1h é.

    Sem a carência o vigia avisaria o Jordan de gente atravessando o portão — e o José Luís JÁ
    cobra a pessoa nos +10 e +25 minutos. O vigia existe para o caso em que a cobrança falhou.
    """
    agora_cedo = vigia._passou_a_carencia({"status": "SEM_BATIDA", "_hora_turno": "08:00:00"},
                                          "08:05")
    agora_tarde = vigia._passou_a_carencia({"status": "SEM_BATIDA", "_hora_turno": "07:00:00"},
                                           "08:05")
    if agora_cedo:
        _erro("carência furada: turno de 5 minutos atrás já vira aviso no grupo")
    elif not agora_tarde:
        _erro("carência travada: turno de 65 minutos atrás NÃO vira aviso — o vigia emudeceu")
    else:
        _ok("carência: +5min cala, +65min avisa")

    # estrutural NÃO espera: não se resolve com lembrete, precisa de decisão humana
    if not vigia._passou_a_carencia({"status": "ESCALADO_SEM_VINCULO",
                                     "_hora_turno": "08:00:00"}, "08:01"):
        _erro("ESCALADO_SEM_VINCULO esperando carência — posto coberto por demitido é urgente")
    else:
        _ok("veredito estrutural dispara na hora, sem carência")


def _3_noturno() -> None:
    """Turno das 19:00 visto à 01:00 está EM CURSO, não no futuro.

    ⚠️ Este é o erro que eu cometi em 25/09: li 29 turnos com 5 batidas como 17% de cobertura,
    e o número era artefato de contar turnos que não tinham começado. A aritmética ingênua dá
    -1080 minutos e o turno noturno pareceria futuro para sempre — o posto da madrugada nunca
    seria vigiado.
    """
    if not vigia._passou_a_carencia({"status": "SEM_BATIDA", "_hora_turno": "19:00:00"}, "01:00"):
        _erro("turno noturno em curso lido como FUTURO — madrugada fica sem vigia")
    elif vigia._passou_a_carencia({"status": "SEM_BATIDA", "_hora_turno": "19:00:00"}, "19:10"):
        _erro("turno de 10 minutos atrás já avisa — a correção da meia-noite abriu a carência")
    else:
        _ok("meia-noite: 19:00 visto à 01:00 avisa, visto às 19:10 cala")


async def _4_nao_repete(db) -> None:
    """Veredito já avisado não gera 2ª mensagem; veredito novo gera.

    ⭐ O par importa. Uma trava que só sabe calar produziria silêncio total, e silêncio total
    é indistinguível de "está tudo bem" — foi assim que a fila `ged` viveu sem consumidor.
    """
    alvo = {"status": "SEM_BATIDA", "_hora_turno": "23:59:00", "posto": "__ORACULO__",
            "_employee_id": None, "previsto": "23:59–23:59", "quem": "teste"}
    try:
        # 1ª vez: é novidade
        novos = await vigia._novidades(db, [alvo])
        if len(novos) != 1:
            _erro("veredito inédito NÃO foi reconhecido como novo — o vigia nasceria mudo")
            return
        await db.execute(text("""
            INSERT INTO wa_vigia_avisos (dia, employee_id, posto, hora_turno, veredito)
            VALUES (current_date, NULL, :p, CAST(CAST(:h AS text) AS time), :v)
            ON CONFLICT DO NOTHING"""),
            {"p": alvo["posto"], "h": alvo["_hora_turno"], "v": alvo["status"]})
        await db.commit()

        # 2ª vez: mesma coisa, tem de calar
        if await vigia._novidades(db, [alvo]):
            _erro("veredito JÁ avisado voltou como novo — o grupo apitaria a cada 10 minutos")
            return

        # e um veredito DIFERENTE no mesmo turno ainda passa (piorou = notícia)
        pior = {**alvo, "status": "ESCALADO_SEM_VINCULO"}
        if not await vigia._novidades(db, [pior]):
            _erro("veredito NOVO no mesmo turno foi engolido — piora ficaria invisível")
            return
        _ok("repetido cala, mudança de veredito avisa")
    finally:
        # ⚠️ limpa o que escreveu. Um assert vermelho no meio já me deixou 4 apontamentos de
        # teste numa folha de produção, misturados com os reais.
        await db.execute(text("DELETE FROM wa_vigia_avisos WHERE posto = '__ORACULO__'"))
        await db.commit()


async def _5_dry_run_nao_grava(db) -> None:
    """`publicar=False` não deixa rastro.

    Gravar sem publicar QUEIMA o aviso: o problema fica marcado como comunicado sem ninguém ter
    sido comunicado, e nunca mais sai. É o espelho do defeito que me deixou 4 pessoas em
    `aguardando` com zero mensagens enviadas — lá gravei sem enviar, aqui eu quase repeti.
    """
    antes = (await db.execute(text("SELECT count(*) FROM wa_vigia_avisos"))).scalar()
    r = await vigia.varrer(db, publicar=False)
    depois = (await db.execute(text("SELECT count(*) FROM wa_vigia_avisos"))).scalar()
    if depois != antes:
        _erro(f"dry run GRAVOU {depois - antes} linha(s) — avisos queimados sem publicação")
    elif r.get("publicado"):
        _erro("dry run diz que publicou — está mandando mensagem de verdade em modo de teste")
    else:
        _ok(f"dry run puro: {antes} linhas antes e depois, {r['problemas_abertos']} "
            "problema(s) apenas LIDO(s)")


async def _6_nao_alarma_o_normal(db) -> None:
    """COBERTO e AGUARDANDO nunca entram na lista de aviso.

    Verde é silêncio. E AGUARDANDO é futuro: cobrar quem ainda não tem turno é o erro que
    transformou 29 turnos em um alarme falso de 17% de cobertura.
    """
    proibidos = {"COBERTO", "AGUARDANDO", "FOLGA", "AFASTADO", "SEM_BATIDA_JUSTIFICADA"}
    vaza = proibidos & (set(vigia._URGENTE) | vigia._CADASTRO)
    if vaza:
        _erro(f"veredito(s) normal(is) na lista de alarme: {sorted(vaza)}")
    else:
        _ok(f"{len(proibidos)} veredictos normais fora do alarme; "
            f"{len(vigia._URGENTE)} alarmes reais definidos")

    # o buraco de escala precisa ser ALCANÇÁVEL — ramo que nunca executa é promessa, não parede
    achou = await vigia.buracos_de_escala(db, _agora="2026-09-26 05:30:00")
    if not isinstance(achou, list):
        _erro("buracos_de_escala não devolveu lista")
    else:
        _ok(f"buracos_de_escala executável (retrato de 26/09 05:30: {len(achou)})")


async def main() -> None:
    _1_beat_e_fila()
    _2_carencia()
    _3_noturno()
    async with async_session_factory() as db:
        await _4_nao_repete(db)
        await _5_dry_run_nao_grava(db)
        await _6_nao_alarma_o_normal(db)

    if falhas:
        print(f"\nTEST vigia_postos FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST vigia_postos PASS")


if __name__ == "__main__":
    asyncio.run(main())
