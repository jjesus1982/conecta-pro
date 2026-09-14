/** Manual de EQUIPAMENTOS & FROTA. 15 telas.
 *  HONESTIDADE NECESSÁRIA: em 13/09/2026 TODAS as telas deste módulo estão vazias
 *  («Nenhum registro ainda»). O manual ensina a usar e diz isso com todas as letras —
 *  um manual que finge dado que não existe ensina a confiar no número errado. */
'use strict';
const P = '/opt/conecta-pro/uploads/manual_prints/';

module.exports = {
  arquivo: 'Manual_12_Equipamentos_e_Frota',
  titulo: 'Manual de Equipamentos & Frota — Conecta PRO',
  telas: [
    { t: 'capa', kicker: 'Manual do sistema · Módulo 12', titulo: 'Equipamentos',
      destaque: 'e Frota',
      sub: 'Patrimônio, comodatos, manutenção, veículos e a avaliação do cliente por ambiente — o módulo está pronto e esperando o primeiro lançamento.',
      meta: [{ label: 'Versão', valor: 'Setembro de 2026' }, { label: 'Estado', valor: 'Pronto, sem dado lançado' }] },

    { t: 'secao', kicker: 'Leia isto primeiro', icone: 'info', titulo: 'O módulo está pronto e está vazio',
      texto: 'Em 13 de setembro de 2026, todas as quinze telas deste módulo respondem «Nenhum registro ainda — os dados aparecem aqui assim que houver lançamentos». Não é falha: é um módulo construído esperando o cadastro começar. Este manual mostra as telas como elas são hoje e explica o que cada uma vai fazer quando o primeiro equipamento entrar.',
      chips: ['Patrimônio', 'Comodatos', 'Manutenções', 'Frota · Painel', 'Abastecimentos', 'Vistorias', 'Avaliação · Painel', 'Ambientes', 'Links'],
      nota: { icone: 'triangle-alert', texto: 'Enquanto não houver cadastro, nenhum relatório deste módulo vale como informação. Tela vazia não é tela errada — mas também não é resposta.' } },

    { t: 'tela', kicker: 'Patrimônio', titulo: 'O que a tela promete',
      imagem: P + 'eq-patrimonio.png', legenda: 'Equipamentos & Patrimônio › Patrimônio',
      notas: [
        { titulo: 'As colunas dizem o cadastro', desc: 'Código, equipamento, tipo, serial, status e cliente. É o mínimo para rastrear um bem.' },
        { titulo: 'Serial é o que importa', desc: 'É o número que identifica a câmera, o rádio ou o detector específico — não o modelo.' },
        { titulo: 'A coluna Cliente', desc: 'Em qual condomínio o bem está instalado. É o que transforma inventário em responsabilidade.' },
        { titulo: 'A frase que aparece hoje', desc: '«Nenhum registro ainda — os dados aparecem aqui assim que houver lançamentos.» É literal.' }] },

    { t: 'tela', kicker: 'Frota', titulo: 'O painel de veículos e a lógica do «restam»',
      imagem: P + 'eq-frota-painel.png', legenda: 'Equipamentos & Patrimônio › Frota — painel',
      notas: [
        { titulo: 'Leia o subtítulo', desc: '«KM atual e ‹Restam› até a próxima troca (só com leitura nos últimos 30 dias)». Sem leitura recente, a conta não é feita.' },
        { titulo: 'Óleo, pneu e correia', desc: 'Cada um tem o seu «restam», em quilômetros. É manutenção preventiva por uso, não por calendário.' },
        { titulo: 'O que alimenta', desc: 'A aba «KM / abastecimento» é onde o motorista lança a leitura. Sem ela, o painel fica cego.' },
        { titulo: 'Vistorias chegada × saída', desc: 'A aba vizinha compara o estado do veículo ao sair e ao voltar — é o que resolve discussão de avaria.' }] },

    { t: 'cards', kicker: 'As três frentes', titulo: 'O que o módulo cobre', cols: 3,
      cards: [
        { icone: 'package', titulo: 'Patrimônio e comodato', desc: 'O bem que é nosso e está instalado no cliente. O comodato é o contrato que formaliza isso — e o que garante a devolução se a relação acabar.', cor: 'F26A21' },
        { icone: 'car', titulo: 'Frota', desc: 'Veículo, leitura de quilometragem, abastecimento, vistoria de chegada e saída, e a manutenção preventiva calculada por uso.', cor: '38BDF8' },
        { icone: 'star', titulo: 'Avaliação por ambiente', desc: 'Link compartilhável por ambiente do condomínio: o morador avalia o serviço onde ele acontece, não a empresa em abstrato.', cor: '17297B' }]},

    { t: 'passos', kicker: 'Para ligar o módulo', icone: 'play', titulo: 'Os cinco primeiros passos',
      passos: [
        { icone: 'clipboard-list', titulo: 'Levantar o que existe', desc: 'Câmeras, rádios, controladoras, nobreaks — com serial e o condomínio onde estão.' },
        { icone: 'plus', titulo: 'Cadastrar o patrimônio', desc: 'Um bem por linha. O serial é o que impede duas fichas para o mesmo equipamento.' },
        { icone: 'file-signature', titulo: 'Formalizar os comodatos', desc: 'O contrato que diz que o bem é nosso e está lá — o documento que sustenta a retirada.' },
        { icone: 'car', titulo: 'Cadastrar os veículos', desc: 'Placa, modelo e a leitura de KM inicial. Sem a primeira leitura, o «restam» não começa a contar.' },
        { icone: 'link', titulo: 'Criar os links de avaliação', desc: 'Um por ambiente. É o canal mais barato de descobrir insatisfação antes da renovação.', destaque: true }] },

    { t: 'cardsLargos', kicker: 'Cuidado aqui', titulo: 'O que já se sabe que vai dar errado',
      cards: [
        { icone: 'copy', titulo: 'Cadastrar sem serial', desc: 'Dois bens iguais sem serial viram um só na prática. Quando um sumir, ninguém vai saber qual.' },
        { icone: 'car-front', titulo: 'Parar de lançar a leitura de KM', desc: 'O painel só calcula com leitura dos últimos 30 dias. Sem lançamento, a manutenção preventiva vira corretiva.' },
        { icone: 'file-x', titulo: 'Instalar sem comodato', desc: 'Equipamento nosso instalado sem contrato é equipamento difícil de recuperar quando o contrato acaba.' },
        { icone: 'eye-off', titulo: 'Deixar o módulo vazio e confiar nele', desc: 'Enquanto não houver cadastro, qualquer número daqui é zero — e zero não é a mesma coisa que «não temos».' }] },

    { t: 'contato', kicker: 'Vamos ligar este módulo?', titulo: 'Ele está pronto. Falta o cadastro.',
      frase: 'Inteligência que zela pela sua segurança.',
      assinatura: { nome: 'Jordan Jesus', cargo: 'Diretor Executivo · CONECTAMAIS ELETRÔNICA LTDA' } },
  ],
};
