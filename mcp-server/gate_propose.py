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
    # ⭐ As de EFEITO EXTERNO vêm primeiro porque são as que o aprovador mais precisa
    # entender — e eram justamente as que estavam mudas. Validação do Cowork (11/09/2026):
    # a parede segurava `enviar_link_assinatura` e `assinar_contrato_empresa`, mas quem
    # abrisse o pedido lia "consequência NÃO declarada — aprove só se souber o que ela faz".
    # Pedir aprovação sem dizer o que se aprova é pedir assinatura em branco.
    "enviar_link_assinatura": [
        "MANDA UM E-MAIL, agora, para o endereço do CLIENTE",
        "o e-mail leva um link que abre a plataforma de assinatura",
        "a partir daí o cliente pode ASSINAR — e um contrato assinado não se desfaz",
        "se o contrato estiver com dado errado, o erro vai junto e com a sua marca",
        "não há 'cancelar envio': e-mail entregue foi lido ou não, e isso você não controla",
    ],
    "assinar_contrato_empresa": [
        "APLICA a assinatura da empresa no instrumento, com o certificado ICP-Brasil",
        "é ATO JURÍDICO: vincula a Conecta Mais ao que está escrito no contrato",
        "carimba hash, IP e horário no manifesto — a trilha fica, inclusive do erro",
        "assinar antes de conferir a cláusula é assinar a cláusula errada",
    ],
    "enviar_proposta": [
        "MANDA a proposta por e-mail ao cliente, com o preço que está lá dentro",
        "preço enviado é âncora de negociação: revisar depois custa desconto",
    ],
    "enviar_proposta_completa": [
        "MANDA a proposta COM OS ANEXOS por e-mail ao cliente",
        "anexo errado é informação que sai da empresa e não volta",
    ],
    "enviar_proposta_whatsapp": [
        "MANDA a proposta por WhatsApp, para o número cadastrado do cliente",
        "WhatsApp é lido em minutos — não há janela para corrigir",
    ],
    "enviar_nps": [
        "DISPARA a pesquisa de satisfação para os clientes da lista",
        "é envio em massa: um destinatário errado é um constrangimento por cliente",
    ],
    "followup_whatsapp": [
        "MANDA um follow-up por WhatsApp, agora, para o número do cliente",
        "WhatsApp é lido em minutos — não existe janela para corrigir o texto",
    ],
    "followup_em_lote": [
        "MANDA follow-ups para VÁRIOS clientes de uma vez",
        "erro em lote não é um erro: é um por destinatário",
    ],
    "inscrever_em_sequencia": [
        "INSCREVE o contato numa régua que dispara mensagens SOZINHA, nos próximos dias",
        "depois de inscrito, o envio não depende mais de ninguém apertar nada",
    ],
    "propor_pagamento": [
        "coloca um pagamento na fila do DINHEIRO QUE SAI",
        "a saída ainda exige OTP humano — mas a fila é onde o erro entra",
    ],
    "gerar_lote_diarias_mes": [
        "PROGRAMA o lote de pagamento das diárias do mês",
        "é dinheiro que sai: valor errado aqui vira pagamento errado lá",
    ],
    "fechar_folha": [
        "FECHA a folha do mês: os valores passam a ser os definitivos",
        "não existe reabrir — o que estiver errado vira holerite errado na mão de gente",
        "depois disso a correção é rescisão complementar ou acordo, não um clique",
    ],
    "fechar_mes_ponto": [
        "FECHA o mês do ponto: batida corrigida depois disso não entra mais",
        "a folha do mês passa a ser calculada sobre o que está fechado aqui",
    ],
    "calcular_verbas_rescisorias": [
        "calcula a RESCISÃO de uma pessoa específica",
        "valor errado aqui é passivo trabalhista, não linha de planilha",
    ],
    "lancar_diaria": [
        "lança uma diária A PAGAR, entrando na fila do dinheiro que sai",
        "diarista lançado tem direito a VT+VR programados automaticamente",
    ],
    "expurgar_documentos_teste": [
        "APAGA documentos do sistema — não há lixeira",
        "se o filtro pegar um documento real, ele não volta",
    ],
    "excluir_documento": [
        "APAGA o documento — não há lixeira",
        "documento anexado a contrato assinado é prova; apagado, não é mais",
    ],
    "excluir_campanha": [
        "APAGA a campanha e o histórico de disparos dela",
        "o que foi enviado continua enviado; só o registro desaparece",
    ],
    "aceitar_proposta": [
        "marca a proposta como ACEITA",
        "GERA COMISSÃO para o vendedor (nasce pendente, mas é obrigação registrada)",
        "move a oportunidade para closed_won",
        "cria um CONTRATO em rascunho",
    ],
    "calcular_folha_todos": ["recalcula a folha de TODOS os colaboradores do mês"],
    "aprovar_ferias": ["APROVA as férias — vira evento de eSocial e afeta a folha"],
    "concluir_admissao": ["conclui a admissão e dispara os eventos de admissão"],
    "registrar_custo_recorrente": ["cria custo recorrente que passa a entrar no fluxo"],
    "enviar_whatsapp": [
        "ENVIA MENSAGEM REAL, agora, para um número fora da empresa",
        "sai em nome da Conecta Mais — quem recebe lê como palavra da empresa",
        "mensagem entregue não se apaga do outro lado",
    ],
    "inscrever_lead_em_sequencia": ["inscreve o lead numa régua que passa a ENVIAR sozinha"],
    # 18/09/2026 — entrou em EFEITO_EXTERNO por autorização do Jordan
    "reativar_lead": [
        "o José Luís MANDA uma mensagem de WhatsApp agora, para o celular do lead",
        "sai em nome da Conecta Mais — quem recebe lê como palavra da empresa",
        "lead frio reabordado na hora errada queima de vez; não há como despedir a mensagem",
    ],
    # ⚠️ entrada REFORÇADA em 18/09/2026, não duplicada: ela já existia dizendo apenas
    # "submete o contrato", o que não é o que dói. Entrou em IRREVERSIVEL hoje, e quem vai
    # aprovar precisa ler o efeito no dinheiro.
    "ativar_contrato": [
        "o contrato passa a ATIVO e sai de rascunho para valer entre as partes",
        "sendo recorrente, o valor mensal ENTRA NO MRR — é de lá que nasce a cobrança",
        "reverter depois é cancelamento de contrato, com cliente na frente, não um clique",
    ],
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
    # ⭐ 18/09/2026 — autorizado pelo Jordan depois da rodada 4. `reativar_lead(confirmar=true)`
    # manda o José Luís dar um toque no lead por WhatsApp: sai da empresa, exatamente como
    # `followup_whatsapp`, que já estava aqui. Ela estava `write_low` e FORA do muro — o
    # mesmo efeito com duas classificações opostas, e a mais frouxa era a que ninguém tinha
    # olhado. Não é a tool que decide se precisa de aprovação, é o EFEITO.
    "reativar_lead": "um toque de WhatsApp para o lead frio, em nome da empresa",
}

# ⭐ IRREVERSÍVEL INTERNO — aprovação humana em QUALQUER MODO, como o efeito externo.
#
# Achado em 12/09/2026 medindo o R20: `fechar_folha` está classificado `propose` e mesmo
# assim EXECUTARIA no conector público, porque `precisa_aprovacao` dependia de MODO_AGENTE.
# Eram ONZE ações nessa situação, entre elas `expurgar_documentos_teste` (APAGA documentos)
# e `aceitar_proposta` (GERA COMISSÃO).
#
# É exatamente o defeito do CP-MCP-001 pela outra porta. O princípio que o Jordan aprovou
# lá vale aqui: quem chama o conector público é um LLM agindo em nome dele, não ele clicando
# — e ação sem desfazer pedida por um LLM precisa de decisão humana.
#
# CRITÉRIO da lista, para não inflar: entra o que DESTRÓI, o que cria obrigação de DINHEIRO,
# ou o que fecha período contábil/trabalhista. NÃO entra o que é recalculável
# (`calcular_folha_todos` roda de novo), nem o que só lê (`exportar_folha_dominio`), nem o
# que se desfaz administrativamente (`aprovar_ferias`). Parede que barra o trabalho normal
# vira parede que alguém desliga.
IRREVERSIVEL: dict[str, str] = {
    "fechar_folha": "FECHA a folha do mês — não existe reabrir, e o que estiver errado vira "
                    "holerite errado na mão de gente",
    "fechar_mes_ponto": "FECHA o mês do ponto; batida corrigida depois não entra mais",
    "calcular_verbas_rescisorias": "calcula a RESCISÃO de uma pessoa — valor errado aqui é "
                                   "passivo trabalhista, não linha de planilha",
    "aceitar_proposta": "GERA COMISSÃO a pagar e cria contrato: obrigação de dinheiro que "
                        "nasce registrada",
    "lancar_diaria": "lança uma diária a PAGAR — entra na fila do dinheiro que sai",
    "expurgar_documentos_teste": "APAGA documentos do sistema; não há lixeira",
    "excluir_documento": "APAGA o documento; não há lixeira",
    "excluir_campanha": "APAGA a campanha e o histórico dela",
    # ⭐ 18/09/2026 — autorizado pelo Jordan. `ativar_contrato` leva o contrato a `active` e,
    # sendo recorrente, LANÇA NO MRR: nasce faturamento recorrente registrado. Cabe no
    # critério escrito acima ("cria obrigação de DINHEIRO") e é irmão de `aceitar_proposta`,
    # que já estava aqui pela mesma razão. Era `propose` com o muro ABERTO no conector
    # público, porque `precisa_aprovacao` só valia para `propose` em modo agente — o mesmo
    # buraco que fechei para as outras onze em 12/09 e que esta escapou.
    "ativar_contrato": "ATIVA o contrato e lança o valor no MRR — faturamento recorrente "
                       "que nasce registrado, com cobrança atrás",
}

# Exceções revisadas à mão: nome parece de efeito externo e o efeito é interno. Cada linha é
# uma decisão registrada, lida na ROTA — não uma gaveta.
NAO_SAI_DA_EMPRESA: dict[str, str] = {
    "cadastrar_whatsapp_cliente": "POST /crm/whatsapp/cadastrar — grava e normaliza o "
                                  "número no cadastro; não manda mensagem nenhuma",
    "gerar_apresentacao": "POST /crm/apresentacoes/gerar — produz o arquivo; enviar é outro "
                          "passo, feito por outra ferramenta",
}


# Nome do código de recusa, fixado pela issue CP-MCP-001 e afirmado pelo caso R11 da suíte.
# Uma constante e não uma string solta nos três despachantes: a auditoria vai conferir o
# nome exato, e três literais divergem na primeira vez que alguém reescrever um deles.
CODIGO_APROVACAO = "REQUER_APROVACAO_HUMANA"


def efeito_externo(nome: str) -> str:
    """O que sai da empresa se esta ferramenta rodar. Vazio = não sai nada."""
    return EFEITO_EXTERNO.get(nome, "")


def por_que_exige_aprovacao(nome: str) -> str:
    """O que torna esta ação inegociável — vai na recusa, para o dono saber o que evitou."""
    return EFEITO_EXTERNO.get(nome) or IRREVERSIVEL.get(nome, "")


def envelope_recusa(nome: str, *, caminho: str = "") -> dict:
    """A recusa COMPLETA, igual nos quatro caminhos. Uma implementação, não quatro.

    ⭐ Validação do Cowork (12/09/2026): as quatro recusas vinham "byte a byte idênticas",
    só mudando o nome da tool — sem `vai_acontecer`, sem dizer que `fechar_folha` não tem
    desfazer, que `expurgar_documentos_teste` APAGA ou que `aceitar_proposta` gera COMISSÃO.
    Os três despachantes montavam a própria mensagem genérica e ignoravam o que o gate já
    sabia.

    "A parede sobe. Ela só não conta por que subiu" — e contar era o ponto do Bloco 10.
    """
    sai = EFEITO_EXTERNO.get(nome, "")
    irrev = IRREVERSIVEL.get(nome, "")
    if sai:
        cabeca = (f"`{nome}` não é executada por mim. Se eu rodar isto, SAI DA EMPRESA: "
                  f"{sai}. Isso não se desfaz — e quem recebe é uma pessoa de verdade.")
    elif irrev:
        cabeca = (f"`{nome}` não é executada por mim. O que ela faz NÃO TEM DESFAZER: "
                  f"{irrev}.")
    else:
        cabeca = (f"`{nome}` é ação de classe {classe_de(nome)} e precisa de aprovação "
                  f"humana.")
    fora = {
        "ok": False, "codigo": CODIGO_APROVACAO, "http": 403,
        "acao": nome, "classe": classe_de(nome),
        "mensagem": cabeca,
        "vai_acontecer": consequencias(nome),
        "sai_da_empresa": sai or None,
        "irreversivel": irrev or None,
        "dica": ("Eu não tenho como aprovar o que eu mesmo pedi. Leve à pessoa que decide — "
                 "a aprovação acontece em outra superfície, com OTP quando é dinheiro ou "
                 "assinatura."),
    }
    if caminho:
        # a dica adaptada ao caminho tentado, que o Cowork elogiou e vale manter
        fora["por_que_aqui_tambem"] = {
            "ensaiar": "Ensaio mostra o que faria; esta ação não é ensaiada nem executada.",
            "no_sandbox": "Sandbox não é caminho alternativo para aprovação humana.",
            "segundo_plano": "Segundo plano muda QUANDO, não O QUÊ.",
        }.get(caminho, "")
    return fora


def precisa_aprovacao(nome: str) -> bool:
    # a ordem importa: efeito externo e irreversível NÃO dependem do modo.
    if nome in EFEITO_EXTERNO or nome in IRREVERSIVEL:
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

class _SemRegistro(Exception):
    """Controle de fluxo: a recusa vale, e não há pedido a registrar (ensaio/sandbox)."""


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

            # ⭐ SÓ PRODUÇÃO cria pedido. Bloco 9 da validação: fila poluída por teste treina
            # humano a aprovar sem ler, e o dia em que um pedido legítimo chegar no meio de
            # cinco testes é o dia em que alguém assina o contrato errado clicando rápido.
            #
            # ⚠️ Medido em 12/09: `ensaiar`, `no_sandbox` e `executar_em_segundo_plano` JÁ
            # não chegavam aqui — eles recusam antes, sem registrar. A poluição da auditoria
            # veio de chamadas DIRETAS, que são produção legítima. Esta guarda existe para o
            # caso de alguém ligar um desses caminhos ao middleware depois; sem ela, a
            # regressão voltaria em silêncio.
            origem = "producao"
            if getattr(_srv, "_ENSAIO", None) is not None and _srv._ENSAIO.get() is not None:
                origem = "ensaio"
            elif getattr(_srv, "_SANDBOX", None) is not None and _srv._SANDBOX.get():
                origem = "sandbox"
            if origem != "producao":
                registro = (f"\n\n🧪 Origem `{origem}`: o muro disparou e NENHUM pedido foi "
                            f"criado na Central. Teste não entra na fila de quem decide.")
                raise _SemRegistro
            pedido["origem"] = origem
            r = await _srv.erp.post("/agente/pedir-aprovacao", json=pedido)
            if isinstance(r, dict) and r.get("ok"):
                registro = f"\n\n📋 {r.get('message', 'Pedido registrado.')}"
            else:
                registro = f"\n\n⚠️ NÃO consegui registrar o pedido: {str(r)[:120]}"
        except _SemRegistro:
            pass  # a mensagem já foi montada acima; a recusa continua valendo
        except Exception as _e:  # noqa: BLE001
            # A recusa vale MESMO sem registro — a parede não depende da Central estar de
            # pé. Mas dizer que registrou sem ter registrado seria a pior das saídas.
            registro = f"\n\n⚠️ NÃO consegui registrar o pedido ({str(_e)[:90]}) — leve à mão."
        # NÃO devolve "como confirmar". A versão anterior imprimia a própria senha
        # (confirmar="ACEITAR") — degrau que ensina a subir. Aqui não há degrau: a
        # aprovação acontece em OUTRA superfície, com OUTRA pessoa.
        sai = efeito_externo(nome)
        irrev = IRREVERSIVEL.get(nome, "")
        cabeca = (
            f"⛔ `{nome}` não é executada por mim. Se eu rodar isto, SAI DA EMPRESA: "
            f"{sai}.\n\nIsso não se desfaz — e quem recebe é uma pessoa de verdade, "
            f"não um registro."
            if sai else
            f"⛔ `{nome}` não é executada por mim. O que ela faz NÃO TEM DESFAZER: "
            f"{irrev}."
            if irrev else
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
        # ⭐ ENVELOPE + PROSA na mesma recusa. O agente precisa de `codigo`/`http` para
        # DECIDIR (e a suíte R11 afirma os dois); a pessoa precisa da frase para ENTENDER o
        # que quase aconteceu. Mandar só a prosa obriga o agente a interpretar texto — que é
        # como uma recusa vira "acho que deu erro, tento de novo". Mandar só o código
        # esconde do dono o que a ação faria.
        import json as _json  # noqa: PLC0415

        from fastmcp.exceptions import ToolError  # noqa: PLC0415

        # a MESMA função dos três despachantes: quatro caminhos, uma implementação. Quatro
        # textos separados foi exatamente como eles divergiram — os despachantes contavam
        # menos do que o gate já sabia.
        envelope = {**envelope_recusa(nome), "mensagem": texto}
        envelope["registro_na_central"] = registro.strip() or None
        raise ToolError(_json.dumps(envelope, ensure_ascii=False))


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
