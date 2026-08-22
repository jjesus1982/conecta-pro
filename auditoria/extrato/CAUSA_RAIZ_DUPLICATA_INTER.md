# Duplicata do extrato do Inter — causa raiz e o que falta

Medido em 22/08/2026, perseguindo a divergência de **R$1.999,34** entre o nosso extrato
do Inter e o saldo que o próprio banco informa.

## A cadeia, do sintoma à causa

1. **Sintoma:** oráculo do extrato vermelho — nosso saldo maior que o do banco.
2. **Primeira suspeita, ERRADA:** 12 grupos de "duplicata multi-fonte". Cheguei a montar o
   `DELETE`. Conferi com o banco antes: são **pagamentos gêmeos legítimos** (dois VT de
   R$32 no mesmo dia, dois contratos da Full Telecom quitados juntos). O banco tem 18
   lançamentos em 25/06 e nós 18. Apagar teria destruído transação real — como já
   aconteceu com o pagamento da Loide, restaurado depois.
3. **Duplicatas reais, encontradas:** 3 linhas em 10-11/08 (crédito de R$5.940,00 do
   Condomínio Gelain; débitos de R$2.743,21 do Banco Toyota e R$1.229,45 do C6).
   Apagadas → divergência caiu para **R$32,00**.
4. **Os R$32:** não era linha a mais, eram **três diferenças ao mesmo tempo** — uma
   duplicata do EWERTON e **duas ausências** (Alan Vieira e Jair Soares). A ponte
   deduplica por CONTAGEM por (data, valor): origem tinha 9 lançamentos de R$32 e o
   extrato já tinha 9, então concluiu "nada a inserir". ⭐ **A duplicata de um lado
   mascarou duas ausências do outro** — contagem não sabe QUAIS faltam.
5. **A divergência VOLTOU** a R$1.967,34 depois que rodei o sync: a ponte recriou as 3
   linhas apagadas. Apagar do extrato é enxugar gelo.
6. **CAUSA RAIZ:** a duplicação está em `inter_transactions` (a tabela de ORIGEM). A
   chave é `uq_inter_transactions_dedup (data_lancamento, tipo_operacao, valor,
   descricao)` — e o Inter **muda o texto da descrição entre importações**:

   | importada em | descrição |
   |---|---|
   | 12/08 09:07 | `PAGAMENTO DE TITULO - BANCO TOYOTA DO BRASIL SA` |
   | 14/08 12:00 | `BANCO TOYOTA DO BRASIL SA` |

   Texto instável usado como chave de identidade. A constraint não pega, e a mesma
   transação entra duas vezes.

## A correção que fecha

`GET /banking/v2/extrato/completo` — confirmado hoje, HTTP 200 — devolve **`idTransacao`**:

    idTransacao: "MDAxXzAwMDE5XzM3MDk5MDA3Ml8yMDI2LTA4LTExXzM3MzMwNTYyMQ=="
    dataInclusao, dataTransacao, tipoTransacao, tipoOperacao, valor,
    titulo, descricao, numeroDocumento, detalhes

Identificador estável do próprio banco. A importação deve usar `/completo` e trocar a
chave de dedup de `descricao` para `idTransacao`.

⚠️ **Não basta remover `descricao` da chave**: sem ela, dois VT de R$32 para pessoas
DIFERENTES no mesmo dia viram "duplicata" e um seria suprimido. A descrição é hoje a
única coisa que separa gêmeos legítimos — por isso a troca tem de ser por um id, não uma
subtração.

## Feito

- ponte grava `external_id = inter_tx_<id da origem>` + `ON CONFLICT DO NOTHING`
  (a garantia do banco estava DESLIGADA: 645 de 4.450 linhas sem id, e em índice único
  parcial NULO nunca colide com NULO)
- oráculo vigia linha NOVA do Inter sem `external_id`
- linha de base de gêmeos legítimos 8 → 12, com o método registrado
- backup das linhas removidas em `duplicatas_inter_20260822.json`

## Falta

1. importação passar a usar `/extrato/completo` e `idTransacao` como chave
2. ponte trocar dedup por contagem → por `external_id` (exige backfill do id nas 641
   linhas herdadas antes, senão re-insere tudo)
3. só então limpar as duplicatas, que hoje voltam a cada sync
