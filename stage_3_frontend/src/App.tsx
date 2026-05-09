import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Hero } from "./components/Hero";
import { LogoMark } from "./components/LogoMark";
import { TimeControls } from "./components/TimeControls";
import { RestaurantMap } from "./components/RestaurantMap";
import { CurrentHourSummary } from "./components/CurrentHourSummary";
import { MetricsCards } from "./components/MetricsCards";
import { CoverageHeatmap } from "./components/CoverageHeatmap";
import { Legend } from "./components/Legend";
import { DownloadPanel } from "./components/DownloadPanel";
import { EmployeeDetailsPanel } from "./components/EmployeeDetailsPanel";
import { EmptyState } from "./components/EmptyState";
import { loadData, type DataBundle } from "./lib/loadData";
import {
  availableHours,
  findHour,
} from "./lib/normalizeTimeline";
import type { EmployeeAtSlot, StationKey } from "./lib/types";

type Phase = "hero" | "main" | "empty";

export default function App() {
  const [phase, setPhase] = useState<Phase>("hero");
  const [data, setData] = useState<DataBundle | null>(null);
  const [loadError, setLoadError] = useState(false);

  const [dayIndex, setDayIndex] = useState(0);
  const [hour, setHour] = useState(7);
  const [selectedStation, setSelectedStation] =
    useState<StationKey | "ALL">("ALL");
  const [isPlaying, setIsPlaying] = useState(false);
  const [selectedEmployee, setSelectedEmployee] =
    useState<EmployeeAtSlot | null>(null);

  const intervalRef = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadData()
      .then((d) => {
        if (cancelled) return;
        setData(d);
        const firstDay = d.timeline.days[0];
        const hours = availableHours(firstDay);
        if (hours.length > 0) setHour(hours[0]);
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const day = data?.timeline.days[dayIndex];
  const hourSlot = useMemo(
    () => (data ? findHour(data.timeline, dayIndex, hour) : null),
    [data, dayIndex, hour],
  );
  const dayHours = availableHours(day);
  const minHour = dayHours[0] ?? 7;
  const maxHour = dayHours[dayHours.length - 1] ?? 22;

  useEffect(() => {
    setHour((h) => {
      if (dayHours.length === 0) return h;
      if (h < minHour) return minHour;
      if (h > maxHour) return maxHour;
      return h;
    });
  }, [dayIndex, dayHours.length, minHour, maxHour]);

  const stopPlay = useCallback(() => {
    if (intervalRef.current) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  const togglePlay = useCallback(() => {
    setIsPlaying((p) => !p);
  }, []);

  useEffect(() => {
    if (!isPlaying) {
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    intervalRef.current = window.setInterval(() => {
      setHour((current) => {
        if (current >= maxHour) {
          stopPlay();
          return current;
        }
        return current + 1;
      });
    }, 900);
    return () => {
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isPlaying, maxHour, stopPlay]);

  const goPrev = useCallback(() => {
    stopPlay();
    setHour((h) => Math.max(minHour, h - 1));
  }, [minHour, stopPlay]);

  const goNext = useCallback(() => {
    stopPlay();
    setHour((h) => Math.min(maxHour, h + 1));
  }, [maxHour, stopPlay]);

  const showEmpty =
    !!data && data.validation && data.validation.is_valid === false && !data.isMock;

  if (loadError && !data) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6">
        <div className="card max-w-md p-6 text-center">
          <div className="text-graphite-900 font-semibold mb-2">
            Не удалось загрузить данные
          </div>
          <div className="text-graphite-500 text-sm">
            Попробуйте обновить страницу.
          </div>
        </div>
      </div>
    );
  }

  if (phase === "hero" || !data) {
    return (
      <Hero
        onStart={() => {
          if (showEmpty) setPhase("empty");
          else setPhase("main");
        }}
      />
    );
  }

  if (showEmpty) {
    return <EmptyState onReset={() => setPhase("hero")} />;
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 backdrop-blur bg-white/85 border-b border-graphite-100">
        <div className="max-w-[1400px] mx-auto px-5 py-3 flex items-center justify-between gap-4">
          <button
            type="button"
            onClick={() => setPhase("hero")}
            className="flex items-center gap-3 group"
          >
            <LogoMark
              size={36}
              className="group-hover:scale-105 transition"
            />
            <div className="text-left leading-tight">
              <div className="font-extrabold tracking-tight text-graphite-900 text-base">
                ТОЧКА ЗАПЯТАЯ
              </div>
              <div className="text-[11px] text-graphite-500 -mt-0.5">
                Симулятор расписания смен
              </div>
            </div>
          </button>
          <div className="flex items-center gap-2">
            {data.validation.is_valid ? (
              <span className="pill bg-brand-forest text-white border border-brand-forest">
                <span className="h-1.5 w-1.5 rounded-full bg-brand-orange" />
                Расписание валидно
              </span>
            ) : (
              <span className="pill bg-brand-orange text-white border border-brand-orange-deep">
                Расписание невалидно
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1400px] mx-auto px-5 py-5 space-y-5">
        <TimeControls
          timeline={data.timeline}
          dayIndex={dayIndex}
          hour={hour}
          isPlaying={isPlaying}
          onChangeDay={(idx) => {
            stopPlay();
            setDayIndex(idx);
          }}
          onChangeHour={(h) => {
            stopPlay();
            setHour(h);
          }}
          onTogglePlay={togglePlay}
          onPrevHour={goPrev}
          onNextHour={goNext}
        />

        <AnimatePresence mode="wait">
          <motion.div
            key={`${dayIndex}-${hour}-${selectedStation}`}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.18 }}
          >
            <RestaurantMap
              hour={hourSlot}
              selectedStation={selectedStation}
              onSelectStation={(s) => setSelectedStation(s)}
              onEmployeeClick={(e) => setSelectedEmployee(e)}
              highlightedEmployeeId={
                selectedEmployee?.employee_id ?? null
              }
            />
          </motion.div>
        </AnimatePresence>

        <MetricsCards validation={data.validation} />

        <div className="grid grid-cols-12 gap-5">
          <div className="col-span-12 xl:col-span-8">
            <CurrentHourSummary
              hour={hourSlot}
              onEmployeeClick={(e) => setSelectedEmployee(e)}
            />
          </div>
          <div className="col-span-12 xl:col-span-4 space-y-4">
            <Legend />
            <DownloadPanel availability={data.fileAvailability} />
          </div>
        </div>

        <CoverageHeatmap
          day={day ?? null}
          selectedHour={hour}
          onSelectHour={(h) => {
            stopPlay();
            setHour(h);
          }}
        />

        <footer className="pt-2 pb-8 text-center text-xs text-graphite-400">
          Команда «Точка запятая» · Стек: React + TypeScript + OR-Tools CP-SAT
        </footer>
      </main>

      <EmployeeDetailsPanel
        employee={selectedEmployee}
        date={day?.date ?? ""}
        hour={hour}
        summary={data.employeeSummary}
        onClose={() => setSelectedEmployee(null)}
      />
    </div>
  );
}
