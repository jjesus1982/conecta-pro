"""Composição dos 8 grupos do Departamento Pessoal (fundação tabs, igual ao financeiro).

Mesma mecânica de `_fin_grupos.py` / `_op_grupos.py`: mapeia TODA tela do DP para
(grupo, aba), stub-a a antiga com `moved()` (deep-link `?t=` antigo continua valendo) e
deixa o menu com 8 entradas em vez de 24 itens soltos.

A ORDEM DOS GRUPOS SEGUE O CICLO DE VIDA de um colaborador, que é como a Pyetra pensa o
trabalho dela: entra (Admissão) → bate ponto → recebe (Folha) → tira férias/afasta →
tem benefício → sai (Desligamento), com Saúde/eSocial como a trilha de conformidade que
corre em paralelo. Não é ordem alfabética nem de tela: é a ordem do quadro dela.

Prefixo _ = o discovery de builders pula este arquivo (é helper, não módulo).

`grp`/`moved` são importados DENTRO de montar_grupos, não no topo: o
`departamento_pessoal.py` importa este arquivo no nível de módulo (para o MENU) e o
`redesign_data_controller` é quem descobre e importa os builders — importar aqui em cima
fecharia o ciclo. O financeiro não tropeça nisso porque importa `_fin_grupos` lá dentro
do build.
"""

GRUPOS = [
    ("g-visao", "Visão geral", "Quadro de pessoal, contratos e cadastro", [
        ("visao", "Resumo"), ("funcionarios", "Funcionários"),
        ("contratos", "Contratos"), ("headcount", "Headcount"), ("cadastro-incompleto", "Cadastro incompleto"),
        ("sem-escala", "Sem alocação"), ("cct-conformidade", "Conformidade CCT"), ("importar-cadastro", "Importar cadastro"),
        ("turnover-dashboard", "Turnover")]),  # dgx t1

    ("g-admissao", "Admissão & Cadastro", "Entrada do colaborador, documentos e certificações", [
        ("admissao", "Admissões"), ("nova-admissao", "Nova admissão"),
        ("prestadores-pj", "Prestadores PJ"), ("novo-prestador-pj", "Novo prestador PJ"),
        ("documentos", "Documentos"), ("nova-documento", "Enviar documento"),
        ("certificacao", "Certificações"), ("nova-certificacao", "Nova certificação"),
        ("gerar-certificacoes", "Gerar certificações"), ("certificacoes-gerar-folha", "Certificações da folha (competência)"), ("prestadores-pj-links-empresa", "Links PJ por empresa"),
        # dgx f6 — dependentes (fonte que a folha lê) e crachás em lote
        ("dependentes", "Dependentes"), ("dependente-novo", "Novo dependente"), ("crachas-lote", "Crachás em lote"),
        # dgx t1 — foto (alimenta o crachá), ficha única e validade de cursos/certificados
        ("colaboradores-fotos", "Fotos"), ("colaborador-foto", "Enviar foto"), ("colaboradores-fotos-lote", "Fotos em lote (ZIP)"),
        ("ficha-colaborador", "Ficha do colaborador"), ("certificados-vencimento", "Cursos e certificados — validade")]),

    ("g-ponto", "Ponto & Jornada", "Batidas, justificativas e fechamento do mês", [
        ("ponto", "Ponto"), ("fechamento-ponto", "Fechamento"),
        ("fechar-mes-ponto", "Fechar mês"), ("espelho-fechar", "Espelho: calcular/fechar"),
        ("ponto-lancar", "Lançamento manual"), ("ponto-ajuste", "Ajustar batida"),
        ("revisar-justificativa", "Revisar justificativas"), ("espelho-solicitar-homologacao", "Espelho: solicitar homologação"),
        # AFD/AEJ (Portaria 671): existiam no banco e em nenhuma tela — o documento que a
        # fiscalização pede primeiro era invisível no sistema (medido em 14/09/2026).
        ("afd", "AFD — arquivo fiscal"), ("justificar-ponto", "Justificar falta/atraso"),
        # dgx f7 (24/09/2026): montadas DEPOIS de montar_grupos por `_dgx_f7_ponto.telas(db, out)`,
        # que as anexa ao fim deste grupo; listadas aqui para a composição do grupo ficar num lugar só.
        ("ponto-configuracoes", "Configurações de ponto"), ("ponto-configuracao-nova", "Nova configuração"),
        ("relogios-ponto", "Relógios/aparelhos"), ("feriados", "Feriados"), ("feriado-novo", "Novo feriado"),
        ("cartao-ponto-lote", "Cartão de ponto em lote"), ("ausencias-dashboard", "Ausências"),
        # dgx t2 (24/09/2026): idem, anexadas por `_dgx_t2_ponto.telas(db, out)` — fechamento como
        # ato (reabrir com motivo) e integração de batimentos (arquivo AFD de relógio → batidas).
        ("integracao-batimentos", "Integração de batimentos"), ("integracao-batimentos-importar", "Importar arquivo do relógio"),
        ("ponto-reaberturas", "Meses fechados / reaberturas"), ("ponto-reabrir-mes", "Reabrir mês")]),

    ("g-folha", "Folha de pagamento", "Geração, conferência contra a Portte e contracheques", [
        ("folha", "Folha"), ("folha-gerar", "Gerar folha"),
        ("folha-por-condominio", "Por condomínio"), ("pareamento-folha", "Conecta × Portte"),
        ("folha-rubricas", "Rubricas"), ("folha-rubrica-nova", "Nova rubrica"),  # dgx f1
        ("folha-nao-conformidades", "Não conformidades"), ("folha-apontamento", "Apontar"),
        ("contracheques-lote", "Contracheques em lote"),
        ("chaves-pix", "Chaves PIX"), ("cadastrar-pix-key", "Cadastrar chave PIX"), ("pagar-folha-preview", "Folha PIX: prévia"), ("pagar-folha-status", "Folha PIX: status"),
        # Descontos recorrentes: 97 ativos no banco descontando da folha todo mês, e nenhuma
        # tela (medido em 14/09/2026). Criar/editar/encerrar só existia pelo `psql`.
        ("descontos", "Descontos (consignado, pensão)"), ("desconto-novo", "Novo desconto"),
        # dgx f6 — vale (adiantamento avulso, mesmo caminho dos descontos) e evento coletivo
        ("vales", "Vales"), ("vale-novo", "Novo vale"), ("eventos-coletivos", "Eventos coletivos"), ("evento-coletivo-novo", "Novo evento coletivo")]),

    ("g-ferias", "Férias & Afastamentos", "Programação, saldo, cálculo e licenças", [
        ("ferias", "Férias"), ("solicitar-ferias", "Solicitar"),
        ("saldo-ferias", "Saldo"), ("calcular-ferias", "Calcular (CLT)"),
        ("aviso-ferias", "Aviso prévio de férias"), ("sync-ferias-solides", "Sincronizar Sólides"),
        ("licencas", "Licenças"), ("nova-licenca", "Registrar afastamento")]),

    # dgx f2 — CCT como dado: sindicato → funções → eventos/benefícios por função → municípios.
    ("g-cct", "Sindicato & CCT", "Sindicato, funções da convenção, eventos e benefícios por função, municípios", [
        ("cct-sindicato", "Sindicato"), ("cct-funcoes", "Funções"),
        ("cct-funcao-eventos", "Eventos por função"), ("cct-funcao-beneficios", "Benefícios por função"),
        ("cct-municipios", "Municípios"), ("cct-municipio-novo", "Adicionar município"),
        ("cargos-atributos", "Cargos: CBO e exigências"), ("cargo-atributos-form", "Editar cargo")]),  # dgx t1

    ("g-beneficios", "Benefícios & Reembolsos", "VT/VR, benefícios da CCT e reembolsos", [
        ("beneficios", "Benefícios"), ("nova-beneficio", "Adicionar benefício"),
        ("beneficios-cct", "Benefícios CCT"), ("novo-beneficio-cct", "Adicionar da CCT"),
        ("reembolsos", "Reembolsos"), ("registrar-reembolso", "Registrar reembolso"),
        # dgx u5 (24/09/2026): anexadas DEPOIS de montar_grupos por `_dgx_u5_entrega_beneficio.telas(db, out)`,
        # ao fim deste grupo (depois das abas da frente 03 e da f3); listadas aqui pela composição ficar num lugar só.
        ("beneficio-entregas", "Entregas (lote)"), ("beneficio-entrega-nova", "Nova entrega"), ("beneficio-entrega-itens", "Itens da entrega")]),

    ("g-saude", "Saúde & eSocial", "ASO (NR-7) e espelho dos eventos do eSocial", [
        ("renovar-aso", "Agendar/renovar ASO"),
        ("esocial", "eSocial"), ("esocial-eventos", "eSocial · eventos próprios"), ("sincronizar-esocial", "Sincronizar espelho")]),

    ("g-desligamento", "Desligamento", "Aviso prévio, cálculo e rescisão", [
        ("aviso-previo", "Aviso prévio"), ("rescisao", "Rescisões"),
        ("nova-rescisao", "Nova rescisão"), ("calcular-rescisao", "Calcular (CLT)"),
        ("demissao-lote", "Demissão em lote")]),  # dgx f6
]

#: Telas que somem da navegação por serem DUPLICATA exata de outra já agrupada — mesmo
#: endpoint, mesmos campos. Duas portas para a mesma coisa é o oposto de organizado, e o
#: deep-link antigo continua funcionando porque vira `moved()` para a aba que ficou.
#: `registrar-licenca` foi criada por mim em 06/08 procurando o slug errado; `nova-licenca`
#: já fazia exatamente isso (POST /hr/leaves com os mesmos campos — o controller lê
#: `notes` ou `motivo`, então as duas sempre gravaram igual).
DUPLICATAS = {"registrar-licenca": ("g-ferias", "nova-licenca")}


def montar_grupos(out: dict) -> None:
    """Compõe os grupos a partir das telas JÁ montadas em out e stub-a as antigas (redirect).
    Ordem importa: capturar as referências ANTES de stubar."""
    from modules.operacional.controllers.redesign_data_controller import grp, moved

    novos = {}
    for gid, titulo, sub, tabs in GRUPOS:
        novos[gid] = grp(titulo, sub, [(tid, lbl, out.get(tid)) for tid, lbl in tabs])
    for gid, _t, _s, tabs in GRUPOS:
        for tid, _l in tabs:
            if tid in out:
                out[tid] = moved(gid, tid)
    for velho, (gid, tab) in DUPLICATAS.items():
        if velho in out:
            out[velho] = moved(gid, tab)
    out.update(novos)


#: FONTE do menu do módulo. O menu de verdade vive no pacote do front
#: (`frontend/src/app/redesign/_modules/departamento-pessoal.json`, chave "menu"), porque é
#: assim que o financeiro faz e o `EXTRA_MENU` do builder está zerado. Esta lista existe para
#: os títulos e a ORDEM ficarem ao lado dos GRUPOS que eles abrem — mexeu aqui, copie para o
#: JSON (o front lê o JSON, não isto). Ordem e ids têm que bater com GRUPOS acima.
MENU = [
    {"id": "g-visao", "label": "Visão geral",
     "icon": "M3 12l9-9 9 9M5 10v10h14V10"},
    {"id": "g-admissao", "label": "Admissão & Cadastro",
     "icon": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M20 8v6M23 11h-6"},
    {"id": "g-ponto", "label": "Ponto & Jornada",
     "icon": "M12 6v6l4 2M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20"},
    {"id": "g-folha", "label": "Folha de pagamento",
     "icon": "M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"},
    {"id": "g-ferias", "label": "Férias & Afastamentos",
     "icon": "M8 2v4M16 2v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z"},
    {"id": "g-cct", "label": "Sindicato & CCT",  # dgx f2
     "icon": "M3 21h18M5 21V7l7-4 7 4v14M9 21v-6h6v6M9 11h.01M15 11h.01"},
    {"id": "g-beneficios", "label": "Benefícios & Reembolsos",
     "icon": "M20 12v10H4V12M2 7h20v5H2zM12 22V7M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7zM12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"},
    {"id": "g-saude", "label": "Saúde & eSocial",
     "icon": "M22 12h-4l-3 9L9 3l-3 9H2"},
    {"id": "g-desligamento", "label": "Desligamento",
     "icon": "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"},
]
