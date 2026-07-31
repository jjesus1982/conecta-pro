# Fase E — folha do motor persistida em paralelo (2026-07-31)

> `source_system='conecta'` gravado ao lado da Portte. **A Portte NÃO foi tocada** (314 linhas,
> R$416.810,25 antes e depois). Idempotente (re-run não duplica). Reversível:
> `DELETE FROM hr_payslips WHERE source_system='conecta'`.

## Resultado

| Espelho | Linhas | Σ líquido |
|---|--:|--:|
| `portte` (verdade) | 314 | 416.810,25 |
| `conecta` (motor) | 312 | 448.418,40 |

As 2 linhas a menos são **PJ** (`tipo_contrato='pj'`) — PJ não recebe holerite CLT, exclusão correta.

## Decomposição do delta (onde mora a diferença)

| População | Linhas | Δ (conecta−portte) | Σ\|Δ\| | Causa |
|---|--:|--:|--:|---|
| **`ativo`** | 224 | +1.048 | **6.395** | ✅ é exatamente o Σ\|Δ\| do harness C1 — população reconciliada |
| Com **rescisão** | 18 | +26.821 | 26.821 | motor **não modela rescisão** |
| Demais não-ativos | 70 | ~+3.740 | ~12.250 | motor não modela **afastamento/suspensão** sem espelho de dias |

### Por que o agregado parece pior do que é
1. **Rescisão (18 casos):** a Portte lança `LIQUIDO RESCISAO` como **desconto** de valor igual aos
   proventos → o `net_salary` da Portte fica **0,00** embora a pessoa tenha trabalhado e recebido.
   O motor calcula o salário normal. **Comparar net-a-net nesses casos é apples-to-oranges**, não é
   o motor inflando. Verificado: 100% das linhas Portte com líquido zero têm a verba de rescisão.
2. **Afastados/suspensos:** o motor paga o mês cheio porque `folha_dias_espelho` só tem fatia de dias
   para quem a Portte registrou `DIAS/HORAS NORMAIS`. Sem linha, não há fatia.

## Mudanças no motor (necessárias para o recálculo histórico)

`calculo_service.py::calcular_folha_colaborador`:
1. O filtro `status='ativo'` passou a aceitar também **quem estava empregado na competência**
   (`data_desligamento >= 1º dia do mês`). Sem isso, todo desligado sumia do recálculo histórico
   (29% da base em 2026). Mês corrente: comportamento inalterado.
2. Novo parâmetro `historico: bool = False`. Quando `True`, dispensa o filtro de status porque o
   **chamador já provou o vínculo** (existe holerite Portte do mês). Necessário porque **14 pessoas
   marcadas `inativo`/`demitido` não têm NENHUMA data de desligamento no cadastro** — e inventar
   data seria fabricar. Default `False` = zero mudança para todos os chamadores existentes.

## Achado de cadastro (para o Jordan)

**14 colaboradores estão `inativo`/`demitido` sem `data_desligamento` nem `data_demissao`.** O sistema
não sabe quando saíram. Isso quebra qualquer cálculo proporcional de desligamento e obrigou o flag
`historico`. Corrigir o cadastro é a solução de raiz.

## Próximo (gated — NÃO autônomo)

Nada aqui vira oficial. O flip de `source='conecta'` para fonte da verdade (e o corte da Portte)
depende de revisão da diretoria sobre este delta. As duas linhas coexistem até bater.
