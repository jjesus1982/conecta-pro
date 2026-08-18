# Efí — o que resolver na abertura da conta (antes de qualquer código)

Escrito em 14/08/2026, com a documentação já navegada. Serve como roteiro do contato com
a Efí — cada item aqui muda o que precisa ser construído.

---

## 1. ⚠️ O bloqueador: limite diário

> Documentação da Efí, textual: *"limites diários pré-aprovados de cada conta: Contas Efí
> Pro: R$ 0,30. Contas Efí Empresas: R$ 1,00. É um requisito do endpoint, que tenha conta
> do tipo Efí Empresas para realizar alterações nos limites de envio."*

**Fora da caixa a Efí envia um real por dia. A folha é R$94.394,91/mês.**

Duas coisas a garantir na abertura:

- [ ] A conta tem que ser **Efí Empresas** (a Pro não altera limite)
- [ ] Pedir o **aumento do limite diário de envio por escrito**, informando o volume real:
      **~R$95.000/mês, distribuídos em ~54 pagamentos de folha, concentrados entre o dia
      1 e o dia 10**

Sem isso, tudo o que for construído fica pronto e parado. É o único item que não tem
contorno técnico.

**CNPJ:** `66.014.833/0001-10` (Conecta Mais Patrimonial) — o **mesmo** da conta Cora.
Abrir noutro CNPJ transforma a transferência Cora → Efí em mistura de caixa entre empresas,
que é problema contábil, não técnico.

---

## 2. Três perguntas com impacto direto em código

- [ ] **Existe consulta de chave PIX (DICT)?** Varri a lista de escopos e não achei. Se
      existir, muda como validamos o favorecido antes de pagar. Se não existir, a mitigação
      é mandar para a **chave CPF**: quem não tiver chave registrada devolve erro no envio
      — falha, não paga errado.
- [ ] **Qual o payload exato do webhook de envio?** A doc confirma que o webhook avisa
      sucesso/rejeição, mas não mostra o corpo. É o que fecha o ciclo sem varrer extrato.
- [ ] **O teto pode ser configurado por API**, ou só pelo painel/atendimento?

---

## 3. Pedir junto, no mesmo contato

- [ ] Credenciais de **homologação** + certificado
- [ ] Confirmar que o escopo **`pix.send`** está habilitado (a doc diz que às vezes é
      preciso desativar e reativar o escopo para o recurso funcionar)
- [ ] Confirmar o requisito: **a chave PIX do pagador precisa ter um webhook associado**
      para o envio funcionar — não é opcional
- [ ] Chave pública da Efí para o **mTLS do webhook** (norma do Bacen) e liberação do IP
      de origem `34.193.116.226`

---

## 4. O que a homologação já resolve sozinha

A Efí tem gatilhos **determinísticos por valor** — dá para exercitar a máquina de estados
inteira sem depender de sorte:

| valor | resultado |
|---|---|
| R$0,01 a R$10,00 | confirmado, resultado por webhook |
| R$10,01 a R$20,00 | rejeitado, resultado por webhook |
| acima de R$20,00 | rejeitado já na requisição |
| **R$4,00** | gera **duas devoluções** de R$2,00 |
| **R$5,00** | gera **uma devolução** de R$5,00 |

Isso fecha, no sandbox, três dos itens que o desenho original deixou como suposição: o
shape do retorno, os literais de status e o payload do webhook.

---

## 5. O que já está pronto do nosso lado

Nada disto precisa ser construído quando a conta sair:

- **Fluxo de lote com OTP e teto** (`ordem_pagamento_service`) — o mesmo lote serve para
  Cora (executado no app) e para Efí (executado por API). Só muda quem executa.
- **Conciliação por CPF e `endToEndId`** — o extrato dos dois bancos já identifica a
  contraparte desde 14/08. A regra de fechamento está provada: 84 de 96 pagamentos de
  folha, zero ambíguo.
- **Padrão de adapter com mTLS + OAuth2** — a Efí usa a mesma família do Inter; o
  `EfiClient` do desenho recebido entra quase inteiro em `adapters/efi.py`.
- **Beat de fechamento** às 08:40, que reconhece o pagamento no extrato sem ninguém
  voltar na tela.

## 6. O que falta construir, e em que ordem

Atualizado em 14/08/2026. Tudo o que **não** dependia das credenciais já está no ar:

| # | item | estado |
|---|---|---|
| 1 | `adapters/efi.py` no nosso padrão | ✅ feito |
| 2 | Conta `1.1.1.03` no plano + resolução no razão | ✅ feito |
| 3 | Coluna `banco` em `inter_payments` (D7 serve aos três) | ✅ feito |
| 4 | Estado **`DEVOLVIDO`** na máquina | ✅ feito |
| 5 | `efi_sync_service` — extrato diário | ⏳ precisa de credencial |
| 6 | Webhook com mTLS | ⏳ precisa de credencial |

Sobre o item 2: o mapa de contas era por **uuid** de `bank_accounts`, e esse uuid só nasce
quando a conta abre. Ficou resolvido por **código de banco** (`364`), então o extrato da
Efí escritura sozinho no dia em que a conta entrar — ninguém precisa voltar no código
para colar um identificador.

Sobre o item 3: a origem do pagamento viajava escondida num campo jsonb, sem validação, e
o executor mandava para o **Inter** qualquer valor que não fosse `cora` — um erro de
digitação pagaria pelo banco errado, de outro CNPJ. Agora há constraint no banco e erro no
roteador.

**Só faltam 5 e 6, e os dois dependem da credencial de homologação.** Nada vai para
produção antes do limite diário estar aprovado por escrito (seção 1).
