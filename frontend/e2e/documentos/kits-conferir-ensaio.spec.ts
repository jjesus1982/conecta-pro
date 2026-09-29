/**
 * O ENSAIO da conferência de kits abre no NAVEGADOR e mostra o «Por quê».
 *
 * O Jordan autorizou esta tela com uma razão explícita: «ela vê antes de mexer — e mostra o
 * motivo, que é o que permite ela discordar de mim». Então o que se testa aqui não é o HTTP 200:
 * é a COLUNA DO MOTIVO renderizada, com texto dentro. Campo certo no JSON e coluna que não
 * aparece na tela é o defeito mais comum desta casa, e mediria como sucesso pelo despachante.
 *
 * ⚠️ TRÊS ARMADILHAS, e eu caí nas três escrevendo este arquivo:
 *
 * 1. **A tela não tem URL própria.** `/redesign/documentos/kits-conferir` devolve **404**. O
 *    ModuleView seleciona a tela pelo parâmetro `t` (`ModuleView.tsx:1261`).
 * 2. **`input` genérico com `.first()` pega a caixa «Buscar…» do cabeçalho**, não o campo do
 *    formulário — e o teste reprova uma tela boa dizendo que a competência veio vazia.
 * 3. **Há DOIS botões «Conferir»**: o do cabeçalho e o do cartão. Clicar no errado não roda nada.
 *
 * Os campos não têm `name`, `id` nem rótulo associado — o texto do rótulo é um elemento irmão.
 * Por isso o ancoradouro é o **placeholder**, que é único na tela.
 */
import { test, expect } from '@playwright/test';

const PLACEHOLDER_COMPETENCIA = /use BARRA nesta tela/i;

test.describe('Conferir kits do mês — ensaio', () => {
  test.slow(); // a flakiness aqui já foi medida como LENTIDÃO, não corrida

  test('o ensaio roda e a coluna «Por quê» aparece com o motivo', async ({ page }) => {
    await page.goto(`/redesign/documentos?t=kits-conferir&_cb=${Date.now()}`);
    await page.waitForLoadState('networkidle');

    const comp = page.getByPlaceholder(PLACEHOLDER_COMPETENCIA);
    await expect(comp).toBeVisible({ timeout: 30_000 });

    // O padrão chegou à tela: mês anterior, com BARRA (esta tela; o GEDEON usa ponto).
    await expect(comp).toHaveValue(/^\d{2}\/\d{4}$/);

    // ⭐ O ancoradouro certo é o <main> INTERNO: o cabeçalho (com o «Conferir» duplicado e a
    // caixa «Buscar…») fica FORA dele. Há dois <main> na página; o de dentro é o da tela.
    // Escopar por div «que contém o campo» não serve — o menor deles envolve só o input.
    const cartao = page.locator('main').last();

    // O caminho SEGURO é o default, de propósito: ninguém aplica sem escolher aplicar.
    await expect(cartao.locator('select').first()).toHaveValue('ensaio');

    await cartao.getByRole('button', { name: 'Conferir', exact: true }).click();

    // ⭐ O que esta tela existe para provar: o MOTIVO de cada linha, na tela.
    await expect(page.getByText(/Por qu[êe]/i).first()).toBeVisible({ timeout: 120_000 });
    await expect(page.getByText(/ENSAIO/i).first()).toBeVisible();

    await page.screenshot({ path: 'e2e/.out/kits-conferir-ensaio.png', fullPage: true });

    // ⚠️ O redesign NÃO usa <table>: a grade é montada com divs. Afirmar `table` reprovaria
    // uma tela que funciona — é o mesmo erro de alvo das outras três armadilhas deste arquivo.
    const corpo = await cartao.innerText();
    expect(corpo.length, 'a tabela do ensaio veio vazia').toBeGreaterThan(40);
    expect(corpo, 'nenhuma linha traz motivo — a coluna «Por quê» está vazia')
      .toMatch(/batida|trabalhou|condomínio|conferência/i);

    // 🔴 SOBREPOSIÇÃO MEDIDA (29/09): o selo de «O que acontece» é desenhado POR CIMA do
    // texto de «Por quê». A coluna do motivo é a razão de a tela existir — se a primeira linha
    // dela fica ilegível, a Pyetra perde exatamente o que lhe permite discordar.
    const selo = page.getByText(/remover \d+ vínculo/i).first();
    const motivo = page.getByText(/não tem nenhuma batida em posto/i).first();
    const [a, b] = [await selo.boundingBox(), await motivo.boundingBox()];
    if (a && b) {
      const sobrepoe = a.x < b.x + b.width && b.x < a.x + a.width
                    && a.y < b.y + b.height && b.y < a.y + a.height;
      expect(sobrepoe, `selo e motivo se sobrepõem na tela — selo=${JSON.stringify(a)} motivo=${JSON.stringify(b)}`)
        .toBe(false);
    }

    console.log('GRADE DO ENSAIO RENDERIZADA:\n' + corpo.slice(0, 1500));
  });
});
