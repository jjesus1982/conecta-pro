# Ponderação — "1 agente especializado por módulo + skills" (Conecta PRO)
*2026-06-30 — cruza a auditoria profunda de Gestão de Pessoas com o catálogo real da Avora (1.161 skills).*

## 1) O que a Avora é (de verdade, logado)
Marketplace de **frameworks de prompt** ("Validated structures… Copy, customize, and deliver") — **1.161 skills** em 13 temas:

| Skills | Tema | Encaixe Conecta PRO |
|---|---|---|
| 245 | Operations, HR & Management | RH/Operações — **parcial** (SOP, OKR, onboarding *genéricos*) |
| 221 | Marketing, Sales & Advertising | **Comercial/José Luís — forte** |
| 210 | Content & Copy | Comercial/Marketing — **forte** |
| 133 | Finance, Legal & Compliance | Financeiro/Fiscal — **parcial** |
| 90 | Routine, Tasks & Organization | Produtividade geral |
| 55 | Legal & Law Practice | Jurídico/Contratos — **bom** |
| 44 | Product, E-commerce & SaaS | baixo |
| 38 | Career, Education & Personal Brand | baixo |
| 33 | SEO, Analytics & Data | BI — **parcial** |
| 26 | Leadership & Teams | Gestão/Liderança — bom |
| 24 | Design & Branding | Marketing |
| 22 | Code, Dev & Automation | Dev — fraco (genérico) |
| 20 | Creative Direction | Marketing |

### Veredito honesto sobre a Avora
**São skills de negócio/marketing/conteúdo — NÃO de domínio técnico do nosso ERP.** Onboarding ali = "Welcome Email / Onboarding Checklist" genérico, **não** admissão CLT + eSocial S-2200 + ASO admissional. Não há nada de **folha CLT/CCT, ponto Portaria 671/AFD, eSocial S-2210/2220/2240, NFS-e Manaus**. Logo:
- **Servem (adaptáveis):** Comercial/CRM (propostas, objeções, follow-up), Marketing AI, rotinas de gestão (SOP, OKR, 1:1, KPI report), checklists de compliance/LGPD, conteúdo jurídico.
- **NÃO resolvem** o núcleo quebrado que a auditoria achou (folha, ponto, SST, integração). Esse núcleo precisa de **skills CUSTOM nossas** — e a auditoria é a matéria-prima delas.

## 2) A arquitetura (correta) — 3 camadas
- **Subagente por módulo** (`.claude/agents/*.md`): system prompt = "manual de operação" do módulo destilado da auditoria (caminhos, modelo de dados, **arestas de integração**, armadilhas reais). É o maior valor e é nosso/custom.
- **Skills custom de rotina** (`.claude/skills/*/SKILL.md`): deploy/bake seguro, E2E Playwright do portal, migration segura, montar kit GED, padrão de payload de evento. Nosso/custom.
- **Skills Avora** (camada geral): plugadas nos agentes onde fazem sentido (comercial, gestão, jurídico, BI).

## 3) Mapa módulo → agente → skills
| Módulo ERP | Agente | Skills CUSTOM (núcleo) | Skills Avora aplicáveis |
|---|---|---|---|
| Comercial/CRM (José Luís) | `agente-comercial` | funil, link assinatura | **Sales/Funnel/Objections/Follow-up, Copy** (forte) |
| Marketing AI | `agente-marketing` | atribuição lead | **Content & Copy, Ads, Editorial** (forte) |
| DP/Folha | `agente-dp-folha` | **CLT/CCT, eSocial, rescisão, férias** | — (Avora não cobre) |
| Ponto | `agente-ponto` | **Portaria 671/AFD, 12x36, noturno** | — |
| SST | `agente-sst` | **NR-1/PCMSO/PPRA, eSocial S-2210/20/40** | LGPD/risco (checklists) |
| RH | `agente-rh` | OKR/clima/360 do ERP | Leadership, OKR, 1:1, feedback |
| Recrutamento | `agente-recrutamento` | admissão→DP | Job Description, Screening, CV |
| Operações | `agente-operacoes` | escala/posto↔cliente | SOP, checklists operacionais |
| Portal (cliente+func) | `agente-portal` | materializar kit, raio-x | — |
| GED/GEDEON | `agente-ged` | drift-finder (existe), kit | — |
| Financeiro | `agente-financeiro` | conciliação, boletos | Cash flow, KPI, pricing, margem |
| Fiscal | `agente-fiscal` | NFS-e/SPED Manaus | Comparativo tributário, compliance |
| Jurídico/Contratos | `agente-juridico` | contrato ERP | **Contract reviewer, cláusulas, LGPD** (bom) |
| BI | `agente-bi` | dashboards ERP | Dashboards, KPI, relatórios |

## 4) Conclusão da ponderação
1. A intuição do "1 agente por módulo + skills" está **certa** — é "configurar o harness".
2. Mas o **valor que destrava produção** (o que a auditoria achou) vem das **skills custom + system prompts da auditoria**, não da Avora.
3. A Avora é **ótima na camada comercial/marketing/gestão/jurídico** — exatamente onde já temos José Luís e o Marketing AI. É aí que ela rende.
4. **Sequência sugerida:** primeiro os 3 movimentos da auditoria (payload de evento, backfill posto↔cliente, 1 event-bus) — eles valem mais que qualquer skill. Em paralelo, montar 1 agente-piloto (DP/Folha ou Comercial) pra você sentir o ganho.
