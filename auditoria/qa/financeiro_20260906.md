# Financeiro — fechamento 06/09/2026 (etapa 2 do plano de conclusão)

## Veredito
| Lente | Status | Evidência |
|---|---|---|
| DADO | ✅ | 9 oráculos do financeiro verdes: extrato, recebíveis, balanço, contábil_fecha, comprovante_folha, vavt_multibanco, medida_fluxo, u2_financeiro, dedup_inter. `fechado_financeiro.py` 6/6 |
| TELA | ✅ | 12 telas-chave abertas no navegador (`/redesign/financeiro?t=<slug>`), logado como jjesus: balanço 27 valores, balancete 105, pagar 205, receber 50, fiscal 330, conciliação 96, diaristas 28, DRE 20; 0 respostas 5xx na segunda passada (1 × 502 transitório na primeira) |
| CÓDIGO | ✅ | 3 arquivos tocados (inter_sync_service, financial/tasks, oráculo de recebíveis); os 9 oráculos antes e depois; ruff sem erro novo |

## O que estava errado e foi consertado
1. **Extrato do Inter parado desde 23/08.** O INSERT do sync citava a constraint `uq_inter_transactions_dedup`, apagada pela migration 774dcd61a5fe; o beat das 08:00 dizia "succeeded" com 0 sincronizadas e o erro engolido em `erros`. Divergência R$ 5.260,83 = a soma exata do extrato vivo entre 24/08 e 04/09. Fix no alvo do ON CONFLICT; sync de 16 dias: 136 linhas, 0 erros; oráculo: "R$ 1.803,13 = saldo do próprio banco". A task agora LEVANTA quando `erros` vem preenchido.
2. **Oráculo de recebíveis acusava 3 títulos "dobrados".** Agrupava por (cliente, valor): condomínio que paga igual todo mês somava dois meses. Os vínculos estavam certos nas duas direções. GROUP BY por título.
3. **Seção contábil sumiu do redesign** por causa da quarentena (`fin_cost_centers` citada pelo builder). 79 tabelas citadas por código vivo devolvidas ao `public`; balanço resolve; 172 seguem em quarentena.

## O que o mapa chamava de 🟡 e é 🟢
- **VT/VR (item 1 da fila):** o beat roda de hora em hora e devolve `{'novos': 0, 'ja': 4}` — ele encontra tudo já programado porque você clica "Programar VT+VR agora" antes dele. Funciona; o botão é atalho, não substituto.
- **Auto-baixa (item 2):** o beat das 08:30 roda e sucede; o `propor_baixa_pendentes` está atrás de `CONECTA_PROPOR_BAIXA=0` **por decisão** (celery_app.py). Os 36 rascunhos de baixa são de 13/08, quando esteve ligado.

## Achados que ficam com você
- **32 débitos do Inter de 24/08 a 06/09 (R$ 13.605,33) entraram agora e estão `pendente` de classificação** — são os 13 dias em que o extrato não sincronizou. A tela "Classificar transações" (`just-classificar`) é o caminho.
- `conciliar_saidas` nunca casa nada automaticamente (0 de 1.654, "sem match ou ambíguo"): o casamento exato CNPJ+valor+data não encontra par porque os pagamentos saem pelo fluxo OTP que já grava a linha. Não é defeito; é que a auto-baixa por extrato não tem o que fazer neste desenho.

## Não coberto
- As 17 telas de formulário do financeiro sem vigia (cashflow-sync, gerar-parcelas, nfse-entrada-*, payables-auto-criar, custo-*, estoque-saida, just-*, orcamento-kv, pricing-calcular) foram abertas mas **não submetidas** — 💰 nunca em happy-path. Continuam sem oráculo.
- Asaas sem saldo de abertura no corte (oráculo "NÃO COBERTO"); Cora sincroniza às 08:10.
- Durabilidade: os 3 arquivos estão nos containers por `docker cp`; o bake automático recusa enquanto houver WIP alheio em `backend/`.

## 2ª passada (07/09)
- **Oráculo novo `test_oraculo_fin_visao`** vigia a Visão Geral: MRR, saldo da conta principal e médias de 90 dias. Três verdes; a média de entradas diverge 5,8% do recálculo sem transferências (235.464 × 249.873): definição do builder a apurar, fica vermelha até isso.
- Os 32 débitos do Inter sem classificação exigem categoria por contraparte (ação "Classificar saídas"): é sua.


## 3ª passada (07/09, madrugada) — inventário de KPIs de todos os builders

| Achado | Medido | Ação |
|---|---|---|
| Apuração Lucro Real tributava o capital social | tela: Receita líquida R$ 500.000,00 · IRPJ+CSLL R$ 146.000 · razão: 1 lançamento C 3.1.1.01 | 7 leitores movidos para `plano_contas_caixa.saldo()` (plano 13/08); `checar_dominio` proíbe `conta_credito LIKE '3.1.1` e `conta_debito LIKE '4` em modules/ |
| DRE mensal / consolidado / Empresas no plano velho | receita 0 ou lida como custo | idem; DRE mensal 2026 agora: jan 264,6 mil … set |
| BI: Margem bruta 86,7% | `src_folha` = "última competência" = 1ª parcela do 13º (2026-11, R$ 35.864) | `src_folha` ignora `13O-%` e competências futuras → folha ago R$ 112.411,57, margem 58,3% |
| MRR em duas fontes | billing_rules 270.586,96 × contracts 269.700,06 | registrado; definição é do dono |
| Agosto faturado pela metade | jul 269,9 mil × ago 175,1 mil (competência) | Jordan confere emissão |
| Oráculo `test_oraculo_kpis_telas` | 32 KPIs de cabeçalho, 32/32 ao centavo | roda toda noite |

Ficam fora do oráculo (não é SQL escalar): cobertura de postos (repo), presença (serviço), DSO/DPO, margens da DRE, tributos por CNPJ. Continuam sem vigia.

## 4ª passada (07/09) — fechamento contábil do razão

| Achado | Medido | Ação |
|---|---|---|
| Fechamento parado desde 11/08 | último `nfse_emitida` 11/08 09:00; task SUCCESS com `razao: {null, null}` | `_post` aceita data em texto; `fechar_grupo` ok=False ⇒ task falha |
| Purge apagaria jan–jul | 182 lançamentos, R$ 1,96 mi, sem repost possível | purge só ≥ `CORTE_CONTABIL` |
| Agosto fora do razão | 0 notas/folha/tomadas | fechado: 13 notas, 54 holerites, 20 tomadas; `notas_sem_razao = 0` |
| Recebimentos em 4.9.9.01 | 13, R$ 132.898,35 (categoria `recebimento_cliente` ignorada) | extrato lê `coalesce(justificativa, category)`; `reclassificar_transitorias` no fechamento |
| Saídas justificadas presas em 5.9.9.01 | 25 (VT/VR diaristas etc.) | reclassificadas pela regra do plano |
| Saídas sem justificativa | 165, R$ 142.353,06 (Cora, ago) | do Jordan: justificar; oráculo não cobra o que não tem regra |
| `test_oraculo_contabil_fecha` | 6/6 | +passo 6 (transitória com regra = 0) |
