"""Prova o vigia 24h dos grupos: ele VÊ a mídia, JULGA antes de gritar, e não fala onde não deve.

🔴 O DIA QUE PRODUZIU ISTO — 27/09/2026. Jordan: *"preciso que ele reporte problemas, troca de
turno, fotos, erros, falhas operacionais, despadronização dos agentes de portaria, ele tem que
ser um vigia de verdade 24h"*, *"o hermes entra como a memória do que já foi reportado"*,
*"ele só pode falar no escritório e gestão… e só quando for marcado"*.

Cada asserção abaixo é um defeito medido naquele dia — quatro deles meus, no mesmo arquivo:

  1. **A MÍDIA NÃO CHEGAVA AO GRUPO.** `analisar_midia` só atualizava `cwi_message_log`;
     `wa_grupo_mensagens` ficava com `📎 [analisando anexo(s)…]` para sempre. Medido: **1.282
     presas em 5 dias** contra 1.935 já descritas do outro lado. O José Luís estava cego
     justamente para a FOTO DE TROCA DE TURNO.
  2. **O RÓTULO NASCIA ANTES DO CONTEÚDO.** A classificação acontece na entrada, quando o texto
     ainda é o marcador — e marcador não casa com sinal nenhum, então TODA mídia nascia
     `tom`/irrelevante. Das 1.248 imagens recuperadas, **684 mudaram de classe**; dos 26 vídeos,
     **24 viraram `operacional`**.
  3. **O REGEX SOZINHO GRITAVA EM TUDO.** O 1º ensaio publicava *"o condomínio segue tranquilo e
     sem alterações"* como ocorrência. Vigia que grita em tudo é vigia que ninguém lê.
  4. **A RÉGUA DE DESPADRONIZAÇÃO MEDIA A SI MESMA.** `conecta\\s*mais` solto casava com **147
     descrições de imagem** em 24h ("A imagem enviada no atendimento da Conecta Mais mostra uma
     CNH…") contra 257 relatórios reais.

⚠️ Afirma a REGRA, não a fotografia: nenhuma contagem do dia, nenhum nome de pessoa.
"""

import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

falhas: list[str] = []

#: Casos de controle da régua mecânica. Cada um veio de texto REAL do banco.
_RELATORIOS = [
    ("*Conecta Mais – Segurança e Tecnologia*\n*Data*: 27/09/2026\n*Posto*: X\n"
     "*Turno*: Diurno\n*Agente de Portaria P1* Fulano", [], "relatório completo"),
    ("*Conecta Mais – Segurança e Tecnologia*\n*Data*: 27/09/2026\n*Posto*: X\n*Turno*: Diurno",
     ["Agente"], "falta o campo Agente"),
    ("🖼 [imagem recebida]: A imagem enviada no atendimento da Conecta Mais mostra uma CNH",
     [], "DESCRIÇÃO DE IMAGEM — 147 destas eram acusadas de relatório despadronizado"),
    ("🎥 [vídeo recebido]: IMAGENS: [cena 1] instalação hidráulica da Conecta Mais",
     [], "descrição de VÍDEO — mesma armadilha"),
    ("a Conecta Mais vai mandar o material amanhã", [], "cita a empresa no meio da frase"),
    ("bom dia pessoal", [], "conversa solta"),
]


async def main() -> None:
    from modules.integrations.connectors.whatsapp import grupos as G
    from modules.integrations.connectors.whatsapp import varredura as V

    # 1 — ⭐ A RÉGUA MECÂNICA MEDE O RELATÓRIO, NÃO A SI MESMA.
    for texto, esperado, desc in _RELATORIOS:
        got = V._despadronizado(texto)
        if got != esperado:
            falhas.append(f"despadronização errou em «{desc}»: devolveu {got}, esperado {esperado}")
    if not any("despadronização errou" in f for f in falhas):
        print(f"  ok  régua de despadronização: {len(_RELATORIOS)} casos, inclusive os de mídia")

    # 2 — ⭐ DESPADRONIZAÇÃO NÃO PASSA PELO JUIZ. Campo faltando é fato, não avaliação.
    #     Quando passava, o juiz reprovou TUDO: 145 mensagens, zero incidentes.
    src = inspect.getsource(V.varrer)
    if "_mecanico" not in src or "a_julgar" not in src:
        falhas.append("a varredura voltou a mandar TUDO ao juiz — despadronização é mecânica, e "
                      "pedir juízo sobre o objetivo apaga um requisito que o dono pediu")
    else:
        print("  ok  o juiz decide o subjetivo; o campo faltando é medido, não julgado")

    # 2b — ⭐ O RELATÓRIO É ACOMPANHAMENTO DO TIME, NÃO ECO DO GRUPO.
    #
    # Jordan, 27/09: *"quero ele mais como acompanhamento do nosso time operacional, e não para
    # postar o que eles postam no grupo"* e *"ele vai ver tudo, mas relatar só o que nos
    # interessa"*. A 1ª versão colava 260 caracteres da mensagem original — que a pessoa já
    # tinha postado no grupo dela.
    _amostra = [
        {"autor_nome": "JONHATA DINIZ", "grupo": "Ideal", "cat": "padrao",
         "rotulo": "relatório sem agente", "conteudo": "TEXTO_ORIGINAL_QUE_NAO_PODE_APARECER"},
        {"autor_nome": "JONHATA DINIZ", "grupo": "Ideal", "cat": "padrao",
         "rotulo": "relatório sem agente", "conteudo": "TEXTO_ORIGINAL_QUE_NAO_PODE_APARECER"},
        {"autor_nome": "ERIKA CRISTINA", "grupo": "Laranjeiras", "cat": "ponto",
         "rotulo": "não conseguiu bater ponto", "conteudo": "TEXTO_ORIGINAL_QUE_NAO_PODE_APARECER"},
    ]
    saida = V._texto(_amostra, 0, 9, 60)
    if "TEXTO_ORIGINAL_QUE_NAO_PODE_APARECER" in saida:
        falhas.append("o relatório voltou a COLAR a mensagem original — o grupo já postou "
                      "aquilo; repetir no Gestão é ruído com cara de trabalho")
    elif "(2×)" not in saida:
        falhas.append("o relatório não agrupou a repetição — o mesmo agente com o mesmo desvio "
                      "duas vezes virou duas linhas iguais")
    elif "PONTO" not in saida or "PADRÃO" not in saida:
        falhas.append(f"o relatório perdeu as seções por categoria:\n{saida}")
    else:
        print("  ok  relatório agrupa por pessoa/posto e NÃO cola a mensagem do grupo")

    # 3 — ⭐ QUEM O CHAMA É RECONHECIDO PELO NOME, e a rotina não vira chamada.
    for txt, esperado, desc in (
        ("José Luís , fica atento a troca de turno", True, "como o dono realmente escreve"),
        ("jose luis me manda o relatorio", True, "sem acento"),
        ("*Conecta Mais – Segurança e Tecnologia*\n*Data*: 27/09", False,
         "troca de turno — 980 mensagens assim não são chamada"),
        ("bom dia a todos", False, "conversa"),
    ):
        if G.foi_chamado(txt) is not esperado:
            falhas.append(f"`foi_chamado` errou em «{desc}»: esperava {esperado}")
    if not any("foi_chamado" in f for f in falhas):
        print("  ok  chamada reconhecida pelo NOME, e rotina não conta como chamada")

    async with async_session_factory() as db:
        # 4 — ⭐ SÓ DOIS GRUPOS FALAM. Regra do dono, verificada nos DADOS.
        falantes = [r[0] for r in (await db.execute(text(
            "SELECT nome FROM wa_grupos WHERE modo = 'falar' ORDER BY nome"))).all()]
        if sorted(falantes) != ["Escritório", "Gestão"]:
            falhas.append(f"grupos em modo `falar` mudaram: {falantes} — o dono autorizou "
                          "APENAS Escritório e Gestão")
        else:
            print(f"  ok  só falam: {', '.join(falantes)}")

        teto_furado = (await db.execute(text(
            "SELECT count(*) FROM wa_grupos WHERE modo = 'observar' AND max_falas_dia > 0"))).scalar()
        if teto_furado:
            falhas.append(f"{teto_furado} grupo(s) em `observar` com teto de fala > 0 — em grupo "
                          "de cliente o silêncio é obrigatório")
        else:
            print("  ok  nenhum grupo observado tem teto de fala")

        # 5 — 🔴 A MÍDIA CHEGA AO GRUPO. Esta é a asserção que pega o pior defeito:
        #     tudo analisado, e a tabela que o vigia lê continuando cega.
        presas = (await db.execute(text(
            "SELECT count(*) FROM wa_grupo_mensagens "
            " WHERE conteudo = '📎 [analisando anexo(s)…]' "
            "   AND criado_em < now() - interval '30 minutes'"))).scalar() or 0
        if presas > 5:
            falhas.append(f"{presas} mensagem(ns) de grupo presas no marcador de análise há mais "
                          "de 30 min — a descrição existe em `cwi_message_log` e não está "
                          "chegando aqui. O José Luís volta a ficar cego para a foto de turno")
        else:
            print(f"  ok  mídia de grupo chega descrita ({presas} em análise agora)")

        # 6 — ⭐ E CHEGA COM O RÓTULO CERTO. Descrição real classificada como `tom` significa
        #     que o rótulo foi posto quando o conteúdo ainda era o marcador.
        midia = (await db.execute(text(
            "SELECT count(*) FILTER (WHERE classificacao <> 'tom') AS com_classe, count(*) AS total "
            "  FROM wa_grupo_mensagens "
            " WHERE conteudo LIKE '🖼%' OR conteudo LIKE '🎥%' OR conteudo LIKE '🎙%'"))).first()
        if midia and midia[1] and midia[0] == 0:
            falhas.append(f"as {midia[1]} mídias descritas estão TODAS como `tom` — o rótulo "
                          "voltou a ser posto antes de haver conteúdo, e a varredura as ignora")
        elif midia and midia[1]:
            print(f"  ok  mídia reclassificada com o conteúdo real "
                  f"({midia[0]} de {midia[1]} fora de `tom`)")
        else:
            print("  ·   nenhuma mídia descrita ainda (controle vazio)")

        # 7 — ⭐ O HERMES É A MEMÓRIA: a mesma mensagem nunca é reportada duas vezes.
        repetida = (await db.execute(text(
            "SELECT count(*) FROM (SELECT chatwoot_message_id FROM cwi_message_log "
            "  WHERE direction='cas' AND status='varredura' AND chatwoot_message_id IS NOT NULL "
            "  GROUP BY 1 HAVING count(*) > 1) x"))).scalar() or 0
        if repetida:
            falhas.append(f"{repetida} mensagem(ns) reportada(s) mais de uma vez pela varredura — "
                          "a memória por `chatwoot_message_id` furou")
        else:
            print("  ok  nenhuma mensagem reportada duas vezes")

        # 8 — CONTROLE: ensaio não queima novidade. Gravar num dry run marcaria como reportado
        #     algo que ninguém viu, e nunca mais sairia.
        antes = (await db.execute(text(
            "SELECT count(*) FROM cwi_message_log WHERE direction='cas' AND status='varredura'"))).scalar()
        await V.varrer(db, janela_min=30, publicar=False)
        depois = (await db.execute(text(
            "SELECT count(*) FROM cwi_message_log WHERE direction='cas' AND status='varredura'"))).scalar()
        if depois != antes:
            falhas.append(f"`publicar=False` GRAVOU memória ({antes}→{depois}) — um ensaio "
                          "queimaria a novidade e o incidente nunca mais sairia")
        else:
            print("  ok  controle: dry run não grava memória nenhuma")

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"\nTEST varredura_grupos FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST varredura_grupos PASS")


if __name__ == "__main__":
    asyncio.run(main())
