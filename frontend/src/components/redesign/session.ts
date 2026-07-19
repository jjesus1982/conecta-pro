// Sessão do redesign — logout reversível (limpa token + cookie e volta ao login).
export function rdLogout() {
  try {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  } catch { /* */ }
  try { document.cookie = 'auth_token=; path=/; max-age=0'; } catch { /* */ }
  window.location.href = '/redesign/login';
}
