import { motion } from "framer-motion";
import { avatarLook, BRAND_LOGO, BRAND_UNIFORM } from "../lib/avatar";
import { UniformBrandMark } from "./UniformBrandMark";

/** Тот же viewBox и фигура, что у ChibiPerson на плане зала — пропорции совпадают при любом size. */
const FIG_VB_W = 80;
const FIG_VB_H = 110;

interface EmployeeAvatarProps {
  employeeId: number;
  size?: number;
  showId?: boolean;
  onClick?: () => void;
  highlighted?: boolean;
  badgeColor?: string;
}

export function EmployeeAvatar({
  employeeId,
  size = 64,
  showId = true,
  onClick,
  highlighted = false,
  badgeColor = "#F26522",
}: EmployeeAvatarProps) {
  const look = avatarLook(employeeId);
  const svgHeight = (size * FIG_VB_H) / FIG_VB_W;
  const padBottom = showId ? 22 : 6;

  return (
    <motion.button
      type="button"
      onClick={onClick}
      layout
      className={`group relative flex flex-col items-center select-none focus:outline-none ${
        onClick ? "cursor-pointer" : "cursor-default"
      }`}
      whileHover={onClick ? { y: -2 } : undefined}
      whileTap={onClick ? { scale: 0.96 } : undefined}
      aria-label={`Сотрудник ${employeeId}`}
    >
      <div
        className={`relative rounded-2xl transition overflow-visible ${
          highlighted
            ? "ring-2 ring-brand-orange ring-offset-2 ring-offset-white"
            : ""
        }`}
        style={{ width: size, height: svgHeight + padBottom }}
      >
        <svg
          viewBox={`0 0 ${FIG_VB_W} ${FIG_VB_H}`}
          width={size}
          height={svgHeight}
          className="block overflow-visible"
        >
          <defs>
            <radialGradient
              id={`shadow-av-${employeeId}`}
              cx="50%"
              cy="50%"
              r="50%"
            >
              <stop offset="0%" stopColor="rgba(20,24,32,0.18)" />
              <stop offset="100%" stopColor="rgba(20,24,32,0)" />
            </radialGradient>
          </defs>
          <ellipse
            cx="40"
            cy="104"
            rx="22"
            ry="4"
            fill={`url(#shadow-av-${employeeId})`}
          />

          <rect
            x="24"
            y="94"
            width="32"
            height="13"
            rx="5"
            fill={BRAND_UNIFORM.black}
          />
          <rect
            x="22"
            y="62"
            width="36"
            height="34"
            rx="10"
            fill={BRAND_UNIFORM.green}
            stroke={BRAND_UNIFORM.greenDeep}
            strokeWidth="0.8"
          />
          <rect
            x="28"
            y="62"
            width="24"
            height="7"
            rx="3"
            fill={BRAND_UNIFORM.trim}
          />
          <rect
            x="22"
            y="68"
            width="36"
            height="6"
            rx="3"
            fill="rgba(255,255,255,0.12)"
          />
          <g transform="translate(40, 76)">
            <UniformBrandMark scale={1.22} />
          </g>
          <rect
            x="14"
            y="68"
            width="10"
            height="22"
            rx="5"
            fill={BRAND_UNIFORM.green}
            stroke={BRAND_UNIFORM.greenDeep}
            strokeWidth="0.6"
          />
          <rect
            x="56"
            y="68"
            width="10"
            height="22"
            rx="5"
            fill={BRAND_UNIFORM.green}
            stroke={BRAND_UNIFORM.greenDeep}
            strokeWidth="0.6"
          />
          <circle cx="19" cy="92" r="6" fill={look.skin} />
          <circle cx="61" cy="92" r="6" fill={look.skin} />

          <ellipse cx="40" cy="36" rx="26" ry="26" fill={look.skin} />

          {look.hairStyle === 0 && (
            <path
              d="M16 36 C16 18, 26 8, 40 8 C54 8, 64 18, 64 36 L64 26 C64 22, 60 20, 56 20 L24 20 C20 20, 16 22, 16 26 Z"
              fill={look.hair}
            />
          )}
          {look.hairStyle === 1 && (
            <path
              d="M16 38 C16 18, 26 8, 40 8 C54 8, 64 18, 64 38 C58 28, 52 24, 40 24 C28 24, 22 28, 16 38 Z"
              fill={look.hair}
            />
          )}
          {look.hairStyle === 2 && (
            <path
              d="M18 36 C18 18, 28 10, 40 10 C52 10, 62 18, 62 36 L58 30 L54 36 L50 30 L46 36 L42 30 L38 36 L34 30 L30 36 L26 30 L22 36 Z"
              fill={look.hair}
            />
          )}

          <ellipse cx="32" cy="38" rx="2" ry="2.6" fill="#1f242c" />
          <ellipse cx="48" cy="38" rx="2" ry="2.6" fill="#1f242c" />
          <path
            d="M34 46 Q40 50 46 46"
            stroke="#1f242c"
            strokeWidth="1.6"
            strokeLinecap="round"
            fill="none"
          />

          <g>
            <path
              d="M14 21.85 C14 7.1 26 2.55 40 2.2 C54 2.55 66 7.1 66 21.85 Z"
              fill={BRAND_UNIFORM.green}
              stroke={BRAND_UNIFORM.greenDeep}
              strokeWidth="0.75"
            />
            <path
              d="M14 21.5 L66 21.5 L64.8 25.65 L15.2 25.65 Z"
              fill={BRAND_LOGO.fries}
              stroke="#e07000"
              strokeWidth="0.45"
            />
            <circle cx="40" cy="3.3" r="1.85" fill={BRAND_LOGO.fries} />
          </g>
          {highlighted && (
            <circle
              cx="40"
              cy="36"
              r="30"
              fill="none"
              stroke={BRAND_LOGO.fries}
              strokeWidth="3"
            />
          )}
        </svg>
        {showId && (
          <div
            className="absolute -bottom-1 left-1/2 -translate-x-1/2 px-1.5 py-0.5 rounded-md text-[10px] font-semibold text-white shadow"
            style={{ background: badgeColor }}
          >
            #{employeeId}
          </div>
        )}
      </div>
    </motion.button>
  );
}
