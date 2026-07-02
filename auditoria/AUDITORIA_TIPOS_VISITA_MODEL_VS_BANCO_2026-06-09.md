# Auditoria READ-ONLY de tipos — model `Visita` vs banco `visitas`

- **Data:** 2026-06-09
- **Servidor:** `srv1134814` (`82.25.75.74`)
- **Objetivo:** Listar TODOS os descompassos model↔banco de uma vez (em vez de descobrir 1 por POST).
- **Fonte da verdade:** o **banco** (não propor migration). Correções sugeridas são no **model**.
- **Estado considerado:** os 2 fixes já aplicados (5 FK removidas + 5 Enum `native_enum=False`) estão vivos no arquivo.
- **NADA editado/testado/commitado.**

---

## 🔴 Mismatches que QUEBRAM o INSERT (3)
| Coluna | Banco | Model (linha) | Categoria | Correção mínima no model |
|--------|-------|---------------|-----------|--------------------------|
| `confirmada_por` | uuid | `String(100)` (176) | uuid↔String | `Column(UUID(as_uuid=True), nullable=True)` |
| `followup_data` | timestamp | `Date` (273) | timestamp↔Date | `Column(DateTime)` |
| `interesse_nivel` | varchar | `Integer` (210) | varchar↔Integer | `Column(String)` |

- `confirmada_por` é o bug #3 ativo (erro atual do POST). `followup_data` e `interesse_nivel` são da **mesma categoria** → próximos 500 esperados. Corrigir os 3 juntos evita mais 2 rodadas.

## 🟡 Mismatches benignos — não quebram (2)
| Coluna | Banco | Model (linha) | Por que não quebra | Alinhamento opcional |
|--------|-------|---------------|--------------------|----------------------|
| `motivo_cancelamento` | text | `String(300)` (267) | varchar→text aceito pelo PG | `Column(Text)` |
| `motivo_nao_fechamento` | text | `String(300)` (222) | idem | `Column(Text)` |

## 🟡 Divergência de nullable (model mais estrito — não quebra) (3)
| Coluna | Banco | Model | Nota |
|--------|-------|-------|------|
| `origem` | YES | `nullable=False` | insert sempre seta default LEAD |
| `responsavel_id` | YES | `nullable=False` | sempre setado |
| `responsavel_tipo` | YES | `nullable=False` | default VENDEDOR |

## 🟡 Colunas no BANCO ausentes no model (10 — todas nullable, não quebram)
`contato_nome`, `contato_telefone`, `complemento`, `referencia`, `valor_estimado`, `probabilidade_fechamento`, `data_prevista_fechamento`, `anotacoes`, `ordem_servico_id`, `ativo`.
- Banco tem **`ativo` E `is_active`** (model só usa `is_active`); e **`complemento`/`referencia`** além de **`endereco_complemento`/`ponto_referencia`** (duplicação histórica). Model ignora as 10 → ficam NULL na criação (sem impacto).

## ✅ Já corrigido (confirmado nesta auditoria)
- 5 Enum → `native_enum=False` (tipo/status/origem/responsavel_tipo/resultado) — alinhados ao varchar.
- 5 FK cross-schema removidas — 0 restantes (só `visita_origem_id`→`visitas.id` self-ref, mantida).

---

## Resumo quantitativo
| Métrica | Valor |
|---------|-------|
| Colunas no banco | 100 |
| Column no model | 90 |
| Model ausentes no banco | 0 |
| Tipos OK (model bate com banco) | 85 |
| **Mismatch que QUEBRA** | **3** (confirmada_por, followup_data, interesse_nivel) |
| Mismatch benigno (varchar↔text) | 2 |
| Nullable divergente (model estrito) | 3 |
| DB-only (incompletude, nullable) | 10 |

## Recomendação (sua decisão)
- **Para o POST 201:** corrigir os **3** mismatches que quebram (1 edição cada, todas alinhando ao banco — sem migration):
  - `confirmada_por` → `UUID(as_uuid=True)`
  - `followup_data` → `DateTime`
  - `interesse_nivel` → `String`
- **Opcional (cosmético):** 2 benignos → `Text`; 3 nullable; e (se quiser usar) mapear as 10 DB-only.
- Depois: testar POST (deve 201) → commit único (FK + enum + 3 tipos) → reaplicar 3ª tool → bakar no rebuild.

---
*Read-only: `information_schema.columns` (100 cols) vs `grep "= Column("` no model (90). Comparação coluna-a-coluna por tipo SQL. Nada editado/testado/commitado.*
