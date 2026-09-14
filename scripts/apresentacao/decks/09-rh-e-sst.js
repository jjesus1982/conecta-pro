/** Manual de RH & SAÚDE OCUPACIONAL. 59 + 23 telas. Recrutamento, treinamento, carreira,
 *  clima, turnover, medidas disciplinares — e ASO, EPI, riscos, CAT, CIPA e LTCAT. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_09_RH_e_Saude_Ocupacional',
  titulo: 'Manual de RH & Saúde Ocupacional — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 09', titulo: 'RH e Saúde',
      destaque: 'Ocupacional',
      sub: 'Recrutar, treinar, avaliar e desenvolver — e provar que cada pessoa está apta, examinada e equipada para o posto onde trabalha.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Para', valor: 'RH, SST e coordenação' }] },

    { t: 'tela', kicker: 'RH', titulo: 'O quadro de gente, em quatro números',
      imagem: P + 'rh-visao-geral.png', legenda: 'Recursos Humanos › Dashboard',
      notas: [
        { titulo: 'Colaboradores ativos', desc: 'O quadro de hoje. O bloco «Quadro por situação» abaixo abre em ativo, inativo, demitido, PJ, candidato e suspenso.' },
        { titulo: 'Candidatos e entrevistas em zero', desc: 'Não é falha da tela: o recrutamento ainda é feito por fora. As telas estão prontas e esperando o primeiro lançamento.' },
        { titulo: 'Certificações', desc: 'Quantas certificações a empresa controla, e em que competência. É o que sustenta a aptidão do vigilante.' },
        { titulo: 'As 59 telas do módulo', desc: 'Vagas, candidaturas, onboarding, treinamentos, cursos, avaliações, carreira, clima, turnover e as calculadoras da CCT.' }] },

    { t: 'cards', kicker: 'RH', titulo: 'As calculadoras da convenção coletiva', cols: 4,
      cards: [
        { icone: 'clock', titulo: 'Hora extra', desc: 'Calcula pela regra da CCT vigente, não pelo genérico da CLT.' },
        { icone: 'moon', titulo: 'Adicional noturno', desc: 'Percentual e hora reduzida conforme a convenção do setor.' },
        { icone: 'gift', titulo: '13º salário', desc: 'Proporcional, com médias de variáveis, na regra da categoria.' },
        { icone: 'scale', titulo: 'Validar salário contra o piso', desc: 'Aponta quem está abaixo do piso antes de virar passivo.', destaque: true }],
      nota: { icone: 'book-open', texto: 'A CCT do setor muda todo ano. As calculadoras leem a convenção cadastrada — trocar a convenção troca o resultado de todas.' } },

    { t: 'lista', kicker: 'RH', titulo: 'O ciclo da pessoa, depois que ela entra',
      itens: [
        { icone: 'clipboard-check', titulo: 'Onboarding', desc: 'A lista do que precisa acontecer nos primeiros dias — e o que ainda está pendente.' },
        { icone: 'graduation-cap', titulo: 'Treinamentos e cursos', desc: 'O catálogo, as inscrições e quem concluiu. É daqui que sai a reciclagem do vigilante.' },
        { icone: 'star', titulo: 'Avaliações', desc: 'Ciclos de avaliação de desempenho, com resultado ligado à ficha da pessoa.' },
        { icone: 'trending-up', titulo: 'Carreira', desc: 'Planos de carreira e os degraus entre cargos.' },
        { icone: 'heart', titulo: 'Clima', desc: 'Como a equipe está se sentindo — a pesquisa que antecede o pedido de demissão.' },
        { icone: 'log-out', titulo: 'Turnover', desc: 'Quem saiu, quando e por quê. O motivo do desligamento é registrado, não suposto.' }] },

    { t: 'tela', kicker: 'Turnover', titulo: 'Quem saiu — e por quê',
      imagem: P + 'rh-turnover.png', legenda: 'Recursos Humanos › Turnover',
      notas: [
        { titulo: 'Colaborador, cargo e data', desc: 'Os desligamentos recentes, do mais novo para o mais velho. O cargo mostra onde a rotatividade dói.' },
        { titulo: 'A coluna Motivo', desc: 'Hoje ela está em «aguardando dado» na lista inteira. Sem motivo registrado, não há análise de causa possível.' },
        { titulo: 'Como preencher', desc: 'A ação «Registrar motivo de desligamento» existe para isso, e leva menos de um minuto por pessoa.' },
        { titulo: 'Por que insistir', desc: 'Turnover sem motivo é um número que assusta e não ensina. Com motivo, vira decisão: salário, chefia, escala ou distância.' }] },

    { t: 'tela', kicker: 'Certificados', titulo: 'As certificações da competência',
      imagem: P + 'rh-certificados.png', legenda: 'Recursos Humanos › Certificados',
      notas: [
        { titulo: 'Colaborador e competência', desc: 'A certificação é gerada por competência — normalmente a mesma da folha do mês.' },
        { titulo: 'Tipo «folha mensal»', desc: 'É a certificação que acompanha a folha. Outros tipos existem: reciclagem, curso e formação.' },
        { titulo: 'O status pendente', desc: 'Certificação gerada e ainda não concluída. Uma lista inteira em pendente é uma competência que ninguém fechou.' },
        { titulo: 'Onde isso importa', desc: 'É esta certificação que sustenta a aptidão do vigilante em Gestão de Pessoas — as duas telas olham o mesmo dado.' }] },

    { t: 'secao', kicker: 'A outra metade', icone: 'stethoscope', titulo: 'Saúde Ocupacional',
      texto: 'Segurança do trabalho não é papelada: é a diferença entre um acidente tratado e uma autuação. Vinte e três telas cobrem exame, risco, EPI, acidente, estabilidade e os laudos que a lei exige.',
      chips: ['Exames (ASO)', 'EPI', 'Riscos', 'CAT', 'Afastamentos', 'Estabilidade', 'Alertas', 'CIPA', 'LTCAT', 'PCMSO'],
      nota: { icone: 'shield-alert', texto: 'Sem ASO válido o colaborador não pode trabalhar (NR-7). Não é recomendação — é condição.' } },

    { t: 'tela', kicker: 'Saúde Ocupacional', titulo: 'O painel da saúde no trabalho',
      imagem: P + 'sst-visao-geral.png', legenda: 'Saúde Ocupacional › Visão geral',
      notas: [
        { titulo: 'ASOs e aptos', desc: 'Cuidado com a leitura: «Aptos» é o resultado do exame. Validade é outra coisa — está no quadro ao lado.' },
        { titulo: 'ASO por status é o alarme', desc: 'Realizado, Vencido e Agendado. O número de vencidos é a fila de trabalho mais urgente do módulo.' },
        { titulo: 'Riscos por nível', desc: 'Alto, médio e baixo, mapeados por posto. Risco alto exige medida de controle registrada.' },
        { titulo: 'NR-1 Compliance (PDF)', desc: 'O botão do topo gera o documento de conformidade com a NR-1 — o que a fiscalização pede primeiro.' }] },

    { t: 'tela', kicker: 'Exames', titulo: 'O ASO de cada pessoa',
      imagem: P + 'sst-exames.png', legenda: 'Saúde Ocupacional › Exames (ASO)',
      notas: [
        { titulo: 'Tipo do exame', desc: 'Admissional, periódico, de retorno ao trabalho, de mudança de risco e demissional. Cada um tem gatilho próprio.' },
        { titulo: 'A coluna Validade', desc: 'A data em que o ASO deixa de valer. É ela, e não a situação, que determina se a pessoa pode trabalhar amanhã.' },
        { titulo: 'A coluna Situação', desc: '«Apto» é o parecer do médico no dia do exame. Um ASO apto e vencido não autoriza ninguém a trabalhar.' },
        { titulo: 'ASOs vencendo em 30 dias', desc: 'A aba ao lado isola quem precisa ser agendado agora, antes de virar impedimento.' }] },

    { t: 'tela', kicker: 'EPI', titulo: 'A entrega que vira prova',
      imagem: P + 'sst-epi.png', legenda: 'Saúde Ocupacional › EPI — Entregas',
      notas: [
        { titulo: 'Uma linha por item entregue', desc: 'Não por pessoa: por item. A mesma pessoa aparece várias vezes, uma para cada equipamento.' },
        { titulo: 'A coluna CA', desc: 'O Certificado de Aprovação do EPI. Sem CA válido, o equipamento não cumpre a norma — por mais adequado que pareça.' },
        { titulo: 'Data de entrega', desc: 'É ela que conta na fiscalização e na defesa. EPI entregue sem data registrada vale pouco.' },
        { titulo: 'A ficha em PDF', desc: 'A ação «Ficha de EPI — gerar» consolida tudo o que a pessoa recebeu, para ela assinar.' }] },

    { t: 'tela', kicker: 'Riscos', titulo: 'O mapa dos riscos do trabalho',
      imagem: P + 'sst-riscos.png', legenda: 'Saúde Ocupacional › Riscos ocupacionais',
      notas: [
        { titulo: 'Categoria e descrição', desc: 'Acidente, ergonômico, físico. A descrição é específica do nosso trabalho: ronda em área escura, portaria 12h em pé, calor de Manaus.' },
        { titulo: 'A coluna Nível', desc: 'Alto, médio ou baixo. É o nível que determina a obrigatoriedade da medida de controle.' },
        { titulo: 'Identificado × Controlado', desc: 'Identificado é risco mapeado e ainda sem medida. Controlado já tem ação implantada. A diferença é a sua fila.' },
        { titulo: 'Alimenta o LTCAT e o PCMSO', desc: 'O mapa de riscos é a base dos dois laudos. Risco não mapeado não entra em laudo nenhum.' }] },

    { t: 'cards', kicker: 'Saúde Ocupacional', titulo: 'O que mais o módulo controla', cols: 4,
      cards: [
        { icone: 'hard-hat', titulo: 'EPI', desc: 'Entrega registrada com data, e a ficha de EPI em PDF — a prova de que o equipamento foi dado.' },
        { icone: 'siren', titulo: 'CAT', desc: 'Comunicação de Acidente de Trabalho, com transmissão do S-2210 ao eSocial.' },
        { icone: 'shield', titulo: 'Estabilidade', desc: 'Quem tem garantia de emprego e até quando: acidente, gestação, CIPA.', destaque: true },
        { icone: 'file-text', titulo: 'LTCAT e PCMSO', desc: 'O laudo das condições ambientais e a esteira de exames dos próximos seis meses.' }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'calendar-x', titulo: 'Confundir «apto» com «válido»', desc: 'Apto é o parecer do médico naquele dia. Válido é a data de vencimento. Um ASO apto e vencido não autoriza trabalho nenhum.' },
        { icone: 'user-x', titulo: 'Demitir quem tem estabilidade', desc: 'Acidente, gestação e mandato de CIPA geram garantia de emprego. A tela Estabilidade existe exatamente para essa consulta.' },
        { icone: 'clock-alert', titulo: 'Atrasar a CAT', desc: 'A comunicação de acidente tem prazo próprio. Atraso é multa — e enfraquece a defesa se virar processo.' },
        { icone: 'hard-hat', titulo: 'Entregar EPI sem registrar', desc: 'EPI entregue e não registrado é, para todos os efeitos, EPI não entregue. A responsabilidade fica com a empresa.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
