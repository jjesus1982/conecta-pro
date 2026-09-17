import { describe, it, expect } from 'vitest';
import { filtrar, normalizar, titulo, casaTermo, type Alvo } from '../BuscaTelas';

/**
 * A busca do topo. Origem: 17/09/2026 — o Jordan: «to super perdido no sistema, difícil de
 * achar as coisas». O campo existia e era um `<input>` sem código.
 */

const U: Alvo[] = [
  { slug: 'documentos', id: 'kits-assinaturas-pendentes', label: 'Central de assinaturas' },
  { slug: 'documentos', id: 'assinaturas-cobrar-lote', label: 'Cobrar quem não assinou' },
  { slug: 'crm', id: 'abrir-assinatura', label: 'Abrir assinatura' },
  { slug: 'operacional', id: 'g-diaristas', label: 'Diaristas' },
  { slug: 'departamento-pessoal', id: 'g-ponto', label: 'Ponto & Jornada' },
  { slug: 'gestao-de-pessoas', id: 'ponto-espelho', label: 'Ponto · Espelho' },
  { slug: 'rh', id: 'cct-ferias', label: 'CCT — Férias' },
];

describe('normalizar — acento não pode atrapalhar', () => {
  it('tira acento e pontuação', () => {
    expect(normalizar('CCT — Férias')).toBe('cct ferias');
    expect(normalizar('Ponto · Espelho')).toBe('ponto espelho');
  });
});

describe('filtrar — achar o que a pessoa procura', () => {
  it('acha sem digitar acento', () => {
    expect(filtrar(U, 'ferias').map((a) => a.id)).toContain('cct-ferias');
    expect(filtrar(U, 'diaria').map((a) => a.id)).toContain('g-diaristas');
  });

  it('exige TODAS as palavras — "cobrar assinou" não traz tudo que tem "assinou"', () => {
    const r = filtrar(U, 'cobrar assinou');
    expect(r).toHaveLength(1);
    expect(r[0].id).toBe('assinaturas-cobrar-lote');
  });

  it('nome exato vem primeiro', () => {
    expect(filtrar(U, 'abrir assinatura')[0].id).toBe('abrir-assinatura');
  });

  it('acha por módulo, não só pelo rótulo', () => {
    expect(filtrar(U, 'crm').map((a) => a.slug)).toContain('crm');
  });

  it('uma letra não dispara busca — a lista inteira não ajuda ninguém', () => {
    expect(filtrar(U, 'a')).toHaveLength(0);
    expect(filtrar(U, '')).toHaveLength(0);
  });

  it('termo sem resultado devolve vazio, não a lista toda', () => {
    expect(filtrar(U, 'xpto')).toHaveLength(0);
  });

  it('respeita o teto', () => {
    expect(filtrar(U, 'a a', 2).length).toBeLessThanOrEqual(2);
  });

  it('"assinatura" acha a Central — o caso que motivou tudo', () => {
    expect(filtrar(U, 'assinatura').map((a) => a.id)).toContain('kits-assinaturas-pendentes');
  });
});

describe('titulo — o módulo aparece legível ao lado', () => {
  it('usa o nome bonito quando existe', () => {
    expect(titulo('departamento-pessoal')).toBe('Departamento Pessoal');
    expect(titulo('rh')).toBe('Recursos Humanos');
  });
  it('e inventa um legível para slug desconhecido', () => {
    expect(titulo('minha-tela-nova')).toBe('Minha Tela Nova');
  });
});

describe('casaTermo — a mesma regra, usada pelo CommandPalette', () => {
  it('tolera acento e raiz, que `includes` cru não tolera', () => {
    expect(casaTermo('Diaristas', 'diaria')).toBe(true);
    expect(casaTermo('CCT — Férias', 'ferias')).toBe(true);
    expect('Diaristas'.toLowerCase().includes('diaria')).toBe(false);  // o que havia antes
  });

  it('exige todas as palavras', () => {
    expect(casaTermo('Cobrar quem não assinou', 'cobrar assinou')).toBe(true);
    expect(casaTermo('Central de assinaturas', 'cobrar assinou')).toBe(false);
  });

  it('termo curto não casa com tudo', () => {
    expect(casaTermo('Diaristas', 'a')).toBe(false);
    expect(casaTermo('Diaristas', '')).toBe(false);
  });
});
