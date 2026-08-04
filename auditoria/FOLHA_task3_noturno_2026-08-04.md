# Folha × Portte — Task 3 (noturno) e o que ela revelou · 04/08/2026

> Loop das 5 frentes. Task 1 ✅ (rubrica duplicada) · Task 3 ✅ (pareamento) ·
> Task 4 **decodificada, aguardando decisão** · Tasks 2/5/6 abertas.

---

## 1. O que eu tinha escrito, e estava errado

O plano dizia: *"as batidas do noturno vêm quase todas tipadas `entrada`, então nunca
forma par — é isso que produz os 29%."*

Medi antes de codar. **`punch_type` está equilibrado**: 1.171 `entrada` × 1.075 `saida`.
Não é "quase todas". A tipagem errada existe (RENE, 05→06/07: `21:01 entrada` → `09:01
entrada`, turno de 12h perdido), mas é subconjunto — e explica **3%** do buraco, não 100%.

Registro isso porque a hipótese estava escrita com confiança no plano e no meu resumo de
sessão. O número desmentiu.

## 2. Task 3 — feita, e o defeito era em dois lugares

`horas_reais_ponto` pareava confiando no tipo da batida. Agora pareia em **ordem
cronológica** com janela de plausibilidade.

**A janela se calibrou pelo dado**, não por palpite — a distribuição das durações tem duas
modas nítidas (4–5h = diurno partido pelo almoço; 11–13h = 12x36) e nada legítimo acima de
13h. Testei 13/14/16/24h: quanto mais larga, mais noturno aparece (24h dá 1.138h). Como a
Portte está *acima* de nós, seria fácil alargar até bater no alvo. **Isso seria fabricar.**
Fixei em 13h porque é onde os turnos terminam.

| | antes | depois |
|---|--:|--:|
| pares formados | 1.066 | **1.082** |
| horas noturnas | 857,9 | **930,6** (+8,5%) |
| pessoas com noturno | 24 | **25** |

Também corrigi o turno da virada (entra 31/07 22:00, sai 01/08 07:00 — a saída caía fora do
mês e o turno inteiro sumia). Conta no mês da **entrada**, sem contar duas vezes.

**Duplicação eliminada:** `punch_service.py` tinha uma **cópia** do mesmo loop, com o mesmo
defeito — era o **fechamento do mês**, fechando com hora a menos. Os dois agora chamam
`horas_service.parear_batidas`; muda só o transporte (sync/async). Self-check no arquivo
cobre os 3 casos.

Julho reprocessado e persistido: 53 holerites, líquido R$81.680,80 → **R$81.943,36**.

## 3. A descoberta que explica o resto — e que não é bug nosso

Derivei as horas implícitas da Portte a partir do valor pago (junho, 17 pessoas). Elas são
**múltiplos exatos de 8**: 128, 120, 112, 104, 88, 40, 24, 8.

Não é ruído de arredondamento. Significa:

> **A Portte paga o noturno por ESCALA — 8h por plantão — não pelo ponto batido.**

E o 8 fecha a conta: 7 horas de relógio na janela 22:00–05:00 ÷ 52min30s (hora noturna
reduzida, art. 73 §1º CLT) = **exatamente 8 horas legais**. A integralidade valida de uma
vez o divisor 180, a alíquota de 20% e o método.

As outras duas rubricas saem do mesmo lugar:

| Rubrica | Portte calcula | Confirmação |
|---|---|---|
| Adicional noturno | 8h × plantões, a 20% | múltiplos exatos de 8 |
| Hora noturna reduzida | ~1,8h × plantões, a 100% | 3 plantões→5,4h · 11→19,8h · 13→23,4h |
| Intrajornada | **= hora noturna reduzida** | razão 1,0000 — mediana **e máximo**, n=49 |

**Nosso ponto real cobre 69% (mediana) das horas que a Portte paga.** Não porque o cálculo
erra: porque batida faltando é real. **28% dos dias têm uma única batida** e 37% têm número
ímpar. Nenhum algoritmo inventa a batida que não existe.

## 4. Task 4 (intrajornada) — não é cálculo faltando, é cálculo desligado

A CCT define intrajornada como **flag por pessoa** (`employees.recebe_intrajornada`,
default off — só paga quem de fato recebe). O motor **lê a flag** (linha 248) e depois
**zera o valor** (linha 318, `intrajornada_valor = Decimal("0")`).

Conferi a flag contra 6 meses de folha real da Portte:

**21 pessoas com flag `true` — 21 recebem da Portte. Zero divergências.**

O cadastro está certo. Falta só ligar o cálculo, e o valor já é conhecido: igual à hora
noturna reduzida.

## 5. 🛑 A decisão que é sua, não minha

Ligar isso exige escolher a base — e a escolha mexe no contracheque de gente real:

**Se adotarmos a escala (como a Portte):** o noturno bate, ~R$7,7k de divergência fecha, e
ninguém perde nada.

**Se mantivermos o ponto real:** somos tecnicamente mais rigorosos, mas cada agente noturno
passa a receber ~31% menos de adicional do que recebe hoje. Isso é **redução salarial de
fato**, com risco trabalhista, causada por falha de registro de ponto — não por falta.

Minha leitura: pagar pela escala e usar o ponto para **detectar exceção** (falta, troca,
plantão extra). Mas quem decide é você — é a mesma classe do DSR.

## 6. Onde está o Σ|Δ|

| | valor |
|---|--:|
| Σ\|Δ\| medido em 04/08 | R$10.664,27 |
| efeito da Task 3 | **−R$227** (~2%) |
| efeito estimado da decisão do item 5 | **−R$7.700** (~72%) |

A Task 3 valeu pouco em dinheiro e muito em entendimento: foi ela que expôs o método da
Portte e matou uma duplicação que corrompia o fechamento do mês.

## 7. Pendências suas

1. **Noturno: escala ou ponto real?** (item 5) — destrava R$7,7k e a Task 4 inteira
2. **DSR** (+R$456) — continua parado aguardando você, como combinado
3. Tasks 2 (salário-família), 5 (férias) e 6 (script oficial) seguem abertas

## 8. Correção de memória

A memória `feedback_batidas_fonte_verdade_escalas` diz *"punch_timestamp é UTC → converter
para Manaus"*. **Está errada** e foi superada pela convenção canônica de 17/07:
`punch_timestamp` é **Manaus local naive, leitura direta**. A memória canônica registra que
"corrigir" isso para UTC já foi feito e revertido **duas vezes**. Quase caí na terceira —
corrigi o texto da memória antiga.
