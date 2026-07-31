# Ponto — diagnóstico medido (2026-07-31)

> READ-ONLY. Fonte: `gp_clock_punches`. Nenhuma escrita. Mede o que existe; não estima o que não existe.

## 1. Cobertura real por mês

| Mês | Batidas | Funcionários | Pendentes | Facial OK | Geofence OK |
|---|--:|--:|--:|--:|--:|
| 2026-01 | **0** | 0 | — | — | — |
| 2026-02 | **0** | 0 | — | — | — |
| 2026-03 | 1.830 | 43 | 403 | 0 | 0 |
| 2026-04 | **0** | 0 | — | — | — |
| 2026-05 | 382 | 21 | 5 | 0 | 0 |
| 2026-06 | 2.022 | 46 | 943 | 0 | 0 |
| 2026-07 | 2.151 | 55 | 1.884 | 7 | 2 |

Universo: **65 funcionários ativos**; julho tem 55 com batida (**85%**).

## 2. Origem das batidas (`device_type`) — explica os buracos

| Origem | Batidas | Período |
|---|--:|---|
| `tangerino` | 4.547 | 03/05/2026 → 30/07/2026 |
| `web` | 1.828 | 01/03/2026 → 30/03/2026 |
| `facial` | 6 | 14–16/07/2026 |
| `manual` | 2 | 28/03/2026 |
| `mobile` | 1 | 21/07/2026 |
| `conecta_pro_app` | 1 | 13/07/2026 |

**Conclusão:** houve **dois pilotos desconexos** — `web` cobriu só março; a importação do **Tangerino** começou em 03/maio. Janeiro, fevereiro e **abril** caem no vão entre eles: nenhum sistema estava capturando.

## 3. Conclusões (medidas, não supostas)

1. **jan/fev/abr são IRRECUPERÁVEIS.** Não é cobertura baixa nem bug de importação: **não existe batida nenhuma**. Nenhum código recupera dado que nunca foi capturado. Para esses meses, a única verdade é o espelho Portte — que **já está carregado** (`folha_verba_espelho`, 850 linhas).
2. **O resíduo HE do C1 NÃO dependia de ponto.** Estava documentado como "precisa ponto real", mas o HE existe no espelho Portte nos 6 meses e foi fechado hoje pelo `classifica()` (Δ −2.087 → +17). Suposição custou tempo; a medição resolveu.
3. **A fonte de verdade operacional hoje é o Tangerino**, não o app próprio. `facial` (6 batidas) e `conecta_pro_app` (1) são piloto, não produção.
4. **Facial e geofence não populam.** Em 6.385 batidas, apenas 7 têm `facial_match` e 2 `dentro_geofence`. As colunas existem e o fluxo facial existe, mas a esmagadora maioria das batidas entra pela importação Tangerino, que não traz esses campos. Qualquer tela/relatório que prometa "validação facial" hoje está sobre dado vazio.
5. **Backlog de aprovação: 3.235 `pending`** (1.884 só em julho, de 2.151). É pendência **operacional** (alguém precisa revisar/aprovar), não de código. Julho não fecha enquanto isso não for tratado.

## 4. O que NÃO fazer

- Não estimar ponto para jan/fev/abr. O motor já se comporta certo: sem batida → 0, com aviso explícito (`noturno_pendente_ponto`), nunca fabrica.
- Não prometer facial/geofence em tela enquanto a origem dominante for a importação Tangerino.

## 5. Pendências (para o Jordan decidir)

- **Aprovar o backlog de 3.235 batidas** (ou definir aprovação automática por regra) — bloqueia o fechamento de julho.
- Definir se o **app próprio/facial** substitui o Tangerino ou se o Tangerino segue como fonte.

---

## 6. CAUSA SISTÊMICA dos dias "furados" (medido 2026-07-31, pós-aprovação)

Investiguei a concentração dos furos. **Não é falha de colaborador — é estrutural do turno noturno.**

### Distribuição por perfil de escala

| Perfil | Dias c/ 1 só batida | Dias pareados (ent+saí) | Total dias | % pareado |
|---|--:|--:|--:|--:|
| **12x36 / noturno** | **780** | **96** | 1.098 | **9%** |
| 12x36 / diurno | 189 | 300 | 711 | 42% |
| 44h / diurno | 12 | 152 | 844 | 18% |

### Duas causas somadas

1. **Turno cruza a meia-noite.** 12x36 noturno entra ~19h do dia D e sai ~07h do dia D+1. Qualquer
   agregação por `punch_timestamp::date` **parte o turno em dois** — o dia D fica "sem saída" e o
   D+1 "sem entrada". Medido: **552 pares encadeados** (dia sem saída seguido de dia sem entrada,
   mesmo colaborador). Esses **não são anomalias**.
2. **`punch_type` não confiável no noturno.** Amostra real (RENE RICARDO, 12x36 noturno):
   `05/07 21:01 entrada` · `06/07 09:01 **entrada**` · `07/07 17:02 entrada` · `08/07 05:02 **entrada**`.
   Os pares existem no relógio, mas a saída vem tipada como `entrada`. No agregado os tipos até se
   equilibram (tangerino: 2.336 entrada / 2.211 saída), mas **no noturno 484 dos 780 dias de batida
   única estão tipados `entrada`**.

### Impacto no objetivo de desligar a Portte

**Hoje isso está mascarado** — a folha usa o espelho Portte (`folha_verba_espelho`), não o ponto.
Mas quando a folha for nativa, **adicional noturno e HE do 12x36 noturno não terão base apurável**:
9% de dias pareados não sustenta cálculo. O motor se comporta certo (sem batida → 0 + aviso, nunca
estima), então o efeito seria **subpagamento**, não erro silencioso — mas é bloqueio real.

### Conserto (nesta ordem)

1. **Agregar por JORNADA, não por data** — parear entrada→próxima saída dentro de uma janela (ex.: 16h),
   atravessando a meia-noite. Corrige os 552 pares sem tocar em dado. Vale para a tela DP → Ponto
   (que hoje mostra `--:--` na saída do noturno) e para qualquer apuração de horas.
2. **Corrigir o `punch_type` na importação Tangerino** — derivar entrada/saída pela alternância
   dentro da jornada, não confiar no campo de origem.
3. Só depois disso o ajuste manual (botão "Ajustar") faz sentido — hoje ajustaria dias que **não
   estão furados de verdade**.
