import './BrandMark.css'

function BrandMark({ size = 'md', className = '' }) {
  const sizes = {
    sm: { mark: 24, text: 'text-sm' },
    md: { mark: 32, text: 'text-base' },
    lg: { mark: 40, text: 'text-lg' },
    xl: { mark: 48, text: 'text-xl' },
  }
  const s = sizes[size] || sizes.md

  return (
    <span className={`brand-mark brand-mark--${size} ${className}`.trim()}>
      <svg
        className="brand-mark__svg"
        width={s.mark}
        height={s.mark}
        viewBox="0 0 48 48"
        fill="none"
        aria-hidden="true"
      >
        <rect width="48" height="48" rx="12" fill="var(--color-primary)" />
        <path
          d="M14 30V18l10-7 10 7v12l-10 7-10-7z"
          fill="var(--color-primary-contrast)"
          opacity="0.95"
        />
        <path
          d="M24 21v9M19 24h10"
          stroke="var(--color-primary)"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      </svg>
      <span className={`brand-mark__text ${s.text}`}>RESOLVE</span>
    </span>
  )
}

export default BrandMark