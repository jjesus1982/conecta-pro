"""«Fulano faltou, Beltrano rendeu» vira registro estruturado — e só um humano executa.

🔴 POR QUE ESTE ARQUIVO NASCEU EM 27/09/2026.

Jordan, ao sair: *"a kelly patricia que estava escalada não foi ao posto, faltou, quem rendeu o
jonilson foi o rilen que não é do posto… no green hills a Thayna não foi ao posto, consegui um
diarista novo, Erlon… infelizmente em portaria é comum esses atrasos, faltas, rotatividade
acontecerem e termos que chamar quem nunca foi da empresa. nosso hermes agent e o josé luis
precisam aprender e se adaptar a essas circunstâncias"*.

E os DADOS diziam o mesmo, antes de ele falar. Das 6 conversas que o `hermes_ponte` marcou como
`falhou`, **duas são exatamente isto**, ambas sem nenhuma tool disponível:

  · *"Dona Ericka chegou atrasada"*
  · *"Se eu detectei esse problema é porque eu já assumi o posto"*

## ⭐ A máquina já existia. O que faltava era a porta — e a CAPTURA ESTRUTURADA.

`substitutions` existe com o formato exato (`original_employee_id`, `substitute_employee_id`,
`reason`, `post_id`, `shift_id`), tem dois controllers (`POST /falta/{shift_id}`,
`GET /substitutos/{id}`, `POST /substituir/{id}`) e um service. **Zero linhas desde que nasceu**
— era tela que ninguém abre.

E `pendencia_dp` já explicava, em comentário, por que o relato solto não executa:

> *"o payload destes tipos é RELATO EM TEXTO LIVRE — sem `shift_id`, sem `employee_id` de
> destino. Um executor que tentasse aplicar isso estaria deduzindo a mudança da prosa, que é
> fabricação."*

Está certo. A peça que faltava não é execução: é **transformar a prosa em alvo verificado no
momento em que alguém ainda pode confirmar**. Quem tem esse contexto é o agente, na conversa.
Aqui o nome vira `employee_id`, o dia vira `shift_id`, o posto vira `post_id` — e o que vai para
a Central é um alvo, não uma frase.

## ⚠️ O QUE ESTE MÓDULO NÃO FAZ

**Não escreve em `shifts` nem em `employee_alocacoes`.** A escala é curada à mão pelo Jordan e
continua dele. Este módulo cria um RASCUNHO 🟡; quem aprova é humano, e a execução roda com o
escopo operacional REAL de quem aprovou — não com um escopo que eu inventaria.

**Não cria diarista nem diária.** Quando quem rendeu não está em `employees` (o caso do ERLON,
que *"já trabalhou no condomínio"* mas nunca foi da empresa), o nome é capturado como texto e o
rascunho diz em voz alta que falta cadastrar a pessoa. ⭐ A chave entre diarista e funcionário é
o **CPF, nunca o nome** — e CPF é dado que só um humano fornece.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Motivos aceitos pelo `FaltaBody` do controller. Lista FECHADA de propósito: motivo em texto
#: livre do modelo faria a tela de faltas virar caixa de entrada sem dono.
MOTIVOS: dict[str, str] = {
    "falta": "não apareceu e não avisou",
    "atestado": "apresentou atestado médico",
    "emergencia": "emergência pessoal ou familiar",
    "pessoal": "motivo pessoal comunicado",
    "outro": "outro motivo, descrito no relato",
}

#: O turno de quem faltou, hoje ou ontem — a mesma janela que `POST /falta/{shift_id}` aceita.
#: ⚠️ ONTEM entra por causa do NOTURNO: um turno 18:00→06:00 tem `shift_date` do dia em que
#: COMEÇOU, e a falta dele só é percebida de madrugada ou na rendição da manhã seguinte.
_SQL_TURNO = """
SELECT sh.id::text AS shift_id, sh.post_id::text AS post_id, sh.shift_date::text AS dia,
       p.name AS posto, to_char(sh.planned_start_time,'HH24:MI') AS ini,
       to_char(sh.planned_end_time,'HH24:MI') AS fim, sh.status,
       (SELECT count(*) FROM gp_clock_punches c
         WHERE c.employee_id = sh.employee_id
           AND c.punch_timestamp BETWEEN (sh.shift_date + sh.planned_start_time - interval '3 hours')
                                     AND (sh.shift_date + sh.planned_start_time + interval '18 hours')
       ) AS batidas
  FROM shifts sh JOIN posts p ON p.id = sh.post_id
 WHERE sh.employee_id = CAST(:e AS uuid) AND sh.is_active AND NOT sh.is_off_day
   AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
   AND sh.shift_date BETWEEN ((now() AT TIME ZONE 'America/Manaus')::date - 1)
                         AND ((now() AT TIME ZONE 'America/Manaus')::date)
 ORDER BY sh.shift_date DESC, sh.planned_start_time DESC
"""


async def registrar(db, *, faltou: str, rendeu: str | None = None, motivo: str = "falta",
                    relato: str = "", reportado_por: str | None = None) -> dict[str, Any]:
    """Captura a cobertura e devolve o que o agente deve dizer. NUNCA muta escala.

    `faltou` e `rendeu` podem ser nome ou `employee_id` — a resolução é a mesma porta única do
    `destinatario`, que **recusa ambíguo**. Cinco pessoas nesta casa se chamam ANTONIO; escolher
    "a mais provável" é como o passo a passo do Jair foi parar no Antonio Carlos.
    """
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho
    from modules.integrations.connectors.whatsapp.destinatario import resolver

    motivo = motivo if motivo in MOTIVOS else "outro"
    relato = (relato or "").strip()

    # ⚠️ `exigir_telefone=False`: aqui só preciso saber QUEM É. Um cadastro com telefone torto
    # não pode impedir o registro de um fato — seria recusa no lugar errado.
    quem = await resolver(db, faltou or "", exigir_telefone=False)
    if not quem.get("ok"):
        return {"ok": False, "motivo": f"não consegui identificar quem faltou: {quem.get('motivo')}"}

    turnos = (await db.execute(text(_SQL_TURNO), {"e": quem["employee_id"]})).mappings().all()
    if not turnos:
        # ⭐ FALHA FECHADO E DIZ O PORQUÊ. Aconteceu de verdade em 27/09: a KELLY PATRICIA, que
        # o dono disse estar escalada, **não tinha turno nenhum** na escala — só alocação ao
        # posto. Sem turno não há falta a registrar, e inventar um seria escrever na escala a
        # partir de uma frase. Isto vira relatório, não correção.
        return {"ok": False, "sem_turno": True,
                "motivo": (f"{quem['nome']} não tem turno na escala hoje nem ontem, então não há "
                           f"falta a registrar contra um turno. Isso costuma significar que a "
                           f"escala está desatualizada — reporte ao Jordan, que é quem cura a "
                           f"escala.")}
    if len(turnos) > 1:
        lista = "; ".join(f"{t['dia']} {t['ini']}–{t['fim']} em {t['posto']}" for t in turnos)
        return {"ok": False, "motivo": (f"{quem['nome']} tem {len(turnos)} turnos na janela "
                                        f"({lista}). Me diga de qual deles você está falando.")}
    t = turnos[0]
    if t["batidas"]:
        # quem bateu ponto não faltou — e o fato mais forte é a batida, não o relato
        return {"ok": False, "motivo": (f"{quem['nome']} TEM batida registrada no turno de "
                                        f"{t['dia']} em {t['posto']}. Se ele saiu antes ou "
                                        f"chegou atrasado, isso é ajuste de ponto, não falta.")}

    # quem rendeu: pode ser da casa, pode não ser (o caso do ERLON)
    sub_id = sub_nome = None
    de_fora = None
    if rendeu:
        s = await resolver(db, rendeu, exigir_telefone=False)
        if s.get("ok"):
            sub_id, sub_nome = s["employee_id"], s["nome"]
            if sub_id == quem["employee_id"]:
                return {"ok": False, "motivo": "quem rendeu não pode ser a mesma pessoa que faltou"}
        elif "AMBÍGUO" in (s.get("motivo") or ""):
            return {"ok": False, "motivo": f"não consegui identificar quem rendeu: {s['motivo']}"}
        else:
            # ⭐ NÃO É ERRO: é a rotatividade da portaria. Jordan: *"termos que chamar quem nunca
            # foi da empresa, como no caso do erlon, mas que já trabalhou no condomínio"*.
            # Guardo o NOME como texto e digo que falta cadastro — não invento uma pessoa.
            de_fora = rendeu.strip()[:120]

    titulo = f"{quem['nome']} faltou em {t['posto']} ({t['dia']} {t['ini']}–{t['fim']})"
    cobertura = (f"Coberto por *{sub_nome}*." if sub_nome
                 else f"Coberto por *{de_fora}*, que NÃO está no cadastro." if de_fora
                 else "*Sem substituto informado* — o posto pode estar descoberto.")
    resumo = (
        f"{quem['nome']} não apareceu no turno de {t['dia']}, {t['ini']}–{t['fim']}, em "
        f"{t['posto']}.\nMotivo informado: {MOTIVOS[motivo]}.\n\n{cobertura}\n\n"
        + (f"Relato de quem contou:\n\"{relato[:800]}\"\n\n" if relato else "")
        + ("Aprovar = registrar a falta E escalar o substituto (turno espelho), pelo caminho "
           "oficial da casa, com o SEU escopo operacional.\n"
           if sub_id else
           "Aprovar = registrar APENAS a falta. "
           + (f"⚠️ {de_fora} não está em `employees`: para escalar como diarista alguém precisa "
              "cadastrá-lo com CPF primeiro — a chave entre as tabelas é o CPF, nunca o nome.\n"
              if de_fora else "Nenhum substituto foi informado.\n"))
        + "Rejeitar = nada acontece na escala."
    )

    try:
        r = await criar_rascunho(
            db, None, tipo="cobertura_posto", modulo="operacional",
            titulo=titulo[:180], resumo=resumo,
            payload={"shift_id": t["shift_id"], "post_id": t["post_id"], "dia": t["dia"],
                     "original_employee_id": quem["employee_id"], "faltoso_nome": quem["nome"],
                     "substitute_employee_id": sub_id, "substituto_nome": sub_nome,
                     "substituto_de_fora": de_fora, "motivo": motivo,
                     "relato": relato[:2000], "reportado_por": reportado_por},
            gate="🟡", requires_otp=False,
            roles_aprovador=("admin", "gerente_operacional"),
            # uma cobertura por turno: quem repetir o relato não empilha fila
            idempotency_key=f"cobertura_posto:{t['shift_id']}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("cobertura_posto: rascunho não nasceu para %s — %s", quem["nome"], exc,
                     exc_info=True)
        return {"ok": False, "motivo": f"falha ao registrar: {str(exc)[:160]}"}

    logger.info("cobertura_posto: %s faltou em %s (%s) — substituto=%s de_fora=%s",
                quem["nome"], t["posto"], t["dia"], sub_nome, de_fora)
    return {
        "ok": True, "rascunho": (r or {}).get("draft_id"),
        "faltoso": quem["nome"], "posto": t["posto"], "dia": t["dia"],
        "substituto": sub_nome or de_fora, "substituto_cadastrado": bool(sub_id),
        "msg": (f"Anotei: *{quem['nome']}* faltou em {t['posto']} ({t['ini']}–{t['fim']}) e "
                + (f"*{sub_nome}* rendeu. " if sub_nome
                   else f"*{de_fora}* rendeu. " if de_fora else "ninguém foi informado como rendição. ")
                + "Mandei para a supervisão confirmar — a escala só muda depois que alguém "
                  "aprovar."),
        "diga_a_pessoa": ("Confirme que a supervisão VAI DECIDIR — não diga que a escala já "
                          "mudou, porque não mudou."
                          + (" E avise que falta o CPF para cadastrar quem veio de fora."
                             if de_fora else "")),
    }


async def _exec_cobertura(db, user, payload: dict):  # noqa: ANN001, ANN202
    """Aprovado: registra a falta e, se houver substituto DA CASA, escala o turno espelho.

    ⭐ Chama as COROUTINES dos controllers oficiais (`registrar_falta`, `escalar_substituto`),
    não um INSERT meu. Foi a lição do `chamado_posto`: minha 1ª versão escrevia direto na tabela
    e estourou no primeiro campo, porque `aberto_por` é varchar(20) que guarda RÓTULO. O
    controller valida janela, conflito de turno, restrição por cliente e idempotência — tudo
    isso eu teria de reescrever errado.

    ⚠️ O ESCOPO É O DE QUEM APROVOU, derivado pelo mesmo `get_operational_scope` da API. Montar
    um escopo `all_posts=True` à mão seria conceder permissão que a pessoa talvez não tenha —
    autorização não se inventa no executor.
    """
    from modules.operacional.controllers.falta_substituto_controller import (
        FaltaBody,
        SubstituirBody,
        escalar_substituto,
        registrar_falta,
    )
    from modules.operacional.scope import get_operational_scope

    escopo = await get_operational_scope(current_user=user, db=db)

    falta = await registrar_falta(
        payload["shift_id"],
        FaltaBody(motivo=payload.get("motivo") or "falta",
                  detalhes=(payload.get("relato") or "")[:500] or None),
        scope=escopo, db=db,
    )
    sub_id = (falta or {}).get("substitution_id") or (falta or {}).get("id")

    if payload.get("substitute_employee_id") and sub_id:
        await escalar_substituto(
            str(sub_id),
            SubstituirBody(tipo="funcionario",
                           employee_id=payload["substitute_employee_id"],
                           observacao=f"Relatado ao José Luís no WhatsApp por "
                                      f"{payload.get('reportado_por') or 'quem estava no posto'}"),
            scope=escopo, db=db,
        )
        logger.info("cobertura_posto: %s cobre %s (substituição %s)",
                    payload.get("substituto_nome"), payload.get("faltoso_nome"), sub_id)
    return f"employee:{payload['original_employee_id']}"


def _registrar() -> None:
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import registrar_executor

    registrar_executor("cobertura_posto", _exec_cobertura)


_registrar()
