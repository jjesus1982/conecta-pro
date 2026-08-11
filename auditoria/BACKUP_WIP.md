# Backup do trabalho NÃO COMMITADO (2026-08-10)

Havia **1.149 linhas em 53 arquivos** pendentes na árvore de trabalho, de várias sessões —
incluindo coisa boa e sem commit há horas:

- `ModuleView.tsx` — filtro de tabela por coluna invisível, largura de coluna, e o fix do
  rodapé que mostrava **"Jordan Jesus" para qualquer usuário logado** (a Pyetra via o nome
  dele na conta dela)
- `session_guardian.sh`, `deploy-frontend.sh`, `qa_ged_browser.py`, `redesign.css`, `shell.tsx`

Trabalho sem commit morre com a sessão. **Não commitei o que é de outro** — as sessões estão
vivas e podem estar no meio de uma edição; commitar por cima seria pior que o risco.

## O que fiz

Um objeto de backup no próprio git, **sem tocar na árvore de trabalho**:

```bash
git stash create        # cria os objetos, NÃO mexe no worktree
git update-ref refs/backup/wip-2026-08-10 <sha>   # ancora, senão o gc leva
```

Ref: `refs/backup/wip-2026-08-10` → `239eed96`

## Como recuperar

```bash
# ver tudo que estava pendente
git show --stat refs/backup/wip-2026-08-10

# um arquivo específico
git show refs/backup/wip-2026-08-10:frontend/src/components/redesign/ModuleView.tsx

# restaurar um arquivo
git show refs/backup/wip-2026-08-10:<caminho> > <caminho>

# ou aplicar tudo como patch
git diff HEAD refs/backup/wip-2026-08-10 > /tmp/wip.patch
```

## Para quem é dono desse trabalho

**Commite.** O backup é rede, não substituto — ele congela o estado das 17h de 10/08 e não
acompanha o que você editar depois. E apague a ref quando não precisar mais:
`git update-ref -d refs/backup/wip-2026-08-10`.
