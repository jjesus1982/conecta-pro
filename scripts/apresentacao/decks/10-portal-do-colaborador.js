/** Manual do PORTAL DO COLABORADOR. 16 telas, todas escopadas à própria pessoa.
 *  NOTA HONESTA: os prints foram tirados com um usuário administrador SEM cadastro de
 *  colaborador vinculado — por isso aparecem zerados. A tela diz isso na cara, e é a
 *  primeira lição do manual. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_10_Portal_do_Colaborador',
  titulo: 'Manual do Portal do Colaborador — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 10', titulo: 'Portal do',
      destaque: 'Colaborador',
      sub: 'Holerite, espelho de ponto, férias, benefícios, escala e documentos na mão de quem trabalha — sem passar pelo DP para cada pergunta.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Para', valor: 'Todo colaborador' }] },

    { t: 'secao', kicker: 'A primeira coisa', icone: 'link', titulo: 'Sem vínculo, o portal fica vazio',
      texto: 'O portal mostra os dados de UMA pessoa: você. Para saber quem é você, o seu usuário precisa estar ligado ao seu cadastro de colaborador. Enquanto essa ligação não existir, todas as telas aparecem zeradas — e a tela avisa isso com todas as letras.',
      chips: ['Início', 'Contracheque', 'Meu ponto', 'Minhas férias', 'Meus documentos', 'Benefícios', 'Minha escala', 'Comunicados', 'Bater ponto'],
      nota: { icone: 'user-check', texto: 'Se você lê «vincule seu cadastro de colaborador ao usuário», fale com o DP. É um ajuste de um minuto do lado de lá.' } },

    { t: 'tela', kicker: 'Início', titulo: 'A tela que abre — e o que ela diz quando falta vínculo',
      imagem: P + 'por-visao-geral.png', legenda: 'Portal do Colaborador › Início',
      notas: [
        { titulo: 'Leia o subtítulo', desc: '«Meu portal — dados pessoais — vincule seu cadastro de colaborador ao usuário». É exatamente o aviso de vínculo faltando.' },
        { titulo: 'Os quatro cartões', desc: 'Meus holerites, minhas férias, benefícios e documentos. Com vínculo, cada um mostra o número real da pessoa.' },
        { titulo: 'Meu holerite', desc: 'O quadro abaixo traz o líquido do último contracheque publicado — o número que a pessoa mais procura.' },
        { titulo: 'Minhas férias por status', desc: 'Solicitada, aprovada, rejeitada. É onde se acompanha o pedido sem ligar para o DP.' }] },

    { t: 'tela', kicker: 'Meus direitos', titulo: 'A tela é honesta quando não pode responder',
      imagem: P + 'por-meus-direitos-cct.png', legenda: 'Portal do Colaborador › Meus direitos (CCT)',
      notas: [
        { titulo: '«Vínculo: ausente»', desc: 'Em vez de mostrar zero e parecer que a pessoa não tem direito nenhum, a tela nomeia o problema.' },
        { titulo: 'Com vínculo, o que aparece', desc: 'Piso da função, adicionais devidos, benefícios da convenção e o que a CCT garante para o cargo da pessoa.' },
        { titulo: 'Por que isso importa', desc: 'É a tela que responde «eu deveria estar recebendo isso?» sem depender de boato no grupo do WhatsApp.' },
        { titulo: 'A lição de leitura', desc: 'Toda tela zerada deste portal tem uma frase explicando o motivo. Leia a frase antes de concluir que o sistema está errado.' }] },

    { t: 'cards', kicker: 'O que o colaborador resolve sozinho', titulo: 'Nove coisas que não precisam do DP', cols: 3,
      cards: [
        { icone: 'file-text', titulo: 'Ver e baixar o contracheque', desc: 'Todos os meses publicados, em PDF, sem pedir a ninguém.' },
        { icone: 'clock', titulo: 'Conferir o ponto', desc: 'As batidas do mês, dia a dia, e o espelho para conferir antes de assinar.' },
        { icone: 'plane', titulo: 'Solicitar férias', desc: 'O pedido nasce sobre o saldo real. Não dá para pedir o que não existe.' },
        { icone: 'gift', titulo: 'Ver benefícios', desc: 'VT, VR e o que mais a convenção garante, com o valor da competência.' },
        { icone: 'calendar', titulo: 'Ver a escala', desc: 'A escala publicada, do jeito que o operacional a montou. É a mesma, não uma cópia.' },
        { icone: 'folder', titulo: 'Baixar documentos', desc: 'Os documentos da pessoa que estão no GED, disponíveis para ela.' },
        { icone: 'megaphone', titulo: 'Ler comunicados', desc: 'O que a empresa publicou — com registro de leitura do lado de lá.' },
        { icone: 'calculator', titulo: 'Simular rescisão', desc: 'Quanto receberia se saísse hoje, pela CCT. Simulação, não promessa.' },
        { icone: 'message-square', titulo: 'Ouvidoria', desc: 'Canal direto para o que não cabe no grupo nem no supervisor.' }] },

    { t: 'passos', kicker: 'O primeiro acesso', icone: 'key-round', titulo: 'Como começar a usar',
      passos: [
        { icone: 'user-check', titulo: 'Pedir o vínculo', desc: 'O DP liga o seu usuário ao seu cadastro de colaborador. Sem isso, nada aparece.' },
        { icone: 'log-in', titulo: 'Entrar', desc: 'Mesmo endereço do sistema, mesmo login. O portal reconhece quem você é e mostra só o seu.' },
        { icone: 'eye', titulo: 'Conferir o Início', desc: 'Holerite, férias, benefícios e documentos. Se algum número estiver estranho, fale antes do fechamento.' },
        { icone: 'pen-tool', titulo: 'Assinar o que espera você', desc: 'Assinaturas pendentes mostra o que precisa da sua assinatura — inclusive o espelho de ponto.' },
        { icone: 'smartphone', titulo: 'Bater ponto', desc: 'Pelo celular, com reconhecimento facial. Sem internet, a batida fica guardada e sobe depois.', destaque: true }] },

    { t: 'cards', kicker: 'Bater ponto', titulo: 'Como funciona a batida pelo celular', cols: 3,
      cards: [
        { icone: 'scan-face', titulo: 'Reconhecimento facial', desc: 'A comparação acontece no próprio aparelho. A foto e a medida do rosto vão junto com a batida.', cor: 'F26A21' },
        { icone: 'wifi-off', titulo: 'Sem internet, funciona', desc: 'A batida é guardada no aparelho e entra como pendente de conferência. Quando reconecta, sobe sozinha.', cor: '38BDF8' },
        { icone: 'shield-check', titulo: 'O servidor reconfere', desc: 'Na sincronização, o servidor compara o rosto de novo. Passou, vira definitiva; não passou, vira pendência do DP.', cor: '17297B' }],
      nota: { icone: 'clock', texto: 'A hora do aparelho e a hora do servidor são guardadas as duas. Divergência grande marca a batida como suspeita — nunca a apaga.' } },

    { t: 'cardsLargos', kicker: 'Perguntas que o portal responde', titulo: 'Antes de ligar para o DP, olhe aqui',
      cards: [
        { icone: 'help-circle', titulo: '«Meu holerite já saiu?»', desc: 'Contracheque. Se o mês não aparece, a folha ainda não foi publicada — e ninguém mais recebeu também.' },
        { icone: 'help-circle', titulo: '«Quantos dias de férias eu tenho?»', desc: 'Minhas férias mostra o saldo real, e o pedido é feito sobre ele.' },
        { icone: 'help-circle', titulo: '«Eu bati ponto ontem?»', desc: 'Meu ponto mostra as batidas do mês. Batida faltando é melhor descobrir hoje que no dia 30.' },
        { icone: 'help-circle', titulo: '«Quando eu trabalho semana que vem?»', desc: 'Minha escala traz a escala publicada. Se mudou, mudou lá também.' }] },

    { t: 'contato', kicker: 'Precisa de ajuda?', titulo: 'Fale com a gente.',
      frase: 'O portal é seu. Use.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
