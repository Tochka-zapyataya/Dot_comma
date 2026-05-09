import mockTimeline from "../data/mockTimeline.json";
import mockValidation from "../data/mockValidationReport.json";
import mockEmployeeSummary from "../data/mockEmployeeSummary.json";
import { buildEmployeeSummaryFromTimeline } from "./employee";
import { normalizeTimeline } from "./normalizeTimeline";
import type {
  EmployeeSummaryFile,
  TimelineData,
  ValidationReport,
} from "./types";

const PUBLIC_TIMELINE = "/data/timeline.json";
const PUBLIC_VALIDATION = "/data/validation_report.json";
const PUBLIC_EMPLOYEE_SUMMARY = "/data/employee_summary.json";

export interface DataBundle {
  timeline: TimelineData;
  validation: ValidationReport;
  employeeSummary: EmployeeSummaryFile;
  fileAvailability: {
    schedule_xlsx: boolean;
    schedule_csv: boolean;
    validation_report: boolean;
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

export async function loadData(): Promise<DataBundle> {
  const [tl, vr, es, hasXlsx, hasCsv, hasVRFile] = await Promise.all([
    tryFetchJson<TimelineData>(PUBLIC_TIMELINE),
    tryFetchJson<ValidationReport>(PUBLIC_VALIDATION),
    tryFetchJson<EmployeeSummaryFile>(PUBLIC_EMPLOYEE_SUMMARY),
    tryHead("/data/schedule.xlsx"),
    tryHead("/data/schedule.csv"),
    tryHead(PUBLIC_VALIDATION),
  ]);

  const isMock = tl == null;
  const rawTimeline = tl ?? (mockTimeline as unknown as TimelineData);
  const timeline = normalizeTimeline(rawTimeline);

  const validation =
    vr ?? (mockValidation as unknown as ValidationReport);

  const employeeSummary: EmployeeSummaryFile =
    es ??
    (isMock
      ? (mockEmployeeSummary as unknown as EmployeeSummaryFile)
      : buildEmployeeSummaryFromTimeline(timeline));

  return {
    timeline,
    validation,
    employeeSummary,
    fileAvailability: {
      schedule_xlsx: hasXlsx,
      schedule_csv: hasCsv,
      validation_report: hasVRFile,
    },
    isMock,
  };
}
