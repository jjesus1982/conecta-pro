"""F1 — a parede que faz a etiqueta 🟡 do manifesto AGIR.

Achado que originou (23/08/2026): `tool_risk_manifest` classificava 254 ferramentas e
`server.py` tinha ZERO referências a ele. As 54 classificações que corrigi eram etiquetas
num crachá que nenhum porteiro pedia. O único filtro vivo era `tool_scopes`, que corta por
ASSUNTO — e conter risco por assunto funciona por acidente quando tema e risco coincidem, e
falha calado quando não coincidem (`enviar_whatsapp` está em "comercial" e envia ao cliente).

O que esta parede faz, num conector marcado como AGENTE (`MCP_MODO=agente`):

    read        executa normalmente
    write_low   executa normalmente (interno, reversível)
    propose     NÃO EXECUTA — vira rascunho inerte na Central de Aprovações

A regra que a define: **quem aprova não pode ser quem pede.** A versão anterior do
`aceitar_proposta` pedia `confirmar="ACEITAR"` e devolvia essa própria senha na resposta —
para um humano lendo no Cowork era um bom aviso; para um modelo que lê a resposta era um
degrau que imprime como subir. Confirmação preenchida por quem pede é formulário, não
aprovação.

E o aprovador precisa ver a CONSEQUÊNCIA, não o nome da função. "Aprovar aceitar_proposta?"
não é decisão informada; "aceitar a proposta X: gera comissão, move o deal e cria contrato"
é. Por isso `CONSEQUENCIAS` carrega o que cada ação provoca, e é isso que vai para a tela.
"""
from __future__ import annotations

import os
from typing import Any

try:
    from tool_risk_manifest import TOOL_RISK
except Exception:  # noqa: BLE001 — sem manifesto, a parede fecha (ver `classe_de`)
    TOOL_RISK = {}

# Ligado só onde o chamador é AGENTE. No conector do Jordan (Cowork) a pessoa lê e decide na
# hora — pôr a parede lá seria transformar decisão informada em fila.
MODO_AGENTE = (os.getenv("MCP_MODO") or "").strip().lower() == "agente"

# O que o APROVADOR vê. Uma linha por consequência real, em português de gente.
# Ausente = a parede ainda barra, e a tela diz que a consequência não foi declarada — o que
# é pior de ler e melhor de errar do que uma aprovação às cegas.
CONSEQUENCIAS: dict[str, list[str]] = {
    "aceitar_proposta": [
        "marca a proposta como ACEITA",
        "GERA COMISSÃO para o vendedor (nasce pendente, mas é obrigação registrada)",
        "move a oportunidade para closed_won",
        "cria um CONTRATO em rascunho",
    ],
    "fechar_folha": ["FECHA a folha do mês — depois disso o cálculo não se refaz sozinho"],
    "calcular_folha_todos": ["recalcula a folha de TODOS os colaboradores do mês"],
    "fechar_mes_ponto": ["FECHA o mês do ponto; batida nova deixa de entrar na apuração"],
    "aprovar_ferias": ["APROVA as férias — vira evento de eSocial e afeta a folha"],
    "calcular_verbas_rescisorias": ["calcula rescisão — base do TRCT e do pagamento final"],
    "concluir_admissao": ["conclui a admissão e dispara os eventos de admissão"],
    "lancar_diaria": ["LANÇA DIÁRIA — vira valor a pagar ao diarista"],
    "gerar_lote_diarias_mes": ["programa as diárias do mês inteiro — dinheiro a pagar"],
    "registrar_custo_recorrente": ["cria custo recorrente que passa a entrar no fluxo"],
    "enviar_whatsapp": ["ENVIA MENSAGEM REAL ao cliente, em nome da empresa"],
    "enviar_nps": ["dispara pesquisa de NPS ao cliente"],
    "enviar_proposta": ["ENVIA a proposta ao cliente"],
    "enviar_proposta_completa": ["ENVIA a proposta completa ao cliente"],
    "enviar_proposta_whatsapp": ["ENVIA a proposta por WhatsApp ao cliente"],
    "followup_whatsapp": ["envia follow-up ao cliente"],
    "followup_em_lote": ["envia follow-up EM LOTE — várias pessoas de uma vez"],
    "inscrever_em_sequencia": ["inscreve numa régua que passa a ENVIAR sozinha"],
    "inscrever_lead_em_sequencia": ["inscreve o lead numa régua que passa a ENVIAR sozinha"],
    "expurgar_documentos_teste": ["APAGA documentos — irreversível"],
    "ativar_contrato": ["submete o contrato, tirando-o de rascunho"],
    "gerar_parecer_juridico": ["cria PARECER JURÍDICO no nome do escritório"],
    "analisar_processo_juridico": ["cria registro de processo jurídico"],
    "montar_kit_completo": ["dispara a montagem COMPLETA do kit (vários documentos)"],
    "buscar_documento": ["dispara montagem de kit para localizar o documento"],
    "solicitar_ferias": ["cria solicitação de férias em nome do colaborador"],
    # 11/09/2026 — as cinco que subiram de `read` para `propose` quando a etiqueta passou a
    # ser derivada do VERBO HTTP (ver tool_risk_manifest e checar_etiqueta_de_risco).
    "revisar_justificativa_ponto": [
        "APROVA ou REJEITA a justificativa de falta/atraso de uma pessoa",
        "a folha lê essa decisão no fechamento do mês — mexe no pagamento dela",
    ],
    "definir_parametros_precificacao": [
        "muda o parâmetro de onde sai TODO preço cotado a partir de agora",
        "os seis valores foram confirmados um a um contra o holerite em 10/08",
    ],
    "atualizar_contrato": ["altera um CONTRATO — título executivo, não campo de tela"],
    "excluir_campanha": ["APAGA a campanha de verdade (DELETE, sem soft delete)"],
    "excluir_documento": [
        "manda um arquivo do kit para a LIXEIRA do Drive",
        "confira o file_id: três notas fiscais seguidas parecem cópia uma da outra e não são",
    ],
}


def classe_de(nome: str) -> str:
    """Classe de risco da tool. DESCONHECIDA = `propose` — fail-closed.

    Tool nova sem etiqueta não pode executar sozinha só porque ninguém a classificou. É a
    mesma postura do `tool_scopes`: no caso desconhecido, a parede fecha.
    """
    return TOOL_RISK.get(nome) or "propose"


# ⭐ EFEITO EXTERNO — aprovação humana em QUALQUER MODO, não só no de agente.
#
# Descoberto na auditoria do Cowork em 11/09/2026. `enviar_link_assinatura` ESTAVA
# classificada `propose`, e mesmo assim passou: `precisa_aprovacao` era
# `MODO_AGENTE and classe == "propose"`, e o conector público (o Cowork do Jordan) não é
# modo agente. Ou seja, a parede não existia nele — nem para a chamada direta.
#
# O raciocínio que criou o buraco foi meu, e era quase certo: "parede mais rígida que a
# porta da frente não protege nada, porque quem quisesse burlar usava o caminho direto".
# Isso vale para IDENTIDADE, onde a porta da frente é aberta de propósito para o dono.
# Não vale aqui: nestas ações a porta da frente aberta É o defeito. Quem chama o conector
# público é um LLM agindo em nome do Jordan, não o Jordan clicando um botão — e a regra
# "quem aprova não pode ser quem pede" vale para o LLM nos dois modos.
#
# O valor é O QUE SAI, e ele vai na recusa: o dono precisa saber o que teria acontecido,
# não o nome de uma função.
EFEITO_EXTERNO: dict[str, str] = {
    "enviar_link_assinatura": "um e-mail com link de assinatura, para o CLIENTE",
    "enviar_proposta": "a proposta por e-mail, para o cliente",
    "enviar_proposta_completa": "a proposta com anexos por e-mail, para o cliente",
    "enviar_proposta_whatsapp": "a proposta por WhatsApp, para o número do cliente",
    "enviar_whatsapp": "uma mensagem de WhatsApp, para fora da empresa",
    "enviar_nps": "a pesquisa de satisfação, para os clientes",
    "followup_whatsapp": "um follow-up por WhatsApp, para o cliente",
    "followup_em_lote": "follow-ups em LOTE — vários clientes de uma vez",
    "inscrever_em_sequencia": "inscreve o contato numa régua que dispara mensagens sozinha",
    "assinar_contrato_empresa": "a assinatura da empresa no instrumento, com o certificado "
                                "ICP-Brasil — é ato jurídico, não rascunho",
    "propor_pagamento": "um pagamento para a fila de dinheiro que SAI",
    "gerar_lote_diarias_mes": "o lote de pagamento das diárias — dinheiro que sai",
}

# Exceções revisadas à mão: nome parece de efeito externo e o efeito é interno. Cada linha é
# uma decisão registrada, lida na ROTA — não uma gaveta.
NAO_SAI_DA_EMPRESA: dict[str, str] = {
    "cadastrar_whatsapp_cliente": "POST /crm/whatsapp/cadastrar — grava e normaliza o "
                                  "número no cadastro; não manda mensagem nenhuma",
    "gerar_apresentacao": "POST /crm/apresentacoes/gerar — produz o arquivo; enviar é outro "
                          "passo, feito por outra ferramenta",
}


def efeito_externo(nome: str) -> str:
    """O que sai da empresa se esta ferramenta rodar. Vazio = não sai nada."""
    return EFEITO_EXTERNO.get(nome, "")


def precisa_aprovacao(nome: str) -> bool:
    # a ordem importa: efeito externo NÃO depende do modo.
    if nome in EFEITO_EXTERNO:
        return True
    return MODO_AGENTE and classe_de(nome) == "propose"


def consequencias(nome: str) -> list[str]:
    return CONSEQUENCIAS.get(nome) or [
        f"consequência de `{nome}` NÃO declarada em gate_propose.CONSEQUENCIAS — "
        "aprove só se souber o que ela faz"
    ]


def _quem_pede() -> str:
    """Nome do agente que pediu, declarado pelo conector (`MCP_AGENTE_NOME`)."""
    return (os.getenv("MCP_AGENTE_NOME") or "").strip() or "agente (não declarou o nome)"


def payload_de_aprovacao(nome: str, argumentos: dict[str, Any]) -> dict[str, Any]:
    """O que a Central mostra. Consequência primeiro, nome da função depois."""
    return {
        "acao": nome,
        "vai_acontecer": consequencias(nome),
        "argumentos": argumentos,
        # 11/09/2026: era a string fixa "agente (Bartolo)" — e quem pede pode ser o Hermes,
        # o Bartolo ou o José Luís. Quem aprova precisa saber QUEM pediu; nome errado na tela
        # de aprovação é pior que nome nenhum.
        "pedido_por": _quem_pede(),
        "classe": classe_de(nome),
    }


# ── A PAREDE PROPRIAMENTE DITA ────────────────────────────────────────────────────────
# `on_call_tool` do FastMCP 3.4 (API pública, conferida no container antes de usar — hoje
# eu já tinha errado uma internal supondo `_tool_manager`). É AQUI que a etiqueta 🟡 do
# manifesto deixa de ser adesivo e vira porteiro: `propose` não chega a `call_next`.
# FastMCP chama o middleware como CALLABLE para despachar cada tipo de requisição; só o
# `on_call_tool` não basta. Classe duck-typed derrubava `initialize` com
# "'GatePropose' object is not callable" — e era ESSA a razão do Hermes ficar parked, não o
# conector fora do ar (meu curl viu HTTP 200 e parou; o 200 trazia erro JSON-RPC no corpo).
# Fallback para `object` quando o fastmcp não está importável: as travas rodam no HOST.
try:
    from fastmcp.server.middleware import Middleware as _Base
except Exception:  # noqa: BLE001
    _Base = object

class GatePropose(_Base):
    """Barra `propose` e devolve o pedido de aprovação, sem executar nada."""

    async def on_call_tool(self, context, call_next):  # noqa: ANN001
        nome = getattr(getattr(context, "message", None), "name", "") or ""
        if not precisa_aprovacao(nome):
            return await call_next(context)

        args = getattr(getattr(context, "message", None), "arguments", None) or {}
        pedido = payload_de_aprovacao(nome, dict(args))

        # LEVA o pedido ao humano. Sem isto o gate só recusa, e o dono nunca fica sabendo
        # que foi pedido — a ação morreria na conversa, invisível.
        registro = ""
        try:
            import server as _srv  # noqa: PLC0415

            r = await _srv.erp.post("/agente/pedir-aprovacao", json=pedido)
            if isinstance(r, dict) and r.get("ok"):
                registro = f"\n\n📋 {r.get('message', 'Pedido registrado.')}"
            else:
                registro = f"\n\n⚠️ NÃO consegui registrar o pedido: {str(r)[:120]}"
        except Exception as _e:  # noqa: BLE001
            # A recusa vale MESMO sem registro — a parede não depende da Central estar de
            # pé. Mas dizer que registrou sem ter registrado seria a pior das saídas.
            registro = f"\n\n⚠️ NÃO consegui registrar o pedido ({str(_e)[:90]}) — leve à mão."
        # NÃO devolve "como confirmar". A versão anterior imprimia a própria senha
        # (confirmar="ACEITAR") — degrau que ensina a subir. Aqui não há degrau: a
        # aprovação acontece em OUTRA superfície, com OUTRA pessoa.
        sai = efeito_externo(nome)
        cabeca = (
            f"⛔ `{nome}` não é executada por mim. Se eu rodar isto, SAI DA EMPRESA: "
            f"{sai}.\n\nIsso não se desfaz — e quem recebe é uma pessoa de verdade, "
            f"não um registro."
            if sai else
            f"⛔ `{nome}` não é executada por mim. É uma ação de classe "
            f"{pedido['classe']} — precisa de aprovação humana."
        )
        texto = (
            cabeca + "\n\n"
            "O que ela provocaria:\n"
            + "\n".join(f"  • {c}" for c in pedido["vai_acontecer"])
            + "\n\nEu não tenho como aprovar o que eu mesmo pedi."
            + registro
        )
        from fastmcp.exceptions import ToolError  # noqa: PLC0415

        raise ToolError(texto)


def instalar(mcp) -> bool:
    """SEMPRE instala. Quem decide o que barrar é `precisa_aprovacao`, não o instalador.

    ⚠️ Antes isto devolvia False fora do modo agente e não instalava nada — e era aí que o
    buraco morava: no conector público, `enviar_link_assinatura` chegava ao ERP sem passar
    por parede nenhuma. Classificar a ferramenta corretamente não adianta se o middleware
    que lê a classificação não está no caminho.

    Fora do modo agente ela continua deixando passar tudo que NÃO tem efeito externo, então
    instalar sempre não muda o dia de ninguém — só fecha a porta que não podia estar aberta.
    """
    mcp.add_middleware(GatePropose())
    return True
