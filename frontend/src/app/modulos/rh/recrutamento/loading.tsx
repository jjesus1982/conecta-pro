export default function RecrutamentoLoading() {
  return (
    <div className="p-6 space-y-6 animate-pulse">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-7 w-48 bg-[hsl(var(--muted))] rounded" />
          <div className="h-4 w-72 bg-[hsl(var(--muted))] rounded" />
        </div>
        <div className="h-10 w-32 bg-[hsl(var(--muted))] rounded-lg" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="p-4 rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))]">
            <div className="h-4 w-24 bg-[hsl(var(--muted))] rounded mb-3" />
            <div className="h-8 w-16 bg-[hsl(var(--muted))] rounded" />
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))]">
        <div className="p-4 border-b border-[hsl(var(--border))] flex gap-3">
          <div className="h-9 w-64 bg-[hsl(var(--muted))] rounded-lg" />
          <div className="h-9 w-28 bg-[hsl(var(--muted))] rounded-lg" />
        </div>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="p-4 border-b border-[hsl(var(--border))] last:border-0 flex items-center gap-4">
            <div className="h-4 w-8 bg-[hsl(var(--muted))] rounded" />
            <div className="h-4 flex-1 bg-[hsl(var(--muted))] rounded" />
            <div className="h-4 w-24 bg-[hsl(var(--muted))] rounded" />
            <div className="h-6 w-16 bg-[hsl(var(--muted))] rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}
