import { describe, it, expect } from 'vitest';
import {
  slugify,
  capitalize,
  capitalizeFirst,
  truncate,
  removeAccents,
  normalize,
  removeSpaces,
  cleanSpaces,
  camelToSnake,
  snakeToCamel,
  toKebabCase,
  isNumeric,
  isEmpty,
  repeat,
  reverse,
  countOccurrences,
  extractNumbers,
  extractLetters,
  maskDocument,
  maskEmail,
  maskPhone,
} from '../string';

describe('String Utils', () => {
  describe('slugify', () => {
    it('converte texto simples para slug', () => {
      expect(slugify('Hello World')).toBe('hello-world');
    });

    it('remove acentos', () => {
      expect(slugify('São Paulo')).toBe('sao-paulo');
    });

    it('converte para minúsculas', () => {
      expect(slugify('HELLO WORLD')).toBe('hello-world');
    });

    it('remove caracteres especiais', () => {
      expect(slugify('Hello @#$% World!')).toBe('hello-world');
    });

    it('remove espaços extras', () => {
      expect(slugify('  Hello   World  ')).toBe('hello-world');
    });

    it('remove hífens duplicados', () => {
      expect(slugify('Hello--World')).toBe('hello-world');
    });

    it('retorna string vazia para input vazio', () => {
      expect(slugify('')).toBe('');
    });

    it('retorna string vazia para null', () => {
      expect(slugify(null as any)).toBe('');
    });
  });

  describe('capitalize', () => {
    it('capitaliza cada palavra', () => {
      expect(capitalize('hello world')).toBe('Hello World');
    });

    it('converte restante para minúsculas', () => {
      expect(capitalize('HELLO WORLD')).toBe('Hello World');
    });

    it('capitaliza nome completo', () => {
      expect(capitalize('joão da silva')).toBe('João Da Silva');
    });

    it('lida com palavras já capitalizadas', () => {
      expect(capitalize('Hello World')).toBe('Hello World');
    });

    it('retorna string vazia para input vazio', () => {
      expect(capitalize('')).toBe('');
    });

    it('lida com espaços múltiplos gerando palavras vazias', () => {
      expect(capitalize('  hello  world  ')).toBe('  Hello  World  ');
    });
  });

  describe('capitalizeFirst', () => {
    it('capitaliza apenas primeira letra', () => {
      expect(capitalizeFirst('hello world')).toBe('Hello world');
    });

    it('converte restante para minúsculas', () => {
      expect(capitalizeFirst('HELLO WORLD')).toBe('Hello world');
    });

    it('retorna string vazia para input vazio', () => {
      expect(capitalizeFirst('')).toBe('');
    });

    it('lida com uma letra', () => {
      expect(capitalizeFirst('h')).toBe('H');
    });
  });

  describe('truncate', () => {
    it('trunca texto maior que o limite', () => {
      expect(truncate('Hello World', 5)).toBe('Hello...');
    });

    it('não trunca texto menor que o limite', () => {
      expect(truncate('Hello', 10)).toBe('Hello');
    });

    it('não trunca texto igual ao limite', () => {
      expect(truncate('Hello', 5)).toBe('Hello');
    });

    it('retorna reticências para limite zero', () => {
      expect(truncate('Hello', 0)).toBe('...');
    });

    it('retorna string vazia para input vazio', () => {
      expect(truncate('', 10)).toBe('');
    });
  });

  describe('removeAccents', () => {
    it('remove acentos agudos', () => {
      expect(removeAccents('áéíóú')).toBe('aeiou');
    });

    it('remove acentos circunflexos', () => {
      expect(removeAccents('âêîôû')).toBe('aeiou');
    });

    it('remove til', () => {
      expect(removeAccents('ãõ')).toBe('ao');
    });

    it('remove cedilha', () => {
      expect(removeAccents('ç')).toBe('c');
    });

    it('não altera texto sem acentos', () => {
      expect(removeAccents('hello')).toBe('hello');
    });

    it('retorna string vazia para input vazio', () => {
      expect(removeAccents('')).toBe('');
    });
  });

  describe('normalize', () => {
    it('remove acentos e converte para minúsculas', () => {
      expect(normalize('SÃO PAULO')).toBe('sao paulo');
    });

    it('remove espaços extras', () => {
      expect(normalize('  Hello   World  ')).toBe('hello world');
    });

    it('retorna string vazia para input vazio', () => {
      expect(normalize('')).toBe('');
    });
  });

  describe('removeSpaces', () => {
    it('remove todos os espaços', () => {
      expect(removeSpaces('Hello World')).toBe('HelloWorld');
    });

    it('remove espaços múltiplos', () => {
      expect(removeSpaces('H  e  l  l  o')).toBe('Hello');
    });

    it('retorna string vazia para input vazio', () => {
      expect(removeSpaces('')).toBe('');
    });
  });

  describe('cleanSpaces', () => {
    it('remove espaços do início e fim', () => {
      expect(cleanSpaces('  Hello World  ')).toBe('Hello World');
    });

    it('remove espaços duplicados do meio', () => {
      expect(cleanSpaces('Hello   World')).toBe('Hello World');
    });

    it('retorna string vazia para input vazio', () => {
      expect(cleanSpaces('')).toBe('');
    });
  });

  describe('camelToSnake', () => {
    it('converte camelCase para snake_case', () => {
      expect(camelToSnake('helloWorld')).toBe('hello_world');
    });

    it('converte com múltiplas palavras', () => {
      expect(camelToSnake('helloWorldFooBar')).toBe('hello_world_foo_bar');
    });

    it('converte com letras maiúsculas consecutivas', () => {
      // A função atual insere underscore entre cada letra maiúscula
      expect(camelToSnake('helloHTTPWorld')).toBe('hello_h_t_t_p_world');
    });

    it('mantém já em snake_case', () => {
      expect(camelToSnake('hello_world')).toBe('hello_world');
    });

    it('retorna string vazia para input vazio', () => {
      expect(camelToSnake('')).toBe('');
    });
  });

  describe('snakeToCamel', () => {
    it('converte snake_case para camelCase', () => {
      expect(snakeToCamel('hello_world')).toBe('helloWorld');
    });

    it('converte com múltiplas palavras', () => {
      expect(snakeToCamel('hello_world_foo_bar')).toBe('helloWorldFooBar');
    });

    it('mantém já em camelCase', () => {
      expect(snakeToCamel('helloWorld')).toBe('helloWorld');
    });

    it('retorna string vazia para input vazio', () => {
      expect(snakeToCamel('')).toBe('');
    });
  });

  describe('toKebabCase', () => {
    it('converte camelCase para kebab-case', () => {
      expect(toKebabCase('helloWorld')).toBe('hello-world');
    });

    it('converte snake_case para kebab-case', () => {
      expect(toKebabCase('hello_world')).toBe('hello-world');
    });

    it('converte com múltiplas palavras', () => {
      expect(toKebabCase('helloWorldFooBar')).toBe('hello-world-foo-bar');
    });

    it('retorna string vazia para input vazio', () => {
      expect(toKebabCase('')).toBe('');
    });
  });

  describe('isNumeric', () => {
    it('retorna true para string numérica', () => {
      expect(isNumeric('12345')).toBe(true);
    });

    it('retorna false para string com letras', () => {
      expect(isNumeric('123abc')).toBe(false);
    });

    it('retorna false para string vazia', () => {
      expect(isNumeric('')).toBe(false);
    });

    it('retorna false para string com espaços', () => {
      expect(isNumeric('123 456')).toBe(false);
    });

    it('retorna false para null', () => {
      expect(isNumeric(null as any)).toBe(false);
    });
  });

  describe('isEmpty', () => {
    it('retorna true para string vazia', () => {
      expect(isEmpty('')).toBe(true);
    });

    it('retorna true para string com apenas espaços', () => {
      expect(isEmpty('   ')).toBe(true);
    });

    it('retorna false para string com conteúdo', () => {
      expect(isEmpty('Hello')).toBe(false);
    });

    it('retorna false para string com espaços e conteúdo', () => {
      expect(isEmpty('  Hello  ')).toBe(false);
    });

    it('retorna true para null', () => {
      expect(isEmpty(null as any)).toBe(true);
    });
  });

  describe('repeat', () => {
    it('repete string N vezes', () => {
      expect(repeat('ab', 3)).toBe('ababab');
    });

    it('repete uma vez', () => {
      expect(repeat('ab', 1)).toBe('ab');
    });

    it('retorna vazio para zero repetições', () => {
      expect(repeat('ab', 0)).toBe('');
    });

    it('retorna vazio para string vazia', () => {
      expect(repeat('', 5)).toBe('');
    });

    it('retorna vazio para repetições negativas', () => {
      expect(repeat('ab', -1)).toBe('');
    });
  });

  describe('reverse', () => {
    it('inverte string', () => {
      expect(reverse('hello')).toBe('olleh');
    });

    it('inverte string com espaços', () => {
      expect(reverse('hello world')).toBe('dlrow olleh');
    });

    it('retorna vazio para string vazia', () => {
      expect(reverse('')).toBe('');
    });

    it('inverte uma letra', () => {
      expect(reverse('a')).toBe('a');
    });
  });

  describe('countOccurrences', () => {
    it('conta ocorrências de substring', () => {
      expect(countOccurrences('hello hello world', 'hello')).toBe(2);
    });

    it('retorna zero quando não encontra', () => {
      expect(countOccurrences('hello world', 'foo')).toBe(0);
    });

    it('conta caracteres', () => {
      expect(countOccurrences('hello', 'l')).toBe(2);
    });

    it('retorna zero para string vazia', () => {
      expect(countOccurrences('', 'hello')).toBe(0);
    });

    it('retorna zero para search vazio', () => {
      expect(countOccurrences('hello', '')).toBe(0);
    });
  });

  describe('extractNumbers', () => {
    it('extrai apenas números', () => {
      expect(extractNumbers('abc123def456')).toBe('123456');
    });

    it('retorna string vazia quando não há números', () => {
      expect(extractNumbers('abcdef')).toBe('');
    });

    it('retorna todos os números', () => {
      expect(extractNumbers('123456')).toBe('123456');
    });

    it('retorna vazio para string vazia', () => {
      expect(extractNumbers('')).toBe('');
    });
  });

  describe('extractLetters', () => {
    it('extrai apenas letras', () => {
      expect(extractLetters('abc123def456')).toBe('abcdef');
    });

    it('retorna string vazia quando não há letras', () => {
      expect(extractLetters('123456')).toBe('');
    });

    it('ignora espaços e caracteres especiais', () => {
      expect(extractLetters('a b-c!d@e#f')).toBe('abcdef');
    });

    it('retorna vazio para string vazia', () => {
      expect(extractLetters('')).toBe('');
    });
  });

  describe('maskDocument', () => {
    it('mascara CPF', () => {
      expect(maskDocument('12345678901')).toBe('***.456.789-**');
    });

    it('mascara CNPJ', () => {
      expect(maskDocument('11222333000181')).toBe('**.222.333/0001-**');
    });

    it('remove caracteres não numéricos antes de mascarar', () => {
      expect(maskDocument('123.456.789-01')).toBe('***.456.789-**');
    });

    it('retorna documento limpo se tamanho diferente', () => {
      expect(maskDocument('12345')).toBe('12345');
    });

    it('retorna vazio para string vazia', () => {
      expect(maskDocument('')).toBe('');
    });
  });

  describe('maskEmail', () => {
    it('mascara email', () => {
      expect(maskEmail('joao.silva@gmail.com')).toBe('jo***@gmail.com');
    });

    it('mascara email curto', () => {
      expect(maskEmail('ab@gmail.com')).toBe('a***@gmail.com');
    });

    it('retorna email original se não contiver @', () => {
      expect(maskEmail('emailinvalido')).toBe('emailinvalido');
    });

    it('mascara email com subdomínio', () => {
      expect(maskEmail('joao.silva@empresa.com.br')).toBe('jo***@empresa.com.br');
    });

    it('mascara email com local part de 1 caractere', () => {
      expect(maskEmail('a@gmail.com')).toBe('a***@gmail.com');
    });

    it('retorna vazio para string vazia', () => {
      expect(maskEmail('')).toBe('');
    });

    it('retorna string sem @ inalterada', () => {
      expect(maskEmail('noemail')).toBe('noemail');
    });

    it('mascara email com local part vazio (usa * como fallback)', () => {
      expect(maskEmail('@gmail.com')).toBe('****@gmail.com');
    });

    it('retorna null/undefined como está para entrada falsy', () => {
      expect(maskEmail(null as any)).toBe(null);
    });
  });

  describe('maskPhone', () => {
    it('mascara celular', () => {
      expect(maskPhone('11987654321')).toBe('(11) *****-4321');
    });

    it('mascara telefone fixo', () => {
      expect(maskPhone('1134567890')).toBe('(11) ****-7890');
    });

    it('remove formatação antes de mascarar', () => {
      expect(maskPhone('(11) 98765-4321')).toBe('(11) *****-4321');
    });

    it('retorna limpo se tamanho inválido', () => {
      expect(maskPhone('12345')).toBe('12345');
    });

    it('retorna limpo para telefone com 7 dígitos', () => {
      expect(maskPhone('1234567')).toBe('1234567');
    });
  });
});
