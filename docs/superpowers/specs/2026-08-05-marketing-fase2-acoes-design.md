# Marketing — Fase 2 (ações de escrita) no redesign

> Spec + plano de implementação. Autor: T5. Data: 2026-08-05.
> Propriedade do módulo `marketing` transferida T3 → T5 (registrado em `auditoria/parity/DIVISAO_3T.md`).

## Problema

O módulo marketing do redesign tem **paridade de tela (7/7) e de leitura**, mas **zero paridade de ação**.

| | Rotas de marketing consumidas |
|---|---|
| Clássico | **12** |
| Redesign | **0** |

Os rótulos "Novo lead", "Gerar texto", "Nova campanha" no redesign são cabeçalho de tabela — não existe botão funcional por trás (falta `ctaTo`).

## Fato que define a solução

**O backend está completo.** `backend/modules/crm/controllers/marketing_controller.py` tem 20 rotas montadas, incluindo todas as escritas. **Nada de backend precisa ser escrito.**

E o frontend chama o endpoint **verbatim**: `fetch(scr.submit.endpoint, {headers: Authorization Bearer})` (`ModuleView.tsx:320,387,395` e `:219` para edit). Não há prefixo obrigatório `/redesign/action/*` — aquilo é convenção para ações que precisam de lógica nova, não exigência.

**Consequência:** aponta-se as ações direto para `/api/v1/marketing/*`. Zero backend, zero arquivo compartilhado, só `redesign_builders/marketing.py`. Regra 1 da paridade integralmente respeitada.

## Primitivos do framework (já existentes)

- `tbl(..., docsfn=, editfn=, actionsfn=)` — por linha: documentos, edição inline (PATCH), ações
- `editfn(r)` → `{endpoint, method, fields:[{key,label,type,value,options}]}` — FormScreen inline pré-preenchido
- `actionsfn(r)` → `[{title, endpoint, method, btnLabel, submitLabel, btnStyle, okMsg, fields:[]}]`
- Tela `type:"form"` → `{title, sub, cta, type:"form", submit:{endpoint, okMsg}, fields:[...]}`
- **`ctaTo`** — sem ele o `ModuleView` NÃO desenha o botão do CTA da tabela (`ModuleView.tsx:706`)

## Schemas reais (do controller — não inventar campo)

```
CampaignCreate:      name*, type="organic", budget=0, description, start_date, end_date,
                     utm_source, utm_medium, utm_campaign
MktLeadCreate:       name*, campaign_id, email, phone, whatsapp, source
CopywriterRequest:   formato*, briefing*, objetivo, publico, n_variacoes=3
EstrategistaRequest: objetivo*, periodo_dias=30, orcamento, canais_preferidos
ContentSaveRequest:  formato*, conteudo*, formato_label, titulo, observacao
ContentStatusRequest: status  (validado contra enum ContentStatus)
ContentSendWhatsappRequest: numero  (>=10 dígitos, via Baileys, 1 a 1)
```

## Mapa de wiring (o trabalho)

| Tela | Ação | Endpoint (já existe) | Primitivo |
|---|---|---|---|
| funil | Novo lead | `POST /api/v1/marketing/leads/` | tela form + `ctaTo` |
| campanhas | Nova campanha | `POST /api/v1/marketing/campaigns/` | tela form + `ctaTo` |
| campanhas | Editar | `PATCH /api/v1/marketing/campaigns/{id}` | `editfn` |
| campanhas | Excluir | `DELETE /api/v1/marketing/campaigns/{id}` | `actionsfn` |
| lead-magnet | Converter em cliente | `POST /api/v1/marketing/leads/{id}/convert` | `actionsfn` |
| biblioteca | Editar peça | `PATCH /api/v1/marketing/content/{id}` | `editfn` |
| biblioteca | Enviar WhatsApp | `POST /api/v1/marketing/content/{id}/send-whatsapp` | `actionsfn` (campo `numero`) |
| biblioteca | Aprovar / Arquivar | `PATCH /api/v1/marketing/content/{id}/status` | `actionsfn` |
| biblioteca | Excluir | `DELETE /api/v1/marketing/content/{id}` | `actionsfn` |
| copywriter | Gerar texto (IA) | `POST /api/v1/marketing/copywriter/generate` | tela form + `ctaTo` |
| estrategista | Nova estratégia (IA) | `POST /api/v1/marketing/estrategista/plan` | tela form + `ctaTo` |
| brand-voice | — | (clássico não tem escrita) | mantém leitura |

**Formatos do copywriter** vêm de `GET /copywriter/formats` — as opções do select devem sair de lá ou da mesma fonte, nunca hardcoded inventadas.

## Decisões

- **SQL das tabelas passa a trazer `id`** (hoje vários SELECT não selecionam id) — sem id não há ação por linha. O id não é exibido; entra só como `r[0]` para montar a URL.
- **Nada de gate OTP aqui.** Marketing não é dinheiro-que-sai. O `send-whatsapp` é human-in-the-loop por natureza (o operador digita o número e dispara 1 a 1).
- **Vazio honesto preservado.** As tabelas hoje têm 0 linhas reais (exceto leads). Ação por linha em tabela vazia simplesmente não aparece — não fabricar linha para demonstrar botão.
- **Órfãs não entram nesta fase:** `GET /leads/stats` e `POST /licitacao/convert-to-crm` não têm superfície em lugar nenhum. Reportadas, não wired (nenhuma tela do clássico as usa — não é gap de paridade).

## Verificação (obrigatória antes de dar como pronto)

1. `python3 -c "import ast; ast.parse(open('...marketing.py').read())"` — sintaxe
2. Deploy blue-green (timeout ≥600s, lock) → `curl /api/v1/redesign/data/marketing` retorna as 7 telas + as novas telas-form
3. Provar que cada `ctaTo` aponta para uma tela que existe no payload (senão botão morto)
4. **NÃO** disparar as ações de escrita em produção (criaria campanha/lead/WhatsApp real). Verificação = payload correto + endpoint responde 401/422 sem corpo válido, não 404.
5. Registrar no `CORRECOES.md` e marcar no checklist do `DIVISAO_3T.md`

## Fora de escopo (deliberado)

- Plataforma de vídeo / catálogo de mídia — o `content_drafts` + `biblioteca` + `send-whatsapp` já é o pipeline; vídeo entra como formato depois, não agora
- Conserto da skill `conecta-backend-recon` (referencia `scripts/backend_recon.py` inexistente) — reportado, item separado
- Backend novo de qualquer espécie
