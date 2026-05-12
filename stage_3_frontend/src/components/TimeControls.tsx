import { ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { formatHour, formatRuDate } from "../lib/normalizeTimeline";
import type { TimelineData } from "../lib/types";

interface TimeControlsProps {
  timeline: TimelineData;
  dayIndex: number;
  hour: number;
  isPlaying: boolean;
  onChangeDay: (idx: number) => void;
  onChangeHour: (h: number) => void;
  onTogglePlay: () => void;
  onPrevHour: () => void;
  onNextHour: () => void;
}

export function TimeControls({
  timeline,
  dayIndex,
  hour,
  isPlaying,
  onChangeDay,
  onChangeHour,
  onTogglePlay,
  onPrevHour,
  onNextHour,
}: TimeControlsProps) {
  const day = timeline.days[dayIndex];
  const hours = day?.hours.map((h) => h.hour) ?? [];
  const minHour = hours[0] ?? 7;
  const maxHour = hours[hours.length - 1] ?? 22;

  return (
    <div className="card p-4 lg:p-5 flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-graphite-400 font-semibold">
            Текущий момент
          </div>
          <div className="flex items-baseline gap-3 mt-0.5">
            <div className="text-2xl font-semibold text-graphite-900">
              {formatRuDate(day?.date)}
            </div>
            <div className="text-graphite-400">·</div>
            <div className="text-2xl font-semibold text-brand-orange">
              {formatHour(hour)}
            </div>
            {day?.label && (
              <div className="text-sm text-graphite-500 ml-2">
                {day.label}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn-icon"
            onClick={onPrevHour}
            aria-label="Предыдущий час"
            title="Предыдущий час"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
          <button
            type="button"
            onClick={onTogglePlay}
            className={`btn-primary px-5 py-2.5 ${
              isPlaying ? "bg-graphite-800 hover:bg-graphite-900" : ""
            }`}
            aria-label={isPlaying ? "Пауза" : "Старт"}
          >
            {isPlaying ? (
              <>
                <Pause className="h-4 w-4" />
                Пауза
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Старт
              </>
            )}
          </button>
          <button
            type="button"
            className="btn-icon"
            onClick={onNextHour}
            aria-label="Следующий час"
            title="Следующий час"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {timeline.days.map((d, idx) => {
          const active = idx === dayIndex;
          return (
            <button
              type="button"
              key={d.date}
              onClick={() => onChangeDay(idx)}
              className={`chip-tab ${
                active
                  ? "bg-brand-forest text-white border-brand-forest shadow-sm"
                  : "bg-white text-graphite-700 border-graphite-200 hover:bg-graphite-50"
              }`}
            >
              <span className="text-[11px] mr-2 opacity-80">{d.label}</span>
              <span className="font-semibold">{formatRuDate(d.date)}</span>
            </button>
          );
        })}
      </div>

      <div>
        <input
          type="range"
          min={minHour}
          max={maxHour}
          step={1}
          value={hour}
          onChange={(e) => onChangeHour(parseInt(e.target.value, 10))}
          className="w-full accent-brand-orange"
          aria-label="Час"
        />
        <div className="flex justify-between text-[10px] text-graphite-400 mt-1 select-none">
          {hours.map((h) => (
            <span
              key={h}
              className={`tabular-nums ${
                h === hour ? "text-brand-orange font-semibold" : ""
              }`}
            >
              {formatHour(h).slice(0, 2)}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
