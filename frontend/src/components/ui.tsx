import * as Dialog from "@radix-ui/react-dialog";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { X } from "lucide-react";
import { createContext, useCallback, useContext, useState, type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "../lib/utils";

const buttonStyles = cva("button", {
  variants: {
    variant: {
      primary: "button-primary",
      secondary: "button-secondary",
      quiet: "button-quiet",
      danger: "button-danger",
    },
    size: { default: "", sm: "button-sm", icon: "button-icon" },
  },
  defaultVariants: { variant: "primary", size: "default" },
});

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonStyles> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild, ...props }: ButtonProps) {
  const Component = asChild ? Slot : "button";
  return <Component className={cn(buttonStyles({ variant, size }), className)} {...props} />;
}

export function Panel({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return <section className={cn("card", className)} {...props} />;
}

export function GlassPanel({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return <section className={cn("glass-panel", className)} {...props} />;
}

export function Badge({ className, tone = "neutral", children }: { className?: string; tone?: "neutral" | "sage" | "gold" | "rose" | "ink"; children: ReactNode }) {
  return <span className={cn("badge", `badge-${tone}`, className)}>{children}</span>;
}

export function Avatar({ name, initials, className }: { name: string; initials: string; className?: string }) {
  return <span className={cn("avatar", className)} aria-label={name}>{initials}</span>;
}

interface ToastMessage { id: number; message: string; tone: "success" | "info" }
const ToastContext = createContext<(message: string, tone?: ToastMessage["tone"]) => void>(() => undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const notify = useCallback((message: string, tone: ToastMessage["tone"] = "success") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 3200);
  }, []);
  return <ToastContext.Provider value={notify}>{children}<div className="toast-region" aria-live="polite">{toasts.map((toast) => <div key={toast.id} className={`toast toast-${toast.tone}`}><span className="toast-mark">{toast.tone === "success" ? "✓" : "i"}</span>{toast.message}</div>)}</div></ToastContext.Provider>;
}

export const useToast = () => useContext(ToastContext);

export function ConfirmDialog({ trigger, title, description, confirmLabel, onConfirm }: {
  trigger: ReactNode;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
}) {
  return <Dialog.Root><Dialog.Trigger asChild>{trigger}</Dialog.Trigger><Dialog.Portal>
    <Dialog.Overlay className="modal-backdrop" />
    <Dialog.Content className="modal" aria-describedby="confirm-description">
      <div className="modal-head"><Dialog.Title className="modal-title">{title}</Dialog.Title><Dialog.Close asChild><Button variant="quiet" size="icon" aria-label="Close dialog"><X size={16} /></Button></Dialog.Close></div>
      <Dialog.Description id="confirm-description" className="modal-description">{description}</Dialog.Description>
      <div className="modal-actions"><Dialog.Close asChild><Button variant="secondary">Cancel</Button></Dialog.Close><Dialog.Close asChild><Button onClick={onConfirm}>{confirmLabel}</Button></Dialog.Close></div>
    </Dialog.Content>
  </Dialog.Portal></Dialog.Root>;
}

export const StatusBadge = ({ status }: { status: string }) => {
  const tone = /published|graded|verified|ready|approved|on time|high confidence/i.test(status) ? "sage" : /late|review|processing|pending|low confidence/i.test(status) ? "gold" : /failed|rejected/i.test(status) ? "rose" : "neutral";
  return <Badge tone={tone}><span className="badge-dot" />{status}</Badge>;
};

