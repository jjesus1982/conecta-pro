# F-C.1 pré — Fontes de NFS-e/boleto + envio de mídia no WhatsApp (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear o que já existe para (futuramente) enviar nota/boleto ao cliente pelo WhatsApp — sem duplicar.
- **Veredito:** **Boleto** é enviável hoje como **texto** (link+PIX+linha digitável já gerados pelo Inter). **NFS-e** está **bloqueada** (sem link/PDF: `link_nfse` 0/27). Enviar **arquivo (PDF)** exige **método novo** (o service do WhatsApp só manda texto/JSON).

---

## 1. NFS-e (`nfses`) — dados sim, documento não
- **27 notas**, **11 CNPJs** distintos (tomadores).
- **Busca:** `tomador_cpf_cnpj` (14 díg) + `data_competencia` (date) / `data_emissao`. Campos: `numero_nfse`, `codigo_verificacao`, `valor_servicos`, `descricao_servico`, `status`, `condominio_id`, `prestador_cnpj`.
- ⚠️ **`link_nfse` preenchido em 0/27** — não há URL nem PDF da nota persistido. 27/27 têm `numero_nfse`/`codigo_verificacao`.
- ➜ Para "enviar a nota" faltaria **o documento**: persistir `link_nfse` na emissão **ou** buscar/gerar o PDF na prefeitura de Manaus. **Lacuna de DADO/documento, não de busca.**

## 2. Banco Inter — cobrança/boleto JÁ EXISTE (reusar)
`modules/integrations/inter/` (pacote completo): `client.py`, `cobranca_service.py`, `conciliacao_service.py`, `inter_sync_service.py`, `token_cache.py`, `schemas.py`, `exceptions.py`, `inter_controller.py`. Adapters em `banking/adapters/inter.py` (+ `cora.py`); `gedeon/inter_comprovante_service.py`.
- **`cobranca_service.py` (D6.3):**
  - **`emitir(...)`** → adapter `generate_boleto` → retorna e persiste **`url_boleto` (linkBoleto), `pix_copia_cola` (pixCopiaECola), `linha_digitavel`, `barcode`**, status.
  - **`listar(...)`** → devolve `status, pagador, url_boleto, pix_copia_cola, barcode, linha_digitavel, descricao, created_at`.
  - `sincronizar_status()` + `get_boleto(...)`.
- ➜ **Boleto enviável HOJE como TEXTO** (link + PIX copia-e-cola + linha digitável já existem por cobrança). **Sem upload de arquivo.**
- 🧹 Leftover a limpar um dia: `banking/adapters/inter.py.bak.t2nome`.

## 3. Envio pelo WhatsApp (Chatwoot `connectors/whatsapp/service.py`) — só TEXTO
- `_api(...)` usa **`json=body`** (application/json) — **sem multipart/attachment**.
- `_send_message(phone, message)` manda texto. `send_nfse_notification`/`send_kit_notification`/`send_certificate_alert`/`send_custom` → todos chamam `_send_message` com string. `_resolve_contact` robusto (cria/busca/source_id).
- ➜ **Arquivo real (PDF) = método NOVO**: `aiohttp.FormData` multipart no endpoint de mensagens do Chatwoot (`attachments[]`). **Link/PIX como texto** = já funciona.

## 4. Matriz de viabilidade (fatos)
| Enviar | Hoje? | Como |
|--------|-------|------|
| Boleto: link + PIX + linha digitável | ✅ texto | `cobranca_service.listar/emitir` → `_send_message` |
| Boleto: PDF (arquivo) | ⚠️ método novo | multipart Chatwoot (`attachments[]`) |
| NFS-e: link | 🔴 bloqueado | `link_nfse` 0/27 — persistir/gerar antes |
| NFS-e: PDF | 🔴 bloqueado | falta documento + método multipart |

## 5. DECISÕES (suas — não decidi escopo)
1. Boleto como **texto** (link + PIX) — rápido — ou **PDF anexado** (exige método multipart novo)?
2. NFS-e: passar a **persistir `link_nfse`** na emissão (ou buscar na prefeitura) antes de cogitar envio?
3. Envio parte do **agente** (copiloto sugere/anexa) ou de **endpoint/ação manual** (botão "enviar boleto" no CRM)?

---
*Read-only: `\d nfses` + contagens, `find`/`grep` em `modules/integrations/inter`, leitura de `cobranca_service.py` e `connectors/whatsapp/service.py`. Nada implementado. Escopo aguardando sua definição.*
