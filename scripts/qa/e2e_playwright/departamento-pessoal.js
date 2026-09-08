async (page) => {
  const MOD = "departamento-pessoal"; const TABS = [["g-visao", "visao"], ["g-visao", "funcionarios"], ["g-visao", "contratos"], ["g-visao", "headcount"], ["g-visao", "cadastro-incompleto"], ["g-visao", "sem-escala"], ["g-visao", "cct-conformidade"], ["g-visao", "importar-cadastro"], ["g-admissao", "admissao"], ["g-admissao", "nova-admissao"], ["g-admissao", "prestadores-pj"], ["g-admissao", "novo-prestador-pj"], ["g-admissao", "documentos"], ["g-admissao", "nova-documento"], ["g-admissao", "certificacao"], ["g-admissao", "nova-certificacao"], ["g-admissao", "gerar-certificacoes"], ["g-admissao", "certificacoes-gerar-folha"], ["g-admissao", "prestadores-pj-links-empresa"], ["g-ponto", "ponto"], ["g-ponto", "fechamento-ponto"], ["g-ponto", "fechar-mes-ponto"], ["g-ponto", "espelho-fechar"], ["g-ponto", "ponto-lancar"], ["g-ponto", "ponto-ajuste"], ["g-ponto", "espelho-solicitar-homologacao"], ["g-folha", "folha"], ["g-folha", "folha-gerar"], ["g-folha", "folha-por-condominio"], ["g-folha", "pareamento-folha"], ["g-folha", "folha-rubricas"], ["g-folha", "folha-nao-conformidades"], ["g-folha", "folha-apontamento"], ["g-folha", "contracheques-lote"], ["g-folha", "chaves-pix"], ["g-folha", "cadastrar-pix-key"], ["g-folha", "pagar-folha-preview"], ["g-folha", "pagar-folha-status"], ["g-ferias", "ferias"], ["g-ferias", "solicitar-ferias"], ["g-ferias", "saldo-ferias"], ["g-ferias", "calcular-ferias"], ["g-ferias", "aviso-ferias"], ["g-ferias", "sync-ferias-solides"], ["g-ferias", "licencas"], ["g-ferias", "nova-licenca"], ["g-beneficios", "beneficios"], ["g-beneficios", "nova-beneficio"], ["g-beneficios", "beneficios-cct"], ["g-beneficios", "novo-beneficio-cct"], ["g-beneficios", "registrar-reembolso"], ["g-saude", "renovar-aso"], ["g-saude", "esocial"], ["g-saude", "esocial-eventos"], ["g-saude", "sincronizar-esocial"], ["g-desligamento", "aviso-previo"], ["g-desligamento", "rescisao"], ["g-desligamento", "nova-rescisao"], ["g-desligamento", "calcular-rescisao"]];
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