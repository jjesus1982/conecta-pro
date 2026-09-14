/** APRESENTAÇÃO institucional do Conecta PRO. Não é manual: é o deck que se mostra.
 *  Todo número aqui foi MEDIDO em 13/09/2026, não lembrado:
 *    1.482 rotas   → contagem de app.routes no container em produção
 *    165 oráculos  → backend/scripts/orq/test_*.py
 *    47 caçadores  → backend/scripts/qa/checar_*.py
 *    29 módulos    → redesign_builders/*.py (sem os helpers com prefixo _)
 *  Sem MRR, sem margem, sem custo: este deck pode ser mostrado fora de casa. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Apresentacao_Conecta_PRO',
  titulo: 'Conecta PRO — Apresentação',
  telas: [
    { t: 'capa', kicker: 'O ERP da Conecta Mais', titulo: 'Conecta',
      destaque: 'PRO',
      sub: 'Um ERP feito por dentro de uma empresa de segurança, para empresas de segurança. Com o compliance brasileiro nascido junto, não adaptado depois.',
      meta: [{ label: 'Apresentado em', valor: '13 de setembro de 2026' }, { label: 'Contato', valor: '0800 880 4414 · conectamais.pro' }] },

    { t: 'secao', kicker: 'Quem fez', icone: 'map-pin', titulo: 'Tecnologia daqui, gente daqui.',
      texto: 'O Conecta PRO não foi comprado nem adaptado. Ele nasceu dentro da operação da Conecta Mais, em Manaus, resolvendo os problemas que a gente tinha — posto descoberto, escala no WhatsApp, folha calculada fora, kit documental montado à mão.',
      chips: ['Manaus/AM', 'Equipe própria', 'Código próprio', 'Operação real como laboratório'],
      nota: { icone: 'lightbulb', texto: 'Cada tela deste sistema existe porque alguém aqui perdeu tempo, dinheiro ou sono sem ela.' } },

    { t: 'selos', kicker: 'O que existe hoje', titulo: 'Um sistema, medido',
      selos: [
        { icone: 'route', valor: '1.482', label: 'rotas de API no ar', cor: 'F26A21' },
        { icone: 'layout-grid', valor: '29', label: 'módulos de negócio', cor: '38BDF8' },
        { icone: 'eye', valor: '165', label: 'oráculos vigiando', cor: '17297B' },
        { icone: 'shield-check', valor: '47', label: 'caçadores de defeito', destaque: true, cor: 'F26A21' }],
      sub: 'Números contados no sistema em produção no dia desta apresentação — não estimados.' },

    { t: 'cardsLargos', kicker: 'O ponto de partida', titulo: 'O que nenhum ERP de prateleira resolvia',
      cards: [
        { icone: 'scale', titulo: 'Compliance brasileiro de verdade', desc: 'eSocial, FGTS Digital, DCTFWeb, EFD-Reinf, SPED e NFS-e no padrão nacional. Os concorrentes exportam apontamento para terceiro calcular; aqui a folha é calculada dentro de casa.' },
        { icone: 'shield', titulo: 'A operação de segurança é diferente', desc: 'Posto descoberto, reserva técnica, escala 12x36, interjornada, reciclagem de vigilante e ronda com checkpoint. Nada disso cabe num ERP genérico.' },
        { icone: 'check-check', titulo: 'Número que se pode conferir', desc: 'Não adianta tela bonita com número errado. Todo dia à meia-noite o sistema se audita sozinho e avisa quando um número começa a mentir.' },
        { icone: 'file-signature', titulo: 'Documento que vale como prova', desc: 'Espelho de ponto na Portaria 671, contrato assinado por ICP-Brasil, ronda com PDF e kit documental por condomínio.' }] },

    { t: 'tela', kicker: 'Operacional', titulo: 'O dia da operação, numa tela',
      imagem: P + 'op-visao-geral.png', legenda: 'Operacional › Visão Geral',
      notas: [
        { titulo: 'Cobertura ao vivo', desc: 'Quais postos estão cobertos agora e quais estão abaixo do que o contrato comprou.' },
        { titulo: 'Ocorrências do dia', desc: 'O que aconteceu nas últimas horas, com gravidade — e o cliente vê o mesmo relato.' },
        { titulo: 'Tudo clicável', desc: 'Cada número abre a lista por trás dele. Não existe indicador sem origem.' },
        { titulo: 'Onze abas de profundidade', desc: 'KPIs, mapa, campo, triagem, relatórios e três assistentes de IA.' }] },

    { t: 'tela', kicker: 'Departamento Pessoal', titulo: 'A folha calculada aqui dentro',
      imagem: P + 'dp-folha.png', legenda: 'Departamento Pessoal › Folha de pagamento',
      notas: [
        { titulo: 'Cálculo próprio', desc: 'Salário base, INSS, FGTS, descontos e líquido são resultado de cálculo — não de importação.' },
        { titulo: 'Conferência em paralelo', desc: 'A aba ao lado compara, pessoa por pessoa, a nossa folha com a do sistema antigo.' },
        { titulo: 'Do ponto ao holerite', desc: 'Ponto fechado vira folha, folha vira contracheque, contracheque vira kit do condomínio.' },
        { titulo: 'Sem redigitação', desc: 'Guias de FGTS e INSS saem desta mesma folha, sem ninguém digitar de novo.' }] },

    { t: 'tela', kicker: 'Fiscal & Contábil', titulo: 'O compliance que não é promessa',
      imagem: P + 'fis-visao-geral.png', legenda: 'Fiscal & Contábil › Painel fiscal',
      notas: [
        { titulo: 'Obrigação com valor', desc: 'eSocial, FGTS/GFIP, DCTFWeb, EFD-Reinf e ISS — cada uma com o valor devido ao lado.' },
        { titulo: 'Certidões monitoradas', desc: 'O sistema conta quantas a empresa precisa manter e avisa qual está por vencer.' },
        { titulo: 'Dois regimes', desc: 'Lucro Real e Simples Nacional convivendo no mesmo sistema, cada um com a sua apuração.' },
        { titulo: 'Robô de emissão', desc: 'A certidão que pode ser emitida sozinha é emitida sozinha, e o PDF vai para o acervo.' }] },

    { t: 'cards', kicker: 'Os módulos', titulo: 'O que o sistema cobre', cols: 4,
      cards: [
        { icone: 'shield', titulo: 'Operacional', desc: 'Postos, escalas, presença, diaristas, rondas e ocorrências.' },
        { icone: 'users', titulo: 'Departamento Pessoal', desc: 'Admissão, ponto, folha, férias, benefícios, eSocial e rescisão.' },
        { icone: 'folder-check', titulo: 'Gestão de Pessoas', desc: 'GED, kits documentais, assinatura, SST e aptidão do vigilante.' },
        { icone: 'wallet', titulo: 'Financeiro', desc: 'Receber, pagar, bancos, conciliação, contabilidade e custo por contrato.' },
        { icone: 'landmark', titulo: 'Fiscal & Contábil', desc: 'NFS-e, guias, certidões, SPED, e-CAC e apuração.' },
        { icone: 'trending-up', titulo: 'Comercial', desc: 'Lead, proposta, contrato e assinatura com validade jurídica.' },
        { icone: 'gavel', titulo: 'Jurídico & Licitações', desc: 'Processos, DET, pareceres, risco trabalhista e disputa pública.' },
        { icone: 'smartphone', titulo: 'Portais', desc: 'O colaborador e o cliente, cada um com o seu, escopados por vínculo.' }] },

    { t: 'passos', kicker: 'O que nos separa', icone: 'sparkles', titulo: 'Cinco coisas que quase ninguém faz',
      passos: [
        { icone: 'calculator', titulo: 'Folha em casa', desc: 'O mercado exporta apontamento para o escritório calcular. Aqui o holerite sai do próprio sistema.' },
        { icone: 'file-check', titulo: 'Portaria 671 completa', desc: 'AFD e AEJ no layout do MTP, com CRC-16 e numeração contínua por estabelecimento.' },
        { icone: 'pen-tool', titulo: 'Assinatura ICP-Brasil', desc: 'Contrato assinado com certificado A1 da empresa vale como título executivo, sem testemunha.' },
        { icone: 'message-circle', titulo: 'Agente no WhatsApp', desc: 'Atende cliente e colaborador, registra ponto por contingência e transfere para a pessoa certa.' },
        { icone: 'eye', titulo: '165 oráculos', desc: 'Todo dia à meia-noite o sistema se audita e avisa quando um número começa a mentir.', destaque: true }] },

    { t: 'secao', kicker: 'A parte difícil de copiar', icone: 'shield-check', titulo: 'Um sistema que desconfia de si mesmo',
      texto: 'A maior parte do software mede se o código roda. O Conecta PRO mede se o número está certo. São 165 oráculos e 47 caçadores rodando todo dia contra o sistema em produção, cada um afirmando uma regra de negócio — e falhando alto quando ela quebra.',
      chips: ['Oráculo afirma a regra', 'Caçador procura o defeito', 'Baseline não deixa a dívida crescer', 'Tudo roda à meia-noite'],
      nota: { icone: 'search', texto: 'Foi assim que se descobriu um balanço que não fechava havia meses, e um painel que mentia havia cinco dias.' } },

    { t: 'cardsLargos', kicker: 'Para quem', titulo: 'Quem ganha com este sistema',
      cards: [
        { icone: 'building-2', titulo: 'A empresa de segurança', desc: 'Uma só ferramenta para operação, pessoal, fiscal e comercial — em vez de quatro sistemas que não se falam e três planilhas que ninguém confere.' },
        { icone: 'user-check', titulo: 'O colaborador', desc: 'Holerite, espelho, férias, escala e documentos na mão, pelo celular. Menos fila no DP, menos dúvida no grupo do WhatsApp.' },
        { icone: 'home', titulo: 'O condomínio', desc: 'Portal com a ronda de ontem, a ocorrência da madrugada, o kit documental do mês e a fatura — sem precisar pedir por WhatsApp.' },
        { icone: 'scale', titulo: 'Quem responde pela empresa', desc: 'Prova documental de cada obrigação: ponto na Portaria 671, ASO válido, EPI entregue, reciclagem em dia e contrato assinado com validade jurídica.' }] },

    { t: 'contato', kicker: 'Próximo passo', titulo: 'Vamos conversar?',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
