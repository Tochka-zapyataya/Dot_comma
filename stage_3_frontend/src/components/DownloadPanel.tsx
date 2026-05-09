import { Download, FileSpreadsheet, FileText, FileJson } from "lucide-react";

interface DownloadPanelProps {
  availability: {
    schedule_xlsx: boolean;
    schedule_csv: boolean;
    validation_report: boolean;
  };
}

export function DownloadPanel({ availability }: DownloadPanelProps) {
  const items = [
    {
      key: "xlsx",
      href: "/data/schedule.xlsx",
      label: "schedule.xlsx",
      sub: "Расписание · Excel",
      enabled: availability.schedule_xlsx,
      icon: <FileSpreadsheet className="h-4 w-4" />,
    },
    {
      key: "csv",
      href: "/data/schedule.csv",
      label: "schedule.csv",
      sub: "Расписание · CSV",
      enabled: availability.schedule_csv,
      icon: <FileText className="h-4 w-4" />,
    },
    {
      key: "json",
      href: "/data/validation_report.json",
      label: "validation_report.json",
      sub: "Отчёт валидации",
      enabled: availability.validation_report,
      icon: <FileJson className="h-4 w-4" />,
    },
  ];

  const anyEnabled = items.some((i) => i.enabled);
  if (!anyEnabled) return null;

  return (
    <div className="card p-4">
      <div className="flex items-center gap-2 mb-3">
        <Download className="h-4 w-4 text-graphite-500" />
        <span className="text-[11px] uppercase tracking-wide font-semibold text-graphite-500">
          Файлы
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
        {items
          .filter((i) => i.enabled)
          .map((i) => (
            <a
              key={i.key}
              href={i.href}
              download
              className="rounded-xl border border-graphite-200 bg-white hover:bg-graphite-50 transition px-3 py-2.5 flex items-center gap-3"
            >
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-brand-orange/15 text-brand-orange">
                {i.icon}
              </span>
              <span className="flex flex-col leading-tight">
                <span className="text-sm font-semibold text-graphite-900">
                  {i.label}
                </span>
                <span className="text-xs text-graphite-500">{i.sub}</span>
              </span>
            </a>
          ))}
      </div>
    </div>
  );
}
