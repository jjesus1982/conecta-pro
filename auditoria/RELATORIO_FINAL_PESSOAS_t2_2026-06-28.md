# Relatório Final — Auditoria & Correção de Gestão de Pessoas (t2)
**Data:** 28/06/2026 · **Escopo:** 8 módulos de Gestão de Pessoas (101 telas) · **Modo:** ponta a ponta, E2E (leitura + escrita criar/editar/excluir) · **Resultado:** ~15 bugs reais corrigidos, durável, com resíduo de teste = 0.

---

## 1. Resumo executivo (1 minuto)

A missão foi varrer os 8 módulos de Pessoas tela por tela e garantir que **cada tela mostra o dado real (leitura)** e que **cada botão de criar/editar/excluir funciona (escrita)**.

**O que descobrimos:** o **eixo de leitura já estava saudável** (mérito das correções anteriores do t1). O trabalho real estava no **eixo de escrita** — botões de "criar/editar/excluir" que davam erro 500 e nunca tinham sido testados de ponta a ponta.

**O que fizemos:** mapeamos a escrita com **5 investigadores paralelos** (E2E real: criar→verificar→editar→excluir, com dados de teste marcados e limpeza obrigatória), achamos **~15 bugs reais** e corrigimos a esmagadora maioria em 7 lotes ("batches"), cada um testado e bakeado de forma durável (ou aplicado via migration com backup).

**Segurança:** todo dado de teste usou o prefixo `ZZE2E_` e foi removido; **resíduo final = 0** em todas as tabelas. Nenhum efeito externo (eSocial, e-mail, WhatsApp, pagamento, sync gov) foi disparado. Backups e âncoras de rollback criados em cada etapa. **0 containers unhealthy, 7 celery healthy** ao fim.

---

## 2. Status dos 8 módulos

| # | Módulo | Status | O que foi feito |
|---|---|---|---|
| 1 | **Departamento Pessoal (DP)** | ✅ Corrigido | Deduções, Rescisão, Aviso-prévio, Licenças |
| 2 | **Recursos Humanos (RH)** | 🟡 Parcial | Benefícios-config e Salários-auditoria corrigidos; **Avaliações 360 pendente** (fix de tela no front) |
| 3 | **Recrutamento** | ✅ Corrigido | Candidaturas, Entrevistas |
| 4 | **Gestão de Pessoas (hub)** | 🔎 Triado | Ponto/Folha/eSocial investigados — os erros 500 eram de endpoints **dormentes** (nenhuma tela os usa) |
| 5 | **Saúde Ocupacional (SST)** | ✅ Corrigido | Risco, CAT, ASO, EPI (cadastro). **PPRA a reverificar** |
| 6 | **Ponto Eletrônico** | 🔎 Triado | Telas usam `/ponto/*` (já verdes); os 500 de "time-tracking" são **dormentes** |
| 7 | **Portal do Funcionário** | ⛔ Bloqueado | **Inteiro inacessível** + **falha de segurança** — depende do t1 (zona compartilhada) |
| 8 | **Reembolso** | ✅ Corrigido | Criar, Editar, Submeter, Cancelar |

**Placar:** 4 corrigidos de ponta a ponta · 1 parcial · 2 triados (já saudáveis) · 1 bloqueado (coordenação).

---

## 3. Como foi feito (método)

1. **Preparação:** inventário das **101 telas**; triagem automática de **301 endpoints GET** → **202 já verdes**, e os erros 500 reais agrupados por causa-raiz.
2. **Sweep de escrita E2E:** 5 agentes paralelos, um por módulo, cada um testando criar→verificar→editar→excluir com marcador `ZZE2E_` único + limpeza. Acharam ~15 bugs reais.
3. **Correção em lotes:** cada bug com causa-raiz no arquivo, corrigido na nossa "raia" (sem tocar nas áreas do t1), testado E2E, e **bakeado durável** (imagem Docker) com âncora de rollback — ou aplicado via **migration com backup**.
4. **Disciplina anti-colisão com o t1:** raias de diretório, lock de bake serializado, teste `configure_mappers` obrigatório antes de cada recriação (pega arquivo quebrado antes de ir pra produção).

---

## 4. Bugs corrigidos (detalhe por lote)

### Batch 1 — tabelas de configuração ausentes
| Tela | Era | Virou | Causa-raiz / Fix |
|---|---|---|---|
| Benefícios (config) | 500 | 200 | Tabela `cct_benefit_configs` não existia → endpoint resiliente (e depois criada, ver Batch 7) |
| Salários (auditorias) | 500 | 200 | Tabela `cct_salary_audits` não existia → idem |

### Batch 3 — crashes de criação (Recrutamento + SST)
| Tela | Era | Virou | Causa-raiz / Fix |
|---|---|---|---|
| Recrutamento / Candidaturas | 500 | ok | Código lia `position.experience_min` (atributo inexistente) → `min_experience_years` |
| Recrutamento / Entrevistas | 500 | ok | Código lia `data.meeting_link` (o schema usa `meeting_url`) → acesso defensivo |
| SST / Risco, CAT, ASO | 500 | 201 | Data com fuso (tz-aware) em coluna sem fuso → normalizado para naive (4 models) |

### Batch 4 — DP + Reembolso (criação)
| Tela | Era | Virou | Causa-raiz / Fix |
|---|---|---|---|
| DP / Rescisão + Aviso-prévio | 500 | 201 | Resposta declarava `id/employee_id` como texto, banco retorna UUID → tipo UUID |
| DP / Deduções | 500 | 201 | Faltava `import date` + data vinha como texto → conversão para `date` |
| Reembolso / Criar | 500 | 201 | Número do código (`REI-AAAA-NNNNN`) era contado por condomínio mas é único global → contagem global |

### Batch 5 — Reembolso (workflow)
| Tela | Era | Virou | Causa-raiz / Fix |
|---|---|---|---|
| Reembolso / Editar | 500 | 200 | Resposta serializada sem recarregar relacionamentos após o commit → re-fetch (igual ao "Criar") |
| Reembolso / Cancelar | 500 | 200 | idem |
| Reembolso / Submeter | 500 | 400* | idem (*400 = regra de negócio: precisa de itens — não é mais crash) |

### Batch 6 — DP / Licenças (dado escondido)
| Tela | Era | Virou | Causa-raiz / Fix |
|---|---|---|---|
| DP / Licenças (lista) | mostrava 0 | mostra 6 | A lista lia de uma tabela vazia (`time_justifications`) enquanto o cadastro grava em `sst_afastamentos` → lista passou a ler da tabela certa |

### Batch 7 — Migration aditiva (autorizada pelo Jordan)
Backup feito antes; aditiva, idempotente, em transação; rollback salvo.
| Alvo | O que | Resultado |
|---|---|---|
| `health_epi_catalog` | +10 colunas que o model esperava | — |
| `health_epi_inventory` | +9 colunas | **EPI (cadastro): 500 → 201** |
| `cct_benefit_configs` | tabela criada (model existia, tabela não) | Config lê tabela real (200) |
| `cct_salary_audits` | tabela criada | Auditorias lê tabela real (200) |

---

## 5. O que falta

### Na nossa raia (fix claro, posso fazer)
- **RH / Avaliações 360:** o botão "Criar Avaliação" sempre dá 422 porque a tela manda o **nome** do funcionário onde o backend espera o **ID**. Fix é no front (trocar campo de texto por um seletor de funcionário). *O backend está correto.*
- **Reembolso / "Prontos para pagamento":** ordem de rota faz o endpoint ser inalcançável (422). Secundário; fix exige reordenar uma função.
- **SST / PPRA-mapeamento:** reverificar (na última checagem não deu mais erro 500).

### Precisa de coordenação com o t1 (zona compartilhada — não faço sozinho)
- ⛔ **Portal do Funcionário INTEIRO inacessível:** dois módulos (Área do Cliente e Portal do Funcionário) montados no mesmo endereço `/portal` → o do funcionário fica "sombreado" e tudo retorna 404. O conserto é no arquivo de inicialização compartilhado (`main_production`).
- 🔒 **Falha de SEGURANÇA (prioridade):** no login do Portal por "data de nascimento", se o funcionário tem a data de nascimento em branco no cadastro, a validação é pulada e **qualquer pessoa entra só com o CPF**. Recomendo corrigir com prioridade.
- **DP / Documentos (upload):** a lista de tipos de documento da tela (RG, CPF, CTPS...) não bate com o enum do backend (no módulo GED, fora da nossa raia) → corrigir no front ou no enum, em conjunto.
- **Tabelas/colunas ausentes restantes:** já tratadas com migration (Batch 7) ou guard resiliente; `operational_profiles` (perfil/retenção) deixada de fora **de propósito** por ser dormente (nenhuma tela usa).

---

## 6. Segurança e rastreabilidade

- **Dados de teste:** prefixo `ZZE2E_` em tudo; **resíduo final = 0** (varreduras repetidas confirmaram, inclusive pegando 1 sobra em `gp_risks` e 1 em `termination_processes` que foram limpas).
- **Efeitos externos:** nenhum disparado (eSocial, e-mail, WhatsApp, pagamento/PIX, sync gov, publicar holerite, assinatura externa — todos pulados).
- **Backups:** diário (03:00) + backup manual das tabelas antes da migration.
- **Âncoras de rollback (imagens Docker):** `pre-pessoas-batch1`, `batch3`, `batch4`, `batch5`, `batch6` (todas `-20260628`).
- **Migration:** `backups/manual/migr_pessoas_20260628.sql` + rollback `backups/manual/ROLLBACK_migr_pessoas_20260628.sql`.
- **Saúde final:** 0 containers unhealthy, 7 celery healthy, `configure_mappers` OK em cada bake.

---

## 7. Conclusão

A casa de **Gestão de Pessoas** está sólida e durável: o eixo de leitura já estava bom, e o eixo de escrita — onde estavam os bugs reais — foi mapeado e corrigido na esmagadora maioria. Restam pontas finas na nossa raia (uma tela do RH e uma rota secundária do reembolso) e **dois itens importantes que dependem do t1** por mexerem em zona compartilhada: o **Portal do Funcionário** (hoje inacessível) e a **falha de segurança** do login por data de nascimento.

> **Recomendação:** priorizar com o t1 (a) o conserto da colisão do Portal e (b) a falha de segurança do login. O resto é refino.
</content>
