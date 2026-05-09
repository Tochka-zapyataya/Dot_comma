interface LogoMarkProps {
  size?: number;
  className?: string;
  bgClassName?: string;
  fgClassName?: string;
  rounded?: string;
}

export function LogoMark({
  size = 36,
  className = "",
  bgClassName = "bg-brand-forest",
  fgClassName = "text-brand-orange",
  rounded = "rounded-xl",
}: LogoMarkProps) {
  return (
    <span
      className={`inline-flex items-center justify-center ${rounded} ${bgClassName} ${className} shadow-sm`}
      style={{ width: size, height: size }}
      aria-label="Точка запятая"
      role="img"
    >
      <svg
        viewBox="0 0 40 40"
        width={size}
        height={size}
        className={fgClassName}
        fill="currentColor"
        aria-hidden
      >
        <circle cx="20" cy="13" r="3.6" />
        <circle cx="20" cy="25" r="3.6" />
        <path
          d="M22.6 26.5
             c0.4 2.6 -1.4 5.6 -4.4 6.8
             c-0.5 0.2 -0.9 -0.4 -0.5 -0.8
             c1.6 -1.4 2.4 -3.2 2.3 -5.2
             z"
        />
      </svg>
    </span>
  );
}
