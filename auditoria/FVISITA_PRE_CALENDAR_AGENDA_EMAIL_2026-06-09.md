# F-VISITA pré — Calendar / agenda / email (READ-ONLY)

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Mapear o que existe para "agendar visita técnica/comercial" (o objetivo final do agente WhatsApp) — sem duplicar.
- **Veredito:** **Já existe um módulo completo de visita/agendamento** (`modules/campo/` + tabela `visitas`, vazia) com vínculo a lead E cliente. **Google Calendar não existe** (só Drive). **Email envia de verdade** e está configurado (entrega não verificada).

---

## 1. Módulo de visita/agendamento JÁ EXISTE — `modules/campo/`
Tabela **`visitas`** (0 linhas). Stack completo: `models/visita.py`, `schemas/visita.py`, `repositories/visita_repository.py`, `services/visita_service.py`, `controllers/visita_controller.py`, + roteirização (`roteirizacao_*`).

Campos relevantes (cobrem agendar visita):
- **Agendamento:** `data_visita` (date), `horario_inicio`/`horario_fim` (time), `duracao_prevista_minutos`, `status`, `tipo`, `origem`, `numero`.
- **Vínculo:** **`cliente_id`** e **`lead_id`** (liga a cliente OU lead — ideal p/ o agente WhatsApp que cria Lead). `prospect_nome/telefone/email`, `contato_nome/telefone` (prospect sem cadastro).
- **Responsável:** `responsavel_id/tipo/nome`.
- **Local/execução:** `endereco/complemento/bairro/cidade/estado/cep`, `latitude/longitude`, `referencia`, `checkin_at`/`checkout_at` + geo de check-in.

➜ **Casa natural para "agendar visita". Não criar agenda nova.** Estrutura pronta, nunca usada (0 linhas).

## 2. Google Calendar — NÃO existe (só Drive)
- Buscas por Calendar casaram só com **Google Drive**: `modules/gdrive/` (`gdrive_service.py`, `gdrive_controller.py`), `people_management/ged/google_drive_service.py`, padrão `service_account`.
- **Nenhum uso real da Google Calendar API** (`build('calendar')`, events).
- ➜ Sync com Calendar = **novo**. Reaproveitável: padrão de auth **service-account** do Drive. A agenda interna já é a tabela `visitas`.

## 3. Email — envia de verdade e configurado
- `core/mailer.py`: `async send_email(to_email, subject, html_body)` via **smtplib** (TLS ou SSL conforme `SMTP_USE_TLS`). Early-return se `SMTP_HOST` vazio.
- Já consumido por `operacional/communication/services/notification_service.py` (linha 251).
- **Env do backend tem todas as `SMTP_*` SET:** `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`, `SMTP_USE_TLS` → **configurado** (não cai no early-return).
- ⚠️ **Caveat:** configurado ≠ entrega verificada (não enviei teste). Memória registra o **SMTP do Chatwoot** quebrado — é **outro** SMTP; o do `core/mailer` é independente.

## 4. Viabilidade "agendar visita pelo agente" (fatos)
| Necessidade | Status | Como |
|-------------|--------|------|
| Registrar visita | ✅ pronto | `visitas` via `campo/visita_service` (`lead_id`/`cliente_id`) |
| Prospect sem cadastro | ✅ pronto | `prospect_nome/telefone/email` na `visitas` |
| Confirmação por email | ✅ configurado* | `core/mailer.send_email` (*entrega não verificada) |
| Sync Google Calendar | 🔴 inexistente | novo (auth service-account do Drive reutilizável) |

## 5. DECISÕES (suas — não decidi escopo)
1. Agendar = gravar em **`visitas`** (reusar `campo`)? Confirmar que é a tabela/modelo certo (não inspecionei os métodos do `visita_service`).
2. Basta **agenda interna `visitas` + email**, ou quer **sync Google Calendar** (novo)?
3. O agente **cria a visita** (status "solicitada", humano confirma) ou só **sugere** (mantém copiloto)?
4. Confirmação por email via `core/mailer` — **validar entrega real** antes de prometer ao cliente?

---
*Read-only: greps em modules/core, `\d visitas` + contagem, leitura de `core/mailer.py`, presença de `SMTP_*` no env (sem valores). Nada implementado. Escopo aguardando sua definição.*
