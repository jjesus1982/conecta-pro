# Obrigações Acessórias Fiscais no Conecta PRO — Design

**Data:** 2026-07-25 · **Autor:** T1 (financeiro) · **Aprovado por:** Jordan (arquitetura + decomposição + ordem)

## Objetivo
Trazer para o Conecta PRO a **geração, validação, assinatura, rastreamento (prazo/status) e
guarda** de todas as obrigações acessórias fiscais dos 2 CNPJs — hoje no colo do contador.
"Tudo no sistema": o ERP produz o arquivo/dados oficiais; o **upload final** é 1 clique no
canal do governo (PVA/portal), pois a Receita não expõe web service para SPED.

## Decisões do Jordan (travadas)
1. **Escopo de transmissão = gerar+validar+assinar.** O ERP produz o arquivo oficial assinado
   (cert A1) e valida (0 erros); o envio final é humano no PVA/portal. Sem robô gov.br (evita
   captcha/WAF/fragilidade). O arquivo fica 100% no sistema.
2. **Fonte da verdade = Domínio (contador).** A contabilidade completa e fechada mora no
   Domínio. O ERP **puxa via API** (`DOMINIO_API_URL=https://api.dominiosistemas.com.br`, key
   configurada, "podemos puxar qualquer documento") e espelha num razão-espelho read-only
   (marcado origem=dominio), do qual os geradores produzem os arquivos.

## Arquitetura
```
Domínio (razão completo, fechado) --API--> Conecta PRO: IMPORTADOR --> razão-espelho (read-only)
                                                                              |
        +--------------+--------------+---------------+--------------+--------+
        ECD            ECF            EFD-Contrib      DEFIS          PGDAS-D
     (LR anual)     (LR anual)      (LR mensal)    (Simples anual)  (Simples mês)
        cada gerador: .txt/dados oficiais + VALIDA (0 erros) + ASSINA (cert A1)
                                    |
                    você sobe no PVA/portal (1 clique) · ERP rastreia prazo+status+guarda
```

## Fundação existente (reuso, não do zero)
- `integrations/connectors/dominio/connector.py` — client Domínio (hoje **push-only**:
  `exportar_lancamentos`). #0 adiciona os **GET de pull**.
- `government_integrations/services/sped_contabil_service.py` — gerador **ECD** real (lê
  `accounting_entries`, blocos I050/I150/I155). Molde de ECF/EFD-Contribuições.
- `government_integrations/core/sped_manager.py`, `core/simples_nacional.py` — núcleo SPED/Simples.
- `financial/models/sped_file.py`, `fiscal_obligation.py` — modelos de arquivo/obrigação.
- `financial/agents/tax_calculator.py` — apuração DAS (Simples) e Lucro Real, já ligada à receita real.
- Cert A1 real presente (`/app/credentials/certificates/certificado.pfx` + `patrimonial.pfx`).

## Decomposição em sub-projetos (cada um: spec própria → plano → executa)
| # | Sub-projeto | Depende | CNPJ/Regime | Estado da fundação |
|---|---|---|---|---|
| **0** | Importador Domínio → razão-espelho | API Domínio | ambos | connector push existe; falta pull |
| 1 | ECD (contábil) | #0 | Eletrônica LR | gerador existe (validar/assinar/expor) |
| 2 | ECF (fiscal IRPJ/CSLL) | #0, #1 | Eletrônica LR | apuração existe; gerador novo |
| 3 | EFD-Contribuições (PIS/COFINS mensal) | #0 | Eletrônica LR | molde SPED; gerador novo |
| 4 | DEFIS (anual) | receita Simples | Patrimonial | core simples_nacional |
| 5 | PGDAS-D declaração | — | Patrimonial | estende DAS já entregue |

**Ordem:** #0 → #1 → #2 → #3 (Eletrônica) → #4 → #5 (Patrimonial).

---

## Sub-projeto #0 — Importador Domínio → razão-espelho (detalhado)

### Propósito
Puxar da API do Domínio o razão contábil completo (e documentos fiscais) e materializar um
**razão-espelho read-only** no ERP, marcado `origem='dominio'`, do qual todos os geradores leem.
NÃO substitui o razão interno (`accounting_entries` origem ERP) — é uma tabela/escopo separado
(ou coluna `fonte`) para não misturar o que o ERP apura com o que o contador fechou.

### ⚠️ Descoberta 2026-07-25 (read-only, muda o vetor de pull)
O `DOMINIO_API_URL=https://api.dominiosistemas.com.br` **NÃO resolve DNS** (host inexistente —
placeholder). O vetor REAL de pull é a **Onvio** (nuvem Thomson Reuters que hospeda o Domínio):
`onvio.com.br`/`api.onvio.com.br` resolvem, e o ERP **já** tem auth Onvio (`gedeon/onvio/
onvio_auth.py`, OIDC) + já puxa documentos (`guia-onvio/{fonte}/{id}/pdf`, migration
`sprint82_gedeon_fase3_onvio_sync`, `onvio_document_id`). Portanto o #0 REUSA a Onvio, não o
REST fantasma. Onvio hospeda DOCUMENTOS (o contador sobe ECD/guias/relatórios lá) → o importador
puxa o **ECD (.txt SPED)** do document center da Onvio e parseia os blocos I (fallback do spec
vira o caminho principal). PENDENTE do Jordan: confirmar credenciais Onvio válidas + que o ECD/
razão está disponível no document center do contador (auth Onvio é OIDC, pode exigir passo humano).

### Componentes
1. **Pull via Onvio** (reusar `gedeon/onvio/onvio_auth.py` + padrão `guia-onvio`), NÃO o
   `connectors/dominio` (URL morta). Métodos read-only:
   - `puxar_razao(cnpj, dt_ini, dt_fim)` → lançamentos contábeis (data, D, C, valor, histórico, conta).
   - `puxar_plano_contas(cnpj)` → contas (código, nome, natureza) — já há rota de plano de contas.
   - `puxar_documento(cnpj, tipo, periodo)` → documentos genéricos (balancete, ECD, etc.).
   - Descoberta dos endpoints exatos = Task 1 do plano (testar API viva; usar `endpoints_to_try`
     do `check_connectivity` como pista). Se a API não expor razão estruturado mas sim o ECD.txt,
     o importador parseia o ECD (blocos I) — fallback documentado.
2. **Razão-espelho**: persistir em `accounting_entries` com `fonte='dominio'` + `empresa_id`
   (multi-CNPJ), OU tabela dedicada `razao_espelho_dominio` se o schema exigir isolamento.
   Idempotente por `documento_ref` (ex.: `DOM-{cnpj}-{periodo}-{hash}`). Marcado read-only.
3. **Serviço de sync** `dominio_import_service.importar_razao(empresa_id, periodo)`:
   pull → normaliza → upsert idempotente → retorna {contas, lançamentos, período, batia?}.
4. **Tela redesign** (g-fiscal): "Espelho contábil (Domínio)" — status da última sincronização,
   nº de lançamentos por período, botão gated "Sincronizar Domínio" (pull, não move dinheiro).
5. **Oráculo**: nº de lançamentos importados == nº na resposta da API; soma D == soma C (partida
   dobrada fecha). Se a API vier vazia/fora, sinaliza "aguardando dado" honesto (nunca fabrica).

### Isolamento e segurança
- **Read-only**: o importador só LÊ do Domínio e ESCREVE no espelho. Nunca escreve no Domínio
  (o push existente é outro fluxo, fora deste escopo).
- **Multi-CNPJ**: escopa por `empresa_id`; Eletrônica e Patrimonial não se misturam.
- **Não colide com meu razão apurado**: o espelho é `fonte='dominio'`; minhas telas de apuração
  (que leem `accounting_entries` origem ERP) continuam intactas — decidir na Task 0 se coexistem
  por coluna `fonte` ou tabela separada (menor blast radius).
- **Sem dado legal fabricado**: se o Domínio não retornar, é "aguardando dado", não estimativa.

### Critérios de sucesso (#0)
- `puxar_razao` retorna lançamentos reais da Eletrônica de um período (curl-provado 200).
- `importar_razao` materializa o espelho idempotente (re-rodar não duplica).
- Oráculo: contagem e soma D==C batem com a origem.
- Tela mostra status real da sync; botão gated funciona.
- Zero mistura com o razão ERP; zero escrita no Domínio.

### Fora de escopo (#0)
- Geração de qualquer arquivo SPED (é #1+). #0 só traz e espelha o dado.
- Transmissão. DEFIS/Simples (é #4/#5).
