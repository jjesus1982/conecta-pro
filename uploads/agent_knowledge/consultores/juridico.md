## Conhecimento: papel deste arquivo

- A base principal do Jurídico IA (precedentes reais e playbooks trabalhistas — abandono, gradação disciplinar, transferência de posto, rescisão indireta, pejotização) já está cadastrada no banco (`juridico_conhecimento` e `juridico_playbook`, semeada por `backend/modules/juridico/conhecimento_service.py`). Este `.md` **complementa**, não duplica: traz contexto societário/regulatório que o consultor jurídico precisa mas que não é um "caso" nem um "playbook disciplinar".

## Conhecimento: estrutura societária (contexto para pareceres)

- **CONECTAMAIS ELETRONICA LTDA** (CNPJ1) 35.710.481/0001-03, Manaus-AM — Lucro Real desde 01/01/2026, plano de retorno futuro ao Simples. Fica com Segurança Eletrônica + Portaria Remota (+ PJ/DEV/técnico). empresas.id `619a3df1-8bce-49ce-b77a-04f80a0e8491`.
- **CONECTAMAIS PATRIMONIAL LTDA** (CNPJ2) 66.014.833/0001-10 — Simples Anexo III, CNAE 8111-7/00, serviços humanizados (agente de portaria etc.). empresas.id `7d79ed12-d480-4906-b2e0-2b2c4d299bab`.
- Relevância jurídica: em processos de pejotização/reconhecimento de vínculo, o CNPJ correto do contrato/NFS-e/pagamento importa para a defesa — confirmar sempre qual CNPJ prestou/pagou no período em disputa, especialmente durante a transição de competência (jan–maio/2026 = Eletrônica; junho/2026 em diante = Patrimonial para as funções humanizadas).
- CCT de base: **SINDECOMPRESTS AM000613/2025**, categoria **agentes de portaria** (não vigilância) — relevante para qualquer disputa de enquadramento sindical/categoria profissional.

## Conhecimento: cuidado com a liminar PIS/COFINS/INSS da Patrimonial em disputas

- Se um processo ou parecer tocar em tributos/encargos da Patrimonial (ex.: discussão de custo em rescisão, defesa de capacidade de pagamento), a liminar de PIS/COFINS/INSS **NÃO foi deferida** — a empresa segue com retenção normal, INSS em dobro e DAS integral. Nunca citar "liminar concedida" como fato em peça ou análise.

> _(aguardando confirmação Jordan: status/andamento de processos além dos já cadastrados na base jurídica; qualquer nova ação/liminar societária ou tributária em curso)_

## Playbook: dossiê de processo (READ-ONLY)

Situação: usuário pede "monta o dossiê do processo X" ou "resume a situação jurídica de [empregado/caso]".

Passos:
1. Buscar na base de conhecimento jurídica (`juridico_conhecimento`) precedentes da própria empresa com área e palavras-chave relacionadas ao caso.
2. Buscar no `juridico_playbook` o procedimento correspondente à situação (abandono, disciplinar, transferência, rescisão indireta, pejotização, etc.) e citar a base legal already cadastrada.
3. Reunir os documentos/provas indicados no playbook (ex.: NFS-e, comprovantes de pagamento, cartas, registros de ponto) — apontar quais existem no ERP e quais faltam, sem fabricar.
4. Confirmar o CNPJ/empresa envolvida no período do processo (Eletrônica ou Patrimonial), dado a transição em curso.
5. Redigir o dossiê como leitura organizada: fatos do ERP + precedente aplicável + próximos passos recomendados — nunca como decisão final.

O que verificar antes de concluir:
- Nenhum prazo processual, valor de causa ou andamento foi inventado — só o que está na base ou explicitamente marcado como "não disponível".
- A resposta distingue claramente fato (registro no ERP/processo) de recomendação (opinião jurídica).

Ação: este playbook é **sempre READ-ONLY**. O Jurídico IA nunca assina, protocola, confessa, transaciona ou pratica qualquer ato irreversível — qualquer decisão de estratégia processual, acordo ou resposta formal exige revisão humana (advogado/gestor) antes de sair.
