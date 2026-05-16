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

export function Tabs<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (value: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {options.map((option) => (
        <button
          className={cx("tab", value === option.value && "tab-active")}
          key={option.value}
          onClick={() => onChange(option.value)}
          type="button"
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
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div className="overlay" role="presentation">
      <div aria-modal="true" className="dialog" role="dialog">
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
  children,
  onClose,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}) {
  if (!open) return null;

  return (
    <div className="overlay sheet-overlay" role="presentation">
      <aside aria-modal="true" className="sheet" role="dialog">
        <div className="dialog-header">
          <h2>{title}</h2>
          <Button aria-label="Close source preview" onClick={onClose} size="sm" variant="ghost">
            x
          </Button>
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
