# José Luís — o loop de aprendizado estava morto, e o Hermes não era a cura

25/09/2026. O Jordan ordenou a **integração total do Hermes ao José Luís**, com a razão explícita
de que "o Hermes aprende padrões". Medi antes de implementar. O resultado inverte a ordem, e eu
prefiro dizer isso agora do que entregar uma troca que não entrega aprendizado.

## 1. O Hermes NÃO aprende — e é o MESMO modelo

`ai/conversation/services/hermes_client.py` (99 linhas) é **proxy OpenAI-compat puro**:
`GET /v1/models` + `POST /v1/chat/completions`. Sem tabela, sem embedding, sem fine-tune. O
payload (`:68-71`) não tem `session_id`, `conversation_id` nem `user` — **toda chamada é partida
a frio**, não existe fio entre a de hoje e a de ontem.

A prova que encerra o assunto:

```
bb19c1219cfcec3193d2ba89dcceb1e2  /data/MEMORY.md           (semente, 11/09)
bb19c1219cfcec3193d2ba89dcceb1e2  /data/memories/MEMORY.md  (o que ele "aprendeu")
```

Md5 idêntico, 5673 bytes nos dois. A semente de 11/09 está **byte a byte igual 14 dias depois**,
tendo rodado a triagem de ponto todos os dias. Nunca escreveu um byte na própria memória.

E o modelo: `/data/config.yaml` → `deepseek-v4-flash`, `api.deepseek.com`. O `.env` do José Luís
→ `LLM_MODEL=deepseek-v4-flash`. **O mesmo modelo.** Apontar um para o outro é pagar um salto
HTTP para chegar no mesmo lugar.

Tabelas de aprendizado: `gedeon_learning_events` 0 linhas · `fraud_patterns` 0 ·
`consultor_memorias` 40, das quais **36 `pendente_revisao` desde julho** · nenhuma tabela
`hermes*`. `kit_auditoria_hermes.py` (280 linhas, a única função do repo chamada "aprender") tem
**zero chamadas**.

O que está vivo e vale reusar: **`ponto/triagem_hermes.py`** — beat 08:30 Manaus, 41 notificações
no sino, última hoje 12:32, com guard de prompt-injection que abre *e* fecha o bloco de texto de
terceiro. Boa peça.

## 2. ⭐ O aprendizado do José Luís JÁ EXISTE e estava quebrado numa linha

Ele tem três mecanismos que o Hermes não tem:

| mecanismo | estado |
|---|---|
| `mem` — memória de longo prazo por contato (`agent_service.py:5933`) | ✅ 74 linhas / 30 telefones, viva |
| RAG `/app/uploads/agent_knowledge/*.md` | ⚠️ 16 arquivos, congelados desde 20/07 |
| **`gld` — few-shot de conversas reais curado por nota** (`:6176`) | ❌ **1 linha, de 18/06** |

O `gld` é exatamente o que o Jordan pediu. O auditor que o alimenta roda **todo dia às 20:00** e
entregou 62 avisos no sino — todos com **"média 0.0"**. O portão exige `nota >= 8`. Com nota
sempre 0, nada nunca foi promovido.

**Causa raiz, medida e não inferida:**

```
mesma conversa, dois tetos:
  max_tokens=300   → finish_reason=length · reasoning 1052 chars · content 0 chars  → nota 0
  max_tokens=2000  → finish_reason=stop   · reasoning  959 chars · content 78 chars → nota 9
```

`modelo_barato()` cai em `deepseek-v4-flash`, que é **modelo de raciocínio**: gasta o teto de 300
pensando e devolve `content` vazio. E `tasks.py:268` fazia `json.loads(content or "{}")` — vazio
virava dict vazio, `_nota()` lia 0, **sem levantar exceção**. Por isso não há um único warning em
meses de log. A rotina de fundo mais silenciosa da casa.

Isso é a família `or padrão` que esta casa já documentou duas vezes (`tools_self.py:63`,
`agent_service.py:387`). Terceira reincidência.

### O conserto tem duas partes, e uma só não aguenta
1. **Teto**: `AGENT_AUDIT_MAX_TOKENS`, default 4000 (era 300 fixo).
2. **Falha FECHADA**: `content` vazio ou sem `nota` → conversa **DESCARTADA da auditoria, não
   reprovada**, com log que nomeia o teto e o modelo. Ninguém pode ser mal avaliado por falha
   minha, e o próximo modelo que quebrar isso vai gritar em vez de pontuar 0.

Efeito medido logo após: **média 0.0 → 3.5, máximo 7.0**. O loop respira.

## 3. ⭐ Mas o portão do gold era COMERCIAL, e o ofício dele mudou

A rubrica dizia *"pede o CNPJ cedo, conduz à visita"*, e o gold exigia `pediu_cnpj` OU
`conduziu_visita`. O José Luís de hoje atende sobretudo **funcionário**: ponto, chave PIX, escala,
VT/VR. **Uma conversa em que ele resolve o ponto de alguém com perfeição nunca poderia ser
exemplo**, porque ninguém pede CNPJ a porteiro. Medido: 11 conversas auditadas, **0 promovíveis,
nenhuma comercial**.

Rubrica agora classifica `tipo` (comercial × funcionario) e mede `resolveu`,
`prometeu_sem_fazer` e `repetiu_se`. Dois caminhos para o gold, os dois exigindo nota alta, sem
preço, **sem promessa vazia e sem repetição**:
- comercial → CNPJ ou visita (como antes);
- funcionário → `resolveu` = problema encaminhado **com destino**, não "vou ver".

## 4. O que o histórico diz que ele precisa aprender (5.833 mensagens medidas)

- **123 mensagens de desistência em 78 conversas**: "problema técnico" 52 · "acho que me perdi"
  44 · "não estou conseguindo te atender" 18. **15 dos "me perdi" vieram depois de um simples
  "Sim"/"Ok"** — ele perde o fio da própria pergunta.
- **"Já registrei" dito 49 vezes em 39 conversas** × `agent_drafts` com **189 rascunhos e 5
  executados**. Cada promessa dessas é dívida. Foi assim que **9 leads morreram** entre 16/06 e
  11/08, saindo "para um endereço que ninguém atende".
- **Ponto: 12 pessoas, 36% de quem respondeu à pesquisa de 11/09.** App não abre (9) · facial não
  reconhece (6) · saída registra como entrada (5) · sem login (5) · trava carregando (3). E duas
  coisas que ninguém codificou: **medo de punição** — *"só pra deixar bem claro que eu não faltei
  e nem me atrasei, então se estiver havendo alguma falha no aplicativo não é culpa minha"* — e
  **app em nome de outra pessoa**: *"Meu aplicativo está em nome de Graciene"*.
- **Ele não sabe quem é da casa**: **721 de 992** mensagens de grupo marcadas `autor_tipo='lead'`,
  incluindo "Ronda Mirante das Flores" (383) e "PRIME ARENA PORTARIA" (97) — postos próprios. E
  `classificacao` joga **675 de 992 em "tom"**, com **1 único `problema_ponto`** num período em que
  gente reclamava de ponto.
- **Tom invertido**: 54% das mensagens dos AGPs têm ≤40 caracteres e 36% ≤15; só 6% começam com
  saudação; mandam **242 imagens** (print do erro). O agente responde com **40% acima de 200
  caracteres** e 360 mensagens acima de 500. Quem manda "🫡" recebe parágrafo.

## 5. Recomendação

**Não troque o LLM do José Luís pelo Hermes** — é o mesmo `deepseek-v4-flash` sem memória. O que
produz aprendizado real é o que foi consertado aqui: auditor vivo → `gld` promovido → few-shot de
conversas reais que ele passa a espelhar. O dado já existe; faltava o portão abrir.

O que o Hermes pode dar, e vale considerar depois: ele é o único caminho com **guard de
prompt-injection** já escrito e triagem diária funcionando. Reusar aquela peça é melhor negócio
que trocar o cliente de LLM.

Pendente de decisão do Jordan: as **36 memórias `pendente_revisao`** paradas desde julho esperam
curadoria humana em `/redesign/aprovacoes`.
