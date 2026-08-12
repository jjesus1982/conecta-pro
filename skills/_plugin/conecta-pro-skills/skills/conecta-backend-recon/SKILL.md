---
name: conecta-backend-recon
description: Mapa "codado × exposto × órfão" do backend do Conecta PRO por módulo — descobre endpoints montados que NÃO têm superfície no front (geradores de documento sem botão, rotas de dinheiro/gov esquecidas, integrações internas). Use quando quiser investigar a fundo o que o backend de um módulo (DP, fiscal, financeiro, etc.) implementa mas o front não expõe. READ-ONLY, roda no host.
---

# Backend Recon — Conecta PRO

## O que responde
"O backend codou X, mas eu não vejo no front" — o caso clássico do DP. Cruza:
- **verdade do backend** = rotas MONTADAS em `main_production:app` (não o que o arquivo declara — o que de fato subiu), filtradas por prefixo do módulo, **com o `summary`/docstring de cada endpoint** para dizer *o que a capacidade é*;
- **superfície do front** = índice `token → arquivos` do `frontend/src` clássico + `redesign_builders/` + `redesign_data_controller.py`;
- **leitura direta do banco** = tabelas que os builders do redesign consultam por SQL (a tela mostra dado sem chamar rota).

Saída em 5 baldes:
- 🔴 **GERADORES ÓRFÃOS** — rota de documento (pdf/xml/zip/export/download/recibo/espelho/holerite…) montada e sem prova de uso. Onde mora "codaram o PDF e nunca puseram o botão". Flags 💰 (dinheiro) e 🏛️ (gov/fiscal).
- 🟠 **ÓRFÃS DE ESCRITA** — POST/PUT/DELETE/PATCH sem superfície. **É a fila de trabalho real** para fechar paridade.
- ⚪ **ÓRFÃS DE LEITURA** — GET sem superfície e sem tabela correspondente nos builders.
- 🔵 **PROVÁVEIS FALSO-ÓRFÃO** — GET cujo recurso casa com tabela que o builder lê direto: a tela provavelmente já mostra o dado.
- ✅ **EXPOSTAS** — com o **arquivo do front que prova** e o motivo do casamento.

Cada linha traz `→ o que a rota faz` e, quando órfã, `motivo:` dizendo qual segmento não foi encontrado.

## v2.2 (2026-08-10) — comentário deixou de contar como cobertura

Dois consertos no mesmo dia, ambos no `build_index`:

1. **`grep -H` obrigatório.** Sem ele o grep **omite o nome do arquivo quando o alvo é UM
   arquivo** (o caso do `redesign_data_controller.py`): a linha sai `732:token` em vez de
   `arq:732:token`, o `split(':',2)` devolve 2 campos e o parser descartava **tudo em
   silêncio**. Os 18.483 tokens daquele arquivo ficavam fora do índice, inflando órfãos.
   Efeito: 207 → 191.

2. **Comentário e docstring não entram no índice.** Um builder que documenta o que *não*
   ligou — `# de fora: /docs/orcamento/pdf exige lista de objetos` — punha `orcamento` no
   índice e a rota aparecia **COBERTA**. O medidor passava a bajular quem documentava
   exclusão. Medido: dizia 79 rotas fechadas quando eram 43.
   Usa `tokenize`, não regex: `#` dentro de string não é comentário, e docstring de várias
   linhas precisa do bloco inteiro. String multi-linha só conta como comentário quando não
   há código antes dela na linha — senão SQL embutido sumiria do índice.

**Regra de leitura:** desconfie de queda no número de órfãos logo depois de alguém editar
um builder. Se caiu junto com uma leva de comentários, era o instrumento, não o sistema.

## Como a cobertura é decidida (v2 — 2026-08-07)

Os segmentos que **identificam** o recurso (sem `api`/`v1`/params/genéricos como `pdf`, `status`, `list`) precisam **co-ocorrer no MESMO arquivo** do front. Escolhem-se os **dois mais raros** — raridade é o que discrimina: `employee`, `hr` e `status` aparecem em centenas de arquivos e não provam nada; `vacations` e `balance` provam.

**Por que mudou.** A v1 fazia `key in corpus`: substring numa string de megabytes com todos os tokens do front. `/hr/contracts/{id}/document` era dado como COBERTO porque a palavra "document" existia em qualquer canto. Medido em 2026-08-07 no `people-management`: **89 de 449 "expostas" (20%) casavam só por substring**. Esse erro **esconde buraco** — pior que o falso-órfão, que a v1 já documentava. Efeito da correção no mesmo módulo: expostas 444 → 205.

A v1 também tinha guard de ≥4 chars na âncora, o que jogava `ppp`/`cat`/`epi` em órfão automático. A v2 usa ≥3 e co-ocorrência: `/sst/ppp/{id}/pdf` agora sai **coberta**, com a prova (`ppp+sst` em `redesign_builders/saude_ocupacional.py`).

## Princípios (inegociáveis)
- **READ-ONLY.** Nunca edita, nunca deploya, nunca chama rota que escreve. O `--curl` só sonda **GET** sem parâmetro.
- **Órfão ≠ bug.** É um *candidato*. Muita rota órfã é integração interna legítima (`/integration/*`, webhooks) ou admin sem tela. A skill **lista evidência** (rota + motivo + arquivo), quem decide é humano.
- **A skill não julga correção.** Ela mede *alcance*, não *veracidade*. Um endpoint exposto que devolve 200 com número errado é ✅ para ela. Caso real: o defeito de pareamento de ponto (28% dos dias-funcionário) vivia em rotas que ela classificava como saudáveis — quem achou foi o [[graphify]]. Para correção, ver [[veracity-sweep]].
- **Sem corte silencioso.** Todos os baldes saem completos. `--limite-expostas N` corta a lista de ✅ e **avisa no cabeçalho** quantas foram omitidas.
- **💰 dinheiro que SAI** (pix/pagamento/payroll) que apareça órfão: NUNCA testar happy-path (dispara OTP real). Só reportar.
- **Rode `--self-check` depois de mexer na skill.** 11 asserts sobre a lógica de pareamento, sem docker e sem banco (~instantâneo).

## Uso
Roda **no host**, de `/opt/conecta-pro` (`scripts/backend_recon.py` é symlink para esta skill):
```
python3 scripts/backend_recon.py --self-check                 # valida a lógica, sem docker (~0s)
python3 scripts/backend_recon.py <prefixo-de-rota>
python3 scripts/backend_recon.py people-management            # DP + RH + portal + ponto + ged + integrações
python3 scripts/backend_recon.py people-management --curl --token <BEARER>   # + sonda 200/4xx/5xx nas GET
python3 scripts/backend_recon.py people-management --surface redesign        # gap p/ MATAR O CLÁSSICO
python3 scripts/backend_recon.py fiscal --surface redesign --limite-expostas 20
```

⚠️ **Redirecione os DOIS fluxos.** O `dump_routes` escreve o erro em `stderr` e faz `sys.exit(1)`;
com `> arquivo` apenas, uma falha produz **arquivo de 0 bytes sem pista nenhuma** (aconteceu em
31/07 e 01/08). Use `> saida.txt 2> erro.txt` e confira os dois tamanhos.

### `--surface` (crucial p/ o objetivo "desligar o clássico")
Escolhe contra qual front cruzar as rotas montadas:
- **`all`** (default) — clássico + redesign juntos. Acha o que não existe em **lugar nenhum** (órfão de verdade).
- **`redesign`** — SÓ o redesign (builders + `frontend/src/app/redesign` + `components/redesign`). Acha o que o **redesign ainda não cobre** = a lista para atingir paridade e desligar o clássico. **É este o oráculo do progresso rumo a "redesign 100%".**
- **`classic`** — SÓ o clássico. O delta `classic − redesign` = tudo que o clássico faz e o redesign não.

⚠️ O `all` **subestima** o gap de matar-o-clássico (conta exposição no clássico como cobertura). No DP: `all`=65 órfãs vs `redesign`=322. Para o objetivo do Jordan, use **sempre `--surface redesign`**. Nuance: os builders leem dados direto do banco (SQL), então parte dos GET-only o redesign cobre sem chamar a rota — o gap acionável é o subconjunto ação/escrita/documento (filtre por método POST/PUT/DELETE + geradores).
Prefixos por módulo (verifique com `docker exec conecta-pro-backend python3 -c "from main_production import app; ..."` se em dúvida):
- DP/RH/pessoas: `people-management`
- Fiscal/contábil: `fiscal` · Financeiro: `financeiro` ou `financial`
- Operacional: `operacional` · Comercial/CRM: `comercial`
- GED (raiz própria): `ged`

**Custo:** ~1–2 min. O gargalo é importar `main_production` no container (~75s: sobe os 14 módulos). Não dá pra encurtar — `/openapi.json` está **desabilitado em produção** (404). Rode como tarefa em background se preferir.

## Como funciona (scripts/backend_recon.py)
1. `dump_routes(prefix)` — `docker exec ... python3 -c "from main_production import app; [r.path for r in app.routes if prefix in r.path]"`, devolve JSON via marcador `<<J>>…<<J>>` (os logs de startup vão pra **stderr**, o JSON pro stdout — não confundir).
2. `build_corpus()` — **um** pass de `grep -rhoIE "[A-Za-z0-9/._-]{4,}"` nas SURFACE_DIRS extraindo TODOS os tokens ≥4 chars → string única em memória. A classificação vira `key in corpus` — mesma semântica do `grep -rIl -F key` original (a chave aparece em qualquer lugar do front), mas em UM pass em vez de um grep por rota (698×full-scan ≈ 2m37s → ≈1m38s). Tokens e não só linhas-de-chamada: senão as rotas do portal (URL montada por base+path num service) viram falso-órfãs.
3. Classifica cada rota: âncora ∈ corpus → EXPOSTA, senão ÓRFÃ; regex marca GERADOR/💰/🏛️.
4. `--curl` opcional: sonda cada GET sem `{param}` → pega 500 de schema drift ([[finding-schema-drift]]) e 404 de rota morta.

## Depois de rodar — o que fazer com os achados
- Gerador órfão real (confirmado à mão que o front não tem o botão) → é trabalho de **wiring de botão de documento** no `redesign_builders/<mod>.py` (helper `doc(...)`, curl-verifica a rota 200+bytes+type antes). Padrão em [[project_paridade_t4_financeiro_comercial]].
- Rota `/integration/*` órfã → provavelmente server-to-server, **não** é buraco de front. Confirmar quem chama (grep no backend) antes de qualquer coisa.
- 💰/🏛️ órfão → reportar ao Jordan, não mexer sozinho.
- Divergência exibido≠banco em rota exposta → é veracidade, não recon: ver [[veracity-sweep]].

## Expansão
Feito pra rodar módulo a módulo. Começou pelo DP (`people-management`); depois: fiscal, financeiro, operacional, comercial. Mesmo comando, só troca o prefixo. Consolidar os relatórios em `auditoria/backend_recon/<modulo>_<data>.md`.
