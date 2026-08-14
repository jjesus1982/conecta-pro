# Handoff para o terminal do Departamento Pessoal — 13º salário

Achado em 14/08/2026 pelo terminal do **financeiro**, durante levantamento de caixa para os
próximos 4 meses. **Não executei nada disso** — 13º é do módulo de DP. Fica aqui para não
ser redescoberto.

## 1. Não existe gerador de 13º no código

`grep -rl "decimo_terceiro_1a"` no repositório inteiro: **nenhum arquivo**. Os 94 holerites
de 13º em `hr_payslips` (47 de `decimo_terceiro_1a` + 47 de `decimo_terceiro_2a`, todos
`status='draft'`) foram gravados por uma **rodada avulsa em 03/08/2026 15:29–15:34** que não
deixou código. Enquanto não houver gerador, todo 13º depende de alguém rodar algo à mão.

## 2. A rodada de 03/08 perdeu 4 pessoas, e ninguém percebeu

A folha de julho/2026 tem **51** holerites; o 13º tem **47**. Os 4 que sumiram estão todos
`ativo` na Patrimonial e todos tinham holerite de julho na data da geração — ou seja, **não
foi questão de data de admissão**:

| funcionário | admissão | observação |
|---|---|---|
| **ELEN XAVIER NUNES** | 2024-04-14 | ⚠️ o caso grave: 14 holerites, meses 1 a 7, sem explicação |
| ALEXANDRE SOUZA DA SILVA | 2026-07-19 | tinha holerite de julho |
| KELLY PATRICIA DA SILVA DE SOUZA | 2026-07-19 | tinha holerite de julho |
| NAILSON GARCIA GOMES | 2026-07-19 | tinha holerite de julho |

Caso à parte: **CINTIA BEZERRA OLIVEIRA** (adm. 2026-02-22) está ativa e também não tem 13º,
mas ela não tem holerite de julho — só de fevereiro a junho. Vale entender por quê.

## 3. O cálculo é só sobre salário base

A rubrica gravada é `{"codigo": "0070", "descricao": "13º Salário — 1ª Parcela
(adiantamento)", "referencia": "12/12 avos"}`. Os avos estão certos, mas **não há média de
variáveis**. Como o adicional noturno é pago por escala nesta operação, ele entra na média do
13º — o valor real será maior que o do rascunho.

## 4. Números do rascunho atual (para referência)

- 1ª parcela (nov): R$ 35.864,16 · 2ª parcela (dez): R$ 30.410,64 · líquido R$ 66.274,80
- Cálculo por avos sobre os 52 ativos reais, só base: **R$ 73.033,68** — tratar como piso

## 5. Um registro de teste estava contando como funcionário

`TESTE PONTO (JORDAN)`, CPF `11111111111`, estava `ativo` na Patrimonial e entrava em toda
contagem de headcount. **Já inativei** (renomeado para `[REGISTRO DE TESTE - NAO CONTAR]`) —
ativos da Patrimonial passaram de 53 para 52. Não deu para apagar: há um registro em `users`
e outro em `portal_notifications` apontando para ele. Backup em
`auditoria/teste_ponto_backup.json`.

## Sugestão (não executada)

Um oráculo que compare a contagem do 13º com a da folha do mês de referência. Foi exatamente
essa conferência que faltou e deixou a ELEN de fora.
