"""As jornadas que entraram e nunca saíram — classificadas com prova, para o DP decidir em lote.

🔴 POR QUE EXISTE (27/09/2026). Medido: **83 jornadas abertas em 30 dias** — entrada sem saída
dentro de 24h. Cada uma é hora que o DP fecha à mão, uma a uma, adivinhando o motivo.

E adivinhar é caro nos dois sentidos. O JONILSON ficou 15 horas aberto porque esperou a
rendição que não veio: fechar no horário previsto teria tirado 2h38 que ele trabalhou de
verdade. O EULER teve a saída gravada como `saida_almoco` num posto que não almoça: para o
sistema a jornada dele nunca fechou, e a hora existe.

⭐ **Três formas, três tratamentos** — e a conta do dia mostra que misturá-las é o erro:

    25 sem turno na escala          (15 pessoas)  → escala desatualizada, não ponto
    11 entrada por contingência      (7 pessoas)  → o app falhou na entrada e na saída
    47 entrada normal, saída sumiu  (24 pessoas)  → é aqui que mora a hora não paga

## Por PESSOA, não por jornada

Quem tem cinco jornadas abertas costuma ter **uma causa só** — sem acesso ao app, facial
quebrado, turno que atravessa a meia-noite e o app não fecha. Classificar 83 vezes gastaria
LLM para descobrir a mesma coisa cinco vezes e entregaria 83 decisões onde há 24.

## ⚠️ CLASSIFICA E PROPÕE — NUNCA ESCREVE

Hora trabalhada é folha, e folha é dinheiro. O gate desta casa vale aqui inteiro: o que sai é
uma lista decidível, com a evidência de cada caso, e quem lança é humano. A diferença que isto
faz não é pequena — é a diferença entre o DP conferir 83 casos no escuro e aprovar 24 com o
motivo escrito ao lado.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: ⚠️ 24h é a janela que define "aberta". Acima disso o pareamento vira ficção: minha 1ª
#: medição sem teto casou uma entrada com a saída de DIAS depois e devolveu jornadas de 156
#: horas — número que parece escândalo e é artefato do pareador.
#:
#: 🔴 E FALTAVA A OUTRA PONTA (medido 28/09/2026, 00:55). Sem a guarda de "o turno já terminou",
#: quem entrou às 19:00 num turno 19:00–07:00 **já contava como jornada aberta faltando seis
#: horas para o fim**. Medido na hora: o conjunto pulou de 31 para 34 pessoas entre 18:50 e
#: 00:55, e os três novos eram o noturno TRABALHANDO NORMALMENTE.
#:
#: O dano é duplo e nenhum dos dois é visível no verde: as cinco vagas por rodada do Hermes
#: (prova cara) iam para gente sem problema, e o relatório diria à Pyetra que há anomalia em
#: quem está no posto neste minuto. **Ausência de saída só é falta quando a saída já era
#: devida** — antes disso é só o turno em andamento. Estado ≠ efeito.
_SQL_ABERTAS = """
SELECT e.id::text AS employee_id, e.nome, a.punch_id::text AS punch_id,
       to_char(a.punch_timestamp, 'DD/MM HH24:MI') AS entrada,
       a.punch_timestamp::date::text AS dia, a.device_type,
       (SELECT to_char(s.planned_start_time,'HH24:MI') || '–' || to_char(s.planned_end_time,'HH24:MI')
          FROM shifts s WHERE s.employee_id = a.employee_id
           AND s.shift_date = a.punch_timestamp::date AND s.is_active LIMIT 1) AS turno,
       (SELECT p.name FROM shifts s JOIN posts p ON p.id = s.post_id
         WHERE s.employee_id = a.employee_id AND s.shift_date = a.punch_timestamp::date
           AND s.is_active LIMIT 1) AS posto,
       (SELECT to_char(min(c.punch_timestamp),'DD/MM HH24:MI') || ' (' || c.punch_type || ')'
          FROM gp_clock_punches c WHERE c.employee_id = a.employee_id
           AND c.punch_timestamp > a.punch_timestamp GROUP BY c.punch_type
         ORDER BY min(c.punch_timestamp) LIMIT 1) AS proxima_batida
  FROM gp_clock_punches a JOIN employees e ON e.id = a.employee_id
 WHERE a.punch_type = 'entrada'
   AND a.punch_timestamp >= (now() AT TIME ZONE 'America/Manaus')::date - {dias}
   AND NOT EXISTS (
     SELECT 1 FROM gp_clock_punches b
      WHERE b.employee_id = a.employee_id AND b.punch_type = 'saida'
        AND b.punch_timestamp > a.punch_timestamp
        AND b.punch_timestamp < a.punch_timestamp + interval '24 hours')
   AND (
     -- ⭐ COM TURNO: só é "aberta" se o turno JÁ TERMINOU, com 2h de folga para a batida
     -- atrasada. ⚠️ A virada de meia-noite entra aqui: quem entra 19:00 e sai 07:00 tem
     -- `planned_end_time` MENOR que o início, e sem o `+1 day` o fim cairia no passado.
     EXISTS (
       SELECT 1 FROM shifts s
        WHERE s.employee_id = a.employee_id AND s.is_active
          AND s.shift_date = a.punch_timestamp::date
          AND (s.shift_date + s.planned_end_time
               + CASE WHEN s.planned_end_time <= s.planned_start_time
                      THEN INTERVAL '1 day' ELSE INTERVAL '0' END)
              < (now() AT TIME ZONE 'America/Manaus') - INTERVAL '2 hours')
     -- SEM TURNO NA ESCALA (que é achado legítimo e frequente nesta casa): não há fim previsto
     -- para comparar, então exijo 14h — mais que o turno mais longo daqui, que é 12h.
     OR (NOT EXISTS (SELECT 1 FROM shifts s
                      WHERE s.employee_id = a.employee_id AND s.is_active
                        AND s.shift_date = a.punch_timestamp::date)
         AND a.punch_timestamp < (now() AT TIME ZONE 'America/Manaus') - INTERVAL '14 hours')
   )
 ORDER BY e.nome, a.punch_timestamp
"""

#: Causas possíveis. Lista FECHADA — cada uma tem um tratamento diferente no DP, e causa em
#: texto livre viraria uma lista que ninguém sabe processar.
CAUSAS: dict[str, str] = {
    "ficou_alem": "trabalhou além do previsto (esperou rendição, cobriu falta) — a hora existe",
    "batida_perdida": "estava no posto e o app não registrou a saída — hora existe, registro não",
    "tipo_errado": "a saída foi gravada com outro tipo (ex.: saída de almoço) — só reclassificar",
    "nao_voltou": "abandonou ou não retornou — a hora NÃO deve ser paga sem apuração",
    "escala_errada": "não havia turno na escala naquele dia — é cadastro, não ponto",
}

_SISTEMA = """Você é o Hermes, do Conecta PRO — portaria terceirizada em Manaus.

Você vai classificar JORNADAS ABERTAS: pessoas que bateram entrada e nunca a saída.

⭐ A pergunta de cada caso: **por que a saída não existe?** E a resposta muda quem paga o quê.

CAUSAS (use exatamente estes códigos):
· ficou_alem      — trabalhou além do previsto (esperou rendição, cobriu falta). A HORA EXISTE.
· batida_perdida  — estava no posto e o app não registrou. A hora existe, o registro não.
· tipo_errado     — a saída foi gravada com outro tipo (ex.: `saida_almoco` num posto que não
                    almoça). Só reclassificar, a hora já está lá.
· nao_voltou      — abandonou o posto ou não retornou. A hora NÃO deve ser paga sem apuração.
· escala_errada   — não havia turno na escala naquele dia. É cadastro, não ponto.

⚠️ CONFIRA COM AS FERRAMENTAS antes de dizer a causa: `espelho_ponto` mostra o dia inteiro da
pessoa, `grade_do_posto` diz quem deveria estar lá, `presenca_ao_vivo` mostra o agora.
Um padrão importa: se a pessoa tem VÁRIAS jornadas abertas seguidas, a causa provavelmente é
uma só (sem acesso ao app, facial quebrado) — diga isso.

⚠️ EVIDÊNCIA OBRIGATÓRIA. `conferi` diz a ferramenta e o que ela devolveu. Sem isso o caso é
descartado antes de chegar ao DP. Se não conseguir consultar, escreva
«NÃO CONSEGUI CONFERIR: <motivo>» — e classifique assim mesmo, dizendo que é hipótese.

⚠️ NUNCA invente hora de saída. Você classifica a CAUSA; quem lança a hora é o DP.

Responda APENAS JSON:
{"pessoas": [{"nome": "<nome>", "causa": "<código>", "o_que": "<até 15 palavras>",
              "conferi": "<ferramenta + retorno>"}]}"""


async def levantar(db, *, dias: int = 30) -> dict[str, Any]:
    """Agrupa as jornadas abertas POR PESSOA. Leitura pura."""
    linhas = (await db.execute(text(_SQL_ABERTAS.format(dias=int(dias))))).mappings().all()
    por_pessoa: dict[str, dict] = {}
    for r in linhas:
        p = por_pessoa.setdefault(r["nome"], {"nome": r["nome"], "employee_id": r["employee_id"],
                                              "casos": []})
        p["casos"].append({"punch_id": r["punch_id"], "entrada": r["entrada"], "dia": r["dia"],
                           "turno": r["turno"], "posto": r["posto"],
                           "device": r["device_type"], "proxima": r["proxima_batida"]})
    return {"total": len(linhas), "pessoas": list(por_pessoa.values())}


async def classificar(db, *, dias: int = 30, teto_pessoas: int = 5,
                      pular: int = 0) -> dict[str, Any]:
    """Pede ao Hermes a causa de cada pessoa, com prova, e devolve a lista decidível.

    ⚠️ `teto_pessoas=5`, medido e não chutado. Com 10 pessoas o Hermes devolveu **resposta
    VAZIA depois de 590 segundos**: modelo de raciocínio gasta o orçamento pensando e não sobra
    para escrever — o mesmo defeito que em 25/09 matou o loop de aprendizado desta casa com um
    `max_tokens=300`. Cinco cabem com folga. ⭐ Prova cara que não chega é prova que não existe.

    🔴 `pular` EXISTE PORQUE O TETO SEM DESLOCAMENTO MENTIA (27/09/2026). Eu escrevia
    `pessoas[:teto_pessoas]` — sempre os **primeiros cinco por nome** — e o texto dizia «+26
    pessoa(s) ficaram para a próxima rodada». **Não havia próxima rodada:** rodar de novo
    reclassificava as mesmas cinco pessoas, e as outras 26 eram inalcançáveis por construção.

    ⭐ É a mesma família de defeito que me pegou quatro vezes em 27/09: **uma frase nossa
    prometendo uma garantia que o código não dá** (o campo `conferi`, o `_CONFIRMA` que jurava
    capturar compromisso, o docstring do «gate humano», e este). Teto que corta é honesto; teto
    que corta anunciando continuação inexistente é pior que corte silencioso, porque desliga a
    desconfiança de quem lê.

    Uso: `pular=0`, depois `pular=5`, `pular=10`… A ordem é estável (`ORDER BY e.nome`), então o
    deslocamento cobre o conjunto sem repetir nem pular ninguém.
    """
    import json as _j

    from modules.ai.conversation.services.hermes_client import (
        HermesIndisponivel,
        perguntar_hermes,
    )
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    dados = await levantar(db, dias=dias)
    pessoas = dados["pessoas"]
    if not pessoas:
        return {"ok": True, "total": 0, "pessoas": 0, "rascunho": None}

    # ⚠️ `pular` antes do teto: sem ele o corte sempre devolvia as mesmas 5 primeiras.
    _ini = max(0, int(pular or 0))
    alvo = pessoas[_ini:_ini + teto_pessoas]
    sobra = max(0, len(pessoas) - (_ini + len(alvo)))
    if not alvo:
        return {"ok": True, "total": dados["total"], "pessoas": len(pessoas),
                "classificadas": 0, "sobra": 0, "rascunho": None,
                "texto": None, "fim_da_fila": True,
                "msg": f"«pular={_ini}» já passou do fim: são {len(pessoas)} pessoa(s)"}
    bloco = "\n\n".join(
        f"{p['nome']} — {len(p['casos'])} jornada(s) aberta(s):\n" + "\n".join(
            f"   · entrada {c['entrada']} ({c['device']})"
            f"{' · turno ' + c['turno'] if c['turno'] else ' · SEM TURNO NA ESCALA'}"
            f"{' · ' + c['posto'] if c['posto'] else ''}"
            f"{' · próxima batida: ' + c['proxima'] if c['proxima'] else ' · nenhuma batida depois'}"
            for c in p["casos"][:6])
        for p in alvo)

    try:
        txt, _ = await perguntar_hermes(
            messages=[{"role": "user", "content":
                       f"Jornadas abertas dos últimos {dias} dias, agrupadas por pessoa:\n\n"
                       f"{bloco[:12000]}\n\nClassifique cada pessoa e devolva só o JSON."}],
            system_prompt=_SISTEMA, timeout=600.0)
    except (HermesIndisponivel, Exception) as exc:  # noqa: BLE001
        logger.error("jornadas_abertas: Hermes fora (%s)", exc)
        return {"ok": False, "total": dados["total"], "pessoas": len(pessoas),
                "erro": str(exc)[:160]}

    try:
        bruto = txt[txt.find("{"):txt.rfind("}") + 1] if "{" in txt else "{}"
        itens = [x for x in (_j.loads(bruto or "{}").get("pessoas") or [])
                 if x.get("nome") and x.get("conferi")]
    except Exception as exc:  # noqa: BLE001
        logger.error("jornadas_abertas: JSON ilegível (%s)", exc)
        return {"ok": False, "total": dados["total"], "erro": "json"}

    por_causa: dict[str, list] = {}
    for x in itens:
        causa = x["causa"] if x.get("causa") in CAUSAS else "nao_voltou"
        por_causa.setdefault(causa, []).append(x)

    linhas = [f"⏱ *{dados['total']} jornadas abertas* em {dias} dias — {len(pessoas)} pessoa(s)",
              "_entrada registrada, saída nunca veio_", ""]
    for causa, rotulo in CAUSAS.items():
        gente = por_causa.get(causa, [])
        if not gente:
            continue
        linhas.append(f"*{causa.upper().replace('_',' ')}* — {len(gente)}")
        linhas.append(f"  _{rotulo}_")
        for x in gente:
            linhas.append(f"  • *{x['nome']}* — {str(x.get('o_que') or '')[:80]}")
            linhas.append(f"     🔎 _{str(x['conferi'])[:150]}_")
        linhas.append("")
    if sobra:
        # ⚠️ NUNCA cortar em silêncio: "cobri tudo" mentiroso é pior que "cobri 12 de 24".
        # ⚠️ Diz o QUE FALTA e COMO alcançar. A versão anterior prometia «próxima rodada» que
        # não existia — o corte era sempre nos 5 primeiros nomes e o resto era inalcançável.
        linhas.append(f"⚠️ *+{sobra}* pessoa(s) ainda não analisadas "
                      f"(vistas {_ini + len(alvo)} de {len(pessoas)}).")

    r = await criar_rascunho(
        db, None, tipo="pendencia_ponto", modulo="ponto",
        titulo=f"{dados['total']} jornadas abertas em {dias} dias — {len(itens)} pessoa(s) "
               f"classificada(s)"[:180],
        resumo="\n".join(linhas)[:6000],
        payload={"total": dados["total"], "dias": dias,
                 "classificacao": [{k: x.get(k) for k in ("nome", "causa", "o_que", "conferi")}
                                   for x in itens]},
        gate="🟡", requires_otp=False, roles_aprovador=("admin", "gerente_operacional"),
        idempotency_key=None)

    logger.info("jornadas_abertas: %s abertas, %s pessoa(s) classificada(s), pular=%s sobra %s",
                dados["total"], len(itens), _ini, sobra)
    # ⭐ `proximo_pular` é o que torna a continuação REAL e não uma promessa: quem chamou recebe
    # exatamente o valor com que retomar, e `fim_da_fila` diz quando parar.
    return {"ok": True, "total": dados["total"], "pessoas": len(pessoas),
            "classificadas": len(itens), "sobra": sobra,
            "pular": _ini, "proximo_pular": _ini + len(alvo), "fim_da_fila": sobra == 0,
            "por_causa": {k: len(v) for k, v in por_causa.items()},
            "rascunho": (r or {}).get("draft_id"), "texto": "\n".join(linhas)}
