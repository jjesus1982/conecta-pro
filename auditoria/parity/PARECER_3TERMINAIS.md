# PARECER — Paralelizar a paridade em 3 terminais (o porquê e o desenho)

> Consolidação das análises independentes de T1 e T3, que convergiram. 2026-07-21.

## O bloqueador é técnico, não organizacional
Todo o redesign é servido por **UM arquivo**: `redesign_data_controller.py` (2.894 linhas,
24 builders `_build_<mod>` + um `EXTRA_MENU` dict único + ~24 endpoints `/action/*`). Se 3
terminais editam esse arquivo ao mesmo tempo → **merge-hell** (pior no `EXTRA_MENU` e nos
endpoints). É por isso que hoje se faz **1 tela por vez**: o arquivo é o gargalo.

## A solução: quebrar o monólito (Passo 0, feito 1×, antes do fanout)
```
backend/modules/operacional/controllers/
  redesign_data_controller.py     ← REGISTRY fino: descobre os builders, monta
                                     BUILDERS/EXTRA_MENU, inclui routers. Ninguém edita depois.
  redesign_builders/
    _shared.py    ← helpers CONGELADOS: t, b, brl, initials, _scalar, _fmtdate, _helpers, S, IC
    operacional.py  financeiro.py  dp.py  ...  ← 1 arquivo por módulo
```
Cada `redesign_builders/<mod>.py` expõe: `build(db)->dict` (as telas), `EXTRA_MENU=[...]`
(itens de menu do módulo) e, se precisar, um `router` (APIRouter) com os `/action/*` do módulo.
O registry faz **override + merge**: builder do arquivo do módulo vence o do monólito; menus e
routers são somados. Assim novos módulos/telas entram **sem tocar arquivo compartilhado**.

**Por que zera o conflito:** cada terminal dono de módulos DISJUNTOS → arquivos disjuntos →
`git pull --rebase` na mesma branch nunca conflita. Registry auto-descobre → nem ele é tocado.
Helpers são read-only. (Opcional: git worktree por terminal = isolamento de disco também,
com a ressalva de mesclar antes do deploy, que assa 1 imagem.)

## Denominador da divisão: telas-wireable, não P0
- **161 telas não-wired** = trabalho paralelizável AGORA (fase 1 = wiring de leitura/compute).
- **~611 P0** = buraco TOTAL, inclui capacidade de escrita GATED (transmissões, OTP, wizards,
  workflows, CRUD, ponto facial, LGPD) que é reconstrução, não paralelizável nesta fase.
- Dividir por P0 cru superdimensiona módulos cujo P0 é quase todo escrita. → dividimos por
  telas-wireable; o mapa de P0 por criticidade vira o **roteiro da fase 2**.

## Risco único e como mitigar
O refactor mexe num arquivo de 2.894 linhas que serve **128 telas vivas**. Regra: **1 sessão
faz + prova por curl que as 128 seguem IDÊNTICAS ao `BASELINE_PRE_REFACTOR.json` + deploy, e SÓ
ENTÃO** libera o fanout. Design escolhido minimiza o risco: só os **helpers** saem do monólito
(mudança contida); os 24 builders continuam funcionando; novos módulos entram por override.

## Sequência
1. T1 faz a fundação, prova, deploya, commita, avisa "FUNDAÇÃO PRONTA".
2. T2/T3 leem DIVISAO_3T.md, criam `redesign_builders/<seus_módulos>.py`, trabalham em loop.
3. T4 monitora os 3 e reporta ao Jordan.
