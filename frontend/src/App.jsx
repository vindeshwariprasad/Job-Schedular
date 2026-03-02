import { Toaster } from "react-hot-toast";
import { useLocation } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { useTheme } from "./context/ThemeContext";
import AppLayout from "./layout/AppLayout";
import AppRoutes from "./routes";

const publicPaths = ["/login", "/register"];

function AppContent() {
  const location = useLocation();
  const pathname = location.pathname.replace(/\/+$/, "") || "/";
  const isPublic = publicPaths.includes(pathname);

  if (isPublic) {
    return <AppRoutes />;
  }

  return (
    <AppLayout>
      <AppRoutes />
    </AppLayout>
  );
}

function App() {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  return (
    <AuthProvider>
      <Toaster
        position="top-right"
        toastOptions={{
          duration: 4000,
          style: {
            borderRadius: "12px",
            background: isDark ? "#1f2937" : "#ffffff",
            color: isDark ? "#f9fafb" : "#111827",
            fontSize: "14px",
            padding: "12px 16px",
            boxShadow: isDark
              ? "0 10px 25px -5px rgba(0,0,0,0.4)"
              : "0 10px 25px -5px rgba(0,0,0,0.1)",
            border: isDark ? "1px solid #374151" : "1px solid #e5e7eb",
          },
          success: {
            iconTheme: { primary: "#22c55e", secondary: isDark ? "#f9fafb" : "#ffffff" },
          },
          error: {
            iconTheme: { primary: "#ef4444", secondary: isDark ? "#f9fafb" : "#ffffff" },
            duration: 5000,
          },
        }}
      />
      <AppContent />
    </AuthProvider>
  );
}

export default App;
