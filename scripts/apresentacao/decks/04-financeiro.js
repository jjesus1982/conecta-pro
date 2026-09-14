/** Manual do FINANCEIRO. 10 grupos, 150 telas — o maior módulo do sistema.
 *  ATENÇÃO: os prints deste manual mostram saldo, contas a pagar e margem por contrato.
 *  É documento INTERNO. Não circula com cliente. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_04_Financeiro',
  titulo: 'Manual do Financeiro — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 04 · uso interno', titulo: 'Financeiro',
      destaque: 'e Contábil',
      sub: 'Receber, pagar, bancos, conciliação, contabilidade e custo por contrato — o maior módulo do sistema, em dez grupos.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Circulação', valor: 'Interna — não enviar a cliente' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'wallet', titulo: 'Dez grupos, e uma regra de ouro',
      texto: 'Dinheiro entra por «Receber». Dinheiro sai por três portas diferentes, e é isso que mais confunde quem chega: pessoas em «Pessoas & Folha», boleto e imposto em «Contas & Impostos», e lote e histórico em «Ordens & Histórico». A lista do que se deve fica em «Pagar».',
      chips: ['Visão Geral', 'Receber', 'Pagar', 'Pessoas & Folha', 'Contas & Impostos', 'Ordens & Histórico', 'Bancos & Conciliação', 'Fiscal & Contábil', 'Custos & Orçamento', 'Cadastros'],
      nota: { icone: 'shield-alert', texto: 'Toda saída de dinheiro de verdade passa por OTP. Registrar uma conta não paga nada — são coisas diferentes de propósito.' } },

    { t: 'selos', kicker: 'Em números', titulo: 'O que o módulo movimenta',
      selos: [
        { icone: 'receipt', valor: '5.072', label: 'lançamentos bancários', cor: 'F26A21' },
        { icone: 'layout-grid', valor: '150', label: 'telas ligadas a dado real', cor: '38BDF8' },
        { icone: 'landmark', valor: '2', label: 'bancos sincronizados', cor: '17297B' },
        { icone: 'building-2', valor: '2', label: 'CNPJs no grupo', destaque: true, cor: 'F26A21' }],
      sub: 'Inter e Cora, com saldo sincronizado a cada quinze minutos, nos dois CNPJs do grupo.' },

    { t: 'cardsLargos', kicker: 'O ponto de partida', titulo: 'O que doía antes',
      cards: [
        { icone: 'file-spreadsheet', titulo: 'O saldo era a planilha de ontem', desc: 'Agora Inter e Cora sincronizam sozinhos a cada quinze minutos, e a tela mostra a hora do último sync para você saber o quanto o número é fresco.' },
        { icone: 'copy', titulo: 'Pagava-se duas vezes o mesmo dia', desc: 'Diária e folha CLT viviam em listas separadas. Hoje a aba «Sobrepostas à folha CLT» existe justamente para essa colisão aparecer antes do pagamento.' },
        { icone: 'search-x', titulo: 'Ninguém sabia a margem de um contrato', desc: 'Custo de pessoal era estimativa. Agora é folha + FGTS + provisão de férias e 13º + VT/VR + diaristas, contrato a contrato.' },
        { icone: 'scale', titulo: 'O balanço não fechava e ninguém via', desc: 'O Balanço Patrimonial hoje diz na primeira linha se Ativo = Passivo + PL, e aponta conta com saldo contrário à natureza.' }] },

    { t: 'passos', kicker: 'A rotina', icone: 'calendar-days', titulo: 'A semana do financeiro',
      passos: [
        { icone: 'landmark', titulo: 'Segunda: saldos', desc: 'Abra Bancos & Conciliação › Saldos. Confira o saldo dos dois bancos e o teto de pagamento do dia.' },
        { icone: 'arrow-down-to-line', titulo: 'Terça: receber', desc: 'Contas a Receber. O que venceu e não entrou vira fila de cobrança.' },
        { icone: 'arrow-up-from-line', titulo: 'Quarta: pagar', desc: 'Contas a Pagar por vencimento. Aprovar o que precisa de alçada antes do dia.' },
        { icone: 'users', titulo: 'Quinta: pessoas', desc: 'VT/VR e diárias do dia. O pagamento sai por lote da data, com OTP.' },
        { icone: 'git-compare', titulo: 'Sexta: conciliar', desc: 'Rodar a conciliação do extrato contra o sistema e classificar o que sobrou.', destaque: true }] },

    // ── Visão Geral ────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Visão Geral', titulo: 'O caixa, lançamento por lançamento',
      imagem: P + 'fin-fluxo-caixa.png', legenda: 'Financeiro › Visão Geral › Fluxo de Caixa',
      notas: [
        { titulo: 'A frase do topo', desc: '«5072 lançamentos bancários». É o extrato dos dois bancos já dentro do sistema, não um resumo.' },
        { titulo: 'A coluna Tipo', desc: 'Debit, PIX enviado, PIX recebido. É por ela que se separa o que saiu do que entrou.' },
        { titulo: 'Descrição', desc: 'Vem do banco. Quando aparece só «[CORA] PIX», é lançamento que ainda precisa ser classificado.' },
        { titulo: 'Confirmado', desc: 'O lançamento já existe no extrato do banco. Não é previsão — é dinheiro que se moveu.' }] },

    { t: 'lista', kicker: 'Visão Geral', titulo: 'As abas que respondem "como estamos?"',
      sub: 'Dezoito abas neste grupo. Estas seis são as que se abre toda semana.',
      itens: [
        { icone: 'layout-dashboard', titulo: 'Cockpit', desc: 'A visão de comando: o que entrou, o que saiu e o que vem pela frente.' },
        { icone: 'waves', titulo: 'Fluxo de Caixa', desc: 'O extrato consolidado dos dois bancos, lançamento por lançamento.' },
        { icone: 'trending-up', titulo: 'Projeção & Insights', desc: 'Para onde o caixa vai, com base no que está agendado para entrar e sair.' },
        { icone: 'file-chart-column', titulo: 'DRE', desc: 'Receita, custo e resultado do período — a demonstração de resultado do exercício.' },
        { icone: 'timer', titulo: 'Indicadores DSO/DPO', desc: 'Quantos dias o cliente demora a pagar, e quantos dias a empresa demora a pagar.' },
        { icone: 'bot', titulo: 'CFO IA', desc: 'Pergunte em português sobre o financeiro. Ele lê o sistema — inclusive com anexo.' }] },

    { t: 'tela', kicker: 'Visão Geral', titulo: 'A DRE, com as três margens no alto',
      imagem: P + 'fin-dre-inline.png', legenda: 'Financeiro › Visão Geral › DRE',
      notas: [
        { titulo: 'A frase do topo diz a fonte', desc: 'Regime Lucro Real, com NFS-e emitidas somadas à folha, encargos e despesas do razão. Não é planilha paralela.' },
        { titulo: 'Bruta, operacional e líquida', desc: 'As três margens juntas contam a história: dá para ter margem bruta boa e margem líquida negativa.' },
        { titulo: 'O gráfico de grupos', desc: 'Receita bruta, receita líquida, lucro bruto, despesas administrativas, EBITDA e o resultado do exercício.' },
        { titulo: 'O demonstrativo abaixo', desc: 'O mesmo acumulado do ano em linhas, com os sinais explícitos: o que soma em verde, o que subtrai em vermelho.' }] },

    // ── Receber ────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Receber', titulo: 'O que o cliente ainda deve',
      imagem: P + 'fin-contas-receber.png', legenda: 'Financeiro › Receber › Contas a Receber',
      notas: [
        { titulo: 'Uma linha por cobrança', desc: 'Cliente, descrição com o número do contrato, valor e vencimento. O contrato na descrição é o que liga dinheiro a serviço.' },
        { titulo: 'Pendente × Pago', desc: 'Pendente é o que ainda não entrou. Pago já foi conciliado contra o extrato do banco.' },
        { titulo: 'A coluna Cobrança', desc: '«Sem cobrança» quer dizer que existe o valor a receber, mas nenhum boleto foi emitido. É dinheiro esperando sem ninguém pedir.' },
        { titulo: 'As dezoito abas', desc: 'Emitir boleto, cobrar PIX, régua de cobrança, recorrência do MRR e faturamento do mês saem todas deste grupo.' }] },

    { t: 'tela', kicker: 'Receber', titulo: 'A fila de cobrança',
      imagem: P + 'fin-cobrancas.png', legenda: 'Financeiro › Receber › Cobranças',
      notas: [
        { titulo: 'Só o que está em aberto', desc: 'O subtítulo é preciso: recebíveis pendentes ou parciais. O que já foi pago não polui a tela.' },
        { titulo: 'O contrato na descrição', desc: 'CTR-2026-00006. É ele que liga a cobrança ao serviço prestado — e o que se cita quando o cliente pergunta.' },
        { titulo: 'Vencimento no passado', desc: 'Linha com data anterior a hoje é atraso. É dessa lista que a régua de cobrança se alimenta.' },
        { titulo: 'A régua ao lado', desc: 'A aba «Régua» define quando e como cobrar. Automatizar isso é o que evita a cobrança depender de humor.' }] },

    { t: 'passos', kicker: 'Receber', icone: 'arrow-down-to-line', titulo: 'Do serviço prestado ao dinheiro na conta',
      passos: [
        { icone: 'file-text', titulo: 'Faturar o mês', desc: 'Gera o que cada contrato ativo deve faturar na competência.' },
        { icone: 'receipt', titulo: 'Emitir a NFS-e', desc: 'A nota sai pelo módulo Fiscal, no padrão ABRASF de Manaus.' },
        { icone: 'barcode', titulo: 'Emitir o boleto', desc: 'Ou cobrar por PIX. A cobrança bancária é emitida pelo próprio Conecta PRO.' },
        { icone: 'bell', titulo: 'Régua de cobrança', desc: 'Quem não pagou entra na fila e recebe o lembrete sem ninguém precisar lembrar.' },
        { icone: 'circle-check', titulo: 'Dar baixa', desc: 'A conciliação bancária reconhece o pagamento e a linha vira Pago.', destaque: true }] },

    // ── Pagar ──────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Pagar', titulo: 'O que a empresa deve',
      imagem: P + 'fin-contas-pagar.png', legenda: 'Financeiro › Pagar › Contas a Pagar',
      notas: [
        { titulo: 'A frase do topo é um mapa', desc: 'Ela diz onde cada tipo de saída mora: diaristas e folha em «Pessoas & Folha», boleto e imposto em «Contas & Impostos», lotes em «Ordens & Histórico».' },
        { titulo: 'Fornecedor e descrição', desc: 'A descrição traz o número da NFS-e ou da NF-e que originou a conta. Conta sem origem é conta a investigar.' },
        { titulo: 'O botão Pagar na linha', desc: 'Só aparece onde há forma de pagamento cadastrada. Onde só há «Ver», falta dado para pagar.' },
        { titulo: 'Aging em PDF', desc: 'O botão do topo gera o relatório de vencimentos — quanto está a vencer, vencido em 30, em 60, em 90.' }] },

    // ── Pessoas & Folha ────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Pessoas & Folha', titulo: 'VT, VR e diárias: o pagamento por dia',
      imagem: P + 'fin-pagamentos-diaristas.png', legenda: 'Financeiro › Pessoas & Folha › A pagar — VT+VR e diárias',
      notas: [
        { titulo: 'Paga o dia, não a linha', desc: 'O botão «Pagar este dia» leva o lote inteiro daquela data: VT/VR e diária saem juntos. É a regra mais importante da tela.' },
        { titulo: '«Sem PIX» é bloqueio', desc: 'Quer dizer que falta a chave no cadastro do Operacional. Sem chave não há pagamento, por mais que o valor esteja certo.' },
        { titulo: 'O cartão «Como pagar»', desc: 'Ele avisa o que é OTP, que se paga o lote da data inteira, e que é preciso escolher entre os dois CNPJs.' },
        { titulo: 'A pagar POR DIA', desc: 'O quadro da esquerda mostra quanto sai em cada data. É o que permite planejar o caixa da semana.' }] },

    { t: 'cards', kicker: 'Saída de dinheiro', titulo: 'As três portas — e por que são três', cols: 3,
      cards: [
        { icone: 'users', titulo: 'Pessoas & Folha', desc: 'Quem recebe da empresa: diarista, VT/VR, folha CLT e folha PJ. Paga por lote da data, com OTP.', cor: 'F26A21' },
        { icone: 'landmark', titulo: 'Contas & Impostos', desc: 'Boleto, PIX avulso, TED, DARF e GPS. Cada um com o seu formulário e o seu gate de OTP.', cor: '38BDF8' },
        { icone: 'layers', titulo: 'Ordens & Histórico', desc: 'Montar ordem, aprovar com OTP, executar no app e ver o que já saiu — inclusive o pago por fora.', cor: '17297B' }],
      nota: { icone: 'list', texto: '«Pagar» não paga: é a lista do que se deve. O pagamento acontece em uma destas três portas.' } },

    // ── Bancos ─────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Bancos & Conciliação', titulo: 'Quanto há em caixa, agora',
      imagem: P + 'fin-saldos.png', legenda: 'Financeiro › Bancos & Conciliação › Saldos',
      notas: [
        { titulo: 'Dois bancos, dois CNPJs', desc: 'Inter na Eletrônica e Cora na Patrimonial. O saldo de cada um é do último sync, que roda a cada quinze minutos.' },
        { titulo: 'A coluna Atualizado', desc: 'Mostra o quão fresco o número é. Se a hora está velha, o sync falhou — e o saldo na tela não é o saldo real.' },
        { titulo: 'Limite de pagamento de hoje', desc: 'Teto diário, quanto já saiu e quanto ainda cabe. É uma trava de segurança, não um informativo.' },
        { titulo: 'As 23 abas do grupo', desc: 'Extrato, PIX recebidos, devolver PIX, conciliação, classificação de saídas e consolidação multi-CNPJ.' }] },

    { t: 'tela', kicker: 'Bancos & Conciliação', titulo: 'Conciliar: o extrato contra o sistema',
      imagem: P + 'fin-conciliacao-bancaria.png', legenda: 'Financeiro › Bancos & Conciliação › Conciliação (extrato)',
      notas: [
        { titulo: 'Uma linha por mês e por banco', desc: 'Itens conciliados são os que casaram. Pendentes são os que o extrato tem e o sistema não reconheceu.' },
        { titulo: 'Em andamento × Concluída', desc: 'Concluída é mês fechado. «Em andamento» com zero conciliado é mês que ainda não foi rodado.' },
        { titulo: 'O número de pendentes importa', desc: '617 pendentes num mês concluído é muito lançamento sem classificação — e classificação é o que alimenta a DRE.' },
        { titulo: 'Rodar conciliação', desc: 'A aba ao lado faz o casamento automático. O que sobra vai para «Classificar saídas», no olho.' }] },

    // ── Fiscal & Contábil ──────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Fiscal & Contábil', titulo: 'O Balanço que diz se fecha',
      imagem: P + 'fin-balanco-patrimonial.png', legenda: 'Financeiro › Fiscal & Contábil › Balanço Patrimonial',
      notas: [
        { titulo: 'A primeira linha é a auditoria', desc: 'Ela diz de onde vem (razão real, classificado por account_type) e se FECHA: Ativo = Passivo + Patrimônio Líquido.' },
        { titulo: 'O aviso das contas contrárias', desc: '«7 conta(s) com saldo CONTRÁRIO à natureza» é a pista de recebimento ou pagamento lançado sem a origem.' },
        { titulo: 'Os quatro cartões', desc: 'Ativo, Passivo, PL e o selo Fecha. Se o selo sumir, pare tudo: a contabilidade está inconsistente.' },
        { titulo: 'As vinte abas do grupo', desc: 'Plano de contas, lançamentos, balancete, DRE por caixa, apuração IRPJ/CSLL, provisões de férias e 13º.' }] },

    // ── Custos ─────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Custos & Orçamento', titulo: 'A margem de cada contrato',
      imagem: P + 'fin-rentabilidade.png', legenda: 'Financeiro › Custos & Orçamento › Rentabilidade por contrato',
      notas: [
        { titulo: 'O que entra no custo', desc: 'A frase do topo é explícita: folha + FGTS 8% + provisão de férias, 1/3 e 13º (19,4%) + VT/VR + diaristas. Indireto não entra.' },
        { titulo: 'A coluna Recebe', desc: 'É o faturamento daquele contrato no mês. Zerada quer dizer que o mês ainda não foi faturado — e não que o contrato não rende.' },
        { titulo: 'Margem hoje', desc: 'Recebe menos custo total. Com Recebe em zero, toda margem aparece negativa: é aritmética, não prejuízo.' },
        { titulo: 'Com liminar', desc: 'A coluna ao lado recalcula recuperando o INSS retido real de cada nota, quando há liminar.' }] },

    { t: 'tela', kicker: 'Custos & Orçamento', titulo: 'Custeio CCT: quanto custa mesmo um colaborador',
      imagem: P + 'fin-custeio-cct.png', legenda: 'Financeiro › Custos & Orçamento › Custeio CCT',
      notas: [
        { titulo: 'Três campos, uma resposta', desc: 'Salário base, número de colaboradores e meses de contrato. O piso da CCT já vem sugerido no campo.' },
        { titulo: '«Cálculo, nada é gravado»', desc: 'O subtítulo avisa: é simulador. Nada do que se calcula aqui altera folha, contrato ou custo lançado.' },
        { titulo: 'O que ele soma', desc: 'Provisões e encargos da CCT sobre a folha — o custo que não aparece no salário e que decide a margem.' },
        { titulo: 'Para que serve na prática', desc: 'Responder «quanto custa colocar mais um posto?» antes de prometer preço ao cliente.' }] },

    { t: 'lista', kicker: 'Custos & Orçamento', titulo: 'O que mais vive neste grupo',
      itens: [
        { icone: 'chart-pie', titulo: 'Custeio ABC', desc: 'Rateia o custo indireto por atividade, para saber o custo real de cada operação.' },
        { icone: 'scale', titulo: 'Simulador CCT', desc: 'Simula o impacto de um reajuste da convenção antes de ele acontecer.' },
        { icone: 'tag', titulo: 'Precificação', desc: 'O preço de um posto a partir do custo real, não do chute do concorrente.' },
        { icone: 'target', titulo: 'Orçado × Realizado', desc: 'Onde o mês saiu do plano, categoria por categoria.' },
        { icone: 'repeat', titulo: 'Custos recorrentes', desc: 'O que se repete todo mês e não deveria surpreender ninguém.' },
        { icone: 'building', titulo: 'Resultado por CNPJ', desc: 'O mesmo resultado separado por empresa do grupo — Eletrônica e Patrimonial.' }] },

    { t: 'cards', kicker: 'Novidades', titulo: 'O que chegou em setembro de 2026', escuro: true, cols: 4,
      cards: [
        { icone: 'shield-check', titulo: 'OTP em toda saída', desc: 'Pagamento de verdade exige segundo fator. Registrar conta continua livre — pagar, não.' },
        { icone: 'copy-x', titulo: 'Diária sobreposta à folha', desc: 'A aba que mostra quem seria pago duas vezes pelo mesmo dia, antes de o dinheiro sair.' },
        { icone: 'scale', titulo: 'Balanço com prova', desc: 'O selo «Fecha ✓» e o aviso de conta com saldo contrário à natureza, no alto da tela.', destaque: true },
        { icone: 'building-2', titulo: 'Consolidação multi-CNPJ', desc: 'Eletrônica e Patrimonial somadas, sem planilha no meio.' }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'clock-alert', titulo: 'Confiar em saldo com sync velho', desc: 'A coluna Atualizado existe para isso. Saldo de três horas atrás não serve para decidir pagamento de hoje.' },
        { icone: 'copy', titulo: 'Pagar diária de quem está na folha', desc: 'A aba «Sobrepostas à folha CLT» mostra a colisão. Ignorá-la é pagar duas vezes o mesmo dia.' },
        { icone: 'file-x', titulo: 'Deixar receber «sem cobrança»', desc: 'Valor a receber sem boleto emitido é dinheiro parado porque ninguém pediu.' },
        { icone: 'triangle-alert', titulo: 'Fechar o mês com conciliação pendente', desc: 'Lançamento não classificado não entra na DRE. O resultado do mês sai errado e parece certo.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
