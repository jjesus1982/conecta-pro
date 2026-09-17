'use client';

/**
 * Busca de telas do topo — o campo "Buscar…" do shell.
 *
 * Origem: 17/09/2026. O Jordan: «to super perdido no sistema, tudo muito confuso, difícil de
 * achar as coisas....tá foda». Medido naquele dia: 291 abas em 25 módulos e 587 telas, e o
 * campo de busca do shell era um `<input>` SEM UMA LINHA DE CÓDIGO — digitar não fazia nada.
 * Não havia como achar nada senão clicando por um menu de centenas de linhas.
 *
 * Duas fontes, porque o menu mora em dois lugares e nenhum dos dois basta sozinho:
 *   · os pacotes JSON locais (`MODULES`) — as abas BASE de cada módulo, sem rede;
 *   · `GET /api/v1/redesign/indice` — as abas EXTRA, que só o backend conhece. Buscar
 *     "diária" sem ela devolvia zero, com a tela de diaristas existindo o tempo todo.
 *
 * O índice remoto é opcional de propósito: se a rede falhar, a busca segue funcionando com o
 * que é local. Melhor achar metade do que não achar nada.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Search, CornerDownLeft } from 'lucide-react';
import { MODULES } from './modules';

export type Alvo = { slug: string; id: string; label: string };

/** Sem acento e sem pontuação: quem digita "ferias" tem de achar "Férias". */
export function normalizar(s: string): string {
  return s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

const TITULO: Record<string, string> = {
  'departamento-pessoal': 'Departamento Pessoal', 'gestao-de-pessoas': 'Gestão de Pessoas',
  'portal-do-funcionario': 'Portal do Funcionário', 'saude-ocupacional': 'Saúde Ocupacional',
  'orquestrador-executivo': 'Orquestrador', 'area-do-cliente': 'Área do Cliente',
  'consultor-ia': 'Consultor IA', 'meu-espaco': 'Meu Espaço', rh: 'Recursos Humanos',
  crm: 'CRM', bi: 'BI', fiscal: 'Fiscal & Contábil',
};
export const titulo = (slug: string) =>
  TITULO[slug] ?? slug.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/**
 * Filtra e ordena — a lógica inteira da busca, pura para poder ser travada por teste.
 *
 * Exige TODAS as palavras do termo (quem digita "assinar recibo" não quer tudo que tem
 * "recibo"), e ordena por precisão: nome exato, depois quem começa com o termo, depois o
 * resto; empate desempata pelo rótulo mais curto — o mais específico costuma ser o menor.
 */
const RAIZ_MIN = 5;

/**
 * Uma palavra do termo casa com o alvo.
 *
 * Substring resolve quase tudo, mas não o caso que motivou a busca: quem procura a tela de
 * diaristas digita "diária", e `"diaria"` NÃO está contido em `"diaristas"` — as duas
 * divergem no sexto caractere. Por isso também casa quando termo e palavra do alvo
 * compartilham uma raiz de ao menos 5 letras: "diari" serve a diária, diárias e diaristas.
 * Radical curto demais colaria coisas sem parentesco ("cont" → contrato, contábil, conta).
 */
function casaPalavra(p: string, alvo: string): boolean {
  if (alvo.includes(p)) return true;
  if (p.length < RAIZ_MIN) return false;
  return alvo.split(' ').some((w) => {
    if (w.length < RAIZ_MIN) return false;
    let i = 0;
    while (i < p.length && i < w.length && p[i] === w[i]) i++;
    return i >= RAIZ_MIN;
  });
}

export function filtrar(universo: Alvo[], termo: string, teto = 12): Alvo[] {
  const q = normalizar(termo);
  if (q.length < 2) return [];
  const partes = q.split(' ').filter(Boolean);
  const pontua = (a: Alvo): number => {
    const alvo = normalizar(`${a.label} ${titulo(a.slug)}`);
    if (!partes.every((p) => casaPalavra(p, alvo))) return -1;
    const rot = normalizar(a.label);
    if (rot === q) return 0;
    if (rot.startsWith(q)) return 1;
    return 2;
  };
  return universo
    .map((a) => ({ a, p: pontua(a) }))
    .filter((x) => x.p >= 0)
    .sort((x, y) => x.p - y.p || x.a.label.length - y.a.label.length)
    .slice(0, teto)
    .map((x) => x.a);
}

/** Abas dos pacotes locais. Roda uma vez: `MODULES` é import estático. */
function alvosLocais(): Alvo[] {
  const out: Alvo[] = [];
  for (const [slug, pac] of Object.entries(MODULES || {})) {
    for (const it of ((pac as { menu?: Alvo[] })?.menu ?? [])) {
      if (it?.id && it?.label) out.push({ slug, id: it.id, label: it.label });
    }
  }
  return out;
}

/**
 * Painel de busca — abre com Ctrl+K (ou pelo botão da barra) e some com Esc.
 *
 * Deliberadamente NÃO substitui o campo «Buscar…» do topo: aquele filtra o conteúdo da tela
 * ABERTA (a tabela), é outra função e é útil. Eu quase o troquei por este — o campo morto que
 * eu tinha visto está no `shell.tsx`, que nenhuma tela usa. Duas buscas com papéis diferentes
 * pedem dois lugares: o campo filtra o que está na frente, o Ctrl+K leva para outra tela.
 */
export function BuscaTelas() {
  const router = useRouter();
  const [termo, setTermo] = useState('');
  const [aberto, setAberto] = useState(false);
  const [remotos, setRemotos] = useState<Alvo[]>([]);
  const [cursor, setCursor] = useState(0);
  const caixa = useRef<HTMLDivElement>(null);
  const campo = useRef<HTMLInputElement>(null);

  // Índice remoto: uma vez por sessão. Falha em silêncio — ver nota no topo.
  useEffect(() => {
    let vivo = true;
    fetch('/api/v1/redesign/indice', {
      headers: { Authorization: `Bearer ${localStorage.getItem('access_token') ?? ''}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((j) => { if (vivo && Array.isArray(j?.itens)) setRemotos(j.itens); });
    return () => { vivo = false; };
  }, []);

  const universo = useMemo(() => {
    const vistos = new Set<string>();
    const out: Alvo[] = [];
    for (const a of [...alvosLocais(), ...remotos]) {
      const chave = `${a.slug}:${a.id}`;
      if (vistos.has(chave)) continue;   // a mesma aba nas duas fontes é uma só
      vistos.add(chave);
      out.push(a);
    }
    return out;
  }, [remotos]);

  const achados = useMemo(() => filtrar(universo, termo), [termo, universo]);

  useEffect(() => setCursor(0), [termo]);

  // Ctrl+K / Cmd+K de qualquer lugar; Esc fecha.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        campo.current?.focus();
        setAberto(true);
      }
      if (e.key === 'Escape') setAberto(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // Clique fora fecha — senão a lista fica pendurada sobre a tela.
  useEffect(() => {
    const fora = (e: MouseEvent) => {
      if (caixa.current && !caixa.current.contains(e.target as Node)) setAberto(false);
    };
    document.addEventListener('mousedown', fora);
    return () => document.removeEventListener('mousedown', fora);
  }, []);

  const ir = (a: Alvo) => {
    setAberto(false);
    setTermo('');
    router.push(`/redesign/${a.slug}?t=${a.id}`);
  };

  const teclas = (e: React.KeyboardEvent) => {
    if (!achados.length) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => (c + 1) % achados.length); }
    if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => (c - 1 + achados.length) % achados.length); }
    // O cursor pode apontar fora da lista: ele é zerado por efeito DEPOIS do render em que
    // `achados` encolheu. Enter nesse instante chamaria `ir(undefined)`.
    if (e.key === 'Enter') {
      e.preventDefault();
      const alvo = achados[cursor] ?? achados[0];
      if (alvo) ir(alvo);
    }
  };

  if (!aberto) return null;

  return (
    <div
      role="presentation"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setAberto(false); }}
      style={{
        position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(3,8,20,.55)',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '12vh',
      }}
    >
      <div
        ref={caixa}
        style={{
          width: 'min(620px, 92vw)', background: 'var(--card, #12203f)',
          border: '1px solid var(--border, #24365f)', borderRadius: 12,
          boxShadow: '0 24px 60px rgba(0,0,0,.5)', overflow: 'hidden',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '12px 16px',
                      borderBottom: '1px solid var(--border, #24365f)' }}>
          <Search size={17} color="var(--placeholder, #8ea2c9)" />
          <input
            ref={campo}
            value={termo}
            placeholder="Buscar tela pelo nome — assinatura, ponto, férias…"
            onChange={(e) => setTermo(e.target.value)}
            onKeyDown={teclas}
            aria-label="Buscar tela"
            autoFocus
            style={{
              flex: 1, background: 'transparent', border: 'none', outline: 'none',
              color: 'inherit', fontSize: 15,
            }}
          />
          <kbd style={{ fontSize: 10, opacity: .55, border: '1px solid currentColor',
                        borderRadius: 4, padding: '1px 5px' }}>Esc</kbd>
        </div>

        <div role="listbox" aria-label="Telas encontradas" style={{ maxHeight: '52vh', overflowY: 'auto' }}>
          {normalizar(termo).length < 2 ? (
            <div style={{ padding: '18px 18px', fontSize: 13, color: 'var(--placeholder, #8ea2c9)' }}>
              Digite o nome da tela. São {universo.length} telas — «assinatura», «diária»,
              «ponto», «férias», «holerite».
            </div>
          ) : achados.length === 0 ? (
            <div style={{ padding: '18px', fontSize: 13, color: 'var(--placeholder, #8ea2c9)' }}>
              Nada com “{termo}”. A busca lê o NOME da tela — tente o assunto.
            </div>
          ) : (
            achados.map((a, i) => (
              <button
                key={`${a.slug}:${a.id}`}
                type="button"
                role="option"
                aria-selected={i === cursor}
                onMouseEnter={() => setCursor(i)}
                onClick={() => ir(a)}
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  gap: 12, width: '100%', textAlign: 'left', padding: '11px 16px',
                  background: i === cursor ? 'rgba(242,101,34,.16)' : 'transparent',
                  border: 'none', cursor: 'pointer', color: 'inherit', fontSize: 14,
                }}
              >
                <span style={{ fontWeight: 500 }}>{a.label}</span>
                <span style={{ fontSize: 11, color: 'var(--placeholder, #8ea2c9)', whiteSpace: 'nowrap' }}>
                  {titulo(a.slug)}
                  {i === cursor && <CornerDownLeft size={11} style={{ marginLeft: 7, verticalAlign: -1 }} />}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
