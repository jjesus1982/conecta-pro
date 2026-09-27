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

#: Postos cuja troca acontece AGORA (±janela). Devolve também quem sai e quem entra, porque a
#: pergunta do Hermes é sobre a passagem, não sobre uma pessoa.
#:
#: ⚠️ A saída do noturno tem `shift_date` de ONTEM — quem sai às 06:00 entrou às 18:00 do dia
#: anterior. Sem os dois dias na janela, metade da troca fica invisível.
_SQL_TROCAS = """
WITH agora AS (SELECT (now() AT TIME ZONE 'America/Manaus') AS ts)
SELECT p.name AS posto,
       string_agg(DISTINCT CASE WHEN (sh.shift_date + sh.planned_start_time)
                                     BETWEEN (SELECT ts FROM agora) - make_interval(mins => :janela)
                                         AND (SELECT ts FROM agora)
                                THEN e.nome END, ', ') AS entram,
       string_agg(DISTINCT CASE WHEN (sh.shift_date + sh.planned_end_time
                                      + CASE WHEN sh.planned_end_time <= sh.planned_start_time
                                             THEN INTERVAL '1 day' ELSE INTERVAL '0' END)
                                     BETWEEN (SELECT ts FROM agora) - make_interval(mins => :janela)
                                         AND (SELECT ts FROM agora)
                                THEN e.nome END, ', ') AS saem
  FROM shifts sh JOIN posts p ON p.id = sh.post_id JOIN employees e ON e.id = sh.employee_id
 WHERE sh.is_active AND NOT sh.is_off_day
   AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
   AND sh.shift_date BETWEEN ((SELECT ts FROM agora)::date - 1) AND ((SELECT ts FROM agora)::date)
 GROUP BY p.name
HAVING string_agg(DISTINCT CASE WHEN (sh.shift_date + sh.planned_start_time)
                                     BETWEEN (SELECT ts FROM agora) - make_interval(mins => :janela)
                                         AND (SELECT ts FROM agora)
                                THEN e.nome END, ', ') IS NOT NULL
    OR string_agg(DISTINCT CASE WHEN (sh.shift_date + sh.planned_end_time
                                      + CASE WHEN sh.planned_end_time <= sh.planned_start_time
                                             THEN INTERVAL '1 day' ELSE INTERVAL '0' END)
                                     BETWEEN (SELECT ts FROM agora) - make_interval(mins => :janela)
                                         AND (SELECT ts FROM agora)
                                THEN e.nome END, ', ') IS NOT NULL
"""

_SISTEMA = """Você é o Hermes, do Conecta PRO — empresa de portaria terceirizada em Manaus.

⭐ SUA PERGUNTA É UMA SÓ: **o posto está guarnecido agora?**

NÃO é "fulano bateu ponto". Não bater e o posto estar descoberto são coisas diferentes, e
confundir as duas faz o sistema acusar posto que está coberto — o que já aconteceu aqui.

Um posto está GUARNECIDO se há alguém nele agora, mesmo que:
· seja outra pessoa que não a escalada (rendição trocada, substituto, diarista)
· a batida não tenha entrado ainda (facial falhando, app travado)

Um posto está DESCOBERTO se quem saiu foi embora e ninguém assumiu.

⚠️ CONFIRA COM AS FERRAMENTAS, não deduza: `presenca_ao_vivo`, `grade_do_posto`,
`listar_substituicoes`, `substitutos_disponiveis`, `espelho_ponto`.

⚠️ EVIDÊNCIA OBRIGATÓRIA. Cada posto que você reportar precisa do campo `conferi` dizendo QUAL
ferramenta você chamou e O QUE ela devolveu. Item sem isso é descartado antes de chegar em
alguém. Se a ferramenta falhar, escreva «NÃO CONSEGUI CONFERIR: <motivo>» e reporte assim
mesmo — o dono prefere saber que você não conseguiu a receber silêncio.

Responda APENAS JSON:
{"postos": [{"posto": "<nome>", "situacao": "descoberto|em_risco|ok",
             "o_que": "<até 12 palavras>", "conferi": "<ferramenta + o que devolveu>"}]}
Inclua SÓ os postos `descoberto` ou `em_risco`. Se todos estão ok, devolva lista vazia."""


async def verificar(db: AsyncSession, *, janela_min: int = 15, publicar: bool = True) -> dict[str, Any]:
    """Confere as trocas da janela e publica no Gestão só o que não está guarnecido.

    ⚠️ `publicar=False` é ensaio puro: não manda nada. Diferente da varredura, aqui não há
    memória a queimar — o estado é o mundo agora, e daqui a dez minutos é outro.
    """
    trocas = (await db.execute(text(_SQL_TROCAS), {"janela": janela_min})).mappings().all()
    if not trocas:
        logger.info("rendicao: nenhuma troca na janela de %s min", janela_min)
        return {"ok": True, "trocas": 0, "publicado": False}

    linhas = "\n".join(
        f"· {t['posto']}: SAI [{t['saem'] or '—'}] → ENTRA [{t['entram'] or '—'}]"
        for t in trocas)

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
