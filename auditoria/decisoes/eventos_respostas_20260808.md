# Respostas — os eventos restantes (2026-08-08)

Fecha a fila aberta em `eventos_orfaos_20260807.md` e `eventos_investigacao_20260807.md`.
Ordem pedida pelo Jordan: 6 amarelos → 3 vermelhos → ponto → espelhar.

---

## 🟡 Os 6 amarelos

### 1 · `crm.cliente.ativo` — **JÁ RESOLVIDO**
Não era amarelo: o GEDEON já assinava por string literal (`gedeon.py:87`). Minha medição
não via literais. Nada a fazer.

### 2 · `dp.funcionario.transferido` (12 disparos) — **registrar divergência, não mover**
O funcionário mudou de posto no DP. A tentação é o operacional mover a alocação sozinho.

**Não.** Alocação é curada à mão por você. Um handler que move alocação faz o sistema
discordar de você em silêncio — e alocação errada é porteiro no posto errado.

**Decisão: handler que só registra a divergência** (DP diz posto X, operacional tem posto Y)
numa lista que você revisa. Vira trabalho quando alguém escrever a tela dessa lista;
sem tela, o registro não é visto e não vale o código.
**Portanto: adiar até existir onde mostrar.** Não implementar agora.

### 3 · `ponto.batida.registrada` (8) — **nada, e é decisão firme**
Tentação: atualizar presença ao vivo. Mas as telas **já leem `gp_clock_punches` direto**.
Um handler criaria um segundo caminho para o mesmo dado — dois lugares para divergir.

E há o impedimento maior: enquanto `dp.ponto.registrado` coexistir, **subscriber aqui conta
batida em dobro**. Ver seção do ponto.
**Decisão: não ligar. Reavaliar quando o clássico morrer.**

### 4 · `crm.contrato.assinado` (5) — **jurídico sim, operacional não**
Três candidatos a ouvinte:
- **operacional criar postos** → ⚠️ NÃO. Seu território.
- **financeiro abrir régua de faturamento** → plausível, mas régua envolve valor e
  vencimento; errar gera cobrança errada. **Vai para a fila vermelha.**
- **jurídico iniciar ciclo de vida** (vencimento, reajuste, alerta) → ✅ é leitura e alerta,
  reversível, e o módulo jurídico já existe para isso.

**Decisão: implementar só o jurídico.** É o mesmo critério que usamos no `espelhar`:
começa pelo que não toca operação nem dinheiro.

### 5 · `dp.ponto.registrado` (3) — resolvido na seção do ponto (depreciado)

### 6 · `operacional.diarista.criada` (2) — **nada**
Tentação: financeiro provisionar custo. Mas o fluxo de diarista já tem tela própria e o
pagamento já é registrado lá. Provisionar por evento criaria um segundo lançamento.
**Decisão: não ligar.** Volume baixo (2), valor baixo, risco de duplicar lançamento.

---

## 🔴 Os 3 vermelhos — a resposta é NÃO, e por quê

Não é cautela genérica. Cada um tem um motivo específico e uma condição que teria de mudar.

### 1 · `dp.beneficio.adicionado` (6) → recalcular folha
**Não automatizar.** Recalcular folha por evento significa o valor do holerite mudando sem
alguém mandar. A folha é o custo do produto e o salário de uma pessoa; ela tem um dono
(o DP) e um momento (o fechamento).

*O que teria de mudar:* recálculo automático só faria sentido dentro de uma competência
aberta, com trilha de quem disparou e o valor antes/depois, e com o DP vendo antes de fechar.
Isso é uma funcionalidade, não um subscriber.

### 2 · `dp.esocial.gerado` (5) 🏛️ → transmitir ao governo
**Não automatizar, e este é o mais duro dos três.** Transmissão ao eSocial é
**irreversível** — evento no governo não se apaga. E hoje quem transmite a folha é a Portte:
transmitir por aqui geraria **evento duplicado** no eSocial.

*O que teria de mudar:* só depois de desligar a Portte, e ainda assim com o padrão
propor→aprovar que o projeto já usa para SST. Nunca automático.

**Alternativa segura e útil:** registrar no espelho e alertar o DP de que há evento gerado
aguardando transmissão. Isso é notificação, não transmissão. **Recomendo.**

### 3 · `financeiro.pagamento.recebido` (2) 💰 → baixa automática
**Não automatizar.** Baixa no contas a receber altera registro financeiro. Se o evento
disparar errado ou duplicado, a inadimplência some da tela sem o dinheiro ter entrado.

*O que teria de mudar:* a baixa precisaria ser conciliada contra o extrato do banco — que é
exatamente o que a conciliação Inter/Cora já faz, por outro caminho e melhor. **Ligar aqui
seria criar um segundo caminho para a mesma baixa.**

---

## Ponto — `dp.ponto.registrado` × `ponto.batida.registrada`

**Decisão do Jordan, implementada em 2026-08-08:**

- `DP_PONTO_REGISTRADO` marcado como **DEPRECADO** no catálogo, com o motivo e o apontamento
  para o canônico. Valor **inalterado** — os 3 eventos já no stream continuam casando.
- `publish_ponto_registrado` ganhou docstring de depreciação explicando que continua
  publicando só para não quebrar os 4 pontos de chamada do HR, e que morre com o clássico.
- **Nenhum subscriber ligado em nenhum dos dois.** Escrito no código, nos dois arquivos.

**O risco que essa marcação evita:** um agente ou pessoa futura ligando handler no canônico
para "atualizar presença" e contando em dobro toda batida feita pela tela clássica.

---

## `gedeon.cliente.espelhar` — os outros 4 módulos

O payload pede espelhamento em `[ged, operacional, financeiro, fiscal, portal]`.
O GED foi feito. Os outros:

| Módulo | O que "espelhar" significaria | Decisão |
|---|---|---|
| **operacional** | criar os postos do contrato | ❌ **Não.** Posto é curado à mão. Um evento criando posto é o sistema discordando de você. |
| **financeiro** | abrir régua de faturamento | ⏸️ **Depende.** Envolve valor e vencimento — errar gera cobrança errada. Mesma família do vermelho nº 4. |
| **fiscal** | pré-cadastrar o tomador para NFS-e | 🟢 **Candidato bom.** É cadastro, não emissão. Não gera nota, não fala com prefeitura. Precisa saber para qual CNPJ (Eletrônica ou Patrimonial) — e isso depende do tipo de serviço, que **está no payload** (`tipo_contrato`, `servicos`). |
| **portal** | criar acesso do cliente | ⏸️ **Não sozinho.** Criar acesso é criar credencial. Precisa de política: quem recebe, como a senha chega. |

**Recomendo: o fiscal é o próximo**, pelo mesmo critério do GED — cadastro, reversível, não
toca operação nem dinheiro nem governo. Os outros três ficam.

---

## Resumo executivo

| Item | Decisão |
|---|---|
| `dp.funcionario.transferido` | adiar — sem tela onde mostrar a divergência |
| `ponto.batida.registrada` | não ligar — telas já leem o banco, e risco de dobro |
| `crm.contrato.assinado` | **implementar só o jurídico** (ciclo de vida) |
| `operacional.diarista.criada` | não ligar — duplicaria lançamento |
| `dp.beneficio.adicionado` | não automatizar (folha tem dono e momento) |
| `dp.esocial.gerado` | não transmitir; **alertar o DP** é a alternativa útil |
| `financeiro.pagamento.recebido` | não automatizar — a conciliação bancária já faz melhor |
| `dp.ponto.registrado` | ✅ **depreciado** (feito) |
| `espelhar` → operacional / financeiro / portal | não |
| `espelhar` → fiscal | **candidato ao próximo** |

**Implementáveis se você aprovar:** o jurídico do `crm.contrato.assinado`, o alerta do
`dp.esocial.gerado`, e o fiscal do `espelhar`. Os três são cadastro/alerta — nenhum cria
posto, move dinheiro ou fala com o governo.
