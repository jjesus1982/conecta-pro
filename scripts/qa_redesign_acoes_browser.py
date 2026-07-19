"""QA de regressão — 17 ações de escrita do /redesign (browser real).

Prova, numa ÚNICA sessão de login no domínio público, que todas as ações de
escrita do redesign continuam funcionando fim-a-fim (form → POST → badge).
Guarda anti-regressão: rode após QUALQUER deploy que toque
`redesign_data_controller.py`, `ModuleView.tsx` ou os forms.

COMO RODAR (usa o Chromium headless do container det-robot):
    docker cp scripts/qa_redesign_acoes_browser.py conecta-pro-det-robot:/state/qa.py
    docker exec conecta-pro-det-robot python /state/qa.py

O QUE FAZ (marcador QA_REGRESS em todos os dados de teste):
  - 13 ações CREATE seguras: preenche + submete + confere badge de sucesso.
  - 2 que mutam registro real (mover funil / resolver ocorrência): submete SEM
    seleção e espera o 400 de validação ("endpoint vivo", sem mutar nada real).
  - 2 de falta (registrar-falta / escalar-substituto): só confere RENDER —
    REGRA: só testar em falta REAL (nunca fabricar falta no quadro ao vivo).

LIMPEZA (obrigatória após rodar) — apaga tudo pelo marcador, respeitando FK:
    docker exec conecta-pro-backend python3 - <<'PY'
    from core.database.session import SyncSessionLocal; from sqlalchemy import text
    db=SyncSessionLocal(); M='%QA_REGRESS%'
    db.execute(text("DELETE FROM proposal_items WHERE proposal_id IN (SELECT id FROM proposals WHERE title LIKE :m)"),{'m':M})
    db.execute(text("DELETE FROM reimbursement_items WHERE request_id IN (SELECT id FROM reimbursement_requests WHERE title LIKE :m)"),{'m':M})
    db.execute(text("DELETE FROM diaria_lancamentos WHERE observacao LIKE :m OR diarista_id IN (SELECT id FROM diaria_diaristas WHERE nome LIKE :m)"),{'m':M})
    for t,w in {'diaria_diaristas':'nome','occurrence_comments':'content','leads':'name',
                'proposals':'title','crm_tasks':'title','crm_client_notes':'nota',
                'payable_accounts':'description','receivable_accounts':'description',
                'gp_epi_deliveries':'epi_nome','gp_justifications':'reason',
                'reimbursement_requests':'title','job_positions':'title'}.items():
        db.execute(text(f"DELETE FROM {t} WHERE {w} LIKE :m"),{'m':M})
    db.commit(); print('limpo')
    PY

Esperado: 17/17 PASS.
"""
from playwright.sync_api import sync_playwright

BASE = "https://erp.conectamais.pro"
MARK = "QA_REGRESS"
D1, D2 = "2026-08-20", "2027-08-20"

OK_WORDS = ["registrad", "criad", "aberta", "salva", "lançad", "lancad",
            "cadastrad", "adicionad", "comentário", "comentario", "movid", "atualizad"]
ERR_WORDS = ["não foi possível", "nao foi possivel", "inválid", "invalid", "selecione",
             "mínimo", "minimo", "obrigat", "não encontrad", "nao encontrad", "erro", "falha"]

# (rótulo, slug, screen, mode, ops)
# ops: (kind, idx, value). kinds: t=text, d=date, s=select(value), sf=select_first_nonempty, a=textarea
ACTIONS = [
    ("Lançar diária", "operacional", "lancar-diaria", "submit",
     [("sf",0,None),("d",0,D1),("sf",1,None),("sf",2,None),("sf",3,None),("a",0,MARK+" diaria")]),
    ("Cadastrar diarista", "operacional", "cadastrar-diarista", "submit",
     [("t",0,MARK+" Diarista"),("t",1,"529.982.247-25"),("t",2,"529.982.247-25"),("t",3,"92991110000"),("t",4,"qa@teste.com")]),
    ("Resolver ocorrência", "operacional", "resolver-ocorrencia", "validate", []),
    ("Comentar ocorrência", "operacional", "comentar-ocorrencia", "submit",
     [("sf",0,None),("a",0,MARK+" comentario")]),
    ("Novo lead", "crm", "novo-lead", "submit",
     [("t",0,MARK+" Lead"),("t",1,"QA Co"),("t",2,"qa@teste.com"),("t",3,"92991110000"),("sf",0,None),("t",4,"50,00"),("a",0,"obs")]),
    ("Nova proposta", "crm", "nova-proposta", "submit",
     [("sf",0,None),("t",0,MARK+" Proposta"),("t",1,"Servico QA"),("t",2,"50,00"),("a",0,"desc")]),
    ("Mover no funil", "crm", "mover-oportunidade", "validate", []),
    ("Nova tarefa", "crm", "nova-tarefa", "submit",
     [("t",0,MARK+" Tarefa"),("sf",0,None),("d",0,D1),("sf",1,None),("a",0,"desc")]),
    ("Anotar cliente", "crm", "anotar-cliente", "submit",
     [("sf",0,None),("a",0,MARK+" nota")]),
    ("Conta a pagar", "financeiro", "registrar-conta-pagar", "submit",
     [("t",0,MARK+" pagar"),("t",1,"Forn QA"),("t",2,"50,00"),("d",0,D1),("a",0,"obs")]),
    ("Conta a receber", "financeiro", "registrar-conta-receber", "submit",
     [("t",0,MARK+" receber"),("t",1,"Cliente QA"),("t",2,"50,00"),("d",0,D1),("a",0,"obs")]),
    ("Entrega de EPI", "gestao-de-pessoas", "registrar-entrega-epi", "submit",
     [("sf",0,None),("t",0,MARK+" EPI"),("t",1,"CA-1"),("t",2,"1"),("t",3,"NR-6"),("d",0,D1),("d",1,D2)]),
    ("Justificativa ponto", "gestao-de-pessoas", "registrar-justificativa-ponto", "submit",
     [("sf",0,None),("sf",1,None),("sf",2,None),("a",0,MARK+" justificativa ponto")]),
    ("Reembolso", "departamento-pessoal", "registrar-reembolso", "submit",
     [("t",0,MARK+" Reembolso"),("sf",0,None),("t",1,"50,00"),("t",2,"QA loja"),("d",0,D1),("a",0,"desc")]),
    ("Abrir vaga", "recrutamento", "abrir-vaga", "submit",
     [("t",0,MARK+" Vaga"),("t",1,"Op"),("sf",0,None),("sf",1,None),("t",2,"1"),("t",3,"Manaus"),("t",4,"AM"),("t",5,"1670,00"),("t",6,"1900,00"),("a",0,"req"),("a",1,"desc")]),
    ("Registrar falta (só render)", "operacional", "registrar-falta", "render", []),
    ("Escalar substituto (só render)", "operacional", "escalar-substituto", "render", []),
    # Solicitar férias: exige colaborador com saldo + datas coerentes (5..30 dias, futuro).
    # Deixado como 'render' aqui p/ não depender de saldo; provado individualmente (prova_ferias.png).
    ("Solicitar férias (só render)", "departamento-pessoal", "solicitar-ferias", "render", []),
]

def badge(pg):
    try: return pg.locator(".rd-form-card .rd-badge").first.inner_text(timeout=6000)
    except Exception: return "(sem badge)"

def pick_first(sel):
    opts = sel.locator("option")
    for i in range(opts.count()):
        v = opts.nth(i).get_attribute("value")
        if v: sel.select_option(v); return True
    return False

def classify(mode, bd):
    b = bd.lower()
    if mode == "render": return "PASS(render)"
    if mode == "validate":
        return "PASS(alive)" if any(w in b for w in ERR_WORDS) else "FAIL"
    if any(w in b for w in ERR_WORDS): return "FAIL"
    if any(w in b for w in OK_WORDS): return "PASS"
    return "FAIL"

results = []
with sync_playwright() as pw:
    b = pw.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage"])
    ctx = b.new_context(ignore_https_errors=True, viewport={"width":1340,"height":900})
    pg = ctx.new_page()
    pg.goto(f"{BASE}/redesign/login", wait_until="domcontentloaded", timeout=45000); pg.wait_for_timeout(1500)
    pg.fill("input[type=email]", "mcp-service@conectamais.pro")
    pg.fill("input[type=password]", "67142814d66bdb5aa96b97e902e98cc486ae")
    pg.click("button[type=submit]"); pg.wait_for_url("**/redesign", timeout=20000)

    for label, slug, screen, mode, ops in ACTIONS:
        try:
            pg.goto(f"{BASE}/redesign/{slug}?t={screen}", wait_until="domcontentloaded", timeout=45000)
            pg.wait_for_selector(".rd-form-card", timeout=20000); pg.wait_for_timeout(1500)
            if mode == "render":
                has = pg.locator(".rd-form-card").count() > 0
                results.append((label, "PASS(render)" if has else "FAIL", "form presente")); continue
            texts = pg.locator(".rd-form-card input[type=text]")
            dates = pg.locator(".rd-form-card input[type=date]")
            sels  = pg.locator(".rd-form-card select")
            areas = pg.locator(".rd-form-card textarea")
            if sels.count():
                for _ in range(20):
                    if all(sels.nth(i).locator("option").count() >= 1 for i in range(sels.count())): break
                    pg.wait_for_timeout(400)
            for kind, idx, val in ops:
                if kind == "t": texts.nth(idx).fill(val)
                elif kind == "d": dates.nth(idx).fill(val)
                elif kind == "a": areas.nth(idx).fill(val)
                elif kind == "s": sels.nth(idx).select_option(val)
                elif kind == "sf": pick_first(sels.nth(idx))
            pg.click(".rd-form-card button.rd-btn-primary"); pg.wait_for_timeout(4500)
            bd = badge(pg)
            results.append((label, classify(mode, bd), bd))
        except Exception as e:
            results.append((label, "ERROR", str(e)[:80]))

    ctx.close(); b.close()

print("\n==== QA REGRESSÃO /redesign — RESULTADOS ====")
npass = 0
for label, st, detail in results:
    if st.startswith("PASS"): npass += 1
    print(f"[{st:12}] {label:34} | {detail[:66]}")
print(f"\n{npass}/{len(results)} PASS")
print("LEMBRE: rode a limpeza por marcador QA_REGRESS (ver docstring).")
