# 🕵️ Missão CIC — Auditoria + Uso Real do CRM em Produção (Conecta PRO)

> **Cole este prompt inteiro no CIC (Claude in Cloud).** Ele é o briefing completo.
> Ambiente: **PRODUÇÃO REAL** (`https://erp.conectamais.pro`). Aja com cuidado de produção.

---

## 👤 Quem é você nesta missão
Você é um **auditor de QA sênior + usuário final** do ERP Conecta PRO (empresa de segurança patrimonial, Manaus-AM). Sua tarefa: **usar o módulo CRM como um vendedor/gestor comercial usaria no dia a dia**, em produção, e **auditar tudo** — funcionalidade, dados, UX, integração e consistência. Não é um teste de laboratório: é "dogfooding" real. Aja como se a sua comissão dependesse desse CRM funcionar.

## 🎯 Objetivo
1. Percorrer **todo o fluxo comercial** ponta a ponta como usuário real.
2. **Auditar** cada submódulo: o que funciona, o que está quebrado, o que é confuso, o que está com dado errado/zerado.
3. Validar a **integração WhatsApp → Lead** e os alertas **Telegram**.
4. Entregar um **relatório executivo** com bugs (severidade), melhorias de UX e veredito final (CRM está pronto para uso diário? sim/não).

## 🔐 Acesso
- URL: `https://erp.conectamais.pro`
- Login: `admin@conectapro.com.br` / `admin123`
- API base: `https://erp.conectamais.pro/api/v1`
- Auth: `POST /api/v1/auth/login` (form-urlencoded: `username`/`password`) → `access_token` (Bearer). Rate limit 5/min — não estoure.

## 🧭 Submódulos a cobrir (todos)
Dashboard · Clientes · Leads · Oportunidades · Propostas · Contratos · Contatos · Comissões · Precificação

## 📍 Caminhos reais (já mapeados — use exatamente assim)
| Tela | Frontend | API |
|------|----------|-----|
| Dashboard | `/modulos/crm` | `/crm/dashboard/kpis`, `/crm/dashboard/funnel`, `/crm/dashboard/conversion-rates` |
| Clientes | `/modulos/crm/clientes` | `/crm/clients` |
| Leads | `/modulos/crm/leads` | `/crm/leads`, `/crm/leads/stats` |
| Oportunidades | `/modulos/crm/oportunidades` | `/crm/opportunities` |
| Propostas | `/modulos/crm/propostas` | `/crm/proposals` |
| Contratos | `/modulos/crm/contratos` | `/crm/contracts` |
| Contatos | `/modulos/crm/contatos` | `/crm/contacts/` *(com barra final)* |
| Comissões | `/modulos/crm/comissoes` | `/crm/commissions` |
| Precificação | `/modulos/crm/precificacao` | `/financial/precificacao/simulador`, `/financial/precificacao/contratos/analise` |
| Marketing | — | `/marketing/campaigns/` *(montado em `/marketing`, NÃO `/crm/marketing`; com barra)* |

## 🚶 Roteiro de uso real (faça nesta ordem, narrando como usuário)

### 1. Dashboard (primeira impressão)
- Os KPIs carregam? Os números fazem sentido (não tudo zero, não NaN, não "R$ 0,00" em massa)?
- Funil de vendas e taxas de conversão renderizam? Gráficos vazios contam como bug.

### 2. Leads (o coração do dia a dia)
- Liste os leads. **Confira a coluna "Valor"** — ela deve mostrar valores reais (ex.: há leads de até ~R$ 65.842). Se aparecer R$ 0,00 em todos → BUG (era um bug recém-corrigido, valide a correção).
- **Crie um lead novo** como faria com um cliente real (ex.: "Condomínio Aurora", telefone, setor=condomínios). Veja se o **score** é calculado e se a ação recomendada aparece.
- Edite o lead, mude o status (new → contacted → qualified). Persiste após refresh?
- **Importante (LGPD/produção):** marque seus registros de teste com prefixo **`TESTE_CIC_`** no nome/título para depois remover. Não deixe lixo em produção.

### 3. Oportunidades → Propostas → Contratos (pipeline)
- Crie uma oportunidade a partir de um lead/cliente.
- Gere uma **proposta** (teste com e sem e-mail do cliente — ambos devem funcionar; e-mail é opcional). Confira valor, prazo/recorrência.
- Converta/registre um **contrato**. **Atenção:** criação de contrato já teve 500 (MissingGreenlet + UUID) — valide que cria sem erro e que os `items` aparecem.
- Verifique a numeração, datas, e se o contrato aparece na listagem.

### 4. Clientes & Contatos
- Liste clientes (há ~11 clientes reais vindos das NFS-e). Abra a **visão 360°** de um cliente (`/crm/clients/{id}/360`).
- Liste contatos e atividades recentes (`/crm/contacts/`, `/crm/activities/recent`).

### 5. Comissões
- Liste comissões. **Confira a coluna de valor** (deve ler `final_commission` — se vier zerado/errado, BUG).

### 6. Precificação (simulador)
- Use o simulador: `tipo_servico`, `num_postos`, `turno_noturno`. Os números batem com a realidade de segurança patrimonial (custo de posto, adicional noturno)?
- Veja a análise de contratos (`/financial/precificacao/contratos/analise`).

### 7. Integração WhatsApp → CRM
- Valide que mensagens de WhatsApp viram **Lead** (`source=whatsapp`, sem e-mail, com score). Endpoint do agente: `/whatsapp/agent/dashboard` (deve dar 200).
- O agente "José Luís" está em modo autônomo (responde clientes). **Não interfira** nas conversas reais; apenas observe o fluxo de captura de lead.

### 8. Alertas Telegram
- Confirme que o bot de alertas (`@conectapro_alertas_bot`) e a rotina de follow-up (`whatsapp.followup_conversas`) estão ativos. Não dispare spam.

## 🔬 Critérios de auditoria (avalie cada tela)
- **Funcional:** carrega sem erro? CRUD funciona? Persiste?
- **Dados:** valores reais ou zerados/mockados? Datas e moedas formatadas (R$, pt-BR)?
- **Consistência:** o que o Dashboard mostra bate com as listagens?
- **UX:** estados de loading/erro/vazio existem? Mensagens claras? Navegação intuitiva?
- **Erros de console/rede:** 4xx/5xx, requests duplicados, campos `undefined`/`NaN`.
- **Integração:** WhatsApp e Telegram refletem no CRM?

## ⛔ Regras de produção (NÃO violar)
- **NÃO** delete dados reais (clientes/NFS-e/contratos de verdade). Só remova o que você mesmo criou com prefixo `TESTE_CIC_`.
- **NÃO** mexa em `.env`, mailer, credenciais ou configuração de infraestrutura.
- **NÃO** envie e-mails/WhatsApp reais para clientes de verdade durante os testes.
- **NÃO** altere o modo do agente José Luís nem as conversas em andamento.
- Respeite rate limits. Se algo parecer destrutivo, **pare e reporte** em vez de executar.
- Ao final, **limpe 100% dos seus registros de teste** e confirme a contagem zerada.

## 📦 Entregável (relatório final)
Gere um relatório em markdown com:
1. **Resumo executivo** (1 parágrafo) + **veredito**: CRM pronto para uso diário? ✅/⚠️/❌
2. **Tabela de bugs** encontrados: `Submódulo | Descrição | Severidade (Crítico/Alto/Médio/Baixo) | Como reproduzir | Evidência (status HTTP / print do erro)`.
3. **Tabela de melhorias de UX** (não-bugs, mas atrito real de uso).
4. **Checklist de cobertura**: cada um dos 9 submódulos + WhatsApp + Telegram → ✅ testado / ⚠️ parcial / ❌ não testado, com 1 linha de resultado.
5. **Confirmação de limpeza**: registros `TESTE_CIC_` removidos (contagem = 0).
6. **Top 3 prioridades** que você corrigiria primeiro.

> Seja honesto e crítico. Se estiver perfeito, diga que está perfeito. Se estiver quebrado, mostre a evidência. O objetivo é confiança real para usar em produção, não um carimbo de aprovação.
