/** Manual da GESTÃO DE PESSOAS. 31 telas: GED documental, ponto eletrônico, espelho da
 *  Portaria 671, saúde ocupacional, SST, aptidão de vigilante e uniforme/EPI. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_03_Gestao_de_Pessoas',
  titulo: 'Manual da Gestão de Pessoas — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 03', titulo: 'Gestão',
      destaque: 'de Pessoas',
      sub: 'O acervo documental, o ponto eletrônico na Portaria 671, a saúde ocupacional e a aptidão do vigilante — tudo o que prova que a pessoa pode trabalhar.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Para', valor: 'DP, RH e SST' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'folder-check', titulo: 'Aqui mora a prova',
      texto: 'Este módulo existe para uma coisa: provar. Provar que o documento foi assinado, que a jornada foi essa, que o exame está válido, que o vigilante está apto e que o EPI foi entregue. Quando alguém questiona, é daqui que sai a resposta.',
      chips: ['GED — Documentos', 'GED · Kits', 'GED · Assinaturas', 'Ponto eletrônico', 'Ponto · Espelho', 'Saúde · Exames', 'SST', 'Vigilante · Aptidão', 'Uniforme/EPI'],
      nota: { icone: 'scale', texto: 'Vigilante sem reciclagem válida não pode assumir posto. A régua trata ausência de dado como inapto — nunca como válido.' } },

    { t: 'selos', kicker: 'Em números', titulo: 'O acervo de hoje',
      selos: [
        { icone: 'files', valor: '4.641', label: 'documentos no GED', cor: 'F26A21' },
        { icone: 'package', valor: '137', label: 'kits documentais', cor: '38BDF8' },
        { icone: 'clock', valor: '50', label: 'fechamentos de ponto', cor: '17297B' },
        { icone: 'shield-check', valor: '24', label: 'meses de validade da reciclagem', destaque: true, cor: 'F26A21' }],
      sub: 'O acervo cresce todo mês: cada contracheque, comprovante e escala gerada entra aqui automaticamente.' },

    { t: 'cardsLargos', kicker: 'O ponto de partida', titulo: 'O que doía antes',
      cards: [
        { icone: 'folder-x', titulo: 'Documento vivia em pasta de e-mail', desc: 'Achar o contracheque de um mês antigo era caçada. Agora são 4.641 documentos indexados por tipo, colaborador e competência.' },
        { icone: 'package-x', titulo: 'O kit do condomínio era montado à mão', desc: 'Alguém juntava contracheque, comprovante, escala e guia todo mês. Hoje o sistema materializa o kit e mostra a porcentagem de conclusão de cada um.' },
        { icone: 'file-warning', titulo: 'Ninguém sabia quem estava sem reciclagem', desc: 'Descobria-se na fiscalização. A régua de aptidão hoje separa apto, vencido e sem dado — e trata sem dado como inapto.' },
        { icone: 'hard-hat', titulo: 'Entrega de EPI era assinatura em papel', desc: 'A ficha sumia justamente quando era preciso. Agora a entrega fica registrada com data e a ficha sai em PDF.' }] },

    { t: 'tela', kicker: 'Visão geral', titulo: 'O módulo em quatro números',
      imagem: P + 'gp-visao-geral.png', legenda: 'Gestão de Pessoas › Visão geral',
      notas: [
        { titulo: 'Documentos, ASOs, EPIs, batidas', desc: 'Os quatro pilares do módulo num olhar. Cada cartão abre a lista que está por trás dele.' },
        { titulo: 'ASO por status', desc: 'Realizado, Vencido e Agendado. O número de vencidos é a fila mais urgente que este módulo tem.' },
        { titulo: 'GED por tipo', desc: 'Comprovante de pagamento, contracheque, comprovante de VT e de VR, folha de ponto. É o retrato do que o kit consome.' },
        { titulo: 'Batidas de ponto', desc: 'O acumulado de marcações registradas. É o volume que alimenta o AFD da Portaria 671.' }] },

    // ── GED ────────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'GED — Documentos', titulo: 'O acervo, documento por documento',
      imagem: P + 'gp-ged.png', legenda: 'Gestão de Pessoas › GED — Documentos',
      notas: [
        { titulo: 'Documento, tipo e colaborador', desc: 'Toda peça do acervo é atribuída a uma pessoa e a um tipo. É assim que ela é encontrada depois.' },
        { titulo: 'A coluna Assinado', desc: 'Verde quer dizer que a assinatura já saiu. Documento sem assinatura não serve de prova — e essa coluna diz qual é qual.' },
        { titulo: 'De onde vem', desc: 'A maior parte entra sozinha: contracheque gerado, comprovante de PIX pago, escala publicada.' },
        { titulo: 'Remover é definitivo', desc: 'O botão existe, mas apaga do acervo. Documento que virou prova não se remove por conveniência.' }] },

    { t: 'tela', kicker: 'GED · Kits', titulo: 'O kit documental de cada condomínio',
      imagem: P + 'gp-ged-kits.png', legenda: 'Gestão de Pessoas › GED · Kits',
      notas: [
        { titulo: 'A coluna Conclusão', desc: 'A porcentagem do kit já montada. 90% quer dizer que falta pouco — e a tela do GED diz exatamente qual peça falta.' },
        { titulo: 'Em montagem × Completo', desc: 'Completo é kit com todas as peças da competência. Em montagem ainda espera contracheque, guia ou nota.' },
        { titulo: 'Leia a frase do topo', desc: 'Ela separa duas coisas: o kit MATERIALIZADO pelo sistema e o kit ENTREGUE ao cliente, que é o do Drive.' },
        { titulo: 'Gerar PDFs, anexar NFS-e, enviar', desc: 'Os três botões da linha são o caminho do kit: gerar as peças, anexar a nota e mandar para o cliente.' }] },

    { t: 'tela', kicker: 'GED · Assinaturas', titulo: 'Assinar uma pasta inteira de uma vez',
      imagem: P + 'gp-ged-assinaturas.png', legenda: 'Gestão de Pessoas › GED · Central de assinaturas',
      notas: [
        { titulo: 'Três filas na mesma linha', desc: 'Quantos esperam a EMPRESA, quantos esperam FUNCIONÁRIOS e quantos esperam CLIENTES. Cada uma se resolve de um jeito.' },
        { titulo: '«Assinar todos»', desc: 'Assina a pasta inteira de uma vez. O código OTP vai para o seu e-mail e cada documento recebe a assinatura ICP-Brasil da empresa.' },
        { titulo: 'Por pasta, não por documento', desc: 'A organização é a do kit: «Kit 09/2026 · CONDOMINIO X». Assinar por pasta é o que torna o volume administrável.' },
        { titulo: 'Esperam funcionários', desc: 'Esses não dependem de você: dependem de o colaborador entrar no portal dele. É onde o portal precisa ser usado.' }] },

    { t: 'passos', kicker: 'O kit do mês', icone: 'package', titulo: 'Como o kit chega ao síndico',
      passos: [
        { icone: 'lock', titulo: 'Fechar o ponto', desc: 'Sem o mês do ponto fechado, não há espelho nem folha — e sem eles não há kit.' },
        { icone: 'file-text', titulo: 'Gerar as peças', desc: 'Contracheque, comprovante de pagamento, espelho e escala saem da folha da competência.' },
        { icone: 'receipt', titulo: 'Anexar a NFS-e', desc: 'A nota do serviço daquele condomínio entra no kit, junto com as guias.' },
        { icone: 'check-check', titulo: 'Conferir a conclusão', desc: 'A porcentagem tem de chegar a 100%. Abaixo disso, falta peça — e o síndico vai notar.' },
        { icone: 'send', titulo: 'Enviar', desc: 'O kit vai para o Drive do cliente. É esse o kit que vale como entrega.', destaque: true }] },

    // ── Ponto ──────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Ponto · Espelho', titulo: 'O fechamento na Portaria 671',
      imagem: P + 'gp-ponto-espelho.png', legenda: 'Gestão de Pessoas › Ponto · Espelho',
      notas: [
        { titulo: 'Um fechamento por pessoa e competência', desc: 'Dias trabalhados, horas, hora extra 50%, faltas e atraso em minutos. É o resumo legal do mês.' },
        { titulo: 'O selo Fechado', desc: 'Competência encerrada. Depois disso, mudar exige reabrir com registro — não se altera um espelho fechado em silêncio.' },
        { titulo: 'Dias zero com horas zero', desc: 'Acontece com quem entrou ou saiu no meio do mês, ou esteve afastado. Não é erro, mas merece um olhar.' },
        { titulo: 'Por que Portaria 671', desc: 'É a norma do MTP que define o espelho, o AFD e o AEJ. O formato desta tela existe para caber nela.' }] },

    { t: 'tela', kicker: 'Ponto eletrônico', titulo: 'As batidas chegando, ao vivo',
      imagem: P + 'gp-ponto.png', legenda: 'Gestão de Pessoas › Ponto eletrônico',
      notas: [
        { titulo: 'Entrada e Saída, com data e hora', desc: 'A lista mais recente primeiro. É onde se confere se a batida de alguém chegou mesmo.' },
        { titulo: 'O status Pendente', desc: 'Batida registrada e ainda não conferida. É o estado normal de uma marcação recém-chegada.' },
        { titulo: '«Fora_local» é diferente', desc: 'A batida aconteceu longe da coordenada do posto. Não é rejeitada — é marcada, para alguém olhar.' },
        { titulo: 'Por que não apagar', desc: 'Batida suspeita apagada vira buraco no AFD. O sistema prefere marcar e explicar a sumir com o registro.' }] },

    { t: 'cards', kicker: 'Portaria 671/2021', titulo: 'Os três arquivos que a norma exige', cols: 3,
      cards: [
        { icone: 'file-digit', titulo: 'AFD', desc: 'Arquivo Fonte de Dados: todas as marcações, no layout do Anexo I, com verificação CRC-16 e numeração sequencial contínua por estabelecimento.', cor: 'F26A21' },
        { icone: 'file-clock', titulo: 'AEJ', desc: 'Arquivo Eletrônico de Jornada: a jornada apurada, com o que foi previsto, o que foi cumprido e o que foi compensado.', cor: '38BDF8' },
        { icone: 'file-signature', titulo: 'Espelho', desc: 'O relatório que o colaborador confere e assina. É a peça que entra no kit e que a fiscalização pede primeiro.', cor: '17297B' }],
      nota: { icone: 'shield-check', texto: 'A numeração do AFD é contínua por CNPJ, não por origem da batida. Quebrar essa sequência invalida o arquivo inteiro.' } },

    // ── Vigilante ──────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Vigilante · Aptidão', titulo: 'Quem pode assumir posto hoje',
      imagem: P + 'gp-vigilante-aptidao.png', legenda: 'Gestão de Pessoas › Vigilante · Aptidão',
      notas: [
        { titulo: 'Os quatro números do topo', desc: 'Escalados hoje sujeitos à régua, aptos, vencidos e sem dado. A conta é feita para a data do dia.' },
        { titulo: '«Sem dado» é o pior estado', desc: 'Pior que vencido: é gente escalada que o DP nem cadastrou. O quadro à esquerda nomeia quem.' },
        { titulo: 'A régua em vigor está escrita', desc: 'Funções que exigem credencial, validade da reciclagem em 24 meses da conclusão, e a regra de ouro.' },
        { titulo: 'A regra de ouro', desc: '«Ausência de dado = Inapto (nunca válido)». O sistema prefere errar barrando a errar liberando.' }] },

    { t: 'lista', kicker: 'Saúde e SST', titulo: 'O que mais este módulo controla',
      itens: [
        { icone: 'stethoscope', titulo: 'Saúde · Exames (ASO)', desc: 'Admissional, periódico, de retorno e demissional. Sem ASO válido, a pessoa não trabalha (NR-7).' },
        { icone: 'hard-hat', titulo: 'SST — Entrega de EPI', desc: 'O que foi entregue, para quem e quando. A ficha de EPI sai em PDF a partir daqui.' },
        { icone: 'shirt', titulo: 'Uniforme/EPI — grade', desc: 'O SKU e o tamanho de cada item. Sem grade cadastrada, a entrega não sabe o que entregar.' },
        { icone: 'graduation-cap', titulo: 'RH · Treinamentos', desc: 'Cursos, inscrições e a reciclagem que mantém a aptidão do vigilante de pé.' },
        { icone: 'briefcase', titulo: 'RH · Cargos', desc: 'A estrutura de cargos e os planos de carreira que se apoiam nela.' },
        { icone: 'bot', titulo: 'Consultor de Pessoas IA', desc: 'Pergunte em português sobre gente, documento ou aptidão — inclusive anexando um arquivo.' }] },

    { t: 'cards', kicker: 'Novidades', titulo: 'O que chegou em setembro de 2026', escuro: true, cols: 4,
      cards: [
        { icone: 'file-check', titulo: 'AFD e AEJ completos', desc: 'Os dois arquivos fiscais do ponto no layout do MTP, com CRC-16 e sequência por estabelecimento.' },
        { icone: 'shield-alert', titulo: 'Régua de aptidão do vigilante', desc: 'Apto, vencido e sem dado — com a regra escrita na própria tela, não escondida no código.', destaque: true },
        { icone: 'shirt', titulo: 'Grade de uniforme e EPI', desc: 'SKU e tamanho por pessoa, e entrega em lote para quando chega o carregamento.' },
        { icone: 'pen-tool', titulo: 'Central de assinaturas', desc: 'Tudo o que espera assinatura num lugar só — inclusive o que espera a assinatura da empresa.' }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'user-x', titulo: 'Escalar vigilante «sem dado»', desc: 'Não é burocracia: é posto assumido por quem a lei não permite. O quadro nomeia quem — resolva antes da escala.' },
        { icone: 'package-x', titulo: 'Enviar kit abaixo de 100%', desc: 'O síndico percebe a peça que falta antes de você. A coluna Conclusão existe para isso não acontecer.' },
        { icone: 'file-x', titulo: 'Confiar em documento não assinado', desc: 'A coluna Assinado é o que separa arquivo de prova. Documento sem assinatura não defende ninguém.' },
        { icone: 'calendar-x', titulo: 'Deixar ASO vencer', desc: 'Sem ASO válido o colaborador não pode trabalhar — e a empresa responde pelo dia em que ele trabalhou assim.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
