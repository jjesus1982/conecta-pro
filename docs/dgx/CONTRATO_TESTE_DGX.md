# Contrato do agente de PASSAGEM — testar o DGX por dentro e implementar o que falta (24/09/2026)

Mandato do Jordan: *"testa tudo e implementa o que faltar, loop autônomo."* Você cuida de UM
grupo de módulos do DGX. Quatro fases, nesta ordem, sem pular:

## Fase A — exercitar o DGX (botão a botão, fluxo a fluxo)
- Cliente pronto: `scripts/dgx/dgx_client.py` (`DGX()` loga como Master na PATRIMONIAL; `get`,
  `form`, `salvar`, `lista`, `botoes`, `api_get`, `api_post`, e `d.page` = Playwright para as telas
  `/frontend/*` e `/view/*` que não são formulário MVC). Rode o `__main__` uma vez para ver.
- Mapa que já existe (leia antes): `docs/dgx/00_ARVORE_DE_MENUS.md` (rotas), `01`/`02`
  (campos dos formulários), `04` (modais descobertos), `05` (127 parâmetros), `06`/`07` (telas SPA e
  rotas REST do bundle), `08`/`09` (API real). **Não refaça o mapa** — use-o para IR ATRÁS do que
  ele não diz: o que cada botão FAZ, o que o fluxo produz, o que muda em outra tela depois.
- Crie dado de teste com prefixo `TESTE CP` (colaborador, posto, contrato, o que precisar). Se
  o grupo precisa de um colaborador e ele ainda não existe, crie `TESTE CP COLABORADOR 01` em
  `/Colaboradores/Incluir` (o form tem dezenas de campos — preencha o mínimo que o servidor aceita
  e ANOTE o que ele exigiu). Compartilhado entre agentes: se já existir, reuse.
- Para cada tela do seu grupo, registre: **botões** (texto → o que acontece), **fluxo** (passos →
  resultado observável: registro criado, status mudou, PDF gerado, outra tela refletiu), **regras**
  que o servidor impôs (mensagens de validação, 4xx), **relatórios/exports** disponíveis.
- Telas `/view/*` (React): clique pelo Playwright; a API por trás está no `07_...`.
- Apps de celular (Q-Watcher, Vigilância, Frotas): não há como instalar — registre o que a tela web
  "Usuários" de cada app configura e o que os dashboards/mapas mostram; marque como "não exercitado".
- Nunca: apagar dado que não é `TESTE CP`; alterar Configurações/Parâmetros globais sem voltar ao
  valor; gravar a senha do banco que vaza em `/api/Escoltas/Filiais`.

## Fase B — comparar com o Conecta PRO (cave, não suponha)
Para cada recurso encontrado: `grep -rln` em `backend/modules` e `frontend/src/app`, abrir a tela no
redesign (`GET /api/v1/redesign/data/<slug>` no container efêmero — receita em
`docs/dgx/CONTRATO_AGENTE.md`), ler `auditoria/RELATORIO_NOITE_2026-09-13.md` e
`auditoria/RELATORIO_NOITE_2026-09-24.md` (o que já foi trazido ontem e hoje). Classifique:
**TEMOS** (igual ou melhor) · **TEMOS PARCIAL** (o quê falta) · **NÃO TEMOS** · **NÃO SE APLICA** (com
motivo — ex.: escolta não é o negócio).

## Fase C — a lista de lacunas
`docs/dgx/lacunas/<grupo>.md`: tabela `Recurso DGX | tela/fluxo | o que faz | Conecta PRO |
classificação | vale para a Conecta Mais? (alto/médio/baixo, por quê) | esforço (P/M/G)`. Ordene por
valor. Commit desta fase ANTES de implementar (é o que o Jordan lê se você não terminar).

## Fase D — implementar as lacunas (alto e médio valor, P/M de esforço), na ordem da lista
Regras de `docs/dgx/CONTRATO_AGENTE.md` valem inteiras (worktree, `_dgx_t<n>_<nome>.py`, `_ensure`
idempotente, porta no menu, oráculo, container efêmero com `--tmpfs /app/logs:rw,mode=1777` e as
pastas `backend/logs`/`backend/uploads` na worktree, commit por pathspec, relatório
`auditoria/frentes/DGX_T<n>_<grupo>.md`, mensagem final ≤ 40 linhas). O que ficar de fora (G, baixo
valor, não se aplica) vai no §5 do relatório com o motivo. Paralelo cego em tudo que toca folha.
Nada de Telegram, `alembic/versions/`, `docker-compose*`, `.env*`, `main_production.py`, `frontend/`.

Ao terminar, apague o que criou no DGX com prefixo `TESTE CP` **exceto o colaborador compartilhado**
(o orquestrador apaga no fim). Pare o container efêmero.
