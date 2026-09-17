// Destino pós-login — o ÚNICO lugar que decide para onde a pessoa vai depois de entrar.
//
// Origem: 17/09/2026. A mesma linha `searchParams.get('redirect') || '/redesign'` estava
// copiada em três lugares do /login — e o callback do Google, que é o caminho que o próprio
// aviso "Portal atualizado" manda o funcionário usar, não era um deles: tinha '/redesign'
// fixo no código e nem olhava o ?redirect=. Resultado medido no nginx: 69 IPs distintos
// vindos do link de assinatura caíram no painel da empresa em vez da aba de assinar.
//
// Regra: quem tem destino declarado vai para ele. Quem não tem vai para o lugar do seu
// papel — `funcionario` (67 usuários) não tem o que fazer no painel da empresa.

const PADRAO_EMPRESA = '/redesign';
const PADRAO_FUNCIONARIO = '/modulos/meu-espaco';
const CHAVE_DESTINO = 'destino_pos_login';

/**
 * Só aceita caminho interno. `//evil.com`, `https://evil.com` e `/\evil.com` são
 * redirect aberto — o browser trata os dois primeiros como host externo.
 */
export function destinoSeguro(valor: string | null | undefined): string | null {
  if (!valor || !valor.startsWith('/')) return null;
  if (valor.startsWith('//') || valor.startsWith('/\\')) return null;
  return valor;
}

/** Para onde mandar a pessoa depois de autenticar. */
export function destinoPosLogin(
  redirect: string | null | undefined,
  role?: string | null,
): string {
  return (
    destinoSeguro(redirect) ??
    (role === 'funcionario' ? PADRAO_FUNCIONARIO : PADRAO_EMPRESA)
  );
}

/**
 * Guarda o destino antes de sair para o Google. O botão é um <a href> comum: a aba
 * sobrevive ao round-trip do OAuth, então sessionStorage volta preenchido no callback.
 * Não dá para usar o `state` do OAuth sem mexer no backend, e não precisa.
 */
export function guardarDestino(redirect: string | null | undefined): void {
  const destino = destinoSeguro(redirect);
  try {
    if (destino) sessionStorage.setItem(CHAVE_DESTINO, destino);
    else sessionStorage.removeItem(CHAVE_DESTINO);
  } catch {
    // Navegação anônima com storage bloqueado: cai no padrão por papel. Não é erro.
  }
}

/** Lê e consome o destino guardado, na volta do Google. */
export function resgatarDestino(): string | null {
  try {
    const destino = sessionStorage.getItem(CHAVE_DESTINO);
    sessionStorage.removeItem(CHAVE_DESTINO);
    return destinoSeguro(destino);
  } catch {
    return null;
  }
}
