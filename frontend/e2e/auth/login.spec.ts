import { test, expect } from '@playwright/test';
import { loginViaAPI } from '../helpers/auth';
import { SENHA } from '../_credenciais';

test.describe('Autenticação - Login', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('deve exibir página de login corretamente', async ({ page }) => {
    // Verifica título da página
    await expect(page).toHaveTitle(/Conecta/i);

    // Verifica elementos principais
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
    await expect(page.locator('text=Bem-vindo de volta')).toBeVisible();
  });

  test('deve fazer login com credenciais válidas', async ({ page }) => {
    // Mock do endpoint de login para sucesso
    await page.route('**/api/v1/auth/login', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          access_token: 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkBjb25lY3RhcGx1cy5jb20uYnIiLCJleHAiOjE3NzI2NTUyMzUsInVzZXJfaWQiOiJhMWIyYzNkNC1lNWY2LTc4OTAtYWJjZC1lZjEyMzQ1Njc4OTAiLCJ0ZW5hbnRfaWQiOiJhMWIyYzNkNC1lNWY2LTc4OTAtYWJjZC1lZjEyMzQ1Njc4OTAiLCJyb2xlIjoiYWRtaW4iLCJwZXJtaXNzaW9ucyI6WyIqIl19.lZ87J5aTHd9Ia3Gi1bKHOav2edxml12AtT6o_jf-umM',
          refresh_token: 'refresh_token_mock',
          token_type: 'bearer',
        }),
      });
    });

    // Mock do endpoint /auth/me
    await page.route('**/api/v1/auth/me', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
          email: 'admin@conectaplus.com.br',
          name: 'Admin',
          role: 'admin',
          is_active: true,
          permissions: ['*'],
          tenant_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        }),
      });
    });

    // Preenche formulário
    await page.fill('input[type="email"]', 'admin@conectaplus.com.br');
    await page.fill('input[type="password"]', SENHA);
    await page.click('button[type="submit"]');

    // Verifica redirecionamento
    await expect(page).toHaveURL(/\/(dashboard|modulos)/, { timeout: 10000 });
  });

  test('deve mostrar erro com credenciais inválidas', async ({ page }) => {
    // Mock do endpoint de login para erro
    await page.route('**/api/v1/auth/login', (route) => {
      route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({
          detail: 'Credenciais inválidas',
        }),
      });
    });

    await page.fill('input[type="email"]', 'invalido@teste.com');
    await page.fill('input[type="password"]', 'senhaerrada');
    await page.click('button[type="submit"]');

    // Verifica mensagem de erro
    await expect(page.locator('text=Credenciais inválidas')).toBeVisible({ timeout: 5000 });

    // Verifica que permanece na página de login
    await expect(page).toHaveURL(/\/login/);
  });

  test('deve validar campos obrigatórios', async ({ page }) => {
    // Tenta enviar formulário vazio
    await page.click('button[type="submit"]');

    // Verifica validação HTML5 do campo email
    const emailInput = page.locator('input[type="email"]');
    await expect(emailInput).toHaveAttribute('required', '');

    // Verifica validação HTML5 do campo password
    const passwordInput = page.locator('input[type="password"]');
    await expect(passwordInput).toHaveAttribute('required', '');
  });

  test('deve fazer logout com sucesso', async ({ page }) => {
    // Realiza login via API helper
    await loginViaAPI(page);

    // Navega para o dashboard
    await page.goto('/dashboard');

    // Aguarda carregamento
    await expect(page.locator('text=Bom dia, Admin')).toBeVisible({ timeout: 10000 });

    // Clica no botão de logout
    await page.click('button:has([name="logout"]), button:has(.lucide-logout), button:has([class*="logout"])');

    // Verifica redirecionamento para login
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
  });

  test('deve redirecionar para dashboard se já autenticado', async ({ page }) => {
    // Injeta token no localStorage
    await page.addInitScript(() => {
      localStorage.setItem('access_token', 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbkBjb25lY3RhcGx1cy5jb20uYnIiLCJleHAiOjE3NzI2NTUyMzV9.test');
    });

    // Mock do endpoint /auth/me
    await page.route('**/api/v1/auth/me', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
          email: 'admin@conectaplus.com.br',
          name: 'Admin',
          role: 'admin',
          is_active: true,
          permissions: ['*'],
          tenant_id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
        }),
      });
    });

    // Tenta acessar login estando autenticado
    await page.goto('/login');

    // Aguarda possível redirecionamento
    await page.waitForTimeout(2000);

    // Verifica se foi redirecionado
    const url = page.url();
    expect(url).toMatch(/\/(dashboard|modulos)/);
  });

  test('deve ter link "Esqueci a senha" funcional', async ({ page }) => {
    const forgotPasswordLink = page.locator('a:has-text("Esqueci a senha"), a:has-text("esqueci")');
    await expect(forgotPasswordLink).toBeVisible();
    await expect(forgotPasswordLink).toHaveAttribute('href', '#');
  });

  test('deve ter checkbox "Lembrar-me"', async ({ page }) => {
    const rememberCheckbox = page.locator('input[type="checkbox"]');
    await expect(rememberCheckbox).toBeVisible();

    // Verifica se pode ser marcado
    await rememberCheckbox.check();
    await expect(rememberCheckbox).toBeChecked();
  });
});

test.describe('Autenticação - Proteção de Rotas', () => {
  test('deve redirecionar para login ao acessar dashboard sem autenticação', async ({ page }) => {
    // Limpa qualquer autenticação existente
    await page.goto('/dashboard');

    // Aguarda redirecionamento
    await page.waitForTimeout(2000);

    // Verifica se foi redirecionado para login
    await expect(page).toHaveURL(/\/login/);
  });

  test('deve redirecionar para login ao acessar módulos sem autenticação', async ({ page }) => {
    await page.goto('/modulos');

    // Aguarda redirecionamento
    await page.waitForTimeout(2000);

    // Verifica se foi redirecionado para login
    await expect(page).toHaveURL(/\/login/);
  });
});
