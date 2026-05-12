import type { ValidationReport } from "./types";

function isPlainRecord(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function coercibleNumber(v: unknown): number | undefined {
  if (v == null) return undefined;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

/** Подставить в `out` ключи с верхнего уровня отчёта, если в metrics пусто. */
function liftFromRoot(
  out: Record<string, unknown>,
  root: Record<string, unknown>,
  keys: readonly string[],
) {
  for (const k of keys) {
    if (out[k] == null && root[k] != null) out[k] = root[k];
  }
}

/**
 * stage_2 кладёт `total_hours` и `overstaffed_slots`; мок и старый UI ждут
 * `total_work_hours` и `overstaffed_ok_slots`. Приводим к единому виду.
 *
 * Дополнительно: подхватываем метрики с корня JSON (старые/урезанные ответы),
 * разворачиваем вложенный `metrics.metrics`, приводим строковые числа к числам.
 */
export function normalizeValidationReport(v: unknown): ValidationReport {
  if (!isPlainRecord(v)) return v as unknown as ValidationReport;

  const root = v;
  let metricsBlock: Record<string, unknown>;

  if (isPlainRecord(root.metrics)) {
    metricsBlock = { ...root.metrics };
  } else {
    const synth: Record<string, unknown> = {};
    liftFromRoot(synth, root, [
      "total_shifts",
      "total_hours",
      "total_work_hours",
      "total_required_hours",
      "exact_coverage_slots",
      "overstaffed_slots",
      "overstaffed_ok_slots",
      "understaffed_slots",
      "too_much_overstaffed_slots",
    ]);
    if (Object.keys(synth).length === 0) {
      return v as unknown as ValidationReport;
    }
    metricsBlock = synth;
  }

  let out: Record<string, unknown> = { ...metricsBlock };

  const nested = out.metrics;
  if (isPlainRecord(nested)) {
    const { metrics: _drop, ...rest } = out;
    out = { ...nested, ...rest };
  }

  liftFromRoot(out, root, [
    "total_shifts",
    "total_hours",
    "total_work_hours",
    "total_required_hours",
    "exact_coverage_slots",
    "overstaffed_slots",
    "overstaffed_ok_slots",
    "understaffed_slots",
    "too_much_overstaffed_slots",
  ]);

  const thN = coercibleNumber(out.total_hours);
  const twN = coercibleNumber(out.total_work_hours);
  const hours = twN ?? thN;
  if (hours != null) {
    out.total_hours = hours;
    out.total_work_hours = hours;
  }

  const osN = coercibleNumber(out.overstaffed_slots);
  const ookN = coercibleNumber(out.overstaffed_ok_slots);
  const over = ookN ?? osN;
  if (over != null) {
    out.overstaffed_slots = over;
    out.overstaffed_ok_slots = over;
  }

  return {
    ...root,
    metrics: out as ValidationReport["metrics"],
  } as unknown as ValidationReport;
}
