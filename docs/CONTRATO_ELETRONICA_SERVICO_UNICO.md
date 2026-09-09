# Contrato de segurança eletrônica em serviço único — como emitir

Modelo `eletronica_servico_unico`, para **fornecimento + instalação + configuração** em valor
ÚNICO (não recorrente): controle de acesso, CFTV, automação de portões, cerca elétrica,
interfonia. Sai sempre pela **Conecta Mais Eletrônica** (35.710.481/0001-03).

Texto-base: contrato Chácaras Maiápolis, revisão Furtado Maia, aprovado pelo Jordan em
09/09/2026. Seed em `backend/scripts/seed/modelo_eletronica_unico.py`.

## O fluxo, em duas chamadas

```
criar_contrato (contract_type=one_time, total_value)  →  emitir-por-modelo  →  PDF
```

`POST /crm/contracts/emitir-por-modelo` devolve **200 com `faltam_dados`** enquanto faltar
informação — com as perguntas prontas. Responda e chame de novo com as respostas. Restrito a
Jordan e Pyetra.

O que ele pergunta num contrato de valor único (e **não** pergunta dia de vencimento,
carência nem vigência, que só existem no recorrente):

| campo | onde é gravado | exemplo |
|---|---|---|
| `template_id` | `contracts.template_id` | `b7e4c9a2-…` |
| `representante` + `representante_cpf` | `crm_contacts` | Mayana Bruna Cabral Miller |
| `valor_total` | `contracts.total_value` | `46320` |
| `objeto_resumo` | `contracts.description` | "controle de acesso por biometria facial; …" |
| `proposta_numero` | `contracts.sla_config` | `PROP-2026-00001` |
| `itens` | `contract_items` | ver abaixo |

O cronograma de pagamento vai em `itens`, e cada um declara seu **papel** — é o que o render
lê para escrever a Cláusula 3.2:

```json
[{"tipo":"entrada","nome":"Entrada (50%) na assinatura","qtd":1,"total":"23160.00"},
 {"tipo":"parcela","nome":"Parcela 1/2","qtd":1,"total":"7720.00","vencimento":"30 dias"},
 {"tipo":"parcela","nome":"Parcela 2/2","qtd":1,"total":"7720.00","vencimento":"60 dias"},
 {"tipo":"retida","nome":"Parcela final retida","qtd":1,"total":"7720.00"}]
```

⚠️ **A soma tem de fechar com `total_value`.** O wizard recusa antes de emitir — contrato com
tabela que não soma é convite a disputa.

## Parâmetros com default

Ficam em `contract_templates.variables` e podem ser sobrescritos por contrato (vão para
`contracts.sla_config` quando você os passa na emissão):

```
prazo_exec_dias 60 · multa_atraso_dia 0,5 · multa_teto_pct 10 · homologacao_dias 10
garantia_meses 6 · cortesia_meses 6 · conecta_plus_valor 400 · foro Manaus/AM
```

Passe só o que mudar. Provado: um segundo contrato com prazo 30, garantia 12, cortesia 3 e
teto 15% sai correto sem tocar no modelo.

## Testemunhas

Este é o **único modelo da casa com testemunha** — duas, assinando eletronicamente na mesma
plataforma (decisão do Jordan, 09/09/2026). Ligado por `variables.testemunhas` no modelo.

⚠️ O fecho do texto e o quadro andam juntos. Manutenção e portaria seguem **sem** testemunha,
apoiados na dispensa do art. 784 §4º do CPC — um modelo que invoque a dispensa e ao mesmo
tempo colha assinatura de testemunha contradiz a si mesmo. O oráculo reprova esse caso.

## Provar que continua de pé

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend \
  python3 /app/scripts/orq/test_oraculo_contrato_eletronica_unico.py
```

Afirma as 8 blindagens jurídicas pela string, o CNPJ da Eletrônica, o total conferido contra
a composição no banco, a coerência do fecho — e, como regressão, que os dois contratos
recorrentes seguem intactos e sem quadro de testemunha.

## Recadastrar o modelo

O seed é idempotente (upsert por `service_type`), então rodar de novo atualiza o texto:

```bash
docker exec -e PYTHONPATH=/app conecta-pro-backend \
  python3 /app/scripts/seed/modelo_eletronica_unico.py
```

## Armadilhas medidas nesta implementação

- **`coalesce(sla_config,'{}')` não basta.** A coluna pode guardar o JSON `null` (que não é
  SQL NULL), e `'null'::jsonb || '{…}'::jsonb` devolve um **array**, não um objeto. O
  parâmetro some sem erro e a pendência volta na cara do usuário. Use `jsonb_typeof`.
- **`contracts.start_date` é NOT NULL**, inclusive no serviço único — lá ela é a data da
  assinatura, não o início de uma vigência que não existe.
- **`num_extenso` é masculino.** Saiu "02 (dois) parcelas" na primeira emissão.
