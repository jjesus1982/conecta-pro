'use client';

interface MesRefSelectorProps {
  value: string;
  onChange: (value: string) => void;
}

function generateMonthOptions(): string[] {
  const options: string[] = [];
  const now = new Date();
  for (let i = 0; i < 12; i++) {
    const date = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const y = date.getFullYear();
    options.push(`${m}.${y}`);
  }
  return options;
}

export function MesRefSelector({ value, onChange }: MesRefSelectorProps) {
  const options = generateMonthOptions();

  return (
    <div className="flex items-center gap-2">
      <label htmlFor="mes-ref-select" className="text-sm font-medium text-[hsl(var(--foreground))]">
        Mês/Ano:
      </label>
      <select
        id="mes-ref-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--card))] text-[hsl(var(--foreground))] px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
