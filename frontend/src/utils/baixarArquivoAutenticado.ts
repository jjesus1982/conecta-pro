/**
 * Baixa um arquivo protegido por autenticação (endpoint que exige Bearer).
 *
 * Corrige o bug de `window.open(file_url)`: a navegação do browser NÃO envia o
 * token do localStorage, então endpoints protegidos respondem 401. Aqui fazemos
 * um fetch com o header Authorization, transformamos a resposta em blob e
 * disparamos o download via <a download>.
 *
 * @param fileUrl  URL (relativa, mesma origem) do arquivo a baixar.
 * @param filename Nome sugerido para o arquivo salvo (opcional; senão usa o
 *                 Content-Disposition do servidor ou o último segmento da URL).
 */
export async function baixarArquivoAutenticado(
  fileUrl: string,
  filename?: string,
): Promise<void> {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('access_token') || localStorage.getItem('token')
      : null;

  const res = await fetch(fileUrl, {
    method: 'GET',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!res.ok) {
    let detail = `Erro ${res.status} ao baixar arquivo`;
    try {
      const err = await res.json();
      if (err?.detail) detail = err.detail;
    } catch {
      /* resposta não-JSON; mantém mensagem padrão */
    }
    throw new Error(detail);
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;

  let downloadName = filename;
  if (!downloadName) {
    const cd = res.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="?([^";]+)"?/);
    downloadName = match?.[1] ?? fileUrl.split('/').pop() ?? 'arquivo';
  }
  a.download = downloadName;

  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
