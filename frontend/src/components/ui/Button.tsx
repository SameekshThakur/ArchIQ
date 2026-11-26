import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'outline' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leading?: ReactNode;
  trailing?: ReactNode;
}

const variants: Record<ButtonVariant, string> = {
  primary:
    'accent-bg text-accent-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.22)] hover:brightness-110 active:brightness-95 border border-transparent',
  secondary: 'bg-raised text-fg border border-line hover:bg-overlay hover:border-fg-3/40 active:bg-raised',
  outline: 'bg-transparent text-fg border border-line hover:bg-raised active:bg-overlay',
  ghost: 'bg-transparent text-fg-2 border border-transparent hover:bg-raised hover:text-fg active:bg-overlay',
  danger: 'bg-critical/10 text-critical border border-critical/30 hover:bg-critical/20 active:bg-critical/25',
};

const sizes: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1.5',
  md: 'h-8 px-3 text-sm gap-2',
  lg: 'h-10 px-4 text-base gap-2',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading, leading, trailing, className, children, disabled, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'relative inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap rounded font-medium transition-[background,border-color,color,filter] duration-150',
        'disabled:cursor-not-allowed disabled:opacity-50',
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : leading}
      {children}
      {!loading && trailing}
    </button>
  );
});

export interface IconButtonProps extends Omit<ButtonProps, 'leading' | 'trailing'> {
  label: string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = 'ghost', size = 'md', loading, className, children, ...rest },
  ref,
) {
  const dim = size === 'sm' ? 'h-7 w-7' : size === 'lg' ? 'h-10 w-10' : 'h-8 w-8';
  return (
    <Button
      ref={ref}
      variant={variant}
      loading={loading}
      aria-label={label}
      title={label}
      className={cn('!px-0', dim, className)}
      {...rest}
    >
      {children}
    </Button>
  );
});

export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        'inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border border-line bg-raised px-1 font-mono text-[10px] leading-none text-fg-2',
        className,
      )}
    >
      {children}
    </kbd>
  );
}
