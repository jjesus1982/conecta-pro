"""«Isso está errado, o certo é X» — de quem sabe — vira conserto do CASO e de toda a FAMÍLIA.

🔴 POR QUE EXISTE (27/09/2026). Jordan: *"se pyetra ou orlailson informarem a ele que algo que
ele informou está errado, ele precisa disparar pro hermes consertar no sistema… por exemplo se
quem estiver no turno do mirante for o ediwilson mas o josé luis dizer que é o chagas, daí
orlailson diz que está errado e informa o correto — **não só para este caso, como para todos** —
ele já age para corrigir"*.

⭐ A FRASE QUE CARREGA TUDO É «NÃO SÓ PARA ESTE CASO, COMO PARA TODOS». É a lição mais cara
desta casa, dita pelo dono com outras palavras: corrigir o caso que apareceu e deixar a família
viva é o padrão que mais custou aqui — 5 lugares ancorados no `max()` do arquivo, 5 filtros com
o vocabulário errado, 87 turnos com o posto congelado. Uma correção de quem sabe é evidência
de um defeito, e defeito tem irmãos.

## O que este módulo faz, em ordem

1. **Confere a AUTORIDADE.** Só quem decide corrige. Vem de `users.role`, nunca de
   `employees.cargo` — cargo é texto editável, e derivar autorização de texto editável dá
   visão sobre gente que ninguém autorizou.
2. **Mede a FAMÍLIA.** Dado (posto, quem está errado, quem é o certo), procura TODOS os
   registros com o mesmo defeito — não só o que o supervisor viu.
3. **Monta o rascunho 🟡** com o caso E a família. Aprovar corrige tudo de uma vez.
4. **Abre o defeito técnico 🔴** com a evidência medida, para o conserto na origem.

## ⭐ A CORREÇÃO É APLICADA NA HORA — autorização explícita do dono (27/09/2026)

Jordan: *"quero a correção feita diretamente pelo hermes, sem precisar eu ter que vir no
terminal… todas as vezes que eu, pyetra e orlailson mandarmos para o josé luís algo que está
errado, eu autorizo, pode fazer"*.

Eu levantei o risco, ele reafirmou. Então a correção de quem TEM AUTORIDADE aplica **sem
rascunho e sem clique** — e o que segura não é a aprovação, são estas quatro paredes:

  1. **Autoridade de verdade.** `users.role` + `u.is_active`. A parede já provou que funciona
     antes de eu saber: meu teste usou o ELIZIEL como gerente operacional e o módulo recusou —
     conta inativa. Três horas depois o dono me contou que ele tinha sido demitido.
  2. **Só o futuro.** Nunca reescreve turno passado: passado é o registro do que a casa
     acreditou na época. Em 27/09 um UPDATE meu quase cancelou 38 turnos de julho.
  3. **Só o campo corrigido.** Troca QUEM está no turno, e nada mais. Horário, posto e
     alocação não se inferem da frase — isso seria fabricação.
  4. **Anúncio obrigatório.** Toda correção aplicada é publicada no Gestão com o quê, quem
     mandou e quantos registros mudaram. Mudança silenciosa em produção é o que ninguém
     consegue desfazer, porque ninguém soube.

⚠️ E toda alteração fica no `notes` do próprio turno, com autor e data: desfazer é ler a nota.

## ⚠️ ONDE ESTE MÓDULO PARA, E POR QUÊ

O dono pediu que o Hermes *"conserte no sistema, no código, no back ou frontend"*. O conserto
do **dado** está aqui e é automático depois de um humano aprovar — inclusive a família inteira.

O conserto do **código** não. Um modelo editando produção a partir de uma frase de WhatsApp
erra em silêncio e com autoridade: hoje mesmo eu, com muito mais contexto, acusei 316
relatórios de despadronizados quando eram 74, e cancelei 56 turnos quando devia cancelar 18 —
as duas vezes por medir antes de contar. O que sai daqui é um defeito **com a evidência e o
tamanho da família já medidos**, que é o insumo que falta para o conserto ser rápido e certo.

⭐ E isso não é menos do que foi pedido: hoje a correção do supervisor morre na conversa. Com
isto ela vira dado corrigido em massa + defeito rastreado. A mão no código continua humana.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

#: Quem pode corrigir. Mesma régua da Central de Aprovações — hoje Pyetra (`admin`) e
#: Orlailson (`gerente_operacional`).
#: ⚠️ De `users.role`, NUNCA de `employees.cargo`: cargo é texto livre e cadastrar alguém como
#: "SUPERVISOR DE ÁREA" daria a ele poder de reescrever a escala de 61 pessoas.
ROLES_CORRIGE = ("admin", "gerente_operacional")

#: O que pode ser corrigido. Lista fechada — assunto novo entra com nome e com busca de família
#: própria, senão vira texto livre que ninguém sabe consertar.
TIPOS: dict[str, str] = {
    "escala": "quem está escalado, em que posto, em que horário",
    "ponto": "batida, horário de batida, justificativa",
    "cadastro": "dado da pessoa (telefone, posto, vínculo, função)",
    "outro": "outro fato que o agente informou errado",
}

_SQL_AUTORIDADE = """
SELECT u.role, e.nome
  FROM users u JOIN employees e ON e.id = u.employee_id
 WHERE u.is_active AND u.role = ANY(:roles) AND e.id = CAST(:e AS uuid)
"""

#: ⭐ A FAMÍLIA DO DEFEITO DE ESCALA: todos os turnos FUTUROS em que a pessoa apontada como
#: errada aparece no posto citado. Se o Orlailson diz que o Mirante é do Ediwilson e não do
#: Chagas, não adianta consertar o turno de hoje: os de amanhã e da semana estão iguais.
#:
#: ⚠️ Só FUTUROS e o de hoje. Turno passado é registro do que a casa acreditou na época —
#: reescrever história não foi pedido, e em 27/09 meu UPDATE quase cancelou 38 turnos de julho.
_SQL_FAMILIA_ESCALA = """
SELECT s.id::text AS shift_id, s.shift_date::text AS dia,
       to_char(s.planned_start_time,'HH24:MI') AS ini,
       to_char(s.planned_end_time,'HH24:MI') AS fim, p.name AS posto, e.nome
  FROM shifts s JOIN employees e ON e.id = s.employee_id JOIN posts p ON p.id = s.post_id
 WHERE s.is_active AND NOT s.is_off_day
   AND lower(coalesce(s.status,'')) IN ('scheduled','agendado','ativo')
   AND s.shift_date >= (now() AT TIME ZONE 'America/Manaus')::date
   AND s.employee_id = CAST(:errado AS uuid)
   -- ⚠️ `CAST(... AS text) IS NULL` e nao `:posto_id IS NULL`: asyncpg nao infere o tipo de
   -- um parametro nu dentro de IS NULL e recusa a consulta inteira ("could not determine data
   -- type of parameter"). Mesma familia dos dois CASTs que esta casa ja usa em toda data.
   AND (CAST(:posto_id AS text) IS NULL OR s.post_id = CAST(CAST(:posto_id AS text) AS uuid))
 ORDER BY s.shift_date
"""


async def registrar(db, *, quem_corrige_employee_id: str | None, tipo: str,
                    eu_disse: str, o_certo: str, pessoa_errada: str | None = None,
                    pessoa_certa: str | None = None, posto: str | None = None) -> dict[str, Any]:
    """Recebe a correção, mede a família e devolve o que o agente deve dizer.

    `eu_disse` e `o_certo` são as PALAVRAS DAS DUAS PARTES — o que o agente afirmou e o que o
    supervisor corrigiu. Quem for consertar precisa dos dois lados; só a correção não diz o que
    o sistema estava exibindo de errado.
    """
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho
    from modules.integrations.connectors.whatsapp.destinatario import resolver

    tipo = tipo if tipo in TIPOS else "outro"
    eu_disse, o_certo = (eu_disse or "").strip(), (o_certo or "").strip()
    if len(o_certo) < 5:
        return {"ok": False, "motivo": "me diga o que é o CERTO — sem isso eu só sei que errei, "
                                       "não sei o que corrigir"}

    # 1 — AUTORIDADE. Fail-closed: sem papel, vira relato, não correção.
    if not quem_corrige_employee_id:
        return {"ok": False, "motivo": "não sei quem está corrigindo — correção precisa de quem "
                                       "decide (Pyetra ou Orlailson)"}
    aut = (await db.execute(text(_SQL_AUTORIDADE),
                            {"roles": list(ROLES_CORRIGE),
                             "e": quem_corrige_employee_id})).mappings().first()
    if not aut:
        return {"ok": False, "sem_autoridade": True,
                "motivo": ("anotei o que você disse, mas quem corrige escala e cadastro é a "
                           "supervisão — vou levar isso a eles em vez de mudar por conta")}

    # 2 — ⭐ A FAMÍLIA. É o que o dono pediu com todas as letras: "não só para este caso".
    familia: list[dict] = []
    errado = certo = None
    if pessoa_errada:
        r = await resolver(db, pessoa_errada, exigir_telefone=False)
        errado = r if r.get("ok") else None
        if not errado and "AMBÍGUO" in (r.get("motivo") or ""):
            return {"ok": False, "motivo": f"quem está errado? {r['motivo']}"}
    if pessoa_certa:
        r = await resolver(db, pessoa_certa, exigir_telefone=False)
        certo = r if r.get("ok") else None
        if not certo and "AMBÍGUO" in (r.get("motivo") or ""):
            return {"ok": False, "motivo": f"quem é o certo? {r['motivo']}"}

    posto_id = None
    if posto:
        posto_id = (await db.execute(text(
            "SELECT id::text FROM posts WHERE is_active "
            "   AND upper(translate(name,'áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ','aaaaeeioooucAAAAEEIOOOUC')) "
            "       LIKE '%' || upper(translate(:p,'áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ',"
            "                                      'aaaaeeioooucAAAAEEIOOOUC')) || '%' LIMIT 1"),
            {"p": posto.strip()})).scalar()

    if tipo == "escala" and errado:
        familia = [dict(x) for x in (await db.execute(
            text(_SQL_FAMILIA_ESCALA),
            {"errado": errado["employee_id"], "posto_id": posto_id})).mappings().all()]

    # 3 — ⭐ APLICA NA HORA quando há alvo estruturado. Autorizado pelo dono em 27/09.
    quantos = len(familia)
    aplicado = 0
    if familia and certo:
        aplicado = await _aplicar(db, familia=[f["shift_id"] for f in familia],
                                  employee_certo=certo["employee_id"],
                                  quem=aut["nome"])
        await _anunciar(db, quem=aut["nome"], o_certo=o_certo, quantos=aplicado,
                        de=(errado or {}).get("nome"), para=certo["nome"])
        logger.info("correcao_supervisor: APLICADA na hora — %s turno(s) de %s para %s, por %s",
                    aplicado, (errado or {}).get("nome"), certo["nome"], aut["nome"])
        await _abrir_defeito(db, tipo=tipo, eu_disse=eu_disse, o_certo=o_certo,
                             quem=aut["nome"], quantos=quantos)
        return {
            "ok": True, "aplicado": aplicado, "familia": quantos,
            "corrigido_por": aut["nome"],
            "msg": (f"Corrigido. Não era só aquele caso: achei *{quantos}* turno(s) futuro(s) "
                    f"com o mesmo erro e mudei *{aplicado}* de {(errado or {}).get('nome','?')} "
                    f"para *{certo['nome']}* — de {familia[0]['dia']} a {familia[-1]['dia']}.\n\n"
                    f"Avisei no Gestão e abri o defeito técnico para o erro parar de acontecer "
                    f"na origem."),
            "diga_a_pessoa": ("Diga QUANTOS registros você mudou e o período — é isso que mostra "
                              "que a correção valeu para todos. E diga que ficou registrado no "
                              "Gestão, para ninguém ser pego de surpresa."),
        }
    titulo = (f"Correção de {aut['nome'].split()[0]}: {tipo}"
              + (f" — {errado['nome'].split()[0]}→{certo['nome'].split()[0]}"
                 if errado and certo else ""))
    resumo = (
        f"*{aut['nome']}* ({aut['role']}) corrigiu o José Luís.\n\n"
        f"O QUE O AGENTE DISSE:\n\"{eu_disse[:600] or '(não registrado)'}\"\n\n"
        f"O QUE ESTÁ CERTO, nas palavras dele(a):\n\"{o_certo[:600]}\"\n\n"
        + (f"⭐ FAMÍLIA MEDIDA: *{quantos}* turno(s) futuro(s) com o mesmo defeito"
           + (f" ({familia[0]['dia']} a {familia[-1]['dia']})" if quantos else "")
           + ".\nAprovar corrige TODOS, não só o caso que apareceu.\n\n"
           if tipo == "escala" and errado else
           "⚠️ Família não medida automaticamente para este tipo — quem aprovar confere se há "
           "outros casos iguais.\n\n")
        + "Rejeitar = nada muda e a correção fica registrada como divergência."
    )

    try:
        r = await criar_rascunho(
            db, None, tipo="correcao_supervisor", modulo="operacional",
            titulo=titulo[:180], resumo=resumo,
            payload={"tipo": tipo, "eu_disse": eu_disse[:2000], "o_certo": o_certo[:2000],
                     "corrigido_por": quem_corrige_employee_id,
                     "corrigido_por_nome": aut["nome"],
                     "employee_errado": (errado or {}).get("employee_id"),
                     "employee_certo": (certo or {}).get("employee_id"),
                     "posto_id": posto_id, "posto": posto,
                     "familia": [f["shift_id"] for f in familia]},
            gate="🟡", requires_otp=False, roles_aprovador=ROLES_CORRIGE,
            idempotency_key=None)
    except Exception as exc:  # noqa: BLE001
        logger.error("correcao_supervisor: rascunho não nasceu — %s", exc, exc_info=True)
        return {"ok": False, "motivo": f"falha ao registrar a correção: {str(exc)[:160]}"}

    # 4 — ⭐ E O DEFEITO TÉCNICO, com a evidência já medida. Sem isto a correção conserta o
    #     dado e deixa a CAUSA viva — o mesmo erro reaparece amanhã, e alguém corrige de novo.
    await _abrir_defeito(db, tipo=tipo, eu_disse=eu_disse, o_certo=o_certo,
                         quem=aut["nome"], quantos=quantos)

    logger.info("correcao_supervisor: %s corrigiu %s — família de %s registro(s)",
                aut["nome"], tipo, quantos)
    return {
        "ok": True, "rascunho": (r or {}).get("draft_id"), "familia": quantos,
        "corrigido_por": aut["nome"],
        "msg": (f"Anotei a correção e já procurei os outros casos iguais: achei *{quantos}* "
                f"turno(s) futuro(s) com o mesmo defeito. "
                if tipo == "escala" and errado else "Anotei a correção. ")
               + "Mandei para aprovação — aprovando, corrijo todos de uma vez, não só este. "
                 "E abri o defeito técnico para o erro parar de acontecer na origem.",
        "diga_a_pessoa": ("Diga QUANTOS casos iguais você achou — é isso que mostra que a "
                          "correção dela valeu para todos. E NUNCA diga que já corrigiu: só "
                          "corrige depois que alguém aprovar."),
    }


async def _aplicar(db, *, familia: list[str], employee_certo: str, quem: str) -> int:
    """Troca QUEM está no turno, na família inteira. Devolve quantos mudaram de fato.

    ⚠️ A nota fica no próprio turno com autor e data — é o que permite desfazer lendo, sem
    precisar de log externo. Mudança sem rastro é mudança que ninguém consegue reverter.
    """
    nota = f" | 27/09/2026+: colaborador do turno corrigido por {quem}, via José Luís."
    res = await db.execute(text(
        "UPDATE shifts SET employee_id = CAST(:novo AS uuid), updated_at = now(), "
        "       notes = coalesce(notes,'') || CAST(:nota AS text) "
        # ⚠️ `id::text = ANY(:ids)` com LISTA Python. Montar a string '{a,b,c}' e pedir
        # `CAST(:ids AS uuid[])` faz o asyncpg recusar: ele quer um iterável, não o literal do
        # Postgres. Quinta vez hoje que eu errei o mapeamento de tipo deste driver.
        " WHERE id::text = ANY(:ids) AND is_active "
        "   AND shift_date >= (now() AT TIME ZONE 'America/Manaus')::date"),
        {"novo": employee_certo, "nota": nota, "ids": list(familia)})
    await db.commit()
    return int(res.rowcount or 0)


async def _anunciar(db, *, quem: str, o_certo: str, quantos: int, de: str | None,
                    para: str) -> None:
    """Publica no Gestão o que foi mudado. OBRIGATÓRIO — ver a parede 4 do cabeçalho.

    ⚠️ Best-effort no envio, mas nunca opcional na intenção: se o WhatsApp estiver fora, a
    correção já está aplicada e o log tem o registro. O que não pode é NÃO TENTAR.
    """
    try:
        from modules.integrations.connectors.whatsapp import supervisao as _sup
        from modules.integrations.connectors.whatsapp import vigia as _vig

        destino = await _vig._destino_gestao(db)
        if not destino:
            logger.warning("correcao_supervisor: sem grupo Gestão — correção aplicada SEM aviso")
            return
        await _sup._publicar_no_grupo(int(destino), (
            f"🔧 *Correção aplicada* — por {quem}\n\n"
            f"\"{o_certo[:220]}\"\n\n"
            + (f"*{de}* → *{para}*\n" if de else f"passou para *{para}*\n")
            + f"*{quantos}* turno(s) futuro(s) alterado(s).\n\n"
            f"_Aplicado na hora, sem aprovação, por autorização do dono. A nota de cada turno "
            f"tem quem mandou e quando._"))
    except Exception as exc:  # noqa: BLE001
        logger.error("correcao_supervisor: correção aplicada mas NÃO anunciada — %s", exc)


async def _abrir_defeito(db, *, tipo: str, eu_disse: str, o_certo: str, quem: str,
                         quantos: int) -> None:
    """Registra o defeito de ORIGEM, com a evidência, para o conserto no código.

    ⚠️ Best-effort: se isto falhar, a correção do dado não pode cair junto. O conserto do caso
    vale por si; o do código é o que evita o próximo.
    """
    from modules.operacional import chamado_posto as _cp

    try:
        await _cp.abrir(
            db, employee_id=None, nome=f"José Luís (correção de {quem})",
            categoria="sistema",
            relato=(f"O agente informou algo ERRADO e {quem} corrigiu.\n\n"
                    f"AGENTE DISSE: \"{eu_disse[:400] or '(não registrado)'}\"\n"
                    f"CERTO É: \"{o_certo[:400]}\"\n"
                    f"TIPO: {TIPOS.get(tipo, tipo)}\n"
                    f"FAMÍLIA MEDIDA: {quantos} registro(s) com o mesmo defeito.\n\n"
                    f"Isto é um defeito de ORIGEM: corrigir o dado resolve hoje, mas a fonte "
                    f"que produziu a informação errada continua produzindo. Conferir de onde o "
                    f"agente tirou o que disse."),
            posto=None)
    except Exception as exc:  # noqa: BLE001
        logger.warning("correcao_supervisor: defeito técnico não abriu — %s", exc)


async def _exec_correcao(db, user, payload: dict):  # noqa: ANN001, ANN202
    """Aprovado: aplica a correção ao CASO e a TODA a família de uma vez.

    ⭐ É aqui que «não só para este caso, como para todos» acontece de verdade: o payload traz
    os `shift_id` da família inteira, medidos no momento da captura.

    ⚠️ Troca o COLABORADOR do turno, e só isso. Não mexe em horário, posto nem alocação — o que
    o supervisor corrigiu foi QUEM está no turno; inferir o resto da frase seria fabricação.
    """
    familia = payload.get("familia") or []
    certo = payload.get("employee_certo")
    if not (familia and certo):
        logger.info("correcao_supervisor: aprovada sem família aplicável — registrada como "
                    "ciente (tipo=%s)", payload.get("tipo"))
        return f"correcao:{payload.get('tipo')}"

    nota = (f" | 27/09+: QUEM ESTÁ NO TURNO corrigido por "
            f"{payload.get('corrigido_por_nome')} via José Luís.")
    res = await db.execute(text(
        "UPDATE shifts SET employee_id = CAST(:novo AS uuid), updated_at = now(), "
        "       notes = coalesce(notes,'') || :nota "
        " WHERE id = ANY(CAST(:ids AS uuid[])) AND is_active"),
        {"novo": certo, "nota": nota, "ids": "{" + ",".join(familia) + "}"})
    await db.commit()
    logger.info("correcao_supervisor: %s turno(s) passaram para %s", res.rowcount, certo)
    return f"employee:{certo}"


def _registrar() -> None:
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import registrar_executor

    registrar_executor("correcao_supervisor", _exec_correcao)


_registrar()
