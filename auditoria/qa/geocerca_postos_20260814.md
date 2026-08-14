# Geocerca dos postos — 4 coordenadas erradas fabricam `fora_local`

**14/08/2026. Relatório, não conserto.** Posto é curado à mão pelo Jordan e é read-only
para agente — a proposta está aqui com o número; quem aplica é ele.

## O sintoma

`gp_clock_punches.status = 'fora_local'`: **116 na janela de 30 dias, e 13 das 21 batidas
de hoje (62%)**. Isso entra direto na decisão pendente *"batida não-aprovada conta na
apuração?"* — porque se `fora_local` for defeito de cadastro, a pergunta muda: não é regra
de negócio, é dado errado.

## A causa

**Quatro postos carregam a MESMA coordenada** — `-3.0739478, -60.0893432`:

| posto | ativo |
|---|---|
| Condomínio Mirante das Flores | ✅ |
| Condomínio Villa dos Pássaros | ✅ |
| Condomínio Villa dos Pássaros *(registro duplicado)* | ❌ |
| Portaria Principal - Mirante das Flores | ❌ |

Uma coordenada repetida em quatro postos distintos não é medição — é valor copiado.

## A prova de que quem erra é o cadastro, não a pessoa

As batidas de cada posto se agrupam **num ponto próprio, com desvio de ~11 metros**
(`stddev` 0,0001°). As pessoas estão sempre no mesmo lugar, batida após batida. Esse lugar
é o posto. O que está deslocado é o registro.

Se fosse gente batendo de casa, a nuvem seria dispersa — cada um na sua casa. Ela é
apertada.

## Distância entre o cadastrado e o real

Raio da geocerca em todos: **150 m**.

| posto | batidas | latitude real | longitude real | distância | veredito |
|---|---:|---|---|---:|---|
| Condomínio Villa dos Pássaros | 44 | -2.980291 | -60.021450 | **12.871 m** | 🔴 12,9 km fora |
| Condomínio Michelangelo | 17 | -3.102879 | -60.010574 | **1.484 m** | 🔴 |
| Condomínio Mirante das Flores | 35 | -3.061974 | -60.090394 | **1.338 m** | 🔴 |
| Condomínio Villa Dei Fiori | 13 | -3.088362 | -60.027666 | **1.152 m** | 🔴 |
| Condomínio Ideal Flores da Cidade | 39 | -3.049333 | -60.008665 | 186 m | 🟠 36 m além do raio |
| Condomínio Prime Arena | 20 | -3.088505 | -60.029532 | 114 m | 🟢 dentro |
| Residencial Laranjeiras Village | 11 | -3.055415 | -60.014675 | 29 m | 🟢 dentro |

Coordenada real = **mediana** das batidas do posto (mediana, não média: resiste a uma
batida solta longe distorcendo o centro).

Isso explica exatamente o que se via: **100% `fora_local`** nos quatro primeiros, **3%** no
Ideal Flores (186 m contra raio de 150 m — quase lá) e **0%** nos dois últimos.

## Mais duas coisas no cadastro

- **`Condomínio Villa dos Pássaros` existe duas vezes** (`fdde51f0` ativo, `5f901f9e`
  inativo). Vale conferir se algum turno/alocação aponta para o inativo.
- **`Conecta Base (Escritorio)` está sem coordenada nenhuma** (latitude e longitude NULL).
  Batida ali nunca poderá ser validada por geocerca.

## O que fazer

1. Corrigir a coordenada dos 4 postos 🔴 para os valores da tabela.
2. Ideal Flores: ou corrigir a coordenada (186 m), ou subir o raio para ~250 m. Corrigir a
   coordenada é melhor — raio grande aceita batida de fora do portão.
3. Decidir o que fazer com as 116 batidas `fora_local` já gravadas: elas foram marcadas por
   um cadastro errado, não por comportamento. **Reclassificar em massa é escrita em cima de
   ponto e não fiz nada disso** — é decisão sua.
4. Resolver o posto duplicado e a coordenada ausente do escritório.

## Nota sobre `dentro_geofence`

A coluna está **NULL em 5.887 de 6.066 batidas** (90 dias). Só 179 tiveram a verificação
de geocerca de fato executada. Ou seja: mesmo depois de corrigir as coordenadas, a
validação não está rodando na maioria das batidas — o `status='fora_local'` vem de outro
caminho. Vale investigar separadamente antes de confiar nesse campo para qualquer regra.

---

# ADENDO — 14/08, depois da correção do T2

O T2 aplicou as coordenadas. Confirmado no banco: os 5 postos corrigidos bateram
com as medianas propostas até a 5ª casa decimal.

## Como ficaram (medido só com batida de agosto)

| posto | distância do cadastro | espalhamento p90 | veredito |
|---|---:|---:|---|
| Michelangelo | 0 m | 4 m | 🟢 |
| Ideal Flores | 0 m | 17 m | 🟢 |
| Villa Dei Fiori | 0 m | 37 m | 🟢 |
| Villa dos Pássaros | 0 m | 45 m | 🟢 |
| Mirante das Flores | 1 m | 38 m | 🟢 |
| Laranjeiras | 29 m → **0 m** | 10 m | 🟢 ajustado agora |
| **Prime Arena** | 114 m | **1.938 m** | ⛔ **não tocado, de propósito** |

Espalhamento p90 = raio dentro do qual caem 90% das batidas daquele posto. Nos
corrigidos ele vai de 4 a 45 m, contra raio de geocerca de 150 m — folga larga.

## ⚠️ O "depois 100%" ainda não é observação

A correção entrou às **17:00**; a última batida do sistema é de **13:08**. **Zero
batidas depois da correção.** O 100% é recálculo de batida velha contra coordenada
nova — projeção, não comportamento. A prova real sai amanhã de manhã, no primeiro
turno.

## ⛔ Por que Prime Arena ficou de fora

Distância de 114 m parece caso igual aos outros, mas o **espalhamento p90 é de
1.938 m**. As batidas do Prime Arena **não se agrupam** — nos outros postos a nuvem
é de metros, aqui é de quilômetros. Mover o centro para a mediana de uma nuvem
dispersa é chute com cara de precisão.

Os 70% dele não são cadastro errado; são comportamento (ou posto com área grande,
ou gente batendo a caminho). **Precisa de olho humano no local**, não de conta.

## Aplicado no banco agora

1. `Residencial Laranjeiras Village` → centro real (29 m → 0 m).
2. Dois postos **inativos** ainda seguravam a coordenada-placeholder
   `-3.0739478,-60.0893432`: `Portaria Principal - Mirante das Flores` e a
   duplicata de `Condomínio Villa dos Pássaros`. Apontados para o centro real do
   posto que cada um representa — se alguém reativar, o bug não volta.
   **Placeholder no cadastro: 0 restantes.**

## Fica pendente

- `Conecta Base (Escritorio)` segue **sem coordenada**. Não é bug: sem coordenada o
  código não valida geocerca (`dentro=None`) e a batida entra normal. Só não dá
  para conferir presença no escritório.
- `Condomínio Gelain` tem coordenada mas **menos de 4 batidas em agosto** — não deu
  amostra para verificar. Fica sem aval.
- A duplicata de `Villa dos Pássaros` (uma ativa, uma inativa) continua existindo.
