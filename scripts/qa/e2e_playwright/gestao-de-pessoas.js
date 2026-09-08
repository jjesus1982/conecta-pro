async (page) => {
  const MOD = "gestao-de-pessoas"; const TABS = [["", "visao"], ["", "ged"], ["", "ponto"], ["", "ponto-espelho"], ["", "saude-exames"], ["", "sst"], ["", "registrar-entrega-epi"], ["", "registrar-justificativa-ponto"], ["", "ged-kits"], ["", "ged-envios"], ["", "ged-assinaturas"], ["", "ponto-banco"], ["", "rh"], ["", "rh-treinamentos"], ["", "rh-cargos"], ["", "saude"], ["", "consultor"], ["", "consultor-gestao"], ["", "consultor-gestao-arquivo"], ["", "carreira-planos"], ["", "treinamento-inscricoes"]];
  const out = []; let cons = []; let fails = [];
  const onCons = m => { if (m.type()==='error') cons.push(m.text().slice(0,160)); };
  const onResp = r => { try { const u=r.url(); if (u.includes('/api/') && r.status()>=400) fails.push(r.status()+' '+u.replace('https://erp.conectamais.pro','').slice(0,120)); } catch(e){} };
  page.on('console', onCons); page.on('response', onResp);
  for (const [gid, tid] of TABS) {
    cons = []; fails = [];
    const url = 'https://erp.conectamais.pro/redesign/' + MOD + (gid ? `?t=${gid}&tab=${tid}` : `?t=${tid}`);
    const t0 = Date.now(); let nav='ok';
    try { await page.goto(url, {waitUntil:'domcontentloaded', timeout: 30000}); } catch(e) { nav='goto:'+String(e).slice(0,80); }
    try { await page.waitForFunction(() => { const m=document.querySelector('main.rd-content')||document.querySelector('main'); return m && m.innerText.length>50 && !document.body.innerText.includes('carregando…'); }, null, {timeout: 20000}); } catch(e) { nav = nav==='ok' ? 'timeout-carregando' : nav; }
    await page.waitForTimeout(600);
    const info = await page.evaluate(() => {
      const m = document.querySelector('main.rd-content') || document.querySelector('main');
      const t = m ? m.innerText : document.body.innerText;
      const login = location.pathname.includes('/login');
      const btns = [...(m||document).querySelectorAll('button')].map(b=>b.innerText.trim()).filter(Boolean).length;
      const erro = /Erro ao|Falha ao|Internal Server|Unexpected|undefined|NaN|\[object Object\]/.test(t);
      return {len: t.length, login, btns, erro, head: t.replace(/\s+/g,' ').slice(0,70)};
    }).catch(e => ({len:0, login:false, btns:0, erro:true, head:'evaluate:'+String(e).slice(0,60)}));
    out.push({gid, tid, nav, ms: Date.now()-t0, ...info, cons: [...new Set(cons)].slice(0,4), fails: [...new Set(fails)].slice(0,4)});
    if (info.login) break;
  }
  page.off('console', onCons); page.off('response', onResp);
  return out.map(o=>[(o.gid?o.gid+'/':'')+o.tid,o.nav,o.ms,o.len,o.btns,o.erro?'ERRO':'',o.cons.join(' ~ '),o.fails.join(' ~ '),o.head.slice(0,70)].join('|')).join('\n');
}