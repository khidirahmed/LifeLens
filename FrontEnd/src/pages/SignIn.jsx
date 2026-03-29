import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Logo from "../components/Logo";

export default function SignIn() {
  const { signin } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => setForm((f) => ({ ...f, [e.target.name]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await signin(form.email, form.password);
      navigate("/dashboard");
    } catch (err) {
      setError(err.response?.data?.error || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-blue flex flex-col items-center justify-center px-4 py-16">
      {/* Top logo */}
      <Link to="/" className="mb-12">
        <Logo size={44} showText textClass="text-2xl" />
      </Link>

      <div className="w-full max-w-md">
        <div className="card">
          <h2
            className="text-2xl text-white mb-2"
            style={{ fontFamily: "Playfair Display, Georgia, serif" }}
          >
            Welcome back
          </h2>
          <p className="text-white/40 text-sm mb-8">Good to see you again.</p>

          {error && (
            <div className="bg-red-500/10 border border-red-400/30 text-red-300 text-sm px-4 py-3 rounded-sm mb-6">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-white/50 text-xs tracking-widest uppercase mb-2">
                Email
              </label>
              <input
                className="input-field"
                type="email"
                name="email"
                placeholder="you@example.com"
                value={form.email}
                onChange={handleChange}
                required
                autoComplete="email"
              />
            </div>

            <div>
              <label className="block text-white/50 text-xs tracking-widest uppercase mb-2">
                Password
              </label>
              <input
                className="input-field"
                type="password"
                name="password"
                placeholder="••••••••"
                value={form.password}
                onChange={handleChange}
                required
                autoComplete="current-password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>
        </div>

        <p className="text-center text-white/40 text-sm mt-6">
          Don't have an account?{" "}
          <Link to="/signup" className="text-tan hover:text-tan-dark transition-colors">
            Get Started
          </Link>
        </p>
      </div>
    </div>
  );
}
