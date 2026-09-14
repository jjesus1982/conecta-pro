#!/usr/bin/env node
/**
 * gerar.js — monta os manuais e a apresentação, e converte para PDF.
 *
 *   node gerar.js                 # tudo
 *   node gerar.js operacional dp  # só estes
 *
 * O PPTX sai do marca.js (o timbrado da casa em código). O PDF sai do soffice do host:
 * `gerar_apresentacao` com formato='pdf' devolve 500 em produção porque falta LibreOffice
 * na imagem do backend — enquanto não entrar, a conversão acontece aqui.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const { gerar } = require('./marca');

const SAIDA = process.env.SAIDA_MANUAIS || '/opt/conecta-pro/uploads/manuais';
const DECKS = path.join(__dirname, 'decks');

async function main() {
  const pedidos = process.argv.slice(2);
  const arquivos = fs.readdirSync(DECKS).filter((f) => f.endsWith('.js')).sort();
  const alvos = arquivos.filter((f) => !pedidos.length || pedidos.includes(path.basename(f, '.js')));
  if (!alvos.length) { console.error('nenhum deck casou com', pedidos); process.exit(2); }
  let falhas = 0;
  for (const f of alvos) {
    const nome = path.basename(f, '.js');
    try {
      const deck = require(path.join(DECKS, f));
      const faltando = deck.telas.filter((t) => t.t === 'tela' && !fs.existsSync(t.imagem));
      if (faltando.length) {
        // print ausente = slide sem a tela que ele promete explicar. Falha, não improvisa.
        throw new Error(`print ausente: ${faltando.map((t) => path.basename(t.imagem)).join(', ')}`);
      }
      const pptx = await gerar(deck, SAIDA);
      execFileSync('/usr/bin/soffice', ['--headless', '--convert-to', 'pdf', '--outdir', SAIDA, pptx],
        { stdio: 'ignore', timeout: 600000 });
      const pdf = pptx.replace(/\.pptx$/, '.pdf');
      if (!fs.existsSync(pdf)) throw new Error('soffice não produziu o PDF');
      const kb = (n) => Math.round(fs.statSync(n).size / 1024);
      console.log(`OK  ${nome.padEnd(24)} ${String(deck.telas.length).padStart(3)} slides  ` +
        `${String(kb(pdf)).padStart(5)} KB  →  ${path.basename(pdf)}`);
    } catch (e) {
      falhas++;
      console.error(`ERRO ${nome}: ${e.message}`);
    }
  }
  process.exit(falhas ? 1 : 0);
}

main();
