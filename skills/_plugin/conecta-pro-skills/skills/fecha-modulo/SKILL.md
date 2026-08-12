---
name: fecha-modulo
description: QA end-to-end de um módulo do Conecta PRO DEPOIS de implementar — prova que o dado exibido bate com o banco, que a tela funciona no navegador e que a regressão não voltou. Use ao fechar trabalho num módulo, antes de dizer "pronto", antes de deploy, ou quando alguém (humano ou agente) reportar conclusão e você precisar conferir. Complementa raio-x-modulo (que mede alcance, não veracidade).
---

# Fecha módulo — QA E2E do Conecta PRO

Três lentes, um veredito. **A regra que governa tudo: evidência antes de afirmação.**

| Lente | Pergunta | Como |
|---|---|---|
| **DADO** | o exibido bate com o banco? | oráculos `scripts/orq/` + [[veracity-sweep]] |
| **TELA** | o clique funciona de verdade? | Playwright no navegador |
| **CÓDIGO** | a regressão não voltou? | baseline↔depois + `/code-review` no diff |

> **"NÃO VERIFICADO" é resultado válido. "Passou" sem evidência não é.**
> Se uma lente estiver bloqueada (sem credencial, sem container, sem oráculo), diga qual e
> por quê. Nunca converta ausência de teste em aprovação — é a mesma fabricação que o
> projeto proíbe no dado.

---

## Lente 1 · DADO — exibido == banco

Existem **81 oráculos** em `backend/scripts/orq/`. Eles chamam o builder e comparam com o banco.

```bash
cd /opt/conecta-pro
ls backend/scripts/orq/ | grep -iE "<modulo>|oraculo" | head
docker exec conecta-pro-backend python3 scripts/orq/test_oraculo_<alvo>.py
```

Gates conhecidos (rodar sempre que o arquivo correspondente mudar):

| Se mexeu em | Rode |
|---|---|
| `orquestrador/tools_rh_doc.py` | `test_oraculos_fase6_f6.py` e `_f7.py` |
| `redesign_builders/operacional.py` | `test_oraculo_op_dashboards_redesign.py` |
| RBAC / gates de módulo | `test_oraculos_rbac.py` |

Sem oráculo para a tela em questão: invoque **`veracity-sweep`** e prove por
`curl` (o que a API devolve) × `psql` (o que o banco tem). Divergência é achado, não ruído.

## Lente 2 · TELA — o clique funciona

**Regra da casa: API 200 ≠ entregue.** Builder correto e tela quebrada é o defeito mais
comum aqui. Só vale o que abriu no navegador.

```bash
# público, sempre com cache-bust — o nginx serve estático com cache longo
https://erp.conectamais.pro/redesign/<slug>?_cb=$(date +%s)
```

Use as tools `mcp__playwright__*`. Ao encerrar, **mate só o chromium do seu perfil**, nunca
`pkill chromium` (derruba sessão de outra pessoa).

**Credencial (verificado 2026-08-09):** `ERP_USER`/`ERP_PASS` **existem** no `.env` da raiz
e o login funciona. Sempre confira antes de desistir — esta linha já esteve errada:

```bash
grep -E "^ERP_(USER|PASS)=" /opt/conecta-pro/.env    # vazio = lente bloqueada
```

Duas armadilhas medidas nesta casa:

- **Sessão velha no perfil do navegador dá 403** e a tela renderiza o menu de fallback, sem
  os itens novos — parece "não subiu" e é só token expirado. `localStorage.clear()` e logue.
- **Viewport pequena faz o Playwright recusar clique** ("outside of the viewport") mesmo em
  `nav` rolável. Use `browser_resize` 1440×900 antes de acusar defeito de layout.

Se a credencial realmente faltar, a lente fica **NÃO VERIFICADA**: registre no relatório o
que alguém com acesso precisa conferir, em passos concretos ("abrir X, clicar Y, esperar Z").
Não invente aprovação e não force o login por outro caminho.

⚠️ **`type: "form"` só exibe `d.message`/`okMsg` e descarta o corpo**
(`ModuleView.tsx:495`). Tela de cálculo que responde 200/201 pode estar jogando o número
fora. Em qualquer tela que CALCULA, confira o corpo da resposta contra o que aparece —
"Calculado" sem número é defeito, não sucesso.

## Lente 3 · CÓDIGO — a regressão não voltou

**Sempre com baseline dos dois lados.** Contar falhas só depois não prova nada: o projeto
tem falhas pré-existentes (E2E que exigem API viva), e elas parecem culpa sua.

```bash
cd /opt/conecta-pro/backend
S=/tmp/qa; mkdir -p $S; F=<arquivo-que-voce-mudou>
cp $F $S/DEPOIS.py; git show HEAD:backend/$F > $S/BASE.py

cp $S/BASE.py $F;    echo "=== ANTES ===";  venv/bin/python -m pytest <suites> -p no:warnings 2>&1 | tail -1
cp $S/DEPOIS.py $F;  echo "=== DEPOIS ==="; venv/bin/python -m pytest <suites> -p no:warnings 2>&1 | tail -1
venv/bin/ruff check $F
```

Igual ou menor = sem regressão. **Maior = pare e investigue**, não justifique.

Depois: **`/code-review`** no diff (bugs de correção + simplificação) e
**`superpowers:verification-before-completion`** antes de qualquer frase de conclusão.

Se o trabalho tocou lógica não-trivial e **não deixou teste**, isso é um achado da
auditoria — não uma observação. Ponytail exige uma checagem executável por lógica não-trivial.

## Fronteiras (nunca cruzar em QA)

- **💰 dinheiro que sai: NUNCA happy-path.** Dispara OTP e PIX reais. Verifique por leitura de código e por registro no banco, jamais acionando.
- **🏛️ gov (eSocial/SPED/NFS-e):** transmitir em QA gera evento real no governo. Só leitura.
- **Operacional é curado à mão pelo Jordan e READ-ONLY para agentes.** Divergência vira relatório, nunca correção.
- **Não deployar** para validar. Se precisa de deploy, peça.

## Relatório

`auditoria/qa/<mod>_<AAAAMMDD>.md`, com **veredito por lente** e nada escondido:

```markdown
## Veredito
| Lente   | Status              | Evidência |
|---------|---------------------|-----------|
| DADO    | ✅ / ❌ / ⚠️ parcial | oráculo X: N/N · query vs curl |
| TELA    | 🚫 NÃO VERIFICADA   | sem ERP_PASS — passos p/ quem tem acesso |
| CÓDIGO  | ✅                  | ANTES 12 falhas → DEPOIS 9 (as 9 pré-existentes) |

## Achados
(defeito · onde · como reproduzir · impacto medido)

## Não coberto
(o que ficou de fora e por quê — nunca omitir)
```

## Ao auditar trabalho de terceiro (humano ou agente)

Não aceite o relatório pela palavra — **reproduza os números**. E confira sua própria
janela antes de acusar: nesta casa já quase reportei divergência de cobertura porque usei
30 dias e o builder usava mês corrente. **Os quatro números do outro estavam certos; a
janela errada era minha.**

Ao achar divergência real, separe: *o número está errado* × *a afirmação está errada*.
"100% pronto" pode significar "as telas mostram dado real" (verdade) e ao mesmo tempo
convivir com 93 rotas de escrita fora do redesign (também verdade). Pergunte o que a
palavra media antes de chamar de furo.

## Custo

~10–20 min por módulo, dependendo de quantas telas a lente 2 cobre. Exige
`conecta-pro-backend` de pé. A lente 3 exige o venv do host (o container não tem pytest).
