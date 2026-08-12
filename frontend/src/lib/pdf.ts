// Helper único do sistema para VER / BAIXAR qualquer PDF protegido por token.
// O <a href> não carrega o Bearer (o token vive no localStorage, não em cookie),
// então buscamos via fetch com Authorization e abrimos/baixamos o blob.
// Mostra a mensagem de erro REAL do servidor (ex.: "espelho ainda não calculado").
export async function abrirPdf(url: string, opts: { download?: boolean; nome?: string } = {}) {
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('access_token') ?? localStorage.getItem('token') ?? '') : ''
  const sep = url.includes('?') ? '&' : '?'
  const full = opts.download ? `${url}${sep}download=1` : url
  let res: Response
  try {
    res = await fetch(full, { headers: { Authorization: `Bearer ${token}` } })
  } catch {
    alert('Falha de rede ao abrir o PDF.')
    return
  }
  if (!res.ok) {
    let msg = `Não foi possível abrir o PDF (HTTP ${res.status}).`
    try {
      const j = await res.json()
      if (j?.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch { /* corpo não-JSON */ }
    alert(msg)
    return
  }
  const blob = await res.blob()
  const objUrl = URL.createObjectURL(blob)
  if (opts.download) {
    const a = document.createElement('a')
    a.href = objUrl
    a.download = opts.nome || ''
    document.body.appendChild(a)
    a.click()
    a.remove()
  } else {
    window.open(objUrl, '_blank', 'noopener')
  }
  setTimeout(() => URL.revokeObjectURL(objUrl), 60000)
}
