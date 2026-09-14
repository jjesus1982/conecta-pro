#!/usr/bin/env node
/**
 * aparar.js — corta o vazio do rodapé dos prints.
 *
 * A tela do redesign quase sempre termina bem antes do fim da janela de 1600x1000. Esse
 * vazio entra no slide como altura, e como a caixa do slide é limitada em ALTURA, é ele que
 * espreme a parte útil do print. Cortando, a mesma tela aparece maior sem mudar nada nela.
 *
 * Como acha o fim: compara cada linha de pixels com a última linha da imagem. Enquanto
 * forem iguais (a mesma faixa de sidebar escura + fundo claro), é vazio. A primeira linha
 * diferente, de baixo para cima, é onde o conteúdo acaba.
 *
 * Guarda-corpo: nunca corta abaixo de 46% da altura original nem deixa a imagem mais
 * estreita que 2,6:1 — print exageradamente achatado fica ilegível no PDF.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');

const DIR = process.argv[2] || '/opt/conecta-pro/uploads/manual_prints';
const TOLERANCIA = 6;       // diferença de canal que ainda conta como "mesma cor"
const MARGEM = 28;          // respiro abaixo do último conteúdo
const MIN_FRACAO = 0.46;
const MAX_RAZAO = 2.6;

async function aparar(arq) {
  const img = sharp(arq);
  const { width, height } = await img.metadata();
  const { data, info } = await img.raw().toBuffer({ resolveWithObject: true });
  const canais = info.channels;
  // Compara só a ÁREA DE CONTEÚDO (16% a 88% da largura). Fora dela moram duas coisas que
  // impediam o corte: a sidebar, que tem o cartão do usuário colado embaixo, e o botão
  // flutuante do chat, no canto inferior direito. Com a linha inteira, 0 de 182 eram cortados.
  const ini = Math.floor(width * 0.16) * canais;
  const fim2 = Math.floor(width * 0.88) * canais;
  const linha = (y) => data.subarray(y * width * canais + ini, y * width * canais + fim2);
  const fundo = linha(height - 1);
  const igual = (a, b) => {
    for (let i = 0; i < a.length; i += canais * 7) {   // amostra 1 pixel a cada 7: basta
      for (let c = 0; c < 3; c++) if (Math.abs(a[i + c] - b[i + c]) > TOLERANCIA) return false;
    }
    return true;
  };
  let fim = height - 1;
  while (fim > 0 && igual(linha(fim), fundo)) fim--;
  let novo = Math.min(height, fim + MARGEM);
  novo = Math.max(novo, Math.round(height * MIN_FRACAO), Math.round(width / MAX_RAZAO));
  if (novo >= height - 4) return null;
  const tmp = arq + '.tmp';
  await sharp(arq).extract({ left: 0, top: 0, width, height: novo }).png().toFile(tmp);
  fs.renameSync(tmp, arq);
  return { de: height, para: novo };
}

(async () => {
  const arqs = fs.readdirSync(DIR).filter((f) => f.endsWith('.png')).sort();
  let cortados = 0;
  for (const f of arqs) {
    try {
      const r = await aparar(path.join(DIR, f));
      if (r) { cortados++; process.stdout.write(`  ${f}: ${r.de} → ${r.para}\n`); }
    } catch (e) { console.error(`  x ${f}: ${e.message}`); }
  }
  console.log(`${cortados}/${arqs.length} prints aparados`);
})();
