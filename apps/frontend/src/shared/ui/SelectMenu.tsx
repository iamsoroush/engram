import React from "react";
import { createPortal } from "react-dom";

export type SelectOption = { value: string; label: string };

/**
 * A small, accessible dropdown that renders its menu in a portal positioned at the trigger — so it
 * never mis-places or gets clipped by an ancestor's overflow/transform the way a native <select>
 * popup can (notably in embedded/webview browsers). Click-outside / Esc / scroll close it.
 */
export function SelectMenu({
  value,
  options,
  onChange,
  ariaLabel,
  disabled,
  className,
}: {
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  ariaLabel: string;
  disabled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [rect, setRect] = React.useState<DOMRect | null>(null);
  const triggerRef = React.useRef<HTMLButtonElement>(null);
  const current = options.find((option) => option.value === value);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const dismiss = () => setOpen(false);
    document.addEventListener("keydown", onKey);
    // Any scroll (capture phase) or resize closes it — simplest correct behavior, no stale positions.
    window.addEventListener("scroll", dismiss, true);
    window.addEventListener("resize", dismiss);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", dismiss, true);
      window.removeEventListener("resize", dismiss);
    };
  }, [open]);

  const toggle = () => {
    if (disabled) return;
    if (!open && triggerRef.current) setRect(triggerRef.current.getBoundingClientRect());
    setOpen((value) => !value);
  };

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        className={`select-menu-trigger${className ? ` ${className}` : ""}`}
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={toggle}
      >
        <span dir="auto">{current?.label ?? value}</span>
        <span className="select-menu-chev" aria-hidden="true">
          <svg viewBox="0 0 24 24" focusable="false">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </span>
      </button>
      {open && rect
        ? createPortal(
            <div className="select-menu-layer">
              <div className="select-menu-backdrop" onClick={() => setOpen(false)} />
              <ul
                className="select-menu-popup"
                role="listbox"
                aria-label={ariaLabel}
                style={{ position: "fixed", top: rect.bottom + 4, left: rect.left, minWidth: rect.width }}
              >
                {options.map((option) => (
                  <li
                    key={option.value}
                    role="option"
                    aria-selected={option.value === value}
                    className={`select-menu-option${option.value === value ? " selected" : ""}`}
                    onClick={() => {
                      onChange(option.value);
                      setOpen(false);
                    }}
                  >
                    <span dir="auto">{option.label}</span>
                    {option.value === value ? <span aria-hidden="true">✓</span> : null}
                  </li>
                ))}
              </ul>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
