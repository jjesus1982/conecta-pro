# Folha em lote via Efí — desenho técnico (Conecta PRO)

**Contexto.** A conta operacional da Conecta Mais **Patrimonial** recebe no Cora e
é abastecida via 2–3 transferências grandes/mês para a Efí. A **folha** é paga a
partir da Efí, em lote, pela API, de dentro do Conecta PRO — **sem aprovação em
app** (a Efí liquida PIX de saída direto pela API; foi o que destravou este desenho).

Este documento cobre só o **pagamento de saída (cash-out) via Efí**. Cobrança
(Bolix) é outro fluxo.

---

## 1. Componentes

| Arquivo | Papel |
|---|---|
| `schema.sql` | DDL PostgreSQL (fonte da verdade da migração) |
| `models.py` | ORM SQLAlchemy espelhando o schema |
| `efi_client.py` | Adapter Efí: OAuth+mTLS, `enviar_pix_por_chave`, `consultar_por_id_envio` |
| `payroll_service.py` | Autorização do lote, orquestração, reconciliação |
| `webhook.py` | Recebe status de PIX enviado, idempotente |

Stack: FastAPI + PostgreSQL + httpx (mTLS). Mesmo formato do adapter Inter →
reaproveitamento alto (troca base_url, credencial e o shape de payload).

---

## 2. Fluxo

```
RH monta lote (N itens)            Conecta PRO                 Efí
        │                              │                        │
        │ 1. cria lote + itens         │                        │
        │    (status RASCUNHO)         │                        │
        │─────────────────────────────>│                        │
        │ 2. autorizar_lote (OTP)      │                        │
        │    guard: Σ itens == total   │                        │
        │─────────────────────────────>│ status AUTORIZADO      │
        │ 3. executar_lote             │                        │
        │    loop c/ 5 workers         │                        │
        │                              │  PUT /v3/gn/pix/{idEnvio} (por item)
        │                              │───────────────────────>│
        │                              │  202 {e2eId, EM_PROC.}  │
        │                              │<───────────────────────│
        │                              │  item -> PROCESSANDO    │
        │                              │                        │  (liquida)
        │                              │  webhook {REALIZADO}    │
        │                              │<───────────────────────│
        │                              │  item -> LIQUIDADO      │
        │  reconciliar_pendentes (cron): consulta idEnvio dos presos em PROCESSANDO
```

---

## 3. Máquina de estados do pagamento

```
PENDENTE ─claim─> ENVIANDO ─202─> PROCESSANDO ─webhook REALIZADO─> LIQUIDADO ✔
   ▲                 │                  │
   │                 │                  └─webhook NAO_REALIZADO──> FALHOU ✖
   │           erro rede/5xx/429
   │                 ▼
   └──── ERRO_ENVIO (retry com MESMO idEnvio) 
                     │
              erro 4xx negócio
                     ▼
                  FALHOU ✖
```

Terminais: `LIQUIDADO`, `FALHOU`. `FALHOU` **não** é reprocessado no mesmo lote
(pode ter sido rejeição de negócio); vira item de um novo lote de correção,
com **novo idEnvio**.

---

## 4. As três garantias que folha exige

**a) Nunca pagar duas vezes.** Três camadas:
- `idEnvio` **determinístico** = `CP{lote}L{favorecido}F`. Reprocessar o mesmo
  item manda o mesmo idEnvio; a Efí deduplica no lado dela.
- `UNIQUE(id_envio)` e `UNIQUE(lote_id, favorecido_id)` no banco.
- Claim atômico `SELECT … FOR UPDATE SKIP LOCKED`: dois workers/processos nunca
  pegam o mesmo item.

**b) Nunca disparar lote não conferido.** `autorizar_lote` aborta se
`Σ valor_centavos != total_esperado_centavos` (divergência de 1 centavo já
barra) e exige OTP interno. `executar_lote` se recusa a rodar lote fora de
`AUTORIZADO`.

**c) Falha de rede ≠ falha de pagamento.** Erro **antes** de confirmar → `ERRO_ENVIO`
(retryável com mesmo idEnvio). Erro 4xx de negócio → `FALHOU` (não retry cego).
A chamada de rede acontece **fora** da transação — não seguramos lock durante I/O.

---

## 5. Modos de falha e cobertura

| Falha | O que acontece | Cobertura |
|---|---|---|
| Timeout no envio (não sei se a Efí recebeu) | `ERRO_ENVIO` | Retry com mesmo idEnvio → Efí deduplica |
| Webhook perdido | Item fica `PROCESSANDO` | `reconciliar_pendentes` consulta por idEnvio |
| Webhook duplicado | — | `dedup_key` (e2e+status) descarta |
| Processo cai no meio do lote | Itens ficam `ENVIANDO`/`PENDENTE` | Reexecutar o lote retoma só o que faltou |
| Chave PIX errada | `FALHOU` (4xx) | Vai pro relatório de exceções; ver DICT abaixo |
| Saldo insuficiente na Efí | `FALHOU` | Guard de saldo pré-lote (recomendado, TODO) |

---

## 6. Segurança e compliance

- **Certificado**: `.pem`/`.p12` **nunca no repositório**. Secret manager ou
  volume cifrado; caminho via env. Sem log de chave/segredo.
- **OTP interno** antes do disparo (você já faz isso no Inter). O controle de
  aprovação é *seu*, não da Efí.
- **Auditoria**: toda transição grava em `pagamento_evento` (origem: api /
  webhook / reconciliacao). Rastreável pra RH e fiscal.
- **Webhook**: autenticar a origem (mTLS ou HMAC) **antes** de processar.
- **Limite/teto**: aplicar teto por lote e por item no `autorizar_lote`
  (TODO — depende do teto diário que a Efí liberar; ver §8).

---

## 7. ⚠️ Lacunas vs. Inter (assumir e mitigar)

1. **DICT (validação de chave) — não encontrado na doc de envio da Efí.**
   No Inter você valida nome/documento do favorecido antes de pagar. Aqui,
   mitigação: validar a chave **no cadastro do funcionário** (`favorecido.
   chave_validada_em` + `chave_nome_bacen`) e **congelar** o snapshot no item do
   lote. Se a Efí expuser consulta de chave, plugar em `EfiClient` e conferir
   `documento` esperado × retornado antes de cada envio. **Confirmar com a Efí.**
2. **Sem lote nativo.** O lote é orquestração nossa (loop). Sem impacto de custo
   (PIX de saída é grátis), só de implementação.

---

## 8. Itens a confirmar no SANDBOX antes de produção

- [ ] Shape exato do corpo de `PUT /v3/gn/pix/{idEnvio}` e do retorno (nomes de campos).
- [ ] Literais de `status` (assumi `REALIZADO`/`NAO_REALIZADO`) — ajustar `_STATUS_MAP`.
- [ ] Payload real do **webhook de envio** e como autenticar a origem.
- [ ] Charset/limite de `idEnvio` (assumi `[A-Za-z0-9]`, ≤35).
- [ ] Existe **consulta de chave (DICT)**? (lacuna §7.1)
- [ ] **Teto diário de cash-out** da conta (IP costuma começar baixo — R$137k/mês
      de folha pode esbarrar).
- [ ] Rate limit da API → ajustar `MAX_WORKERS`.

---

## 9. Fora do código, mas parte do desenho

- **Mesmo CNPJ.** Conta Cora e conta Efí devem ser o **mesmo CNPJ (Patrimonial)**.
  Senão a transferência Cora→Efí mistura caixa entre empresas — problema
  contábil/fiscal, não técnico.
- **Sem FGC.** Efí é instituição de pagamento. Não estacione reserva lá: receba/
  pague e **varra o excedente para um banco pleno** (proteção + rendimento).
- **Ponte Cora→Efí.** 2–3 transferências grandes/mês, com aprovação manual no app
  do Cora — aceitável nessa frequência. Não tente automatizar isso via PIX do
  Cora (não existe por API) nem via TED sem contar a aprovação no app.
