# Revisão financeiro — fiscal + relatórios (agente só-leitura, 08/09/2026 ~01h Manaus)

Incidente: o agente disparou `POST /financial/bank-reconciliations/auto` por engano (esperava 422 do shadow) e a rota conciliou o PIX `[CORA] Concregrama Prime Arena` (R$ 4.300, 10/08) com o receivable `Servicos 09/2026 - CONDOMINIO PRIME ARENA (CTR-2026-00012)` (R$ 33.479,60) por casar a palavra "PRIME". As duas linhas foram restauradas para `pendente` às 01:0x e a rota foi apagada. Um `publish_nota_emitida(nota_id="conciliacao_1", valor=33479.6)` foi ao event bus e não foi desfeito.

## Defeitos (mais grave primeiro)
1. `nfse_entrada_controller.py` conciliacao_auto — S1 casa por palavra do nome sem conferir valor; marca receivable `paga` sem paid_value/payment_date; publica nota fictícia. **Apagada.**
2. `GET /bank-reconciliations/status` sombreada por `/bank-reconciliations/{id}` → 422 sempre. **Apagada.**
3. `models/nfse.py` `__tablename__="nfse"` e `nfe.py` `"nfe"` — tabelas não existem (banco tem `nfses`/`nfes`). Todo caminho ORM em `fiscal_repository.py` 259–369 e 404–507 → 500. Rotas POST /fiscal/nfe, /nfe/emitir, /nfe/cancelar, /nfse, /nfse/emitir, /nfse/cancelar. Emissão real é o portal nacional.
4. `agents/tax_calculator.py:407–447` calcular_retencoes_nfse (VIVA no redesign): IRRF 1,5% aplicado a portaria/limpeza/locação de mão de obra (é 1%, art. 716 RIR/2018); gatilho `>= 215.05` errado (dispensa é imposto ≤ R$ 10); cobra IR/CSLL/PIS/COFINS de prestador Simples sem liminar. **Validar com a contadora.**
5. `relatorios_controller.py:597` tributos_consolidados: FGTS lido de `4.1.2.01` (plano velho); no razão está em `5.1.1.02` (409 lançamentos, R$ 60.987,20) → fgts=0. L621/630 PIS/COFINS zerados "por liminar" para a Eletrônica (Lucro Real) — a liminar é da Patrimonial e está `a_solicitar`.
6. `relatorios_controller.py:111–136` × tabela `liminares`: duas fontes contraditórias (`fiscal_liminares` 2× vigente vs `liminares` 2× a_solicitar). painel_fiscal L544 chumba texto.
7. `fiscal_controller.py:1497–1570` dashboard: `total_nfe_mes` recebe contagem de NFS-e; `valor_total_nfse` é acumulado histórico rotulado como mês; sem empresa_id nem filtro cancelada. Mesmo filtro falta em listar_nfses (753), fiscal_stats_real, ged/nfse_controller list/dashboard, financial_overview_controller:27.
8. `fiscal_controller.py:753` lista devolve id=chave_acesso (nfse_emitidas_nacional); detalhe/PATCH/DANFSe (824/840/1735) exigem UUID de `nfses` legada → 422 ao clicar.
9. `fiscal_repository.py:742–756` "atrasadas" = status='atrasada' (0 linhas) → sempre []; há 19 pendentes vencidas. Correção: pendente AND data_vencimento < hoje Manaus.
10. `financial_dashboard_controller.py` 62–137, 230–257, 374–407, 568–572 e `financial_overview_controller.py` 59/84/119: CURRENT_DATE do Postgres (UTC) × date.today() Manaus. Das 20h às 23h59 o SQL está no dia seguinte.
11. `financial_dashboard_controller.py` 208/343/533/620/706/750: except Exception → 200 com {"error", traceback}.
12. `financial_dashboard_controller.py:230–276` cashflow/forecast: saldo só is_main_account (Inter R$ 1.323) × médias de todas as contas; fallbacks chumbados 88000/80000/100000.
13. `financial_overview_controller.py:139–222` cashflow_dashboard (clássico): closing_balance = Σ cashflow_entries desde sempre (−R$ 1.470.294); upcoming_* = 10% inventado; overdue_* = 0.
14. `ged/controllers/nfse_controller.py:796–860` headcount: JOIN ged_clients mas posts.client_id referencia clients → sempre 0.
15. `ged/controllers/nfse_controller.py:600–673` renew_contract: INSERT status='ativo' enquanto MRR filtra 'active'; não copia empresa_id/tipo_servico/retencao_*/payment_day/template_id.
16. `ged/controllers/nfse_controller.py:64/90` POST /financial/nfse/emitir: optante_simples=True default para a Eletrônica (Lucro Real); grava em nfses legada; ABRASF Manaus. Espelho fiscal_controller.py:922 optante_simples=False chumbado.
17. `ged/controllers/nfse_controller.py:497` mrr_total soma drafts (293.600 vs 269.700).
18. `relatorios_controller.py:1354` _dre_simplificado: adicional IRPJ teto fixo R$ 20.000 seja 1 ou 12 meses. L1392 rótulos "4.1.1/4.1.2".
19. `relatorios_controller.py:1265` listar_custos passa contrato_id= a listar_custos_por_tipo() (TypeError engolido → 200 total 0). 4 das 5 tabelas de custeio estão em `lixo_20260906`.
20. `nfse_entrada_controller.py` auto-criar-payables ×3: lêem `nfse_entrada` legada (10 notas, todas com payable) → sempre "0 criadas". **Apagadas**; caminho real = payable_sources_service (task registrar_obrigacoes). custos/resumo, sync ×2, status-sync também **apagadas**.
21. `fiscal_controller.py:1294–1320` calcular_das: rbt12 > 4,8M → KeyError 500. fiscal_obligation.py:670 repartição fixa "Faixa 3".
22. `fiscal_controller.py:367–432` retencao/calcular: retencoes_federais vazia → 404 sempre; repository 228–241 scalar_one_or_none com ORDER BY → MultipleResultsFound; cfop_ncm.py:333 dispensa PCC por imposto < 215,05 (regra: ≤ R$ 10).
23. `relatorios_controller.py` 52/111/181 `_ensure_*`: CREATE TABLE + seed + commit em GET.
24. `relatorios_controller.py:1049–1195` /orcamentos, /execucao, /ytd: BudgetService lê fin_journal_entries (ledger morto) → sempre vazio. Substituído por /orcamentos-kv.
25. `fiscal_controller.py:459` GET /nfe: `return []` chumbado (nfes tem 2).
26. `fiscal_controller.py` 994/1351/1479 (retencoes/competencia, receita-12-meses, stats): nfses/nfes legadas → zeros.
27. `nfse_entrada_controller.py` resumo_fiscal: total_liquido = valor − iss sem saber se ISS foi retido.
28. `ged/controllers/nfse_controller.py:917` competencia_mes NULL → TypeError (latente).
29. main_production.py:819–826 fiscal_router montado em /financial/fiscal E /financial/fiscal/fiscal (63 rotas viram 126).
30. relatorios_controller.py:642–693 chama serviços psycopg2 síncronos dentro de handlers async.

## Vereditos
- MORTA (apagar): /fiscal/cfop*, /fiscal/retencao*, /fiscal/nfe*, POST /fiscal/nfse, GET/PATCH /fiscal/nfse/{id}, /nfse/{id}/danfse, /nfse/emitir, /nfse/cancelar, /nfse/retencoes/competencia, /fiscal/sped*, /obrigacao/atrasadas (como está), /fiscal/das (POST/GET/competencia/calcular/receita-12-meses), /fiscal/suframa*, /fiscal/stats, nfse_entrada legadas (feito), relatorios /orcamentos ×3, /custeio ×5, /bi/overview, /bi/dashboards, /bi/profitability, ged POST /financial/nfse/emitir, /financial/headcount.
- VIVA (corrigir): /fiscal/ncm* (clássico), GET /fiscal/nfse, /obrigacao (POST/GET), /calcular/simples|lucro-real|comparativo|verificar-limite|retencoes-nfse, /fiscal/dashboard, nfse-entrada (GET, pdf), relatorios orcamentos-kv, guias-do-mes, *pdf, dashboard, ged GET /nfse, /nfse/dashboard, /contracts*, /bidding/dashboard, /bi/dashboard, overview stats ×4.
- LIGAR: GET /nfse-emitida/{chave}/danfse (botão DANFSe), /obrigacao/pendentes, /obrigacao/{id} PATCH (dar baixa em obrigação), /das/faixas, relatorios liminares (após unificar), parcelamentos, contas-receber/contas-pagar/fornecedores (aging por competência), apuracao-lucro-real, dre/mensal, balanco-patrimonial, /bi/kpis, /fiscal/stats-real.
- INTERNA: resumo-fiscal, balancete-real/balancete, painel-fiscal, tributos, fluxo-caixa, dre, cashflow/forecast.

Números: 127 rotas únicas · VIVA 34 · LIGAR 18 · INTERNA 9 · MORTA 66. Postgres UTC, container −04. nfse_emitidas_nacional 112 (R$ 2.228.917,40); nfse_tomadas_nacional 322; fiscal_obligations 63 (28 pendentes, 19 vencidas).
