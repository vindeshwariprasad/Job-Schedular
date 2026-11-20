import { useEffect, useRef, useState, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

const MAX_RECONNECT_ATTEMPTS = 10;

export function useExecutionWebSocket() {
  const [status, setStatus] = useState("disconnected"); // "connected" | "connecting" | "disconnected"
  const wsRef = useRef(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const connectRef = useRef(null);
  const queryClient = useQueryClient();

  const attemptReconnect = useCallback(() => {
    if (reconnectCountRef.current >= MAX_RECONNECT_ATTEMPTS) return;

    const delay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 30000);
    reconnectCountRef.current += 1;

    reconnectTimerRef.current = setTimeout(() => {
      connectRef.current?.();
    }, delay);
  }, []);

  const connect = useCallback(() => {
    const token = localStorage.getItem("token");
    if (!token) return;

    setStatus("connecting");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const wsUrl = `${protocol}//${host}/ws/executions?token=${encodeURIComponent(token)}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setStatus("connected");
      reconnectCountRef.current = 0;
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (message.type === "execution_update") {
          // Invalidate relevant queries so TanStack Query refetches fresh data
          queryClient.invalidateQueries({ queryKey: ["executions"] });
          queryClient.invalidateQueries({ queryKey: ["user-stats"] });
          queryClient.invalidateQueries({ queryKey: ["metrics"] });
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setStatus("disconnected");
      wsRef.current = null;
      attemptReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [queryClient, attemptReconnect]);

  // Keep connectRef in sync so attemptReconnect can call the latest connect
  useEffect(() => {
    connectRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect(); // eslint-disable-line react-hooks/set-state-in-effect -- WebSocket setup legitimately sets state via callbacks

    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  return status;
}
