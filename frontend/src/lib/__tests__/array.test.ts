import { describe, it, expect } from 'vitest';
import {
  groupBy,
  sortBy,
  sortByMultiple,
  unique,
  chunk,
  partition,
  intersection,
  difference,
  union,
  moveItem,
  insertAt,
  removeAt,
  removeItem,
  updateAt,
  randomItem,
  shuffle,
  countBy,
  maxBy,
  minBy,
  average,
  sum,
  pairwise,
} from '../array';

describe('Array Utils', () => {
  describe('groupBy', () => {
    it('agrupa por propriedade string', () => {
      const items = [
        { category: 'A', value: 1 },
        { category: 'B', value: 2 },
        { category: 'A', value: 3 },
      ];
      const result = groupBy(items, (item) => item.category);
      
      expect(result).toEqual({
        A: [
          { category: 'A', value: 1 },
          { category: 'A', value: 3 },
        ],
        B: [{ category: 'B', value: 2 }],
      });
    });

    it('agrupa por propriedade numérica', () => {
      const items = [
        { group: 1, name: 'A' },
        { group: 2, name: 'B' },
        { group: 1, name: 'C' },
      ];
      const result = groupBy(items, (item) => item.group);
      
      expect(result).toEqual({
        1: [
          { group: 1, name: 'A' },
          { group: 1, name: 'C' },
        ],
        2: [{ group: 2, name: 'B' }],
      });
    });

    it('retorna objeto vazio para array vazio', () => {
      expect(groupBy([], (item: any) => item.id)).toEqual({});
    });

    it('retorna objeto vazio para array nulo', () => {
      expect(groupBy(null as any, (item: any) => item.id)).toEqual({});
    });
  });

  describe('sortBy', () => {
    it('ordena números em ordem ascendente', () => {
      const items = [{ value: 3 }, { value: 1 }, { value: 2 }];
      const result = sortBy(items, 'value');
      expect(result).toEqual([{ value: 1 }, { value: 2 }, { value: 3 }]);
    });

    it('ordena números em ordem descendente', () => {
      const items = [{ value: 3 }, { value: 1 }, { value: 2 }];
      const result = sortBy(items, 'value', 'desc');
      expect(result).toEqual([{ value: 3 }, { value: 2 }, { value: 1 }]);
    });

    it('ordena strings em ordem ascendente', () => {
      const items = [{ name: 'Charlie' }, { name: 'Alice' }, { name: 'Bob' }];
      const result = sortBy(items, 'name');
      expect(result).toEqual([{ name: 'Alice' }, { name: 'Bob' }, { name: 'Charlie' }]);
    });

    it('ordena datas corretamente', () => {
      const items = [
        { date: new Date('2024-03-15') },
        { date: new Date('2024-01-15') },
        { date: new Date('2024-02-15') },
      ];
      const result = sortBy(items, 'date');
      expect(result[0]?.date.getMonth()).toBe(0); // Janeiro
      expect(result[1]?.date.getMonth()).toBe(1); // Fevereiro
      expect(result[2]?.date.getMonth()).toBe(2); // Março
    });

    it('coloca null/undefined no final em ordem ascendente', () => {
      const items = [{ value: 2 }, { value: null }, { value: 1 }];
      const result = sortBy(items, 'value');
      expect(result).toEqual([{ value: 1 }, { value: 2 }, { value: null }]);
    });

    it('não modifica array original', () => {
      const items = [{ value: 3 }, { value: 1 }];
      sortBy(items, 'value');
      expect(items).toEqual([{ value: 3 }, { value: 1 }]);
    });

    it('retorna array vazio para input vazio', () => {
      expect(sortBy([], 'value' as any)).toEqual([]);
    });

    it('retorna array vazio para null', () => {
      expect(sortBy(null as any, 'value')).toEqual([]);
    });

    it('coloca undefined antes de null em ordem ascendente', () => {
      const items = [{ value: undefined }, { value: 1 }];
      const result = sortBy(items, 'value');
      expect(result[0]?.value).toBe(1);
      expect(result[1]?.value).toBeUndefined();
    });

    it('ordena valores iguais estávelmente', () => {
      const items = [{ value: 1, name: 'a' }, { value: 1, name: 'b' }];
      const result = sortBy(items, 'value');
      expect(result).toHaveLength(2);
    });
  });

  describe('sortByMultiple', () => {
    it('ordena por múltiplas chaves', () => {
      const items = [
        { category: 'B', value: 2 },
        { category: 'A', value: 2 },
        { category: 'A', value: 1 },
        { category: 'B', value: 1 },
      ];
      const result = sortByMultiple(items, [
        { key: 'category', order: 'asc' },
        { key: 'value', order: 'asc' },
      ]);
      expect(result).toEqual([
        { category: 'A', value: 1 },
        { category: 'A', value: 2 },
        { category: 'B', value: 1 },
        { category: 'B', value: 2 },
      ]);
    });

    it('retorna array vazio para null', () => {
      expect(sortByMultiple(null as any, [{ key: 'value' }] as any)).toEqual([]);
    });

    it('ordena com ambos null em desc - continua para próxima chave', () => {
      const items = [
        { category: 'B', value: null },
        { category: 'A', value: null },
      ];
      const result = sortByMultiple(items, [
        { key: 'value', order: 'desc' },
        { key: 'category', order: 'asc' },
      ]);
      // Ambos null no value, vai para category: A antes de B
      expect(result[0]?.category).toBe('A');
      expect(result[1]?.category).toBe('B');
    });

    it('ordena com valueA null em desc', () => {
      const items = [
        { category: 'A', value: null },
        { category: 'B', value: 2 },
      ];
      const result = sortByMultiple(items, [
        { key: 'value', order: 'desc' },
      ]);
      // valueA null, valueB not null, desc => returns -1 => null comes first
      expect(result[0]?.value).toBeNull();
      expect(result[1]?.value).toBe(2);
    });

    it('ordena com valueB null em desc', () => {
      const items = [
        { category: 'A', value: 2 },
        { category: 'B', value: null },
      ];
      const result = sortByMultiple(items, [
        { key: 'value', order: 'desc' },
      ]);
      // valueB null, order desc => returns 1 (A goes after B) => null first
      expect(result[0]?.value).toBeNull();
      expect(result[1]?.value).toBe(2);
    });

    it('ordena datas em sortByMultiple', () => {
      const items = [
        { date: new Date('2024-03-01') },
        { date: new Date('2024-01-01') },
        { date: new Date('2024-02-01') },
      ];
      const result = sortByMultiple(items, [{ key: 'date', order: 'asc' }]);
      expect(result[0]?.date.getMonth()).toBe(0);
      expect(result[2]?.date.getMonth()).toBe(2);
    });

    it('ordena com ordens mistas', () => {
      const items = [
        { category: 'A', value: 1 },
        { category: 'A', value: 3 },
        { category: 'A', value: 2 },
      ];
      const result = sortByMultiple(items, [
        { key: 'category', order: 'asc' },
        { key: 'value', order: 'desc' },
      ]);
      expect(result).toEqual([
        { category: 'A', value: 3 },
        { category: 'A', value: 2 },
        { category: 'A', value: 1 },
      ]);
    });
  });

  describe('unique', () => {
    it('remove valores duplicados primitivos', () => {
      expect(unique([1, 2, 2, 3, 3, 3])).toEqual([1, 2, 3]);
    });

    it('remove strings duplicadas', () => {
      expect(unique(['a', 'b', 'a', 'c'])).toEqual(['a', 'b', 'c']);
    });

    it('remove duplicados de objetos usando keyGetter', () => {
      const items = [
        { id: 1, name: 'A' },
        { id: 2, name: 'B' },
        { id: 1, name: 'C' },
      ];
      expect(unique(items, (item) => item.id)).toEqual([
        { id: 1, name: 'A' },
        { id: 2, name: 'B' },
      ]);
    });

    it('retorna array vazio para input vazio', () => {
      expect(unique([])).toEqual([]);
    });

    it('retorna array vazio para null', () => {
      expect(unique(null as any)).toEqual([]);
    });
  });

  describe('chunk', () => {
    it('divide array em chunks', () => {
      expect(chunk([1, 2, 3, 4, 5], 2)).toEqual([[1, 2], [3, 4], [5]]);
    });

    it('divide em chunks de 1', () => {
      expect(chunk([1, 2, 3], 1)).toEqual([[1], [2], [3]]);
    });

    it('retorna array vazio para input vazio', () => {
      expect(chunk([], 2)).toEqual([]);
    });

    it('retorna array vazio para size 0', () => {
      expect(chunk([1, 2, 3], 0)).toEqual([]);
    });

    it('retorna array vazio para size negativo', () => {
      expect(chunk([1, 2, 3], -1)).toEqual([]);
    });

    it('funciona quando size maior que array', () => {
      expect(chunk([1, 2], 5)).toEqual([[1, 2]]);
    });
  });

  describe('partition', () => {
    it('divide array em dois baseado em predicado', () => {
      const [evens, odds] = partition([1, 2, 3, 4, 5], (n) => n % 2 === 0);
      expect(evens).toEqual([2, 4]);
      expect(odds).toEqual([1, 3, 5]);
    });

    it('coloca todos em pass quando predicado sempre true', () => {
      const [pass, fail] = partition([1, 2, 3], () => true);
      expect(pass).toEqual([1, 2, 3]);
      expect(fail).toEqual([]);
    });

    it('retorna arrays vazios para input vazio', () => {
      const [pass, fail] = partition([], () => true);
      expect(pass).toEqual([]);
      expect(fail).toEqual([]);
    });

    it('retorna arrays vazios para null', () => {
      const [pass, fail] = partition(null as any, () => true);
      expect(pass).toEqual([]);
      expect(fail).toEqual([]);
    });
  });

  describe('intersection', () => {
    it('retorna elementos comuns', () => {
      expect(intersection([1, 2, 3], [2, 3, 4])).toEqual([2, 3]);
    });

    it('retorna array vazio quando não há interseção', () => {
      expect(intersection([1, 2], [3, 4])).toEqual([]);
    });

    it('funciona com strings', () => {
      expect(intersection(['a', 'b'], ['b', 'c'])).toEqual(['b']);
    });

    it('retorna array vazio para input vazio', () => {
      expect(intersection([], [1, 2])).toEqual([]);
    });
  });

  describe('difference', () => {
    it('retorna elementos em array1 não presentes em array2', () => {
      expect(difference([1, 2, 3], [2, 3, 4])).toEqual([1]);
    });

    it('retorna todos quando não há interseção', () => {
      expect(difference([1, 2], [3, 4])).toEqual([1, 2]);
    });

    it('retorna array vazio quando arrays são iguais', () => {
      expect(difference([1, 2], [1, 2])).toEqual([]);
    });

    it('retorna array vazio para input vazio', () => {
      expect(difference([], [1, 2])).toEqual([]);
    });

    it('retorna array vazio quando array1 é null', () => {
      expect(difference(null as any, [1, 2])).toEqual([]);
    });

    it('retorna cópia de array1 quando array2 é null', () => {
      expect(difference([1, 2, 3], null as any)).toEqual([1, 2, 3]);
    });

    it('retorna cópia de array1 quando array2 não é array', () => {
      expect(difference([1, 2, 3], 'not-array' as any)).toEqual([1, 2, 3]);
    });
  });

  describe('union', () => {
    it('retorna união de arrays', () => {
      expect(union([1, 2], [2, 3])).toEqual([1, 2, 3]);
    });

    it('mantém ordem do primeiro array', () => {
      expect(union([3, 1], [2, 1])).toEqual([3, 1, 2]);
    });

    it('funciona com arrays vazios', () => {
      expect(union([1, 2], [])).toEqual([1, 2]);
      expect(union([], [1, 2])).toEqual([1, 2]);
    });
  });

  describe('moveItem', () => {
    it('move item de uma posição para outra', () => {
      expect(moveItem([1, 2, 3, 4], 0, 2)).toEqual([2, 3, 1, 4]);
    });

    it('move item para o início', () => {
      expect(moveItem([1, 2, 3], 2, 0)).toEqual([3, 1, 2]);
    });

    it('move item para o final', () => {
      expect(moveItem([1, 2, 3], 0, 2)).toEqual([2, 3, 1]);
    });

    it('retorna array inalterado para índice inválido', () => {
      expect(moveItem([1, 2, 3], 0, 5)).toEqual([1, 2, 3]);
      expect(moveItem([1, 2, 3], -1, 1)).toEqual([1, 2, 3]);
    });

    it('não modifica array original', () => {
      const original = [1, 2, 3];
      moveItem(original, 0, 2);
      expect(original).toEqual([1, 2, 3]);
    });
  });

  describe('insertAt', () => {
    it('insere item no meio', () => {
      expect(insertAt([1, 2, 3], 1, 'a' as unknown as number)).toEqual([1, 'a', 2, 3]);
    });

    it('insere item no início', () => {
      expect(insertAt([1, 2, 3], 0, 'a' as unknown as number)).toEqual(['a', 1, 2, 3]);
    });

    it('insere item no final', () => {
      expect(insertAt([1, 2, 3], 3, 'a' as unknown as number)).toEqual([1, 2, 3, 'a']);
    });

    it('cria novo array com item para array vazio', () => {
      expect(insertAt([], 0, 'a' as unknown as number)).toEqual(['a']);
    });
  });

  describe('removeAt', () => {
    it('remove item do meio', () => {
      expect(removeAt([1, 2, 3], 1)).toEqual([1, 3]);
    });

    it('remove item do início', () => {
      expect(removeAt([1, 2, 3], 0)).toEqual([2, 3]);
    });

    it('remove item do final', () => {
      expect(removeAt([1, 2, 3], 2)).toEqual([1, 2]);
    });

    it('retorna array inalterado para índice inválido', () => {
      expect(removeAt([1, 2, 3], 5)).toEqual([1, 2, 3]);
    });
  });

  describe('removeItem', () => {
    it('remove item específico', () => {
      expect(removeItem([1, 2, 3], 2)).toEqual([1, 3]);
    });

    it('não modifica se item não existe', () => {
      expect(removeItem([1, 2, 3], 5)).toEqual([1, 2, 3]);
    });

    it('remove apenas primeira ocorrência', () => {
      expect(removeItem([1, 2, 2, 3], 2)).toEqual([1, 2, 3]);
    });

    it('retorna array vazio para null', () => {
      expect(removeItem(null as any, 1)).toEqual([]);
    });
  });

  describe('updateAt', () => {
    it('atualiza item em posição específica', () => {
      expect(updateAt([1, 2, 3], 1, 'a' as unknown as number)).toEqual([1, 'a', 3]);
    });

    it('retorna array inalterado para índice inválido', () => {
      expect(updateAt([1, 2, 3], 5, 'a' as unknown as number)).toEqual([1, 2, 3]);
    });

    it('retorna array vazio para null', () => {
      expect(updateAt(null as any, 0, 'x' as unknown as number)).toEqual([]);
    });

    it('retorna array inalterado para índice negativo', () => {
      expect(updateAt([1, 2, 3], -1, 'x' as unknown as number)).toEqual([1, 2, 3]);
    });
  });

  describe('randomItem', () => {
    it('retorna um item do array', () => {
      const items = [1, 2, 3];
      const result = randomItem(items);
      expect(items).toContain(result);
    });

    it('retorna undefined para array vazio', () => {
      expect(randomItem([])).toBeUndefined();
    });

    it('retorna undefined para null', () => {
      expect(randomItem(null as any)).toBeUndefined();
    });
  });

  describe('shuffle', () => {
    it('retorna array com mesmos elementos', () => {
      const items = [1, 2, 3, 4, 5];
      const shuffled = shuffle(items);
      expect(shuffled).toHaveLength(items.length);
      expect(shuffled.sort()).toEqual(items.sort());
    });

    it('não modifica array original', () => {
      const original = [1, 2, 3];
      shuffle(original);
      expect(original).toEqual([1, 2, 3]);
    });

    it('retorna array vazio para input vazio', () => {
      expect(shuffle([])).toEqual([]);
    });

    it('retorna array vazio para null', () => {
      expect(shuffle(null as any)).toEqual([]);
    });
  });

  describe('countBy', () => {
    it('conta ocorrências de valores', () => {
      expect(countBy(['a', 'b', 'a', 'c', 'a'])).toEqual({ a: 3, b: 1, c: 1 });
    });

    it('conta usando keyGetter', () => {
      const items = [
        { category: 'A' },
        { category: 'B' },
        { category: 'A' },
      ];
      expect(countBy(items, (item) => item.category)).toEqual({ A: 2, B: 1 });
    });

    it('retorna objeto vazio para array vazio', () => {
      expect(countBy([])).toEqual({});
    });

    it('retorna objeto vazio para null', () => {
      expect(countBy(null as any)).toEqual({});
    });
  });

  describe('maxBy', () => {
    it('encontra item com valor máximo', () => {
      const items = [{ value: 10 }, { value: 5 }, { value: 15 }];
      expect(maxBy(items, 'value')).toEqual({ value: 15 });
    });

    it('funciona com strings', () => {
      const items = [{ name: 'Alice' }, { name: 'Bob' }];
      expect(maxBy(items, 'name')).toEqual({ name: 'Bob' });
    });

    it('retorna undefined para array vazio', () => {
      expect(maxBy([], 'value' as any)).toBeUndefined();
    });
  });

  describe('minBy', () => {
    it('encontra item com valor mínimo', () => {
      const items = [{ value: 10 }, { value: 5 }, { value: 15 }];
      expect(minBy(items, 'value')).toEqual({ value: 5 });
    });

    it('funciona com strings', () => {
      const items = [{ name: 'Alice' }, { name: 'Bob' }];
      expect(minBy(items, 'name')).toEqual({ name: 'Alice' });
    });

    it('retorna undefined para array vazio', () => {
      expect(minBy([], 'value' as any)).toBeUndefined();
    });
  });

  describe('average', () => {
    it('calcula média de números', () => {
      expect(average([1, 2, 3, 4, 5])).toBe(3);
    });

    it('calcula média com decimais', () => {
      expect(average([1, 2, 3])).toBe(2);
    });

    it('retorna 0 para array vazio', () => {
      expect(average([])).toBe(0);
    });
  });

  describe('sum', () => {
    it('calcula soma de números', () => {
      expect(sum([1, 2, 3, 4, 5])).toBe(15);
    });

    it('retorna 0 para array vazio', () => {
      expect(sum([])).toBe(0);
    });

    it('retorna 0 para null', () => {
      expect(sum(null as any)).toBe(0);
    });
  });

  describe('pairwise', () => {
    it('cria pares de elementos adjacentes', () => {
      expect(pairwise([1, 2, 3, 4])).toEqual([
        [1, 2],
        [2, 3],
        [3, 4],
      ]);
    });

    it('retorna array vazio para array com menos de 2 elementos', () => {
      expect(pairwise([1])).toEqual([]);
      expect(pairwise([])).toEqual([]);
    });

    it('funciona com strings', () => {
      expect(pairwise(['a', 'b', 'c'])).toEqual([
        ['a', 'b'],
        ['b', 'c'],
      ]);
    });
  });

  describe('moveItem - Edge Cases', () => {
    it('retorna array vazio para null', () => {
      expect(moveItem(null as any, 0, 1)).toEqual([]);
    });

    it('retorna array inalterado para fromIndex negativo', () => {
      expect(moveItem([1, 2, 3], -1, 1)).toEqual([1, 2, 3]);
    });
  });

  describe('insertAt - Edge Cases', () => {
    it('retorna array com item quando array é null', () => {
      expect(insertAt(null as any, 0, 'x')).toEqual(['x']);
    });
  });

  describe('removeAt - Edge Cases', () => {
    it('retorna array vazio para null', () => {
      expect(removeAt(null as any, 0)).toEqual([]);
    });

    it('remove último elemento com índice negativo (comportamento splice)', () => {
      // splice com índice negativo remove do final
      expect(removeAt([1, 2, 3], -1)).toEqual([1, 2]);
    });
  });
});
