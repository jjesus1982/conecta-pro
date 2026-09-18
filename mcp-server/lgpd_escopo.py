"""Escopo LGPD por ferramenta — Bloco 7 do prompt de 11/09/2026.

`folha_dp` expõe CPF, holerite, ASO, ficha de funcionário, dado de saúde ocupacional. Parte
é dado pessoal; parte é dado pessoal SENSÍVEL (art. 5º, II da LGPD — saúde).

Pedido textual do Jordan: *"Não pretendo abrir esse domínio por conta própria. Preciso que o
sistema DECLARE o escopo, em vez de eu decidir caso a caso."*

⭐ TRÊS NÍVEIS, e a fronteira é o QUE SE VÊ, não o que a tool faz:

  agregado                — totais, contagens, médias. Ninguém identificável.
  identificado_operacional — nome, função, posto, escala. Necessário para operar.
  sensivel                — CPF, holerite, salário individual, ASO, dado de saúde.

⚠️ FAIL-CLOSED: tool que toca pessoa e não está classificada aqui é tratada como
`sensivel`. Classificar 55 ferramentas à mão erra em algumas, e a errada tem de errar para
o lado que protege. `test_lgpd_escopo.py` reprova o build quando aparece uma sem classe.

⚠️ E o nível NÃO substitui a parede de identidade. Ele DECLARA o que a chamada vai acessar,
para o agente saber antes de acessar e para o log registrar o quê, não só o quem.

CONCESSÃO DE ESCOPO, não OTP por chamada: o Jordan autoriza uma LISTA de tools sensíveis que
o assistente pode ler em operação normal, com validade. OTP a cada holerite inviabiliza o
trabalho; concessão auditável não.
"""
from __future__ import annotations

import re
from datetime import date

NAO_SE_APLICA = "nao_se_aplica"
AGREGADO = "agregado"
OPERACIONAL = "identificado_operacional"
SENSIVEL = "sensivel"

O_QUE_SIGNIFICA = {
    NAO_SE_APLICA: "não toca dado de pessoa (contrato, proposta, saldo da empresa)",
    AGREGADO: "totais e contagens; nenhuma pessoa identificável",
    OPERACIONAL: "nome, função, posto, escala — o necessário para operar",
    SENSIVEL: "CPF, holerite, salário individual, ASO ou dado de saúde",
}

# ── A classificação, ferramenta por ferramenta ────────────────────────────────────────
NIVEL: dict[str, str] = {
    # agregado
    "folha_dashboard": AGREGADO,
    "estatisticas_funcionarios": AGREGADO,
    "resumo_folha": AGREGADO,
    "dashboard_operacional": AGREGADO,
    # 17/09/2026: AGREGADO significa "nenhuma pessoa identificável", mas a ferramenta recebe
    # `employee_id` como parâmetro — o resultado é de UMA pessoa, nomeada.
    "banco_horas": OPERACIONAL,
    "listar_rubricas_folha": AGREGADO,
    "divergencias_folha_pagamentos": AGREGADO,
    "gaps_esocial": AGREGADO,
    "estoque_epi": AGREGADO,
    # As dez que a trava cobrou, decididas pela ROTA de cada uma (não pelo nome):
    "ponto_dashboard": AGREGADO,                  # /ponto/dashboard — totais do mês
    "sst_dashboard": AGREGADO,                    # /sst/dashboard — contagens de SST
    "status_fechamento_ponto": AGREGADO,          # /ponto/fechamento/status — estado do mês
    "status_pcmso": AGREGADO,                     # /sst/pcmso/status — programa, não pessoa
    "status_ppra": AGREGADO,                      # /sst/ppra/status — idem
    "listar_eventos_esocial": AGREGADO,           # /esocial/eventos — fila de transmissão

    # identificado operacional
    "listar_funcionarios": OPERACIONAL,
    "buscar_funcionario": OPERACIONAL,
    # 17/09/2026: estava OPERACIONAL, cuja legenda é "nome, função, posto, escala". Chamada de
    # verdade contra o conector devolveu CPF, PIS e data de nascimento — que é a definição de
    # SENSIVEL. Como a trilha só registra o nível sensível (carimbo.py:71), esse acesso não
    # deixava rastro nominal nenhum. Promover não fecha o buraco do isolamento, mas faz o que
    # acontece ali passar a ser AUDITÁVEL.
    "obter_funcionario": SENSIVEL,
    "listar_alocacoes": OPERACIONAL,
    "alocacoes_vigentes": OPERACIONAL,
    "funcionarios_disponiveis_posto": OPERACIONAL,
    "colaboradores_sem_escala": OPERACIONAL,
    "substitutos_disponiveis": OPERACIONAL,
    "listar_escalas": OPERACIONAL,
    "listar_admissoes": OPERACIONAL,
    "listar_vagas": OPERACIONAL,
    "listar_candidatos": OPERACIONAL,
    "listar_ferias": OPERACIONAL,
    "ferias_funcionario": OPERACIONAL,
    "justificativas_ponto_pendentes": OPERACIONAL,
    "painel_espelho_ponto": OPERACIONAL,
    "espelho_ponto": OPERACIONAL,
    "listar_rescisoes": OPERACIONAL,
    "concluir_admissao": OPERACIONAL,
    "aprovar_ferias": OPERACIONAL,
    "fechar_mes_ponto": OPERACIONAL,
    "revisar_justificativa_ponto": OPERACIONAL,
    "consultar_kit": OPERACIONAL,
    "consultor_dp": OPERACIONAL,
    "esocial_timeline_funcionario": OPERACIONAL,
    "esocial_espelho_resumo": OPERACIONAL,
    "diaristas_a_cadastrar": OPERACIONAL,
    "listar_beneficios_funcionario": OPERACIONAL,
    "beneficios_cct": OPERACIONAL,
    "tabela_salarial_cct": OPERACIONAL,
    "saldo_ferias": OPERACIONAL,
    "solicitar_ferias": OPERACIONAL,              # nome e período; é o fluxo de operar
    "vagas_abertas": OPERACIONAL,                 # postos com vaga, não candidatos
    "buscar_documento": OPERACIONAL,
    # nome, cargo, CPF e RG de UMA pessoa — identificável, e o CPF torna sensível
    "definir_representante_cliente": SENSIVEL,              # /gedeon/kits/montagem — kit por pessoa
    "registrar_evento_kit": OPERACIONAL,
    # R6-4: inscreve um LEAD identificado, com telefone, numa régua de WhatsApp. Vinha
    # `nao_se_aplica` por inferência — o nome não diz "lead" e a descrição não dizia o que
    # entra na régua.
    "inscrever_lead_em_sequencia": OPERACIONAL,
    "inscrever_em_sequencia": OPERACIONAL,          # checklist do kit de admissão

    # sensível — CPF, salário individual, holerite, saúde
    "baixar_holerite_pdf": SENSIVEL,
    "calcular_holerite": SENSIVEL,
    "ficha_funcionario": SENSIVEL,
    "buscar_funcionario_por_cpf": SENSIVEL,
    "asos_vencendo": SENSIVEL,
    "funcionarios_sem_aso": SENSIVEL,
    "calcular_verbas_rescisorias": SENSIVEL,
    "calcular_folha_todos": SENSIVEL,
    "fechar_folha": SENSIVEL,
    "exportar_folha_dominio": SENSIVEL,
    "baixar_espelho_ponto_pdf": SENSIVEL,
    "baixar_recibo_vt_vr_pdf": SENSIVEL,
    "dossie_juridico": SENSIVEL,
    "listar_beneficiarios_pix": SENSIVEL,
    "baixar_comprovante_pagamento_pdf": SENSIVEL,
}

# ── Concessão de escopo ───────────────────────────────────────────────────────────────
# ⭐ Ponto de partida SUGERIDO pelo próprio relatório e que segue a lógica dele: ler
# `asos_vencendo` e `funcionarios_sem_aso` porque é obrigação de SST e **o risco de NÃO
# olhar é maior que o de olhar** — ASO vencido com funcionário em campo é exposição hoje.
# NÃO inclui holerite individual nem CPF: para esses, o pedido tem de ser específico.
#
# ⚠️ A concessão tem VALIDADE. Autorização sem prazo vira permanente por esquecimento, que é
# como um escopo temporário se torna a nova regra sem ninguém decidir.
CONCESSAO = {
    "tools": ("asos_vencendo", "funcionarios_sem_aso"),
    "concedido_por": "Jordan Jesus",
    "concedido_em": "2026-09-12",
    "valido_ate": "2026-12-31",
    "motivo": ("obrigação de SST: o risco de não olhar é maior que o de olhar. "
               "ASO vencido com funcionário em campo é exposição trabalhista hoje."),
    "nao_inclui": ("holerite individual", "CPF", "salário individual", "ficha completa"),
}


# Ferramentas que NÃO tocam pessoa. Declaradas de propósito e não por omissão: o fail-closed
# continua valendo para o desconhecido, e estas saem da suspeita por decisão registrada.
#
# ⭐ Validação do Cowork (12/09/2026): `documentos` e `financeiro` vinham 100% `sensivel`,
# incluindo `inter_saldo` — saldo bancário DA EMPRESA — com a legenda "CPF, holerite, ASO ou
# dado de saúde". O erro de desenho foi meu: apliquei "desconhecida = sensível" ao universo
# INTEIRO, quando o fail-closed deve valer onde há pessoa. Marcar tudo como sensível é o
# oposto do critério que eu mesmo escrevi para a categoria IRREVERSIVEL — "parede que barra
# trabalho normal vira parede que alguém desliga".
SEM_DADO_PESSOAL: frozenset = frozenset({
    # contratos e propostas: dado de empresa cliente, não de pessoa física
    "baixar_contrato_pdf", "baixar_proposta_pdf", "obter_contrato", "listar_contratos",
    "listar_propostas", "listar_modelos_contrato", "criar_modelo_contrato",
    "atualizar_modelo_contrato", "validar_modelo_contrato", "vincular_modelo_ao_contrato",
    "gerar_contrato_por_modelo", "criar_contrato_por_modelo", "briefing_contrato_novo",
    "status_assinatura_contrato", "abrir_assinatura_contrato", "procedencia_da_proposta",
    "aceitar_estimativa_da_proposta", "orcamento_por_natureza",
    "consultar_parametros_precificacao",
    # documentos: o conteúdo pode ser qualquer coisa, mas a tool é genérica de arquivo
    "anexar_documento", "listar_documentos_da_entidade", "baixar_documento",
    "listar_documentos",
    # financeiro da EMPRESA: saldo, extrato, cobrança emitida — pessoa jurídica
    "resumo_financeiro", "inter_saldo", "inter_extrato_resumo", "listar_cobrancas_inter",
    "pix_recebidos", "contabil_grupo",
    # comercial
    "listar_clientes", "contexto_cliente", "listar_deals", "criar_cliente",
    "atualizar_cliente", "buscar_cliente_por_cnpj", "proposta_da_oportunidade",
    # POSTO é lugar, não pessoa. `listar_alocacoes` e `funcionarios_disponiveis_posto`
    # continuam em NIVEL porque nomeiam gente; a grade do posto, não.
    "listar_postos", "estatisticas_postos", "grade_postos", "grade_do_posto",
})


# ── Inferência para o que NÃO está nas duas listas ────────────────────────────────────
# ⭐ 13/09/2026 — Bloco 1 do prompt de fechamento do Jordan. O defeito que ele mediu:
# `capabilities(tool=...)` devolvia `sensivel` com a legenda "CPF, holerite, salário
# individual, ASO ou dado de saúde" para `excluir_proposta`, `arquivar_contrato`,
# `definir_meta_mensal` (meta de vendas EM REAIS), `margem_por_condominio`, `gerar_recibo_pdf`.
#
# ⚠️ A hipótese dele era "se escreve, então sensível" — e ela NÃO se confirma. O critério era
# fail-closed puro sobre duas listas enumeradas à mão: 69 em NIVEL + 40 em SEM_DADO_PESSOAL,
# e as 171 restantes caíam em `sensivel` sem ninguém decidir nada. O achado está certo; a
# causa era outra.
#
# ⚠️ E é a MESMA falha de 12/09, quando o Cowork mostrou `inter_saldo` rotulado "CPF,
# holerite, ASO". Eu "consertei" acrescentando 40 nomes ao SEM_DADO_PESSOAL — tratei as
# instâncias e deixei o mecanismo. Enumeração à mão com fail-closed sobre o universo não
# escala: cada tool nova nasce mentindo até alguém lembrar de listá-la.
#
# O fail-closed CONTINUA, mas passa a valer onde há pessoa. O que decide é a assinatura e a
# descrição da própria ferramenta — o que ela toca, não o que eu lembrei de escrever.

# parâmetro que identifica uma PESSOA e dá acesso ao que ela tem de mais sensível
_PARAM_PESSOA_SENSIVEL = re.compile(
    r"employee_id|funcionario_id|colaborador_id|^cpf$|_cpf$|holerite|matricula", re.I)
# descrição que declara, com estas palavras, o que está sendo exposto.
#
# ⚠️ AJUSTADA depois de medir: a 1ª versão marcou 7 como sensível e QUATRO eram falso
# positivo, todos pelo mesmo motivo — a régua lia a PALAVRA, não o que ela nomeia:
#   · `ensaiar` diz "holerite" como EXEMPLO no docstring (é despachante: o nível é o da tool
#     ensaiada, nunca o dele);
#   · `simular_preco` e `cronograma_kit` dizem "salário" como BASE DE CUSTO — preço de posto,
#     não remuneração de uma pessoa;
#   · `gerar_orcamento` diz "CPF" como CAMPO DE DOCUMENTO do cliente ("CNPJ/CPF").
#
# Por isso: "salári"/"remunera" saem (ambíguos com custo) e "CPF" desce para sinal
# OPERACIONAL. CPF como PARÂMETRO continua sensível — aí a tool está buscando uma pessoa.
# Ficam só termos que não têm leitura de custo: holerite, ASO, saúde, rescisão.
_DOC_SENSIVEL = re.compile(
    r"holerite|contracheque|sal[áa]rio individual|\bASO\b|atestado de sa[úu]de|"
    r"sa[úu]de ocupacional|exame (?:m[ée]dico|peri[óo]dico|admissional)|verbas rescis|"
    r"dado (?:pessoal )?sens[íi]vel|PIS/PASEP|carteira de trabalho", re.I)
# pessoa identificável, sem o núcleo sensível: nome, posto, escala, telefone, contato
_PESSOA_OPERACIONAL = re.compile(
    r"funcion[áa]ri|colaborador|candidat|di[áa]rista|escala|aloca[çc]|ponto\b|batida|"
    r"substitut|tel[eé]fone|whatsapp|celular|contato\b|benefici[áa]ri|f[ée]rias|"
    r"\bCPF\b|remunera|sal[áa]ri", re.I)

# ⚠️ DESPACHANTES: o nível é o da ferramenta DESPACHADA, nunca o do despachante. Sem isto,
# `ensaiar` herda "sensível" de um holerite citado como exemplo no próprio docstring dele —
# e passa a exigir concessão para ensaiar qualquer coisa.
_DESPACHANTES = frozenset({
    "ensaiar", "no_sandbox", "executar_em_segundo_plano", "status_job", "resultado_job",
    "conecta_pro_capabilities", "changelog_mcp",
})


def _texto_da_tool(tool: str) -> tuple[str, str]:
    """(nomes dos parâmetros, docstring) da ferramenta. Vazio quando não dá para olhar.

    ⚠️ import LOCAL: `server` importa este módulo, então import no topo seria circular.
    """
    try:
        import inspect  # noqa: PLC0415

        import server as _srv  # noqa: PLC0415

        fn = getattr(_srv, tool, None)
        if not callable(fn):
            return "", ""
        params = " ".join(inspect.signature(fn).parameters)
        return params, (inspect.getdoc(fn) or "")
    except Exception:  # noqa: BLE001
        return "", ""


def inferir(tool: str) -> str | None:
    """Nível por INSPEÇÃO da ferramenta. `None` = não consegui olhar (cai no fail-closed).

    ⚠️ Devolver `None` quando não há assinatura nem docstring é deliberado: é o que mantém
    tool desconhecida caindo em `sensivel`. Inferência que responde para tudo destrói o
    fail-closed em vez de estreitá-lo.
    """
    if tool in _DESPACHANTES:
        return NAO_SE_APLICA
    params, doc = _texto_da_tool(tool)
    if not params and not doc:
        return None
    if _PARAM_PESSOA_SENSIVEL.search(params) or _DOC_SENSIVEL.search(doc):
        return SENSIVEL
    # ⚠️ ASSIMETRIA DELIBERADA: o NOME da ferramenta entra no sinal operacional e NUNCA no
    # sensível. `registrar_optout_whatsapp` documenta "número", não "telefone", e caía em
    # `nao_se_aplica` — mas telefone é dado pessoal. Já decidir SENSÍVEL por nome é o erro que
    # `test_lgpd_escopo` documenta: `folha_dashboard` e `baixar_holerite_pdf` compartilham a
    # palavra e têm níveis opostos. Nome só pode APERTAR de "não se aplica" para "operacional",
    # onde errar custa uma etiqueta a mais; nunca soltar nem marcar o núcleo sensível.
    if (_PESSOA_OPERACIONAL.search(params) or _PESSOA_OPERACIONAL.search(doc)
            or _PESSOA_OPERACIONAL.search(tool)):
        return OPERACIONAL
    return NAO_SE_APLICA


def nivel(tool: str) -> str:
    """O nível desta ferramenta.

    Ordem: classificação explícita → declarada sem dado pessoal → INFERIDA da assinatura e
    da descrição → fail-closed em `sensivel`.

    O fail-closed continua no fim, e é ele que faz tool que eu não consigo INSPECIONAR nascer
    protegida. O que ele deixou de fazer é responder pelo sistema inteiro: marcar tudo como
    sensível é a mesma coisa que não classificar, com a aparência de rigor.
    """
    if tool in NIVEL:
        return NIVEL[tool]
    if tool in SEM_DADO_PESSOAL:
        return NAO_SE_APLICA
    inferido = inferir(tool)
    return inferido if inferido is not None else SENSIVEL


def concessao_vale_para(tool: str, *, hoje: date | None = None) -> bool:
    """A concessão cobre esta tool HOJE? Vencida não cobre — por isso tem data."""
    if tool not in CONCESSAO["tools"]:
        return False
    try:
        return (hoje or date.today()) <= date.fromisoformat(CONCESSAO["valido_ate"])
    except ValueError:
        return False


def declarar(tool: str) -> dict:
    """O que vai no `capabilities` por tool, para o agente saber ANTES de acessar."""
    n = nivel(tool)
    d = {"lgpd_nivel": n, "lgpd_significa": O_QUE_SIGNIFICA[n]}
    if n == NAO_SE_APLICA:
        return d
    if n == SENSIVEL:
        coberta = concessao_vale_para(tool)
        d["lgpd_autorizado"] = coberta
        d["lgpd_aviso"] = (
            f"Autorizado em operação normal por concessão de escopo de "
            f"{CONCESSAO['concedido_por']} até {CONCESSAO['valido_ate']} — {CONCESSAO['motivo']}"
            if coberta else
            # ⭐ 13/09/2026, e o Cowork foi cirúrgico: ele leu "acesse apenas com pedido
            # específico", chamou `dossie_juridico` sem pedido, foi ATENDIDO, e o sistema
            # anotou `autorizado_por_concessao: false`. Ele não chamou de bug — chamou de
            # texto errado, e é isso mesmo: *"a distância entre 'isto é bloqueado' e 'isto é
            # anotado' é a diferença entre um controle e um relatório; quem lê o capabilities
            # para decidir o que pode fazer precisa saber qual dos dois está olhando."*
            #
            # É TRILHA, não parede. Escrito como parede, ensinava a confiar numa proteção
            # que não existe — pior que não ter texto nenhum.
            "⚠️ NÃO BLOQUEADO, REGISTRADO. Dado pessoal SENSÍVEL sem concessão de escopo: "
            "a chamada é atendida e o acesso fica na trilha com seu nome, a ferramenta e o "
            "argumento. Quem responde por ele depois é você — acesse só com pedido "
            "específico do dono. A parede aqui é de auditoria, não de permissão."
        )
    return d
