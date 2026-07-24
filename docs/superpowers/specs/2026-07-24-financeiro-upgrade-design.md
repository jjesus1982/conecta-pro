# Spec — Upgrade do Módulo Financeiro (Redesign)

**Data:** 2026-07-24 · **Aprovado por:** Jordan · **Execução:** SOLO no T1, em LOOP, fases definidas pelo T1. O que importa é o FINAL: tudo entregue.

---

## 1. Contexto e problema (análise concluída)

Fontes: 34 screenshots do clássico + 43 do redesign (Drive) · auditoria de 26 controllers/502 rotas do backend (`auditoria/parity/FINANCEIRO_MAPA_UPGRADE.md` + `FINANCEIRO_BACKEND_{bancos,receber_pagar,contabil_fiscal}.md`).

- **Cobertura:** das ~163 capacidades relevantes do backend, o redesign expõe totalmente **15 (9%)**; 38 parciais; **110 (68%) ausentes**.
- **5 telas-substituto enganosas** (mostram dado de OUTRA fonte): Contabilidade (extrato categorizado ≠ razão de partidas dobradas), Compras (itens NF-e ≠ requisições/ordens), Estoque (saldo NF-e ≠ movimentos), Conciliação (folha×Inter ≠ conciliação bancária de extrato), Clientes (`clients` do CRM ≠ `customers` do contas-a-receber).
- **Features do clássico perdidas:** projeção/insights de fluxo, Importar OFX, conciliação de extrato (4 abas), plano de contas/centros de custo/balancete, régua de inadimplência, PIX recorrente (MRR), calculadora de medição, contratos a faturar, fila de aprovação D7, categorização, audit log, aging com KPIs na tela.
- **Menu:** ~42 itens planos e redundantes (7 sobre bancos, 9 ações "pagar-*" como navegação, duplicatas literais `inter-pagamentos`==`pagamentos-inter`, `custeio`==`custeio-cct`).
- **Motivo de urgência:** o clássico será DESLIGADO — o que não existir no redesign se perde.
- **Boa notícia:** ~tudo é gap de FIAÇÃO (endpoint/dado já existe no backend), não de construção. Inclui o audit log (campos `prepared_by/approved_by/approval_otp_used/executed_at/...` em `inter_payments`).

## 2. Objetivo e critérios de sucesso

**Objetivo:** o financeiro do redesign vira um módulo ORGANIZADO (7 grupos com abas) e COMPLETO (capacidades do backend expostas, dado honesto), pronto para o desligamento do clássico.

**Critérios de sucesso (DoD global):**
1. Menu do financeiro: 42 itens → **7 grupos**; ações de pagamento viram botões dentro das telas (gated OTP), não itens de menu.
2. As **5 telas-substituto** corrigidas (fonte certa) ou renomeadas honestamente.
3. As **12 famílias de capacidade ausentes** (lista §4) expostas — leitura fiada; escrita com gate.
4. **Nenhuma regressão**: tudo que o redesign já mostra hoje continua acessível (deep-links `?t=<id-antigo>` redirecionam para grupo+aba).
5. QA oráculo (exibido==banco por tela) + E2E Playwright (clicar, abrir, baixar) verdes; relatório final entregue.
6. Payload/tempo do `/redesign/data/financeiro` dentro do orçamento (§6-C).

## 3. Design aprovado

### 3.1 Abordagem técnica: tipo de tela `tabs` no ModuleView (aditiva)
- `ModuleView` ganha o tipo `tabs`: `{type:'tabs', tabs:[{id, label, screen}]}` — cada aba renderiza uma tela normal (dash/table/cards/list/form) pelos renderers existentes (DocButtons/ExportMenu/OTP-form inclusos, sem mudanças neles).
- Menu do `financeiro.json` → 7 itens (grupos). Builders montam cada grupo compondo as telas existentes como abas.
- **Deep-link map:** `?t=<id-antigo>` resolve para `grupo` + aba ativa (nada quebra: bookmarks, ctaTo, integrações).
- Rejeitadas: (B) páginas Next custom = 2º frontend p/ manter; (C) só agrupar menu = amontoado persiste.

### 3.2 Os 7 grupos (conteúdo)
1. **Visão Geral** — Resumo (saldo consolidado Inter+Cora · DRE do mês · MRR · KPIs pagar/receber) · Raio-X · Projeção & Insights (`cashflow/projection`, `forecast`, `ai/risks`, `ai/opportunities`) · CFO IA.
2. **Receber** *(PILOTO)* — Contas a Receber (aging com KPIs) · Cobranças (emitir boleto/PIX · emitidas · PIX Recorrente (`recurring_billing`) · Régua (`billing_rules`) · inadimplentes) · Faturamento (contratos a faturar + calculadora de medição, `ai/billing/*`) · Clientes (fonte `customers` do AR — corrige substituto).
3. **Pagar** — Contas a Pagar (aging) · Fila de Aprovação D7 (`payable approve/bulk/reject/schedule` — ação humana) · Pagamentos Inter (histórico + audit log + comprovantes) · Folha PJ · Diaristas · ações pagar-boleto/PIX/TED/DARF como BOTÕES gated OTP.
4. **Bancos & Conciliação** — Saldos · Extrato Inter/Cora · Conciliação bancária real (`bank_reconciliation` matching/progresso) · Importar OFX (`bank-transactions/import/ofx`) · Conciliação folha×Inter (atual, renomeada "Conciliação de folha").
5. **Fiscal & Contábil** — NFS-e emitidas/entrada + DANFSe · Guias · Certidões · Contabilidade REAL (`accounting`: plano de contas · centros de custo · lançamentos · balancete) · Justificativas Lucro Real (`justificativa_controller`).
6. **Custos & Orçamento** — Custos CCT · Custeio ABC real (`custeio /abc /contratos`) · Precificação · Orçamentos.
7. **Cadastros & Suprimentos** — Fornecedores · Contratos · Compras reais (`purchase`: requisições/ordens) · Estoque real (`inventory`: movimentos/inventários).

### 3.3 Fases do loop (sequência do T1)
| Fase | Entrega | Gate de saída |
|---|---|---|
| **F0** | Fundação `tabs` + deep-link map + menu 7 grupos (esqueleto; telas atuais realocadas SEM perda) | provado no browser; outros módulos intactos |
| **F1** | **Piloto Receber** completo (incl. correção Clientes) | QA oráculo + E2E; padrão congelado |
| **F2** | Bancos & Conciliação (incl. correção Conciliação, OFX) | idem |
| **F3** | Pagar (fila D7, audit log; máximo cuidado money-out) | idem + gates OTP intactos |
| **F4** | Visão Geral & IA (projeção/insights/DRE inline) | idem |
| **F5** | Fiscal & Contábil (incl. Contabilidade real) | idem |
| **F6** | Custos & Orçamento (Custeio ABC real) | idem |
| **F7** | Cadastros & Suprimentos (incl. Compras/Estoque reais) | idem |
| **F8** | QA total + E2E Playwright de tudo + relatório final | DoD global |

Cada fase: rota curl-verificada ANTES de fiar · commit por etapa (pathspec) · deploy blue-green ao fim da fase · prova no browser · não-conformidade corrigida na hora.

## 4. As 12 famílias de capacidade a restaurar
1 Contabilidade real (~50 rotas accounting) · 2 Conciliação bancária + OFX · 3 Fluxo inteligente (projeção/insights/DRE inline) · 4 Cobrança/recorrência (régua + PIX recorrente) · 5 Ciclo de vida receber/pagar (aprovar/agendar/baixar/renegociar/protestar/write-off/acordo) · 6 Custeio ABC · 7 Faturamento IA (medição + a-faturar) · 8 CFO IA completo · 9 Compras & Estoque reais · 10 Justificativas Lucro Real · 11 Aging com KPIs na tela · 12 Audit log de pagamentos.

## 5. Regras invioláveis
- **Dinheiro-que-sai = gate OTP humano** (fluxo existente do redesign_write_gate). Aprovação D7 = ação humana explícita, nunca automatizada.
- **Nunca fabricar dado**: oráculo exibido==banco; vazio-real = "aguardando dado"; stub/placeholder = disabled honesto.
- **Nunca testar caminho feliz de pagamento/cobrança** (dispara OTP real / move dinheiro real / cobra cliente real). Testa render + gate disparando.
- **Régua/PIX recorrente**: são mensagens/cobranças a CLIENTES reais → entregar primeiro READ-ONLY (config + preview + histórico); qualquer disparo automatizado só com aprovação explícita do Jordan.
- Deploy backend blue-green (lock, porta-travada py_compile); frontend rebuild imagem (DET pausado).
- Browser: matar Chromium órfão antes; matar a própria sessão ao concluir.

## 6. PRÉ-MORTEM (é 2026-08 e deu errado — por quê?)

### A. A fundação `tabs` quebrou os OUTROS módulos (impacto: catastrófico · prob: média)
`ModuleView` é compartilhado por TODOS os 31 módulos. Um bug no tipo novo (ou num refactor "de passagem") derruba o sistema inteiro.
**Mitigação:** tipo `tabs` 100% ADITIVO — zero mudanças nos renderers existentes; `default:` do switch intacto. Após F0, smoke-test em 3 módulos não-financeiro no browser. Rollback = git revert de 1 commit.

### B. Deep-links quebraram silenciosamente (alto · alta)
42 ids antigos (`?t=contas-pagar` etc.) viram 404 visual ("Tela em preparação") depois da reorganização — bookmarks, ctaTo e hábitos do Jordan quebram.
**Mitigação:** mapa `id-antigo → (grupo, aba)` na F0 com teste automatizado: os 42 ids listados e resolvidos; QA da F0 percorre todos.

### C. Payload-monstro: o /redesign/data/financeiro ficou lento (alto · ALTA)
Já é **860KB / 0,96s** com 42 telas. Restaurar 110 capacidades no mesmo fetch único pode levar a 3MB+/vários segundos → módulo "lento" = upgrade percebido como piora.
**Mitigação:** ORÇAMENTO por fase: payload ≤ 2MB, tempo ≤ 2,5s (medido no gate de cada fase). Ferramentas: LIMIT em toda query (≤200), resumir tabs pesadas (KPIs + top-N), e se estourar → dividir o fetch por grupo (`/redesign/data/financeiro?grupo=`) — decisão na fase que estourar, não antes.

### D. O builder virou arquivo-monstro ingovernável (médio · ALTA)
`financeiro.py` já tem 922 linhas; com 7 grupos vai a 3000+ → edição arriscada, conflitos, contexto estourado.
**Mitigação:** VERIFICADO: o discovery PULA arquivos `_*` (`_mi.name.startswith("_")`). Dividir em `_fin_receber.py`, `_fin_pagar.py`… importados pelo `financeiro.py`. Um arquivo por grupo, ≤500 linhas.

### E. Corrigir as telas-substituto muda números que o Jordan conhece (médio · certa)
"Contabilidade" mostrando o razão real ≠ o extrato categorizado que ele via; "Clientes" com `customers` ≠ contagem do CRM. Sem aviso, parece BUG.
**Mitigação:** rótulos honestos na transição (sub da tela explicita a fonte: "Razão contábil (partidas dobradas)"); onde os dois dados têm valor, ambos viram abas (ex.: "Extrato categorizado" E "Razão contábil"). Nada some — realoca.

### F. Ação de escrita disparou dinheiro/mensagem real em teste (catastrófico · média)
Fila D7 "Aprovar", PIX recorrente (cobra clientes REAIS via Inter cobv!), régua (mensagens a clientes). Um teste de caminho feliz = incidente real.
**Mitigação:** regra §5 — escrita sensível entra como READ-ONLY + preview primeiro; botões de disparo com gate OTP + confirm; QA testa APENAS render e gate disparando (nunca completa). Régua/recorrente só ativam com aprovação explícita do Jordan em produção.

### G. Endpoint "existe" mas 404/500 com dado real (médio · ALTA — já mordeu 2×)
`crm/proposals` filtrava is_active (404); DANFSe buscava de outra tabela. Grep achar a rota ≠ rota funcionar.
**Mitigação:** regra de ouro mantida: **curl-verificar CADA rota com id real ANTES de fiar** (200 + shape). O que falhar → investigar o filtro/fonte (como fizemos) ou disabled honesto.

### H. Árvore compartilhada / deploy do disco (alto · média)
Outras sessões (Hermes etc.) commitam na mesma árvore; deploy bakeia o disco inteiro.
**Mitigação:** pathspec-commit sempre; porta-travada (py_compile de TODOS os builders + tsc) antes de cada deploy de fase; deploy dentro do lock.

### I. `except:pass`/safe() esconde tela que morreu (médio · alta — já mordeu)
Tela nova falha silenciosamente → aba some, QA "verde".
**Mitigação:** QA por fase conta telas/abas esperadas vs presentes (oráculo numérico: N abas declaradas == N renderizadas); grep no log do container por "redesign_builders/… falhou".

### J. Loop de 8 fases perde o rumo / scope creep (médio · média)
163 capacidades convidam a "só mais essa"; ou o loop trava numa fase difícil.
**Mitigação:** DoD fechado POR FASE (tabela §3.3); o que não é da fase vai para a lista da fase dona; se uma capacidade emperrar > esforço razoável → disabled honesto + registro no relatório, segue o loop (entregar tudo > perfeição de um item).

### K. Fora de escopo explícito (para não inchar)
NÃO entram neste upgrade: emissão fiscal write (NF-e emitir/cancelar, SPED gerar — continuam disabled honesto até projeto fiscal próprio); DANFE/NFC-e placeholder; mudanças em OUTROS módulos; automação de mensagens da régua (só config/preview); mobile-first redesign (mantém responsivo atual).

## 7. Riscos aceitos
- Fetch único por módulo continua (mitigado por orçamento §6-C; divisão por grupo só se estourar).
- Algumas capacidades de escrita profundas (renegociar/protestar/write-off) podem entrar como read-only + registro manual gated na v1 — melhor que não aparecer; upgrade de workflow completo fica para iteração seguinte se o loop apertar.

## 8. Sucesso final
Jordan abre o financeiro e vê 7 grupos limpos; cada aba mostra dado REAL da fonte CERTA; projeção/insights/balancete/régua/recorrência/aprovação/audit visíveis; ações sensíveis gated; nada do clássico se perde quando ele for desligado.
