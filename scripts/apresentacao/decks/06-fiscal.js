/** Manual do FISCAL & CONTÁBIL. 33 telas. NFS-e, guias, certidões, DCTFWeb, EFD-Reinf,
 *  SPED, e-CAC e apuração do Lucro Real. Documento INTERNO (traz faturamento e apuração). */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_06_Fiscal_e_Contabil',
  titulo: 'Manual do Fiscal & Contábil — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 06 · uso interno', titulo: 'Fiscal',
      destaque: '& Contábil',
      sub: 'NFS-e, guias, certidões, DCTFWeb, EFD-Reinf, SPED e a apuração do Lucro Real — o compliance brasileiro nativo, sem intermediário.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Circulação', valor: 'Interna — traz faturamento e apuração' }] },

    { t: 'secao', kicker: 'Para começar', icone: 'landmark', titulo: 'O calendário manda, o sistema avisa',
      texto: 'Obrigação fiscal não espera. Cada uma tem prazo próprio, e o atraso é multa automática. O papel deste módulo é fazer o prazo aparecer antes de virar dívida.',
      chips: ['Painel fiscal', 'NFS-e', 'Guias', 'Certidões (CND)', 'DCTFWeb', 'EFD-Reinf', 'SPED', 'e-CAC', 'Lucro Real'],
      nota: { icone: 'triangle-alert', texto: 'Certidão vencida trava licitação, trava contrato novo e trava pagamento de cliente público. É a primeira coisa a olhar.' } },

    { t: 'tela', kicker: 'Painel fiscal', titulo: 'O estado fiscal da empresa, em quatro números',
      imagem: P + 'fis-visao-geral.png', legenda: 'Fiscal & Contábil › Painel fiscal',
      notas: [
        { titulo: 'NFS-e emitidas', desc: 'Quantas notas de serviço a empresa emitiu. Cada uma é uma receita reconhecida e um imposto a recolher.' },
        { titulo: 'Certidões: 57/58', desc: 'O denominador é quantas certidões a empresa precisa manter. O aviso entre parênteses diz quantas já venceram.' },
        { titulo: 'Obrigações em aberto', desc: 'Guias e declarações com prazo correndo. O quadro abaixo abre uma a uma, com o valor de cada.' },
        { titulo: 'O quadro Obrigações', desc: 'eSocial S-1200, FGTS/GFIP, DCTFWeb, EFD-Reinf, ISS Manaus e DARF IRRF, com o valor devido ao lado.' }] },

    { t: 'selos', kicker: 'Em números', titulo: 'O que o módulo controla',
      selos: [
        { icone: 'receipt', valor: '831', label: 'NFS-e no histórico', cor: 'F26A21' },
        { icone: 'shield-check', valor: '58', label: 'certidões monitoradas', cor: '38BDF8' },
        { icone: 'building-2', valor: '2', label: 'CNPJs, regimes diferentes', cor: '17297B' },
        { icone: 'layout-grid', valor: '33', label: 'telas ligadas a dado real', destaque: true, cor: 'F26A21' }],
      sub: 'A Eletrônica está no Lucro Real desde janeiro de 2026; a Patrimonial é Simples Nacional, Anexo III.' },

    { t: 'tela', kicker: 'NFS-e', titulo: 'As notas de serviço emitidas',
      imagem: P + 'fis-nfse.png', legenda: 'Fiscal & Contábil › NFS-e',
      notas: [
        { titulo: 'Leia a frase do topo', desc: 'Ela avisa que esta aba é o ARQUIVO anterior a 2026. As notas atuais estão em «NFS-e emitidas (nacional)».' },
        { titulo: 'Número e tomador', desc: 'O número é sequencial por emitente. O tomador é o condomínio — é ele que aparece no kit documental do mês.' },
        { titulo: 'O selo ok', desc: 'A nota foi aceita pela prefeitura. Nota rejeitada aparece com outro selo e precisa de ação.' },
        { titulo: 'Padrão ABRASF', desc: 'A emissão segue o padrão nacional adotado por Manaus — não é digitação no site da prefeitura.' }] },

    { t: 'tela', kicker: 'Certidões (CND)', titulo: 'A certidão que vence antes de você lembrar',
      imagem: P + 'fis-certidoes.png', legenda: 'Fiscal & Contábil › Certidões (CND)',
      notas: [
        { titulo: 'A coluna Situação é o alarme', desc: '«Vence em 2d», «Vence em 4d», «Vencida». Ordenada do pior para o melhor, sem você pedir.' },
        { titulo: 'Empresa e órgão emissor', desc: 'Prefeitura de Manaus, CEF/FGTS, SEFAZ-AM, TJ-AM, Receita. Cada CNPJ do grupo tem o seu conjunto.' },
        { titulo: 'Abrir e Baixar', desc: 'O PDF da certidão fica guardado. É ele que vai para o cliente, para a licitação e para o kit documental.' },
        { titulo: 'O robô de certidões', desc: 'Boa parte é emitida automaticamente. Quando o órgão exige captcha, a aba «subir PDF emitido manualmente» resolve.' }] },

    { t: 'tela', kicker: 'Guias / Obrigações', titulo: 'A fila do que vence',
      imagem: P + 'fis-guias.png', legenda: 'Fiscal & Contábil › Guias / Obrigações',
      notas: [
        { titulo: 'Uma linha por obrigação e empresa', desc: 'A mesma competência gera obrigações diferentes para a Eletrônica e para a Patrimonial — e as duas aparecem aqui.' },
        { titulo: 'Competência × Vencimento', desc: 'Competência é o mês do fato. Vencimento é quando o dinheiro precisa sair. Nunca são o mesmo dia.' },
        { titulo: 'Pendente é ação', desc: 'Toda linha pendente tem o botão «Dar baixa» ao lado. Baixa dada é obrigação cumprida e registrada.' },
        { titulo: 'Valor R$ 0,00', desc: 'Aparece quando a guia ainda não foi calculada ou o débito é zero na competência. Vale conferir antes de dar baixa.' }] },

    { t: 'tela', kicker: 'DCTFWeb', titulo: 'A série histórica de uma obrigação',
      imagem: P + 'fis-dctfweb.png', legenda: 'Fiscal & Contábil › DCTFWeb',
      notas: [
        { titulo: 'Mês a mês, do ano inteiro', desc: 'Cada competência com valor devido, valor pago, vencimento e o estado. É o histórico que a fiscalização pede.' },
        { titulo: 'Cumprida × Pendente', desc: 'Verde é declaração entregue. A única laranja da lista é a competência corrente — e o prazo dela está correndo.' },
        { titulo: 'Devido e Pago lado a lado', desc: 'Diferença entre os dois é débito em aberto. Iguais e zerados é competência sem movimento.' },
        { titulo: 'Mesmo padrão nas vizinhas', desc: 'EFD-Reinf, Guias FGTS, Guias INSS e eSocial têm telas iguais a esta — muda a obrigação, não a leitura.' }] },

    { t: 'tela', kicker: 'Lucro Real', titulo: 'O resultado, mês a mês',
      imagem: P + 'fis-dre-mensal.png', legenda: 'Fiscal & Contábil › DRE mês a mês — 2026',
      notas: [
        { titulo: 'Receita bruta e resultado do ano', desc: 'Os dois cartões do topo. Verde e vermelho não são decoração: dizem se o ano está somando ou subtraindo.' },
        { titulo: 'Cada linha é um mês', desc: 'Receita, custos, despesas e o resultado daquela competência, tirados do razão real.' },
        { titulo: 'Mês com receita zero', desc: 'É competência ainda não faturada. O resultado dela aparece negativo por aritmética — não por prejuízo operacional.' },
        { titulo: 'Para que serve', desc: 'É a tela que mostra em qual mês o resultado virou, e permite ir atrás do motivo enquanto ele ainda está fresco.' }] },

    { t: 'tela', kicker: 'Parcelamentos', titulo: 'O que a empresa deve ao fisco, parcelado',
      imagem: P + 'fis-parcelamentos.png', legenda: 'Fiscal & Contábil › Parcelamentos e acordos',
      notas: [
        { titulo: 'Órgão e número do acordo', desc: 'PGFN, Receita e SEMEF Manaus, cada um com o número do processo. É por ele que se fala com o órgão.' },
        { titulo: 'A coluna Parcelas', desc: 'Lê-se pagas/total. «0/60» é acordo firmado e ainda não iniciado — e vale conferir se a primeira parcela já venceu.' },
        { titulo: 'Saldo devedor', desc: 'O quanto ainda falta, com acréscimos. É esse o número que entra no planejamento de caixa.' },
        { titulo: 'Por que centralizar', desc: 'Acordo esquecido rompe sozinho, e acordo rompido volta como dívida inteira, com a certidão junto.' }] },

    { t: 'lista', kicker: 'Obrigações', titulo: 'O que sai deste módulo todo mês',
      itens: [
        { icone: 'file-text', titulo: 'DCTFWeb', desc: 'A declaração que confessa o débito previdenciário. Sem ela, não se emite a guia.' },
        { icone: 'file-input', titulo: 'EFD-Reinf', desc: 'Retenções na fonte sobre serviços tomados e prestados. Alimenta a DCTFWeb.' },
        { icone: 'landmark', titulo: 'Guias FGTS e INSS', desc: 'Geradas a partir da folha do próprio sistema — não digitadas de novo.' },
        { icone: 'database', titulo: 'SPED', desc: 'A escrituração fiscal e contábil digital, no layout da Receita.' },
        { icone: 'building', titulo: 'ISS Manaus', desc: 'O imposto sobre serviço da competência, apurado sobre as NFS-e emitidas.' },
        { icone: 'globe', titulo: 'e-CAC', desc: 'Situação fiscal, débitos e parcelamentos lidos direto do portal da Receita.' }] },

    { t: 'tela', kicker: 'Lucro Real', titulo: 'A apuração de IRPJ e CSLL',
      imagem: P + 'fis-apuracao-lucro-real.png', legenda: 'Fiscal & Contábil › Apuração IRPJ/CSLL — Lucro Real 2026',
      notas: [
        { titulo: 'A base é o razão, não a presunção', desc: 'A frase do topo é explícita: receita menos ISS menos despesas dedutíveis, tirado do razão real.' },
        { titulo: 'É consulta, não gera guia', desc: 'A tela calcula e mostra. O recolhimento continua sendo ato deliberado, feito em outro lugar.' },
        { titulo: 'Lucro antes de IRPJ/CSLL negativo', desc: 'Quando o resultado é prejuízo, IRPJ e CSLL devidos ficam em zero — e é isso que a tela mostra.' },
        { titulo: 'Base de cálculo aberta', desc: 'Receita bruta, dedução de ISS, receita líquida, despesa de pessoal, encargos e custo de material, linha a linha.' }] },

    { t: 'cards', kicker: 'Os dois CNPJs', titulo: 'Regimes diferentes, tratamento diferente', cols: 2,
      cards: [
        { icone: 'building-2', titulo: 'Conecta Mais Eletrônica — Lucro Real', desc: 'Desde janeiro de 2026. Apuração pelo razão real, IRPJ e CSLL sobre o lucro efetivo, PIS e COFINS não cumulativos. É o regime que exige contabilidade de verdade — e é por isso que o Balanço Patrimonial existe no módulo Financeiro.', cor: 'F26A21' },
        { icone: 'building', titulo: 'Conecta Mais Patrimonial — Simples, Anexo III', desc: 'DAS único, sem patronal. A aba «DAS Patrimonial (Simples)» calcula o devido e a aba «Limite do Simples» avisa quando o faturamento se aproxima do teto — porque estourar o limite muda o regime no meio do ano.', cor: '38BDF8' }],
      nota: { icone: 'git-compare', texto: 'A aba «Comparar regimes» simula Simples contra Lucro Real com o faturamento real — útil antes de cada virada de ano.' } },

    { t: 'passos', kicker: 'A rotina', icone: 'calendar-check', titulo: 'O mês fiscal, na ordem',
      passos: [
        { icone: 'receipt', titulo: 'Emitir as NFS-e', desc: 'Depois do faturamento do mês, as notas saem no padrão nacional.' },
        { icone: 'calculator', titulo: 'Apurar', desc: 'ISS sobre o serviço, retenções na fonte e o resultado do razão.' },
        { icone: 'file-input', titulo: 'Transmitir EFD-Reinf', desc: 'As retenções vão primeiro. A DCTFWeb depende delas.' },
        { icone: 'file-text', titulo: 'Fechar a DCTFWeb', desc: 'Confessa o débito e libera a emissão da guia previdenciária.' },
        { icone: 'shield-check', titulo: 'Renovar certidão', desc: 'A lista ordena por quem vence antes. Renovar cedo é mais barato que destravar depois.', destaque: true }] },

    { t: 'cards', kicker: 'Novidades', titulo: 'O que chegou em setembro de 2026', escuro: true, cols: 4,
      cards: [
        { icone: 'file-check', titulo: 'NFS-e nacional (DPS)', desc: 'Emissão pelo padrão nacional, com a Declaração de Prestação de Serviço.' },
        { icone: 'bot', titulo: 'Robô de certidões', desc: 'Emite a CND automaticamente onde o órgão permite, e guarda o PDF no lugar certo.', cor: '38BDF8' },
        { icone: 'handshake', titulo: 'Parcelamentos e acordos', desc: 'O que está parcelado, quanto falta e quando vence cada parcela.', destaque: true },
        { icone: 'scale', titulo: 'Comparar regimes', desc: 'Simples contra Lucro Real sobre o faturamento real, antes da virada do ano.' }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'Os quatro erros que mais custam',
      cards: [
        { icone: 'calendar-x', titulo: 'Deixar certidão vencer', desc: 'Certidão vencida trava licitação, contrato novo e pagamento de cliente público. A coluna Situação existe para isso não acontecer.' },
        { icone: 'arrow-down-up', titulo: 'Transmitir na ordem errada', desc: 'EFD-Reinf vem antes da DCTFWeb. Invertido, a declaração fecha com valor errado.' },
        { icone: 'trending-up', titulo: 'Ignorar o limite do Simples', desc: 'Estourar o teto muda o regime no meio do ano, com efeito retroativo. A aba avisa antes.' },
        { icone: 'eye-off', titulo: 'Confiar no arquivo antigo', desc: 'A aba NFS-e mostra o histórico anterior a 2026. As notas atuais estão em «NFS-e emitidas (nacional)» — conferir a aba errada dá número errado.' }] },

    { t: 'contato', kicker: 'Dúvida no meio do caminho?', titulo: 'Estamos do lado de cá.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
