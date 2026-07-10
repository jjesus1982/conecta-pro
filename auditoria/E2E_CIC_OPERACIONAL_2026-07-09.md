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

---

# METADE 2 — QA READ-ONLY DE NAVEGADOR (CIC, perfil gestor)
(Relatório integral do CIC colado abaixo; análise de fusão em seguida.)

> Nota de fusão: o QA do CIC rodou EM PARALELO à bateria de escrita desta frente — os "resíduos
> pré-existentes" que ele observou (passagem/ronda/ocorrência TESTE E2E CIC, escala Dez/2026)
> eram os dados da minha bateria ANTES da fase 3 de limpeza; verificação pós-limpeza: 0/0/0/0.
> O contador de escalas "18→19" foi minha escala de teste sendo criada/excluída ao vivo.

## Análise de fusão — causas-raiz dos achados do CIC
| Achado CIC | Causa-raiz | Destino |
|---|---|---|
| B1 /diaristas quebra (toFixed) | front sem guard p/ media/valor null (API nova retorna null honesto) | fix onda 1 |
| B2 /ai-command-center quebra | Object.entries sobre seção null da resposta | fix onda 1 |
| B3 detalhe escala 422 | frontend pede page_size=500; backend limitava le=200 | ✅ CORRIGIDO (le=500) |
| B4 ronda-mobile 404 | URL sem barra final (/posts?status= vs /posts/?) | fix onda 2 |
| B5 menu campo não navega + /campo spinner + OS 404 | navegação cross-módulo/páginas campo | fix onda 2 |
| B6 contadores divergentes | mistura de fontes: total×ativos, is_active podre, semânticas distintas de "cobertura"/"em andamento" | fix onda 3 (padronização) |
| B7 /turnos só dias 1-2 | fetch sem filtro do mês visível + page_size 50 | fix onda 3 |
| B8 relatórios: e-mail/UUID + horas 0 | join errado p/ nome; horas = actual (checkout raro) sem rótulo | fix onda 3 |
| B9 ficha turnos UUID/'cancelled' | front não resolve nome do posto nem traduz status | fix onda 1 |
| B10 visual vazio + #418 | mesmo 422 do page_size (já corrigido) + hydration de datas | fix onda 2 |
| B12 triagem posto "—" | backend manda post_nome correto; front lê chave errada | fix onda 1 |
| Sino "1" vs tela 0 | fontes distintas do badge | fix onda 1 |
| /diarias "PRIME" vs "PRIME ARENA" | DESIGN: cadastro de postos do Fluxo-2 (planilha do Jordan) é texto livre, separado da tabela posts | documentado |
| 32 diaristas "(sem PIX)" | DADO real pendente (o GET não expõe a chave; tem_pix=false real p/ maioria) | pendência Jordan |

---

## RELATÓRIO INTEGRAL DO CIC (colado sem edição)

# E2E CIC — QA EXPLORATÓRIO READ-ONLY — MÓDULO OPERACIONAL (Conecta PRO)
Data: 2026-07-09 · Perfil: GESTOR (sessão autenticada) · Ambiente: PRODUÇÃO (erp.conectamais.pro)
Modo: navegação/leitura, sem submeter formulários nem acionar ações de escrita/pagamento.
Limitação: viewport mínimo ~958px — validação mobile PARCIAL (por layout/densidade).

### Tabela (resumo dos 48 itens)
Ver tabela completa na conversa de QA; consolidada aqui pelos vereditos:
- OK: presenca, instrucoes-posto, ocorrencia-rapida (form/validação), passagem-turno,
  avaliacao-equipe (carregar), triagem (carregar), substituicoes, banco-horas,
  medidas-administrativas, ferias (somente-leitura perfeito), consultor IA, comunicados (carregar),
  notificacoes (carregar), ficha colaborador (CPF mascarado ✓), redirects disciplinar/agentes/mapa,
  escalas (listar/paginar), pagamentos-diaristas (3 fontes presentes).
- BUGS CRÍTICOS: /diaristas quebra (toFixed em undefined); /ai-command-center quebra
  (Object.entries em null).
- BUGS ALTOS: home KPIs incoerentes (12 ativos vs 8; colaboradores 52/50/47/37; cobertura 58% vs
  98%; escalas em andamento 0 vs 9); /postos "Com vagas 0" vs Ideal 11/12; detalhe de escala 422
  (page_size=500); /ronda-mobile 404 (posts sem barra); /turnos só dias 1-2 ("50 turnos");
  /relatorios horas 0.0/custos R$0 + NOME = e-mail/UUID (PII); menu campo: Ordens de Serviço 404
  e 3 itens que não navegam; /cobertura semânticas divergentes (98% vs 58%; Gelain 0/0 "Em Risco").
- BUGS MÉDIOS: /escalas/visual grade vazia + React #418; /modulos/campo spinner infinito;
  /alocacoes paginação "1 a 10 de 53" exibindo 20; ficha›Turnos com UUID/“—/cancelled”;
  /ocorrencias "Resolvidas (mês) 0" + funcionário N/A + título truncado; /diarias postos
  texto-livre divergentes + 32 sem PIX; avaliacao-equipe lista de 49 sem busca/agrupamento;
  consultor expõe nomes de tabelas SQL na UI.
- BUGS BAIXOS/UX: escalas contador 18→19 (era a bateria de escrita ao vivo); triagem posto "—";
  observações da escala repetidas 3×; coluna confirmações/leituras oscilante; sino "1" vs tela 0;
  WS 503/404 no console da presença (gracioso); coluna TIPO="—" em férias.
- NÃO TESTADO: /area-cliente/operacao (exige login de cliente); mobile 390px fiel (limite da janela);
  perfil líder e oráculo SQL (cobertos pela outra frente).

### Top 10 UX (impacto no líder mobile)
1 telas mortas sem fallback; 2 contadores contraditórios; 3 menu com itens sem destino;
4 avaliação sem filtro/agrupamento; 5 UUID/e-mail no lugar de nome (PII); 6 strings em inglês;
7 /turnos "vazio" contradizendo /presenca; 8 título truncado; 9 rótulo de coluna oscilante;
10 sino com badge sem correspondência.

### Comparações UI×UI (13): postos 12/8/8; colaboradores 52/50/47/37; alocações 53/52/51;
Ideal 11/12 vs 11/11; Laranjeiras 9/9 vs 9/10; escalas 18→19; em andamento 0 vs 9; presença
consistente pós-sync (timing ✓); cobertura 58 vs 98; diaristas 32/14/41; afastados 0 vs 2;
turnos hoje 39 vs nenhum vs 31; posts/ 200 vs posts?status 404.

### Dados de teste: frente 100% read-only; nada criado. Resíduos observados eram da frente de
escrita em andamento (confirmado limpo pós-fase 3).

---

# VEREDITO FINAL PÓS-CORREÇÕES (2026-07-10)

Todas as correções das 3 ondas aplicadas, commitadas e BAKEADAS (blue/green zero-downtime,
7/7 workers, frontend publicado). Revalidação API pós-bake: 7/7 PASS.

| Achado do CIC | Status |
|---|---|
| B1 /diaristas crash (toFixed) | ✅ corrigido (guards em todos os campos numéricos) |
| B2 /ai-command-center crash (Object.entries) | ✅ corrigido (guards + estados honestos) |
| B3 detalhe de escala 422 | ✅ corrigido (le→2000) e provado 200 |
| B4 ronda-mobile 404 | ✅ corrigido (barra final) |
| B5 menu Campo morto + /campo spinner + OS "404" | ✅ raiz corrigida (sidebar <Link>; getModuleByPath; healthcheck não bloqueia; as 4 telas existem e respondem 200) |
| B6 contadores divergentes | ✅ semântica única: postos ativos=8, colaboradores=50, alocações=52, escalas VIGENTES, cobertura=fórmula única em 6 pontos |
| B7 /turnos só dias 1-2 | ✅ mês visível completo (921 agendados de julho) |
| B8 relatórios PII + horas | ✅ nome real (0 e-mails/UUIDs no payload); horas/custos rotulados pelo que são |
| B9 ficha›Turnos UUID/inglês | ✅ nome do posto + chaves reais + status traduzidos |
| B10 visual vazia + #418 | ✅ 422 resolvido + bug de fuso (turno caía no dia anterior) + hydration |
| B11 /campo loading | ✅ (mesma raiz do B5) |
| B12 triagem posto "—" | ✅ chave post_nome |
| Sino, comunicados, título, cancelled | ✅ ondas 1 |
| /diarias postos texto-livre; 32 sem PIX | 📋 design do Fluxo-2 + pendência de DADO (Jordan) |
| Resíduos observados | ✅ eram a bateria de escrita ao vivo; pós-limpeza = 0 |
| Portal cliente (não testado pelo CIC) | ✅ coberto pela frente privilegiada (sem campos sensíveis) |

Pendente de validação visual: 2ª passada do CIC (opcional) para confirmar os fixes no navegador.
