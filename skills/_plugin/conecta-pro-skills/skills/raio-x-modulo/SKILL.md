---
name: raio-x-modulo
description: Investiga a fundo UM módulo do Conecta PRO — o que o backend codou, o que o front alcança, o que está duplicado e o que é casca. Combina graphify (estrutura por dentro) + backend_recon (alcance backend↔front) + leitura do controller antes de chamar qualquer coisa de buraco. Use quando perguntarem "o que tem no <módulo> que não está no redesign", "o que o backend do <módulo> faz que ninguém alcança", antes de planejar paridade de um módulo, ou para medir progresso rumo a desligar o clássico.
---

# Raio-X de módulo — Conecta PRO

Três ferramentas, um relatório. **READ-ONLY exceto pelo relatório final.**

- **graphify** → estrutura por dentro (duplicação, código morto, o formato real)
- **backend_recon v2** → alcance (rota montada × superfície do front)
- **leitura do controller** → o que a ferramenta não sabe julgar

Nenhuma das três sozinha responde. A recon não sabe o que a rota *faz*; o graphify não sabe se ela *tem botão*; e as duas juntas ainda não sabem se o número exibido é *verdade* (isso é [[veracity-sweep]], deliberadamente fora daqui).

## Mapa dos módulos (não redescubra o prefixo)

| Módulo | Prefixo da recon | Onde o código mora | Rotas |
|---|---|---|---:|
| DP / RH / Pessoas | `people-management` | `modules/people_management` | 697 |
| Financeiro | `financial` | `modules/financial` | 593 |
| **Fiscal / Governo** | `government` e `fiscal` | ⚠️ **`modules/government_integrations`** (177 arq). `modules/fiscal` tem só 8 | 470 |
| Operacional | `operacional` | `modules/operacional` | 301 |
| CRM | `crm` | `modules/crm` | 245 |
| GED | `ged` | `modules/ged` | 200 |
| Recrutamento | `recruitment` | `modules/recruitment` | 166 |
| Licitações | `bidding` | `modules/bidding` | 87 |
| Campo | `campo` | `modules/campo` | 77 |
| Serviços | `services` | `modules/services` | 63 |
| Jurídico | `juridico` | `modules/juridico` | 52 |

Sem argumento: **liste os módulos e pergunte**. Não chute.

## Os 5 passos

### 1 · LOCALIZAR — o nome do módulo pode mentir
```bash
cd /opt/conecta-pro
find backend/modules/<nome> -name "*.py" -not -path "*pycache*" | wc -l
```
Se der menos de ~20 arquivos para um módulo com centenas de rotas, o código mora em outro lugar. Ache o dono real:
```bash
grep -rln "<prefixo-da-rota>" backend/modules --include=*controller*.py | cut -d/ -f3 | sort | uniq -c | sort -rn | head
```
Caso conhecido: `fiscal` → o peso está em `government_integrations`.

### 2 · ESTRUTURA — graphify (~20s, zero LLM)
```bash
graphify update backend/modules/<caminho-real>
```
Grafo em `backend/modules/<caminho>/graphify-out/`. Depois, pergunte a ele o que a fila do passo 3 revelar:
```bash
graphify query "<conceito que apareceu na fila>" --budget 1200
```
**É aqui que se acha duplicação de implementação** — o caso que motivou esta skill: três pareadores de batida, dois corrigidos e um esquecido, servindo 4 endpoints com 28% dos dias errados.

### 3 · ALCANCE — recon v2 (~1m45; 75s são o import, irredutível)
```bash
python3 scripts/backend_recon.py <prefixo> --surface redesign \
  > auditoria/backend_recon/<mod>_redesign_$(date +%Y%m%d).txt \
  2> /tmp/recon_err.txt
echo "exit=$? stderr=$(wc -c < /tmp/recon_err.txt)b"
```
⚠️ **Redirecione os DOIS fluxos.** O `dump_routes` escreve o erro em `stderr` e faz `exit(1)`: com `>` sozinho, uma falha produz **arquivo de 0 bytes sem pista** (aconteceu em 31/07 e 01/08). Confira os dois tamanhos.

Baldes: 🔴 geradores órfãos · 🟠 órfãs de ESCRITA (a fila) · ⚪ órfãs de leitura · 🔵 provável falso-órfão · ✅ expostas com prova.

### 4 · LER — antes de chamar qualquer coisa de buraco
Abra o controller de **todo item do balde 🔴** e de **toda duplicação aparente**. São legítimos e costumam ter comentário explicando:

- **alias de compat** — `include_in_schema=False` + comentário. No fiscal: 63 rotas `/fiscal/fiscal/*` serviam o client orval. Pareciam bug, eram deliberadas.
- **integração server-to-server** — `/integration/*`, webhooks. Esperado sem front.
- **admin sem tela** — capacidade real, decisão de produto.

Regra da casa: **órfão ≠ bug.** A ferramenta lista evidência; quem decide é humano.

### 5 · CONSOLIDAR
Escreva `auditoria/tripe/<mod>_<AAAAMMDD>.md` com:
- **fila real de escrita** = bruta − alias − server-to-server, agrupada por área, cada linha com o que a rota faz
- **achados estruturais do grafo** (duplicação, código morto, o módulo mentindo o nome)
- **leads de outro escopo** — o que apareceu e não é deste módulo
- **o que foi descartado e por quê** (nunca omita: um balde some da vista e vira "coberto")

## Armadilhas medidas (todas custaram tempo real)

| Armadilha | Como evitar |
|---|---|
| O nome do módulo mente | Passo 1 sempre. `modules/fiscal` = 1,5% do fiscal |
| Órfão parece bug | Passo 4 sempre. 63 aliases deliberados no fiscal |
| Contar path em vez de (path, método) | `app.routes` tem uma entrada por decorator: GET+POST no mesmo path conta 2. Contei 727 "duplicados" e o número real era 315 |
| `> saida.txt` sem `2> erro.txt` | Arquivo de 0 bytes, sem pista |
| Achar que a dupla vê correção | Ela mede alcance, não veracidade. O defeito de 28% dos dias vivia em rota classificada como saudável |
| `pgrep -f <script>` | Casa com a própria linha de comando e com processos de espera de outras sessões. Use `deploy_backend_blue[g]reen` |

## Fronteiras

- **Operacional é READ-ONLY para agentes** (postos/alocações curados à mão pelo Jordan). Raio-x nele produz **relatório, nunca wiring**.
- 💰 dinheiro que sai e 🏛️ gov órfãos: **reportar ao Jordan, nunca acionar**. Happy-path dispara OTP real.
- Detalhe da heurística de cobertura: ver `conecta-backend-recon`. Pipeline completo do grafo: ver `graphify`. **Não duplique aqui** — três cópias divergem na primeira mudança.

## Custo

~5–10 min por módulo (20s grafo + 1m45 recon + leitura + escrita). Exige `conecta-pro-backend` de pé.

Rodar o mesmo módulo de novo meses depois e comparar os relatórios datados **é a medida de progresso rumo a desligar o clássico**.
