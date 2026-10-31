import { useEffect, useState } from "react";
import { MESSAGES_CHANGED_EVENT, messageService } from "../../services/messages";

const POLL_MS = 30_000;

/** Total unread chat messages for the sidebar badge. Polls while the tab is visible, and refreshes
 *  immediately when the Messages page reads or sends something. Fails quietly (badge just hides),
 *  e.g. before phase3c_course_messages.sql is applied. */
export function useUnreadMessages(enabled: boolean): number {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setUnread(0);
      return;
    }
    let active = true;
    // 503 = messaging isn't set up on the server (migration not applied): stop asking until reload,
    // instead of failing a request every 30 s on every page.
    let unavailable = false;
    const load = () => {
      if (unavailable || document.visibilityState !== "visible") return;
      messageService
        .listThreads()
        .then((threads) => active && setUnread(threads.reduce((sum, t) => sum + t.unread_count, 0)))
        .catch((error: { response?: { status?: number } }) => {
          if (error?.response?.status === 503) unavailable = true;
        });
    };
    load();
    const timer = window.setInterval(load, POLL_MS);
    window.addEventListener(MESSAGES_CHANGED_EVENT, load);
    document.addEventListener("visibilitychange", load);
    return () => {
      active = false;
      window.clearInterval(timer);
      window.removeEventListener(MESSAGES_CHANGED_EVENT, load);
      document.removeEventListener("visibilitychange", load);
    };
  }, [enabled]);

  return unread;
}
