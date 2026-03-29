import { createContext, useContext, useState, useEffect } from "react";
import api from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("ll_token");
    if (token) {
      api.get("/auth/me")
        .then(({ data }) => {
          setUser(data.user);
          setAlerts(data.alerts);
        })
        .catch(() => localStorage.removeItem("ll_token"))
        .finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const signin = async (email, password) => {
    const { data } = await api.post("/auth/signin", { email, password });
    localStorage.setItem("ll_token", data.access_token);
    setUser(data.user);
    setAlerts([]);
  };

  const signup = async (name, email, password, phone_number) => {
    const { data } = await api.post("/auth/signup", { name, email, password, phone_number });
    localStorage.setItem("ll_token", data.access_token);
    setUser(data.user);
    setAlerts([]);
  };

  const signout = () => {
    localStorage.removeItem("ll_token");
    setUser(null);
    setAlerts([]);
  };

  const refreshUser = async () => {
    const { data } = await api.get("/auth/me");
    setUser(data.user);
    setAlerts(data.alerts);
  };

  return (
    <AuthContext.Provider value={{ user, alerts, loading, signin, signup, signout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
