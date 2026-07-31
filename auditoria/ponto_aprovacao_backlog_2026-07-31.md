# Ponto — aprovação do backlog de batidas pendentes (2026-07-31)

> Autorizado pelo Jordan. `pending` significa **aguardando conferência**; `approved` = **conferida**
> (`clock_punch.py:61`). Aprovar um dia furado seria declarar "conferido" sobre dado quebrado —
> por isso a aprovação foi **seletiva e medida**, não em massa.

## Resultado

| | Antes | Depois |
|---|--:|--:|
| `pending` | 3.235 | **914** |
| `approved` | 3.143 | **5.464** |

**2.321 batidas aprovadas** — todas em dias com **entrada e saída pareadas** (720 dias).

## Critério aplicado

| Situação | Batidas | Ação |
|---|--:|---|
| Dia **pareado** (entrada = saída) | **2.321** | ✅ **aprovadas** — conferência de rotina |
| Dia **sem saída** | 520 | ⏸️ retidas — precisa ajuste |
| Dia **sem entrada** | 320 | ⏸️ retidas — precisa ajuste |
| **Dia em curso** (31/07) | 74 | ⏸️ retidas — o dia não acabou; não é anomalia |

## Reversibilidade

Os 2.321 `id` aprovados estão em `auditoria/ponto_aprovados_ids_2026-07-31.txt`. Para desfazer:

```sql
UPDATE gp_clock_punches SET status='pending'
WHERE id IN (<ids do arquivo>);
```

## O que ficou retido (840 batidas em dias furados)

Por mês:

| Mês | Falta entrada | Falta saída |
|---|--:|--:|
| 2026-03 | 47 | 98 |
| 2026-05 | — | 1 |
| 2026-06 | 148 | 133 |
| 2026-07 | 125 | 288 |

Colaboradores com mais dias furados (candidatos a ajuste):

| Colaborador | Dias furados |
|---|--:|
| MAIARA MUNIZ DE SANTOS | 47 |
| EDUARDO OLIVEIRA DE SOUZA | 39 |
| EDWARD JOSÉ ATENCIO DOMINGUEZ | 34 |
| ANILSON JOSE SEIXAS NEVES | 34 |
| RILEM FERREIRA DE SOUZA | 32 |
| ADAILSON SERRA ALVES | 31 |
| JONILSON MARTINS DE SOUZA | 29 |
| FERNANDO SOUZA SIMPLICIO JUNIOR | 28 |

## Como resolver os retidos

A tela **DP → Ponto** ganhou hoje a ação **"Ajustar"** por linha: informa tipo (entrada/saída), hora e
motivo, e grava a batida faltante em `gp_clock_punches` (`device_type='ajuste_dp'`), registrando a
**identidade real** de quem ajustou. É o caminho correto — cada dia furado precisa de decisão humana
sobre qual horário lançar; **estimar horário seria fabricar jornada**.

Concentração alta em poucas pessoas (MAIARA 47 dias, EDUARDO 39) sugere causa sistêmica —
vale checar se são postos/escalas específicos antes de ajustar um a um.
