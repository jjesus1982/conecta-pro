## Conhecimento: os dois CNPJs e seus regimes

- **CONECTAMAIS ELETRONICA LTDA** (CNPJ1) 35.710.481/0001-03, Manaus-AM — regime **LUCRO REAL desde 01/01/2026**, com plano de retorno futuro ao Simples. Banco Inter. empresas.id `619a3df1-8bce-49ce-b77a-04f80a0e8491`.
- **CONECTAMAIS PATRIMONIAL LTDA** (CNPJ2) 66.014.833/0001-10 — **SIMPLES Nacional, Anexo III**, CNAE **8111-7/00**. Banco Cora. empresas.id `7d79ed12-d480-4906-b2e0-2b2c4d299bab`.
- O regime tributário vigente de cada CNPJ deve ser confirmado no cadastro vivo (`empresas`) no momento da apuração — este arquivo fixa só o que é estrutural.

## Conhecimento: apuração por regime

- **Eletrônica (Lucro Real):** apuração de IRPJ/CSLL/PIS/COFINS não-cumulativos conforme regras do Lucro Real; ISS recolhido em **Manaus**; retenção previdenciária de **11%** sobre nota de cessão de mão de obra; FGTS **8%** sobre a folha.
- **Patrimonial (Simples Anexo III):** **DAS integral** — enquanto a liminar de PIS/COFINS/INSS não for deferida, **não há isenção**: PIS/COFINS entram normalmente no cálculo do DAS e o **INSS incide em dobro** (retenção de 11% na nota de serviço + o próprio INSS embutido na alíquota do DAS/Simples). NUNCA relatar isso como "zerado" ou "não retido".
- NFS-e das funções humanizadas (agente de portaria, serviços gerais, artífice, jardineiro, líder de portaria) passam a ser emitidas pela **Patrimonial** conforme a transição de competência avança (ver seção Transição).
- ISS é municipal — Manaus é o município de referência para ambos os CNPJs.

## Conhecimento: liminar PIS/COFINS/INSS (Patrimonial) — status

- **Deu entrada, mas NÃO foi obtida/deferida** (posição 2026-07). Estado atual real: retenção normal de PIS/COFINS, INSS em dobro, DAS integral. Se perguntado sobre prazo de decisão, responder que não está disponível no contexto — não estimar data.

## Conhecimento: CCT e transição de competência

- **CCT SINDECOMPRESTS AM000613/2025** — piso 2026 = **R$ 1.670,00** — categoria **agentes de portaria** (não vigilância). Escala típica de Portaria = 12x36.
- Transição: jan–maio/2026 a folha foi apurada pela Eletrônica; junho/2026 (fechada em julho/2026) é a **1ª folha apurada como Patrimonial**. Após a migração das funções humanizadas, a Eletrônica retorna ao Simples.

> _(aguardando confirmação Jordan: alíquotas específicas de IRPJ/CSLL/PIS/COFINS aplicadas no Lucro Real da Eletrônica, calendário fiscal de vencimentos DAS/DCTFWeb/obrigações acessórias, CNAE completo da Eletrônica)_

## Playbook: apuração mensal por CNPJ

Situação: fechamento fiscal do mês / "quanto vamos pagar de imposto".

Passos:
1. Identificar o CNPJ e confirmar o regime vigente no cadastro ao vivo.
2. Se **Eletrônica**: apurar conforme Lucro Real (ISS Manaus, FGTS 8%, INSS 11% s/ cessão de mão de obra, PIS/COFINS não-cumulativos, IRPJ/CSLL) usando os valores reais do período (tool de leitura fiscal/financeira) — nunca estimar sem dado.
3. Se **Patrimonial**: apurar o DAS **integral** do Anexo III, considerando **INSS em dobro** enquanto a liminar não for deferida; confirmar se as NFS-e do período já foram emitidas pela Patrimonial (transição em curso) ou ainda pela Eletrônica.
4. Cruzar NFS-e emitidas x período apurado; sinalizar qualquer nota emitida no CNPJ errado dado o estágio da transição.
5. Reportar valores com fonte explícita; nunca arredondar/chutar tributo.

O que verificar antes de concluir:
- A resposta NÃO afirma "PIS/COFINS zerado" nem "INSS não retido" para a Patrimonial.
- Todo valor citado veio de uma tool ao vivo, com a fonte identificada.
- Se envolver decisão de mudança de regime ou disputa de recolhimento: sinalizar para validar com a Portte.

Ação: este playbook é diagnóstico/apuração — não protocola nem recolhe guia sozinho. Qualquer ato formal (retificação, pedido, resposta a fiscalização) passa por decisão humana com a contabilidade.
