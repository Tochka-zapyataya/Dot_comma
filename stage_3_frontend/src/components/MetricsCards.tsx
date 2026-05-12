import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock3,
  Layers,
  ShieldCheck,
} from "lucide-react";
import type { ValidationReport } from "../lib/types";

interface MetricsCardsProps {
  validation: ValidationReport;
}

function firstDefinedNumber(
  x: Record<string, unknown>,
  keys: string[],
): number | undefined {
  for (const k of keys) {
    const v = x[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
    if (typeof v === "string" && v.trim() !== "") {
      const n = Number(v);
      if (Number.isFinite(n)) return n;
    }
  }
  return undefined;
}

/** Часы и слоты: несколько имён ключей (stage_2, моки, возможные camelCase). */
function totalWorkHours(m: ValidationReport["metrics"]): number | undefined {
  const x = m as Record<string, unknown>;
  return firstDefinedNumber(x, [
    "total_work_hours",
    "total_hours",
    "totalHours",
    "total_workHours",
  ]);
}

function overstaffedOkSlots(
  m: ValidationReport["metrics"],
): number | undefined {
  const x = m as Record<string, unknown>;
  return firstDefinedNumber(x, [
    "overstaffed_ok_slots",
    "overstaffed_slots",
    "overstaffedOkSlots",
    "overstaffedSlots",
  ]);
}

export function MetricsCards({ validation }: MetricsCardsProps) {
  const m = validation.metrics ?? {};
  const isValid = validation.is_valid;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <Card
        icon={<ShieldCheck className="h-4 w-4" />}
        label="Расписание"
        value={isValid ? "Валидно" : "Невалидно"}
        tone={isValid ? "green" : "orangeDeep"}
        big
      />
      <Card
        icon={<Layers className="h-4 w-4" />}
        label="Всего смен"
        value={fmt(m.total_shifts)}
        tone="neutral"
      />
      <Card
        icon={<Clock3 className="h-4 w-4" />}
        label="Рабочих часов"
        value={fmt(totalWorkHours(m))}
        tone="neutral"
      />
      <Card
        icon={<CheckCircle2 className="h-4 w-4" />}
        label="Точное покрытие"
        value={fmt(m.exact_coverage_slots)}
        tone="green"
      />
      <Card
        icon={<Activity className="h-4 w-4" />}
        label="Допустимый запас"
        value={fmt(overstaffedOkSlots(m))}
        tone="orange"
      />
      <Card
        icon={<AlertCircle className="h-4 w-4" />}
        label="Нарушения"
        value={fmt(
          (Number(m.understaffed_slots ?? 0) +
            Number(m.too_much_overstaffed_slots ?? 0)) ||
            0,
        )}
        tone={
          (Number(m.understaffed_slots ?? 0) +
            Number(m.too_much_overstaffed_slots ?? 0)) >
          0
            ? "orangeDeep"
            : "green"
        }
      />
    </div>
  );
}

function fmt(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    return new Intl.NumberFormat("ru-RU").format(v);
  }
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    if (Number.isFinite(n)) return new Intl.NumberFormat("ru-RU").format(n);
  }
  return String(v);
}

function Card({
  icon,
  label,
  value,
  tone,
  big = false,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone: "green" | "orange" | "orangeDeep" | "neutral";
  big?: boolean;
}) {
  const cls =
    tone === "green"
      ? "border-brand-forest/30 bg-brand-forest-soft"
      : tone === "orange"
        ? "border-brand-orange/40 bg-brand-orange-soft"
        : tone === "orangeDeep"
          ? "border-brand-orange-deep bg-brand-orange text-white"
          : "border-graphite-100 bg-base-card";
  const iconCls =
    tone === "green"
      ? "bg-brand-forest text-white"
      : tone === "orange"
        ? "bg-brand-orange text-white"
        : tone === "orangeDeep"
          ? "bg-white/25 text-white"
          : "bg-graphite-100 text-graphite-700";
  const labelCls =
    tone === "orangeDeep"
      ? "text-white/90"
      : tone === "green"
        ? "text-brand-forest"
        : tone === "orange"
          ? "text-brand-orange-deep"
          : "text-graphite-500";
  const valueCls = tone === "orangeDeep" ? "text-white" : "text-graphite-900";
  return (
    <div
      className={`relative rounded-2xl border p-4 min-w-0 flex flex-col justify-between min-h-[110px] ${cls}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div
          className={`text-[11px] uppercase tracking-wide font-semibold leading-tight ${labelCls}`}
        >
          {label}
        </div>
        <span
          className={`shrink-0 inline-flex h-7 w-7 items-center justify-center rounded-lg ${iconCls}`}
        >
          {icon}
        </span>
      </div>
      <div
        className={`mt-3 ${
          big ? "text-2xl" : "text-3xl"
        } font-extrabold leading-none tabular-nums truncate ${valueCls}`}
        title={value}
      >
        {value}
      </div>
    </div>
  );
}
