/**
 * Credencial da suíte e2e — vem do AMBIENTE, nunca do repositório.
 *
 * 🔴 29/09/2026. Catorze arquivos da suíte tinham `admin@conectapro.com.br` / `admin123`
 * escritos no código. Duas coisas erradas numa:
 *
 * 1. **Senha em arquivo versionado.**
 * 2. **Essa conta está DESATIVADA** — então a suíte inteira estava quebrada. O `auth.setup.ts`
 *    falhava no login e os testes dependentes nem rodavam: a lente de navegador estava cega há
 *    meses e ninguém sabia, porque um teste que não roda não fica vermelho de forma visível.
 *
 * Use assim:
 *
 *     import { USUARIO, SENHA, corpoLoginUrlEncoded } from './_credenciais';
 *
 * `ERP_USER`/`ERP_PASS` já existem no `.env` da raiz e são o que o resto da casa usa. Carregue
 * antes de rodar:
 *
 *     set -a; . /opt/conecta-pro/.env; set +a; npx playwright test
 *
 * ⚠️ Sem as variáveis, `exigirCredencial()` FALHA DIZENDO O QUE FAZER. O anterior tentava uma
 * conta morta e escondia o motivo atrás de um `isAuthenticated: false`.
 */

export const USUARIO = process.env.ERP_USER || '';
export const SENHA = process.env.ERP_PASS || '';

/** Lança com instrução acionável quando o ambiente não foi carregado. */
export function exigirCredencial(): { usuario: string; senha: string } {
  if (!USUARIO || !SENHA) {
    throw new Error(
      'ERP_USER/ERP_PASS ausentes. Rode: set -a; . /opt/conecta-pro/.env; set +a; ' +
        'npx playwright test — a suíte não usa credencial escrita no repositório.',
    );
  }
  return { usuario: USUARIO, senha: SENHA };
}

/** Corpo `application/x-www-form-urlencoded` do `POST /auth/login` (o formato que a API exige). */
export function corpoLoginUrlEncoded(): string {
  const { usuario, senha } = exigirCredencial();
  return `username=${encodeURIComponent(usuario)}&password=${encodeURIComponent(senha)}`;
}

/** Corpo JSON, para os testes que montam `{ username, password }`. */
export function corpoLoginJson(): { username: string; password: string } {
  const { usuario, senha } = exigirCredencial();
  return { username: usuario, password: senha };
}
