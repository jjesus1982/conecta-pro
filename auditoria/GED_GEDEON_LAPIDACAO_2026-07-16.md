# GED/GEDEON — Lapidação completa · Relatório de execução
**Conecta PRO · 16/07/2026 · commit `d5733894` · deployado durável (blue/green + testes na imagem baked)**
Método: sweep de API (96 GETs) + sweep de browser (15 telas) + oráculo de veracidade
(tela × banco × Drive) + correção na raiz + guard-rails + QA automatizado.

---

## 1. O que foi encontrado e corrigido

### BUG 1 — Consultor GEDEON mentia no panorama (dado real × exibido) 🔴
**Sintoma:** painel do consultor mostrava "Funcionários ≈0" para TODOS os 11 condomínios
e "Kits montados 0/11" para junho — com 52 funcionários alocados e 9 kits no Drive.
**Causas-raiz (duas):**
- Funcionários: o SQL casava posto↔cliente **por nome** (`ILIKE`), que nunca batia
  (acento: "Condomínio" × "CONDOMINIO"; estrutura: "DO EDIFICIO" no meio). O elo FORMAL
  `posts.client_id` (curado pelo Jordan) já existia e não era usado.
- Kits: o panorama só olhava `gedeon_kit_history` (fluxo GEDEON), que não tem 2026-06 —
  mas os kits EXISTEM (montados por outros fluxos): `ged_document_kits` (espelho do
  Drive) tem 9 kits de junho com 384 docs. O elo ged_clients↔clients é por nome exato
  (11/11 verificado).
**Agora:** Michelangelo 3 func · Ideal Flores 11 · Mirante 9 · Prime Arena 6 · Villa dos
Pássaros 6 · Villa Dei Fiori 7 · Laranjeiras 10; kits 9/11 SIM com docs reais (106, 79,
58…), `pronto_para_fechar` coerente, campo `drive_link` incluído.

### BUG 2 — 6 rotas GED engolidas por /{param} (4× HTTP 500 + 2× 422) 🔴
`/document-shares/owner`, `/recipient`, `/document-signatures/signer`,
`/document-tags/most-used`, `/folders/root`, `/documents/expired` — todas capturadas
pelas rotas `/{share_id}` etc. declaradas antes ("owner" ia pro banco como UUID → 500).
**Fix:** conversor `:uuid` em 60 rotas dos 5 controllers (mesmo padrão do Operacional).
Rotas literais → 200; rotas com UUID real seguem funcionando.

### BUG 3 — Pastas-lixo no Drive poluíam o painel de completude 🔴 (ATIVO no dia)
**Sintoma:** painel mostrava **24 "kits"** (real: ~11) — 12 deles eram PASTAS na raiz do
workspace com NOME DE ARQUIVO ("Comprovante de Pagamento de Salário_Fulano.pdf/Julho/…"),
criadas em 30/06 e **16/07 (bug vivo)** por chamadas com argumentos trocados
(nome de arquivo no lugar do condomínio em `garantir_pasta_kit`).
**Fix em 3 camadas:**
1. Limpeza: 12 pastas-lixo movidas pra lixeira do Drive (100% vazias — verificado item a
   item antes; recuperáveis 30 dias).
2. **Guard no choke point:** `garantir_pasta_kit` RECUSA "condomínio" com extensão de
   arquivo (log de warning aponta o caller) — a classe inteira morre, qualquer que seja
   o caller.
3. Filtro em `condominios_do_workspace` (extensões + pastas meta).
**Agora:** completude = 11 kits reais, média honesta 43% (era 20% distorcida).

### BUG 4 — Dashboard GED travava 30s a cada 90s 🟡
Ler o Drive frio custa ~30s e o cache tinha TTL 90s → a tela ficava presa em "Lendo os
kits no Drive…" quase sempre. **Fix:** TTL completude 90s→600s, kit_cache 90s→300s.
Seguro: toda mutação via API invalida na hora (`_invalidar_kit`), e o botão "Atualizar"
força releitura (`refresh=true`).

### BUG 5 — RiskMonitor/GEDEON financeiro quebrado 🟡
Task `gedeon.risk_monitor` rodava com `erro: ReceivableStatus has no attribute ABERTA`
(enum nunca teve ABERTA) → contexto financeiro zerado nos alertas. **Fix:** filtro por
`notin_` de status fechados. Contexto agora calcula inadimplência real (R$242k/8 títulos).

### Observações honestas (não são bugs)
- `/envios` zerado = **vazio-real** (feature de kits-template/atribuições, tabela vazia).
- `/documentos` exige filtro antes de listar = design (não mente dado).
- Certidões: cards ricos com fontes marcadas (inclusive "portal indisponível" honesto).

## 2. Provas (tudo na imagem baked, pós-recreate)
- **Suíte pytest: 29/29** (12 regressões GED novas + 17 do Financeiro sem regressão) —
  `backend/tests/ged_release/`: rotas destravadas, panorama com elo formal, kits do
  espelho do Drive, completude sem lixo, guard anti-arquivo, RiskMonitor sem erro.
- **QA de browser: 19/19** — `scripts/qa_ged_browser.py` (permanente): 15 telas sem
  crash/console-error/HTTP≥400 + consultor sem "≈0 geral" (9/11 kits) + painel resolve
  + sem pasta-lixo + certidões reais.
- Drive workspace limpo (12 pastas na lixeira, raiz só com condomínios reais).

## 3. Pendências conhecidas (P2/futuro)
- 2 condomínios sem kit em junho (GREEN HILLS, PARISE VILLAGE) — sem funcionários
  alocados; provável cliente sem operação: **Jordan confirma** se é esperado.
- Primeira carga fria do painel ainda custa ~30s (natureza do Drive); mitigado pelo TTL.
  Se incomodar: pré-aquecer via celery beat (não feito — decisão de escopo).
- Incidente das pastas-lixo: caller original não reproduzível no código atual (rodou em
  estado docker-cp anterior ao bake das 13:53); o guard mata a classe toda de qualquer
  forma e loga o caller se voltar.
