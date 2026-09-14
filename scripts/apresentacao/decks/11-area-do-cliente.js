/** Manual da ÁREA DO CLIENTE. 10 telas. É o portal externo do cliente — administrado
 *  daqui de dentro. A tela Início mostra a CARTEIRA (com MRR e saúde): uso INTERNO. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_11_Area_do_Cliente',
  titulo: 'Manual da Área do Cliente — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 11 · uso interno', titulo: 'Área do',
      destaque: 'Cliente',
      sub: 'O portal externo do condomínio — o que o síndico vê, o que ele pode pedir, e como a gente administra isso daqui de dentro.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Circulação', valor: 'Interna — a carteira traz MRR' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'users', titulo: 'Duas visões da mesma coisa',
      texto: 'Você, daqui de dentro, vê a carteira inteira: todos os condomínios, com contrato, saúde e faturamento. O síndico, do lado de lá, vê apenas o condomínio dele — ronda, ocorrência, chamado, documento e fatura. Nunca o de outro cliente, nunca o nosso custo.',
      chips: ['Início (carteira)', 'Operação', 'Chamados', 'Financeiro', 'Documentos', 'Relatórios', 'Convidar clientes', 'Resumo mensal'],
      nota: { icone: 'eye-off', texto: 'MRR, custo e margem são dados internos. Eles aparecem na sua tela e nunca na do cliente.' } },

    { t: 'tela', kicker: 'Início', titulo: 'A carteira, como você a vê',
      imagem: P + 'cli-visao-geral.png', legenda: 'Área do Cliente › Início',
      notas: [
        { titulo: 'Segmento', desc: 'Enterprise, Grande, Pequeno. Serve para priorizar atendimento e definir o ritmo de contato.' },
        { titulo: 'A coluna Saúde', desc: 'Uma nota de 0 a 100 por cliente. Abaixo de 100 é sinal para olhar: ocorrência, cobrança atrasada ou chamado parado.' },
        { titulo: 'MRR por cliente', desc: 'A receita recorrente mensal daquele contrato. Este número é interno — não vai para tela nenhuma do cliente.' },
        { titulo: 'O botão Ver', desc: 'Abre o cliente com contrato, operação, chamados e documentos — a mesma matéria que ele vê, do seu lado.' }] },

    { t: 'tela', kicker: 'Operação', titulo: 'A prestação de contas que o síndico abre',
      imagem: P + 'cli-operacao.png', legenda: 'Área do Cliente › Operação',
      notas: [
        { titulo: 'As rondas com código', desc: 'RON-2026-00083 é o mesmo código do módulo Operacional. Não há segunda versão da verdade.' },
        { titulo: 'Concluída × Em andamento', desc: 'O cliente vê o mesmo estado que você. Ronda aberta há dias aparece para ele também — vale encerrar.' },
        { titulo: 'Postos e Ocorrências', desc: 'Quantos postos a ronda cobriu e quantas ocorrências gerou. Zero em ocorrências é boa notícia.' },
        { titulo: 'Por que isso muda a relação', desc: 'O síndico deixa de perguntar «vocês passaram ontem?» e passa a abrir a tela e ver.' }] },

    { t: 'cards', kicker: 'O que o cliente faz sozinho', titulo: 'As cinco áreas do portal dele', cols: 5,
      cards: [
        { icone: 'shield', titulo: 'Operação', desc: 'Rondas, ocorrências e a supervisão do mês.' },
        { icone: 'life-buoy', titulo: 'Chamados', desc: 'Abre pedido e acompanha o andamento.' },
        { icone: 'wallet', titulo: 'Financeiro', desc: 'Faturas, boletos e a situação de cada uma.' },
        { icone: 'folder', titulo: 'Documentos', desc: 'O kit documental do mês, com tudo o que a lei exige.' },
        { icone: 'chart-column', titulo: 'Relatórios', desc: 'Os números do serviço no período.' }],
      nota: { icone: 'shield-check', texto: 'O acesso é escopado por contrato: o síndico não alcança o dado de outro condomínio, nem por endereço direto.' } },

    { t: 'passos', kicker: 'Colocar um cliente no portal', icone: 'user-plus', titulo: 'Como fazer o onboard',
      passos: [
        { icone: 'list', titulo: 'Ver quem nunca acessou', desc: 'A tela «Convidar clientes que nunca acessaram» já traz a lista pronta.' },
        { icone: 'send', titulo: 'Convidar', desc: 'O convite cria o acesso e manda o link. Não é preciso criar senha por ninguém.' },
        { icone: 'folder-check', titulo: 'Conferir o kit', desc: 'Antes de o síndico entrar, confira se o kit do mês está em 100%. A primeira impressão é essa.' },
        { icone: 'calendar', titulo: 'Ligar o resumo mensal', desc: 'O disparo do resumo do mês mantém o portal vivo sem depender de ele lembrar de entrar.' },
        { icone: 'phone', titulo: 'Avisar por WhatsApp', desc: 'Um recado curto do gerente na primeira semana converte muito mais que um e-mail.', destaque: true }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Quatro coisas que o cliente percebe antes de você',
      cards: [
        { icone: 'clock-alert', titulo: 'Ronda aberta há dias', desc: 'Ele vê «Em andamento» na tela dele. Uma ronda que começou e nunca encerrou parece serviço não prestado.' },
        { icone: 'package-x', titulo: 'Kit incompleto', desc: 'A peça que falta no kit é a primeira que ele procura. Conferir a completude antes de enviar evita a conversa.' },
        { icone: 'message-square-x', titulo: 'Chamado sem resposta', desc: 'O chamado fica visível para ele com a data de abertura. O tempo parado é contado por quem está esperando.' },
        { icone: 'heart-crack', titulo: 'Saúde caindo sem ninguém notar', desc: 'A nota de saúde cai antes de o cliente reclamar. É o único aviso que chega antes do problema.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
