// The "n" arch (a horizon) with the moon dot. Arch = text token, dot = accent token, so the
// same component is right in both themes.
export function Mark({ size = 24 }: { size?: number }) {
  return (
    <svg viewBox="22 14 66 68" width={size} height={size} aria-hidden="true">
      <path d="M32 76V48a18 18 0 0 1 36 0v28" fill="none" stroke="currentColor"
            strokeWidth="12" strokeLinecap="round" />
      <circle cx="78" cy="24" r="7" fill="rgb(var(--accent))" />
    </svg>
  );
}

export function Logo() {
  return (
    <span className="inline-flex items-center gap-2 text-text" aria-label="nightly">
      <Mark />
      <span className="font-display text-xl font-medium tracking-tight">
        nightly<span className="text-accent">.</span>
      </span>
    </span>
  );
}
