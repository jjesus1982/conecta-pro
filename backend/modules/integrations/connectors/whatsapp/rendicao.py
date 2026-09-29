"""A rendição AO VIVO: dez minutos depois da troca, o posto está guarnecido ou não?

🔴 POR QUE EXISTE (27/09/2026). Eu acompanhei a troca das 06:00 no olho, a pedido do dono, e
ela falhou três vezes no mesmo dia:

  · a KELLY PATRICIA não foi render o JONILSON no Ideal Flores; quem cobriu foi o RILEM, que
    não é do posto — e o Jonilson ficou 15 horas com a jornada aberta esperando
  · a THAYNA não foi ao Green Hills; um diarista de fora (ERLON) rendeu o MAURÍCIO
  · a ÉLEN só pôde sair quando a ERIKA chegou, 37 minutos atrasada

⭐ Nenhuma das três apareceu como buraco no minuto em que aconteceu. O `troca_turno` já PEDE
confirmação e LEMBRA uma hora antes — mas ninguém confere DEPOIS se a rendição de fato
aconteceu. Confirmar que vai é promessa; verificar que foi é fato.

## Por que isto é diferente do vigia

O `vigia` diz *"fulano não bateu"*. Verdadeiro e insuficiente: não bater e o posto estar
descoberto são coisas diferentes, e foi essa confusão que me fez acusar posto guarnecido o dia
inteiro. Aqui a pergunta é outra — **tem gente no posto agora?** — e quem responde é o Hermes,
com `presenca_ao_vivo` e `grade_do_posto` na mão.

⚠️ EVIDÊNCIA OBRIGATÓRIA, como em toda encomenda ao Hermes desde 27/09: cada posto reportado
volta com a ferramenta citada e o que ela devolveu. Sem prova, não publica.

## Quando roda

Dez minutos depois de cada troca — tempo de a pessoa chegar, bater e o sync do ponto alcançar.
Medido no dia: as trocas são 06:00, 07:00, 08:00, 10:00, 18:00 e 19:00, com 4, 4, 1, 1, 5 e 3
pessoas. Fora desses minutos não há o que verificar, e rodar à toa é custo sem sinal.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: Uma LINHA POR PESSOA da troca — quem sai, quem entra, e **se a batida dela existe**.
#:
#: 🔴 POR QUE A BATIDA VEM DAQUI, e não da ferramenta (medido em 27/09, 1ª execução automática).
#: Eu mandei o Hermes descobrir sozinho com `presenca_ao_vivo`, e ele reportou:
#:   «ALAN VIEIRA status presente (batida 06:00) … **sem saída registrada**»
#: O Alan havia batido SAÍDA às 18:00:01, dez minutos antes. Fui ler a ferramenta: o quadro de
#: presença **não tem conceito de saída por pessoa** — ele calcula a PRIMEIRA batida da janela e
#: chama de `presente`. A única saída que existe lá é `saidas_noturno_ontem`, um contador do dia
#: anterior. Ou seja: a ferramenta nunca disse aquilo. **O Hermes converteu "a ferramenta não me
#: informa" em "não existe"** — e escreveu a invenção dentro do campo `conferi`, que eu criei
#: para ser a prova. A exigência de evidência conferiu a CITAÇÃO e não a VERACIDADE: um detalhe
#: fabricado passou por prova só por estar vestido de nome de ferramenta.
#:
#: ⭐ A lição é de projeto, não de prompt: quando o fato é apurável em SQL, entregue-o apurado.
#: Pedir ao LLM que descubra o que já sabemos cria a chance de ele inventar — e nenhuma régua de
#: evidência distingue citação verdadeira de citação plausível.
#:
#: ⚠️ A saída do noturno tem `shift_date` de ONTEM — quem sai às 06:00 entrou às 18:00 do dia
#: anterior. Sem os dois dias na janela, metade da troca fica invisível.
_SQL_TROCAS = """
WITH lim AS (SELECT (now() AT TIME ZONE 'America/Manaus') AS ts,
                    (now() AT TIME ZONE 'America/Manaus') - make_interval(mins => :janela) AS ini),
base AS (
    SELECT p.name AS posto, e.nome, sh.employee_id, sh.shift_date,
           sh.planned_start_time, sh.planned_end_time
      FROM shifts sh
      JOIN posts p ON p.id = sh.post_id
      JOIN employees e ON e.id = sh.employee_id
     WHERE sh.is_active AND NOT sh.is_off_day
       AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
       AND sh.shift_date BETWEEN ((SELECT ts FROM lim)::date - 1) AND ((SELECT ts FROM lim)::date)
),
pessoas AS (
    SELECT posto, nome, employee_id, 'entra' AS papel, 'entrada' AS tipo,
           (shift_date + planned_start_time) AS marco
      FROM base
     WHERE (shift_date + planned_start_time)
           BETWEEN (SELECT ini FROM lim) AND (SELECT ts FROM lim)
    UNION ALL
    SELECT posto, nome, employee_id, 'sai' AS papel, 'saida' AS tipo,
           (shift_date + planned_end_time
            + CASE WHEN planned_end_time <= planned_start_time
                   THEN INTERVAL '1 day' ELSE INTERVAL '0' END) AS marco
      FROM base
     WHERE (shift_date + planned_end_time
            + CASE WHEN planned_end_time <= planned_start_time
                   THEN INTERVAL '1 day' ELSE INTERVAL '0' END)
           BETWEEN (SELECT ini FROM lim) AND (SELECT ts FROM lim)
)
SELECT ps.posto, ps.nome, ps.papel, to_char(ps.marco, 'HH24:MI') AS hora,
       to_char(b.punch_timestamp, 'HH24:MI') AS bateu,
       b.dentro_geofence,
       round(b.distancia_posto_metros::numeric) AS metros
  FROM pessoas ps
  -- ⭐ 29/09/2026: LATERAL em vez de subconsulta escalar porque agora se precisa de TRÊS campos
  -- da mesma batida, não só da hora. O motivo está no comentário de `marca`, em `verificar`:
  -- «existe batida» não é «a pessoa está no posto». Equivale ao `min()` anterior (a mais antiga
  -- da janela), então a hora reportada não mudou.
  LEFT JOIN LATERAL (
        SELECT g.punch_timestamp, g.dentro_geofence, g.distancia_posto_metros
          FROM gp_clock_punches g
         WHERE g.employee_id = ps.employee_id
           AND g.punch_type = ps.tipo
           AND g.punch_timestamp BETWEEN ps.marco - INTERVAL '2 hours'
                                     AND ps.marco + INTERVAL '2 hours'
         ORDER BY g.punch_timestamp
         LIMIT 1
  ) b ON TRUE
 ORDER BY ps.posto, ps.papel, ps.nome
"""

_SISTEMA = """Você é o Hermes, do Conecta PRO — empresa de portaria terceirizada em Manaus.

⭐ SUA PERGUNTA É UMA SÓ: **o posto está guarnecido agora?**

NÃO é "fulano bateu ponto". Não bater e o posto estar descoberto são coisas diferentes, e
confundir as duas faz o sistema acusar posto que está coberto — o que já aconteceu aqui.

Um posto está GUARNECIDO se há alguém nele agora, mesmo que:
· seja outra pessoa que não a escalada (rendição trocada, substituto, diarista)
· a batida não tenha entrado ainda (facial falhando, app travado)

⚠️ AS BATIDAS JÁ VÊM APURADAS na lista abaixo — «saída BATIDA 18:00» ou «saída NÃO BATIDA». Não
procure batida em ferramenta nenhuma: o que está escrito ali é o banco, lido agora.

🔴 «⚠️ FORA DO POSTO (N m)» NA LINHA MUDA TUDO: a batida é real, mas a geolocalização diz que a
pessoa estava a N metros do posto quando bateu. **Batida fora do posto NÃO é prova de que o posto
está guarnecido** — nunca a use como evidência de cobertura.

Em 29/09 você disse a um vigilante que a rendição dele já havia batido. Ela havia: a **4.959 m**
do posto. Ele continuou lá, sozinho, 12h20 no total, e ainda foi cobrado por 18 minutos de
atraso na saída — os mesmos 18 em que esperou a rendição que você declarou presente.

Com essa marca, o posto é `descoberto` (se quem saía já bateu saída) ou `em_risco` (se não bateu)
— e o `o_que` **tem de dizer a distância**, porque é o número que permite a um humano decidir se
é GPS ruim de guarita, raio do posto cadastrado pequeno, ou pessoa que não está lá.

⚠️ Sem a marca, não invente distância nem desconfiança: batida sem marca é batida boa.

OS TRÊS BALDES, e o do meio é o mais estreito:

· `descoberto` — quem saía **bateu a saída** e o entrante NÃO bateu entrada. Ninguém batido no
  posto agora. É o único que significa posto possivelmente vazio.
· `em_risco` — o anterior NÃO bateu saída (segue no posto) e o entrante não chegou. Ele está
  segurando o posto em hora extra que ninguém combinou.
· `ok` — todo o resto, inclusive entrante que bateu atrasado. Não reporte.

🔴 A REGRA QUE VOCÊ NÃO PODE QUEBRAR: **nunca afirme que algo "não está registrado" se a
ferramenta não te disse isso.** Em 27/09 você reportou «ALAN VIEIRA presente, sem saída
registrada» — e o Alan havia batido saída dez minutos antes. O `presenca_ao_vivo` não tem campo
de saída nenhum; você converteu "a ferramenta não me informa" em "não existe" e escreveu a
invenção no campo de prova. Se a ferramenta não cobre a pergunta, escreva «a ferramenta não
informa isso» — nunca a resposta que você imagina.

⚠️ Para o RESTO (quem cobre, substituto, diarista) confira com as ferramentas e não deduza:
`grade_do_posto`, `listar_substituicoes`, `substitutos_disponiveis`, `espelho_ponto`.
Lembre: diarista NÃO bate ponto — a diária é o registro. Substituto bate com o ID dele.

⚠️ EVIDÊNCIA OBRIGATÓRIA. Cada posto que você reportar precisa do campo `conferi` dizendo QUAL
ferramenta você chamou e O QUE ela devolveu — ou citando a batida já apurada da lista. Item sem
isso é descartado antes de chegar em alguém. Se a ferramenta falhar, escreva «NÃO CONSEGUI
CONFERIR: <motivo>» e reporte assim mesmo — o dono prefere saber que você não conseguiu a
receber silêncio.

Responda APENAS JSON:
{"postos": [{"posto": "<nome>", "situacao": "descoberto|em_risco|ok",
             "o_que": "<até 12 palavras>", "conferi": "<ferramenta + o que devolveu>"}]}
Inclua SÓ os postos `descoberto` ou `em_risco`. Se todos estão ok, devolva lista vazia."""


async def verificar(db: AsyncSession, *, janela_min: int = 15, publicar: bool = True) -> dict[str, Any]:
    """Confere as trocas da janela e publica no Gestão só o que não está guarnecido.

    ⚠️ `publicar=False` é ensaio puro: não manda nada. Diferente da varredura, aqui não há
    memória a queimar — o estado é o mundo agora, e daqui a dez minutos é outro.
    """
    pessoas = (await db.execute(text(_SQL_TROCAS), {"janela": janela_min})).mappings().all()
    if not pessoas:
        logger.info("rendicao: nenhuma troca na janela de %s min", janela_min)
        return {"ok": True, "trocas": 0, "publicado": False}

    # ⭐ A batida vai ESCRITA na linha. O Hermes não precisa (nem pode) descobrir isto sozinho —
    # ver o comentário de `_SQL_TROCAS`: foi inventando uma saída que ele errou na estreia.
    por_posto: dict[str, list[str]] = {}
    for p in pessoas:
        rotulo = "SAI" if p["papel"] == "sai" else "ENTRA"
        tipo = "saída" if p["papel"] == "sai" else "entrada"
        marca = f"{tipo} BATIDA {p['bateu']}" if p["bateu"] else f"{tipo} NÃO BATIDA"
        # 🔴 29/09/2026, e quem achou foi o MAURICIO, não uma trava. Ele estava no posto do Green
        # Hills esperando rendição e o agente disse a ele que a rendição já havia batido. Ele
        # respondeu: «como ela tá batendo o ponto se a mesma não tá no posto». A batida dela era
        # real (rosto casou, confiança 0,895) e foi a **4.958,7 m do posto**.
        #
        # ⭐ A batida entrava aqui como «BATIDA 07:01» e mais nada. O Hermes lê exatamente esta
        # linha — o prompt manda não procurar batida em ferramenta nenhuma — então ele concluiu
        # posto guarnecido de forma impecável a partir de um dado incompleto. Não foi erro dele.
        #
        # A distância existia no banco desde sempre; só não chegava a quem decide. Agora chega.
        # ⚠️ `is False` de propósito: geofence NULO é «não deu para medir», e isso NÃO pode virar
        # acusação de que a pessoa não está no posto.
        if p["bateu"] and p["dentro_geofence"] is False:
            m = p["metros"]
            marca += f" ⚠️ FORA DO POSTO ({int(m)} m)" if m is not None else " ⚠️ FORA DO POSTO"
        por_posto.setdefault(p["posto"], []).append(
            f"{rotulo} {p['nome']} ({p['hora']}) — {marca}")
    linhas = "\n".join(f"· {posto}:\n    " + "\n    ".join(itens)
                       for posto, itens in por_posto.items())
    trocas = list(por_posto)

    from modules.ai.conversation.services.hermes_client import (
        HermesIndisponivel,
        perguntar_hermes,
    )

    try:
        txt, _ = await perguntar_hermes(
            messages=[{"role": "user", "content":
                       f"Trocas de turno que acabaram de acontecer:\n\n{linhas}\n\n"
                       "Para CADA posto, confira no sistema se há alguém lá agora. "
                       "Devolva apenas o JSON."}],
            system_prompt=_SISTEMA, timeout=300.0)
    except (HermesIndisponivel, Exception) as exc:  # noqa: BLE001
        # ⭐ FALHA DITA, NUNCA SILENCIOSA. Rendição não verificada parecendo rendição ok é o
        # pior desfecho possível: o posto pode estar vazio e ninguém saber.
        logger.error("rendicao: Hermes fora (%s) — publicando o AVISO de que não verifiquei", exc)
        if publicar:
            await _publicar(db, f"⚠️ *Rendição não verificada* — {len(trocas)} troca(s) agora "
                                f"e o Hermes não respondeu ({str(exc)[:80]}).\n\n"
                                f"{linhas}\n\n_Confiram no olho, por favor._")
        return {"ok": False, "trocas": len(trocas), "erro": str(exc)[:120], "publicado": publicar}

    import json as _j
    try:
        bruto = txt[txt.find("{"):txt.rfind("}") + 1] if "{" in txt else "{}"
        itens = [x for x in (_j.loads(bruto or "{}").get("postos") or [])
                 if str(x.get("situacao")) in ("descoberto", "em_risco") and x.get("conferi")]
    except Exception as exc:  # noqa: BLE001
        logger.error("rendicao: JSON ilegível do Hermes (%s)", exc)
        return {"ok": False, "trocas": len(trocas), "erro": "json", "publicado": False}

    if not itens:
        logger.info("rendicao: %s troca(s) verificada(s), todos guarnecidos", len(trocas))
        return {"ok": True, "trocas": len(trocas), "problemas": 0, "publicado": False}

    corpo = [f"🚨 *Rendição* — {len(itens)} posto(s) para olhar agora", ""]
    for x in itens:
        icone = "🔴" if x["situacao"] == "descoberto" else "🟠"
        corpo.append(f"{icone} *{x['posto']}* — {str(x.get('o_que') or '')[:70]}")
        corpo.append(f"     🔎 _{str(x['conferi'])[:170]}_")
    corpo += ["", f"_Verificado {len(trocas)} posto(s) em troca; os demais estão guarnecidos._"]

    publicado = await _publicar(db, "\n".join(corpo)) if publicar else False
    logger.info("rendicao: %s de %s posto(s) com problema (publicado=%s)",
                len(itens), len(trocas), publicado)
    return {"ok": True, "trocas": len(trocas), "problemas": len(itens), "publicado": publicado,
            "postos": [x["posto"] for x in itens]}


async def _publicar(db: AsyncSession, texto_msg: str) -> bool:
    from modules.integrations.connectors.whatsapp import supervisao as _sup
    from modules.integrations.connectors.whatsapp import vigia as _vig

    destino = await _vig._destino_gestao(db)
    if not destino:
        logger.warning("rendicao: sem grupo Gestão — nada publicado")
        return False
    return bool(await _sup._publicar_no_grupo(int(destino), texto_msg))
