import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

// Shared axios instance that attaches the JWT token to every request
export const api = axios.create({
  baseURL: API,
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 401 interceptor: clear auth state on expired/invalid tokens
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("token");
      localStorage.removeItem("user");
      // Redirect to login if not already there
      if (window.location.pathname !== "/login" && window.location.pathname !== "/register") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export const register = (username, email, password) =>
  api.post("/auth/register", { username, email, password }).then((res) => res.data);

export const login = (username, password) =>
  api.post("/auth/login", { username, password }).then((res) => res.data);

export const getMe = () => api.get("/auth/me").then((res) => res.data);
