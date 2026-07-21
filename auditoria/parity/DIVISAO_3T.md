# DIVISÃO 3 TERMINAIS — Paridade Redesign (fonte da verdade)

> Documento OFICIAL de coordenação. Orquestrador = **T1**. Duas análises independentes
> (T1 e T3) convergiram na mesma arquitetura → desenho travado. Atualizado 2026-07-21.

## Objetivo da FASE 1
Ligar (wire) ao DADO REAL do clássico as **161 telas não-wired** do redesign, em 3 terminais
**sem conflito**. Cobertura atual: **128 wired / 258 no menu (≈37%)**. Ação legal/dinheiro
(transmitir eSocial, pagar, OTP) fica SEMPRE **GATED** — nunca disparada em teste.
Fase 2 (reconstrução das ~611 capacidades de escrita) vem depois, com outro placar.

## Identidades (TRAVADAS — não confundir)
| Terminal | Papel | tmux |
|---|---|---|
| **T1** | Orquestrador + fundação (refactor) + seus módulos | (sessão que fez telas 1-24) |
| **T2** | Trabalhador — cluster financeiro/comercial | ponto CLT (termina e migra) |
| **T3** | Trabalhador — cluster pessoas | já com diagnóstico na mão |
| **T4** | Monitor (NÃO codifica) | sessão nova |

## Divisão por módulo (cada módulo pertence a EXATAMENTE um terminal)
| Terminal | Módulos (gap = telas não-wired) | ~telas |
|---|---|---|
| **T1** | operacional(28) · saude-ocupacional(3) · fiscal(6) · juridico(8) · integracoes(5) · campo(2) · documentos(2) · relatorios(1) · meu-espaco(0) · suprimentos(1) · homologacao(1) | **~57** |
| **T2** | financeiro(21) · gestao-de-pessoas(9) · crm(3) · empresas(4) · seguranca(5) · recrutamento(1) · servicos(2) · agendador(3) · assistente(2) · bi(0) · analytics(0) | **~50** |
| **T3** | departamento-pessoal(10) · rh(10) · marketing(7) · area-do-cliente(6) · portal-do-funcionario(5) · licitacoes(3) · configuracoes(6) · equipamentos(4) · automacoes(3) | **~54** |

Denominador = **telas wireable** (não P0 cru: P0 mede o buraco total, inclui escrita GATED que
ninguém faz em paralelo agora).

## As 4 REGRAS INVIOLÁVEIS (quebrou = conflito / perda de trabalho)
1. **Propriedade de arquivo.** Cada terminal edita SÓ `backend/modules/operacional/controllers/redesign_builders/<seu_módulo>.py`. NUNCA o registry (`redesign_data_controller.py`), NUNCA `_shared.py`, NUNCA módulo alheio.
2. **Commit antes de deploy.** O blue-green assa a árvore git inteira → commite seu arquivo antes de subir. Arquivos disjuntos → `git pull --rebase` nunca conflita → deploy de um carrega o commitado de todos (aditivo).
3. **Deploy serializa pelo lock** `/tmp/conecta_deploy.lock`. Use retry-loop se ocupado. 1 imagem por vez; builds ~2-3 min enfileiram.
4. **Checklist ao vivo.** Marque a tela que pegou aqui embaixo ANTES de começar (evita 2 pegarem a mesma).

## Padrão de cada tela (ver CORRECOES.md p/ exemplos)
1. Achar menu-id não-wired no `_modules/<slug>.json`.
2. No SEU `redesign_builders/<mod>.py`: `await safe("<id>", tbl(...))` lendo a MESMA tabela do clássico.
3. Coluna enum/json → `::text` / `->>'k'` no coalesce (senão `safe()` engole a tela e ela some).
4. Deploy blue-green → grep container → `curl /redesign/data/<slug>` prova dado real → commit atômico + linha no CORRECOES.md.
5. Ação de escrita legal (transmitir/pagar) = form GATED, NUNCA dispara.

## STATUS DA FUNDAÇÃO
- [ ] T1: refactor monólito → `redesign_builders/` (helpers em `_shared.py` + registry por descoberta + EXTRA_MENU/router por módulo)
- [ ] T1: provar as 128 telas wired idênticas ao `BASELINE_PRE_REFACTOR.json` (curl)
- [ ] T1: deploy + commit + **avisar** "FUNDAÇÃO PRONTA"
- **T2 e T3 NÃO começam antes desse aviso.**

## CHECKLIST AO VIVO (marque `[x] <terminal> <tela>` quando fechar)
<!-- ex.: - [x] T1 fiscal/certidoes-cnd (curl 9 CNDs) commit abc123 -->
