import { describe, it, expect, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useExecutionWebSocket } from "../../hooks/useExecutionWebSocket";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe("useExecutionWebSocket", () => {
  beforeEach(() => {
    localStorage.clear();
    WebSocket.instances = [];
  });

  it("returns disconnected when no token", () => {
    const { result } = renderHook(() => useExecutionWebSocket(), {
      wrapper: createWrapper(),
    });
    // No token = no connection attempt, stays disconnected
    expect(result.current).toBe("disconnected");
  });

  it("attempts connection when token exists", async () => {
    localStorage.setItem("token", "test-token");

    renderHook(() => useExecutionWebSocket(), {
      wrapper: createWrapper(),
    });

    // Should have created a WebSocket instance
    await waitFor(() => {
      expect(WebSocket.instances.length).toBeGreaterThan(0);
    });
  });

  it("transitions to connected after websocket opens", async () => {
    localStorage.setItem("token", "test-token");

    const { result } = renderHook(() => useExecutionWebSocket(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current).toBe("connected");
    });
  });

  it("builds correct WebSocket URL with token", async () => {
    localStorage.setItem("token", "my-jwt-token");

    renderHook(() => useExecutionWebSocket(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(WebSocket.instances.length).toBeGreaterThan(0);
    });

    const wsUrl = WebSocket.instances[0].url;
    expect(wsUrl).toContain("/ws/executions");
    expect(wsUrl).toContain("token=my-jwt-token");
  });
});
