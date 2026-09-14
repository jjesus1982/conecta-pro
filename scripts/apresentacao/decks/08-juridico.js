/** Manual do JURÍDICO & LICITAÇÕES. 27 + 11 telas. Processos, DET, pareceres, risco
 *  trabalhista, base de conhecimento, e o ciclo de licitação pública. INTERNO. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_08_Juridico_e_Licitacoes',
  titulo: 'Manual do Jurídico & Licitações — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 08 · uso interno', titulo: 'Jurídico',
      destaque: '& Licitações',
      sub: 'Processos, DET, pareceres, exposição trabalhista e o ciclo completo de uma licitação pública — do edital à medição.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Circulação', valor: 'Interna — traz exposição por pessoa' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'gavel', titulo: 'O que o jurídico precisa saber antes de ser chamado',
      texto: 'Empresa de segurança vive de gente. Onde há gente há risco trabalhista, e o risco não aparece quando a reclamatória chega — ele já estava lá. Este módulo serve para vê-lo antes.',
      chips: ['Visão geral', 'Processos', 'Contratos', 'Pareceres', 'Análise de contratos', 'DET / Intimações', 'Riscos', 'Prazos', 'Playbook', 'Base de conhecimento'],
      nota: { icone: 'triangle-alert', texto: 'O DET é intimação eletrônica trabalhista: prazo corre do momento em que é disponibilizado, tenha alguém lido ou não.' } },

    { t: 'tela', kicker: 'Visão geral', titulo: 'O estado jurídico da empresa',
      imagem: P + 'jur-visao-geral.png', legenda: 'Jurídico › Visão geral',
      notas: [
        { titulo: 'Os quatro números', desc: 'Processos, escalonados, itens na base de conhecimento e contratos sob a guarda do jurídico.' },
        { titulo: 'Escalonado é o que urge', desc: 'Processo que passou do trâmite normal e precisa de decisão. É o número que não pode crescer.' },
        { titulo: 'Processos por status e por tipo', desc: 'Os dois quadros abrem a fila. «Trabalhista» concentra praticamente tudo neste setor.' },
        { titulo: 'A base de conhecimento', desc: 'Peças, teses e decisões já usadas. É o que evita reescrever a mesma defesa do zero.' }] },

    { t: 'tela', kicker: 'Riscos', titulo: 'A exposição trabalhista, pessoa por pessoa',
      imagem: P + 'jur-riscos.png', legenda: 'Jurídico › Riscos Jurídicos — Exposição trabalhista',
      notas: [
        { titulo: 'A frase do topo é a tese', desc: 'Exposição estimada total, quantos colaboradores entram na conta, e a quebra por tipo de verba.' },
        { titulo: '«Estimativa, não provisão»', desc: 'A própria tela avisa. Serve para dimensionar risco e negociar acordo — não para lançar na contabilidade.' },
        { titulo: 'Meses de casa', desc: 'Quanto mais tempo, maior a exposição: aviso prévio proporcional, férias acumuladas e 13º crescem com o tempo.' },
        { titulo: 'As verbas somadas', desc: 'FGTS mais multa de 40%, aviso prévio, férias proporcionais mais 1/3 e 13º proporcional.' }] },

    { t: 'tela', kicker: 'Processos', titulo: 'Cada processo com número e reclamante',
      imagem: P + 'jur-processos.png', legenda: 'Jurídico › Processos',
      notas: [
        { titulo: 'O número é o do tribunal', desc: '0000338-26.2026.5.11.0003. É por ele que se acompanha no PJe e se fala com o escritório.' },
        { titulo: 'Tipo e reclamante', desc: 'Trabalhista, e o nome de quem reclama. O nome liga o processo à ficha da pessoa no DP.' },
        { titulo: 'O status conta a fase', desc: '«nao_localizado_clt» quer dizer que o sistema não achou o reclamante no cadastro — vale conferir antes de responder.' },
        { titulo: 'Enviar CQB', desc: 'O botão dispara a Certidão de Quitação de Débitos Trabalhistas ao processo, sem sair da tela.' }] },

    { t: 'tela', kicker: 'Prazos', titulo: 'O que vence, e em quantos dias',
      imagem: P + 'jur-prazos.png', legenda: 'Jurídico › Prazos jurídicos',
      notas: [
        { titulo: 'Prazo manual e automático', desc: 'O subtítulo explica: além dos que alguém cadastra, o sistema cria prazo sozinho a partir de contrato e certidão.' },
        { titulo: 'A coluna Dias restantes', desc: 'Número negativo é prazo JÁ vencido. «-13» quer dizer treze dias de atraso, não treze dias para vencer.' },
        { titulo: 'Origem', desc: 'Contrato ou certidão. Prazo de origem automática não é editável — muda-se o contrato ou a certidão, não o prazo.' },
        { titulo: 'Vigência de contrato', desc: 'Fim de vigência aparece aqui como prazo. É o aviso que evita continuar prestando serviço com contrato vencido.' }] },

    { t: 'tela', kicker: 'DET', titulo: 'O que o Ministério do Trabalho deixou para a empresa',
      imagem: P + 'jur-det-comunicacoes.png', legenda: 'Jurídico › DET — Comunicações',
      notas: [
        { titulo: 'Título, tipo e órgão', desc: 'Aviso ou Notificação, e de qual órgão veio — Secretaria de Inspeção do Trabalho, Crédito do Trabalhador.' },
        { titulo: 'A coluna Prazo', desc: 'A data limite daquela comunicação. É ela que manda, não a data em que alguém abriu.' },
        { titulo: 'O status Nova', desc: 'Comunicação ainda não tratada. Uma lista cheia de «Nova» com prazos antigos é risco acumulado.' },
        { titulo: 'Abrir e Baixar', desc: 'O documento original do MTE fica guardado. É ele que o escritório vai querer ver.' }] },

    { t: 'cards', kicker: 'DET', titulo: 'Domicílio Eletrônico Trabalhista', cols: 3,
      cards: [
        { icone: 'inbox', titulo: 'As comunicações', desc: 'Tudo o que o MTE deixou no domicílio da empresa. Ler aqui evita perder prazo por não ter aberto o portal.', cor: 'F26A21' },
        { icone: 'bot', titulo: 'O robô de coleta', desc: 'Busca as comunicações sozinho. Quando o portal exige login supervisionado, a tela pede a intervenção humana e registra.', cor: '38BDF8' },
        { icone: 'file-input', titulo: 'Ingerir manualmente', desc: 'Comunicação que chegou por fora entra por texto ou por arquivo, e passa a contar prazo como as demais.', cor: '17297B' }],
      nota: { icone: 'clock', texto: 'Prazo de DET corre a partir da disponibilização. Não há «não vi» que valha como defesa.' } },

    { t: 'lista', kicker: 'O que o módulo faz por você', titulo: 'Além de guardar processo',
      itens: [
        { icone: 'file-search', titulo: 'Analisar processo', desc: 'Cole o texto ou suba o arquivo: o sistema resume, classifica e aponta o risco.' },
        { icone: 'file-pen', titulo: 'Gerar parecer', desc: 'Parecer jurídico em PDF timbrado, a partir do caso e da base de conhecimento.' },
        { icone: 'file-check', titulo: 'Análise de contratos', desc: 'Lê a minuta e aponta cláusula de risco antes de a empresa assinar.' },
        { icone: 'book-open', titulo: 'Playbook jurídico', desc: 'O que fazer em cada situação recorrente — a regra da casa escrita, não na memória de alguém.' },
        { icone: 'calendar-clock', titulo: 'Prazos', desc: 'O que vence quando. É a tela que evita a perda de prazo por esquecimento.' },
        { icone: 'building', titulo: 'Consultas ao escritório', desc: 'O que foi perguntado ao escritório externo e o que ele respondeu, registrado.' }] },

    { t: 'secao', kicker: 'A outra metade', icone: 'landmark', titulo: 'Licitações',
      texto: 'Contrato público segue outro ritual: edital, habilitação, proposta, disputa, resultado e medição. Onze telas cobrem o ciclo, e a habilitação depende de uma coisa que mora no módulo Fiscal — a certidão válida.',
      chips: ['Oportunidades', 'Editais', 'Propostas', 'Contratos públicos', 'Certidões', 'Disputas', 'Documentos', 'Resultados', 'Medições'],
      nota: { icone: 'shield-check', texto: 'Certidão vencida derruba habilitação. Antes de qualquer disputa, olhe Fiscal › Certidões (CND).' } },

    { t: 'tela', kicker: 'Licitações', titulo: 'O funil público em quatro números',
      imagem: P + 'lic-visao-geral.png', legenda: 'Licitações › Visão geral',
      notas: [
        { titulo: 'Oportunidades e editais', desc: '«9/11» lê-se: de onze editais, participamos de nove. O denominador é o que passou pelo radar.' },
        { titulo: 'Oportunidades por status', desc: 'Nova, Analisando, Descartada e Convertida. Descartar cedo é tão valioso quanto participar.' },
        { titulo: 'Editais por modalidade', desc: 'Pregão eletrônico, concorrência e tomada de preços. Cada modalidade tem exigência de habilitação diferente.' },
        { titulo: 'Contratos públicos', desc: 'O valor total já contratado com o poder público. Ele fatura por medição, não por mensalidade fixa.' }] },

    { t: 'passos', kicker: 'Licitação', icone: 'route', titulo: 'O ciclo de uma disputa pública',
      passos: [
        { icone: 'search', titulo: 'Oportunidade', desc: 'O edital que interessa entra como oportunidade, com objeto, valor e prazo.' },
        { icone: 'file-check', titulo: 'Habilitação', desc: 'Certidões, atestados e documentos societários. É aqui que a maioria cai.' },
        { icone: 'calculator', titulo: 'Proposta', desc: 'Preço montado sobre o custo real da CCT, não sobre o preço do concorrente.' },
        { icone: 'gavel', titulo: 'Disputa', desc: 'Os lances e o que aconteceu na sessão ficam registrados.' },
        { icone: 'file-text', titulo: 'Contrato e medição', desc: 'Ganho, vira contrato público — e cada medição mensal é o que autoriza faturar.', destaque: true }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'clock-alert', titulo: 'Tratar DET como e-mail', desc: 'O prazo corre da disponibilização, não da leitura. Deixar o robô parado é deixar prazo correndo às escuras.' },
        { icone: 'trending-up', titulo: 'Ignorar a exposição por tempo de casa', desc: 'Ela cresce sozinha, todo mês. Quem tem 35 meses de casa custa muito mais que quem tem 3 — e isso é gerenciável.' },
        { icone: 'file-x', titulo: 'Entrar em licitação com certidão vencida', desc: 'Perde-se a habilitação por documento, não por preço. Conferir antes custa cinco minutos.' },
        { icone: 'pen-off', titulo: 'Assinar minuta sem análise', desc: 'A análise de contratos lê a minuta e aponta cláusula de risco. Pular esse passo é assinar no escuro.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
