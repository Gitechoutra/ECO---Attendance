import { forwardRef } from 'react'
import clsx from 'clsx'
import { Loader2 } from 'lucide-react'

const VARIANTS = {
  primary: 'bg-brand text-[#03211D] hover:bg-brand-strong active:bg-brand-strong font-semibold',
  dark: 'bg-ink text-surface hover:bg-ink-2 font-semibold',
  secondary: 'bg-surface text-ink border border-line-strong hover:bg-surface-2 hover:border-faint',
  ghost: 'text-ink-2 hover:bg-surface-2 hover:text-ink',
  danger: 'bg-danger text-white hover:brightness-95 font-semibold',
  'danger-ghost': 'text-danger hover:bg-danger-soft',
  link: 'text-brand-ink hover:underline underline-offset-2 px-0 h-auto',
}
const SIZES = {
  xs: 'h-7 px-2.5 text-xs gap-1.5 rounded-md',
  sm: 'h-8 px-3 text-[13px] gap-1.5 rounded-lg',
  md: 'h-10 px-4 text-sm gap-2 rounded-lg',
  lg: 'h-11 px-5 text-[15px] gap-2 rounded-xl',
}

export const Button = forwardRef(function Button(
  { variant = 'primary', size = 'md', loading, icon: Icon, iconRight: IconRight, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={clsx(
        'inline-flex select-none items-center justify-center whitespace-nowrap font-medium transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:opacity-55',
        VARIANTS[variant], variant !== 'link' && SIZES[size], className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : Icon && <Icon className={size === 'xs' ? 'h-3.5 w-3.5' : 'h-4 w-4'} />}
      {children}
      {IconRight && !loading && <IconRight className="h-4 w-4" />}
    </button>
  )
})

export function IconButton({ icon: Icon, label, className, size = 'md', variant = 'ghost', ...rest }) {
  const dims = { sm: 'h-8 w-8', md: 'h-9 w-9', lg: 'h-10 w-10' }[size]
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={clsx(
        'inline-flex shrink-0 items-center justify-center rounded-lg transition-colors disabled:opacity-50',
        variant === 'ghost' && 'text-muted hover:bg-surface-2 hover:text-ink',
        variant === 'outline' && 'border border-line-strong text-ink-2 hover:bg-surface-2',
        variant === 'danger' && 'text-muted hover:bg-danger-soft hover:text-danger',
        dims, className,
      )}
      {...rest}
    >
      <Icon className="h-[18px] w-[18px]" />
    </button>
  )
}
