# Regra de ferro — `empresa_id` e quarentena (Fase −1 / Task 2)

**Contexto:** os 2 CNPJs do Grupo (Eletrônica `619a3df1-…`, Patrimonial `7d79ed12-…`)
compartilham o mesmo `condominio_id` do ESCRITÓRIO (`a1b2c3d4-e5f6-7890-abcd-ef1234567890`).
Por isso `condominio_id` **não** separa empresa.

## A regra (o futuro cérebro/consultor DEVE obedecer)
1. **Nenhuma agregação por CNPJ pode incluir linha com `empresa_id IS NULL` ou `empresa_review = true`.** Quarentena não entra em soma por empresa.
2. **Nunca chutar `empresa_id`.** Só preencher via derivação 1:1 confiável; o resto fica em quarentena até o Jordan reclassificar.
3. Tabelas com `empresa_id` confiável (RH/contábil/fiscal — ~14 tabelas) podem agregar por CNPJ. As 5 tabelas da Task 2 (`occurrences`, `nfses`, `receivable_accounts`, `payable_accounts`, `leads`) estão **100% em quarentena** hoje.

## Relatório de quarentena (para o Jordan reclassificar)
```sql
SELECT 'receivable_accounts' t, count(*) FROM receivable_accounts WHERE empresa_review
UNION ALL SELECT 'payable_accounts', count(*) FROM payable_accounts WHERE empresa_review
UNION ALL SELECT 'nfses', count(*) FROM nfses WHERE empresa_review
UNION ALL SELECT 'occurrences', count(*) FROM occurrences WHERE empresa_review
UNION ALL SELECT 'leads', count(*) FROM leads WHERE empresa_review;
```
Estado 2026-07-21: receivable 22, payable 71, nfses 27, occurrences 4, leads 22 — todos em quarentena.
