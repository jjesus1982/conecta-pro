/** Manual do DEPARTAMENTO PESSOAL. 8 grupos, 74 telas (inventário real do redesign).
 *  As notas de cada print descrevem o que está NA TELA — foram escritas olhando o print,
 *  não deduzindo do nome da aba. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_02_Departamento_Pessoal',
  titulo: 'Manual do Departamento Pessoal — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 02', titulo: 'Departamento',
      destaque: 'Pessoal',
      sub: 'Da admissão ao desligamento: ponto, folha, férias, benefícios e eSocial — calculados aqui dentro, não exportados para terceiro calcular.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Para', valor: 'DP e RH' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'route', titulo: 'Oito grupos, na ordem da vida do colaborador',
      texto: 'O menu segue a história de quem trabalha aqui: entra, bate ponto, recebe, tira férias, recebe benefício, faz exame, e um dia sai. Cada etapa é um grupo.',
      chips: ['Visão geral', 'Admissão & Cadastro', 'Ponto & Jornada', 'Folha de pagamento', 'Férias & Afastamentos', 'Benefícios & Reembolsos', 'Saúde & eSocial', 'Desligamento'],
      nota: { icone: 'calculator', texto: 'A folha é calculada aqui. O Conecta PRO não manda apontamento para escritório fechar — ele fecha.' } },

    { t: 'selos', kicker: 'Em números', titulo: 'O que o módulo movimenta',
      selos: [
        { icone: 'users', valor: '65', label: 'colaboradores ativos', cor: 'F26A21' },
        { icone: 'clock', valor: '378', label: 'jornadas na competência', cor: '38BDF8' },
        { icone: 'file-text', valor: '66', label: 'linhas na folha do mês', cor: '17297B' },
        { icone: 'landmark', valor: '232', label: 'eventos do eSocial com XML', destaque: true, cor: 'F26A21' }],
      sub: 'Números lidos do sistema no momento em que este manual foi gerado. Eles mudam todo dia — a leitura é que não muda.' },

    { t: 'cardsLargos', kicker: 'O ponto de partida', titulo: 'O que doía antes',
      cards: [
        { icone: 'file-spreadsheet', titulo: 'A folha vivia fora de casa', desc: 'O apontamento saía daqui e voltava calculado por terceiro, dias depois. Hoje o cálculo acontece dentro do sistema, e a conferência contra o cálculo antigo fica lado a lado na tela.' },
        { icone: 'clock-alert', titulo: 'Batida solta só aparecia no fechamento', desc: 'Entrada sem saída ficava escondida até o dia 30. A coluna Batidas mostra 1/4, 2/4 ou 1/2 no dia em que acontece.' },
        { icone: 'gift', titulo: 'VT e VR eram planilha e fé', desc: 'Ninguém conseguia provar quantos dias a pessoa trabalhou contra quantos recebeu. Agora escala, ponto, folha e portal ficam em quatro colunas na mesma linha.' },
        { icone: 'landmark', titulo: 'eSocial era caixa-preta', desc: 'Não dava para saber o que o governo tinha e o que faltava. O espelho traz evento, tipo, CPF e número do recibo — e diz quanto ainda falta baixar.' }] },

    { t: 'passos', kicker: 'A rotina', icone: 'calendar-check', titulo: 'O mês do DP, em cinco marcos',
      passos: [
        { icone: 'clock', titulo: 'Todo dia: o ponto', desc: 'Olhe Ponto & Jornada. Batida solta corrigida no dia é ajuste; no fim do mês, é acerto de folha.' },
        { icone: 'plane', titulo: 'Até o dia 10: férias', desc: 'Aprovar ou rejeitar o que está pendente, e conferir quem entra em férias no mês seguinte.' },
        { icone: 'gift', titulo: 'Antes do fechamento: benefícios', desc: 'Conferir o paralelo benefício × ponto × portal e calcular a competência.' },
        { icone: 'lock', titulo: 'Fechar o mês do ponto', desc: 'Depois de fechado, o espelho vira a base da folha. Ajuste posterior exige reabrir com registro.' },
        { icone: 'banknote', titulo: 'Gerar e conferir a folha', desc: 'Gerar, conferir contra a Portte, tratar não conformidades e emitir contracheques.', destaque: true }] },

    { t: 'tela', kicker: 'Visão geral', titulo: 'O quadro de pessoal, e o que falta no cadastro',
      imagem: P + 'dp-funcionarios.png', legenda: 'Departamento Pessoal › Visão geral › Funcionários',
      notas: [
        { titulo: 'A coluna Cadastro (eSocial)', desc: 'A estrela da tela. Diz em porcentagem quanto do cadastro exigido pelo eSocial já está preenchido.' },
        { titulo: 'Ela diz o que falta', desc: '«93% · CTPS Número» é um campo faltando. «33% · Estado Civil, Nome da Mãe, RG +7» é admissão que vai travar.' },
        { titulo: 'Verde e vermelho', desc: 'Verde é cadastro que passa. Vermelho é evento que o governo vai rejeitar — e rejeição tem prazo correndo.' },
        { titulo: 'O botão Editar', desc: 'Abre a ficha exatamente nos campos que faltam. Não é preciso procurar.' }] },

    { t: 'lista', kicker: 'Visão geral', titulo: 'As oito abas que abrem o módulo',
      itens: [
        { icone: 'gauge', titulo: 'Resumo', desc: 'O painel do DP: quantos ativos, o que vence e o que está pendente de você.' },
        { icone: 'users', titulo: 'Funcionários', desc: 'Todo mundo, com a completude do cadastro eSocial em porcentagem.' },
        { icone: 'file-text', titulo: 'Contratos', desc: 'O contrato de trabalho de cada um: tipo, jornada e vigência.' },
        { icone: 'chart-column', titulo: 'Headcount', desc: 'O quadro por mês: quem entrou, quem saiu e onde o número está crescendo.' },
        { icone: 'user-round-x', titulo: 'Cadastro incompleto', desc: 'Só quem tem campo faltando. É a fila de trabalho do cadastro.' },
        { icone: 'scale', titulo: 'Conformidade CCT', desc: 'Quem está abaixo do piso ou sem adicional que a convenção manda pagar.' }] },

    { t: 'tela', kicker: 'Admissão & Cadastro', titulo: 'A entrada de quem chega',
      imagem: P + 'dp-admissao.png', legenda: 'Departamento Pessoal › Admissão & Cadastro › Admissões',
      notas: [
        { titulo: 'O processo antes da pessoa', desc: 'A admissão existe como processo antes de existir como funcionário: candidato, CPF, cargo e início previsto.' },
        { titulo: 'A coluna Status', desc: 'Acompanha o processo do início ao fim. Cancelada fica no histórico — não some, e é assim que se explica a vaga depois.' },
        { titulo: 'Onze abas neste grupo', desc: 'Admissão, prestador PJ, documentos, certificações e os links de PJ por empresa.' },
        { titulo: 'Certificações', desc: 'É aqui que entra a reciclagem de vigilante, que tem prazo legal e derruba a aptidão quando vence.' }] },

    // ── Ponto ──────────────────────────────────────────────────────────────────
    { t: 'secao', kicker: 'Grupo 3', icone: 'clock', titulo: 'Ponto & Jornada',
      texto: 'É a base de tudo o que vem depois. Folha, benefício, banco de horas e o arquivo fiscal da Portaria 671 saem todos daqui.',
      chips: ['Ponto', 'Fechamento', 'Fechar mês', 'Espelho: calcular/fechar', 'Lançamento manual', 'Ajustar batida', 'Solicitar homologação'] },

    { t: 'tela', kicker: 'Ponto & Jornada', titulo: 'A jornada de cada dia, pessoa por pessoa',
      imagem: P + 'dp-ponto.png', legenda: 'Departamento Pessoal › Ponto & Jornada › Ponto',
      notas: [
        { titulo: 'A coluna Batidas', desc: 'Lê-se lidas/esperadas. Quem tem intrajornada bate 2× (entrada e saída); os demais batem 4× (entrada, almoço, volta, saída).' },
        { titulo: '1/4 e 1/2 são alarme', desc: 'Significam que o par não fechou. A jornada daquele dia não tem horas trabalhadas calculáveis.' },
        { titulo: 'O seletor Filtrar', desc: 'Troque a competência para ver meses anteriores sem sair da tela.' },
        { titulo: 'O botão Ajustar', desc: 'Corrige a batida com registro de quem corrigiu e por quê. Nada é sobrescrito em silêncio.' }] },

    { t: 'lista', kicker: 'Ponto & Jornada', titulo: 'O caminho do fechamento',
      itens: [
        { icone: 'list', titulo: 'Ponto', desc: 'A jornada diária de todo mundo, com as batidas lidas e as esperadas.' },
        { icone: 'pencil', titulo: 'Ajustar batida', desc: 'Corrigir uma batida específica. Fica registrado quem ajustou.' },
        { icone: 'plus', titulo: 'Lançamento manual', desc: 'Para o dia em que o relógio não pegou nada: atestado, trabalho externo, treinamento.' },
        { icone: 'file-check-2', titulo: 'Espelho: calcular/fechar', desc: 'Gera o espelho de ponto do colaborador no formato da Portaria 671.' },
        { icone: 'signature', titulo: 'Solicitar homologação', desc: 'Manda o espelho para o colaborador conferir e assinar pelo portal.' },
        { icone: 'lock', titulo: 'Fechar mês', desc: 'Trava a competência. Depois disso, a folha pode ser gerada com segurança.' }] },

    { t: 'tela', kicker: 'Ponto & Jornada', titulo: 'O espelho do mês, com as anomalias à mostra',
      imagem: P + 'dp-fechamento-ponto.png', legenda: 'Departamento Pessoal › Ponto & Jornada › Fechamento',
      notas: [
        { titulo: 'Um espelho por pessoa', desc: 'Posto, horas trabalhadas, extras e faltas do mês. A frase do topo diz a competência e quantos espelhos existem.' },
        { titulo: 'A coluna Status', desc: 'Não diz «ok»: diz quantas anomalias aquele espelho tem. «16 anomalia(s)» é um mês que precisa de conversa antes de virar folha.' },
        { titulo: 'O que é anomalia', desc: 'Batida solta, jornada acima do previsto, falta sem justificativa, intervalo que não bate com a escala.' },
        { titulo: 'Documento', desc: 'Abrir e Baixar geram o espelho em PDF — o mesmo que o colaborador assina na homologação.' }] },

    // ── Folha ──────────────────────────────────────────────────────────────────
    { t: 'secao', kicker: 'Grupo 4', icone: 'banknote', titulo: 'Folha de pagamento',
      texto: 'Proventos, encargos e descontos calculados dentro de casa, com doze abas para gerar, conferir, corrigir e pagar.',
      chips: ['Folha', 'Gerar folha', 'Por condomínio', 'Conecta × Portte', 'Rubricas', 'Não conformidades', 'Contracheques em lote', 'Chaves PIX'],
      nota: { icone: 'shield-check', texto: 'A folha nasce em rascunho. Enquanto estiver assim, nada foi pago nem enviado a ninguém.' } },

    { t: 'tela', kicker: 'Folha de pagamento', titulo: 'A folha da competência, linha a linha',
      imagem: P + 'dp-folha.png', legenda: 'Departamento Pessoal › Folha de pagamento › Folha',
      notas: [
        { titulo: 'Escolha a competência', desc: 'O seletor no topo troca o mês. Ao lado dele, quantas linhas aquele mês tem.' },
        { titulo: 'As colunas do cálculo', desc: 'Salário base, INSS, FGTS 8%, descontos e líquido. Cada uma é resultado de cálculo, não de digitação.' },
        { titulo: 'O selo Rascunho', desc: 'Folha ainda não fechada. É o estado em que se confere e se corrige à vontade.' },
        { titulo: 'Os dois botões do topo', desc: 'Folha consolidada (PDF) para conferir, e Export Domínio (TXT) para quem ainda recebe o arquivo pelo caminho antigo.' }] },

    { t: 'tela', kicker: 'Folha de pagamento', titulo: 'Conecta × Portte: a conferência que pega divergência',
      imagem: P + 'dp-pareamento-folha.png', legenda: 'Departamento Pessoal › Folha de pagamento › Conecta × Portte',
      notas: [
        { titulo: 'Duas folhas, lado a lado', desc: 'A coluna Portte é o cálculo de fora. A coluna Conecta é o nosso. É o mês inteiro em paralelo.' },
        { titulo: 'A coluna Δ', desc: 'Verde quer dizer que pagamos igual. Vermelho é divergência a investigar — e é ela que você caça.' },
        { titulo: '«Só Conecta» e «só Portte»', desc: 'Pessoa que aparece de um lado e não do outro. «Só Portte» costuma ser rescisão: o motor do Conecta só calcula quem está ativo.' },
        { titulo: 'Por que existe', desc: 'Enquanto a operação roda em paralelo, esta tela é a prova de que o cálculo próprio bate com o antigo.' }] },

    { t: 'lista', kicker: 'Folha de pagamento', titulo: 'As abas que fecham o mês',
      itens: [
        { icone: 'play', titulo: 'Gerar folha', desc: 'Calcula a competência a partir do ponto fechado e da CCT vigente.' },
        { icone: 'building-2', titulo: 'Por condomínio', desc: 'A mesma folha quebrada por cliente — é o recorte que entra no kit documental.' },
        { icone: 'git-compare', titulo: 'Conecta × Portte', desc: 'O paralelo mês a mês. Δ vermelho é o que precisa de olho humano.' },
        { icone: 'list-checks', titulo: 'Rubricas', desc: 'Cada verba de provento e desconto, com a base legal por trás.' },
        { icone: 'triangle-alert', titulo: 'Não conformidades', desc: 'O que o sistema achou de errado antes de você: piso, adicional faltando, desconto indevido.' },
        { icone: 'files', titulo: 'Contracheques em lote', desc: 'Gera o holerite de todo mundo de uma vez e publica no portal de cada um.' }] },

    // ── Férias ─────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Férias & Afastamentos', titulo: 'Quem pediu, quem já foi aprovado',
      imagem: P + 'dp-ferias.png', legenda: 'Departamento Pessoal › Férias & Afastamentos › Férias',
      notas: [
        { titulo: 'Uma linha por solicitação', desc: 'Colaborador, início, fim, dias e o estado do pedido. A frase do topo diz de onde vem: fonte canônica.' },
        { titulo: 'Os quatro estados', desc: 'Pendente espera você. Aprovada já vale. Rejeitada e Cancelada ficam no histórico — não somem.' },
        { titulo: 'Aprovar e Rejeitar na linha', desc: 'Só aparecem nas pendentes. Nas demais, sobra apenas Ver.' },
        { titulo: 'As abas ao lado', desc: 'Saldo mostra quanto cada um tem a tirar; Calcular (CLT) faz a conta do pagamento; Aviso prévio de férias gera o documento.' }] },

    { t: 'cards', kicker: 'Férias', titulo: 'Quatro coisas que o sistema faz por você', cols: 4,
      cards: [
        { icone: 'calculator', titulo: 'Calcula pela CLT', desc: 'Um terço constitucional, abono pecuniário e a média de variáveis entram sozinhos na conta.' },
        { icone: 'calendar-clock', titulo: 'Avisa o período vencendo', desc: 'Período aquisitivo que passa de doze meses vira alerta — é multa quando vira dobra.' },
        { icone: 'file-signature', titulo: 'Gera o aviso prévio', desc: 'O documento de aviso de férias sai pronto, com os trinta dias de antecedência que a lei pede.' },
        { icone: 'refresh-cw', titulo: 'Sincroniza com o Sólides', desc: 'Enquanto os dois sistemas convivem, a aba mantém as férias iguais dos dois lados.' }] },

    // ── Benefícios ─────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Benefícios & Reembolsos', titulo: 'O paralelo cego do VT e do VR',
      imagem: P + 'dp-beneficio-conferencia.png', legenda: 'Departamento Pessoal › Benefícios & Reembolsos › Benefício × ponto × portal',
      notas: [
        { titulo: 'Quatro fontes na mesma linha', desc: 'O que o motor calculou pela escala e pelo ponto, o que a folha concede hoje, e o que o portal de fato pagou.' },
        { titulo: 'Por que se chama cego', desc: 'Nada daqui vai para a folha. O cálculo novo roda ao lado do antigo até fechar dois meses batendo.' },
        { titulo: 'Os estados em laranja', desc: '«Sem anterior» é mês sem histórico para comparar. «Sem modalidade» é benefício sem regra cadastrada.' },
        { titulo: 'Quem confere', desc: 'A conferência é humana e tem dona: a Pyetra confere no olho até o paralelo fechar.' }] },

    // ── eSocial ────────────────────────────────────────────────────────────────
    { t: 'tela', kicker: 'Saúde & eSocial', titulo: 'O espelho do que o governo tem',
      imagem: P + 'dp-esocial.png', legenda: 'Departamento Pessoal › Saúde & eSocial › eSocial',
      notas: [
        { titulo: 'Evento, tipo e recibo', desc: 'S-2230 é afastamento, S-2299 é desligamento, S-2220 é monitoramento de saúde. O recibo é o número que o governo devolveu.' },
        { titulo: 'A frase do topo', desc: '«232 evento(s) com XML baixado · 155 aguardando download». O espelho não finge estar completo.' },
        { titulo: 'Por que demora', desc: 'O próprio governo bloqueia os dias 1 a 7 e limita dez acessos por dia. O sistema respeita o limite em vez de tomar bloqueio.' },
        { titulo: 'Tipo e data só depois', desc: 'Eles aparecem quando o XML é baixado. Linha sem tipo é evento que ainda está na fila.' }] },

    { t: 'tabela', kicker: 'eSocial', titulo: 'Os eventos que este módulo transmite',
      cabecalho: ['Evento', 'O que é', 'Quando sai'],
      larguras: [3.2, 8.3, 5.75],
      linhas: [
        ['S-2200', 'Admissão do trabalhador', 'Até o dia anterior ao início do trabalho'],
        ['S-2206', 'Alteração de contrato', 'Até o dia 15 do mês seguinte'],
        ['S-2220', 'Monitoramento da saúde (ASO)', 'Até o dia 15 do mês seguinte ao exame'],
        ['S-2230', 'Afastamento temporário', 'Até o dia 15 do mês seguinte'],
        ['S-2299', 'Desligamento', 'Até dez dias da data do desligamento'],
        ['S-1200', 'Remuneração do trabalhador', 'Até o dia 15 do mês seguinte']],
      nota: { icone: 'triangle-alert', texto: 'Prazo perdido no eSocial é multa automática. É por isso que o espelho mostra o que falta, e não só o que já foi.' } },

    { t: 'tela', kicker: 'Desligamento', titulo: 'Quando alguém sai',
      imagem: P + 'dp-rescisao.png', legenda: 'Departamento Pessoal › Desligamento › Rescisões',
      notas: [
        { titulo: 'Voluntária ou involuntária', desc: 'O tipo muda tudo: aviso prévio, multa do FGTS e o direito ao seguro-desemprego.' },
        { titulo: 'Iniciada × Concluída', desc: 'Iniciada ainda aceita ajuste e mostra os botões Calcular verbas e Concluir. Concluída está fechada.' },
        { titulo: 'Valor total', desc: 'O resultado do cálculo das verbas pela CLT — saldo, aviso, férias proporcionais, décimo terceiro e multa.' },
        { titulo: 'Documento', desc: 'O TRCT e o demonstrativo saem prontos, em PDF, pelos botões Abrir e Baixar de cada linha.' }] },

    { t: 'passos', kicker: 'Desligamento', icone: 'door-open', titulo: 'Os cinco passos de uma rescisão',
      passos: [
        { icone: 'file-pen', titulo: 'Aviso prévio', desc: 'Trabalhado ou indenizado. É a data daqui que define o último dia e todo o resto do cálculo.' },
        { icone: 'circle-plus', titulo: 'Nova rescisão', desc: 'Abre o processo com tipo, motivo e último dia. Nasce como Iniciada.' },
        { icone: 'calculator', titulo: 'Calcular verbas', desc: 'O sistema aplica a CLT e a CCT: saldo, férias, décimo terceiro, multa de 40% e descontos.' },
        { icone: 'file-check', titulo: 'Conferir o TRCT', desc: 'O termo sai em PDF. É o documento que o colaborador assina e que o fisco pode pedir.' },
        { icone: 'send', titulo: 'Concluir e transmitir', desc: 'Fecha a rescisão e abre o caminho do S-2299 no eSocial, que tem dez dias de prazo.', destaque: true }] },

    { t: 'cards', kicker: 'Novidades', titulo: 'O que chegou em setembro de 2026', escuro: true, cols: 4,
      cards: [
        { icone: 'file-check', titulo: 'AFD e AEJ da Portaria 671', desc: 'Os arquivos fiscais do ponto no layout do MTP, com CRC-16 e numeração contínua por estabelecimento.' },
        { icone: 'git-compare-arrows', titulo: 'Paralelo cego de benefícios', desc: 'Escala, ponto, folha e portal na mesma linha — sem tocar na folha até fechar dois meses.' },
        { icone: 'landmark', titulo: 'Espelho do eSocial', desc: 'O que o governo tem, com recibo, respeitando o limite diário de acessos em vez de tomar bloqueio.', destaque: true },
        { icone: 'signature', titulo: 'Homologação do espelho', desc: 'O colaborador confere e assina o espelho de ponto pelo próprio portal.' }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'lock-open', titulo: 'Gerar a folha com o mês do ponto aberto', desc: 'A folha sai sobre um ponto que ainda pode mudar. Feche o mês primeiro, sempre.' },
        { icone: 'eye-off', titulo: 'Ignorar Δ vermelho no Conecta × Portte', desc: 'Divergência não some sozinha. Ela vira reclamatória com o nome da empresa no polo passivo.' },
        { icone: 'calendar-x', titulo: 'Deixar período aquisitivo vencer', desc: 'Férias vencidas pagam em dobro. O alerta existe justamente para que isso nunca seja surpresa.' },
        { icone: 'clock-alert', titulo: 'Deixar batida solta acumular', desc: 'Um dia com 1/4 é um dia sem horas calculáveis. Trinta dias assim é uma folha que não fecha.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
