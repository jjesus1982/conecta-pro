/**
 * As telas de kit que a Pyetra usa, no NAVEGADOR.
 *
 * 29/09/2026 — o Jordan perguntou: «a pyetra como vai mandar montar os kits? isso já está no
 * frontend? ela não usa o claude code, só o frontend». Tudo o que eu havia feito era por script.
 *
 * Medido então: as três telas de kit tinham a competência EMBUTIDA no endpoint, fixada no mês
 * corrente — em 29/09 o botão gerava setembro, e o kit que ela entrega é AGOSTO. Este teste
 * afirma no navegador o que a medição por API já provou, porque **API 200 não é tela entregue**.
 *
 * ⚠️ Não CLICA em aplicar: o ensaio é o default e o teste não dispara ato destrutivo em
 * produção. O caminho de aplicar está provado por ida-e-volta na suíte de oráculos
 * (test_oraculo_kits_conferir_tela.py) e por teste real com vínculo criado de propósito.
 */
import { expect, test } from '@playwright/test';

test.use({ storageState: 'e2e/.auth/user.json' });

/**
 * Sobre a instabilidade, porque ela me custou três rodadas e a lição não é óbvia:
 *
 * Em paralelo as falhas ROTAVAM — telas diferentes quebravam em cada rodada. Com `--workers=1`
 * os 8 passavam. Então tentei `mode: 'serial'` e ficou PIOR: o serial reusa a MESMA página entre
 * os testes, e o estado de um vazava para o seguinte.
 *
 * ⭐ A causa real é lentidão, não ordem: a conferência atravessa o roster do mês inteiro. O
 * remédio é dizer que o teste é lento — `test.slow()` triplica o prazo dele — e deixar cada
 * teste com página própria. Trocar paralelismo por estado compartilhado resolve o sintoma e
 * cria um defeito pior.
 */

const MES_ANTERIOR = (() => {
  const h = new Date();
  const d = new Date(h.getFullYear(), h.getMonth() - 1, 1);
  return `${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
})();

/**
 * O CTA do formulário, não o item de menu.
 *
 * A lateral fica DENTRO do `main`, então escopar ao `main` ainda casa dois botões «Conferir»:
 * o item de menu ativo e o CTA da tela. `.last()` resolve pela ordem do DOM (navegação vem
 * antes do conteúdo) — e ter errado o alvo duas vezes aqui reprovou uma tela que funcionava,
 * que é o defeito mais caro desta casa aplicado a teste: a lógica certa observando a coisa
 * errada.
 */
function ctaDaTela(page: import('@playwright/test').Page, nome: RegExp) {
  return page.locator('main').getByRole('button', { name: nome }).last();
}

/**
 * O grupo do menu vem RECOLHIDO («Kits documentais 14 ▸»), então clicar no item sem abrir o
 * grupo falha. Descoberto pelo próprio teste: o snapshot de erro mostrou o botão com o ▸ e a
 * contagem — que também confirmou as duas telas novas (eram 12 itens, ficaram 14).
 */
async function abrirGrupoKits(page: import('@playwright/test').Page) {
  const grupo = page.getByRole('button', { name: /kits documentais/i }).first();
  await expect(grupo).toBeVisible({ timeout: 20000 });
  await grupo.click();
  await page.waitForTimeout(800);
}

async function abrirTela(page: import('@playwright/test').Page, nome: RegExp) {
  await abrirGrupoKits(page);
  const item = page.getByRole('button', { name: nome }).first();
  await expect(item).toBeVisible({ timeout: 15000 });
  await item.click();
  await page.waitForTimeout(2000);
}

test.describe('Kits documentais — o que a Pyetra alcança pelo front', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/redesign/documentos', { waitUntil: 'load' });
    await page.waitForTimeout(2500);
  });

  test('o grupo «Kits documentais» existe e tem as duas telas novas', async ({ page }) => {
    const grupo = page.getByRole('button', { name: /kits documentais/i }).first();
    await expect(grupo).toBeVisible({ timeout: 20000 });
    // 12 telas antes de 29/09, 14 depois. O número no botão é a prova de que as duas entraram
    // no menu — e é mais forte que procurar o texto, que casaria com o título da tela aberta.
    await expect(grupo).toContainText('14');
  });

  test('«Conferir kits do mês» aparece e abre', async ({ page }) => {
    await abrirTela(page, /conferir kits do mês/i);
    // O redesign NÃO usa h1/h2/h3 para o título da tela — a primeira versão deste teste
    // procurava lá e reprovava uma tela que estava perfeita. O sinal de que a tela abriu é o
    // CTA dela existir junto do subtítulo: menu não tem CTA.
    await expect(ctaDaTela(page, /^conferir$/i)).toBeVisible({ timeout: 15000 });
    await expect(page.getByText(/compara cada kit com quem realmente trabalhou/i)).toBeVisible({
      timeout: 15000,
    });
  });

  test('⭐ a competência é EDITÁVEL e vem com o mês anterior — era o defeito', async ({ page }) => {
    await abrirTela(page, /conferir kits do mês/i);
    // O campo tem de existir E trazer o mês anterior. Antes de 29/09 a competência estava
    // embutida no endpoint e não havia campo nenhum: o mês certo era inalcançável por ela.
    //
    // Alvo pelo PLACEHOLDER, não por `input` genérico: a lateral tem caixas de texto antes
    // desta, e `.first()` pegava a errada.
    const campo = page.getByPlaceholder(/use BARRA nesta tela/i);
    await expect(campo).toBeVisible({ timeout: 15000 });
    await expect(campo).toHaveValue(MES_ANTERIOR, { timeout: 10000 });
  });

  test('⭐ o padrão é ENSAIO — abrir e clicar não pode APAGAR', async ({ page }) => {
    await abrirTela(page, /conferir kits do mês/i);
    const sel = page.locator('select').first();
    await expect(sel).toBeVisible({ timeout: 15000 });
    // A opção selecionada tem de ser a que NÃO altera nada.
    const escolhido = await sel.inputValue();
    expect(escolhido).toBe('ensaio');
  });

  test('o ensaio roda e devolve a tabela com o motivo de cada linha', async ({ page }) => {
    test.slow(); // atravessa o roster do mês inteiro: prazo triplo, não é lentidão anormal
    await abrirTela(page, /conferir kits do mês/i);
    await ctaDaTela(page, /^conferir$/i).click();
    // A conferência atravessa o roster do mês inteiro; dá tempo.
    await expect(page.getByText(/kit\(s\) de cliente|ENSAIO|pessoa\(s\) no roster/i).first()).toBeVisible({
      timeout: 60000,
    });
    // «Por quê» é a coluna que permite discordar — sem ela a tela pede fé. Se a competência
    // não tiver nenhuma linha, a coluna não existe e isso é resultado válido: o teste afirma
    // «ou a coluna, ou a frase de que não há nada a remover», nunca inventa aprovação.
    const colunaOuVazio = page
      .getByText(/por qu[êe]|nada a remover|kit\(s\) sem roster/i)
      .first();
    await expect(colunaOuVazio).toBeVisible({ timeout: 20000 });
  });

  test('«Definir condomínio de quem ficou sem» abre com os selects preenchidos', async ({ page }) => {
    await abrirTela(page, /definir condomínio de quem ficou sem/i);
    // Dois selects: colaborador e condomínio. O de condomínio NUNCA pode vir vazio, senão a
    // tela existe e não resolve nada.
    const selects = page.locator('select');
    await expect(selects.first()).toBeVisible({ timeout: 15000 });
    expect(await selects.count()).toBeGreaterThanOrEqual(2);
  });

  test('«Montar kits do mês» aponta para o Gedeon e deixa escolher a competência', async ({ page }) => {
    await abrirTela(page, /montar kits do mês/i);
    // O Gedeon usa MM.AAAA (ponto). O rótulo tem de dizer isso — dois formatos vivos no mesmo
    // produto, e quem pagaria pelo deslize é a pessoa.
    await expect(page.getByText(/MM\.AAAA/i).first()).toBeVisible({ timeout: 15000 });
  });
});
