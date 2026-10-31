import { Bell, CheckCheck, ClipboardCheck, Clock, FilePen, FilePlus2, MessageSquareWarning, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useToast } from "../ui";
import { cn } from "../../lib/utils";
import { notificationService, type AppNotification, type NotificationType } from "../../services/api";

/** How often the bell checks for new notifications while the tab is visible. */
const POLL_MS = 20_000;

const typeIcon: Record<NotificationType, typeof Bell> = {
  assignment_published: FilePlus2,
  assignment_updated: FilePen,
  result_published: ClipboardCheck,
  result_updated: ClipboardCheck,
  late_decision: Clock,
  review_resolved: MessageSquareWarning,
  submission_received: Upload,
  review_requested: MessageSquareWarning,
};

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

interface NotificationBellProps {
  /** Called when new notifications arrive, so the dashboard can reload assignments, submissions and grades. */
  onNew?: (items: AppNotification[]) => void;
}

/**
 * Topbar bell: students hear about new/updated assignments and results, teachers about new submissions.
 * Polls the backend while the tab is visible (and immediately when it regains focus).
 */
export function NotificationBell({ onNew }: NotificationBellProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AppNotification[]>([]);
  const [unread, setUnread] = useState(0);
  const [unavailable, setUnavailable] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const seen = useRef<Set<string> | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const onNewRef = useRef(onNew);
  onNewRef.current = onNew;

  // 503 = notifications aren't set up on the server (migration not applied): stop polling until
  // reload instead of failing a request every 20 s on every page.
  const serverMissing = useRef(false);
  const refresh = useCallback(async () => {
    if (serverMissing.current) return;
    try {
      const data = await notificationService.list();
      setItems(data.items);
      setUnread(data.unread_count);
      setUnavailable(false);
      // First load only records what exists; later loads announce anything new and unread.
      const fresh = seen.current ? data.items.filter((item) => !seen.current!.has(item.id) && !item.read_at) : [];
      seen.current = new Set([...(seen.current ?? []), ...data.items.map((item) => item.id)]);
      if (fresh.length > 0) {
        toast(fresh.length === 1 ? fresh[0].title : `${fresh.length} new notifications`, "info");
        onNewRef.current?.(fresh);
      }
    } catch (error) {
      if ((error as { response?: { status?: number } })?.response?.status === 503) serverMissing.current = true;
      setUnavailable(true);
    } finally {
      setLoaded(true);
    }
  }, [toast]);

  // Poll while visible; check right away when the user comes back to the tab.
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [refresh]);

  // Close on navigation, outside click and Escape.
  useEffect(() => setOpen(false), [location.pathname, location.search]);
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const markRead = (ids?: string[]) => {
    const now = new Date().toISOString();
    const target = ids ? new Set(ids) : null;
    const changed = items.filter((item) => !item.read_at && (!target || target.has(item.id))).length;
    if (changed === 0) return;
    setItems((current) => current.map((item) => (!item.read_at && (!target || target.has(item.id)) ? { ...item, read_at: now } : item)));
    setUnread((count) => (target ? Math.max(0, count - changed) : 0));
    notificationService.markRead(ids).catch(() => void refresh());
  };

  const openItem = (item: AppNotification) => {
    markRead([item.id]);
    setOpen(false);
    if (item.link) navigate(item.link);
  };

  const badge = unread > 99 ? "99+" : String(unread);

  return (
    <div className="notification-wrap" ref={wrapRef}>
      <button
        className="icon-button notification-button"
        aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => {
          setOpen((value) => !value);
          if (!open) void refresh();
        }}
      >
        <Bell size={17} />
        {unread > 0 && <span className="notification-badge">{badge}</span>}
      </button>
      {open && (
        <div className="notification-popover glass-panel" role="dialog" aria-label="Notifications">
          <div className="notification-head">
            <strong>Notifications</strong>
            {unread > 0 && (
              <button className="notification-mark-all" onClick={() => markRead()}>
                <CheckCheck size={13} /> Mark all read
              </button>
            )}
          </div>
          {unavailable && items.length === 0 ? (
            <p className="notification-empty">Notifications are unavailable right now.</p>
          ) : !loaded ? (
            <p className="notification-empty">Loading…</p>
          ) : items.length === 0 ? (
            <p className="notification-empty">You're all caught up.</p>
          ) : (
            <ul className="notification-list">
              {items.map((item) => {
                const Icon = typeIcon[item.type] ?? Bell;
                return (
                  <li key={item.id}>
                    <button className={cn("notification-item", !item.read_at && "unread")} onClick={() => openItem(item)}>
                      <span className="notification-icon"><Icon size={14} /></span>
                      <span className="notification-copy">
                        <b>{item.title}</b>
                        {item.body && <span>{item.body}</span>}
                        <small>{timeAgo(item.created_at)}</small>
                      </span>
                      {!item.read_at && <span className="notification-unread-dot" aria-label="Unread" />}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
