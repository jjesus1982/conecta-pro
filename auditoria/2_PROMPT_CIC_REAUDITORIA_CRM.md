# 🔁 Prompt CIC — Re-Auditoria do CRM (validar correções da rodada anterior)

> **Cole este prompt inteiro no CIC.** Ambiente: **PRODUÇÃO REAL** (`https://erp.conectamais.pro`).
> Esta é uma **re-auditoria**: a rodada anterior corrigiu os bugs que você encontrou. Sua missão agora é **verificar, sem dó, se as correções funcionam de verdade** e se nada regrediu. Seja cético: só dê ✅ com evidência.

---

## 👤 Papel
Você é o mesmo auditor QA sênior + usuário final. Use o CRM como um gestor comercial usaria no dia a dia, **focando nos pontos que estavam quebrados** e confirmando que agora funcionam ponta a ponta.

## 🔐 Acesso
- URL: `https://erp.conectamais.pro` · Login: `admin@conectapro.com.br` / `admin123`
- API: `https://erp.conectamais.pro/api/v1` · Auth: `POST /auth/login` (form-urlencoded). Rate limit 5/min.

## 📍 Caminhos reais (use exatamente — alguns têm pegadinha)
| Tela | API |
|------|-----|
| Dashboard | `/crm/dashboard/kpis`, `/crm/dashboard/funnel` |
| Leads | `/crm/leads`, `/crm/leads/stats`, `PUT /crm/leads/{id}` (status/edição), `PATCH /crm/leads/{id}/status` |
| Clientes | `/crm/clients`, `/crm/clients/{id}/360` |
| Oportunidades | `/crm/opportunities` |
| Propostas | `/crm/proposals`, `POST /crm/proposals/{id}/accept` |
| Contratos | `/crm/contracts` (criar: `name`, `client_id`, `contract_type`=`recurring`/`one_time`, `monthly_value`) |
| Contatos | `/crm/contacts/` *(com barra)* |
| Comissões | `/crm/commissions`, `/crm/commissions/stats`, `/crm/commissions/rules` |
| Precificação | `/financial/precificacao/simulador` *(GET, não POST)*, `/financial/precificacao/contratos/analise` |
| Marketing | `/marketing/campaigns/` *(em `/marketing`, não `/crm/marketing`; com barra)* |

---

## ✅ O que DEVE estar corrigido agora — confirme cada um com evidência

### 1. [era CRÍTICO] Criar lead pela UI
- Abra **Leads → Novo Lead**, preencha Nome (e use os novos campos **Origem** e **Valor estimado**), clique **Criar Lead**.
- **Esperado:** retorna **201**, o lead aparece na lista, o contador incrementa, e aparece **toast de sucesso**. Em caso de erro, deve aparecer **toast de erro** (não mais falha silenciosa).
- Teste também criar com e **sem** e-mail (e-mail é opcional).

### 2. [era ALTO] Ações na lista de Leads
- Clique no botão **"..."** de um lead → deve abrir menu com **Editar** e **mudar status** (Em contato / Qualificado / Convertido / Perdido).
- Mude o status pela tela e **dê refresh** → a mudança deve **persistir**.
- Clique na **linha** do lead → deve abrir a edição pré-preenchida; salve e confirme que persiste.
- ⚠️ Confirme que os status usados são válidos (`contacted/qualified/won/lost`) — **não deve existir** mais o status inválido `converted`.

### 3. [era MÉDIO] Pipeline ponderado dos leads
- `GET /crm/leads/stats` → **`total_weighted_value` deve ser coerente** com o pipeline (ordem de ~R$ 274 mil), **não** ~R$ 2,7 mil.
- Confirme que **nenhum lead** tem `status='converted'` nem `probability=1` indevido.

### 4. [era comissões zeradas] Geração automática de comissão
- Fluxo E2E: crie uma proposta de teste com valor, **aceite** (`POST /proposals/{id}/accept`).
- **Esperado:** o aceite retorna **201** e uma **comissão é criada automaticamente** (confira em `/crm/commissions?proposal_id=...` → `final_commission` ≈ 5% do valor).
- Confirme que `/crm/commissions`, `/crm/commissions/stats` e `/crm/commissions/rules` retornam **200 com dados** (deve existir 1 regra "Comissão Padrão Vendas 5%").
- ⚠️ Ponto crítico que estava quebrado: a **lista de comissões com dados** deve dar **200** (antes dava 500/MissingGreenlet).

### 5. [era contatos vazios] Contatos
- `GET /crm/contacts/` → deve listar **11 contatos** (1 por cliente, derivados dos dados reais). A visão 360° de um cliente deve mostrar o contato.

### 6. [validar] Criação de contrato
- Crie um contrato de teste (`name`, `client_id`, `contract_type=recurring`, `monthly_value`) → deve dar **201** sem erro, com os `items` aparecendo (sem MissingGreenlet).

---

## 🔍 Regressão — confirme que NÃO quebrou nada
- Os 9 submódulos + WhatsApp + Telegram seguem operacionais.
- WhatsApp→Lead: leads `source=whatsapp` sem e-mail continuam sendo capturados.
- Agente "José Luís" intacto (autonomous, não interferir nas conversas).
- Os 11 clientes reais, 27 NFS-e, contratos e MRR **inalterados**.

## ⛔ Regras de produção (iguais à rodada anterior)
- **NÃO** delete dados reais; marque seus testes com prefixo **`TESTE_CIC_`** e **limpe 100% ao final** (confirme contagem 0).
- **NÃO** toque em `.env`, mailer, credenciais, infra, nem no agente José Luís.
- **NÃO** envie WhatsApp/e-mail real a clientes. Respeite rate limits. Se algo parecer destrutivo, **pare e reporte**.

## 📦 Entregável
1. **Veredito final:** o CRM agora está **Aprovado sem ressalvas ✅**? (sim/não, com justificativa).
2. **Tabela de verificação** dos 6 itens acima: `Item | Esperado | Resultado (HTTP/evidência) | ✅/❌`.
3. **Regressões** encontradas (se houver), com severidade.
4. **Bugs novos** que por acaso aparecerem (não force — só o que for real).
5. **Confirmação de limpeza** (`TESTE_CIC_` = 0).
6. Se ainda houver ⚠️/❌, liste em ordem de prioridade. Se estiver tudo ✅, diga claramente.

> Lembre: na rodada anterior, 4 dos seus "bugs" eram falsos-positivos/estado-vazio (comissões/contatos vazios = falta de dado; simulador POST 405 = GET por design; métricas derivadas zeradas = sem proposta aceita). Agora muitos desses foram **habilitados/populados** — verifique com base nos dados atuais, não nos antigos.
