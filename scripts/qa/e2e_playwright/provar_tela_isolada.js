// Reencena o incidente de 15/09/2026 (vídeo errodp.mp4) e prova que ele não derruba mais o
// módulo inteiro. Intercepta o contrato do redesign e devolve, em toda tela de tabela, uma
// forma que o front não sabe ler — a mesma classe do estrago real, em que o backend passou a
// emitir `fieldsRef`/`verDaLinha` e o bundle no ar não conhecia nenhuma das duas.
//
// Medido nos dois lados, com a mesma sabotagem (41 telas do departamento-pessoal):
//
//     antes do conserto ... tela preta «Algo deu errado» · 0 botões no menu lateral
//     depois ............... card «Esta tela não abriu»  · 8 botões no menu lateral
//
// O ponto não é a tela quebrada — é o menu. Sem ele a Pyetra ficou sem como trocar de tela.
//
//     EMAIL=... SENHA=... [SLUG=departamento-pessoal] node scripts/qa/e2e_playwright/provar_tela_isolada.js
//
// Exit 0 quando o erro fica contido (rota de pé e menu navegável). Sob demanda, não no laço
// diário: precisa de navegador e de produção no ar. A causa é vigiada em segundos pelo
// backend/scripts/qa/checar_contrato_front_back.py, esse sim na regressão.
const { chromium } = require('/opt/conecta-pro/frontend/node_modules/playwright');
const BASE = 'https://erp.conectamais.pro';
const SLUG = process.env.SLUG || 'departamento-pessoal';

(async () => {
  const b = await chromium.launch({ args: ['--no-sandbox'] });
  const p = await (await b.newContext({ viewport:{width:1400,height:900}, ignoreHTTPSErrors:true })).newPage();
  await p.goto(`${BASE}/redesign/login`, { waitUntil:'domcontentloaded' });
  await p.fill('input[type=email], input[name=email]', process.env.EMAIL);
  await p.fill('input[type=password], input[name=password]', process.env.SENHA);
  await p.click('button[type=submit]'); await p.waitForTimeout(6000);

  // sabota o contrato: toda tela de tabela perde `rows`/`cells` e ganha lixo no lugar
  let interceptou = 0, sabotadas = 0;
  await p.route(`**/api/v1/redesign/data/${SLUG}*`, async (route) => {
    interceptou++;
    const r = await route.fetch();
    const d = await r.json();
    // As tabelas reais vivem dentro de `tabs`, não na raiz de screens — sabota recursivo.
    const sabotar = (o) => {
      if (Array.isArray(o)) { o.forEach(sabotar); return; }
      if (!o || typeof o !== 'object') return;
      if (Array.isArray(o.rows)) { o.rows = 'forma-que-o-front-nao-conhece'; o.cols = 42; sabotadas++; }
      Object.values(o).forEach(sabotar);
    };
    sabotar(d.screens || {});
    await route.fulfill({ response: r, json: d });
  });

  await p.goto(`${BASE}/redesign/${SLUG}`, { waitUntil:'domcontentloaded' });
  await p.waitForTimeout(8000);
  console.log(`interceptou=${interceptou} telas sabotadas=${sabotadas}`);
  // a Visão geral é painel, não tabela — vai para o item que a Pyetra clicou no vídeo
  try { await p.locator('nav.rd-nav').getByText('Ponto & Jornada', { exact:true }).first().click({ timeout:8000 }); } catch {}
  await p.waitForTimeout(6000);

  const boundaryRota = await p.locator('text=Algo deu errado').count().catch(()=>0);
  const cardTela     = await p.locator('text=Esta tela não abriu').count().catch(()=>0);
  const menuDePe     = await p.locator('nav.rd-nav button').count().catch(()=>0);
  console.log(`tela preta da rota inteira : ${boundaryRota ? 'SIM (ruim)' : 'nao'}`);
  console.log(`card "Esta tela não abriu" : ${cardTela ? 'SIM' : 'nao'}`);
  console.log(`botões do menu lateral     : ${menuDePe}`);
  await p.screenshot({ path:'/tmp/claude-0/-opt-conecta-pro/7fa40ea6-9df3-4bc7-a3b0-f1d493d66283/scratchpad/prova_boundary.png' });
  await b.close();
  // conserto certo = a rota NÃO caiu E o menu continua navegável
  process.exit(!boundaryRota && menuDePe > 0 ? 0 : 1);
})();
