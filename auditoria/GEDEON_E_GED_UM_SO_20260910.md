# Um GEDEON só — o que cada metade tem e como elas se completam (10/09/2026)

**Origem:** Jordan, olhando o primeiro kit real (Michelangelo, 08/2026): *"dois? precisa dos dois?
… vai a fundo, vai no pré sal, tem mais coisa aí"*. Tinha.

---

## 1. Não são duas versões da mesma coisa. São duas metades.

| | **GEDEON** (`modules/gedeon`) | **GED** (`modules/people_management/ged`) |
|---|---|---|
| Papel | **coletor** — vai buscar documento no mundo | **montador** — gera do nosso dado e registra |
| Robôs de CND nos portais do governo | ✅ `cnd_federal`, `cnd_sefaz_am`, `cnd_caixa_crf`, captcha solver | ❌ |
| Comprovante de pagamento do banco (Inter) | ✅ `inter_kit_service`, `inter_comprovantes_gerais` | ❌ |
| NFS-e no ADN + geração do DANFSe | ✅ `nfse_nacional_adn`, `nfse_danfse_generator` | ❌ |
| Recibo de VT/VR **assinado** publicado no kit | ✅ `recibo_vtvr_kit_service` | ❌ |
| Pacote de rescisão do mês | ✅ `rescisao_kit_service` | ❌ |
| Documentos do Onvio (Portte) | ✅ `onvio_kit_service`, classificador de escopo | parcial (matching) |
| Conferência de **coerência** antes da entrega | ✅ ATLAS (`kit_atlas_service`) | ❌ |
| Cronograma do mês e orquestrador dos 13 | ✅ `kit_orchestrator` | ❌ |
| Busca semântica cross-módulo | ✅ SOPHIA (embeddings) | ❌ |
| Registro no banco (`ged_kit_documents`) | ❌ | ✅ |
| Assinatura eletrônica (funcionário + ICP-Brasil) | ❌ | ✅ |
| Geração pelo motor da folha (holerite, espelho, recibo) | ❌ | ✅ |
| Classificação por **tipo** e não por nome de arquivo | ❌ | ✅ |
| Estrutura de 5 pastas aprovada pelo dono | ❌ | ✅ |

**Conclusão: nenhum dos dois morre.** O que morre é a duplicação — que estava em três lugares.

---

## 2. A duplicação, e o que se fez com cada uma

### 2.1 Duas pastas no Drive (resolvido)

GEDEON escrevia em `[Condomínio]/Setembro/1. Folha e Pessoal…`; GED em
`[Condomínio]/2026-08 Kit Documental/Funcionarios|Certidoes|Guias|Beneficios|Financeiro`.

Nenhum lia o outro. **Medido no Michelangelo: a ficha dizia 9 documentos e 40% com 45 arquivos no
Drive.** O Hermes, que lê pela ficha, repetia o número errado com confiança total.

- **Escrita** unificada na estrutura do GED (`kit_layout.mes_kit_de_competencia` e `SUBPASTAS`).
- **Leitura** soma a nova + os meses antigos em português (`_ler_legado`), para nada entregue sumir.
- Michelangelo: 9 → **74 documentos**.

### 2.2 Quatro fórmulas de completude (resolvido)

| onde | o que responde | quem chamava |
|---|---|---|
| `completude_slots` | régua do CONTRATO, 10 blocos | 2 lugares |
| `kit_completude_service` | leitura das pastas do Drive | a ficha |
| `document_kit.recalculate_completion()` | **assinados ÷ total** | 5 lugares |
| `kit_builder_service` | chamava a terceira **no fim**, sobrescrevendo a primeira | sempre |

A terceira responde outra pergunta. Kit completo e não assinado lia **0%**. E rodava por último.

Agosto/2026: **12,5% → 80,9%** de média. Michelangelo: **100%**, com os 10 blocos cobertos por
arquivo de verdade (a conta exige `file_path IS NOT NULL`).

### 2.3 Sete classificadores para "onde este documento mora" (parcialmente resolvido)

`_BLOCO_DE_TIPO` · `PASTA_DO_TIPO` · `CATEGORIA_FUNCIONARIO` · `CHECKLIST` ·
`subpasta_do_arquivo` · `kit_structure.categoria_de` · `drive_kit_classifier.classify_filename`

Hoje os quatro primeiros estão amarrados por oráculo (`test_oraculo_reguas_do_kit_batem`). Os três
últimos classificam por **nome de arquivo** e continuam existindo porque os robôs depositam um
arquivo sem ter o tipo em mãos. **Próximo passo natural:** o robô resolver o tipo na hora de
depositar e usar a mesma cadeia — aí sobram dois mapas, não sete.

---

## 3. O pré-sal: `posts.ged_client_id` NULO nos 16 postos

A coluna existe. A relação *"de qual condomínio é este posto"* tem lugar no banco e ninguém
preencheu — então **tudo** resolvia por semelhança de nome:

- `nome_pasta_condominio("Condomínio Gelain")` não achava `CONDOMINIO PARQUE RESIDENCIAL GELAIN`;
- o robô de VT/VR criava uma pasta de cliente NOVA ao lado da certa;
- foi assim que nasceram as 7 pastas curtas apagadas em 17/08 — **e que voltaram**
  (`GREEN HILLS`, `PARISE VILLA`, `PARQUE RESIDENCIAL GELAI`, `SMART TORQUATO`);
- e foi por isso que o kit do Michelangelo achou 0 funcionários até alguém ligar na mão.

`posts.client_id` estava preenchido e **correto nos 16**, e `clients.document_number` casa com
`ged_clients.cnpj` em **15**. Preenchido por esse join. Postos que virariam pasta fantasma: **4 → 1**
(e esse 1 é o escritório, que não é cliente).

> É a regra da casa, literal: *se o número toca R$, tributo ou órgão público, prefira ler a fonte a
> codificar a convenção.* Aqui a fonte é um join, e sete lugares preferiram adivinhar.

---

## 4. Onde o Hermes entra — e onde não entra

**Entra no julgamento.** `kit_auditoria_hermes.auditar_kit`: depois do kit sincronizado, ele abre o
kit pelas ferramentas do ERP (conector `mcp-ged`, escopo `ged,fiscal`, 42 ferramentas) e confere
contra as regras da casa. Devolve JSON; o parecer vira nota no kit.

**Não entra na conta.** Calcular folha, gerar PDF, subir arquivo, rotear pasta: continua tudo
determinístico em Python. Passar isso por LLM encareceria e traria erro onde hoje não tem.

O critério é este: os quatro defeitos de 09 e 10/09 — guia na pasta errada, nome de máquina na
pasta do síndico, "assinado" sem PDF, nota fiscal de janeiro no kit de agosto — **eram todos
julgamento**, e todos passaram por uma regra que respondeu com confiança a um caso que não previa.

Custo medido: **91 mil tokens por conferência**, ~13 conferências/mês.

---

## 5. Aberto, e é decisão do dono

| o quê | estado |
|---|---|
| `uniao_kit_service` (19/08, *"o kit é UM só: junta banco e Drive"*) | **zero chamadores** — escrito para este mesmo problema e nunca ligado |
| `gedeon/kit_builder_service.py` (350 linhas) | só chamado por testes |
| `sophia_v1_backup.py` (524 linhas) | backup da v1 ainda no repositório |
| 21 `ged_clients` para 11 condomínios ativos | 3 dos que têm kit são a **própria Conecta Mais**; 7 nunca tiveram kit |
| Pastas duplicadas já no Drive | `GREEN HILLS`, `PARISE VILLA`, `PARQUE RESIDENCIAL GELAI`, `SMART TORQUATO` — a causa foi fechada, as pastas continuam lá |
| Os 3 classificadores por nome de arquivo | podem virar um só quando o robô resolver o tipo ao depositar |
