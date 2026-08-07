# Organograma do Conecta PRO — MEDIDO (2026-08-07)

Levantado do sistema, não de memória: rotas montadas em `main_production:app`, diretórios
reais, slugs do front, builders do redesign e tabelas compartilhadas.

**Números-âncora:** 59 prefixos de rota · 33 slugs no clássico · 41 builders no redesign ·
~4.170 rotas (path+método).

---

## 1 · Menus → módulos → onde o código mora

| Menu | Módulo | Slug (front) | Prefixo de rota | Código | Rotas |
|---|---|---|---|---|---:|
| **Negócios** | CRM | `crm` | `crm` | `modules/crm` | 245 |
| | Marketing | `marketing` | `marketing` | `modules/crm` (marketing) | 20 |
| | Licitações | `licitacoes` | `bidding` | `modules/bidding` | 87 |
| | Serviços | `servicos` | `services` | `modules/services` | 63 |
| **Gestão de Pessoas** | Departamento Pessoal | `dp` | `people-management` | `modules/people_management` | 697¹ |
| | Recursos Humanos | `rh` | `people-management/hr` | idem | ¹ |
| | Gestão de Pessoas | `gestao-pessoas` | `people-management` | idem | ¹ |
| | Operacional | `operacional` | `operacional` | `modules/operacional` | 301 |
| | Saúde Ocupacional | `saude-ocupacional` | `health-occupational` | `people_management/sst` | 40 |
| | Ponto Eletrônico | (em `dp`) | `people-management/ponto` | `people_management/ponto` | ¹ |
| | Portal do Funcionário | `portal` | `portal` | `people_management/employee_portal` | 61 |
| | Recrutamento | `recrutamento` | `recruitment` | `modules/recruitment` | 166 |
| **Financeiro, Fiscal e Jurídico** | Financeiro | `financeiro` | `financial` | `modules/financial` | 592 |
| | Fiscal & Contábil | `fiscal` | `government` + `fiscal` | ⚠️ `modules/government_integrations` | 448+22 |
| | Jurídico | `juridico` | `juridico` | `modules/juridico` | 52 |
| | Empresas | `empresas` | `empresas` | `modules/empresas` | 36 |
| **Inteligência & Patrimônio** | BI | `bi` | (builder lê SQL) | — | — |
| | Analytics | `analytics` | `analytics` | `modules/analytics` | 33 |
| | Relatórios | `relatorios` | `reports` | `modules/reports` | 32 |
| | Equipamentos | `equipamentos` | `equipment`+`installations`+`maintenances`+`comodatos` | `equipment_management` | 96 |
| | Suprimentos | `suprimentos` | `financial` (compras/estoque) | `modules/financial` | — |
| | Documentos | `documentos` | `ged` + `document-kits` + `gedeon` | `modules/ged`, `gedeon` | 300 |
| **Sistema** | Configurações | `configuracoes` | `config` | `modules/config` | 47 |
| | Integrações | `integracoes` | `integrations` | `modules/integrations` | 78 |
| | Automações | `automacoes` | `workflows` | `automation/workflow` | 9 |
| | Agendador | `agendador` | `scheduler` | `modules/scheduler` | 26 |
| | Segurança | `seguranca` | `security` | `modules/security_lgpd` | 29 |
| | Assistente IA | `assistente` | `ai` + `consultores` | `modules/ai` | 20 |
| | Aprovações | (só redesign) | `redesign/action` | `ai/.../orquestrador/acoes` | — |
| | Área do Cliente | `area-cliente` | `portal` (cliente) | `modules/client_portal` | — |
| | Meu Espaço | `meu-espaco` | `portal/self-service` | `employee_portal` | — |
| **Sem menu** | Campo | `campo` | `campo` | `modules/campo` | 77 |
| | Reembolso | `reembolso` | `reimbursements` | `modules/reimbursement` | 26 |
| | Homologação | `homologacao` | `people-management` | `people_management` | ¹ |

¹ As 697 rotas de `people-management` cobrem DP + RH + Gestão de Pessoas + Ponto +
Homologação + parte do Portal. **São 5 itens de menu sobre um módulo de código só.**

---

## 2 · ⚠️ O achado que muda o plano de trabalho

**Os 41 builders do redesign — de TODOS os módulos — moram em
`backend/modules/operacional/controllers/redesign_builders/`.** 287 commits ali desde 01/07.

```
redesign_builders/
  crm.py  financeiro.py  fiscal.py  juridico.py  rh.py  documentos.py  bi.py ...
  _fin_bancos.py  _fin_contabil.py  _dp_grupos.py ...
```

**Três consequências:**

1. **"Escrita só no seu módulo" é impossível** para trabalho de redesign. Fechar o CRM
   escreve em `modules/operacional/`. A regra tem de ser reescrita como: *escrita no seu
   módulo **e** no builder do seu módulo dentro de `redesign_builders/`*.
2. **É o ponto de colisão das sessões paralelas.** Três terminais fechando módulos
   diferentes escrevem no mesmo diretório. Commit por pathspec do arquivo do builder, nunca
   do diretório.
3. **É dívida arquitetural.** O builder de cada módulo deveria morar no módulo. Não é para
   corrigir agora — é para saber.

---

## 3 · Acoplamento real (tabelas compartilhadas, sem os builders)

| Par | Tabelas em comum |
|---|---:|
| financial ↔ operacional | 12 |
| operacional ↔ people_management | 10 |
| ai ↔ crm | 7 |
| crm ↔ operacional | 6 |
| bidding ↔ operacional | 6 |
| ged ↔ people_management | 5 |
| bidding ↔ ged | 4 |
| juridico ↔ people_management | 4 |
| financial ↔ integrations | 4 |
| financial ↔ fiscal | 3 |

*(Medição anterior dizia "operacional ↔ people_management: 41" — era artefato dos builders
morarem em operacional. Excluídos, cai para 10.)*

---

## 4 · Ondas — por acoplamento, não por menu

**Menu é organização de tela; acoplamento é o que quebra junto.** Agrupar por menu criaria
onda de 8 módulos (Gestão de Pessoas) que na prática são 1 módulo de código, e separaria
`financial` de `fiscal`, que dividem 3 tabelas e 130 rotas.

| Onda | Módulos | Por quê | Peso |
|---|---|---|---|
| **1** | Operacional + DP/RH/Ponto/Portal | 10 tabelas em comum; escala↔ponto↔folha | 998 rotas |
| **2** | Financeiro + Fiscal + Empresas | 12 e 3 tabelas; 130 rotas fiscais sob `/financial` | 1.098 |
| **3** | CRM + Marketing + Licitações + Serviços | funil→proposta→contrato; bidding↔crm | 415 |
| **4** | Documentos (GED+GEDEON+Kits) + Jurídico | ged↔people_management 5; juridico↔pm 4 | 352 |
| **5** | Equipamentos + Suprimentos + Campo | patrimônio e campo | 173 |
| **6** | Sistema (config, integrações, segurança, agendador, IA) | infra | ~200 |

**Onda 1 e 2 são grandes porque os módulos são grandes** — não dá para encolher agrupando
diferente. O que dá é fatiar *dentro* da onda: a fila do raio-x já vem por área
(`time-bank`, `scales`, `diaristas`…), e cada área é uma iteração.

---

## 5 · Cobertura clássico × redesign (gaps de tela)

**Slug no clássico sem builder no redesign:** `analytics`, `meu-espaco`, `reembolso`,
`suprimentos`.
**Builder no redesign sem slug no clássico:** `aprovacoes` (Central de Rascunhos, tela nova).

*(`dp`↔`departamento_pessoal`, `gestao-pessoas`↔`gestao_de_pessoas`,
`area-cliente`↔`area_do_cliente`, `portal`↔`portal_do_funcionario` são o mesmo, com nomes
diferentes nos dois lados — normalizar seria bom.)*
