'use client';

import { useEffect } from 'react';

/**
 * Existiam DUAS telas de login. Esta era a bonita e a mais fraca: sem Google, sem
 * entrar-com-o-rosto, sem primeiro acesso, e — o pior — jogava fora qualquer destino que
 * não começasse com `/redesign` (`redirect.startsWith('/redesign') ? redirect : '/redesign'`).
 * Era exatamente o defeito de 17/09/2026 que perdeu 69 pessoas vindas do link de assinatura.
 *
 * A tela viva é `/login`, que desde 17/09/2026 veste a identidade do redesign. Aqui fica só
 * o encaminhamento, preservando o destino — quem tiver esta URL salva não se perde.
 */
export default function RedesignLoginRedirect() {
  useEffect(() => {
    const q = window.location.search;
    window.location.replace(`/login${q}`);
  }, []);
  return null;
}
