"""Triagem diária do ponto pelo HERMES — o laço que faz o agente trabalhar sem ser chamado.

Decisão do Jordan, 11/09/2026: *"quero o Hermes realmente inteligente... quero que tudo
funcione para coleta e resolução de problemas"*. Acesso sem laço é um agente que só existe
quando alguém lembra dele; o valor aparece quando ele olha TODO dia, no mesmo horário, com a
mesma régua — e chama a atenção só quando há o que fazer.

Como a entrega foi decidida, e por quê:
  · **Sino** (`communication_notifications`) sempre — é o registro, e é onde a Pyetra e o DP
    olham a fila. Fica gravado mesmo em dia tranquilo.
  · **WhatsApp ao Jordan só quando há gente a checar.** Mensagem diária que quase sempre diz
    "está tudo bem" é como se aprende a ignorar um canal, e o custo disso já foi pago aqui
    (o sino virou ruído por exatamente isso). Silêncio honesto é o padrão.

O texto é do Hermes, não meu: ele lê o ponto com as ferramentas do conector `pessoas`, aplica
a skill `triagem-de-ponto` e escreve. Aqui só se decide QUANDO ele olha e PARA QUEM vai.
"""
from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_TZ = ZoneInfo("America/Manaus")

#: O pedido. Curto de propósito: o COMO está na skill, versionada com o agente — repetir a
#: régua aqui criaria duas fontes que divergem, e a que diverge cala.
PEDIDO = (
    "Faça a triagem do ponto de hoje ({data}) seguindo a skill `triagem-de-ponto`. "
    "Quero: quem está sem batida no turno de hoje e POR QUÊ (separando atraso de importação "
    "do Tangerino, divergência de escala e ausência real), o que já está resolvido, o que "
    "depende do DP e o que depende de correção de cadastro.\n\n"
    "No FIM da resposta, escreva uma última linha exatamente neste formato, sem mais nada:\n"
    "PRECISAM_DE_GENTE: <número> | <nomes separados por vírgula, ou '—'>"
)

#: Teto do que vai para o WhatsApp do Jordan. O relato inteiro fica no sino.
_LIMITE_WHATSAPP = 700


def _linha_resumo(texto: str) -> tuple[int, str]:
    """Lê a última linha `PRECISAM_DE_GENTE: n | nomes`. Sem ela, devolve (-1, '').

    -1 não é zero: "não sei" e "não há ninguém" são estados diferentes, e tratá-los igual
    faria um dia em que o agente mudou de formato virar um dia silenciosamente tranquilo.
    """
    for linha in reversed((texto or "").strip().splitlines()):
        if linha.strip().upper().startswith("PRECISAM_DE_GENTE:"):
            corpo = linha.split(":", 1)[1]
            parte_num, _, nomes = corpo.partition("|")
            digitos = "".join(c for c in parte_num if c.isdigit())
            return (int(digitos) if digitos else -1), nomes.strip()
    return -1, ""


def _publicar_no_sino(titulo: str, corpo: str, chave: str) -> int:
    from sqlalchemy import text as sql

    from core.database.session import SyncSessionLocal
    from modules.notifications.task_falha import _SQL_DESTINATARIOS, _SQL_SINO

    import json

    extra = json.dumps({"idempotency_key": chave, "origem": "triagem_ponto_hermes",
                        "familia": "operacional", "severidade": "aviso"})
    enviados = 0
    with SyncSessionLocal() as db:
        for (uid,) in db.execute(sql(_SQL_DESTINATARIOS)).all():
            db.execute(sql(_SQL_SINO), {"uid": uid, "title": titulo[:180],
                                        "body": corpo[:8000], "extra": extra})
            enviados += 1
        db.commit()
    return enviados


async def rodar(hoje: str | None = None) -> dict:
    """Pede a triagem ao Hermes, grava no sino e avisa o Jordan se houver gente a checar."""
    from modules.ai.conversation.services.hermes_client import (
        HermesIndisponivel,
        perguntar_hermes,
    )

    data = hoje or datetime.now(_TZ).strftime("%d/%m/%Y")
    try:
        texto, meta = await perguntar_hermes(
            [{"role": "user", "content": PEDIDO.format(data=data)}],
            system_prompt="Você é o Hermes da Conecta Mais fazendo a triagem diária do ponto.",
            timeout=600.0,
        )
    except HermesIndisponivel as e:
        # Falha do agente NÃO some: o sino existe justamente para o dia em que ele não olhou.
        _publicar_no_sino("Triagem de ponto NÃO rodou",
                          f"O Hermes não respondeu hoje ({data}): {e}\n\n"
                          "Ninguém olhou o ponto por aqui — isto não é 'dia tranquilo'.",
                          f"triagem_ponto:{data}:falha")
        logger.error("triagem de ponto: Hermes indisponível — %s", e)
        return {"ok": False, "erro": str(e)[:200]}

    quantos, nomes = _linha_resumo(texto)
    _publicar_no_sino(f"Triagem de ponto — {data}", texto, f"triagem_ponto:{data}")

    avisou = False
    if quantos > 0 or quantos == -1:
        # -1 entra aqui de propósito: se o agente não fechou a linha de resumo, eu não sei se
        # há alguém a checar — e a dúvida vai para o humano, não para o silêncio.
        cabeca = (f"🕐 Triagem de ponto {data}: {quantos} pessoa(s) precisam de checagem"
                  if quantos > 0 else
                  f"🕐 Triagem de ponto {data}: o Hermes não fechou o resumo — confira o sino")
        corpo = f"{cabeca}\n{nomes}" if nomes and nomes != "—" else cabeca
        try:
            from modules.crm.services.orchestration import notify_owner

            avisou = await notify_owner(corpo[:_LIMITE_WHATSAPP])
        except Exception as e:  # noqa: BLE001 — aviso é entrega, não é a triagem
            logger.warning("triagem de ponto: não consegui avisar o dono — %s", e)

    logger.info("triagem de ponto %s: %s caracteres, precisam_de_gente=%s, avisou_dono=%s",
                data, len(texto), quantos, avisou)
    return {"ok": True, "data": data, "precisam_de_gente": quantos, "avisou_dono": avisou,
            "caracteres": len(texto), "modelo": meta.get("model")}
