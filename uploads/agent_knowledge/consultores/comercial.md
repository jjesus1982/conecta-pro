## Conhecimento: estrutura societária relevante à proposta

- **CONECTAMAIS ELETRONICA LTDA** (CNPJ1) 35.710.481/0001-03 — Segurança Eletrônica + Portaria Remota (CFTV, monitoramento, portaria remota). Banco Inter. empresas.id `619a3df1-8bce-49ce-b77a-04f80a0e8491`.
- **CONECTAMAIS PATRIMONIAL LTDA** (CNPJ2) 66.014.833/0001-10, Simples Anexo III, CNAE 8111-7/00 — serviços humanizados: agente de portaria, auxiliar/agente de serviços gerais, artífice, jardineiro, líder de portaria. Banco Cora. empresas.id `7d79ed12-d480-4906-b2e0-2b2c4d299bab`.
- Ao propor um contrato, o CNPJ certo depende do tipo de serviço vendido: portaria/serviços humanizados → Patrimonial; segurança eletrônica/CFTV/portaria remota → Eletrônica. Confirmar isso na proposta evita erro de faturamento e de regime tributário do contrato.
- CCT de referência para dimensionar mão de obra em propostas de portaria: **SINDECOMPRESTS AM000613/2025**, categoria agentes de portaria (não vigilância), piso 2026 = R$ 1.670,00, escala 12x36.

> _(aguardando confirmação Jordan: tabela de preços/margem comercial padrão por tipo de serviço, política de desconto autorizada, SLA de resposta ao lead)_

## Playbook: qualificar lead + gerar proposta

Situação: um lead precisa ser qualificado e, se elegível, receber uma proposta comercial.

Passos:
1. Ler o histórico do lead/cliente via tool de leitura CRM (interações, origem, necessidade declarada).
2. Qualificar: identificar se a necessidade é segurança eletrônica/portaria remota (Eletrônica) ou serviços humanizados de portaria (Patrimonial) — ou ambos.
3. Se qualificado, montar o rascunho da proposta (escopo, tipo de serviço, CNPJ correto) usando só dados reais do lead/cliente disponíveis nas tools — nunca inventar necessidade ou volume não informado.
4. Registrar a proposta usando a tool gated **`propor_proposta_comercial`** — isso grava um rascunho pendente; um humano do comercial revisa e envia.
5. Se o lead precisar de régua de cobrança em vez de proposta nova (ex.: renegociação, cobrança de fatura vencida), usar a tool gated `propor_cobranca` no mesmo espírito (propor, não executar).

O que verificar antes de concluir:
- A proposta não afirma preço/condição que não veio de fonte real (tabela de preço, negociação registrada) — se não houver essa fonte, sinalizar que falta confirmação comercial.
- O CNPJ indicado na proposta é compatível com o tipo de serviço.

Ação: este playbook só **propõe** (`propor_proposta_comercial` / `propor_cobranca`) — o consultor comercial nunca envia proposta, fecha contrato ou realiza cobrança diretamente; o humano do comercial aprova/envia o rascunho gerado.
