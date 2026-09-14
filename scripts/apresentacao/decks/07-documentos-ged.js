/** Manual do GED / DOCUMENTOS. 42 telas: acervo, kits do mês, assinaturas, coleta
 *  automática, certidões e os assistentes GEDEON e SOPHIA. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_07_Documentos_GED',
  titulo: 'Manual do GED e Kits Documentais — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 07', titulo: 'Documentos',
      destaque: 'e Kits',
      sub: 'O acervo, a montagem do kit de cada condomínio, a central de assinaturas e as certidões — a máquina que entrega prova todo mês.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Para', valor: 'GED, DP e atendimento' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'folder-check', titulo: 'Duas coisas com o mesmo nome',
      texto: 'Existe o kit MATERIALIZADO pelo sistema — contracheques, comprovantes e escalas gerados aqui dentro. E existe o kit ENTREGUE ao cliente, que é a pasta no Google Drive. Confundir os dois é a fonte de quase todo mal-entendido deste módulo.',
      chips: ['Visão geral', 'Arquivos', 'Pastas', 'Kits', 'Central de assinaturas', 'Coleta automática', 'Certidões', 'GEDEON', 'SOPHIA'],
      nota: { icone: 'info', texto: 'A Visão geral lê o Google Drive. As demais telas leem o banco. Quando os dois divergem, o Drive é o que o cliente vê.' } },

    { t: 'tela', kicker: 'Visão geral', titulo: 'O mês inteiro em uma tela',
      imagem: P + 'ged-visao-geral.png', legenda: 'Documentos › Visão geral',
      notas: [
        { titulo: 'Os quatro números', desc: 'Kits do mês, completude média, quantos estão completos e quantos pendentes. É o placar da entrega.' },
        { titulo: 'Completude por condomínio', desc: 'Ordenada do melhor para o pior. Quem está em 33% precisa de atenção hoje, não na véspera.' },
        { titulo: 'Acervo no banco', desc: 'Arquivos registrados, assinados e pendentes de assinatura. A diferença entre os dois últimos é a fila de trabalho.' },
        { titulo: 'Kit mais recente (ZIP)', desc: 'Baixa o pacote completo do mês. É o mesmo arquivo que se manda ao síndico quando ele pede tudo de uma vez.' }] },

    { t: 'selos', kicker: 'Em números', titulo: 'O acervo de hoje',
      selos: [
        { icone: 'files', valor: '4.641', label: 'arquivos registrados', cor: 'F26A21' },
        { icone: 'pen-tool', valor: '926', label: 'já assinados', cor: '38BDF8' },
        { icone: 'clock', valor: '3.715', label: 'pendentes de assinatura', cor: '17297B' },
        { icone: 'package', valor: '14', label: 'kits na competência', destaque: true, cor: 'F26A21' }],
      sub: 'A fila de assinatura é grande de propósito: todo documento gerado nasce pendente até alguém assinar.' },

    { t: 'cardsLargos', kicker: 'O ponto de partida', titulo: 'O que doía antes',
      cards: [
        { icone: 'folder-x', titulo: 'O kit era montado no braço', desc: 'Alguém baixava contracheque por contracheque e montava a pasta. Hoje o sistema materializa e mostra a porcentagem de cada condomínio.' },
        { icone: 'search-x', titulo: 'Não se sabia o que faltava', desc: 'Descobria-se quando o síndico reclamava. Agora a completude por condomínio diz a peça exata que está faltando.' },
        { icone: 'pen-off', titulo: 'Assinatura era caça ao tesouro', desc: 'A central de assinaturas junta tudo o que espera assinatura num lugar — inclusive o que espera a assinatura da empresa.' },
        { icone: 'calendar-x', titulo: 'Certidão vencia sem avisar', desc: 'O robô emite o que dá para emitir sozinho e a tela ordena por quem vence antes.' }] },

    { t: 'tela', kicker: 'Kits', titulo: 'A tabela que governa o mês',
      imagem: P + 'ged-kits.png', legenda: 'Documentos › Kits de documentos',
      notas: [
        { titulo: 'Colaboradores, Docs e Assinados', desc: 'Quantas pessoas o kit cobre, quantos documentos ele tem e quantos já estão assinados. Os três contam histórias diferentes.' },
        { titulo: 'Assinados muito abaixo de Docs', desc: '«108 docs, 40 assinados» é kit materializado mas ainda sem a assinatura que o torna prova.' },
        { titulo: 'Completude × Status', desc: 'Completude é a porcentagem de peças. Status é o julgamento: Completo ou Em montagem.' },
        { titulo: 'Os quatro botões da linha', desc: 'Gerar PDFs, Solicitar assinaturas, Anexar NFS-e e Enviar. É o caminho do kit, da esquerda para a direita.' }] },

    { t: 'tela', kicker: 'Central de assinaturas', titulo: 'O que espera a sua assinatura',
      imagem: P + 'ged-kits-assinaturas-pendentes.png', legenda: 'Documentos › Central de assinaturas',
      notas: [
        { titulo: 'A frase do topo divide o mundo', desc: 'Quantos documentos esperam a SUA assinatura e quantos esperam funcionários ou clientes. São filas diferentes.' },
        { titulo: 'Papel: EMPRESA (você)', desc: 'A coluna diz em nome de quem você assina. Cada CNPJ do grupo assina o que é dele.' },
        { titulo: 'Expira em', desc: 'Pedido de assinatura tem prazo. Expirado precisa ser reaberto — e o cliente recebe um link novo.' },
        { titulo: 'Assinatura com hash SHA-256', desc: 'A própria tela explica: assinatura eletrônica com hash, e o PDF assinado volta para o kit na hora.' }] },

    { t: 'tela', kicker: 'Coleta automática', titulo: 'O robô que busca sozinho',
      imagem: P + 'ged-ged-coleta-automatica.png', legenda: 'Documentos › GED — coleta automática',
      notas: [
        { titulo: 'Ligada, e com horário', desc: 'O cron «0 6 21 * *» quer dizer: às 6h do dia 21 de todo mês, no fuso de Manaus.' },
        { titulo: 'Última execução e status', desc: 'Data, hora e resultado. «success» com data velha é robô que rodou bem e não roda mais.' },
        { titulo: 'Atualizado por', desc: 'Quem mexeu na configuração e quando. Mudança de agendamento fica registrada com nome.' },
        { titulo: 'O que ele busca', desc: 'Guias e notas nos portais, todo mês, para o kit não depender de alguém lembrar de baixar.' }] },

    { t: 'passos', kicker: 'A rotina', icone: 'package', titulo: 'O mês do GED, em cinco passos',
      passos: [
        { icone: 'lock', titulo: 'Esperar o ponto fechar', desc: 'Sem mês de ponto fechado não há espelho nem folha — e o kit nasce deles.' },
        { icone: 'wand-sparkles', titulo: 'Montar kits do mês', desc: 'A ação gera as peças de todos os condomínios de uma vez, na competência escolhida.' },
        { icone: 'pen-tool', titulo: 'Assinar o que falta', desc: 'A central de assinaturas mostra o que espera a empresa e o que espera o colaborador.' },
        { icone: 'receipt', titulo: 'Anexar NFS-e e guias', desc: 'A nota do condomínio e as guias da competência entram no kit.' },
        { icone: 'send', titulo: 'Entregar no Drive', desc: 'A pasta no Drive é o que o cliente abre. Antes de enviar, confira a completude.', destaque: true }] },

    { t: 'lista', kicker: 'As telas que você mais usa', titulo: 'Onde fica cada coisa',
      itens: [
        { icone: 'files', titulo: 'Arquivos', desc: 'O acervo inteiro, filtrável por tipo, colaborador e competência.' },
        { icone: 'folder', titulo: 'Pastas', desc: 'A estrutura de pastas espelhada no Drive — é ela que o cliente enxerga.' },
        { icone: 'package', titulo: 'Kits', desc: 'O kit de cada condomínio, com status, completude e os botões de gerar e enviar.' },
        { icone: 'pen-tool', titulo: 'Central de assinaturas', desc: 'Tudo o que espera assinatura, com a opção de assinar em lote o que cabe à empresa.' },
        { icone: 'download', titulo: 'Coleta automática', desc: 'O que o sistema busca sozinho: guias do Drive, notas, comprovantes.' },
        { icone: 'shield-check', titulo: 'Certidões', desc: 'Emitir pelo robô, subir PDF quando o órgão exige captcha, e avisar o cliente por WhatsApp.' }] },

    { t: 'cards', kicker: 'Os dois assistentes', titulo: 'GEDEON e SOPHIA', cols: 2,
      cards: [
        { icone: 'bot', titulo: 'GEDEON — o consultor do kit', desc: 'Responde sobre a montagem: qual condomínio está atrasado, qual peça falta, qual funcionário não assinou o VT/VR, e como está o alinhamento com o DP. É quem você pergunta antes de abrir dez telas.', cor: 'F26A21' },
        { icone: 'search', titulo: 'SOPHIA — a memória do acervo', desc: 'Indexa os 4.641 documentos e responde perguntas sobre o conteúdo deles. Serve para achar aquele documento de que você lembra o assunto, mas não o nome nem o mês.', cor: '38BDF8' }],
      nota: { icone: 'message-circle', texto: 'Os dois respondem em português e leem o sistema no momento da pergunta — não um texto pronto.' } },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'package-x', titulo: 'Enviar kit abaixo de 100%', desc: 'A completude por condomínio está na primeira tela do módulo. Enviar sabendo que falta peça é entregar problema.' },
        { icone: 'shuffle', titulo: 'Confundir o kit do banco com o do Drive', desc: 'O sistema materializa; o Drive entrega. Se o Drive não tem, o cliente não recebeu — por mais que o banco diga 100%.' },
        { icone: 'pen-off', titulo: 'Deixar a fila de assinatura crescer', desc: 'Documento sem assinatura não é prova. Uma fila de milhares é uma fila de documentos que não defendem ninguém.' },
        { icone: 'calendar-x', titulo: 'Esquecer a certidão do kit', desc: 'Certidão vencida no kit é o primeiro item que um síndico atento nota — e o que derruba uma habilitação em licitação.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
