export function Legend() {
  return (
    <div className="card px-4 py-3 flex flex-wrap items-center gap-4 text-xs">
      <span className="text-[11px] uppercase tracking-wide font-semibold text-graphite-400 mr-2">
        Легенда
      </span>
      <Item color="#0F3D2A" text="Покрытие ровно" />
      <Item color="#FF8B4D" text="Допустимый запас" />
      <Item color="#D9551A" text="Нарушение" />
      <Item color="#d6dade" text="Нет данных" />
    </div>
  );
}

function Item({ color, text }: { color: string; text: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-graphite-700">
      <span
        className="inline-block h-3 w-3 rounded-sm"
        style={{ background: color }}
      />
      {text}
    </span>
  );
}
