interface LogoProps {
  size?: number;
  className?: string;
}

export function Logo({ size = 32, className }: LogoProps) {
  const inner = Math.round(size * 0.625);
  return (
    <span
      className={className}
      style={{
        display: "inline-grid",
        placeItems: "center",
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.25),
        background: "linear-gradient(135deg, #3B82F6 0%, #1D4ED8 100%)",
        boxShadow:
          "0 2px 8px rgba(37, 99, 235, 0.22), inset 0 1px 0 rgba(255, 255, 255, 0.18)",
      }}
      aria-hidden="true"
    >
      <svg
        width={inner}
        height={inner}
        viewBox="0 0 32 32"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          d="M16 3.5L28 10.5V21.5L16 28.5L4 21.5V10.5L16 3.5Z"
          stroke="white"
          strokeWidth="1.6"
          strokeLinejoin="round"
        />
        <path
          d="M16 10L22 16L16 22L10 16L16 10Z"
          stroke="white"
          strokeWidth="1.4"
          strokeLinejoin="round"
        />
        <circle cx="16" cy="16" r="2" fill="white" />
      </svg>
    </span>
  );
}
