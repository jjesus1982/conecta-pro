/** Manual do módulo OPERACIONAL. Estrutura e nomes de aba vêm do inventário real do
 *  redesign (GET /api/v1/redesign/data/operacional): 8 grupos, 106 telas. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_01_Operacional',
  titulo: 'Manual do Operacional — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 01', titulo: 'Operacional',
      destaque: 'o dia inteiro em uma tela',
      sub: 'Postos, escalas, presença, diaristas, rondas e ocorrências — tudo o que a operação vive, no lugar onde ela acontece.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Para', valor: 'Supervisão e coordenação' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'compass', titulo: 'Oito grupos. Um dia de trabalho.',
      texto: 'A barra da esquerda tem oito grupos. Cada grupo abre em abas, no topo. Você não precisa decorar nada: se está procurando alguma coisa, ela está no grupo cujo nome descreve o que você quer fazer.',
      chips: ['Visão Geral', 'Escalas & Turnos', 'Postos & Presença', 'Equipe & Ponto', 'Diaristas', 'Disciplina & RH', 'Rondas & Ocorrências', 'Comunicação'],
      nota: { icone: 'lightbulb', texto: 'Se você só tem cinco minutos por dia, fique na Visão Geral. Ela foi feita exatamente para esses cinco minutos.' } },

    { t: 'selos', kicker: 'Em números', titulo: 'O que este módulo já opera hoje',
      selos: [
        { icone: 'building-2', valor: '15', label: 'postos ativos', cor: 'F26A21' },
        { icone: 'users', valor: '68', label: 'postos de trabalho na grade', cor: '38BDF8' },
        { icone: 'user-check', valor: '67', label: 'alocações vigentes', cor: '17297B' },
        { icone: 'layout-grid', valor: '106', label: 'telas ligadas a dado real', destaque: true, cor: 'F26A21' }],
      sub: 'Nenhuma tela de exemplo: cada número desta página sai do banco de produção no momento em que a página abre.' },

    { t: 'cardsLargos', kicker: 'O ponto de partida', titulo: 'O que doía antes',
      cards: [
        { icone: 'phone-off', titulo: 'Posto descoberto só se descobria tarde', desc: 'O aviso vinha pelo síndico, quase sempre depois do turno começar. Hoje a aba Cobertura em risco mostra de manhã o posto que vai ficar sem gente.' },
        { icone: 'file-x', titulo: 'A escala vivia no papel e no WhatsApp', desc: 'Cada supervisor tinha a sua versão, e nenhuma era a versão. Agora só existe uma escala publicada — e ela é a que vale para o ponto, para a folha e para o cliente.' },
        { icone: 'clock-alert', titulo: 'Hora extra aparecia na folha', desc: 'O excesso era descoberto no fechamento, quando já era dinheiro. A apuração compara ponto contra escala todo dia, enquanto ainda dá para corrigir.' },
        { icone: 'search-x', titulo: 'Ocorrência sem rastro', desc: 'Ficava no grupo do WhatsApp e sumia. Agora nasce com foto, hora, posto e responsável — e o cliente pode receber o mesmo relato, sem versão paralela.' }] },

    { t: 'passos', kicker: 'A rotina', icone: 'sunrise', titulo: 'Os cinco minutos da manhã',
      passos: [
        { icone: 'eye', titulo: 'Abra a Visão Geral', desc: 'É a primeira aba do primeiro grupo. Mostra postos ativos, gente alocada e as últimas ocorrências.' },
        { icone: 'triangle-alert', titulo: 'Veja Cobertura em risco', desc: 'Todo posto abaixo de 100% da grade contratual aparece aqui antes de virar problema do cliente.' },
        { icone: 'user-plus', titulo: 'Escale o substituto', desc: 'Da própria linha do posto em risco. O sistema já sugere quem está de folga e apto.' },
        { icone: 'megaphone', titulo: 'Comunique quem mudou', desc: 'Se alguém trocou de posto, o comunicado sai do grupo Comunicação e chega no portal da pessoa.' },
        { icone: 'circle-check', titulo: 'Confira a Presença', desc: 'Quem bateu ponto e quem não bateu, ao vivo. Ausência sem justificativa vira pendência.', destaque: true }] },

    // ── Grupo 1 ────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Visão Geral', titulo: 'A primeira tela do seu dia',
      imagem: P + 'op-visao-geral.png', legenda: 'Operacional › Visão Geral › Resumo',
      notas: [
        { titulo: 'Os quatro cartões do topo', desc: 'Postos ativos, colaboradores, alocações vigentes e ocorrências de hoje. Clique em qualquer um para abrir a lista por trás do número.' },
        { titulo: 'Cobertura dos postos hoje', desc: 'Verde é posto coberto. Laranja é gente em campo cobrindo. Vermelho pede ação agora.' },
        { titulo: 'Últimas ocorrências', desc: 'Do mais novo para o mais velho, com a gravidade ao lado. Um clique abre a ocorrência inteira.' },
        { titulo: 'As abas do topo', desc: 'Resumo, KPIs, Cobertura, Mapa, Campo, Triagem, Relatórios e três abas de IA.' }] },

    { t: 'lista', kicker: 'Visão Geral', titulo: 'O que cada aba entrega',
      sub: 'São onze abas neste grupo. Estas são as que resolvem o dia.',
      itens: [
        { icone: 'gauge', titulo: 'Resumo', desc: 'O panorama de hoje: postos, gente, alocações e ocorrências. É onde o dia começa.' },
        { icone: 'chart-column', titulo: 'KPIs', desc: 'Quatro números do estado atual: postos ativos, ocorrências abertas, rondas do mês e substituições do mês.' },
        { icone: 'shield-alert', titulo: 'Cobertura em risco', desc: 'A aba mais importante do módulo: todo posto abaixo de 100% da grade contratual, do pior para o melhor.' },
        { icone: 'map', titulo: 'Mapa', desc: 'Quais postos já têm coordenada gravada. Sem coordenada, o check-in por GPS não tem contra o que medir.' },
        { icone: 'radio', titulo: 'Campo', desc: 'Quem está em campo agora: check-in de gerente, ronda em andamento, ordem de serviço aberta.' },
        { icone: 'inbox', titulo: 'Triagem', desc: 'O que chegou e ainda não foi tratado — justificativas, pedidos e alertas esperando resposta.' }] },

    { t: 'tela', kicker: 'Visão Geral', titulo: 'Cobertura em risco: o alarme antes do incêndio',
      imagem: P + 'op-cobertura-risco.png', legenda: 'Operacional › Visão Geral › Cobertura em risco',
      notas: [
        { titulo: 'A frase do topo', desc: '«5 posto(s) abaixo de 100% · aja antes de descobrir». Ela resume a tela inteira.' },
        { titulo: 'A coluna Cobertura', desc: 'Quanto da grade contratual daquele posto está de fato preenchida hoje. 100% é o alvo.' },
        { titulo: 'Crítico e Atenção', desc: 'Crítico é posto muito abaixo do contratado. Atenção é folga pequena — ainda dá para resolver sem correria.' },
        { titulo: 'O botão Ver', desc: 'Abre o posto com quem está escalado e quem falta, que é de onde sai a decisão de escalar substituto.' }] },

    { t: 'tela', kicker: 'Visão Geral', titulo: 'Mapa: qual posto o sistema sabe onde fica',
      imagem: P + 'op-mapa.png', legenda: 'Operacional › Visão Geral › Mapa',
      notas: [
        { titulo: 'A conta do topo', desc: '«8/15 georreferenciados». É quantos postos têm coordenada gravada — hoje, pouco mais da metade.' },
        { titulo: 'Latitude e longitude', desc: 'A coordenada do posto. É ela que faz o check-in por GPS e a distância do gerente funcionarem.' },
        { titulo: 'Sem localização', desc: 'Posto com o selo cinza não valida check-in por proximidade. Vale a pena resolver: são poucos cliques em Localização do posto.' },
        { titulo: 'Por que isso importa', desc: 'Sem coordenada, o «17 m de distância» do check-in do gerente não pode ser provado.' }] },

    // ── Grupo 2 ────────────────────────────────────────────────────────────────
    { t: 'secao', kicker: 'Grupo 2', icone: 'calendar-days', titulo: 'Escalas & Turnos',
      texto: 'É aqui que a escala nasce, é conferida, aprovada e publicada. Vinte e duas abas — mas o caminho normal passa por cinco delas.',
      chips: ['Escalas do mês', 'Grade por pessoa', 'Editor visual', 'Gerar escala', 'Submeter', 'Aprovar', 'Publicar', 'Substituições'],
      nota: { icone: 'shield-check', texto: 'Enquanto não for publicada, a escala é rascunho: não vale para o ponto nem para a folha.' } },

    { t: 'tela', kicker: 'Escalas & Turnos', titulo: 'A escala do mês, posto a posto',
      imagem: P + 'op-escalas-mes.png', legenda: 'Operacional › Escalas & Turnos › Escalas do mês',
      notas: [
        { titulo: 'Uma linha por escala', desc: 'Cada posto tem a sua escala do mês. A frase do topo já diz o caminho: rascunho → aprovação → publicada.' },
        { titulo: 'A coluna Turnos', desc: 'Quantos turnos aquela escala tem no mês. Escala com 0 turno é escala vazia — e aparece assim mesmo, sem disfarce.' },
        { titulo: 'O selo Published', desc: 'Verde é escala publicada: vale para o ponto, para a folha e para o portal do colaborador.' },
        { titulo: 'Competência', desc: 'O mês a que a escala pertence. É por ela que o fechamento de ponto vai procurar a régua.' }] },

    { t: 'tela', kicker: 'Escalas & Turnos', titulo: 'A mesma escala, vista pela pessoa',
      imagem: P + 'op-escalas-grade.png', legenda: 'Operacional › Escalas & Turnos › Grade por pessoa',
      notas: [
        { titulo: 'Linha = colaborador', desc: 'A escala vista de quem trabalha, não do posto. É esta visão que a pessoa enxerga no portal dela.' },
        { titulo: 'A coluna Turnos', desc: 'Quantos turnos aquela pessoa tem no período. Número muito acima dos colegas é sinal de sobrecarga.' },
        { titulo: 'De e Até', desc: 'O intervalo que a escala dela cobre. Se o «Até» é antes do fim do mês, há buraco depois daquela data.' },
        { titulo: 'Para que serve', desc: 'Conferir descanso e 12x36 antes de publicar, e responder rápido «quando eu trabalho?» sem abrir o mês do posto.' }] },

    { t: 'tela', kicker: 'Escalas & Turnos', titulo: 'Editor visual: o preenchimento de cada escala',
      imagem: P + 'op-escalas-visual.png', legenda: 'Operacional › Escalas & Turnos › Editor visual',
      notas: [
        { titulo: 'A coluna Preenchidos', desc: 'Lê-se «153/153»: turnos com gente sobre turnos que existem. Igualdade é escala fechada.' },
        { titulo: 'Onde mora o problema', desc: 'Qualquer coisa diferente de x/x é turno sem ninguém — e é exatamente o que vira Cobertura em risco depois.' },
        { titulo: 'Tipo e Período', desc: '12x36 e a competência. Escala de tipo errado quebra a interjornada sem ninguém perceber.' },
        { titulo: 'Escala com 0 turno', desc: 'Existe, está publicada, e não tem nada dentro. Vale conferir antes que o mês comece.' }] },

    { t: 'passos', kicker: 'O caminho oficial', icone: 'route', titulo: 'Como a escala do mês nasce',
      passos: [
        { icone: 'wand-sparkles', titulo: 'Gerar escala', desc: 'O sistema monta o mês a partir da grade contratual do posto: turnos, 12x36 e folgas.' },
        { icone: 'pencil', titulo: 'Ajustar', desc: 'Editor visual ou grade. Férias, curso e preferência entram aqui.' },
        { icone: 'send', titulo: 'Submeter', desc: 'Manda para aprovação. Deste ponto em diante, quem edita fica registrado.' },
        { icone: 'check', titulo: 'Aprovar', desc: 'Só quem tem alçada. Aprovada, a escala pode ser publicada — mas ainda não foi.' },
        { icone: 'megaphone', titulo: 'Publicar', desc: 'Agora ela vale: aparece no portal do colaborador e passa a ser a régua do ponto.', destaque: true }] },

    // ── Grupo 3 ────────────────────────────────────────────────────────────────
    { t: 'secao', kicker: 'Grupo 3', icone: 'map-pin', titulo: 'Postos & Presença',
      texto: 'O posto como o cliente o conhece: onde fica, o que se faz nele, quem está lá agora e o que o turno anterior deixou para o próximo.',
      chips: ['Postos', 'Presença hoje', 'Ausentes hoje', 'Instruções de posto', 'Passagem de turno', 'Onde está o gerente', 'Check-in manual'] },

    { t: 'tela', kicker: 'Postos & Presença', titulo: 'O cadastro de cada posto',
      imagem: P + 'op-postos.png', legenda: 'Operacional › Postos & Presença › Postos',
      notas: [
        { titulo: 'Posto e Cliente', desc: 'O apelido que a operação usa e a razão social do condomínio que paga. São coisas diferentes de propósito.' },
        { titulo: 'Turno', desc: '12x36 ou diurno. É o turno do posto que decide o formato da escala que vai ser gerada para ele.' },
        { titulo: 'Vigilantes', desc: 'Quantas pessoas estão hoje alocadas naquele posto. Zero aqui é o mesmo zero que aparece na cobertura.' },
        { titulo: 'Ver posto', desc: 'Abre a ficha completa: endereço, coordenada, instrução de serviço e o contrato que o sustenta.' }] },

    { t: 'tela', kicker: 'Postos & Presença', titulo: 'Quem está no posto agora',
      imagem: P + 'op-presenca.png', legenda: 'Operacional › Postos & Presença › Presença hoje',
      notas: [
        { titulo: 'A frase do topo', desc: 'Resume o dia inteiro: «12 presente(s) · 2 atrasado(s) · 2 ausente(s) de 16 esperado(s)».' },
        { titulo: 'Esperados × Presentes', desc: 'Esperados vem da escala publicada. Presentes vem do ponto batido. A diferença é o seu problema do dia.' },
        { titulo: 'Atrasados e Ausentes', desc: 'Em laranja, para achar de longe. Atrasado ainda chega; ausente já precisa de cobertura.' },
        { titulo: 'Sem internet no posto', desc: 'A batida offline entra como pendente de conferência e é reconferida pelo servidor quando o aparelho reconecta.' }] },

    { t: 'tela', kicker: 'Postos & Presença', titulo: 'Onde está o gerente',
      imagem: P + 'op-gerente-hoje.png', legenda: 'Operacional › Postos & Presença › Onde está o gerente',
      notas: [
        { titulo: 'Chegou, saiu, tempo', desc: 'O gerente marca «cheguei no posto» e «saí do posto» pelo celular. A tela calcula quanto tempo ele ficou.' },
        { titulo: 'A coluna Distância', desc: '«17 m» é a distância entre o celular dele e a coordenada do posto no momento do check-in. É o que transforma visita em prova.' },
        { titulo: 'A frase do topo', desc: 'Diz a fonte sem rodeio: «últimos 7 dias · fonte: visitas (check-in do celular)».' },
        { titulo: 'Encerrada', desc: 'Visita que já teve saída registrada. Visita sem saída fica aberta — e aparece como «no posto agora».' }] },

    { t: 'lista', kicker: 'Postos & Presença', titulo: 'As abas que você usa toda semana',
      itens: [
        { icone: 'building', titulo: 'Postos', desc: 'Cadastro, endereço, grade contratual e localização de cada posto.' },
        { icone: 'user-check', titulo: 'Presença hoje', desc: 'Quem bateu ponto, por posto, ao vivo.' },
        { icone: 'user-x', titulo: 'Ausentes hoje', desc: 'Só as faltas do dia, prontas para justificar ou cobrir.' },
        { icone: 'clipboard-list', titulo: 'Instruções de posto', desc: 'A ordem de serviço daquele posto — o que o vigilante precisa saber para trabalhar ali.' },
        { icone: 'arrow-left-right', titulo: 'Passagem de turno', desc: 'O que o turno que sai deixa registrado para o turno que entra.' },
        { icone: 'map-pinned', titulo: 'Check-in manual', desc: 'Quando o GPS falha, o supervisor registra a presença com justificativa.' }] },

    // ── Grupo 4 ────────────────────────────────────────────────────────────────
    { t: 'secao', kicker: 'Grupo 4', icone: 'users', titulo: 'Equipe & Ponto',
      texto: 'As pessoas do operacional e o que o relógio diz sobre elas. É aqui que a hora extra é vista enquanto ainda dá para tratar — antes de virar folha.',
      chips: ['Colaboradores', 'Avaliação de equipe', 'Banco de horas', 'Apuração (ponto × escala)', 'Lançar horas', 'Aprovar', 'Compensar'] },

    { t: 'tela', kicker: 'Equipe & Ponto', titulo: 'Apuração: o ponto contra a escala',
      imagem: P + 'op-banco-horas-apuracao.png', legenda: 'Operacional › Equipe & Ponto › Apuração (ponto × escala)',
      notas: [
        { titulo: 'Realizado × Previsto', desc: 'Realizado são os pares entrada→saída reais, com intervalo já descontado. Previsto é o que a escala vigente mandava.' },
        { titulo: 'A coluna Saldo', desc: '+22,0h é sobra sobre o previsto. É candidata a hora extra ou a banco de horas — ainda não é nenhum dos dois.' },
        { titulo: 'Pendências', desc: '«Consistente» é dia fechado. «18 dia(s) c/ batida solta» é entrada sem saída: o par não fechou e a conta daquele dia não vale.' },
        { titulo: 'Não lança nada', desc: 'A própria tela avisa: é cálculo derivado. Para efetivar, use «Lançar horas». Só compara dias COM batida.' }] },

    { t: 'lista', kicker: 'Equipe & Ponto', titulo: 'O ciclo do banco de horas',
      itens: [
        { icone: 'scale', titulo: 'Apuração', desc: 'O sistema calcula sozinho a diferença entre ponto e escala, dia a dia.' },
        { icone: 'plus', titulo: 'Lançar horas', desc: 'Para o que o relógio não pegou: trabalho externo, treinamento, evento.' },
        { icone: 'check-check', titulo: 'Aprovar / Rejeitar', desc: 'Nada entra no banco sem passar por quem tem alçada.' },
        { icone: 'arrow-right-left', titulo: 'Compensar', desc: 'Consome saldo com folga. O saldo consumido some do que iria para a folha.' },
        { icone: 'user-round-check', titulo: 'Avaliação de equipe', desc: 'A ficha de desempenho do colaborador no posto, que alimenta o RH.' },
        { icone: 'id-card', titulo: 'Colaboradores', desc: 'Quem é quem no operacional: posto, função, certificação de vigilante e contato.' }] },

    // ── Grupo 5 ────────────────────────────────────────────────────────────────
    { t: 'secao', kicker: 'Grupo 5', icone: 'calendar-plus', titulo: 'Diaristas',
      texto: 'Quem cobre sem ser do quadro. A diária lançada aqui é a mesma que o financeiro vai pagar — não existe planilha paralela entre as duas pontas.',
      chips: ['Lançar diárias', 'Diaristas', 'Cadastrar diarista', 'Fechamento', 'Cadastro'],
      nota: { icone: 'banknote', texto: 'A diária lançada vira pagamento no grupo «Pessoas & Folha» do Financeiro. Um lançamento, um pagamento.' } },

    { t: 'tela', kicker: 'Diaristas', titulo: 'Lançar a diária de quem cobriu',
      imagem: P + 'op-diarias.png', legenda: 'Operacional › Diaristas › Lançar diárias',
      notas: [
        { titulo: 'O que a diária carrega', desc: 'Data, pessoa, função, posto e valor. A função explica o valor: jardineiro, aux. de serviços gerais e agente de portaria não custam igual.' },
        { titulo: 'O selo Lançado', desc: 'Diária registrada, ainda não paga. Quem paga é o grupo «Pessoas & Folha» do Financeiro — com este mesmo lançamento.' },
        { titulo: 'Diária sobreposta', desc: 'Se a pessoa já está na folha CLT naquele dia, o financeiro acusa. Pagar os dois é erro caro e silencioso.' },
        { titulo: 'Fechamento', desc: 'Consolida o mês por pessoa e gera o recibo — que entra no kit documental do condomínio.' }] },

    // ── Grupo 7 ────────────────────────────────────────────────────────────────
    { t: 'secao', kicker: 'Grupo 7', icone: 'shield', titulo: 'Rondas & Ocorrências',
      texto: 'A prova de que o serviço aconteceu, e o registro de quando alguma coisa saiu do normal. É o que o cliente lê quando pergunta "o que houve ontem à noite?".',
      chips: ['Prestação de contas', 'Rondas', 'Checkpoints', 'Ronda mobile', 'Ocorrências', 'Ocorrência rápida', 'Indicadores'] },

    { t: 'tela', kicker: 'Rondas & Ocorrências', titulo: 'A ronda que aconteceu',
      imagem: P + 'op-rondas.png', legenda: 'Operacional › Rondas & Ocorrências › Rondas',
      notas: [
        { titulo: 'Toda ronda tem código', desc: 'RON-2026-00083. É por ele que a ronda é citada em relatório, em ocorrência e na conversa com o cliente.' },
        { titulo: 'Concluída × Em andamento', desc: 'Em andamento é ronda que começou e não fechou. Se ficar dias assim, alguém esqueceu de encerrar.' },
        { titulo: 'Duração', desc: 'Quanto tempo a ronda levou. «0 min» e «406 min» na mesma lista são os dois extremos que merecem um olhar.' },
        { titulo: 'Documento', desc: 'Abrir e Baixar geram o PDF da ronda. É esse arquivo que vai para o síndico como prestação de contas.' }] },

    { t: 'tela', kicker: 'Rondas & Ocorrências', titulo: 'A ocorrência com rastro',
      imagem: P + 'op-ocorrencias.png', legenda: 'Operacional › Rondas & Ocorrências › Ocorrências',
      notas: [
        { titulo: 'Cada linha é um evento', desc: 'Título, condomínio e o instante em que aconteceu. À direita, a gravidade: leve, em azul; Grave, em vermelho.' },
        { titulo: 'As linhas «TESTE E2E»', desc: 'São registros do próprio controle de qualidade, que roda todo dia contra o sistema no ar. Somem conforme a operação registra as reais.' },
        { titulo: 'Ocorrência rápida', desc: 'A aba ao lado. Para o supervisor registrar do celular em trinta segundos, sem formulário longo.' },
        { titulo: 'Resolver e comentar', desc: 'A ocorrência só fecha com desfecho escrito, e o histórico de comentários fica junto — nada é sobrescrito.' }] },

    { t: 'passos', kicker: 'Do susto ao arquivo', icone: 'siren', titulo: 'O ciclo de uma ocorrência',
      passos: [
        { icone: 'circle-plus', titulo: 'Registrar', desc: 'Ocorrência rápida, do celular, no momento em que acontece. Foto entra aqui.' },
        { icone: 'flag', titulo: 'Classificar', desc: 'Gravidade e tipo. É a classificação que decide quem é avisado.' },
        { icone: 'message-square', titulo: 'Acompanhar', desc: 'Comentários vão sendo somados. Nada é sobrescrito, tudo fica.' },
        { icone: 'circle-check', titulo: 'Resolver', desc: 'Com desfecho escrito. Sem texto, o sistema não deixa fechar.' },
        { icone: 'chart-line', titulo: 'Virar número', desc: 'Entra nos indicadores do posto e no relatório que o cliente recebe.', destaque: true }] },

    { t: 'tela', kicker: 'Comunicação', titulo: 'Falar com a equipe inteira',
      imagem: P + 'op-comunicados.png', legenda: 'Operacional › Comunicação › Comunicados',
      notas: [
        { titulo: 'Tipo e Prioridade', desc: 'Informativo, convocação, operacional, segurança — e Normal, Alta ou Urgente. Juntos decidem o destaque no portal.' },
        { titulo: 'Destinatários', desc: '44 é a quantidade de pessoas que recebem aquele comunicado. Não é lista de transmissão: é o portal de cada uma.' },
        { titulo: 'A coluna Views', desc: 'Quantos abriram de fato. É o número mais honesto da tela — e hoje ele mostra que o portal ainda é pouco usado.' },
        { titulo: 'Leituras', desc: 'A aba ao lado abre nome por nome: quem leu e quem não leu. Isso é prova, não suposição.' }] },

    { t: 'cards', kicker: 'Novidades', titulo: 'O que chegou em setembro de 2026', escuro: true, cols: 4,
      cards: [
        { icone: 'fingerprint', titulo: 'Facial sem internet', desc: 'A batida acontece offline e entra como pendente de conferência. Ao reconectar, o servidor reconfere o rosto.' },
        { icone: 'file-check', titulo: 'AFD da Portaria 671', desc: 'O arquivo fiscal do ponto sai no padrão do MTP, com CRC-16 e numeração contínua por CNPJ.' },
        { icone: 'map-pin-check', titulo: 'Check-in do gerente', desc: 'Chegou no posto, saiu do posto — com hora e coordenada, virando entregável de contrato.', destaque: true },
        { icone: 'bot', titulo: 'Consultor IA', desc: 'Pergunte em português. Ele lê o sistema e responde com o dado de hoje, não com um texto pronto.' }] },

    { t: 'tabela', kicker: 'Alçada', titulo: 'Quem pode fazer o quê',
      cabecalho: ['Papel', 'Pode fazer', 'Não pode'],
      larguras: [4.6, 7.4, 5.25],
      linhas: [
        ['Gerente de posto', 'Check-in, passagem de turno, ocorrência, ronda', 'Aprovar ou publicar escala'],
        ['Supervisor', 'Gerar e submeter escala, escalar substituto, lançar diária', 'Publicar sem aprovação'],
        ['Coordenação', 'Aprovar e publicar escala, aprovar banco de horas', '—'],
        ['Diretoria', 'Tudo, mais relatórios, KPIs e AI Command', '—']],
      nota: { icone: 'lock', texto: 'A alçada é do sistema, não do combinado: o botão não aparece para quem não pode.' } },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'calendar-x', titulo: 'Deixar a escala em rascunho', desc: 'Rascunho não vale para o ponto. A apuração fica sem régua e o mês inteiro sai torto. Publique.' },
        { icone: 'user-round-x', titulo: 'Escalar quem está de férias', desc: 'O sistema avisa, mas o aviso pode ser ignorado. Férias em curso é impedimento, não sugestão.' },
        { icone: 'copy', titulo: 'Lançar diária de quem está na folha', desc: 'É pagar duas vezes pelo mesmo dia. A tela acusa "diária sobreposta" — leia o aviso.' },
        { icone: 'message-square-x', titulo: 'Resolver ocorrência sem desfecho', desc: 'Ocorrência fechada sem texto não serve de prova para ninguém — nem para o cliente, nem para a defesa.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
