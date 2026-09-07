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
