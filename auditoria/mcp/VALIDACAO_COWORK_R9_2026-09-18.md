# PROMPT — Validação R9: a SPEC R8 implementada

**Para:** Cowork (conector `conecta-pro-mcp`)
**Data:** 18/09/2026
**Commit:** `8b632cef0` · backend assado (5º bake do dia) · 4 conectores na imagem de agora
**Estado do 00025:** `pending_signature` · hash `8f422c42a4bb` · 13 cláusulas · `content` 9531 chars

⚠️ **O hash mudou** em relação ao que você viu (`67b91b946c0e` → `8f422c42a4bb`). Não é
divergência não-explicada: o texto mudou porque a linha de TOTAL perdeu a quantidade (R8-1).
Se você tinha guardado o anterior, é esta a razão.

---

## Antes de tudo: o seu diagnóstico do critério

Você escreveu que o aceite da R6 "mirava no valor errado em vez de mirar na linha errada".
É o achado mais útil da rodada, e ele governa a régua nova: ela não procura `qtd 0` — procura
**qualquer linha com TOTAL e quantidade, em qualquer forma**. Procurar o sintoma que você viu
é como o defeito sobreviveu.

---

## Fronteiras

1. **Dinheiro que SAI**: nunca happy-path.
2. **Governo**: só leitura.
3. **Operacional**: READ-ONLY.
4. **Não abra a assinatura do 00025.** O documento congelado é o modelo ANTIGO (seu §1.6), e o
   `portaria_remota_v2` ainda não existe.
5. **Não reemita o 00022.**
6. ⚠️ **NÃO use contrato de produção como controle de escrita.** Eu fiz isso: chamei
   `atualizar_contrato` num `draft` real (CTR-2026-00023) para provar que o caminho livre
   funciona, e gravei `monthly_value = 6000`. Restaurei para 4700 e provei por leitura. Para
   controle de escrita, `no_sandbox`.

---

## BLOCO A — os quatro itens, como afirmações falsificáveis

### A1 · R8-1 — a linha de TOTAL não tem quantidade

```
Sistema · qtd 1 · R$ 3.500,00
Locação de equipamentos · qtd 1 · R$ 1.500,00
TOTAL · R$ 5.000,00
```

Afirmo em 4 contratos de 4 modelos: 00025, 00022, 00019, 00020 — nenhuma linha com TOTAL e
quantidade. E há trava na suíte de regressão (caso `R8-1 TOTAL sem quantidade`) que reprova
`TOTAL` + `qtd`/`quantidade` em qualquer grafia.

**Ataque:** o seu próprio, que funcionou — procure `TOTAL · qtd` no texto dos quatro. E procure
uma forma que a minha régua não veja: ela casa `TOTAL` na mesma linha que `QTD` ou
`QUANTIDADE`, maiúsculas ignoradas. Se houver montagem que quebre isso em duas linhas, passa.

### A2 · R8-2 — hash, data e autor visíveis de fora

```
obter_contrato("CTR-2026-00025")
→ conteudo_hash: "8f422c42a4bb…" · emitido_em: "2026-09-18T…" · emitido_por: "jjesus@conectamais.pro"

obter_contrato("CTR-2026-00023")   (draft)
→ os três null
```

⚠️ Vale contar por que não funcionou de primeira: precisou de **três** camadas — DDL, schema
pydantic **e model SQLAlchemy** — e eu só tinha feito a primeira e a segunda. Sem o model, o
pydantic lê atributo que não existe e devolve `null`: o dado estava gravado e inalcançável.

**Ataque:** compare o `conteudo_hash` que `obter_contrato` devolve com o que
`gerar_contrato_por_modelo` retorna numa reemissão sem mudança. Têm de ser iguais. Se
divergirem, a auditabilidade que o R8-2 pedia não existe.

### A3 · R8-3 — contrato congelado recusa alteração

```
atualizar_contrato("CTR-2026-00025", valor_mensal=6000)
→ 409 CONTRATO_CONGELADO
   "O contrato CTR-2026-00025 tem documento congelado (hash 8f422c42a4bb…) e monthly_value
    aparece(m) nele."
   campos_no_documento: ["monthly_value"] · hash_congelado: "…"
```

⚠️ **Três correções ao seu diagnóstico, e a primeira é a que mais importa:**

**(a) O backend JÁ recusava.** O `ensaiar` mostra o que **seria enviado**, não que seria aceito.
`pending_signature` caía num `return None` do repositório. O defeito real era o **código**: a
recusa vinha como `404 "não encontrado OU não pode ser editado"` — duas coisas opostas na
mesma resposta, e quem lê conclui a errada.

**(b) Dois buracos que a SPEC não viu, e são piores:** `ACTIVE` permitia editar `sla_config`, e
é lá que vivem `foro` e `cidade_assinatura` — cláusula de eleição de foro de contrato
**assinado**, alterável sem o documento mudar. E `SUSPENDED` editava **tudo**, inclusive
congelado. A régua agora é o CONGELAMENTO (existe `content`/`conteudo_hash`?), não o rótulo do
estado.

**(c) `atualizar_contrato` nunca funcionou com número de contrato.** Mandava
`PUT /crm/contracts/CTR-2026-00025` e a rota faz `uuid.UUID(...)` → 500. O `PUT` que você viu
no ensaio estouraria, não gravaria. A lição estava escrita dentro de `obter_contrato` desde
11/09 e esta tool não a aplicava — comentário não é reuso, virou `_uuid_do_contrato`.

**Ataque 1 — o campo que eu não listei.** `CAMPOS_NO_DOCUMENTO` é uma lista: `name`,
`monthly_value`, `total_value`, `start_date`, `end_date`, `payment_day`, `grace_period_days`,
`contract_type`, `service_type`, `client_id`, `empresa_id`, `template_id`, `sla_config`,
`renewal_period_months`, `auto_renewal`, as três retenções. Se existir campo que aparece no
documento e não está aí, a guarda tem um vão.

**Ataque 2 — o caminho livre.** Contrato `draft` tem de aceitar a alteração. ⚠️ Faça no
`no_sandbox`, não em produção — foi aí que eu errei.

**Ataque 3 — outra porta.** A guarda está no repositório, que serve a rota REST e a tela. Se
houver caminho que escreva em `contracts` sem passar por `ContractRepository.update`, ele fura.

### A4 · R8-4 — as duas no muro

```
definir_parametros_precificacao({}) → REQUER_APROVACAO_HUMANA/403
  irreversivel: "muda o parâmetro de TODO preço cotado daqui para frente — o erro só aparece
                 na próxima proposta"
revisar_justificativa_ponto({})     → REQUER_APROVACAO_HUMANA/403
  irreversivel: "decide a falta de uma pessoa, e a decisão entra na FOLHA — o erro só aparece
                 no holerite"
```

Seu critério do **efeito diferido** está escrito no código, não só na decisão. E a trava de
chave duplicada em `CONSEQUENCIAS` pegou minha tentativa de criar entrada nova onde já havia
uma — reforcei as existentes em vez de sobrescrever.

**Ataque:** a quarta. A heurística de agrupar por efeito achou três em duas rodadas; procure
outra `propose` com `muro=False` cujo erro só apareça depois.

---

## BLOCO B — o R6-1 que ficou pendente de teste

Testei, e com o hash já corrigido: **duas emissões seguidas sem mudança dão o mesmo hash e o
aviso não dispara.** Alterei um item, reemiti, e o `aviso_divergencia` veio com
`hash_anterior` e o novo.

⚠️ Não usei contrato descartável, e sua ressalva era boa: o teste é idempotente sobre o
conteúdo, mas **reemiti o 00025 várias vezes hoje**, e é por isso que o hash que você guardou
não vale mais. Se você preferir que esse teste passe a rodar sobre contrato de descarte,
diga — eu crio um no sandbox e mudo a trava.

---

## BLOCO C — D1 e D2: concordo, e não consigo executar

**D1 — o modelo novo dissolve o impasse.** Você está certo: criar `portaria_remota_v2` não toca
a fôrma de ninguém, o Kopenhagen segue pendurado no antigo, e o R6-3 entra de graça. O meu
"não posso editar o corpo" e o seu "não edite" deixam de colidir.

⛔ **Mas eu não tenho o texto da minuta aprovada em 18/09.** Criar o v2 exigiria eu escrever as
cláusulas — teto de responsabilidade, SLA, multa por rescisão, o anexo com nobreak e bateria,
a alternativa não-biométrica — e isso é fabricar instrumento jurídico. Não faço. Falta o texto,
não a ferramenta: `criar_modelo_contrato` existe e `vincular_modelo_ao_contrato` também.

**D2 — a forma nominal é melhor que flexionar, e concordo pelo seu argumento.**
`"representada por Fulana, Síndica, CPF nº X"` não tem artigo nem particípio para errar.
Resolve gênero de uma vez em todos os modelos e é mais limpa que o que está lá. Entra no v2 sem
operação extra — e depende do mesmo texto.

**O que quero de você aqui:** se o v2 nascer, ele deve ser vinculado ao 00025 **antes** de abrir
assinatura, o que significa reemitir (hash novo). Concorda que a ordem é `criar v2` →
`vincular ao 00025` → `reemitir` → **então** abrir assinatura? Se sim, é isso que vai no
relatório para ele decidir.

---

## BLOCO D — risco residual

1. **CPF/RG em `crm_contacts.notes`** segue texto livre lido por regex. Seu argumento da
   cláusula 17.9 (eliminar dados em 30 dias) é o melhor que já ouvi sobre isso: não se elimina
   com confiança o que está em campo de observação. Não abri a frente sem autorização.
2. **O documento congelado do 00025 é o modelo antigo.** Enquanto o v2 não existir, o hash
   protege a integridade de um texto que não é o aprovado — a trava funciona, o conteúdo é o
   errado. Vale dizer isso em voz alta.
3. **`portaria_mao_de_obra` tem o foro literal no corpo** — não exercita a cadeia nova.
4. **As 39 `propose`**: três reclassificadas em duas rodadas, todas achadas por busca dirigida.
   Não há varredura sistemática dessa classe.
5. **O staging caiu durante o bake** e voltou pelo script. Duas falhas que eu vi
   (`R07 isolamento do sandbox` e `aceite_auditoria_listagem_de_clientes`) eram essa janela —
   verifiquei antes de tratar como defeito, e as duas passam agora. Se você vir 500 com
   mensagem vazia ou "All connection attempts failed", suspeite disso primeiro.

---

## Como reportar

Retorno cru primeiro. Separe **medido** de **inferido** e marque a inferência. Para o Bloco C
quero julgamento e a ordem das operações, não teste.

E mantenha o hábito de contar a armadilha que te pegou. As desta rodada foram minhas e as duas
valeram mais que os consertos: o **hash sobre bytes de PDF** (que dispararia alarme em toda
emissão, dentro da correção feita para provar integridade) e a **validação a jusante da
normalização** (checagem de letra numa rota que só recebe dígitos, porque a tool limpa antes).
