# Revisão do desenho Efí — contra o que já existe no Conecta PRO

Revisado em 13/08/2026, cruzando os 6 arquivos com o banco de produção.

---

## O que está certo, e é bom

Não são detalhes — são as decisões que separam um desenho de folha de um exemplo de
tutorial. Manteria todas:

- **Idempotência em três camadas** (`idEnvio` determinístico + `UNIQUE` + claim atômico).
  Folha paga duas vezes não volta; a paranoia aqui está calibrada.
- **`SELECT … FOR UPDATE SKIP LOCKED`** para o claim. É a forma correta, e a maioria dos
  desenhos erra isso.
- **Chamada de rede fora da transação.** Segurar lock durante I/O é como se derruba banco.
- **Guard de soma antes de autorizar** — divergência de 1 centavo aborta.
- **Erro de rede ≠ erro de negócio.** `ERRO_ENVIO` retryável com o mesmo `idEnvio`; 4xx vira
  `FALHOU` sem retry cego.
- **Reconciliação por `idEnvio`** cobrindo webhook perdido.
- **Honestidade sobre o que não foi verificado** (§8). Os campos suspeitos estão isolados em
  funções pequenas. Isso é disciplina, não preguiça.

---

## Problema 1 — duplica um sistema que já existe e está em produção

O desenho cria o schema `folha_efi` com `lote_pagamento`, `pagamento`, `pagamento_evento` e
`webhook_event`. Só que o Conecta PRO **já tem isso**, com dado real dentro:

| tabela existente | linhas | o que já resolve |
|---|---|---|
| `inter_payments` | 43 | `status`, `prepared_by`, `approved_by`, `approved_at`, `approval_otp_used`, `executed_at`, `confirmed_at`, `cancelled_by`, `lote_id`, `categoria`, `inter_payment_id`, `inter_response` |
| `inter_lote_otp` | 51 | OTP por lote, com `expires_at` e `used` |
| `inter_payment_audit` | 128 | trilha de auditoria |
| `financial_pagamentos_pj` | 9 | folha PJ com `nf_exigida`/`nf_ok`, `pix_key`, `e2e_ref` |

**A máquina de estados, o lote e o OTP já existem e foram exercitados hoje** — o pagamento da
Inviolável passou por `D7 preparar → gerar_otp → aprovar → executar`, com o OTP chegando no
e-mail do Jordan.

Dois sistemas de money-out convivendo é como se perde controle: um deles some do radar e a
divergência aparece meses depois. **O caminho é generalizar o que existe**, não erguer um
paralelo — o `inter_payments` já é quase agnóstico de banco; falta uma coluna `banco` e um
adapter novo ao lado do Inter.

---

## Problema 2 — o dinheiro sairia e o razão não veria ⚠️ o mais grave

O desenho nunca escreve em **`bank_transactions`**. E `bank_transactions` é a porta de
entrada do razão: dali sai `accounting_entries`, o balanço, o DRE.

Repare que `inter_payments` tem exatamente a coluna que falta no desenho:
**`reconciled_bank_tx_id`**. Ela existe porque esse problema já foi enfrentado uma vez.

Pior: **não há sync do extrato da Efí em lugar nenhum do desenho.** Hoje temos
`inter_sync_service` e `cora_sync_service` puxando extrato todo dia às 08:00. Sem o
equivalente para a Efí, R$94 mil de folha sairiam por mês e o sistema não teria como saber —
nem pelo pagamento, nem pelo extrato.

Isso é exatamente a doença que passamos o dia 13/08 curando: dinheiro que se move fora da
escrituração. O desenho reintroduz.

**Falta, e é obrigatório:** ao liquidar, gravar em `bank_transactions` com
**`amount` NEGATIVO** (a constraint `ck_bank_tx_sinal_coerente` recusa débito positivo — foi
o que barrou o pagamento do Cora hoje, corretamente), `external_id = e2eId`, e um
`efi_sync_service` diário no mesmo molde dos outros dois.

---

## Problema 3 — o OTP entra como parâmetro `bool`

```python
def autorizar_lote(session, lote_id, usuario: str, otp_ok: bool) -> None:
    ...
    if not otp_ok:
        raise PermissionError("OTP interno não validado")
```

Quem chama decide se o OTP passou. Qualquer caller — inclusive um bug, um script ou um
agente — passa `True` e a trava evapora. A verificação tem que acontecer **dentro**, contra
`inter_lote_otp` (`code`, `expires_at`, `used`), consumindo o código no mesmo commit que
autoriza o lote.

Regra da casa que vale aqui: *quem propõe, quem aprova e quem executa nunca são o mesmo
ator.* Um `bool` no argumento junta os três.

---

## Pontos menores, mas que barram produção

**4. A mitigação do DICT não está de pé.** O desenho propõe validar a chave no cadastro
(`chave_validada_em`, `chave_nome_bacen`). Medido hoje:

```
funcionários ativos:       54
com chave PIX cadastrada:  49
com chave CONFIRMADA:       0
```

A coluna `employees.pix_confirmada` existe e está zerada para todo mundo, e 5 ativos não têm
chave. **Mover folha para uma API sem DICT com 49 chaves nunca conferidas é mandar salário
para CPF não verificado.**

Solução com o que já temos: **o Inter tem DICT** (`GET /pix/v2/dict/key`). Validar as 49
chaves pelo Inter, conferindo nome e documento contra o cadastro, e marcar `pix_confirmada`.
Uma vez, antes de migrar. É pré-requisito, não melhoria.

**5. `favorecido` duplica o cadastro.** `employees` já tem `pix_key`, `pix_key_type` e
`pix_confirmada`. Uma segunda tabela de favorecido cria duas verdades sobre a chave de
pagamento de uma pessoa — e a divergência aparece no pior momento.

**6. O teto quase estoura, e o desenho deixou como TODO.** Temos
`CONECTA_LIMITE_DIARIO_PAGAMENTOS = R$100.000`. A folha medida em agosto pelo Cora foi
**R$94.394,91** — **94% do teto num único lote**. Não é hipótese distante: é o mês passado.
O `autorizar_lote` tem que ler o teto do sistema, e o lote precisa saber se dividir.

**7. Números do desenho a corrigir.** O DESIGN fala em R$137k de folha; o medido é
**R$94.394,91** (60 pagamentos pelo Cora em agosto). Os R$137k são o total de saídas do
Cora, não só folha. E os 88 PIX incluem os R$32 de VT/VR de diarista, que hoje saem pelo
**Inter** (64 pagamentos, R$6.641,71) — se a folha migrar, decidir se esses vão junto.

---

## O que eu faria, em ordem

1. **Antes de qualquer código**: validar as 49 chaves PIX pelo DICT do Inter e marcar
   `pix_confirmada`. Sem isso nada de folha migra.
2. **Generalizar `inter_payments`** em vez de criar `folha_efi`: coluna `banco`
   (`inter`/`efi`), e o `EfiClient` entra ao lado do `InterAdapter` no fluxo D7 que já
   existe. Aproveita OTP, lote, auditoria e `reconciled_bank_tx_id`.
3. **Escrever `efi_sync_service`** no molde do `cora_sync_service` — extrato diário,
   `amount` negativo nas saídas, `external_id = e2eId`, método guardado.
4. **Mover a verificação do OTP para dentro** de `autorizar_lote`, contra `inter_lote_otp`.
5. **Ler o teto do sistema** no guard de autorização.
6. Só então o sandbox da Efí, para fechar os itens da §8 do DESIGN.

O trabalho técnico do desenho é bom e boa parte se aproveita — `efi_client.py` entra quase
inteiro, e as três garantias de folha são exatamente as certas. O que muda é **onde ele
mora**: dentro do sistema de pagamento que já existe, não ao lado dele.
