# Efí × Asaas — qual serve melhor para a folha da Patrimonial

Ambas as documentações navegadas com Playwright em 14/08/2026 (Efí: 14 páginas em
`dev.efipay.com.br`; Asaas: 16 em `docs.asaas.com`). Só o que a doc diz; onde não achei,
está escrito "não encontrado" — que é diferente de "não existe".

**O caso concreto:** pagar 54 pessoas por mês, R$94.394,91, saindo da conta da Conecta Mais
Patrimonial (CNPJ 66.014.833/0001-10), de dentro do Conecta PRO, sem aprovação em app.

---

## Comparação no que importa para folha

| | **Efí** | **Asaas** |
|---|---|---|
| **PIX de saída por chave** | ✅ `PUT /v3/gn/pix/{idEnvio}` | ✅ transferência por chave Pix |
| **Idempotência do envio** | ✅ **documentada no endpoint**: reenviar o mesmo `idEnvio` "garante que nenhum valor seja debitado mais de uma vez" | ⚠️ **não encontrada**. Há `externalReference` (identificador no seu sistema), mas a doc não promete deduplicação |
| **Validação de chave (DICT)** | ❌ não existe (varri os escopos) | ✅ **`Check Pix Key`** — devolve `ownerName`, `cpfCnpj`, banco, agência, conta |
| **Status do envio** | `EM_PROCESSAMENTO` → `REALIZADO` / `NAO_REALIZADO` / `DEVOLVIDO` | 7 eventos: `TRANSFER_CREATED`, `PENDING`, `IN_BANK_PROCESSING`, `BLOCKED`, `DONE`, `FAILED`, `CANCELLED` |
| **Consultar envio depois** | ✅ escopo `gn.pix.send.read` | ✅ (recuperar transferência) |
| **Autenticação** | certificado + OAuth2 (**mTLS**) — **mesma família do nosso adapter Inter** | API key em header |
| **Autenticação do webhook** | **mTLS por norma do Bacen** (chave pública da Efí no nosso servidor) + HMAC opcional; IP `34.193.116.226` | token no header `asaas-access-token` |
| **Limite diário pré-aprovado** | ⚠️ **R$0,30 (Pro) / R$1,00 (Empresas)** — precisa negociar aumento, e só conta Empresas pode alterar | **não encontrado na doc** — perguntar |
| **Homologação** | ✅ **gatilhos determinísticos por valor** (0,01–10 confirma; 10,01–20 rejeita por webhook; >20 rejeita na requisição; 4,00 gera duas devoluções; 5,00 gera uma) | sandbox com aprovar conta / confirmar pagamento |
| **Rate limit** | 500 req/s em PUT/POST | Token Bucket, com endpoint para consultar o saldo de chamadas |
| **Comprovante do pagamento** | ✅ `gn.receipts.read` | não encontrado |
| **Pagar QR de terceiro** | ✅ escopo `gn.qrcodes.pay` | não encontrado (tem QR estático para receber) |
| **Reenviar webhook perdido** | ✅ `POST /v2/gn/webhook/reenviar` | não encontrado |
| **Agendamento** | não encontrado | ✅ `scheduleDate` no payload |
| **Recorrência nativa** | não encontrado | ✅ `recurring` (só para Pix) |

---

## O veredito, e o raciocínio que leva a ele

As duas fazem o essencial: **PIX de saída por API, sem aprovação em app.** A escolha se
decide por duas capacidades, e a assimetria entre elas é o argumento inteiro:

**Idempotência do envio você NÃO consegue construir por fora.** Se o banco não deduplica,
uma falha de rede no meio da folha te deixa sem saber se aquele funcionário recebeu — e a
única saída é consultar antes de reenviar, o que é uma corrida perdida se a consulta também
falhar. A Efí resolve isso no protocolo: o `idEnvio` vai no path e o compromisso está escrito
na documentação.

**Validação de chave você CONSEGUE contornar.** Mandando para a **chave CPF**, quem não tiver
chave registrada devolve erro no envio — não paga errado, apenas falha e entra numa lista.
Auto-corretivo, e sem risco de cair em terceiro: chave CPF, se existe, pertence àquele CPF.

Ou seja: **a Efí tem o que não dá para compensar e não tem o que dá.** É o critério que
decide.

**Três reforços a favor da Efí, no nosso caso específico:**

1. **Autenticação idêntica à do Inter** (certificado + OAuth2, mTLS). Nosso `InterAdapter` já
   faz exatamente isso — o `EfiClient` reaproveita a estrutura. Com o Asaas seria API key em
   header: mais simples de escrever, mas um padrão a menos que já dominamos.
2. **Homologação determinística.** Poder disparar um R$4,00 e saber que virão duas devoluções
   é a diferença entre testar a máquina de estados e torcer por ela. Inclusive descobri assim
   que falta o estado `DEVOLVIDO` no desenho.
3. **Comprovante por API** (`gn.receipts.read`). Para folha, guardar o comprovante junto ao
   lançamento vale mais do que parece — é o documento que o funcionário pede.

**O que pesa a favor do Asaas, e não é pouco:** o ciclo de webhook é mais rico (sete eventos
contra o binário da Efí), tem agendamento e recorrência nativos, e a consulta de chave
resolveria de vez a incerteza sobre o cadastro dos 54.

---

## ⚠️ O que decide antes de qualquer código

**O limite diário da Efí é R$1,00 pré-aprovado.** A folha é R$94.394,91. Aumentar exige conta
**Efí Empresas** e negociação. Enquanto isso não estiver por escrito, a Efí é teórica.

**O limite do Asaas não está na documentação.** Não conclua que é melhor por isso — conclua
que não sabemos.

Então a primeira tarefa não é escolher: é **perguntar às duas, por escrito, qual limite
diário de envio elas aprovam para uma folha de R$95 mil/mês num CNPJ aberto em 2026 sem
histórico.** A resposta pode inverter todo o resto.

**Segunda pergunta, só para o Asaas:** a transferência é idempotente? Se reenviar a mesma
requisição com o mesmo `externalReference`, o dinheiro sai duas vezes? Se a resposta for
"sim, sai duas vezes", o Asaas está fora para folha — e aí a decisão fica simples.

---

## Recomendação

**Abrir as duas contas** — onboarding é barato e nenhuma cobra para existir. Depois:

1. Perguntar limite diário às duas, por escrito.
2. Perguntar idempotência ao Asaas, por escrito.
3. Com as respostas, **integrar a Efí primeiro** (aproveita o adapter do Inter e a
   homologação determinística), mantendo o Asaas como segunda opção já aberta.
4. Se o Asaas responder que a transferência é idempotente **e** liberar limite maior, ele
   passa na frente — porque aí soma idempotência com validação de chave, e não perde em nada.
