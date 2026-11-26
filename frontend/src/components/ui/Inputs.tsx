import * as RTabs from '@radix-ui/react-tabs';
import * as RSwitch from '@radix-ui/react-switch';
import * as RSelect from '@radix-ui/react-select';
import { Check, ChevronDown, Search, X } from 'lucide-react';
import { forwardRef, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';
import { Kbd } from './Button';

/* ---------- Text inputs ---------- */
export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function TextInput(
  { className, ...rest },
  ref,
) {
  return (
    <input
      ref={ref}
      className={cn(
        'h-8 w-full rounded border border-line bg-bg px-2.5 text-sm text-fg placeholder:text-fg-3 transition-colors duration-150',
        'hover:border-fg-3/40 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className,
      )}
      {...rest}
    />
  );
});

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function TextArea(
  { className, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      className={cn(
        'w-full resize-y rounded border border-line bg-bg px-2.5 py-2 text-sm text-fg placeholder:text-fg-3 transition-colors duration-150',
        'hover:border-fg-3/40 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
        className,
      )}
      {...rest}
    />
  );
});

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn('block', className)}>
      <span className="micro mb-1.5 block">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-fg-3">{hint}</span>}
    </label>
  );
}

export const SearchInput = forwardRef<
  HTMLInputElement,
  Omit<InputHTMLAttributes<HTMLInputElement>, 'onChange' | 'value'> & {
    value: string;
    onChange: (v: string) => void;
    shortcut?: string;
  }
>(function SearchInput({ value, onChange, shortcut, className, placeholder = 'Search', ...rest }, ref) {
  return (
    <div className={cn('relative', className)}>
      <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-fg-3" aria-hidden />
      <TextInput
        ref={ref}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        className="pl-8 pr-8 [&::-webkit-search-cancel-button]:hidden"
        {...rest}
      />
      {value ? (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => onChange('')}
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-fg-3 hover:text-fg"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      ) : (
        shortcut && <Kbd className="absolute right-2 top-1/2 -translate-y-1/2">{shortcut}</Kbd>
      )}
    </div>
  );
});

/* ---------- Segmented control ---------- */
export function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  size = 'md',
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; icon?: ReactNode }[];
  size?: 'sm' | 'md';
  label?: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-bg p-0.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o.value)}
            className={cn(
              'inline-flex items-center gap-1.5 rounded font-medium transition-colors duration-150',
              size === 'sm' ? 'h-6 px-2 text-xs' : 'h-7 px-2.5 text-xs',
              active ? 'bg-raised text-fg shadow-inset ring-1 ring-line' : 'text-fg-3 hover:text-fg',
            )}
          >
            {o.icon}
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/* ---------- Tabs ---------- */
export interface TabItem {
  value: string;
  label: ReactNode;
  count?: number;
  content?: ReactNode;
}

export function Tabs({
  value,
  onValueChange,
  items,
  className,
  listClassName,
  contentClassName,
}: {
  value: string;
  onValueChange: (v: string) => void;
  items: TabItem[];
  className?: string;
  listClassName?: string;
  contentClassName?: string;
}) {
  return (
    <RTabs.Root value={value} onValueChange={onValueChange} className={className}>
      <RTabs.List className={cn('flex gap-1 border-b border-line', listClassName)}>
        {items.map((t) => (
          <RTabs.Trigger
            key={t.value}
            value={t.value}
            className={cn(
              'relative -mb-px inline-flex h-9 items-center gap-1.5 border-b-2 border-transparent px-3 text-sm font-medium text-fg-3 transition-colors duration-150',
              'hover:text-fg data-[state=active]:border-accent data-[state=active]:text-fg',
            )}
          >
            {t.label}
            {t.count !== undefined && (
              <span className="num rounded bg-raised px-1.5 font-mono text-[10px] leading-4 text-fg-2">{t.count}</span>
            )}
          </RTabs.Trigger>
        ))}
      </RTabs.List>
      {items.map(
        (t) =>
          t.content !== undefined && (
            <RTabs.Content key={t.value} value={t.value} className={cn('pt-4 focus-visible:outline-none', contentClassName)}>
              {t.content}
            </RTabs.Content>
          ),
      )}
    </RTabs.Root>
  );
}

/* ---------- Switch ---------- */
export function Switch({
  checked,
  onCheckedChange,
  label,
}: {
  checked: boolean;
  onCheckedChange: (c: boolean) => void;
  label: string;
}) {
  return (
    <RSwitch.Root
      checked={checked}
      onCheckedChange={onCheckedChange}
      aria-label={label}
      className="relative h-[18px] w-8 shrink-0 rounded-full border border-line bg-raised transition-colors duration-150 data-[state=checked]:border-transparent data-[state=checked]:bg-accent"
    >
      <RSwitch.Thumb className="block h-3 w-3 translate-x-[2px] rounded-full bg-fg-2 transition-transform duration-150 data-[state=checked]:translate-x-[16px] data-[state=checked]:bg-white" />
    </RSwitch.Root>
  );
}

/* ---------- Select ---------- */
export function Select({
  value,
  onValueChange,
  options,
  placeholder = 'Select',
  label,
  className,
}: {
  value: string;
  onValueChange: (v: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  label?: string;
  className?: string;
}) {
  return (
    <RSelect.Root value={value} onValueChange={onValueChange}>
      <RSelect.Trigger
        aria-label={label ?? placeholder}
        className={cn(
          'inline-flex h-8 min-w-[120px] items-center justify-between gap-2 rounded border border-line bg-bg px-2.5 text-sm text-fg transition-colors duration-150',
          'hover:border-fg-3/40 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30 data-[placeholder]:text-fg-3',
          className,
        )}
      >
        <RSelect.Value placeholder={placeholder} />
        <RSelect.Icon>
          <ChevronDown className="h-3.5 w-3.5 text-fg-3" />
        </RSelect.Icon>
      </RSelect.Trigger>
      <RSelect.Portal>
        <RSelect.Content
          position="popper"
          sideOffset={4}
          className="glass z-[75] min-w-[var(--radix-select-trigger-width)] animate-fadeIn overflow-hidden rounded-md border border-line p-1 shadow-pop"
        >
          <RSelect.Viewport>
            {options.map((o) => (
              <RSelect.Item
                key={o.value}
                value={o.value}
                className="relative flex h-7 cursor-default select-none items-center rounded px-2 pr-7 text-sm text-fg outline-none data-[highlighted]:bg-raised"
              >
                <RSelect.ItemText>{o.label}</RSelect.ItemText>
                <RSelect.ItemIndicator className="absolute right-2">
                  <Check className="h-3.5 w-3.5 text-accent" />
                </RSelect.ItemIndicator>
              </RSelect.Item>
            ))}
          </RSelect.Viewport>
        </RSelect.Content>
      </RSelect.Portal>
    </RSelect.Root>
  );
}

/* ---------- Slider (styled native range) ---------- */
export function Slider({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  label,
  format,
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label: string;
  format?: (v: number) => string;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="micro">{label}</span>
        <span className="num font-mono text-xs text-fg">{format ? format(value) : value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-label={label}
        onChange={(e) => onChange(Number(e.target.value))}
        className="aq-range h-1.5 w-full cursor-pointer appearance-none rounded-full bg-raised outline-none focus-visible:ring-2 focus-visible:ring-accent/40"
        style={{ background: `linear-gradient(90deg, rgb(var(--accent)) ${pct}%, rgb(var(--raised)) ${pct}%)` }}
      />
    </div>
  );
}

/* ---------- Filter bar with chips ---------- */
export interface FilterDef {
  key: string;
  label: string;
  options: { value: string; label: string }[];
}

export function FilterBar({
  filters,
  values,
  onChange,
  search,
  onSearch,
  searchPlaceholder,
  trailing,
}: {
  filters: FilterDef[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  search?: string;
  onSearch?: (v: string) => void;
  searchPlaceholder?: string;
  trailing?: ReactNode;
}) {
  const active = filters.filter((f) => values[f.key] && values[f.key] !== 'all');
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {onSearch && (
          <SearchInput
            value={search ?? ''}
            onChange={onSearch}
            placeholder={searchPlaceholder ?? 'Search'}
            shortcut="/"
            className="w-64"
            data-search-input
          />
        )}
        {filters.map((f) => (
          <Select
            key={f.key}
            label={f.label}
            value={values[f.key] ?? 'all'}
            onValueChange={(v) => onChange(f.key, v)}
            placeholder={f.label}
            options={[{ value: 'all', label: `All ${f.label.toLowerCase()}` }, ...f.options]}
          />
        ))}
        <div className="ml-auto flex items-center gap-2">{trailing}</div>
      </div>
      {active.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          {active.map((f) => (
            <span
              key={f.key}
              className="inline-flex h-6 items-center gap-1 rounded-full border border-accent/30 bg-accent/10 pl-2 pr-1 text-xs text-accent"
            >
              <span className="text-fg-3">{f.label}:</span> {f.options.find((o) => o.value === values[f.key])?.label ?? values[f.key]}
              <button
                type="button"
                aria-label={`Remove ${f.label} filter`}
                onClick={() => onChange(f.key, 'all')}
                className="rounded-full p-0.5 hover:bg-accent/20"
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          ))}
          <button
            type="button"
            onClick={() => active.forEach((f) => onChange(f.key, 'all'))}
            className="px-1 text-xs text-fg-3 hover:text-fg"
          >
            Clear all
          </button>
        </div>
      )}
    </div>
  );
}
