// Abre TODA tela do redesign num navegador de verdade: cada módulo, cada item do menu
// lateral, cada aba dentro dele. Acusa a tela que cai em boundary (de rota ou da própria
// tela) ou que estoura no console.
//
// Origem: 15/09/2026, vídeo errodp.mp4. A Visão geral do Departamento Pessoal ABRIA; quem
// morria era «Ponto & Jornada» — um item de menu. Varrer só os 29 módulos teria dado verde
// no dia do incidente, porque a tela de entrada de cada módulo é painel, não tabela, e o
// estrago estava no que vem depois do primeiro clique.
//
// O detector é provado por autoteste: com SABOTAR=1 ele intercepta o contrato e devolve uma
// forma que o front não conhece. Medido em 15/09 no departamento-pessoal:
//
//     SABOTAR=1 ... 9 de 9 telas acusadas
//     normal ...... 0 de 510 telas
//
// Verde sem o autoteste não vale: rode os dois.
//
//     EMAIL=... SENHA=... SLUGS="departamento-pessoal crm ..." node scripts/qa/e2e_playwright/varrer_telas_e_abas.js
//     EMAIL=... SENHA=... SLUGS="departamento-pessoal" SABOTAR=1 node ...   # prova que enxerga
//
// Exit 1 quando há tela quebrada. Sob demanda: são ~30 min para as 510 telas.
const { chromium } = require('/opt/conecta-pro/frontend/node_modules/playwright');
const BASE = 'https://erp.conectamais.pro';
const SLUGS = (process.env.SLUGS || '').split(/\s+/).filter(Boolean);
const RUIDO = /favicon|net::ERR_|Failed to load resource|ResizeObserver|Download the React DevTools/i;

(async () => {
  const b = await chromium.launch({ args: ['--no-sandbox'] });
  const p = await (await b.newContext({ viewport:{width:1400,height:900}, ignoreHTTPSErrors:true })).newPage();
  await p.goto(`${BASE}/redesign/login`, { waitUntil:'domcontentloaded' });
  await p.fill('input[type=email], input[name=email]', process.env.EMAIL);
  await p.fill('input[type=password], input[name=password]', process.env.SENHA);
  await p.click('button[type=submit]'); await p.waitForTimeout(6000);
  if (p.url().includes('/login')) { console.log('LOGIN FALHOU'); process.exit(2); }

  if (process.env.SABOTAR) {
    // Prova de que este varredor enxerga: devolve, em toda tela de tabela, uma forma que o
    // front não sabe ler. Se a varredura seguir verde com isto ligado, o instrumento é cego.
    await p.route('**/api/v1/redesign/data/**', async (route) => {
      const r = await route.fetch(); const d = await r.json();
      const sabotar = (o) => {
        if (Array.isArray(o)) { o.forEach(sabotar); return; }
        if (!o || typeof o !== 'object') return;
        if (Array.isArray(o.rows)) { o.rows = 'forma-que-o-front-nao-conhece'; o.cols = 42; }
        Object.values(o).forEach(sabotar);
      };
      sabotar(d.screens || {});
      await route.fulfill({ response: r, json: d });
    });
  }

  let quebradas = 0, vistas = 0;
  const erros = [];
  p.on('pageerror', e => erros.push('pageerror: ' + String(e.message).slice(0,180)));
  p.on('console', m => { if (m.type()==='error') erros.push('console: ' + m.text().slice(0,180)); });

  const olhar = async (onde) => {
    vistas++;
    await p.waitForTimeout(2500);
    const boundary = (await p.locator('text=Algo deu errado').count().catch(()=>0))
                   + (await p.locator('text=Esta tela não abriu').count().catch(()=>0));
    const graves = [...new Set(erros.filter(t => !RUIDO.test(t)))];
    erros.length = 0;
    if (boundary || graves.length) {
      quebradas++;
      console.log(`QUEBRADA  ${onde}${boundary ? '  [ALGO DEU ERRADO]' : ''}`);
      graves.slice(0,2).forEach(g => console.log(`            ${g}`));
      // sair do boundary para continuar a varredura
      if (boundary) { await p.goto(`${BASE}/redesign/${onde.split(' > ')[0]}`, { waitUntil:'domcontentloaded' }); await p.waitForTimeout(3000); }
    }
  };

  for (const slug of SLUGS) {
    try {
      await p.goto(`${BASE}/redesign/${slug}`, { waitUntil:'domcontentloaded', timeout:45000 });
    } catch { console.log(`QUEBRADA  ${slug}  [navegacao]`); quebradas++; continue; }
    await olhar(slug);

    // itens do menu lateral
    const menu = await p.locator('nav a, aside a, nav button, aside button').all().catch(()=>[]);
    const rotulos = [];
    for (const m of menu) { const t = (await m.innerText().catch(()=>'')).trim(); if (t && t.length < 40) rotulos.push(t); }
    for (const rot of [...new Set(rotulos)]) {
      if (/minha conta|sair|conta|buscar/i.test(rot)) continue;
      const alvo = p.locator('nav, aside').getByText(rot, { exact:true }).first();
      try { await alvo.click({ timeout:5000 }); } catch { continue; }
      await olhar(`${slug} > ${rot}`);

      // abas dentro do item
      const abas = await p.locator('[role=tab]').all().catch(()=>[]);
      for (let i = 0; i < abas.length && i < 25; i++) {
        const lista = await p.locator('[role=tab]').all().catch(()=>[]);
        if (!lista[i]) break;
        const nome = (await lista[i].innerText().catch(()=>'')).trim().slice(0,30);
        try { await lista[i].click({ timeout:5000 }); } catch { continue; }
        await olhar(`${slug} > ${rot} > ${nome}`);
      }
    }
  }
  console.log(`\nTOTAL: ${quebradas} tela(s) quebrada(s) de ${vistas} visitada(s)`);
  await b.close();
  process.exit(quebradas ? 1 : 0);
})();
