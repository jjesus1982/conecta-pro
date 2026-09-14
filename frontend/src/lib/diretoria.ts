/**
 * Quem é a DIRETORIA da Conecta Mais — fonte única do front.
 *
 * Existia chumbado em dois lugares, cada um com o seu literal:
 *   - `pagamentos/page.tsx`: `setIsJordan(email === "jjesus@..." || email === "jordansjesus@...")`
 *     escondia a aba Audit Log E o botão "Aprovar" (a Pyetra lia "Aguardando Jordan").
 *   - `configuracoes/usuarios/page.tsx`: `JORDAN_EMAIL` marcava "(CEO)", o selo
 *     "Acesso Total" e protegia o registro de ser editado/desativado.
 *
 * Decisão do Jordan em 14/09/2026: *"o perfil da Andrya Pyetra Souza de Jesus, login
 * pjesus@conectamais.pro, precisa ter o mesmo perfil full que eu tenho"*.
 *
 * ⚠️ Isto NÃO é "quem é admin" — admin é papel e vem do backend. Isto é a camada acima:
 * o que é restrito à diretoria e onde nem outro admin entra. O gate que VALE é sempre o
 * do servidor (`core/auth/diretoria.py`); aqui é só o que a tela mostra.
 */

/** E-mails da diretoria. `jordansjesus@gmail.com` é o login alternativo do Jordan. */
export const DIRETORIA = [
  'jjesus@conectamais.pro',
  'jordansjesus@gmail.com',
  'pjesus@conectamais.pro',
] as const;

/** True se o e-mail é da diretoria. Tolera null, espaço e caixa alta. */
export function eDiretoria(email?: string | null): boolean {
  return DIRETORIA.includes((email ?? '').trim().toLowerCase() as (typeof DIRETORIA)[number]);
}
