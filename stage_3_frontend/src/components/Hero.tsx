import { motion } from "framer-motion";
import { ArrowRight, ChefHat, Clock, Users } from "lucide-react";
import { LogoMark } from "./LogoMark";

interface HeroProps {
  onStart: () => void;
}

export function Hero({ onStart }: HeroProps) {
  return (
    <div className="min-h-screen flex flex-col">
      <BrandTopBar />

      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 py-6">
        <div className="max-w-[1180px] w-full space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="relative overflow-hidden rounded-[32px] bg-brand-forest shadow-forest"
          >
            <DecorArrows />
            <div className="relative grid lg:grid-cols-[1.1fr_0.9fr] gap-0">
              <div className="px-8 sm:px-12 lg:px-16 py-12 lg:py-16 text-white">
                <span className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-md bg-brand-orange text-white font-semibold text-sm tracking-wide">
                  <span className="h-1.5 w-1.5 rounded-full bg-white/85" />
                  Команда «Точка запятая»
                </span>
                <h1 className="mt-6 text-[40px] sm:text-5xl lg:text-[58px] font-extrabold leading-[1.05] tracking-tight">
                  Симулятор
                  <br />
                  расписания смен
                  <br />
                  <span className="text-brand-orange">для ресторана</span>
                </h1>
                <p className="mt-5 text-base sm:text-lg text-white/85 max-w-xl leading-relaxed">
                  Прогноз гостей → потребность по станциям → готовое
                  расписание. Смотрим, как сотрудники выходят и закрывают
                  смену — час за часом.
                </p>

                <div className="mt-8 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={onStart}
                    className="inline-flex items-center gap-2 rounded-xl bg-brand-orange hover:bg-brand-orange-deep transition px-7 py-4 text-white font-semibold text-base shadow-soft active:scale-[0.99]"
                  >
                    Запустить симуляцию
                    <ArrowRight className="h-5 w-5" />
                  </button>
                </div>

                <div className="mt-10 grid grid-cols-3 gap-3 max-w-lg">
                  <FeatureChip
                    icon={<ChefHat className="h-4 w-4" />}
                    label="5 станций"
                  />
                  <FeatureChip
                    icon={<Clock className="h-4 w-4" />}
                    label="7×16 часов"
                  />
                  <FeatureChip
                    icon={<Users className="h-4 w-4" />}
                    label="Команда смены"
                  />
                </div>
              </div>

              <div className="relative hidden lg:flex items-center justify-center px-8 py-10">
                <PreviewCard />
              </div>
            </div>
          </motion.div>

        </div>
      </div>
    </div>
  );
}

function BrandTopBar() {
  return (
    <header className="bg-white border-b border-graphite-100">
      <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-4 flex items-center gap-4">
        <div className="flex items-center gap-3">
          <LogoMark size={36} />
          <div className="flex items-baseline gap-2">
            <span className="font-extrabold tracking-tight text-graphite-900 text-lg">
              ТОЧКА ЗАПЯТАЯ
            </span>
          </div>
        </div>
      </div>
    </header>
  );
}

function FeatureChip({
  icon,
  label,
}: {
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <div className="flex items-center gap-2 rounded-xl bg-white/10 backdrop-blur-sm border border-white/15 px-3 py-2.5 text-sm text-white">
      <span className="text-brand-orange">{icon}</span>
      {label}
    </div>
  );
}


function DecorArrows() {
  return (
    <>
      <div className="absolute -bottom-16 -right-16 h-64 w-64 rounded-full bg-brand-forest-light/40 blur-3xl pointer-events-none" />
      <div className="absolute -top-24 -left-20 h-72 w-72 rounded-full bg-brand-forest-deep/60 blur-3xl pointer-events-none" />
    </>
  );
}

function PreviewCard() {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, rotate: -2 }}
      animate={{ opacity: 1, scale: 1, rotate: 0 }}
      transition={{ duration: 0.6, delay: 0.2 }}
      className="relative w-full max-w-md bg-white rounded-2xl shadow-2xl p-5 space-y-3"
    >
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-graphite-400 font-semibold">
            Текущий момент
          </div>
          <div className="text-xl font-bold text-graphite-900">
            27.04.2026 ·{" "}
            <span className="text-brand-orange">12:00</span>
          </div>
        </div>
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-brand-forest-soft text-brand-forest text-xs font-semibold border border-brand-forest/30">
          <span className="h-1.5 w-1.5 rounded-full bg-brand-forest" />
          Валидно
        </span>
      </div>

      <div className="grid grid-cols-5 gap-1.5">
        {[
          { k: "K", n: "Кухня", c: "bg-brand-forest-soft text-brand-forest" },
          { k: "C", n: "Прилавок", c: "bg-brand-forest-soft text-brand-forest" },
          { k: "BVR", n: "Напитки", c: "bg-brand-orange-soft text-brand-orange-deep" },
          { k: "FF", n: "Картофель", c: "bg-brand-forest-soft text-brand-forest" },
          { k: "TS", n: "Зал", c: "bg-brand-forest-soft text-brand-forest" },
        ].map((s) => (
          <div
            key={s.k}
            className={`rounded-lg ${s.c} p-2 text-center border border-current/10`}
          >
            <div className="text-[10px] font-bold tracking-wide">
              {s.k}
            </div>
            <div className="text-[9px] mt-0.5 opacity-80">{s.n}</div>
          </div>
        ))}
      </div>

      <div className="rounded-xl bg-graphite-50 border border-graphite-100 p-3 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-graphite-500">Покрытие часа</span>
          <span className="font-semibold text-graphite-900">12 / 12</span>
        </div>
        <div className="flex gap-1">
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={i}
              className={`h-2 flex-1 rounded-full ${
                i === 4 ? "bg-brand-orange" : "bg-brand-forest"
              }`}
            />
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2">
        <Stat label="exact" value="92%" tone="green" />
        <Stat label="запас" value="+1" tone="orange" />
        <Stat label="недобор" value="0" tone="green" />
      </div>
    </motion.div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "green" | "orange";
}) {
  const toneCls =
    tone === "green"
      ? "bg-brand-forest-soft text-brand-forest border-brand-forest/30"
      : "bg-brand-orange-soft text-brand-orange-deep border-brand-orange/40";
  return (
    <div className={`rounded-lg border p-2 ${toneCls}`}>
      <div className="text-[9px] uppercase tracking-wide opacity-80">
        {label}
      </div>
      <div className="text-base font-bold leading-tight">{value}</div>
    </div>
  );
}
