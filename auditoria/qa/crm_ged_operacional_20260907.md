# CRM, GED e Operacional — fechamento 07/09/2026 (etapa 5 do plano de conclusão)

## Veredito
| Módulo | DADO | TELA | CÓDIGO |
|---|---|---|---|
| CRM / agentes | ✅ 23 oráculos: 21 verdes, `papel_fornecedor` BLOQUEADO (provedor de LLM sem crédito), `canal_ferramentas` corrigido na etapa 3 | ✅ leads (200 valores), propostas (35), clientes (25), pipeline; 0 × 5xx | ✅ registro de tools idempotente (etapa 3); `test_u2_crm` verde |
| GED / GEDEON / Assinatura | ✅ 15 oráculos verdes | ✅ kits (746 números), visão, certidões; 0 × 5xx | ✅ `test_u2_ged` verde; 79 tabelas devolvidas da quarentena (nenhuma do GED vivo) |
| Operacional | ✅ 17 oráculos verdes; `fechado_operacional` no gate semanal | ✅ postos (9 ativos), escalas, diaristas, rondas (556 números), visão; 0 × 5xx | ✅ `test_u2_operacional` verde; **read-only para agentes — nada foi editado** |

## O que o mapa chamava de 🟡 e o que é de verdade
- **Precificação → proposta (item 5 da fila).** `ProposalService` já chama o `PricingEngine`, mas a proposta que você cria de verdade nasce **por itens** (ação `criar-orcamento` / tool `criar_orcamento`: quantidade × preço unitário) e item não carrega custo nem headcount. `margin_percent` e `cct_breakdown` nulos nas 35 propostas não é fio solto: é dado que o fluxo por itens não tem. Para preencher honestamente, ou o item ganha `custo`, ou a proposta nasce de uma simulação de posto (`simular_preco` → `pricing_simulation_id`). É decisão de produto, não conserto.
- **Licitações, Recrutamento, Jurídico, Campo** (etapa 6): ficam até você dizer se são negócio. Números no mapa.

## Achados que ficam com você
- **Provedor de LLM sem crédito (402)** desde pelo menos 06/09: bloqueia `papel_fornecedor`, o oráculo 6 do RBAC, o redator do proativo e qualquer turno do José Luís que precise gerar texto. É saldo, não código.
- **Consultor escopado (chat dos consultores) só volta ao ar no bake** (etapa 3).

## Não coberto
- 62 telas do CRM e 17 do GED sem oráculo continuam sem oráculo; abri 13 telas e não submeti formulário nenhum (nada de envio a lead/cliente).
- As 62 rotas de escrita órfãs do Operacional são relatório, nunca wiring (regra da casa).
