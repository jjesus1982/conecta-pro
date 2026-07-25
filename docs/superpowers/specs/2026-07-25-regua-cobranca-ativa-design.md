# Régua de cobrança ATIVA (gated) — Design (spec)

**Data:** 2026-07-25 · **Onda 2 "COMPLETAR", sub-projeto 2** · Aprovação: PENDENTE — Jordan revisa (é dinheiro/comunicação a cliente real; execução precisa dos gates dele)

## Goal
Transformar a régua de **read-only** (só gera o texto) em **ativa-GATED**: computar a **fila de cobrança** (quem está vencido, dias de atraso, tier, canal, mensagem pronta), o humano **revisa e dispara** (por item ou lote) com confirmação, e o sistema **registra a tentativa**. **NUNCA disparo automático a cliente** — sem beat que manda mensagem sozinho.

## Fato que funda o design (investigado)
- `collection_negotiator.py`: já classifica por dias de atraso → tier + prioridade + canal (`_NIVEIS`, `_classificar`) e monta a **mensagem** (`_MENSAGENS`: lembrete D1-5 · contato D6-15 · notificação D16-30 · negativação iminente D31-60 · jurídico D61+). Read-only hoje (retorna ações, não envia).
- Canal de envio existe: `whatsapp_service.send_template_message(tenant_id, template_name, variables)`. E-mail e re-emissão de boleto/PIX (Inter) também disponíveis.
- Registro: `receivable_accounts` já tem `collection_attempts`, `last_collection_date`, `next_collection_date`, `collection_notes`. Tabela `collection_attempts` dedicada NÃO existe (uso as colunas).
- Hoje **inadimplência = 0** → a fila nasce **vazia** (honesto); a capacidade é pra quando houver atraso.

## Global Constraints (inegociáveis)
- **Money/comms-out a cliente real = gate humano SEMPRE.** Nunca disparo silencioso; nunca testar o caminho feliz (não enviar de verdade a cliente em teste).
- Nunca fabricar: fila = recebíveis realmente vencidos (due<hoje, status não pago/cancelado). Vazio real = "sem inadimplência".
- Negativação/protesto (Serasa/SPC) = **não** automatizar nesta spec (é legal/sério); o tier só **sinaliza** elegibilidade.
- Deploy blue-green (lock — esperar liberar). Oráculo. Sempre planejar com superpowers.

## Arquitetura (3 unidades)

### Unidade 1 — `montar_fila_cobranca(db) -> list` (read-only)
Recebíveis vencidos (due<hoje, status NOT IN pago/cancelada), com: cliente, valor, dias de atraso, **tier** (via `_classificar`), canal sugerido, **mensagem pronta** (via `_MENSAGENS`), `collection_attempts` atual, `last_collection_date`. Ordena por prioridade/dias. Reusa o `collection_negotiator` (não duplica os tiers).

### Unidade 2 — Ação GATED `disparar_cobranca(receivable_id | lote, canal)` 
- Confirmação humana obrigatória: "isto ENVIA cobrança ao cliente X pelo canal Y". 
- Envia pelo canal real (WhatsApp template / e-mail / re-emitir boleto+PIX). Anti-spam: bloqueia se `last_collection_date = hoje` (não recobra 2x no dia).
- **Registra**: `collection_attempts += 1`, `last_collection_date = now`, append `collection_notes` (tier, canal, timestamp, quem disparou), `next_collection_date` = hoje + intervalo do tier.
- Resposta honesta: enviado/erro real do canal (não inventa sucesso).
- Negativação (tier D31-60): NÃO envia a Serasa; retorna "elegível a negativação — ação manual/externa".

### Unidade 3 — Telas redesign (grupo Receber)
- **"Fila de cobrança"** (tabela read-only): a fila da Unidade 1 (tier colorido, dias, mensagem preview). Com inadimplência 0 → "Sem cobranças pendentes — todos em dia".
- **Ação "Disparar cobrança"** (form gated, por cliente): seleciona recebível + canal + confirma → Unidade 2. Sem lote automático na v1 (batch só depois, com dupla confirmação).

## Data flow
`receivable_accounts` (vencidos) + `collection_negotiator` (tiers/mensagem) → `montar_fila_cobranca` → tela Fila (read). Disparo gated → `disparar_cobranca` → canal real (WhatsApp/e-mail/Inter) + grava tentativa em `receivable_accounts`.

## Error handling
- Canal indisponível/erro → mensagem real do canal; NÃO marca tentativa como enviada.
- Recobrança no mesmo dia → bloqueada (anti-spam).
- Cliente sem WhatsApp/e-mail cadastrado → cai pro próximo canal ou sinaliza "sem contato".

## Testing / Oráculo
- Fila = query de vencidos (exibido == banco). Hoje 0 (inadimplência zerada) → tela mostra "todos em dia".
- **NUNCA** disparar de verdade a um cliente em teste. Verificar o disparo só com: (a) validação de que a rota exige confirmação (sem confirm → não envia), (b) anti-spam (2º disparo no dia bloqueia), (c) registro incrementa `collection_attempts` — testável com um recebível de teste isolado (não um cliente real), ou stub do canal.

## Pré-mortem
- **A.** Disparo automático acidental spamma clientes. *Mit.:* SEM beat; gate humano por item; anti-spam mesmo-dia; v1 sem lote.
- **B.** Marca "enviado" sem o canal confirmar → cliente não recebe mas o sistema acha que sim. *Mit.:* só registra tentativa após retorno OK real do canal.
- **C.** Negativação automática (dano ao cliente/legal). *Mit.:* tier só sinaliza; negativação é ação externa manual — fora da automação.
- **D.** Mensagem com dado errado (valor/dias) → cobrança indevida. *Mit.:* fila mostra o preview exato antes do disparo; valor vem do recebível real.
- **E.** Testar o caminho feliz envia a cliente real. *Mit.:* nunca; só recebível de teste isolado ou stub.
- **F.** Cobrar quem já pagou (recebível não baixado). *Mit.:* fila só de status não-pago; a conciliação por líquido (84%) já reduz falso-vencido; recomendar rodar conciliação antes.

## Escopo / fora
- **Nesta spec:** fila (read), disparo gated por-item (WhatsApp/e-mail/re-emitir), registro da tentativa, anti-spam.
- **Fora (próximas):** lote com dupla confirmação; integração Serasa/SPC (negativação real); régua com agendamento (beat) — só se Jordan quiser e com salvaguardas; acordos/renegociação (outro sub-projeto).
