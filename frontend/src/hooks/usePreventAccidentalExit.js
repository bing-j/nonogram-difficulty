import { useCallback, useEffect, useRef } from "react";

const LEAVE_MESSAGE = "You have unsaved progress. Are you sure you want to leave this page?";

export default function usePreventAccidentalExit(shouldPrevent) {
  const allowNavigationRef = useRef(false);

  const allowNextNavigation = useCallback(() => {
    allowNavigationRef.current = true;
  }, []);

  useEffect(() => {
    if (!shouldPrevent || typeof window === "undefined") return;

    const handleBeforeUnload = (event) => {
      if (allowNavigationRef.current) return;
      event.preventDefault();
      event.returnValue = "";
    };

    const handlePopState = () => {
      if (allowNavigationRef.current) return;

      const shouldLeave = window.confirm(LEAVE_MESSAGE);
      if (shouldLeave) {
        allowNavigationRef.current = true;
        window.removeEventListener("beforeunload", handleBeforeUnload);
        window.removeEventListener("popstate", handlePopState);
        window.history.back();
        return;
      }

      window.history.pushState({ nonogramExitGuard: true }, "", window.location.href);
    };

    window.history.pushState({ nonogramExitGuard: true }, "", window.location.href);
    window.addEventListener("beforeunload", handleBeforeUnload);
    window.addEventListener("popstate", handlePopState);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      window.removeEventListener("popstate", handlePopState);
    };
  }, [shouldPrevent]);

  return { allowNextNavigation };
}
