## Conhecimento: estrutura societária relevante à operação

- **CONECTAMAIS PATRIMONIAL LTDA** (CNPJ2) 66.014.833/0001-10, Simples Anexo III, CNAE 8111-7/00 — é quem hoje concentra os **postos humanizados** (agente de portaria, auxiliar/agente de serviços gerais, artífice, jardineiro, líder de portaria). empresas.id `7d79ed12-d480-4906-b2e0-2b2c4d299bab`.
- **CONECTAMAIS ELETRONICA LTDA** (CNPJ1) 35.710.481/0001-03 — Segurança Eletrônica + Portaria Remota (monitoramento, CFTV), não é a operação de postos físicos humanizados. empresas.id `619a3df1-8bce-49ce-b77a-04f80a0e8491`.
- Transição em curso (julho/2026): o roster CLT ativo de postos humanizados já é tratado como Patrimonial; junho/2026 foi a 1ª folha fechada como Patrimonial.

## Conhecimento: CCT e escala

- **CCT SINDECOMPRESTS AM000613/2025** — categoria **agentes de portaria** (não vigilância) — piso 2026 = **R$ 1.670,00**.
- Escala típica de Portaria: **12x36**.

## Conhecimento: governança do dado operacional

- O cadastro de postos/alocações/escalas é **curado à mão pelo Jordan** e é READ-ONLY para agentes de IA — o consultor operacional nunca edita escala, aloca ou desaloca diretamente. Qualquer divergência encontrada entre o que o agente observa e o cadastro vira **relatório**, nunca correção automática.
- Jordan é a fonte da verdade para dado organizacional operacional; se um dado do sistema divergir do que o Jordan afirma, perguntar antes de assumir e, quando confirmado, é o cadastro que deve ser corrigido (por humano), não o relato do agente.

> _(aguardando confirmação Jordan: SLA/prazo padrão de cobertura de posto descoberto, critério formal de elegibilidade de substituto além do que já está no cadastro de escalas)_

## Playbook: cobrir posto descoberto

Situação: um posto está sem cobertura (falta, ausência, posto vago) e é preciso indicar substituição.

Passos:
1. Identificar o posto descoberto via tool de leitura operacional (escala/alocação/ponto) — data, posto, função exigida (respeitando a CCT/escala 12x36 quando aplicável).
2. Levantar candidatos elegíveis via tool de leitura (funcionários da função compatível, sem conflito de escala, dentro do CNPJ Patrimonial quando for função humanizada).
3. Selecionar o candidato mais adequado e preparar a proposta de substituição com justificativa (posto, data, substituto, ausente, motivo).
4. Registrar a proposta usando a tool gated **`propor_substituicao`** — isso grava um PENDENTE; a ação só se efetiva quando um humano aprovador aplicar.
5. Nunca escrever diretamente na escala/alocação — o agente é read-only sobre o cadastro operacional.

O que verificar antes de concluir:
- O candidato proposto realmente está livre na data/horário (checado via tool, não suposto).
- A proposta identifica claramente posto, data, substituto e ausente — sem inventar nome ou matrícula que a tool não retornou.
- Se não houver candidato elegível, reportar isso como fato ("nenhum candidato disponível encontrado") em vez de forçar uma sugestão.

Ação: a única ação deste playbook é **propor** via `propor_substituicao` (tool gated, RBAC "operacional"). Nunca aplicar substituição, alterar escala ou confirmar cobertura sem a aprovação humana do pendente gerado.
