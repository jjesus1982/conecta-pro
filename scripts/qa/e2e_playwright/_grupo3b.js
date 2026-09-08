async (page) => {
  const GRUPO = [["documentos", [["", "gedeon-perguntar-arquivo"], ["", "hermes-classificar"], ["", "ged-agendamento"], ["", "intercorrencias"], ["", "ged-agendamento-pm"], ["", "assinatura-solicitar"], ["", "kits-conferencia"], ["", "kits-assinaturas-pendentes"], ["", "kits-entrega-status"], ["", "kit-entrega-preparar"], ["", "kit-entrega-marcar"], ["", "kit-faturar"], ["", "kit-checklist-evento"], ["", "ged-tipos-documento"], ["", "ged-coleta-automatica"], ["", "ged-coleta-configurar"], ["", "cnd-emitir"], ["", "cnd-upload"], ["", "certidoes-avisar"], ["", "kit-documentos"], ["", "gedeon-panorama"], ["", "gedeon-alinhamento-dp"], ["", "gedeon-funcionarios"], ["", "gedeon-funcionario"], ["", "gedeon-assinaturas-pendentes"], ["", "ged-coleta-historico"], ["", "ged-coleta-executar"]]]];
  const linhas = []; let relogins = 0;
  for (const [MOD, TABS] of GRUPO) {
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

      if (info.login) {
        // sessão caiu (JWT expira): reloga e refaz esta tela uma vez
        try {
          await page.goto('https://erp.conectamais.pro/redesign/login', {waitUntil:'domcontentloaded', timeout: 30000});
          await page.getByRole('textbox', { name: 'voce@empresa.com' }).fill('jjesus@conectamais.pro');
          await page.getByRole('textbox', { name: '••••••••' }).fill('JsJ618908@#%');
          await page.getByRole('button', { name: 'Entrar' }).click();
          await page.waitForURL(u => !String(u).includes('/login'), {timeout: 30000});
          // o token entra no localStorage depois do redirect — sem esperar, a próxima navegação cai no guard
          try { await page.waitForFunction(() => { try { return !!localStorage.getItem('access_token'); } catch (e) { return false; } }, null, {timeout: 15000}); } catch (e) {}
          await page.waitForTimeout(1500);
          relogins++;
          await page.goto(url, {waitUntil:'domcontentloaded', timeout: 30000});
          try { await page.waitForFunction(() => { const m=document.querySelector('main.rd-content')||document.querySelector('main'); return m && m.innerText.length>50 && !document.body.innerText.includes('carregando…'); }, null, {timeout: 20000}); } catch(e) {}
          await page.waitForTimeout(600);
          const info2 = await page.evaluate(() => {
            const m = document.querySelector('main.rd-content') || document.querySelector('main');
            const t = m ? m.innerText : document.body.innerText;
            const btns = [...(m||document).querySelectorAll('button')].map(b=>b.innerText.trim()).filter(Boolean).length;
            const erro = /Erro ao|Falha ao|Internal Server|Unexpected|undefined|NaN|\[object Object\]/.test(t);
            return {len: t.length, login: location.pathname.includes('/login'), btns, erro, head: t.replace(/\s+/g,' ').slice(0,70)};
          }).catch(e => info);
          Object.assign(info, info2); nav = info.login ? 'login-falhou' : 'ok(relogin)';
        } catch (e) { nav = 'relogin:' + String(e).slice(0,60); }
      }
      out.push({gid, tid, nav, ms: Date.now()-t0, ...info, cons: [...new Set(cons)].slice(0,4), fails: [...new Set(fails)].slice(0,4)});
    }
    page.off('console', onCons); page.off('response', onResp);
    linhas.push(...out.map(o=>[MOD,(o.gid?o.gid+'/':'')+o.tid,o.nav,o.ms,o.len,o.btns,o.erro?'ERRO':'',o.cons.join(' ~ '),o.fails.join(' ~ '),o.head.slice(0,70)].join('|')));
  }
  try { await page.evaluate((t) => { try { localStorage.setItem('__e2e', t); } catch (e) {} }, linhas.join('\n')); throw new Error('sem fs'); const fs = null; fs.writeFileSync('/opt/conecta-pro/auditoria/qa/e2e_20260908/grupo3.txt', linhas.join('\n')+'\n'); } catch (e) { /* resultado completo em localStorage.__e2e */ }
  const ruins = linhas.filter(l => /\|(goto:|timeout)|\|ERRO\||\|[45]\d\d /.test(l));
  return `telas=${linhas.length} suspeitas=${ruins.length} relogins=${relogins}\n` + ruins.join('\n');
}
