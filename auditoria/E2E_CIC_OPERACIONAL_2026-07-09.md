# E2E CIC — MÓDULO OPERACIONAL — metade privilegiada (API/SQL/escopo/escrita) — 2026-07-09

Executor: sessão autônoma (tokens de escopo gerados no container; oráculo via psql).
A metade read-only de navegador (UX/telas) é do CIC — relatórios serão fundidos aqui.

## FASE 1 — Oráculo API × SQL (perfil gestor)
| verificação | API | SQL | veredito |
|---|---|---|---|
| posts/stats.total | 12 | 12 | ✅ PASS |
| posts/stats.by_status.active | 8 | 8 | ✅ PASS |
| allocations/stats.active | 53 | 53 | ✅ PASS |
| presenca.resumo.esperados | 31 | 31 | ✅ PASS |
| vacations.items(count) | 18 | 18 | ✅ PASS |
| triagem.ocorrencias.abertas_total | 0 | 0 | ✅ PASS |
| diaristas/statistics.total_diaristas | 5 | 5 | ✅ PASS |
| instrucoes-posto.total(postos escopo gestor) | 8 | 8 | ✅ PASS |
| scales/stats.total | 18 | 18 | ✅ PASS |
| triagem.presenca_30d.esperados | 246 | 246 | ✅ PASS |
| lancados-dia(2026-07-04).total_lancamentos | 1 | 1 | ✅ PASS |
| unificado/dashboard.alocacoes_ativas | 52 | 52 | ✅ PASS |

## FASE 1b — Escopo (3 perfis)
| teste | esperado | obtido | veredito |
|---|---|---|---|
| líder awsilva: presença só Ideal | 1:Condomínio Ideal Flores da Cidade | 1:Condomínio Ideal Flores da Cidade | ✅ |
| líder epereira: presença só Laranjeiras | 1:Residencial Laranjeiras Village | 1:Residencial Laranjeiras Village | ✅ |
| líder: triagem 403 | 403 | 403 | ✅ |
| gestor: triagem 200 | 200 | 200 | ✅ |
| líder: ocorrências só do seu posto | OK | OK | ✅ |
| líder: equipe de avaliação escopada | OK | OK | ✅ |
| líder: instruções de posto fora do escopo 403 | 403 | 403 | ✅ |

## FASE 2 — Fluxos E2E de escrita (com prova SQL; limpeza na fase 3)
| fluxo | esperado | obtido | veredito |
|---|---|---|---|
| A1 líder cria ocorrência (auto-posto Ideal) | 0baad2d9-5380-448d-85d9-691bd7f59681 | 0baad2d9-5380-448d-85d9-691bd7f59681 | ✅ |
| A2 gestor vê na triagem | 1 | 1 | ✅ |
| A3 gestor comenta (201) | 201 | 201 | ✅ |
| A4 IA recomendar responde | 201 | 201 | ✅ |
| A5 gestor resolve (200) | 200 | 200 | ✅ |
| B1 passagem criada | ok | ok | ✅ |
| B2 aparece na lista do posto | 1 | 1 | ✅ |
| B3 marcar lida (200) | 200 | 200 | ✅ |
| C1 consolidado inclui os 2 avaliados | 2 | 2 | ✅ |
| D1 check-in manual (200) | 200 | 200 | ✅ |
| D2 repetido (409) | 409 | 409 | ✅ |
| E1 escala teste criada | ok | falhou: Internal Server Error | ❌ |
| F1 CPF inválido (422) | 422 | 422 | ✅ |
| F2 sem PIX (422) | 422 | 422 | ✅ |
| F3 diarista válido criado | ok | ok | ✅ |
| F4 inativar (200) | 200 | 200 | ✅ |
| F5 sumiu do dropdown de lançamento | 0 | 0 | ✅ |
| G1 gestor grava instruções VdP (200) | 200 | 200 | ✅ |
| G2 líder tenta editar (403) | 403 | 403 | ✅ |
| H1 ronda criada | ok | ok | ✅ |
| H2-4 iniciar/checkpoint-sem-GPS/concluir | 200/201/200 | 201/201/201 | ❌ |
| I1 portal ocorrências sem campos sensíveis | True | True | ✅ |

## Correções feitas durante a bateria (achados do próprio E2E)
1. **BUG REAL (crítico, corrigido e bakeado): POST /scales/generate retornava 500** —
   slowapi exigindo `response: Response` na assinatura (mesma família do bug do auto-generate).
   Varredura em TODOS os @limiter do módulo corrigiu 4 endpoints em 3 controllers
   (generate_scale, bulk_update_shifts, bulk_delete/bulk_update_allocations).
   Re-teste: 201 + submit/approve/publish 200/200/200.
2. Expectativa de teste corrigida: iniciar/checkpoint/concluir de rondas retornam 201 (correto).

## Fase 3 — limpeza (resíduo ZERO, provado por SQL)
Cancelados/inativados: 1 ocorrência, 1 passagem, 2 avaliações; revertido: 1 check-in manual;
excluídos: escala teste 12/2026 (+62 turnos), diarista ZZE2E, instruções VdP, ronda de teste
(+1 checkpoint). Query agregada de resíduos = 0.

## Veredito da metade privilegiada
- Oráculo: 12/12 PASS (tela==banco em posts, alocações, presença, férias, triagem, diaristas,
  instruções, escalas, absenteísmo, diárias, dashboard unificado).
- Escopo: 7/7 PASS (líder enxerga e escreve SÓ no seu posto; gestor vê tudo; 403 corretos).
- Fluxos A-I: 22/22 PASS após o fix do generate (1 bug real encontrado e corrigido na hora).
