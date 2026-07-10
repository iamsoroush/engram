import type { ReactNode } from "react";

type ClassProps = {
  className?: string;
  children?: ReactNode;
};

const cx = (...classes: Array<string | false | undefined>) => classes.filter(Boolean).join(" ");

type ButtonProps = ClassProps &
  React.ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: "default" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
  };

export function Button({ className, variant = "default", size = "md", ...props }: ButtonProps) {
  return <button className={cx("btn", `btn-${variant}`, `btn-${size}`, className)} {...props} />;
}

export function Card({ className, ...props }: ClassProps & React.HTMLAttributes<HTMLDivElement>) {
  return <section className={cx("card", className)} {...props} />;
}

/** Directional chevron used by the back button + disclosure rows.
 *  Points inline-start (LTR "←"); mirrored under [dir="rtl"] via CSS. */
function ChevronBackGlyph() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m15 5-7 7 7 7" />
    </svg>
  );
}

/** Forward chevron (LTR "›"): used by disclosure rows — points inline-end closed, rotates to ▼ open. */
function ChevronForwardGlyph() {
  return (
    <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      <path d="m9 5 7 7-7 7" />
    </svg>
  );
}

/** One shared back affordance: ≥44px tap target, RTL-mirrored SVG chevron (no `←` literal). */
export function BackButton({
  onBack,
  label,
  className,
}: {
  onBack: () => void;
  label: string;
  className?: string;
}) {
  return (
    <button className={cx("back-button", className)} onClick={onBack} type="button">
      <span className="back-button-chevron" aria-hidden="true">
        <ChevronBackGlyph />
      </span>
      <span>{label}</span>
    </button>
  );
}

/** Shared screen header for account/utility screens: back button + title + optional actions. */
export function ScreenHeader({
  title,
  onBack,
  backLabel,
  actions,
}: {
  title: ReactNode;
  onBack: () => void;
  backLabel: string;
  actions?: ReactNode;
}) {
  return (
    <div className="screen-header">
      <BackButton onBack={onBack} label={backLabel} />
      <h1>{title}</h1>
      {actions ? <div className="screen-header-actions">{actions}</div> : null}
    </div>
  );
}

/** Thin styled-native `<select>` wrapper — one visual system with SelectMenu, keeps native a11y. */
export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx("select", className)} {...props} />;
}

/** Full-width disclosure row: ≥44px, RTL-mirroring chevron that rotates 90° when open. */
export function DisclosureRow({
  open,
  onToggle,
  children,
  className,
}: {
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      className={cx("disclosure-row", open && "is-open", className)}
      onClick={onToggle}
      type="button"
      aria-expanded={open}
    >
      <span className="disclosure-row-body">{children}</span>
      <span className="disclosure-row-chevron" aria-hidden="true">
        <ChevronForwardGlyph />
      </span>
    </button>
  );
}

export function Badge({
  className,
  tone = "neutral",
  ...props
}: ClassProps & React.HTMLAttributes<HTMLSpanElement> & { tone?: "neutral" | "blue" | "green" | "amber" | "red" }) {
  return <span className={cx("badge", `badge-${tone}`, className)} {...props} />;
}

export function Input(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx("input", props.className)} {...props} />;
}

export function Textarea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx("textarea", props.className)} {...props} />;
}

export function Alert({
  tone = "blue",
  className,
  ...props
}: ClassProps & React.HTMLAttributes<HTMLDivElement> & { tone?: "blue" | "amber" | "red" | "green" }) {
  return <div className={cx("alert", `alert-${tone}`, className)} {...props} />;
}

export function Separator() {
  return <div className="separator" />;
}

export function ScrollArea({ className, ...props }: ClassProps & React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("scroll-area", className)} {...props} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} />;
}

/** The single segmented control for the app (tabs, scope/series toggles). Renders proper tab
 *  semantics (`role="tab"` + `aria-selected`, matching the clinical-tabs pattern). Pass `ariaLabel`
 *  to name the group and an optional per-option `testId`. */
export function Tabs<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
  className,
}: {
  value: T;
  options: Array<{ value: T; label: string; testId?: string }>;
  onChange: (value: T) => void;
  ariaLabel?: string;
  className?: string;
}) {
  return (
    <div className={cx("tabs", className)} role="tablist" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          className={cx("tab", value === option.value && "tab-active")}
          key={option.value}
          data-testid={option.testId}
          onClick={() => onChange(option.value)}
          type="button"
          role="tab"
          aria-selected={value === option.value}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Dialog({
  open,
  title,
  children,
  footer,
  onClose,
  className,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  className?: string;
}) {
  if (!open) return null;

  return (
    <div className="overlay" role="presentation">
      <div aria-modal="true" className={cx("dialog", className)} role="dialog">
        <div className="dialog-header">
          <h2>{title}</h2>
          <Button aria-label="Close dialog" onClick={onClose} size="sm" variant="ghost">
            x
          </Button>
        </div>
        <div>{children}</div>
        {footer ? <div className="dialog-footer">{footer}</div> : null}
      </div>
    </div>
  );
}

export function Sheet({
  open,
  title,
  leading,
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  leading?: ReactNode;
  children: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div className="overlay sheet-overlay" role="presentation">
      <aside aria-modal="true" className="sheet" role="dialog">
        <div className="dialog-header">
          <div className="sheet-title">
            {leading ? (
              <span className="sheet-title-icon" aria-hidden="true">
                {leading}
              </span>
            ) : null}
            <h2>{title}</h2>
          </div>
          <button aria-label="Close" className="sheet-close" onClick={onClose} type="button">
            <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </div>
        {children}
      </aside>
    </div>
  );
}

export function DropdownMenu({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <details className="dropdown">
      <summary>{label}</summary>
      <div className="dropdown-content">{children}</div>
    </details>
  );
}

export function Toast({ message }: { message?: string }) {
  if (!message) return null;
  return <div className="toast">{message}</div>;
}
