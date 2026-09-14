/** Manual do COMERCIAL (CRM). 70 telas. Lead → proposta → contrato → assinatura → faturamento.
 *  Contém preço, custo e margem por função: documento INTERNO. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_05_Comercial',
  titulo: 'Manual do Comercial — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 05 · uso interno', titulo: 'Comercial',
      destaque: 'do lead ao contrato assinado',
      sub: 'Lead, oportunidade, proposta, contrato e assinatura com validade jurídica — tudo numa linha só, sem planilha no meio.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Circulação', valor: 'Interna — traz custo e margem' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'trending-up', titulo: 'Uma linha reta, do primeiro contato à assinatura',
      texto: 'Todo negócio percorre o mesmo caminho, e cada etapa tem a sua tela. O que muda de cliente para cliente é a velocidade, nunca o percurso.',
      chips: ['Leads', 'Oportunidades', 'Propostas', 'Contratos', 'Assinatura', 'Clientes', 'Precificação', 'Comissões', 'Growth'],
      nota: { icone: 'pen-tool', texto: 'O contrato assinado por ICP-Brasil A1 vale como título executivo, sem precisar de testemunha.' } },

    { t: 'selos', kicker: 'Em números', titulo: 'O funil de hoje',
      selos: [
        { icone: 'user-plus', valor: '7', label: 'leads no funil', cor: 'F26A21' },
        { icone: 'file-text', valor: '10', label: 'propostas emitidas', cor: '38BDF8' },
        { icone: 'file-signature', valor: '19', label: 'contratos no sistema', cor: '17297B' },
        { icone: 'calculator', valor: '10', label: 'funções precificadas pela CCT', destaque: true, cor: 'F26A21' }],
      sub: 'O funil muda toda semana. O que não muda é que cada número aqui tem uma tela por trás, com nome e valor.' },

    { t: 'cardsLargos', kicker: 'O ponto de partida', titulo: 'O que doía antes',
      cards: [
        { icone: 'message-square-x', titulo: 'O lead morria no WhatsApp', desc: 'Conversa que não virava cadastro sumia na rolagem. Agora todo contato do WhatsApp entra como lead, com origem marcada — mesmo quando ainda não se sabe o nome.' },
        { icone: 'file-x', titulo: 'Proposta era Word e improviso', desc: 'Cada um tinha o seu modelo. Hoje a proposta nasce numerada, com o preço calculado pela CCT, e sai em PDF timbrado.' },
        { icone: 'pen-off', titulo: 'Contrato ia e voltava por e-mail', desc: 'Assinar levava semanas. A assinatura digital ICP-Brasil acontece por link, e a tela mostra quantas das assinaturas já saíram.' },
        { icone: 'percent', titulo: 'Preço saía do chute', desc: 'Precificava-se olhando o concorrente. Agora o preço nasce do custo real da função pela convenção coletiva, com a margem à vista.' }] },

    { t: 'passos', kicker: 'O caminho', icone: 'route', titulo: 'Do primeiro contato à primeira fatura',
      passos: [
        { icone: 'user-plus', titulo: 'Lead', desc: 'Chega pelo WhatsApp, indicação ou visita. Entra com origem marcada, mesmo sem nome ainda.' },
        { icone: 'target', titulo: 'Oportunidade', desc: 'O lead qualificado vira oportunidade e passa a andar pelo funil, estágio a estágio.' },
        { icone: 'file-text', titulo: 'Proposta', desc: 'Numerada, com preço da CCT e PDF timbrado. Sai por WhatsApp ou e-mail direto da tela.' },
        { icone: 'file-signature', titulo: 'Contrato', desc: 'Gerado a partir da proposta aceita — sem redigitar nada. Nasce em rascunho.' },
        { icone: 'pen-tool', titulo: 'Assinatura', desc: 'Link de assinatura ICP-Brasil. Assinado, o contrato ativa e já pode ser faturado.', destaque: true }] },

    { t: 'tela', kicker: 'Dashboard', titulo: 'O funil em quatro números',
      imagem: P + 'com-visao-geral.png', legenda: 'CRM › Dashboard',
      notas: [
        { titulo: 'Leads, propostas, contratos', desc: 'Os três estágios do funil, mais o total de comissões a pagar sobre o que já fechou.' },
        { titulo: 'Leads por status', desc: 'New, Contacted, Qualified, Proposal, Won e Lost. Um monte parado em New é funil que ninguém trabalhou.' },
        { titulo: 'Propostas por status', desc: 'Rejected, Accepted, Sent. A relação entre elas é a sua taxa de conversão do mês.' },
        { titulo: 'Dois recortes diferentes', desc: 'Este painel conta o histórico inteiro; a aba Leads mostra um recorte menor. Antes de usar em relatório, confira qual dos dois você quer.' }] },

    // ── Leads ──────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Leads', titulo: 'Quem bateu na porta',
      imagem: P + 'com-leads.png', legenda: 'CRM › Leads',
      notas: [
        { titulo: 'A coluna Origem', desc: 'De onde a pessoa veio: WhatsApp, indicação, visita. É o que permite saber depois qual canal traz negócio.' },
        { titulo: 'Lead sem nome existe', desc: 'Linhas com número de telefone ou emoji são contatos do WhatsApp que ainda não se identificaram. Melhor registrar assim do que perder.' },
        { titulo: 'A coluna Status', desc: 'New, Contacted, Qualified, Proposal, Won. É o estágio do lead — e o Won é o que fecha a conta do mês.' },
        { titulo: 'Valor estimado', desc: 'Zerado quer dizer que ninguém estimou ainda. Preencher ajuda o forecast a valer alguma coisa.' }] },

    { t: 'lista', kicker: 'Leads e Oportunidades', titulo: 'As ações que movem o funil',
      itens: [
        { icone: 'user-plus', titulo: 'Novo lead', desc: 'Cadastro manual, para quem chegou por fora do WhatsApp.' },
        { icone: 'check', titulo: 'Definir lead', desc: 'Qualifica ou descarta. Lead que não é negócio sai do funil sem sumir do histórico.' },
        { icone: 'move-right', titulo: 'Mover no funil', desc: 'Passa a oportunidade de estágio. É o movimento que alimenta o forecast.' },
        { icone: 'flame', titulo: 'Leads frios', desc: 'Quem parou de responder. A tela junta todos para uma retomada em lote.' },
        { icone: 'calendar-plus', titulo: 'Sugerir e confirmar reunião', desc: 'Agenda a visita e registra a confirmação — sem sair do CRM.' },
        { icone: 'sparkles', titulo: 'Growth (Automação)', desc: 'Sequências que tocam o lead sozinhas, no ritmo certo, até ele responder.' }] },

    { t: 'tela', kicker: 'Oportunidades', titulo: 'O que está em jogo agora',
      imagem: P + 'com-oportunidades.png', legenda: 'CRM › Oportunidades',
      notas: [
        { titulo: 'A frase do topo é o resumo', desc: 'Quantas oportunidades, quantas em negociação, quantas em proposta e o valor total do pipeline.' },
        { titulo: 'O nome descreve o negócio', desc: '«Portaria Remota Híbrida — Parque Imperial (48 aptos, 2 blocos) — 24/36». Quem lê depois sabe o que era.' },
        { titulo: 'A coluna Estágio', desc: 'Análise, negociação, proposta, ganho, perdido. Perdido continua na lista — é dele que se aprende.' },
        { titulo: 'O botão Mover', desc: 'Passa a oportunidade de estágio. É esse movimento que alimenta o pipeline e o forecast.' }] },

    // ── Propostas ──────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Propostas', titulo: 'A proposta numerada, com PDF timbrado',
      imagem: P + 'com-propostas.png', legenda: 'CRM › Propostas',
      notas: [
        { titulo: 'Todo número é rastreável', desc: 'PROP-2026-00114. É por ele que a proposta é citada no contrato, na conversa e no histórico do cliente.' },
        { titulo: 'O título diz o escopo', desc: '«Portaria 24h + Limpeza + Manutenção Predial (12 colaboradores) + Conecta Plus cortesia». Quem lê depois entende o que foi vendido.' },
        { titulo: 'sent, accepted, rejected', desc: 'Proposta enviada mostra os botões Aceita e Recusada na linha — é assim que o retorno do cliente entra no sistema.' },
        { titulo: 'Abrir e Baixar', desc: 'Geram o PDF timbrado da proposta. É o mesmo arquivo que o cliente recebeu, não uma segunda via diferente.' }] },

    // ── Contratos ──────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Contratos', titulo: 'O contrato e o estado de cada assinatura',
      imagem: P + 'com-contratos.png', legenda: 'CRM › Contratos',
      notas: [
        { titulo: 'A coluna Assinatura', desc: 'A mais importante da tela. «Não aberta» é contrato que ninguém mandou assinar. «1/4 assinada(s)» é processo pela metade.' },
        { titulo: 'draft × Ativo', desc: 'Rascunho ainda pode mudar e não fatura. Ativo já vale e entra no faturamento do mês.' },
        { titulo: 'Os botões mudam com o estado', desc: 'Rascunho mostra Enviar e Assinatura. Ativo mostra Suspender, Renovar e Encerrar.' },
        { titulo: 'Serviço e valor', desc: 'Mão de obra, portaria remota, manutenção de CFTV — e o valor mensal ou único. É o que o financeiro vai faturar.' }] },

    { t: 'passos', kicker: 'Assinatura', icone: 'pen-tool', titulo: 'Como um contrato vira título executivo',
      passos: [
        { icone: 'file-plus', titulo: 'Gerar da proposta', desc: 'O contrato nasce da proposta aceita, com cliente, escopo e valor já preenchidos.' },
        { icone: 'stamp', titulo: 'Assinar pela empresa', desc: 'A Conecta assina primeiro, com o certificado ICP-Brasil A1 da empresa.' },
        { icone: 'send', titulo: 'Enviar o link', desc: 'O cliente recebe um link. Não precisa instalar nada nem ter certificado próprio.' },
        { icone: 'users', titulo: 'Acompanhar', desc: 'A coluna Assinatura mostra quantas das assinaturas necessárias já saíram.' },
        { icone: 'circle-check', titulo: 'Ativar e faturar', desc: 'Completo, o contrato ativa — e o financeiro pode faturar o contrato ativado.', destaque: true }] },

    // ── Precificação ───────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Precificação', titulo: 'O preço que nasce do custo, não do chute',
      imagem: P + 'com-precificacao.png', legenda: 'CRM › Precificação',
      notas: [
        { titulo: 'Piso, custo e preço', desc: 'O piso é o da CCT 2026. O custo soma encargos, provisões e benefícios sobre ele. O preço é o custo mais a margem.' },
        { titulo: 'A margem à vista', desc: 'A coluna Margem mostra a porcentagem de cada função. É a mesma para todas porque o parâmetro de margem é único.' },
        { titulo: 'Dez funções', desc: 'AGP diurno e noturno, rondante, ASG, ASG insalubre, artífice, jardineiro, auxiliar e líder de portaria.' },
        { titulo: 'Por que importa', desc: 'Vender abaixo do preço desta tela é vender abaixo do custo real da convenção — e isso só aparece na margem do contrato, meses depois.' }] },

    { t: 'tela', kicker: 'Comissões', titulo: 'Quanto se deve a quem vendeu',
      imagem: P + 'com-comissoes.png', legenda: 'CRM › Comissões',
      notas: [
        { titulo: 'A frase do topo', desc: 'Quantas comissões existem, o valor total e quantas ainda estão pendentes de pagamento.' },
        { titulo: 'Referência rastreável', desc: 'COM-2026-00015. Cada comissão aponta para a venda que a originou — não é valor solto.' },
        { titulo: 'Venda e comissão lado a lado', desc: 'O percentual fica evidente sem ninguém precisar calcular na mão.' },
        { titulo: 'O status pending', desc: 'Comissão apurada e ainda não paga. O pagamento acontece pelo Financeiro, não por aqui.' }] },

    { t: 'tela', kicker: 'Growth', titulo: 'O que o comercial andou fazendo',
      imagem: P + 'com-growth.png', legenda: 'CRM › Growth (Automação)',
      notas: [
        { titulo: 'Funil de atividades por tipo', desc: 'Proposta criada, mudança de estágio, lead criado, proposta aceita, contrato criado, proposta assinada.' },
        { titulo: 'A coluna Última', desc: 'Quando cada tipo de atividade aconteceu pela última vez. Data velha é sinal de frente parada.' },
        { titulo: 'Para que serve', desc: 'É o pulso do comercial: muita proposta criada e pouca aceita mostra onde o processo trava.' },
        { titulo: 'Não é relatório de vaidade', desc: 'Número alto de atividade sem contrato assinado é movimento, não resultado.' }] },

    { t: 'cards', kicker: 'Além do funil', titulo: 'O que mais vive neste módulo', cols: 4,
      cards: [
        { icone: 'building', titulo: 'Clientes', desc: 'A ficha de cada cliente: contratos, propostas, anotações e o WhatsApp cadastrado.' },
        { icone: 'percent', titulo: 'Comissões', desc: 'Quanto cada vendedor tem a receber sobre o que fechou, calculado sobre contrato ativo.' },
        { icone: 'bot', titulo: 'Consultor Comercial IA', desc: 'Pergunte sobre o funil em português. Ele lê o CRM e responde com o dado de hoje.' },
        { icone: 'file-plus-2', titulo: 'Aditivos contratuais', desc: 'Reajuste, mudança de escopo e prorrogação viram aditivo — sem refazer o contrato.' }] },

    { t: 'cards', kicker: 'Novidades', titulo: 'O que chegou em setembro de 2026', escuro: true, cols: 4,
      cards: [
        { icone: 'pen-tool', titulo: 'Assinatura ICP-Brasil A1', desc: 'Contrato assinado com certificado digital da empresa vale como título executivo, sem testemunha.' },
        { icone: 'message-circle', titulo: 'Proposta por WhatsApp', desc: 'O PDF timbrado sai da tela direto para a conversa do cliente, com registro do envio.' },
        { icone: 'repeat', titulo: 'Follow-up em lote', desc: 'Toca todas as propostas pendentes de uma vez, com opt-out respeitado para quem pediu para não ser perturbado.', destaque: true },
        { icone: 'calculator', titulo: 'Preço pela CCT 2026', desc: 'O motor de precificação lê a convenção vigente: piso novo, preço novo, sem refazer planilha.' }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'file-clock', titulo: 'Deixar contrato em «Não aberta»', desc: 'Contrato gerado e nunca enviado para assinatura é serviço prestado sem amparo. Olhe a coluna Assinatura toda semana.' },
        { icone: 'tag', titulo: 'Vender abaixo da tela de preço', desc: 'Desconto sobre o preço da CCT come margem que já está calculada. Se precisa descontar, mude o escopo, não o preço.' },
        { icone: 'user-x', titulo: 'Não qualificar o lead', desc: 'Lead parado em New por semanas não é funil, é ruído. Definir lead tira do caminho o que não é negócio.' },
        { icone: 'circle-slash', titulo: 'Esquecer de ativar o contrato assinado', desc: 'Contrato assinado e não ativado não entra no faturamento. O mês fecha sem cobrar um serviço que está sendo prestado.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
