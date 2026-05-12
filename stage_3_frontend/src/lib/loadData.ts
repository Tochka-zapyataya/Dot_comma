import mockTimeline from "../data/mockTimeline.json";
import mockValidation from "../data/mockValidationReport.json";
import mockEmployeeSummary from "../data/mockEmployeeSummary.json";
import { buildEmployeeSummaryFromTimeline } from "./employee";
import { coerceTimelineInput, normalizeTimeline } from "./normalizeTimeline";
import { normalizeValidationReport } from "./normalizeValidation";
import { parseStaffLimitsCsv, type StaffLimitsMap } from "./staffLimits";
import type {
  EmployeeSummaryFile,
  TimelineData,
  ValidationReport,
} from "./types";

const PUBLIC_TIMELINE = "/data/timeline.json";
const PUBLIC_VALIDATION = "/data/validation_report.json";
const PUBLIC_EMPLOYEE_SUMMARY = "/data/employee_summary.json";
const PUBLIC_STAFF_LIMITS = "/data/staff_limits.csv";

export interface DataBundle {
  timeline: TimelineData;
  validation: ValidationReport;
  employeeSummary: EmployeeSummaryFile;
  /** Лимиты из staff_limits.csv (stage_2 / data_tech_and_point), если положить в public/data */
  staffLimits: StaffLimitsMap | null;
  fileAvailability: {
    schedule_xlsx: boolean;
    schedule_csv: boolean;
    validation_report: boolean;
    staff_limits: boolean;
  };
  isMock: boolean;
}

async function tryFetchJson<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    const ct = res.headers.get("content-type") ?? "";
    if (!ct.includes("application/json") && !ct.includes("text/json")) {
      const txt = await res.text();
      if (txt.trim().startsWith("<")) return null;
      try {
        return JSON.parse(txt) as T;
      } catch {
        return null;
      }
    }
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

async function tryHead(url: string): Promise<boolean> {
  try {
    const res = await fetch(url, { method: "HEAD", cache: "no-store" });
    if (!res.ok) return false;
    const ct = res.headers.get("content-type") ?? "";
    return !ct.includes("text/html");
  } catch {
    return false;
  }
}

async function tryFetchText(url: string): Promise<string | null> {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    const ct = res.headers.get("content-type") ?? "";
    if (ct.includes("text/html")) return null;
    const txt = await res.text();
    if (txt.trim().startsWith("<")) return null;
    return txt;
  } catch {
    return null;
  }
}

export async function loadData(): Promise<DataBundle> {
  const [
    rawTl,
    vr,
    es,
    slText,
    hasXlsx,
    hasCsv,
    hasVRFile,
    hasStaffLim,
  ] = await Promise.all([
    tryFetchJson<unknown>(PUBLIC_TIMELINE),
    tryFetchJson<ValidationReport>(PUBLIC_VALIDATION),
    tryFetchJson<EmployeeSummaryFile>(PUBLIC_EMPLOYEE_SUMMARY),
    tryFetchText(PUBLIC_STAFF_LIMITS),
    tryHead("/data/schedule.xlsx"),
    tryHead("/data/schedule.csv"),
    tryHead(PUBLIC_VALIDATION),
    tryHead(PUBLIC_STAFF_LIMITS),
  ]);

  const coerced = rawTl != null ? coerceTimelineInput(rawTl) : null;
  const hasTl = coerced != null && (coerced.days?.length ?? 0) > 0;
  const isMock = !hasTl;
  const baseTimeline = hasTl
    ? coerced!
    : (mockTimeline as unknown as TimelineData);
  const timeline = normalizeTimeline(baseTimeline);

  const validationRaw =
    vr ?? (mockValidation as unknown as ValidationReport);
  const validation = normalizeValidationReport(validationRaw);

  const employeeSummary: EmployeeSummaryFile =
    es ??
    (isMock
      ? (mockEmployeeSummary as unknown as EmployeeSummaryFile)
      : buildEmployeeSummaryFromTimeline(timeline));

  const staffLimitsParsed =
    slText != null ? parseStaffLimitsCsv(slText) : null;
  const staffLimits: StaffLimitsMap | null =
    staffLimitsParsed != null && Object.keys(staffLimitsParsed).length > 0
      ? staffLimitsParsed
      : null;

  return {
    timeline,
    validation,
    employeeSummary,
    staffLimits,
    fileAvailability: {
      schedule_xlsx: hasXlsx,
      schedule_csv: hasCsv,
      validation_report: hasVRFile,
      staff_limits: hasStaffLim,
    },
    isMock,
  };
}
