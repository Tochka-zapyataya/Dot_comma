import type { CoverageStatus } from "./types";

export function computeCoverageStatus(
  required: number,
  assigned: number,
): CoverageStatus {
  if (required <= 0 && assigned <= 0) return "no_data";
  const diff = assigned - required;
  if (assigned < required) return "understaffed";
  if (diff === 0) return "exact";
  if (diff <= 2) return "overstaffed_ok";
  return "overstaffed_bad";
}

export function statusLabel(status: CoverageStatus): string {
  switch (status) {
    case "exact":
      return "Покрытие выполнено";
    case "overstaffed_ok":
      return "Допустимый запас";
    case "understaffed":
      return "Недобор";
    case "overstaffed_bad":
      return "Перебор";
    case "no_data":
    default:
      return "Нет данных";
  }
}

export function statusToHex(status: CoverageStatus): string {
  switch (status) {
    case "exact":
      return "#0F3D2A";
    case "overstaffed_ok":
      return "#FF8B4D";
    case "understaffed":
    case "overstaffed_bad":
      return "#D9551A";
    case "no_data":
    default:
      return "#d6dade";
  }
}

export function statusBg(status: CoverageStatus): string {
  switch (status) {
    case "exact":
      return "bg-brand-forest-soft text-brand-forest border-brand-forest/30";
    case "overstaffed_ok":
      return "bg-brand-orange-soft text-brand-orange-deep border-brand-orange/40";
    case "understaffed":
    case "overstaffed_bad":
      return "bg-brand-orange text-white border-brand-orange-deep";
    case "no_data":
    default:
      return "bg-graphite-100 text-graphite-600 border-graphite-200";
  }
}

export function buildWarnings(
  required: number,
  assigned: number,
  status: CoverageStatus,
): string[] {
  const out: string[] = [];
  if (status === "no_data") {
    out.push("Нет данных");
    return out;
  }
  if (assigned === 0 && required > 0) {
    out.push("Нет сотрудников");
  }
  if (status === "understaffed") out.push("Недобор");
  if (status === "overstaffed_bad") out.push("Перебор > +2");
  return out;
}
