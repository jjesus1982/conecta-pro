async (page) => {
  const CASOS = [["rh", "?t=cct-hora-extra", "Calcular", {"salario_base": "1920.50", "jornada_tipo": "12x36", "horas_extras_normais": "10", "horas_extras_feriado": "12", "intrajornada_nao_concedida": "false"}], ["rh", "?t=cct-noturno", "Calcular", {"salario_base": "1920.50", "jornada_tipo": "12x36", "horas_noturnas": "80"}], ["rh", "?t=cct-validar-salario", "Validar", {"cargo": "Porteiro", "salario_atual": "1600"}], ["fiscal", "?t=calc-simples", "Calcular", {"receita_mes": "255400.06", "rbt12": "2688017"}], ["fiscal", "?t=calc-retencoes", "Calcular", {"valor_servico": "65842.42", "regime_empresa": "simples_nacional"}], ["crm", "?t=simular-preco", "Simular", {"service_type": "portaria", "base_salary": "1920.50", "headcount": "4", "contract_months": "12", "margin_target": "20", "client_state": "AM"}], ["departamento-pessoal", "?t=g-desligamento&tab=calcular-rescisao", "Calcular", {"employee_id": "2430761d-172e-44b8-a817-edfea166e321", "tipo_rescisao": "pedido_demissao", "data_desligamento": "2026-09-04", "dias_trabalhados_mes": "4", "ferias_vencidas_dias": "0", "saldo_fgts": "3994.64"}], ["departamento-pessoal", "?t=g-ferias&tab=calcular-ferias", "Calcular", {"employee_id": "2430761d-172e-44b8-a817-edfea166e321", "dias_gozo": "30", "dias_abono": "0"}], ["financeiro", "?t=g-custos&tab=pricing-calcular", "Calcular", {"tipo": "portaria", "quantidade": "4", "escala": "12x36", "localizacao": "Manaus"}], ["crm", "?t=simular-fechamento", "Simular", {"estagio": "negotiation"}]];
  const out = [];
  for (const [mod, q, cta, vals] of CASOS) {
    const fails = []; const posts = [];
    const onResp = async r => { try { const u=r.url(); if (u.includes('/api/') && r.request().method()==='POST') { let b=''; try { b=(await r.text()).slice(0,220); } catch(e){} posts.push(r.status()+' '+u.replace('https://erp.conectamais.pro','')+' :: '+b.replace(/\s+/g,' ')); } } catch(e){} };
    page.on('response', onResp);
    let nota = '';
    try {
      await page.goto('https://erp.conectamais.pro/redesign/'+mod+q, {waitUntil:'domcontentloaded'});
      await page.waitForFunction(() => { const m=document.querySelector('main.rd-content'); return m && m.innerText.length>50 && !document.body.innerText.includes('carregando…'); }, null, {timeout: 30000});
      await page.waitForTimeout(500);
      const campos = await page.evaluate(() => [...document.querySelectorAll('main.rd-content .rd-field')].map(f => { const el=f.querySelector('input,select,textarea'); return {label:(f.querySelector('label')||{}).innerText||'', tag: el?el.tagName:'', type: el?el.type:''}; }));
      // preencher por ordem de campos do JSON: a ordem dos .rd-field segue scr.fields
      const keys = Object.keys(vals);
      const fields = page.locator('main.rd-content .rd-field');
      const n = await fields.count();
      const ordem = {"rh?t=cct-hora-extra": ["salario_base", "jornada_tipo", "horas_extras_normais", "horas_extras_feriado", "intrajornada_nao_concedida"], "rh?t=cct-noturno": ["salario_base", "jornada_tipo", "horas_noturnas"], "rh?t=cct-validar-salario": ["cargo", "salario_atual", "employee_id"], "fiscal?t=calc-simples": ["receita_mes", "rbt12", "liminares"], "fiscal?t=calc-retencoes": ["valor_servico", "regime_empresa", "liminares"], "crm?t=simular-preco": ["service_type", "base_salary", "headcount", "contract_months", "margin_target", "client_state", "benefits_value", "equipment_value"], "departamento-pessoal?t=g-desligamento&tab=calcular-rescisao": ["employee_id", "tipo_rescisao", "data_desligamento", "dias_trabalhados_mes", "ferias_vencidas_dias", "saldo_fgts"], "departamento-pessoal?t=g-ferias&tab=calcular-ferias": ["employee_id", "dias_gozo", "dias_abono"], "financeiro?t=g-custos&tab=pricing-calcular": ["tipo", "quantidade", "escala", "localizacao"], "crm?t=simular-fechamento": ["estagio", "deals"]};
      for (let i=0;i<n;i++) {
        const key = ordem[mod+q] ? ordem[mod+q][i] : null;
        if (!key || !(key in vals)) continue;
        const el = fields.nth(i).locator('input,select,textarea').first();
        const tag = await el.evaluate(e=>e.tagName);
        if (tag==='SELECT') { await el.selectOption(vals[key]); } else { await el.fill(vals[key]); }
      }
      await page.locator('main.rd-content button', {hasText: new RegExp('^'+cta+'$')}).first().click();
      await page.waitForTimeout(3500);
      nota = await page.evaluate(() => { const m=document.querySelector('main.rd-content'); const t=m?m.innerText:''; const i=Math.max(t.indexOf('Resultado'), t.indexOf('R$'), t.indexOf('rro')); return t.replace(/\s+/g,' ').slice(-260); });
    } catch(e) { nota = 'EXC '+String(e).slice(0,120); }
    page.off('response', onResp);
    out.push(mod+q+' | '+posts.join(' || ')+' | tela: '+nota);
  }
  return out.join('\n');
}