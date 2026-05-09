import { motion } from "framer-motion";
import { avatarLook } from "../lib/avatar";

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
  const bodyHeight = size * 0.55;

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
        className={`relative rounded-2xl transition ${
          highlighted
            ? "ring-2 ring-brand-orange ring-offset-2 ring-offset-white"
            : ""
        }`}
        style={{ width: size, height: size + 8 }}
      >
        <svg
          viewBox="0 0 64 72"
          width={size}
          height={size + 8}
          className="block"
        >
          <defs>
            <radialGradient id={`shadow-${employeeId}`} cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(20,24,32,0.18)" />
              <stop offset="100%" stopColor="rgba(20,24,32,0)" />
            </radialGradient>
          </defs>
          <ellipse
            cx="32"
            cy="68"
            rx="18"
            ry="3"
            fill={`url(#shadow-${employeeId})`}
          />
          <rect
            x={32 - 14}
            y={72 - bodyHeight}
            width="28"
            height={bodyHeight}
            rx="10"
            fill={look.shirt}
          />
          <rect
            x="22"
            y={72 - bodyHeight + 4}
            width="20"
            height="6"
            rx="3"
            fill="rgba(255,255,255,0.18)"
          />
          <circle cx="32" cy="22" r="14" fill={look.skin} />
          {look.hairStyle === 0 && (
            <path
              d="M18 22 C18 14, 24 8, 32 8 C40 8, 46 14, 46 22 L46 16 C46 14, 44 13, 42 13 L22 13 C20 13, 18 14, 18 16 Z"
              fill={look.hair}
            />
          )}
          {look.hairStyle === 1 && (
            <path
              d="M19 24 C19 14, 25 8, 32 8 C39 8, 45 14, 45 24 C42 18, 39 16, 32 16 C25 16, 22 18, 19 24 Z"
              fill={look.hair}
            />
          )}
          {look.hairStyle === 2 && (
            <path
              d="M20 22 C20 14, 26 9, 32 9 C38 9, 44 14, 44 22 L42 19 L40 22 L38 19 L36 22 L34 19 L32 22 L30 19 L28 22 L26 19 L24 22 L22 19 Z"
              fill={look.hair}
            />
          )}
          <circle cx="27" cy="23" r="1.4" fill="#1f242c" />
          <circle cx="37" cy="23" r="1.4" fill="#1f242c" />
          <path
            d="M28 28 Q32 30 36 28"
            stroke="#1f242c"
            strokeWidth="1.2"
            strokeLinecap="round"
            fill="none"
          />
          {look.accessory === "cap" && (
            <path
              d="M16 16 L48 16 L46 12 L18 12 Z M14 17 L50 17 L50 19 L14 19 Z"
              fill="#F26522"
            />
          )}
          {look.accessory === "glasses" && (
            <g
              stroke="#1f242c"
              strokeWidth="1.2"
              fill="rgba(255,255,255,0.6)"
            >
              <circle cx="27" cy="23" r="3" />
              <circle cx="37" cy="23" r="3" />
              <line x1="30" y1="23" x2="34" y2="23" />
            </g>
          )}
          {look.accessory === "earring" && (
            <circle cx="46" cy="25" r="1.2" fill="#F26522" />
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
