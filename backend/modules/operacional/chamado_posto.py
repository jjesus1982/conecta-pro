"""Relato de ocorrência no posto vira CHAMADO na tela, não morre numa conversa transferida.

🔴 POR QUE ESTE ARQUIVO NASCEU EM 26/09/2026 — o caso que o Jordan viu acontecer:

O **MAURÍCIO ALVES CHAGAS**, do Green Hills, escreveu às 18:15: *"COMUNICO-VÓS QUE O LEITOR
FACIAL PASSOU O DIA SEM REGISTRA QUEM ENTROU NO CONDOMÍNIO COM A FACIAL"*. Um dia inteiro sem
registro de acesso num condomínio de cliente — buraco de segurança e possível cobrança.

O agente **transferiu a conversa para "suporte técnico" no Chatwoot** às 18:16 e **não abriu
nada no ERP**. Fui conferir e medi: zero rascunhos naquela hora, e as três tabelas de ocorrência
da casa — `op_chamados`, `op_supervisao_ocorrencias`, `client_tickets` — **vazias, nunca usaram
uma linha**. O relato passou a existir só numa conversa de WhatsApp atribuída a um time: se
ninguém abrisse aquela conversa, ninguém no sistema saberia.

⭐ É o padrão que o dono nomeou como o mais caro desta casa: **a dívida quase nunca é código
faltando — é código DESLIGADO.** `op_chamados` tem o esquema mais rico das três (`numero` com
sequência, `post_id`, `canal`, `categoria`, `prioridade`, `sla_min`, `atribuido_a`), **8
consumidores no código** e uma TELA que lista os abertos com SLA vencido
(`_dgx_f8_operacional`). A tela existia, olhando uma tabela vazia.

## Por que abre DIRETO e não como rascunho

`pendencia_dp` cria rascunho porque o que ela pede é DECISÃO (corrigir espelho, validar batida).
Aqui o que falta é **registro**: o fato já aconteceu e alguém precisa ver. Um rascunho esperando
aprovação manteria o relato invisível, que é exatamente o defeito. Abrir chamado não muda escala,
não mexe em dinheiro e não fala com o governo — é a anotação que faltava.

⚠️ NÃO é escala nem alocação. O operacional continua curado à mão pelo Jordan; isto só registra
o que a pessoa do posto relatou, com as palavras dela.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Lista FECHADA, como em `pendencia_dp.ASSUNTOS`. Categoria nova entra aqui com nome, e não
#: por texto livre do modelo — senão a tela vira caixa de entrada sem dono e o filtro por
#: categoria deixa de significar algo.
CATEGORIAS: dict[str, str] = {
    "equipamento": "equipamento do condomínio com defeito (leitor facial, câmera, portão, "
                   "interfone, nobreak)",
    "estrutura": "problema de estrutura ou instalação no posto (luz, água, guarita, mobiliário)",
    "material": "faltou material de trabalho (uniforme, EPI, papel, caneta, livro de registro)",
    "seguranca": "ocorrência de segurança (invasão, furto, dano, pessoa suspeita, acidente)",
    "cliente": "reclamação ou pedido do síndico, morador ou preposto do cliente",
    "sistema": "sistema da Conecta PRO com problema no posto (app, portal, ponto, internet)",
    "outro": "outra ocorrência do posto relatada por quem está lá",
}

#: Equipamento de controle de acesso e segurança sobem a prioridade sozinhos: um dia sem
#: registro de quem entrou é risco que não espera fila normal.
_ALTA = {"equipamento", "seguranca"}


async def abrir(db, *, employee_id: str | None, nome: str, categoria: str, relato: str,
                posto: str | None = None) -> dict[str, Any]:
    """Abre o chamado pelo SERVIÇO OFICIAL e devolve o que o agente deve dizer à pessoa.

    ⭐ CHAMA `supervisao_service.abrir_chamado`, não um INSERT meu. Minha primeira versão
    escrevia direto na tabela e estourou na hora: passei o `employee_id` (uuid, 36 chars) em
    `aberto_por`, que é **varchar(20)** e guarda RÓTULO — `cliente`, `supervisor`,
    `colaborador`, `sistema`. O serviço já valida isso, numera, calcula SLA e notifica o setor.
    Escrever à mão era reimplementar o que existe e errar no primeiro campo.

    ⚠️ `aberto_por='colaborador'`: quem relata é a pessoa do posto. É o rótulo da casa, não
    inventado — vem de `supervisao_service.ABERTO_POR`.

    O `post_id` sai da ALOCAÇÃO ativa de quem relatou — é o que o Jordan cura à mão. Sem
    alocação o chamado nasce sem posto em vez de nascer com um posto chutado.
    """
    from sqlalchemy import text as _t

    from modules.operacional.services import supervisao_service as _ss

    categoria = categoria if categoria in CATEGORIAS else "outro"
    relato = (relato or "").strip()
    if len(relato) < 15:
        # Relato curto não é chamado: é ruído que alguém vai ter de perguntar de novo.
        return {"ok": False, "motivo": "relato muito curto — descreva o que aconteceu, onde e "
                                       "desde quando, com as palavras da pessoa"}

    post_id = None
    if employee_id:
        post_id = (await db.execute(_t(
            "SELECT ea.posto_id::text FROM employee_alocacoes ea "
            " WHERE ea.employee_id = CAST(:e AS uuid) AND ea.ativo LIMIT 1"),
            {"e": employee_id})).scalar()

    prioridade = "alta" if categoria in _ALTA else "normal"
    try:
        r = await _ss.abrir_chamado(
            db, descricao=relato, post_id=post_id, aberto_por="colaborador",
            solicitante_nome=nome[:120], canal="whatsapp", categoria=categoria,
            prioridade=prioridade,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("chamado_posto: NÃO abri o chamado de %s (%s) — %s", nome, categoria, exc,
                     exc_info=True)
        # ⚠️ Fala a verdade ao agente: se ele disser "registrei" sem ter registrado, a pessoa
        # confia num chamado que não existe.
        return {"ok": False, "motivo": f"falha ao abrir o chamado: {str(exc)[:160]}"}

    numero = r.get("numero") or r.get("chamado", {}).get("numero")
    logger.info("chamado_posto: #%s aberto por %s — %s (prioridade %s)",
                numero, nome, categoria, prioridade)
    return {
        "ok": True,
        "numero": numero,
        "categoria": CATEGORIAS[categoria],
        "prioridade": prioridade,
        "sem_posto": post_id is None,
        "servico": r,
        "msg": (f"Abri o chamado *#{numero}* com o seu relato. Ele já aparece na tela do "
                "operacional e alguém vai tratar — quando tiver resposta eu te aviso aqui."),
        "diga_a_pessoa": ("Confirme o NÚMERO do chamado a ela: é o que permite ela cobrar "
                          "depois. E se for equipamento de acesso ou segurança, oriente o "
                          "registro MANUAL enquanto não normaliza — o condomínio não pode "
                          "ficar sem registro nenhum."),
    }
