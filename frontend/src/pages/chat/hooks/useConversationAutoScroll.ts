import { useLayoutEffect, useRef } from "react";

const AUTO_SCROLL_THRESHOLD_PX = 96;

export function useConversationAutoScroll(dependency: unknown) {
  const conversationRef = useRef<HTMLDivElement | null>(null);
  const shouldAutoScrollRef = useRef(true);

  useLayoutEffect(() => {
    if (!conversationRef.current || !shouldAutoScrollRef.current) {
      return;
    }

    const frameId = window.requestAnimationFrame(() => {
      if (!conversationRef.current) {
        return;
      }

      conversationRef.current.scrollTop = conversationRef.current.scrollHeight;
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [dependency]);

  const handleConversationScroll = () => {
    if (!conversationRef.current) {
      return;
    }

    const { scrollHeight, scrollTop, clientHeight } = conversationRef.current;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX;
  };

  const enableAutoScroll = () => {
    shouldAutoScrollRef.current = true;
  };

  return {
    conversationRef,
    handleConversationScroll,
    enableAutoScroll,
  };
}

