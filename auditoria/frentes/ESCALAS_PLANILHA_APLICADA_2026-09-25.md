# Planilha "ESCALAS SETEMBRO 2026 ATUALIZADO 100%" aplicada em produção — 25/09/2026

Fonte: `auditoria/frentes/escalas_atualizado.xlsx` (md5 `e57bf2eb`, 58 linhas, 9 postos).
Autorização: Jordan, 25/09/2026 — *"essa planilha é a fonte da verdade, o que está nela sempre
prevalece"*. Operacional normalmente é READ-ONLY para agentes; esta escrita é exceção autorizada.

Backup para reversão: tabelas `allocations_bkp_20260925` (89 linhas) e
`employees_posto_bkp_20260925` (104 linhas), no próprio banco.

## Aplicado (verificado por releitura, não pela linha de saída do psql)

| Ação | Qtd |
|---|---:|
| já corretos, nada a fazer | 36 |
| pessoa CRIADA | 4 |
| realocada (posto e/ou setor) | 17 |
| desalocada (planilha diz SEM POSTO) | 1 |
| alocação duplicada corrigida | 1 |
| ciclo PAR/ÍMPAR gravado | 26 |
| `posts.current_headcount` recalculado | 8 |

Divergências planilha × banco: **13 → 1** (a que resta é deliberada, ver Geilson abaixo).

### As 4 pessoas criadas
France Charles Almeida de Sales (Mirante das Flores, rondista) · Jair Soares da Rocha (Prime
Arena, portaria) · Wisley Costa Medeiros (Laranjeiras Village, rondista) · Thayna Rhannele
Cancio Neves (Green Hills, portaria).

🔴 **As 4 estão sem CPF, PIS, data de admissão e salário.** Sem CPF não entram em folha nem em
eSocial. O espelho do eSocial não pôde suprir isso: ele **paraem 03/07/2026** (416 eventos), porque
o beat `espelho` aponta para um módulo que não existe (`government_integrations.tasks.espelho`).

## O eixo PAR/ÍMPAR: existia, mas não no cadastro — está nas BATIDAS

O tipo `12x36` existe (`posts.shift_type`), a **fase** não existia em lugar nenhum. Derivei das
batidas de **entrada** de setembro: 13 PAR + 13 ÍMPAR, equilíbrio exato — que é evidência a favor,
porque um posto 12x36 exige as duas metades iguais. Gravado em `allocations.notes`.

⚠️ **A primeira medição estava errada e a correção importa:** contando todas as batidas, TODOS os
noturnos apareciam "misto". Causa: **turno noturno atravessa a meia-noite** — uma escala gera
batida no dia N (entrada) e no dia N+1 (saída). A data da batida não é a data da escala.

## Pendente de confirmação do Paiva (não inventei nada disso)

1. **Geilson Rodrigues aparece 2× na planilha** (Ideal Flores JARDINEIRO e Villa dos Pássaros
   PORTARIA) e existe **um só** no banco, cargo jardineiro. Mantive Ideal Flores; a 2ª linha NÃO
   foi aplicada. Criar um 2º "Geilson Rodrigues" poderia gerar folha em duplicidade.
2. **Green Hills, linha de nome VAZIO** (noturno/portaria) — vaga real, confere com `FALTA 1`.
3. **Michelangelo pede 3, a planilha lista 2** — `FALTA 1`.
4. **Jeovane do Nascimento não está na planilha, mas TRABALHA** — 11 entradas em setembro em Villa
   dos Pássaros, todas em dia PAR. A planilha tem uma linha faltando, não o Jeovane uma alocação
   sobrando. Por isso **não** o desaloquei: ausência não é afirmação, e batida é fato.
5. **Seis pessoas cujas entradas não obedecem ciclo nenhum** (cobertura, troca ou escala errada):
   Adeilson Diniz (3 par/9 ímpar) · Jonilson Martins (10/6) · Carlos Eduardo Façanha (6/5) ·
   Daniel Vidal Larroque (4/11) · Rilem Ferreira (6/5) · Anilson José Seixas (12/4).

## Conflito planilha × eSocial — escalei, NÃO mexi no status

A planilha tem 4 colunas (nome, posto, turno, setor) e **nenhuma coluna de status de vínculo**.
Não pode prevalecer sobre um fato que ela não afirma, e nesses casos há evento de governo:

| Pessoa | Status no sistema | Na planilha |
|---|---|---|
| Tatiana Santana Nascimento | `demitido` | Ideal Flores, serviços gerais |
| Meire Gabriela da Silva e Silva | `demitido` | Villa dos Pássaros, portaria |
| Cintia Bezerra Oliveira | `afastado_inss` | Vila Dei Fiori, portaria |
| Geilson Rodrigues de Andrade | `ativo`, mas **S-2299 desligamento 30/06** transmitido | Ideal Flores |

Reativar quem tem S-2299 transmitido joga a pessoa na folha. Decisão é do Jordan.
