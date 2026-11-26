import * as Dialog from '@radix-ui/react-dialog';
import * as TooltipPrimitive from '@radix-ui/react-tooltip';
import { CheckCircle2, Info, X, XCircle } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';
import { useUI } from '@/store/ui';
import { IconButton } from './Button';

/* ---------- Tooltip ---------- */
export function Tooltip({
  content,
  children,
  side = 'top',
  delay = 250,
}: {
  content: ReactNode;
  children: ReactNode;
  side?: 'top' | 'right' | 'bottom' | 'left';
  delay?: number;
}) {
  if (!content) return <>{children}</>;
  return (
    <TooltipPrimitive.Root delayDuration={delay}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          side={side}
          sideOffset={6}
          className="glass z-[70] max-w-xs animate-fadeIn rounded-md border border-line px-2 py-1 text-xs text-fg shadow-pop"
        >
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export const TooltipProvider = TooltipPrimitive.Provider;

/* ---------- Drawer (non-modal inspector) ---------- */
export function Drawer({
  open,
  onOpenChange,
  title,
  subtitle,
  actions,
  children,
  width = 480,
  modal = false,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  width?: number;
  modal?: boolean;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={modal}>
      <Dialog.Portal>
        {modal && <Dialog.Overlay className="fixed inset-0 z-40 animate-fadeIn bg-[rgb(var(--scrim)/0.55)]" />}
        <Dialog.Content
          aria-describedby={undefined}
          onInteractOutside={(e) => {
            if (!modal) e.preventDefault();
          }}
          style={{ width }}
          className="glass fixed bottom-0 right-0 top-0 z-50 flex max-w-[94vw] animate-slideIn flex-col border-l border-line shadow-pop"
        >
          <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
            <div className="min-w-0">
              <Dialog.Title className="truncate text-base font-semibold text-fg">{title}</Dialog.Title>
              {subtitle && <div className="mt-1 text-xs text-fg-3">{subtitle}</div>}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {actions}
              <Dialog.Close asChild>
                <IconButton label="Close panel (Esc)" size="sm">
                  <X className="h-4 w-4" />
                </IconButton>
              </Dialog.Close>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ---------- Modal ---------- */
export function Modal({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  width = 520,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] animate-fadeIn bg-[rgb(var(--scrim)/0.6)] backdrop-blur-[2px]" />
        <Dialog.Content
          aria-describedby={description ? undefined : undefined}
          style={{ width }}
          className="glass fixed left-1/2 top-[14vh] z-[61] max-h-[76vh] max-w-[94vw] -translate-x-1/2 animate-rise overflow-hidden rounded-lg border border-line shadow-pop"
        >
          <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-3.5">
            <div>
              <Dialog.Title className="text-base font-semibold">{title}</Dialog.Title>
              {description && <Dialog.Description className="mt-0.5 text-xs text-fg-3">{description}</Dialog.Description>}
            </div>
            <Dialog.Close asChild>
              <IconButton label="Close dialog" size="sm">
                <X className="h-4 w-4" />
              </IconButton>
            </Dialog.Close>
          </div>
          <div className="max-h-[56vh] overflow-y-auto px-5 py-4">{children}</div>
          {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

/* ---------- Toasts ---------- */
const toneIcon = {
  neutral: Info,
  info: Info,
  success: CheckCircle2,
  error: XCircle,
} as const;

export function Toaster() {
  const toasts = useUI((s) => s.toasts);
  const dismiss = useUI((s) => s.dismissToast);
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-[80] flex w-80 flex-col gap-2" aria-live="polite">
      {toasts.map((t) => {
        const Icon = toneIcon[t.tone];
        return (
          <div
            key={t.id}
            role="status"
            className="glass pointer-events-auto flex animate-rise items-start gap-2.5 rounded-lg border border-line p-3 shadow-pop"
          >
            <Icon
              className={cn(
                'mt-0.5 h-4 w-4 shrink-0',
                t.tone === 'success' && 'text-healthy',
                t.tone === 'error' && 'text-critical',
                (t.tone === 'info' || t.tone === 'neutral') && 'text-accent',
              )}
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{t.title}</p>
              {t.description && <p className="mt-0.5 text-xs text-fg-2">{t.description}</p>}
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(t.id)}
              className="rounded p-0.5 text-fg-3 hover:text-fg"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
