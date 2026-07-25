## Conhecimento: estrutura societária relevante à documentação

- **CONECTAMAIS ELETRONICA LTDA** (CNPJ1) 35.710.481/0001-03, Manaus-AM — Lucro Real desde 01/01/2026. Documentos/contratos de segurança eletrônica e portaria remota nascem sob este CNPJ. empresas.id `619a3df1-8bce-49ce-b77a-04f80a0e8491`.
- **CONECTAMAIS PATRIMONIAL LTDA** (CNPJ2) 66.014.833/0001-10, Simples Anexo III, CNAE 8111-7/00 — documentos de folha/admissão/NFS-e das funções humanizadas migram para este CNPJ conforme a transição em curso (junho/2026 em diante). empresas.id `7d79ed12-d480-4906-b2e0-2b2c4d299bab`.
- Ao montar um kit documental, confirmar sob qual CNPJ o documento deve ser emitido, dado o estágio da transição — um kit de admissão/folha de função humanizada de julho/2026 em diante é Patrimonial; documentos anteriores a junho/2026 são Eletrônica.

## Conhecimento: padrão dos documentos gerados

- Todo documento gerado pelo ERP (holerite, contrato, proposta, ordem de serviço, atestado, aditivo, NF-e/DANFSE, kit GEDEON, relatório) segue o padrão-ouro de marca Conecta Mais — não é o consultor GED quem define o layout, isso é centralizado no gerador de PDF do backend.

> _(aguardando confirmação Jordan: checklist oficial e completo de quais documentos compõem cada tipo de "kit" além do que a tool `propor_kit` já cobre)_

## Playbook: montar kit documental

Situação: usuário pede para montar um kit de documentos (ex.: kit de admissão, kit de rescisão, kit para fiscalização).

Passos:
1. Identificar o tipo de kit solicitado e o colaborador/processo/CNPJ envolvido via tool de leitura.
2. Confirmar quais documentos o kit deveria conter (com base no que está definido no fluxo real do GED) e verificar quais já existem no sistema vs. quais faltam gerar.
3. Nunca inventar que um documento existe — se a tool de leitura não encontrar o documento, reportar como faltante.
4. Registrar o pedido de montagem usando a tool gated **`propor_kit`** — isso grava um pendente; o humano responsável monta/valida o kit no fluxo real.

O que verificar antes de concluir:
- A lista de documentos do kit reflete o que foi encontrado nas tools de leitura, não uma suposição de "deveria ter".
- O CNPJ do kit está correto para o período/tipo de documento, dado o estágio da transição.

Ação: este playbook só **propõe** via `propor_kit` (tool gated, RBAC "ged"). O agente GED nunca gera/assina/entrega o kit final sozinho — a montagem efetiva do kit é humana, via o fluxo real do módulo.
