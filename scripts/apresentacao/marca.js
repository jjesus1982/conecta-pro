/**
 * marca.js — o padrão-ouro do slide da Conecta Mais, em código.
 *
 * Cada cor, cada coordenada e cada corpo de fonte aqui foi MEDIDO do slide que o Jordan
 * aprovou e usa (Proposta_Conecta_Mais_-_Parque_dos_Rios_I.pptx, 17 slides, PptxGenJS).
 * Não há valor chutado: o que está aqui saiu de `ppt/slides/slideN.xml` daquele arquivo.
 * Se o padrão da marca mudar, ele muda AQUI e todo deck herda — nunca slide a slide.
 *
 * Regra da casa: material da Conecta Mais nunca sai sem timbrado. Este módulo É o timbrado.
 */
'use strict';
const fs = require('fs');
const path = require('path');
const sharp = require('sharp');
const PptxGenJS = require('pptxgenjs');

// ── Geometria medida (polegadas) ────────────────────────────────────────────────
const W = 20, H = 11.25;      // 18288000 x 10287000 EMU
const MX = 1.38;              // margem esquerda/direita
const CW = 17.25;             // largura útil (1.38 → 18.63)
const Y_REGUA = 10.23;        // filete do rodapé
const Y_RODAPE = 10.47;

// ── Paleta medida ───────────────────────────────────────────────────────────────
const C = {
  navy: '17297B', navyFundo: '0E1533', laranja: 'F26A21', laranjaClaro: 'F5A87A',
  ceu: '38BDF8', ceuForte: '0EA5E9', branco: 'FFFFFF', fundo: 'F2F4F8',
  texto: '4A5670', textoFraco: '8A93A8', linha: 'D5DCE9',
  tintaLaranja: 'FFF1E8', tintaCeu: 'E8F6FE', tintaNavy: 'E9EDFA',
  claroEmEscuro: 'B9C5EC', azulSuave: '9FB0E8', cartaoEscuro: '1B2450',
};
const FONTE = 'Poppins';
const RODAPE = 'CONECTA MAIS · CNPJ 35.710.481/0001-03 · 0800 880 4414 · conectamais.pro';
const DIR_MARCA = path.join(__dirname, 'marca');
const CACHE = path.join(__dirname, '.cache');

// ── Ícones: lucide (o mesmo conjunto do slide modelo), rasterizados ────────────
// PptxGenJS aceita SVG, mas o LibreOffice do host não o rasteriza na conversão p/ PDF —
// o ícone sumiria justamente no formato que o Jordan abre. Por isso vira PNG antes.
const ICONES = path.join(__dirname, 'node_modules', 'lucide-static', 'icons');

async function rasterizarIcone(nome, cor) {
  const arq = path.join(CACHE, `ic_${nome}_${cor}.png`);
  if (fs.existsSync(arq)) return arq;
  // marca/icones/ vence o lucide: é onde moram os glifos que o lucide não tem (ex.: instagram)
  let origem = path.join(DIR_MARCA, 'icones', `${nome}.svg`);
  if (!fs.existsSync(origem)) origem = path.join(ICONES, `${nome}.svg`);
  if (!fs.existsSync(origem)) throw new Error(`ícone inexistente: ${nome}`);
  const svg = fs.readFileSync(origem, 'utf8').replace(/stroke="currentColor"/g, `stroke="#${cor}"`);
  await sharp(Buffer.from(svg), { density: 600 }).resize(256, 256, { fit: 'contain',
    background: { r: 0, g: 0, b: 0, alpha: 0 } }).png().toFile(arq);
  return arq;
}

// Gradientes: o PptxGenJS não escreve gradFill. As duas barras da marca (a vertical
// laranja→navy das telas claras e a horizontal laranja→céu→laranja das escuras) viram PNG.
async function barra(tipo) {
  const arq = path.join(CACHE, `barra_${tipo}.png`);
  if (fs.existsSync(arq)) return arq;
  const larg = tipo === 'vertical' ? 24 : 2400, alt = tipo === 'vertical' ? 2400 : 24;
  const svg = tipo === 'vertical'
    ? `<svg xmlns="http://www.w3.org/2000/svg" width="${larg}" height="${alt}"><defs>
       <linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
       <stop offset="0%" stop-color="#${C.laranja}"/><stop offset="100%" stop-color="#${C.navy}"/>
       </linearGradient></defs><rect width="${larg}" height="${alt}" fill="url(#g)"/></svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" width="${larg}" height="${alt}"><defs>
       <linearGradient id="g" x1="0" y1="0" x2="1" y2="0">
       <stop offset="0%" stop-color="#${C.laranja}"/><stop offset="50%" stop-color="#${C.ceu}"/>
       <stop offset="100%" stop-color="#${C.laranja}"/>
       </linearGradient></defs><rect width="${larg}" height="${alt}" fill="url(#g)"/></svg>`;
  await sharp(Buffer.from(svg)).png().toFile(arq);
  return arq;
}

/** Altura estimada de um bloco de texto (pol). Aproximação boa o bastante para dimensionar
 *  cartão: largura média do glifo da Poppins ~0.52em; entrelinha 1.25 × multiplicador. */
function alturaTexto(txt, largIn, pt, mult = 1.08) {
  const porLinha = Math.max(8, Math.floor((largIn * 72) / (pt * 0.52)));
  const linhas = String(txt || '').split('\n').reduce((a, l) => a + Math.max(1, Math.ceil(l.length / porLinha)), 0);
  return linhas * (pt * 1.25 * mult) / 72;
}

/** Centraliza um bloco de altura `bloco` na faixa livre entre `y0` e o filete do rodapé. */
function centrar(y0, bloco, folgaBaixo = 0.45) {
  const dispon = Y_REGUA - folgaBaixo - y0;
  return y0 + Math.max(0, (dispon - bloco) / 2);
}

// ── Chassi das telas ────────────────────────────────────────────────────────────
function moldura(s, { escuro = false, pagina = null, agua = 'baixo' } = {}) {
  s.background = { color: escuro ? C.navyFundo : C.fundo };
  if (escuro) s.addImage({ path: s._barraH, x: 0, y: 0, w: W, h: 0.1 });
  else s.addImage({ path: s._barraV, x: 0, y: 0, w: 0.15, h: H });
  if (agua) {
    const p = agua === 'alto' ? { x: 14.9, y: -1.6, w: 7.1, h: 7.1 } : { x: 14.9, y: 6.35, w: 7.08, h: 7.08 };
    s.addImage({ path: path.join(DIR_MARCA, 'selo.png'), ...p, transparency: escuro ? 96 : 95 });
  }
  if (pagina !== null) {
    s.addShape('rect', { x: MX, y: Y_REGUA, w: CW, h: 0.012,
      fill: { color: escuro ? '253157' : C.linha } });
    s.addText(RODAPE, { x: MX, y: Y_RODAPE, w: 12, h: 0.35, fontFace: FONTE, fontSize: 15,
      color: escuro ? '5A6894' : C.textoFraco });
    s.addText(String(pagina).padStart(2, '0'), { x: 17.8, y: Y_RODAPE - 0.02, w: 0.83, h: 0.38,
      fontFace: FONTE, fontSize: 16, bold: true, align: 'right',
      color: escuro ? C.claroEmEscuro : C.navy });
  }
}

/** Olho de seção: "CHAPÉU" pequeno em caixa alta + título grande. Com ou sem ícone em bolha. */
function cabeca(s, { kicker, icone, titulo, sub, escuro = false, y = 0.95, corKicker = null, pill = null }) {
  const cork = corKicker || (escuro ? C.laranjaClaro : C.laranja);
  let xk = MX;
  if (icone) {
    s.addShape('ellipse', { x: MX - 0.09, y: y - 0.13, w: 0.5, h: 0.5,
      fill: { color: escuro ? C.laranja : C.ceuForte } });
    s.addImage({ path: s._ic(icone, 'FFFFFF'), x: MX + 0.02, y: y - 0.02, w: 0.28, h: 0.28 });
    xk = MX + 0.66;
  }
  s.addText(kicker.toUpperCase(), { x: xk, y, w: 14, h: 0.42, fontFace: FONTE, fontSize: 18,
    bold: true, color: cork, charSpacing: 2.6 });
  const yT = y + 0.52;
  const largT = pill ? 12.1 : 16.8;
  const fsT = titulo.length > 58 ? 42 : titulo.length > 38 ? 49 : 57;
  // quantas linhas o título realmente ocupa nesta largura — a caixa nasce daí, senão
  // a segunda linha do título come o subtítulo (aconteceu no primeiro teste)
  const linhas = Math.max(1, Math.ceil(titulo.length / Math.floor((largT * 72) / (fsT * 0.52))));
  const altT = linhas * (fsT * 1.02 * 1.25) / 72;
  s.addText(titulo, { x: MX, y: yT, w: largT, h: altT, fontFace: FONTE, fontSize: fsT, bold: true,
    color: escuro ? C.branco : C.navy, valign: 'top', lineSpacingMultiple: 1.02 });
  if (pill) {
    s.addShape('roundRect', { x: 12.7, y: yT + 0.05, w: 5.93, h: 0.86, rectRadius: 0.42,
      fill: { color: escuro ? '1E2A57' : C.navy } });
    s.addImage({ path: s._ic(pill.icone || 'shield-check', 'FFFFFF'), x: 13.06, y: yT + 0.33, w: 0.3, h: 0.3 });
    s.addText(pill.texto, { x: 13.5, y: yT + 0.1, w: 4.95, h: 0.76, fontFace: FONTE, fontSize: 17,
      bold: true, color: C.branco, valign: 'middle' });
  }
  let yFim = yT + altT + 0.12;
  if (sub) {
    s.addText(sub, { x: MX, y: yFim, w: 15.6, h: 0.9, fontFace: FONTE, fontSize: 22,
      color: escuro ? C.claroEmEscuro : C.texto, valign: 'top', lineSpacingMultiple: 1.12 });
    yFim += 0.95;
  }
  return yFim;
}

// ── Os doze tipos de tela ───────────────────────────────────────────────────────
const TELAS = {};

TELAS.capa = (s, d) => {
  s.background = { color: C.navy };
  s.addImage({ path: s._barraH, x: 0, y: 0, w: W, h: 0.1 });
  s.addImage({ path: path.join(DIR_MARCA, 'selo.png'), x: 13.2, y: 0.9, w: 8.4, h: 8.4, transparency: 94 });
  s.addImage({ path: path.join(DIR_MARCA, 'selo.png'), x: MX, y: 1.31, w: 1.54, h: 1.54 });
  s.addText((d.kicker || '').toUpperCase(), { x: MX, y: 3.31, w: 14.2, h: 0.45, fontFace: FONTE,
    fontSize: 19, bold: true, color: C.laranjaClaro, charSpacing: 3.2 });
  const partes = [{ text: d.titulo, options: { color: C.branco } }];
  if (d.destaque) partes.push({ text: ' ' + d.destaque, options: { color: C.laranjaClaro } });
  s.addText(partes, { x: MX, y: 3.95, w: 13.3, h: 3.8, fontFace: FONTE,
    fontSize: d.titulo.length > 30 ? 72 : 88, bold: true, valign: 'top', lineSpacingMultiple: 0.98 });
  s.addShape('roundRect', { x: MX, y: 7.95, w: 1.56, h: 0.09, rectRadius: 0.04, fill: { color: C.laranja } });
  if (d.sub) s.addText(d.sub, { x: MX, y: 8.3, w: 13.3, h: 1.0, fontFace: FONTE, fontSize: 25,
    color: 'DCE3F7', valign: 'top', lineSpacingMultiple: 1.1 });
  (d.meta || []).forEach((m, i) => {
    const x = MX + i * 3.86;
    if (i) s.addShape('rect', { x: x - 0.47, y: 9.59, w: 0.014, h: 0.54, fill: { color: '4C5E9E' } });
    s.addText(m.label.toUpperCase(), { x, y: 9.47, w: 3.5, h: 0.37, fontFace: FONTE, fontSize: 15,
      bold: true, color: C.laranjaClaro, charSpacing: 2.2 });
    s.addText(m.valor, { x, y: 9.84, w: 3.7, h: 0.45, fontFace: FONTE, fontSize: 19, bold: true, color: C.branco });
  });
  s.addShape('roundRect', { x: 14.43, y: 9.54, w: 4.19, h: 0.71, rectRadius: 0.35,
    fill: { color: '2A3D8F' }, line: { color: '4C5E9E', width: 1 } });
  s.addImage({ path: s._ic('shield-check', 'FFFFFF'), x: 14.76, y: 9.76, w: 0.27, h: 0.27 });
  s.addText('CNPJ 35.710.481/0001-03', { x: 15.19, y: 9.68, w: 3.42, h: 0.44, fontFace: FONTE,
    fontSize: 16, bold: true, color: C.branco, valign: 'middle' });
};

/** Abertura de capítulo — tela escura, título grande e "pastilhas" com o que vem. */
TELAS.secao = (s, d, n) => {
  moldura(s, { escuro: true, pagina: n, agua: 'baixo' });
  const y = cabeca(s, { ...d, escuro: true, y: 1.6 });
  const nChips = (d.chips || []).length;
  const blocoH = (d.texto ? alturaTexto(d.texto, 13.4, 24, 1.2) + 0.55 : 0)
    + Math.ceil(nChips / 5) * 0.78 + (d.nota ? 1.86 : 0);
  let cy = centrar(y + 0.25, blocoH, 0.6);
  if (d.texto) {
    const h = alturaTexto(d.texto, 13.4, 24, 1.2);
    s.addText(d.texto, { x: MX, y: cy, w: 13.4, h, fontFace: FONTE,
      fontSize: 24, color: C.claroEmEscuro, valign: 'top', lineSpacingMultiple: 1.2 });
    cy += h + 0.55;
  }
  let cx = MX;
  (d.chips || []).forEach((t) => {
    const larg = Math.min(7.2, 0.62 + t.length * 0.188);
    if (cx + larg > 18.6) { cx = MX; cy += 0.78; }
    s.addShape('roundRect', { x: cx, y: cy, w: larg, h: 0.62, rectRadius: 0.31, fill: { color: '25305C' } });
    s.addText(t, { x: cx + 0.28, y: cy, w: larg - 0.5, h: 0.62, fontFace: FONTE, fontSize: 17,
      bold: true, color: C.branco, valign: 'middle' });
    cx += larg + 0.24;
  });
  if (d.nota) {
    s.addShape('roundRect', { x: MX, y: cy + 1.0, w: Math.min(16.4, 1.6 + d.nota.texto.length * 0.163),
      h: 0.86, rectRadius: 0.43, fill: { color: '25305C' } });
    s.addImage({ path: s._ic(d.nota.icone || 'info', C.ceu), x: MX + 0.34, y: cy + 1.27, w: 0.32, h: 0.32 });
    s.addText(d.nota.texto, { x: MX + 0.86, y: cy + 1.0, w: 15.2, h: 0.86, fontFace: FONTE,
      fontSize: 18, bold: true, color: C.branco, valign: 'middle' });
  }
};

/** Selos: os números grandes que abrem o módulo. */
TELAS.selos = (s, d, n) => {
  moldura(s, { pagina: n, agua: 'baixo' });
  const yc = cabeca(s, { ...d, y: 1.15 });
  const q = d.selos.length, larg = (CW - (q - 1) * 0.33) / q;
  const altS = 3.27, y0 = centrar(yc + 0.3, altS);
  d.selos.forEach((sl, i) => {
    const x = MX + i * (larg + 0.33), esc = !!sl.destaque;
    s.addShape('roundRect', { x, y: y0, w: larg, h: altS, rectRadius: 0.1,
      fill: { color: esc ? C.navy : C.branco } });
    s.addShape('rect', { x, y: y0, w: larg, h: 0.06, fill: { color: sl.cor || C.laranja } });
    s.addImage({ path: s._ic(sl.icone, esc ? C.laranja : (sl.cor || C.navy)),
      x: x + larg / 2 - 0.27, y: y0 + 0.52, w: 0.54, h: 0.54 });
    s.addText(sl.valor, { x, y: y0 + 1.2, w: larg, h: 0.85, fontFace: FONTE,
      fontSize: sl.valor.length > 7 ? 34 : 49, bold: true, align: 'center',
      color: esc ? C.branco : C.navy, valign: 'middle' });
    s.addText(sl.label, { x: x + 0.2, y: y0 + 2.13, w: larg - 0.4, h: 0.9, fontFace: FONTE, fontSize: 18,
      align: 'center', color: esc ? C.azulSuave : C.texto, valign: 'top', lineSpacingMultiple: 1.05 });
  });
};

/** Cartões com ícone em bolha — 3 ou 4 por linha, até 8. O cavalo de batalha do deck. */
TELAS.cards = (s, d, n) => {
  const esc = !!d.escuro;
  moldura(s, { escuro: esc, pagina: n, agua: 'baixo' });
  let y = cabeca(s, { ...d, escuro: esc, y: d.sub ? 0.66 : 0.9 });
  const cols = d.cols || (d.cards.length <= 3 ? 3 : 4);
  const linhas = Math.ceil(d.cards.length / cols);
  const larg = (CW - (cols - 1) * 0.38) / cols;
  const ptD = Math.max(...d.cards.map((c) => c.desc.length)) > 130 ? 15 : 17;
  const precisa = 2.22 + Math.max(...d.cards.map((c) => alturaTexto(c.desc, larg - 0.44, ptD))) + 0.28;
  const folga = d.nota ? 1.3 : 0.45;
  const teto = (Y_REGUA - folga - (y + 0.35) - (linhas - 1) * 0.32) / linhas;
  const alt = Math.min(3.6, Math.max(2.9, Math.min(precisa, teto)));
  const y0 = centrar(y + 0.35, linhas * alt + (linhas - 1) * 0.32 + (d.nota ? 1.06 : 0), d.nota ? 0.5 : 0.45);
  d.cards.forEach((c, i) => {
    const col = i % cols, lin = Math.floor(i / cols);
    const x = MX + col * (larg + 0.38), yy = y0 + lin * (alt + 0.32);
    const dest = !!c.destaque;
    s.addShape('roundRect', { x, y: yy, w: larg, h: alt, rectRadius: 0.1,
      fill: { color: dest ? (esc ? '2E1F2E' : C.navy) : (esc ? C.cartaoEscuro : C.branco) },
      line: esc ? { color: dest ? C.laranja : '2A3563', width: 1 } : undefined });
    s.addShape('rect', { x, y: yy, w: larg, h: 0.06, fill: { color: c.cor || (dest ? C.laranja : C.ceu) } });
    const corIc = dest ? C.laranja : (esc ? C.ceu : (c.cor || C.navy));
    s.addShape('ellipse', { x: x + larg / 2 - 0.44, y: yy + 0.4, w: 0.88, h: 0.88,
      fill: { color: esc ? '243055' : (c.cor === C.laranja ? C.tintaLaranja : c.cor === C.navy ? C.tintaNavy : C.tintaCeu) } });
    s.addImage({ path: s._ic(c.icone, corIc), x: x + larg / 2 - 0.22, y: yy + 0.62, w: 0.44, h: 0.44 });
    s.addText(c.titulo, { x: x + 0.15, y: yy + 1.42, w: larg - 0.3, h: 0.8, fontFace: FONTE,
      fontSize: c.titulo.length > 26 ? 18 : 21, bold: true, align: 'center',
      color: dest ? C.branco : (esc ? C.branco : C.navy), valign: 'top', lineSpacingMultiple: 1.02 });
    s.addText(c.desc, { x: x + 0.22, y: yy + 2.22, w: larg - 0.44, h: alt - 2.35, fontFace: FONTE,
      fontSize: c.desc.length > 130 ? 15 : 17, align: 'center',
      color: dest ? C.azulSuave : (esc ? C.claroEmEscuro : C.texto), valign: 'top', lineSpacingMultiple: 1.08 });
  });
  if (d.nota) rodapeNota(s, d.nota, y0 + linhas * (alt + 0.32) - 0.06);
};

/** Cartões largos, ícone à esquerda — 2 por linha. Para explicação que precisa de texto. */
TELAS.cardsLargos = (s, d, n) => {
  moldura(s, { pagina: n, agua: 'alto' });
  const y = cabeca(s, { ...d, y: d.sub ? 0.78 : 1.0 });
  const q = d.cards.length, linhas = Math.ceil(q / 2);
  const larg = 8.45;
  const ptD = Math.max(...d.cards.map((c) => c.desc.length)) > 150 ? 15 : 17;
  const precisa = 1.0 + Math.max(...d.cards.map((c) => alturaTexto(c.desc, larg - 2.1, ptD, 1.1))) + 0.3;
  const folga = d.nota ? 1.35 : 0.5;
  const teto = (Y_REGUA - folga - (y + 0.35) - (linhas - 1) * 0.36) / linhas;
  const alt = Math.min(3.0, Math.max(1.95, Math.min(precisa, teto)));
  const y0 = centrar(y + 0.35, linhas * alt + (linhas - 1) * 0.36 + (d.nota ? 1.06 : 0), d.nota ? 0.5 : 0.5);
  const tintas = [C.tintaLaranja, C.tintaCeu, C.tintaNavy, C.tintaLaranja, C.tintaCeu, C.tintaNavy];
  const cores = [C.laranja, C.ceuForte, C.navy, C.laranja, C.ceuForte, C.navy];
  d.cards.forEach((c, i) => {
    const x = MX + (i % 2) * 8.8, yy = y0 + Math.floor(i / 2) * (alt + 0.36);
    s.addShape('roundRect', { x, y: yy, w: larg, h: alt, rectRadius: 0.1, fill: { color: C.branco } });
    s.addShape('roundRect', { x: x + 0.5, y: yy + 0.44, w: 0.96, h: 0.96, rectRadius: 0.2,
      fill: { color: c.tinta || tintas[i % 6] } });
    s.addImage({ path: s._ic(c.icone, c.cor || cores[i % 6]), x: x + 0.74, y: yy + 0.68, w: 0.48, h: 0.48 });
    s.addText(c.titulo, { x: x + 1.81, y: yy + 0.4, w: larg - 2.1, h: 0.56, fontFace: FONTE,
      fontSize: c.titulo.length > 34 ? 21 : 25, bold: true, color: C.navy, valign: 'middle' });
    s.addText(c.desc, { x: x + 1.81, y: yy + 1.0, w: larg - 2.1, h: alt - 1.2, fontFace: FONTE,
      fontSize: c.desc.length > 150 ? 15 : 17, color: C.texto, valign: 'top', lineSpacingMultiple: 1.1 });
  });
  if (d.nota) rodapeNota(s, d.nota, y0 + linhas * (alt + 0.36) - 0.02);
};

/** Passo a passo numerado — tela escura. Para rotina do dia e do mês. */
TELAS.passos = (s, d, n) => {
  moldura(s, { escuro: true, pagina: n, agua: 'baixo' });
  const y = cabeca(s, { ...d, escuro: true, y: d.sub ? 0.68 : 0.85 });
  const q = d.passos.length, larg = (CW - (q - 1) * 0.22) / q;
  const ptD = Math.max(...d.passos.map((p) => p.desc.length)) > 150 ? 14 : 16;
  const precisa = 2.95 + Math.max(...d.passos.map((p) => alturaTexto(p.desc, larg - 0.56, ptD))) + 0.3;
  const alt = Math.min(5.9, Math.max(3.5, Math.min(precisa, Y_REGUA - 0.6 - (y + 0.5))));
  const y0 = centrar(y + 0.5, alt, 0.6);
  d.passos.forEach((p, i) => {
    const x = MX + i * (larg + 0.22), dest = !!p.destaque;
    s.addShape('roundRect', { x, y: y0, w: larg, h: alt, rectRadius: 0.1,
      fill: { color: dest ? '2E1F2E' : C.cartaoEscuro }, line: { color: dest ? C.laranja : '2A3563', width: 1 } });
    const cxi = x + larg / 2;
    s.addShape('ellipse', { x: cxi - 0.62, y: y0 + 0.47, w: 1.23, h: 1.23,
      fill: { color: dest ? C.laranja : C.navy }, line: { color: C.laranja, width: 1.2 } });
    s.addImage({ path: s._ic(p.icone, 'FFFFFF'), x: cxi - 0.28, y: y0 + 0.81, w: 0.56, h: 0.56 });
    s.addShape('ellipse', { x: cxi + 0.23, y: y0 + 0.4, w: 0.5, h: 0.5, fill: { color: C.laranja } });
    s.addText(String(i + 1).padStart(2, '0'), { x: cxi + 0.23, y: y0 + 0.4, w: 0.5, h: 0.5,
      fontFace: FONTE, fontSize: 15, bold: true, align: 'center', color: C.navyFundo, valign: 'middle' });
    s.addText(p.titulo, { x: x + 0.28, y: y0 + 1.93, w: larg - 0.56, h: 0.95, fontFace: FONTE,
      fontSize: p.titulo.length > 24 ? 18 : 21, bold: true, align: 'center', color: C.branco,
      valign: 'top', lineSpacingMultiple: 1.03 });
    s.addText(p.desc, { x: x + 0.28, y: y0 + 2.95, w: larg - 0.56, h: alt - 3.1, fontFace: FONTE,
      fontSize: p.desc.length > 150 ? 14 : 16, align: 'center', color: C.claroEmEscuro,
      valign: 'top', lineSpacingMultiple: 1.08 });
  });
};

/** Lista em duas colunas com filete lateral — para "cada aba faz isto". */
TELAS.lista = (s, d, n) => {
  moldura(s, { pagina: n, agua: 'alto' });
  const y = cabeca(s, { ...d, y: d.sub ? 0.8 : 1.0 });
  const q = d.itens.length, linhas = Math.ceil(q / 2);
  const larg = 8.45;
  const ptD = Math.max(...d.itens.map((i) => i.desc.length)) > 140 ? 14 : 16;
  const precisa = 0.86 + Math.max(...d.itens.map((i) => alturaTexto(i.desc, larg - 1.85, ptD))) + 0.22;
  const folga = d.nota ? 1.25 : 0.45;
  const teto = (Y_REGUA - folga - (y + 0.32) - (linhas - 1) * 0.22) / linhas;
  const alt = Math.min(2.4, Math.max(1.5, Math.min(precisa, teto)));
  const y0 = centrar(y + 0.32, linhas * alt + (linhas - 1) * 0.22 + (d.nota ? 1.06 : 0), d.nota ? 0.5 : 0.45);
  const cores = [C.laranja, C.ceuForte, C.navy];
  d.itens.forEach((it, i) => {
    const x = MX + (i % 2) * 8.8, yy = y0 + Math.floor(i / 2) * (alt + 0.22);
    const cor = it.cor || cores[Math.floor(i / 2) % 3];
    s.addShape('roundRect', { x, y: yy, w: larg, h: alt, rectRadius: 0.08, fill: { color: C.branco } });
    s.addShape('rect', { x, y: yy, w: 0.08, h: alt, fill: { color: cor } });
    s.addShape('ellipse', { x: x + 0.52, y: yy + 0.4, w: 0.79, h: 0.79,
      fill: { color: cor === C.laranja ? C.tintaLaranja : cor === C.navy ? C.tintaNavy : C.tintaCeu } });
    s.addImage({ path: s._ic(it.icone, cor), x: x + 0.72, y: yy + 0.6, w: 0.4, h: 0.4 });
    s.addText(it.titulo, { x: x + 1.58, y: yy + 0.3, w: larg - 1.85, h: 0.52, fontFace: FONTE,
      fontSize: it.titulo.length > 36 ? 19 : 22, bold: true, color: C.navy, valign: 'middle' });
    s.addText(it.desc, { x: x + 1.58, y: yy + 0.86, w: larg - 1.85, h: alt - 1.02, fontFace: FONTE,
      fontSize: it.desc.length > 140 ? 14 : 16, color: C.texto, valign: 'top', lineSpacingMultiple: 1.08 });
  });
  if (d.nota) rodapeNota(s, d.nota, y0 + linhas * (alt + 0.22) - 0.02);
};

/** A TELA DO SISTEMA: print grande à esquerda, leitura anotada à direita. */
TELAS.tela = (s, d, n) => {
  moldura(s, { pagina: n, agua: null });
  const y = cabeca(s, { ...d, y: 0.82 });
  const y0 = y + 0.3;
  const caixaW = d.notas && d.notas.length ? 11.75 : CW;
  const caixaH = Y_REGUA - 0.72 - y0;
  const r = d._ratio || 16 / 9;
  let iw = caixaW, ih = iw / r;
  if (ih > caixaH) { ih = caixaH; iw = ih * r; }
  const ix = d.notas && d.notas.length ? MX : MX + (CW - iw) / 2;
  s.addShape('roundRect', { x: ix - 0.09, y: y0 - 0.09, w: iw + 0.18, h: ih + 0.18, rectRadius: 0.08,
    fill: { color: C.branco }, line: { color: C.linha, width: 1 } });
  s.addImage({ path: d.imagem, x: ix, y: y0, w: iw, h: ih });
  if (d.legenda) s.addText(d.legenda, { x: ix, y: y0 + ih + 0.16, w: iw, h: 0.5, fontFace: FONTE,
    fontSize: 16, italic: true, color: C.textoFraco, align: 'center', valign: 'top' });
  (d.notas || []).forEach((nt, i) => {
    const x = 13.35, alt = Math.min(1.95, (caixaH - (d.notas.length - 1) * 0.2) / d.notas.length);
    const yy = y0 + i * (alt + 0.2);
    s.addShape('roundRect', { x, y: yy, w: 5.28, h: alt, rectRadius: 0.08, fill: { color: C.branco } });
    s.addShape('rect', { x, y: yy, w: 0.07, h: alt, fill: { color: i % 2 ? C.ceuForte : C.laranja } });
    s.addShape('ellipse', { x: x + 0.36, y: yy + 0.3, w: 0.46, h: 0.46,
      fill: { color: i % 2 ? C.tintaCeu : C.tintaLaranja } });
    s.addText(String(i + 1), { x: x + 0.36, y: yy + 0.3, w: 0.46, h: 0.46, fontFace: FONTE,
      fontSize: 14, bold: true, align: 'center', color: i % 2 ? C.ceuForte : C.laranja, valign: 'middle' });
    s.addText(nt.titulo, { x: x + 0.95, y: yy + 0.22, w: 4.15, h: 0.62, fontFace: FONTE,
      fontSize: nt.titulo.length > 28 ? 16 : 18, bold: true, color: C.navy, valign: 'middle',
      lineSpacingMultiple: 1.0 });
    s.addText(nt.desc, { x: x + 0.95, y: yy + 0.84, w: 4.15, h: alt - 0.98, fontFace: FONTE,
      fontSize: 14, color: C.texto, valign: 'top', lineSpacingMultiple: 1.06 });
  });
};

/** Tabela — para CCT, prazos, quem-faz-o-quê. */
TELAS.tabela = (s, d, n) => {
  moldura(s, { pagina: n, agua: 'baixo' });
  const y = cabeca(s, { ...d, y: d.sub ? 0.85 : 1.05 });
  const cols = d.cabecalho.length;
  const larguras = d.larguras || Array(cols).fill(CW / cols);
  const altL = Math.min(0.82, (Y_REGUA - (d.nota ? 1.4 : 0.5) - (y + 0.35) - 0.68) / Math.max(1, d.linhas.length));
  const y0 = centrar(y + 0.35, 0.68 + d.linhas.length * altL + (d.nota ? 1.04 : 0));
  s.addShape('roundRect', { x: MX, y: y0, w: CW, h: 0.68, rectRadius: 0.06, fill: { color: C.navy } });
  let x = MX;
  d.cabecalho.forEach((h, i) => {
    s.addText(h.toUpperCase(), { x: x + 0.3, y: y0, w: larguras[i] - 0.4, h: 0.68, fontFace: FONTE,
      fontSize: 15, bold: true, color: C.branco, charSpacing: 1.4, valign: 'middle' });
    x += larguras[i];
  });
  d.linhas.forEach((ln, li) => {
    const yy = y0 + 0.68 + li * altL;
    s.addShape('rect', { x: MX, y: yy, w: CW, h: altL, fill: { color: li % 2 ? 'FFFFFF' : 'EAEEF6' } });
    let xx = MX;
    ln.forEach((cel, ci) => {
      s.addText(String(cel), { x: xx + 0.3, y: yy, w: larguras[ci] - 0.4, h: altL, fontFace: FONTE,
        fontSize: 16, bold: ci === 0, color: ci === 0 ? C.navy : C.texto, valign: 'middle' });
      xx += larguras[ci];
    });
  });
  if (d.nota) rodapeNota(s, d.nota, y0 + 0.68 + d.linhas.length * altL + 0.18);
};

TELAS.contato = (s, d, n) => {
  s.background = { color: C.navyFundo };
  s.addImage({ path: s._barraH, x: 0, y: 0, w: W, h: 0.1 });
  s.addImage({ path: path.join(DIR_MARCA, 'selo.png'), x: -1.9, y: 6.4, w: 7.0, h: 7.0, transparency: 96 });
  s.addText((d.kicker || 'Próximo passo').toUpperCase(), { x: MX, y: 1.9, w: 12, h: 0.45,
    fontFace: FONTE, fontSize: 19, bold: true, color: C.laranjaClaro, charSpacing: 3.2 });
  s.addText(d.titulo, { x: MX, y: 2.5, w: 10.5, h: 2.2, fontFace: FONTE, fontSize: 57, bold: true,
    color: C.branco, valign: 'top', lineSpacingMultiple: 1.02 });
  s.addShape('roundRect', { x: MX, y: 5.2, w: 1.56, h: 0.09, rectRadius: 0.04, fill: { color: C.laranja } });
  if (d.frase) s.addText(d.frase, { x: MX, y: 5.6, w: 10.5, h: 0.9, fontFace: FONTE, fontSize: 24,
    color: C.claroEmEscuro, valign: 'top' });
  if (d.assinatura) {
    s.addText(d.assinatura.nome, { x: MX, y: 6.7, w: 10, h: 0.55, fontFace: FONTE, fontSize: 26,
      bold: true, color: C.branco });
    s.addText(d.assinatura.cargo, { x: MX, y: 7.25, w: 10, h: 0.45, fontFace: FONTE, fontSize: 17,
      color: C.azulSuave });
  }
  const linhas = d.canais || [
    { icone: 'phone', valor: '0800 880 4414', label: 'WhatsApp e ligação gratuita' },
    { icone: 'mail', valor: 'jjesus@conectamais.pro', label: 'E-mail direto' },
    { icone: 'globe', valor: 'www.conectamais.pro', label: 'Site institucional' },
    { icone: 'instagram', valor: '@conectamaisoficial', label: 'Instagram' },
  ];
  const cardH = 2.55 + linhas.length * 1.18;
  s.addShape('roundRect', { x: 12.2, y: 1.9, w: 6.43, h: cardH, rectRadius: 0.1, fill: { color: C.branco } });
  s.addImage({ path: path.join(DIR_MARCA, 'selo.png'), x: 14.7, y: 2.2, w: 1.42, h: 1.42 });
  s.addShape('rect', { x: 12.72, y: 3.95, w: 5.4, h: 0.012, fill: { color: C.linha } });
  linhas.forEach((l, i) => {
    const yy = 4.2 + i * 1.18;
    s.addShape('ellipse', { x: 12.72, y: yy + 0.1, w: 0.56, h: 0.56, fill: { color: C.tintaLaranja } });
    s.addImage({ path: s._ic(l.icone, C.laranja), x: 12.87, y: yy + 0.25, w: 0.27, h: 0.27 });
    s.addText(l.valor, { x: 13.52, y: yy, w: 4.6, h: 0.45, fontFace: FONTE, fontSize: 18, bold: true, color: C.navy });
    s.addText(l.label, { x: 13.52, y: yy + 0.44, w: 4.6, h: 0.4, fontFace: FONTE, fontSize: 14, color: C.textoFraco });
    if (i < linhas.length - 1) s.addShape('rect', { x: 12.72, y: yy + 1.02, w: 5.4, h: 0.012, fill: { color: 'EDF0F6' } });
  });
  s.addShape('rect', { x: MX, y: Y_REGUA, w: CW, h: 0.012, fill: { color: '253157' } });
  s.addText('CONECTA MAIS · CNPJ 35.710.481/0001-03 · Av. Efigênio Salles — Manaus/AM',
    { x: MX, y: Y_RODAPE, w: 13, h: 0.35, fontFace: FONTE, fontSize: 15, color: '5A6894' });
  s.addText(String(n).padStart(2, '0'), { x: 17.8, y: Y_RODAPE - 0.02, w: 0.83, h: 0.38,
    fontFace: FONTE, fontSize: 16, bold: true, align: 'right', color: C.claroEmEscuro });
};

function rodapeNota(s, nota, y) {
  const texto = typeof nota === 'string' ? nota : nota.texto;
  s.addShape('roundRect', { x: MX, y, w: CW, h: 0.86, rectRadius: 0.1, fill: { color: C.navy } });
  s.addImage({ path: s._ic((nota.icone) || 'info', 'FFFFFF'), x: MX + 0.38, y: y + 0.27, w: 0.32, h: 0.32 });
  s.addText(texto, { x: MX + 0.92, y, w: CW - 1.3, h: 0.86, fontFace: FONTE, fontSize: 18,
    color: C.branco, valign: 'middle', lineSpacingMultiple: 1.0 });
}

// ── Montagem ────────────────────────────────────────────────────────────────────
function coletarIcones(telas) {
  const set = new Set();
  const add = (nome, cor) => { if (nome) set.add(`${nome}|${cor}`); };
  for (const t of telas) {
    if (t.icone) { add(t.icone, 'FFFFFF'); }
    if (t.pill) add(t.pill.icone || 'shield-check', 'FFFFFF');
    if (t.nota && t.nota.icone) { add(t.nota.icone, 'FFFFFF'); add(t.nota.icone, C.ceu); }
    for (const c of [...(t.cards || []), ...(t.itens || []), ...(t.selos || [])]) {
      for (const cor of [C.navy, C.ceu, C.ceuForte, C.laranja, 'FFFFFF']) add(c.icone, cor);
    }
    for (const p of (t.passos || [])) add(p.icone, 'FFFFFF');
    for (const l of (t.canais || [])) add(l.icone, C.laranja);
  }
  ['shield-check', 'info', 'phone', 'mail', 'globe', 'instagram'].forEach((i) => {
    add(i, 'FFFFFF'); add(i, C.laranja); add(i, C.ceu);
  });
  return [...set].map((k) => k.split('|'));
}

/**
 * @param {{arquivo:string, titulo?:string, telas:object[]}} deck
 * @returns {Promise<string>} caminho do .pptx
 */
async function gerar(deck, destino) {
  fs.mkdirSync(CACHE, { recursive: true });
  fs.mkdirSync(destino, { recursive: true });
  const [bv, bh] = await Promise.all([barra('vertical'), barra('horizontal')]);
  const mapa = new Map();
  for (const [nome, cor] of coletarIcones(deck.telas)) {
    mapa.set(`${nome}|${cor}`, await rasterizarIcone(nome, cor));
  }
  // proporção real de cada print, para a imagem nunca esticar
  for (const t of deck.telas) {
    if (t.t === 'tela' && t.imagem) {
      const m = await sharp(t.imagem).metadata();
      t._ratio = m.width / m.height;
    }
  }
  const pptx = new PptxGenJS();
  pptx.defineLayout({ name: 'CONECTA', width: W, height: H });
  pptx.layout = 'CONECTA';
  pptx.author = 'Conecta Mais — Segurança e Tecnologia';
  pptx.company = 'CONECTAMAIS ELETRÔNICA LTDA';
  pptx.title = deck.titulo || deck.arquivo;

  deck.telas.forEach((t, i) => {
    const s = pptx.addSlide();
    s._barraV = bv; s._barraH = bh;
    s._ic = (nome, cor) => {
      const k = `${nome}|${cor}`;
      if (!mapa.has(k)) throw new Error(`ícone não pré-renderizado: ${k}`);
      return mapa.get(k);
    };
    const render = TELAS[t.t];
    if (!render) throw new Error(`tipo de tela desconhecido: ${t.t}`);
    render(s, t, i + 1);
  });
  const saida = path.join(destino, `${deck.arquivo}.pptx`);
  await pptx.writeFile({ fileName: saida });
  return saida;
}

module.exports = { gerar, C, FONTE, W, H, MX, CW };
