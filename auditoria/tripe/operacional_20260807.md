# Raio-X — Operacional (2026-08-07)

Skill `conecta-pro-skills:raio-x-modulo` · primeira execução. READ-ONLY exceto este relatório.

> ⚠️ **Operacional é curado à mão pelo Jordan e READ-ONLY para agentes.** Este documento é
> relatório, **não fila de execução**. Nenhuma rota daqui deve ser ligada sem decisão dele.

---

## Passo 1 · LOCALIZAR — o nome não mente

`backend/modules/operacional` = **227 arquivos**. Coerente com 304 rotas.

Mas o prefixo `/operacional/` é servido por mais de um dono:

| Módulo | Controllers que citam `operacional` |
|---|---:|
| `operacional` | 32 |
| **`people_management`** | **18** |
| `financial` | 6 |
| `ai` | 4 |
| `security_lgpd` | 1 |

Os 18 de `people_management` são a costura DP↔operacional (escala↔ponto↔folha). Não é
defeito — mas significa que mexer em operacional sem olhar DP é mexer com um olho fechado.

## Passo 2 · ESTRUTURA — graphify (27s, zero LLM)

**4.795 nodes · 10.398 edges · 175 comunidades.**
Grafo em `backend/modules/operacional/graphify-out/`.

## Passo 3 · ALCANCE — recon v2 (1m45)

```
304 rotas montadas
  108 EXPOSTAS
  196 ORFAS
      102 provável falso-órfão (builder lê a tabela direto)
       94 candidatas reais  →  93 de ESCRITA
    0 geradores de documento órfãos
```

**Dois números dizem quase tudo:**

- **0 geradores órfãos.** Nenhum PDF/export codado sem botão. Contraste: fiscal tem 3, DP tinha 19. O operacional não acumulou documento órfão.
- **93 de 94 órfãs reais são de ESCRITA.** A leitura está coberta (os builders leem o banco direto — daí os 102 do balde 🔵). O que falta no redesign é **ação**, não informação.

## Passo 4 · LER — dois achados

### a) Defeito na própria ferramenta (corrigido)

18 rotas levaram a flag 🏛️ de governo. Ao ler, nenhuma tinha relação com governo:

```
/comunicacao/notificacoes/marcar-todas       🏛️
/medidas-administrativas/templates           🏛️
```

Causa: o regex `GOV` tinha `das` sem fronteira — casava com **"marcar-toDAS"** e
**"mediDAS-administrativas"**. Corrigido na `conecta-backend-recon` com fronteira de
segmento (`(?<![a-z])das(?![a-z])`), mais 4 asserts no `--self-check`.

**Efeito: 18 → 2.** As duas que sobraram são reais: `diaristas/fiscal/calcular-retencoes`
e `diaristas/fiscal/rpa`.

### b) As 3 rotas 💰 não movem dinheiro

```
POST /operacional/diaristas/payments/generate           → gera pagamento de agendamentos
POST /operacional/diaristas/payments/payroll-generate   → gera lote do fechamento de folha
POST /operacional/diaristas/payments/{id}/process       → "Processa pagamento"
```

`process_payment` chama `mark_payment_as_paid` (`diarist_service.py:459`): grava
`data_pagamento` + comprovante e soma no `valor_total_recebido` da diarista. **É
escrituração de pagamento já feito, não transferência.** Nenhuma toca Inter/PIX.

A flag 💰 está correta (é caminho de dinheiro) mas o risco é de *registro divergente*, não
de saída indevida.

## A fila — 93 rotas de escrita, por área

| Área | Rotas | Natureza |
|---|---:|---|
| `diaristas` | 16 | cadastro, agendamento, pagamento (registro), fiscal/RPA |
| `scales` | 10 | escalas |
| `comunicacao` | 10 | alertas, comunicados, confirmação de leitura |
| `medidas-administrativas` | 9 | disciplinar — inclui 3 rotas de **IA recomendando punição** |
| `time-bank` | 6 | banco de horas |
| `rondas` | 6 | inspeção |
| `substitutions` | 4 | substituição |
| `comunicados` | 4 | (duplica `comunicacao`? verificar) |
| `shifts` · `occurrences` · `notificacoes` · `grade` · `allocations` | 3 cada | |
| `unificado` · `scale-optimizer` · `diarias` · `consultor` | 2 cada | |
| `presenca` | 1 | |

## Leads para fora deste módulo

1. **`comunicacao` (10) × `comunicados` (4) × `notificacoes` (3)** — três áreas de rota para
   o mesmo domínio. Cheiro de duplicação; o grafo do passo 2 é o lugar de confirmar.
2. **3 rotas de IA disciplinar** (`ia/recomendar`, `ia/validar-conformidade`,
   `ia/verificar-proporcionalidade`). IA recomendando punição a trabalhador — **decisão do
   Jordan antes de qualquer wiring**, já sinalizado no recon de DP em 05/08.
3. **315 combinações (path, método) montadas 2×+** em toda a aplicação (achado da rodada
   fiscal). No FastAPI o primeiro registro vence; se os dois tiverem *gates* diferentes,
   vale o do primeiro. Investigação própria, fora deste raio-x.

## O que este relatório NÃO responde

Se o número exibido nas telas de operacional bate com o banco. Isso é `veracity-sweep`, e o
histórico do módulo pede: em 29/07 três telas foram de casca fabricada para tabela real
(`banco-horas`, `passagem-turno`, `instrucoes-posto`, `medidas-administrativas`).
Cobertura ≠ veracidade.

---

*Custo: ~4 min de máquina (27s grafo + 2× 1m45 recon, a segunda por causa do fix do regex).*
