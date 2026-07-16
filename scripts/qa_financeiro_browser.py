"""Re-validação CIC executada pelo dev — REG-01 · FIN-04 · FIN-08 · contadores.
Espelha o prompt de re-validação, item por item, em browser real."""
import os, re, sys, json
from playwright.sync_api import sync_playwright

BASE="https://erp.conectamais.pro"; TOK=os.environ["ERP_TOKEN"]
results=[]; console_errors=[]

def check(item, ok, detail):
    results.append((item, ok, detail))
    print(("✅ PASS " if ok else "❌ FAIL ")+item+" — "+detail)

def money(txt):
    if not txt: return None
    m=re.search(r"-?\s*R\$\s*([\d.]+,\d{2})", txt)
    if not m: return None
    v=float(m.group(1).replace(".","").replace(",","."))
    return -v if txt.strip().startswith("-") else v

with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    ctx=b.new_context(viewport={"width":1440,"height":900})
    pg=ctx.new_page()
    pg.on("console", lambda m: console_errors.append(m.text[:160]) if m.type=="error" else None)
    pg.add_init_script(f"try{{localStorage.setItem('access_token','{TOK}')}}catch(e){{}}")

    api_headers={"Authorization": f"Bearer {TOK}"}

    # ═══ 1. REG-01 — /fluxo-caixa ═══
    pg.goto(f"{BASE}/modulos/financeiro/fluxo-caixa", wait_until="domcontentloaded")
    pg.wait_for_selector("table tbody tr", timeout=30000); pg.wait_for_timeout(5000)

    def rows():
        return pg.eval_on_selector_all("table tbody tr", """rs => rs.map(r => {
            const tds=[...r.querySelectorAll('td')];
            const s = tds[3] ? tds[3].querySelector('span') : null;
            return {tipo:(tds[2]||{textContent:''}).textContent.trim(),
                    valor:(tds[3]||{textContent:''}).textContent.trim(),
                    verde: s ? s.className.includes('text-green') : false,
                    vermelho: s ? s.className.includes('text-red') : false};
        })""")

    # 1a. entradas positivas/verdes (via filtro)
    pg.click("button:has-text('Entradas')"); pg.wait_for_timeout(2500)
    ent=rows()
    pix_recebido=[r for r in ent if "+" in r["valor"]]
    check("1a REG-01 entradas positivas/verdes",
          len(ent)>0 and all(r["tipo"]=="Entrada" and r["valor"].startswith("+") and r["verde"] for r in ent),
          f"{len(ent)} linhas; amostra {ent[0]['valor'] if ent else 'n/a'}")
    # 1b. saidas negativas/vermelhas
    pg.click("button:has-text('Saidas')"); pg.wait_for_timeout(2500)
    sai=rows()
    check("1b REG-01 saídas negativas/vermelhas",
          len(sai)>0 and all(r["tipo"]=="Saida" and r["valor"].startswith("-") and r["vermelho"] for r in sai),
          f"{len(sai)} linhas; amostra {sai[0]['valor'] if sai else 'n/a'}")
    # 1c. Todos volta a misturar
    pg.click("button:has-text('Todos')"); pg.wait_for_timeout(2000)
    todos=rows()
    check("1c REG-01 filtro Todos", len(todos)>0, f"{len(todos)} linhas")
    # 1d. barras Receitas
    bars=pg.evaluate("""()=>[...document.querySelectorAll("path[fill='#22c55e']")]
        .filter(x=>(x.getAttribute('d')||'').length>20).length""")
    check("1d REG-01 barras Receitas no gráfico", bars>=4, f"{bars} barras verdes (jun sem crédito = ok)")
    # 1e. KPIs Entradas/Saídas/Saldo coerentes
    kpis=pg.evaluate("""()=>{
        const out={};
        for (const lbl of ['Entradas','Saidas','Saldo Atual']){
            const el=[...document.querySelectorAll('p')].find(x=>x.textContent.trim()===lbl);
            out[lbl]= el ? el.parentElement.querySelector('p').textContent.trim() : null;
        } return out;}""")
    vE,vS,vSa=money(kpis.get("Entradas")),money(kpis.get("Saidas")),money(kpis.get("Saldo Atual"))
    check("1e REG-01 KPIs cards coerentes",
          all(v is not None for v in [vE,vS,vSa]) and vE>0 and vS>0 and 50000<vSa<120000,
          f"Entradas={kpis.get('Entradas')} Saídas={kpis.get('Saidas')} Saldo={kpis.get('Saldo Atual')}")

    # ═══ 2. FIN-04 — card == último ponto da série (comparo com a API da série) ═══
    card=pg.evaluate("""()=>{const el=[...document.querySelectorAll('p')].find(x=>x.textContent.trim()==='Projecao 30d');
        return el?el.parentElement.querySelector('p').textContent.trim():null}""")
    vCard=money(card)
    api=ctx.request.get(f"{BASE}/api/v1/financial/cashflow/projection?condominio_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                        headers=api_headers)
    proj=api.json() if api.ok else []
    vApi=float(proj[-1]["cumulative_balance"]) if proj else None
    ok04 = vCard is not None and vApi is not None and abs(vCard-vApi)<1.0 and abs(vCard)>1000
    check("2 FIN-04 card == série (API)", ok04, f"card={card} vs série={vApi}")

    # ═══ 3. FIN-08 — /faturamento aba Histórico ═══
    pg.goto(f"{BASE}/modulos/financeiro/faturamento", wait_until="domcontentloaded")
    pg.wait_for_timeout(4000)
    pg.click("button:has-text('Historico')"); pg.wait_for_timeout(5000)
    body=pg.evaluate("document.body.innerText")
    mKpi=re.search(r"(R\$\s*[\d.]+,\d{2})\s*\n\s*Valor Fixo Total", body)
    vKpi=money(mKpi.group(1)) if mKpi else None
    rules=ctx.request.get(f"{BASE}/api/v1/financial/billing-rules?limit=100", headers=api_headers).json()
    soma=sum(float(r.get("base_value") or 0) for r in rules if r.get("status")=="ativa" or r.get("is_active"))
    ok08 = vKpi is not None and abs(vKpi-soma)<1.0
    check("3a FIN-08 KPI == Σ base_value ativas", ok08, f"KPI={mKpi.group(1) if mKpi else None} vs Σ API={soma:.2f}")
    mTot=re.search(r"(\d+)\s*\n\s*Total Regras", body); mAtv=re.search(r"(\d+)\s*\n\s*Ativas", body)
    mIna=re.search(r"(\d+)\s*\n\s*Inativas", body)
    tot,atv,ina=(int(m.group(1)) if m else None for m in [mTot,mAtv,mIna])
    check("3b FIN-08 contadores regras", tot==10 and atv==10 and ina==0, f"Total={tot} Ativas={atv} Inativas={ina}")

    # ═══ 4. Contadores gerais ═══
    # 4a. TESTE QA zero em contas-pagar
    pg.goto(f"{BASE}/modulos/financeiro/contas-pagar", wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)
    pg.fill("input[placeholder*='Buscar']", "TESTE QA"); pg.wait_for_timeout(2000)
    n_pagar=pg.eval_on_selector_all("table tbody tr", "rs=>rs.filter(r=>r.textContent.includes('TESTE QA')).length")
    pg.goto(f"{BASE}/modulos/financeiro/contas-receber", wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)
    pg.fill("input[placeholder*='Buscar']", "TESTE QA"); pg.wait_for_timeout(2000)
    n_receber=pg.eval_on_selector_all("table tbody tr", "rs=>rs.filter(r=>r.textContent.includes('TESTE QA')).length")
    check("4a TESTE QA zero", n_pagar==0 and n_receber==0, f"pagar={n_pagar} receber={n_receber}")
    # 4b. DRE cards
    pg.goto(f"{BASE}/modulos/financeiro/relatorios", wait_until="domcontentloaded")
    pg.wait_for_timeout(8000)
    body2=pg.evaluate("document.body.innerText")
    mRec=re.search(r"A Receber \(total\)\s*\n\s*(R\$\s*[\d.]+,\d{2})", body2)
    mPag=re.search(r"A Pagar \(total\)\s*\n\s*(R\$\s*[\d.]+,\d{2})", body2)
    vRec,vPag=money(mRec.group(1)) if mRec else None, None
    vPag=money(mPag.group(1)) if mPag else None
    check("4b DRE cards A Receber/A Pagar", vRec is not None and vRec>400000 and vPag is not None and vPag>150000,
          f"A Receber={mRec.group(1) if mRec else None} A Pagar={mPag.group(1) if mPag else None}")

    # console errors (excluindo #418)
    novos=[e for e in console_errors if "418" not in e and "Minified React error" not in e]
    check("5 console sem erro novo", len(novos)==0, f"{len(novos)} erros: {novos[:3]}")
    b.close()

fails=[r for r in results if not r[1]]
print(f"\n════ RESULTADO: {len(results)-len(fails)}/{len(results)} PASS ════")
for f_ in fails: print("FALHOU:", f_[0], "→", f_[2])
sys.exit(1 if fails else 0)

# ─────────────────────────────────────────────────────────────────────────────
# USO (host, Playwright Python já instalado):
#   TOKEN=$(docker exec -e PYTHONPATH=/app conecta-pro-backend python3 -c "
#   from core.auth.jwt import create_access_token
#   from core.database.session import SyncSessionLocal
#   from sqlalchemy import text
#   s=SyncSessionLocal()
#   uid=s.execute(text(\"SELECT id FROM users WHERE email='jjesus@conectamais.pro' LIMIT 1\")).scalar()
#   print(create_access_token(subject=str(uid)))" | tail -1)
#   ERP_TOKEN=$TOKEN python3 scripts/qa_financeiro_browser.py
# Exit 0 = 11/11 PASS. Telas gated: o token é injetado no localStorage
# antes do app carregar (add_init_script) — sem senha, sem form.
# ─────────────────────────────────────────────────────────────────────────────
