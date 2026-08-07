# Mapa da Orquestra — Conecta PRO (2026-08-07)

Como os módulos se tocam. Medido do código, não descrito de memória.

Quatro camadas que não existiam em lugar nenhum: **eventos** (quem avisa quem),
**imports** (quem depende de quem), **tabelas** (quem escreve, quem lê) e **tarefas de fundo**.

> **Validade.** Estrutura e acoplamento mudam devagar — este mapa serve por semanas.
> Contagens de rota mudam a cada commit. Com 4 terminais ativos em operacional, marketing,
> DP e financeiro, os números **desses quatro** nascem velhos. Regenerar comparando datas.

---

## 1 · A partitura — o barramento de eventos

`infrastructure/event_bus/bus.py` · Redis Streams · catálogo `EventTypes` com **102 eventos**.

```
102 declarados
 59 publicados por alguém
 25 fluem PONTA A PONTA (publicado E escutado)
 34 publicados NO VAZIO — ninguém escuta
 43 nunca referenciados
```

### A descoberta central: a orquestra tem um ouvinte só

**Dos 25 eventos que fluem, o GEDEON é o assinante em 22.**

```
people_management ─┐
operacional       ─┤
financial         ─┼──→  GEDEON   (kits, certidões, assinaturas)
fiscal            ─┤
health_occupational┘

people_management ──→ people_management   (CCT: cargo, reajuste, salário)
people_management ──→ operacional         (admitido, demitido)
dp.folha.fechada  ──→ financial + gedeon  ← o ÚNICO evento com 2 destinos distintos
```

Não é uma orquestra ainda. É **um solista com 22 microfones** — o GEDEON reage a quase tudo,
e quase nada mais reage a nada.

### Os 34 tocando para plateia vazia

Publicados e sem ouvinte. São justamente os que uma orquestra de verdade usaria:

| Evento | Publicado por | Quem deveria ouvir (hipótese) |
|---|---|---|
| `financeiro.pagamento.realizado` | financial | DP (baixa de folha), CRM (inadimplência) |
| `financeiro.inadimplencia.detectada` | financial | CRM (cobrança), jurídico |
| `crm.contrato.assinado` | crm | operacional (criar postos), financial (faturamento) |
| `crm.lead.convertido` | crm | financial |
| `operacional.turno.iniciado` / `.encerrado` | operacional | ponto, folha |
| `ponto.batida.registrada` | people_management | operacional (presença ao vivo) |
| `operacional.alocacao.criada` | operacional | DP, financeiro (custo do posto) |
| `dp.ponto.registrado` | people_management | operacional |
| `operacional.diarista.pagamento_processado` | operacional | financial |
| `saude.afastamento.iniciado` | people_management | operacional (cobertura), folha |

**São 34 fios cortados.** Cada um é um lugar onde hoje alguém sincroniza na mão, ou não
sincroniza. Ligar um subscriber é barato; a infraestrutura já está de pé e testada pelos 25
que funcionam.

---

## 2 · Quem depende de quem — imports entre módulos

**Mais dependidos** (quantos módulos importam):

| Módulo | Importado por |
|---|---:|
| `financial` | 13 |
| `crm` | 12 |
| `ai` | 11 |
| `integrations` | 10 |
| `people_management` · `empresas` · `operacional` | 9 |
| `notifications` · `government_integrations` · `gedeon` | 7 |

**Quem mais depende dos outros:** `ged` e `financial` (7 cada), `gestao`, `integrations`,
`crm`, `fiscal_contabil`, `bidding` (6 cada).

**Leitura:** `financial` é o nó mais central — mexer nele treme em 13 módulos. E é
bidirecional: importa 7 e é importado por 13.

---

## 3 · Quem escreve, quem só lê — direção do dado

```
218 tabelas com escritor identificado
175 com escritor ÚNICO   (dono claro)
 43 com DOIS OU MAIS escritores   ← risco
192 lidas por SQL sem escritor no código (legado, view, ou escrita via ORM)
```

### As tabelas com dois donos — onde uma mudança quebra o vizinho

| Tabela | Escrevem | Model declarado em |
|---|---|---|
| `ged_document_kits` | ai, client_portal, gdrive, ged, gedeon, people_management | people_management |
| `ged_kit_documents` | client_portal, ged, gedeon, integrations, people_management | people_management |
| `communication_notifications` | ai, fiscal_contabil, gedeon, notifications, operacional | operacional |
| **`employees`** | integrations, lgpd, people_management, security_lgpd | **operacional** ⚠️ |
| `ged_certidoes` | ged, gedeon, people_management | ged |
| `inter_lote_otp` | financial, integrations, people_management | *(sem model)* |
| `users` | lgpd, people_management, security_lgpd | *(sem model)* |
| `gp_justifications` | ai, integrations, people_management | people_management |
| `leads` · `proposals` · `crm_followups` | ai, crm, integrations | crm |

⚠️ **`employees` é o caso mais grave:** o model vive em `operacional`, mas quem escreve são
outros quatro módulos. Quem muda o schema não é quem sofre a consequência.

**Regra prática que sai daqui:** antes de mexer numa dessas 43, veja quem mais escreve.
As de escritor único (175) são seguras dentro do módulo.

---

## 4 · Trabalho de fundo — Celery

**194 entradas no beat schedule** · 6 filas: `gov`, `ged`, `integrations`, `operacional`,
`webhooks`, `maintenance`.

| Módulo | Tarefas |
|---|---:|
| integrations · crm | 28 cada |
| people_management | 21 |
| financial | 19 |
| government_integrations | 16 |
| gedeon | 12 |
| bidding | 11 · operacional 9 · notifications 8 |

**Por que importa:** o beat rodou 46 dias quebrado em silêncio (março/2026) porque um fix foi
copiado só para o container `backend`. Tarefa é o canal invisível — quando falha, ninguém vê.

---

## 5 · O que isso muda no trabalho módulo a módulo

**1. `financial` não é um módulo, é o centro.** 13 dependentes, 19 tarefas, 12 tabelas em
comum com operacional. Fechar financeiro isolado é ilusão.

**2. `gedeon` é o consumidor universal.** Qualquer evento novo provavelmente afeta o kit.
Mexeu em DP, fiscal, operacional ou saúde? O GEDEON escuta.

**3. As 43 tabelas de dois donos são a lista de "cuidado".** Vale conferir antes de qualquer
mudança de schema — a `finding-schema-drift` deveria consultá-las.

**4. Os 34 eventos no vazio são a maior oportunidade barata do sistema.** A infra está de pé,
provada por 25 fluxos vivos. Ligar `crm.contrato.assinado → operacional` é um subscriber, não
um projeto.

**5. `employees` com model fora do dono precisa de decisão** — não de código.

---

## Como regenerar

As medições estão nos comandos deste levantamento (grep + AST, sem LLM, ~2 min no total).
Guardar cada geração datada em `auditoria/orquestra/` e comparar: **o que mudou de
acoplamento entre duas datas é a informação de maestro.**

## O que este mapa NÃO cobre

- **Chamadas HTTP entre módulos** (se existirem) — só medi import, evento, tabela e task.
- **Se o fluxo funciona.** Um evento publicado e escutado pode ter handler quebrado. O mapa
  diz que o fio existe, não que passa corrente.
- **Frontend.** Qual tela chama qual módulo é outra medição.
- **As 192 tabelas lidas sem escritor SQL** — provavelmente escrita via ORM, não confirmei.
