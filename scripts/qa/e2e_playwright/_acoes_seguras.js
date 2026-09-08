async (page) => {
  // Ações SEGURAS como usuário final: (a) abrir a 1ª ação/edição por linha e cancelar; (b) enviar formulários de
  // CONSULTA (GET/simulação, sem efeito) que já vêm preenchidos. NUNCA: dinheiro, governo, WhatsApp, e-mail, apagar.
  const ABRIR = [ // módulo, tab, rótulo do botão por linha (regex)
    ["crm", "leads", /^Status$/], ["crm", "clientes", /^Editar$/], ["operacional", "g-diaristas&tab=diaristas-cadastro", /^Editar$/],
    ["rh", "cct-cargos", /^Editar$/], ["configuracoes", "usuarios", /^Permiss/], ["fiscal", "certidoes-cnd", /Avisar|Ver|Baixar/],
    ["saude-ocupacional", "cat-transmitir", /^Transmitir$/], ["documentos", "kits", /^Solicitar assinaturas$/],
    ["empresas", "liminares", /Suspensa|Cassada|A solicitar/], ["integracoes", "inter-categorizacao", /^Corrigir$/],
  ];
  const CONSULTAR = [ // formulários GET/simulação com valores já preenchidos
    ["financeiro", "g-visao&tab=fluxo-resumo"], ["financeiro", "g-visao&tab=fluxo-tendencia"], ["financeiro", "g-contabil&tab=dre-consolidado"],
    ["integracoes", "inter-categorias-stats"], ["integracoes", "onvio-status"], ["crm", "jose-luis-dashboard"],
    ["documentos", "gedeon-panorama"], ["juridico", "det-robo-status"], ["departamento-pessoal", "g-folha&tab=pagar-folha-preview"],
    ["departamento-pessoal", "g-folha&tab=pagar-folha-status"], ["portal-do-funcionario", "calculadora-rescisao"],
  ];
  const out = []; let fails = [];
  const onResp = r => { try { const u=r.url(); if (u.includes('/api/') && r.status()>=400) fails.push(r.status()+' '+u.replace('https://erp.conectamais.pro','').slice(0,100)); } catch(e){} };
  page.on('response', onResp);
  const abrir = async (mod, tab) => {
    await page.goto('https://erp.conectamais.pro/redesign/' + mod + '?t=' + tab, {waitUntil:'domcontentloaded', timeout: 30000});
    try { await page.waitForFunction(() => { const m=document.querySelector('main.rd-content')||document.querySelector('main'); return m && m.innerText.length>50 && !document.body.innerText.includes('carregando…'); }, null, {timeout: 20000}); } catch(e) {}
    await page.waitForTimeout(500);
  };
  for (const [mod, tab, rx] of ABRIR) {
    fails = []; let r = 'sem-botao';
    try {
      await abrir(mod, tab);
      const btn = page.locator('main button').filter({ hasText: rx }).first();
      if (await btn.count()) {
        const antes = await page.evaluate(() => document.body.innerText.length);
        await btn.click(); await page.waitForTimeout(800);
        const dlg = await page.evaluate(() => { const d = document.querySelector('[role=dialog], .rd-modal, .rd-drawer, form'); const inputs = document.querySelectorAll('input, select, textarea').length; return {tem: !!d, inputs, len: document.body.innerText.length}; });
        r = `modal=${dlg.tem} inputs=${dlg.inputs} delta=${dlg.len - antes}`;
        await page.keyboard.press('Escape'); await page.waitForTimeout(300);
        const cancel = page.locator('button').filter({ hasText: /^(Cancelar|Fechar|Voltar)$/ }).first();
        if (await cancel.count()) { try { await cancel.click({timeout: 2000}); } catch (e) {} }
      }
    } catch (e) { r = 'erro:' + String(e).slice(0,80); }
    out.push(['ABRIR', mod, tab, r, fails.join(' ~ ')].join('|'));
  }
  for (const [mod, tab] of CONSULTAR) {
    fails = []; let r = '';
    try {
      await abrir(mod, tab);
      const btn = page.locator('main button').filter({ hasText: /^(Consultar|Simular)$/ }).first();
      if (!(await btn.count())) { r = 'sem-botao'; }
      else {
        await btn.click();
        try { await page.waitForFunction(() => /Consulta feita|Simulado|resultado|Resultado|Erro|erro|Não foi possível/.test(document.body.innerText), null, {timeout: 25000}); } catch (e) {}
        await page.waitForTimeout(500);
        r = await page.evaluate(() => { const t = document.body.innerText; const m = t.match(/(Consulta feita[^\n]*|Simulado[^\n]*|Não foi possível[^\n]*|Erro[^\n]{0,80})/); const pre = document.querySelector('pre, .rd-result, [class*=result]'); return (m ? m[1].slice(0,80) : 'sem-mensagem') + ' | painel=' + (pre ? pre.innerText.length : 0); });
      }
    } catch (e) { r = 'erro:' + String(e).slice(0,80); }
    out.push(['CONSULTAR', mod, tab, r, fails.join(' ~ ')].join('|'));
  }
  page.off('response', onResp);
  return out.join('\n');
}
