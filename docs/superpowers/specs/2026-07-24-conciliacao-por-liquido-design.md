# Conciliação por líquido (NFS-e ↔ banco) — Design (spec)

**Data:** 2026-07-24 · **Onda 2, sub-projeto 1** · Aprovação: Jordan delegou ("não só pode como deve, senão o caixa nunca vai bater")

## Goal
Fazer o **caixa bater**: conciliar os créditos do banco (Inter, depois Cora) contra as **NFS-e emitidas pelo valor LÍQUIDO** (bruto − ISS − retenções), não pelo bruto. Hoje o matcher usa o bruto e por isso nunca fecha.

## Fato que funda o design (provado no dado)
- O que cai no banco é o **líquido**: IDEAL FLORES bruto R$65.842,42 → líquido R$55.355,64 → **casa Inter R$55.355,64 (15/05)**. 10/14 notas da amostra casaram pelo líquido.
- Inter jan-jul: 119 créditos, R$1.131.220,84. NFS-e: 86 notas, líquido R$1.547.427,70, 12 CNPJs.
- Descrição do crédito: **PIX** traz o nome do pagador (`PIX RECEBIDO - Cp :32983165-Condominio Prime Arena`); **boleto** (`RECEBIMENTO TITULO - 112/...`) não traz nome.
- O líquido total das notas (R$1,55M) > créditos Inter (R$1,13M): a diferença é pago via **Cora/Itaú** ou nota recente ainda a compensar. Normal — o relatório mostra o resíduo honesto.

## Global Constraints (inegociáveis)
- Nunca fabricar: cada match provado por valor+identidade+data (oráculo). Sem match → "a conciliar" honesto, nunca forçado.
- Não move dinheiro (bookkeeping). Correções em contas-a-receber = replicar a verdade confirmada, documentado e reversível.
- Deploy blue-green; verificar pela rota; **sempre planejar com superpowers**.

## Arquitetura (isolada, nova — não mexe no matcher rígido antigo)
Novo serviço `conciliacao_liquido_service.py` (não toca `reconciliation_service` legado, que fica pra débitos/outros):

### Unidade 1 — `casar_notas_banco(inicio, fim, persistir=False) -> dict`
Entrada: período. Faz:
1. Carrega NFS-e emitidas (tomador_cnpj, tomador_nome, valor_servicos, iss_valor, valor_liquido, data_emissao) no período.
2. Carrega créditos do banco (bank_transactions, Inter 077 [+ Cora 403 na fase 2], type credit) no período, ainda não conciliados.
3. **Match em camadas** (1:1, um crédito não casa 2 notas):
   - C1: `abs(credito − valor_liquido) ≤ R$0,50` + janela `emissao−5d ≤ credito ≤ emissao+90d`.
   - C2 (retenção variável, ex. INSS 11% retido pelo tomador não refletido na nota): `credito` entre `valor_liquido*0.88` e `valor_liquido*1.005` **E** identidade do pagador bate (nome do PIX contém o tomador, OU CNPJ) + mesma janela.
   - C3 (boleto sem nome): `abs(credito − valor_liquido) ≤ R$0,50` + janela — só por valor+data (boleto não traz nome).
   - Preferir o menor `abs(credito − valor_liquido)`; marcar o crédito usado.
4. Retorna: `casados[]` (nota↔credito, diferença, camada), `notas_sem_credito[]` (a compensar / outro banco), `creditos_sem_nota[]` (recebimento sem NF — ex.: transferência do próprio Jordan, outra receita), totais e **% do líquido conciliado**.
5. Se `persistir=True` (ação gated): marca o crédito `reconciliation_status='conciliado'` + vínculo à nota; e marca o recebível correspondente pago (quando houver). Documentado.

### Unidade 2 — extrair identidade do PIX
`_pagador_do_credito(descricao) -> (nome, cnpj?)`: regex sobre `PIX RECEBIDO - Cp :<8dig>-<NOME>`; casa o nome com `tomador_nome` (normalizado, sem acento/caixa) ou CNPJ.

### Unidade 3 — tela redesign (g-bancos) "Conciliação por líquido"
- Read-only por padrão: resumo (% conciliado, R$ conciliado, R$ a conciliar, nº casados/pendentes) + tabela nota→crédito.
- Ação gated "Aplicar conciliação" → chama `casar_notas_banco(persistir=True)`.

## Data flow
NFS-e emitidas (`nfse_emitidas_nacional`) + bank_transactions (Inter/Cora) → `conciliacao_liquido_service` → relatório (read) / persistência (gated) → `_fin_bancos` builder → tela.

## Error handling
- Nota sem crédito → "a conciliar" (pode ser Cora/Itaú/recente) — nunca marca pago sozinho.
- Crédito sem nota → lista "recebimento sem NF" pra revisão.
- Retenção maior que a tolerância → não casa (honesto); Jordan ajusta a faixa se algum padrão de retenção aparecer.

## Testing / Oráculo
Prova cada match: `credito == valor_liquido` (±tolerância documentada) e identidade bate. Rodar read-only primeiro e mostrar os matches concretos (IDEAL FLORES 55.355,64, LARANJEIRAS 35.618,19). Só persistir após o read provar taxa alta.

## Pré-mortem
- **A.** Tolerância larga (C2) casa nota errada. *Mit.:* C2 exige identidade do pagador; 1:1; preferir menor diferença.
- **B.** Boleto sem nome casa nota errada por valor coincidente. *Mit.:* C3 só com janela estreita + valor exato ±0,50; se 2 notas mesmo valor, marca "ambíguo" pra revisão manual, não força.
- **C.** Persistir marca pago o que não é. *Mit.:* persistir é ação gated + só o que casou por C1/C2 (não C3 ambíguo); reversível (nota documentada).
- **D.** Extrato incompleto (Cora/Itaú fora) → notas ficam "a conciliar". *Mit.:* honesto no relatório; fase 2 traz Cora.
- **E.** Retenção que a nota não reflete (INSS retido) → líquido do banco < valor_liquido da nota. *Mit.:* C2 cobre até −12%; registrar a diferença como "retenção na fonte" no match.

## Escopo / fases
- **Fase 1 (esta):** Inter × NFS-e, read-only report + ação gated de persistir. Prova o caixa batendo.
- **Fase 2:** incluir Cora (403) + Itaú (quando houver extrato); afrouxar/ajustar tolerância de retenção conforme padrões reais.
- Fora: régua ativa, negativação (outras ondas).
