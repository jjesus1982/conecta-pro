# Efí — o que a documentação REAL diz (navegada, não suposta)

Explorado em 14/08/2026 com Playwright em `dev.efipay.com.br/docs/api-pix` — 14 páginas.
Tudo aqui saiu da documentação renderizada; onde não achei, está escrito.

---

## 1. ⚠️ O bloqueador que ninguém tinha visto: o limite diário

> *"Ao consumir o endpoint de envio de Pix, em produção, fique atento aos seguintes **limites
> diários pré-aprovados** de cada conta: **Contas Efí Pro: R$ 0,30** — Para você mesmo ou
> contatos seguros. **Contas Efí Empresas: R$ 1,00** — Para você mesmo ou contatos seguros.
> É um requisito do endpoint, que tenha conta do tipo **Efí Empresas** para realizar
> alterações nos limites de envio."*

Fora da caixa, a Efí envia **um real por dia**. A folha da Patrimonial é **R$94.394,91/mês**.

Isso não mata o plano — move o caminho crítico. **A primeira tarefa não é código: é abrir
conta Efí Empresas e negociar o limite diário.** Enquanto o limite não subir, nenhuma linha
do que for escrito serve para produção. E "contatos seguros" sugere que favorecido novo pode
ter tratamento distinto — confirmar o que qualifica um favorecido como seguro e quanto tempo
leva.

---

## 2. O que está CONFIRMADO e é bom

**Cash-out existe e é idempotente por desenho.** A própria doc diz, sobre
`PUT /v3/gn/pix/:idEnvio`:

> *"O endpoint é idempotente. Se uma transação não for concluída com sucesso (por exemplo,
> devido a falha de comunicação ou tempo de resposta excedido), você deve reenviar a
> requisição utilizando o mesmo identificador (idEnvio). O sistema reconhecerá que se trata
> da mesma operação e garantirá que **nenhum valor seja debitado mais de uma vez**."*

O desenho apostou nisso sem ter lido. A aposta estava certa, e agora tem fonte.

**Os literais de status que o desenho chutou estão certos:** `EM_PROCESSAMENTO`,
`REALIZADO`, `NAO_REALIZADO`, `DEVOLVIDO`. O `_STATUS_MAP` não precisa de ajuste.

**Rate limit: 500 requisições por segundo** em PUT/POST. O `MAX_WORKERS = 5` do desenho é
conservador por três ordens de grandeza — 54 pagamentos de folha não chegam perto.

**Escopos disponíveis** (da página de credenciais):

| escopo | o que dá |
|---|---|
| `pix.send` | **enviar Pix** |
| `gn.pix.send.read` | **consultar Pix enviado** ⭐ resolve o cego do Cora (404 pós-aprovação) |
| `gn.qrcodes.pay` | **pagar QR Code Pix** ⭐ pagar QR de terceiro — o Cora não tem |
| `gn.receipts.read` | **baixar comprovante Pix** ⭐ prova documental do pagamento |
| `gn.balance.read` | consultar saldo |
| `gn.reports.write/read` | relatórios (extrato de conciliação) |
| `webhook.write/read` | configurar webhook |
| `gn.pix.evp.write/read` | chaves aleatórias |
| `gn.split.read/write` | split de pagamento |
| `lotecobv.read/write` | lote de cobrança com vencimento (recebimento) |
| `gn.infractions.*` | MED (infrações) |

**Endpoints úteis além do envio:**
- `POST /v2/gn/relatorios/extrato-conciliacao` — extrato (assíncrono: pede e depois consulta)
- `POST /v2/gn/webhook/reenviar` — **reenviar webhook perdido** ⭐ rede extra que o Cora não dá
- `POST /v2/gn/qrcodes/detalhar` — ler um QR antes de pagar
- `PUT /v2/lotecobv/` — lote de cobrança com vencimento (lado de receber)

---

## 3. Homologação com gatilhos determinísticos ⭐

Isto vale ouro para construir sem medo — o ambiente de teste responde **pelo valor**:

| valor enviado | o que acontece |
|---|---|
| R$0,01 a R$10,00 | Pix **confirmado**, resultado vem por webhook |
| R$10,01 a R$20,00 | Pix **rejeitado**, resultado vem por webhook |
| acima de R$20,00 | Pix **rejeitado já na requisição** (não vem webhook) |
| **R$4,00** | gera **duas devoluções** de R$2,00 |
| **R$5,00** | gera **uma devolução** de R$5,00 |

Dá para exercitar toda a máquina de estados — inclusive devolução, que o desenho não previu —
sem depender de sorte. O teste de homologação vira determinístico, não "vamos ver o que
acontece".

**Consequência para o desenho:** falta o estado **`DEVOLVIDO`**. Um Pix pode ser enviado,
liquidado e depois devolvido. Hoje `LIQUIDADO` é terminal e não há caminho de volta.

---

## 4. O que continua sem resposta

**DICT / consulta de chave: NÃO EXISTE.** Varri a lista de escopos inteira — não há nada de
consulta de chave. Igual ao Cora. A mitigação segue a que já definimos: mandar para a chave
CPF e tratar a falha como lista (quem não tem chave CPF devolve erro, não paga errado).

**Webhook exige mTLS por norma do Bacen** — e isso é infraestrutura, não código:

> *"Por norma do Banco Central, será necessário a inserção de uma **chave pública da Efí no
> seu servidor** para que a comunicação obedeça o padrão mTLS."*

Além disso: HMAC opcional como parâmetro na URL, o parâmetro `ignorar=` impede a Efí de
anexar `/pix` ao fim da URL cadastrada, e o **IP de origem é `34.193.116.226`**.

⚠️ E um requisito que o desenho não menciona: **a chave Pix do pagador precisa ter um webhook
associado a ela** para o envio funcionar. Não é opcional.

---

## 5. Correções ao desenho recebido

| item | veredito |
|---|---|
| `PUT /v3/gn/pix/{idEnvio}` idempotente | ✅ **confirmado na doc** |
| `_STATUS_MAP` (REALIZADO/NAO_REALIZADO) | ✅ **correto** |
| `MAX_WORKERS = 5` | ✅ folgadíssimo (limite é 500 req/s) |
| Estado `DEVOLVIDO` | ❌ **falta** — Pix liquidado pode ser devolvido |
| Webhook na chave do pagador | ❌ **falta** — é pré-requisito do envio |
| mTLS do webhook | ⚠️ está como TODO; é norma do Bacen, não opcional |
| Limite diário | ⚠️ estava como TODO; **é o bloqueador nº 1** |
| DICT | ❌ não existe — mitigação por chave CPF confirmada como único caminho |
| `gn.receipts.read` (comprovante) | ➕ não estava no desenho; vale guardar como prova |
| `POST /v2/gn/webhook/reenviar` | ➕ não estava; rede extra para webhook perdido |

---

## 6. Ordem de execução

1. **Abrir conta Efí Empresas no CNPJ 66.014.833/0001-10** (o mesmo do Cora) e **negociar o
   limite diário** para acomodar R$95 mil de folha. Sem isso, o resto não roda.
2. Credenciais de **homologação** + certificado. Rodar os gatilhos determinísticos da §3 —
   confirma o payload real de envio e do webhook de uma vez.
3. Só então o código: adapter `efi.py` ao lado de `inter.py` e `cora.py`, coluna `banco` em
   `inter_payments`, `efi_sync_service` para o extrato, e o estado `DEVOLVIDO` na máquina.
4. Infra do webhook: chave pública da Efí no servidor (mTLS), HMAC na URL, liberar o IP
   `34.193.116.226`.
