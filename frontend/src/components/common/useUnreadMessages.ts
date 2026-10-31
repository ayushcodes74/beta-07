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
    const load = () => {
      if (document.visibilityState !== "visible") return;
      messageService
        .listThreads()
        .then((threads) => active && setUnread(threads.reduce((sum, t) => sum + t.unread_count, 0)))
        .catch(() => undefined);
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
