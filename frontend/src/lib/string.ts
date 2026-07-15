/**
 * Funções utilitárias para manipulação de strings
 */

/**
 * Converte uma string para slug (URL amigável)
 * Remove acentos, converte para minúsculas, substitui espaços por hífens
 */
export const slugify = (text: string): string => {
  if (!text) return '';

  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '') // Remove acentos
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, '') // Remove caracteres especiais
    .replace(/\s+/g, '-') // Substitui espaços por hífens
    .replace(/-+/g, '-'); // Remove hífens duplicados
};

/**
 * Converte a primeira letra de cada palavra para maiúscula
 */
export const capitalize = (text: string): string => {
  if (!text) return '';

  return text
    .toLowerCase()
    .split(' ')
    .map((word) => {
      if (word.length === 0) return word;
      return word.charAt(0).toUpperCase() + word.slice(1);
    })
    .join(' ');
};

/**
 * Converte apenas a primeira letra da string para maiúscula
 */
export const capitalizeFirst = (text: string): string => {
  if (!text) return '';

  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
};

/**
 * Trunca uma string para um tamanho máximo
 * Adiciona reticências se truncar
 */
export const truncate = (text: string, maxLength: number): string => {
  if (!text) return '';
  if (text.length <= maxLength) return text;

  return text.slice(0, maxLength) + '...';
};

/**
 * Remove acentos de uma string
 */
export const removeAccents = (text: string): string => {
  if (!text) return '';

  return text.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
};

/**
 * Normaliza uma string (remove acentos, converte para minúsculas, remove espaços extras)
 */
export const normalize = (text: string): string => {
  if (!text) return '';

  return removeAccents(text)
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ');
};

/**
 * Remove todos os espaços de uma string
 */
export const removeSpaces = (text: string): string => {
  if (!text) return '';

  return text.replace(/\s/g, '');
};

/**
 * Remove espaços do início e fim e espaços duplicados do meio
 */
export const cleanSpaces = (text: string): string => {
  if (!text) return '';

  return text.trim().replace(/\s+/g, ' ');
};

/**
 * Converte camelCase para snake_case
 */
export const camelToSnake = (text: string): string => {
  if (!text) return '';

  return text
    .replace(/([A-Z])/g, '_$1')
    .toLowerCase()
    .replace(/^_/, '');
};

/**
 * Converte snake_case para camelCase
 */
export const snakeToCamel = (text: string): string => {
  if (!text) return '';

  return text.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
};

/**
 * Converte para kebab-case
 */
export const toKebabCase = (text: string): string => {
  if (!text) return '';

  return camelToSnake(text).replace(/_/g, '-');
};

/**
 * Verifica se uma string contém apenas números
 */
export const isNumeric = (text: string): boolean => {
  if (!text) return false;

  return /^\d+$/.test(text);
};

/**
 * Verifica se uma string é vazia ou contém apenas espaços
 */
export const isEmpty = (text: string): boolean => {
  return !text || text.trim().length === 0;
};

/**
 * Repete uma string N vezes
 */
export const repeat = (text: string, times: number): string => {
  if (!text || times <= 0) return '';

  return text.repeat(times);
};

/**
 * Inverte uma string
 */
export const reverse = (text: string): string => {
  if (!text) return '';

  return text.split('').reverse().join('');
};

/**
 * Conta ocorrências de uma substring
 */
export const countOccurrences = (text: string, search: string): number => {
  if (!text || !search) return 0;

  const matches = text.match(new RegExp(search, 'g'));
  return matches ? matches.length : 0;
};

/**
 * Extrai apenas os números de uma string
 */
export const extractNumbers = (text: string): string => {
  if (!text) return '';

  return text.replace(/\D/g, '');
};

/**
 * Extrai apenas as letras de uma string
 */
export const extractLetters = (text: string): string => {
  if (!text) return '';

  return text.replace(/[^a-zA-Z]/g, '');
};

/**
 * Formata um CPF/CNPJ já limpo para exibição mascarada
 * Ex: ***.456.789-** ou **.223.330/0001-**
 */
export const maskDocument = (document: string): string => {
  const cleaned = extractNumbers(document);

  if (cleaned.length === 11) {
    // CPF: ***.456.789-**
    return `***.${cleaned.slice(3, 6)}.${cleaned.slice(6, 9)}-**`;
  }

  if (cleaned.length === 14) {
    // CNPJ: **.223.330/0001-**
    return `**.${cleaned.slice(2, 5)}.${cleaned.slice(5, 8)}/${cleaned.slice(8, 12)}-**`;
  }

  return cleaned;
};

/**
 * Mascara um email para exibição parcial
 * Ex: j***@gmail.com
 */
export const maskEmail = (email: string): string => {
  if (!email || !email.includes('@')) return email;

  const parts = email.split('@');
  const localPart = parts[0] ?? '';
  const domain = parts[1] ?? '';

  if (localPart.length <= 2) {
    return `${localPart[0] ?? '*'}***@${domain}`;
  }

  const visible = localPart.slice(0, 2);
  return `${visible}***@${domain}`;
};

/**
 * Mascara um telefone para exibição parcial
 * Ex: (11) *****-4321
 */
export const maskPhone = (phone: string): string => {
  const cleaned = extractNumbers(phone);

  if (cleaned.length === 11) {
    // Celular: (11) *****-4321
    return `(${cleaned.slice(0, 2)}) *****-${cleaned.slice(7, 11)}`;
  }

  if (cleaned.length === 10) {
    // Fixo: (11) ****-7890
    return `(${cleaned.slice(0, 2)}) ****-${cleaned.slice(6, 10)}`;
  }

  return cleaned;
};

/**
 * Normaliza o `detail` de um erro de API para STRING exibível.
 * FastAPI/Pydantic 422 retorna detail = [{loc,msg,...}] (array de objetos) — passar
 * isso direto a toast/JSX quebra o React (#31 "object as child") e derruba a tela.
 */
export function msgFromDetail(detail: unknown): string | undefined {
  if (!detail) return undefined;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((e) => (typeof e === 'string' ? e : (e && typeof e === 'object' && 'msg' in e ? String((e as { msg: unknown }).msg) : '')))
      .filter(Boolean);
    return msgs.length ? msgs.join('; ') : undefined;
  }
  if (typeof detail === 'object' && detail !== null && 'msg' in detail) {
    return String((detail as { msg: unknown }).msg);
  }
  return undefined;
}
