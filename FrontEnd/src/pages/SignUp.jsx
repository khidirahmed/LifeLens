import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Logo from "../components/Logo";

export default function SignUp() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone_number: "",
    password: "",
    confirm_password: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleChange = (e) => setForm((f) => ({ ...f, [e.target.name]: e.target.value }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    if (form.password !== form.confirm_password) {
      setError("Passwords do not match.");
      return;
    }
    if (!form.phone_number.startsWith("+")) {
      setError("Phone number must include country code (e.g. +12125551234).");
      return;
    }

    setLoading(true);
    try {
      await signup(form.name, form.email, form.password, form.phone_number);
      navigate("/dashboard");
    } catch (err) {
      setError(err.response?.data?.error || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-blue flex flex-col items-center justify-center px-4 py-16">
      <Link to="/" className="mb-12">
        <Logo size={44} showText textClass="text-2xl" />
      </Link>

      <div className="w-full max-w-md">
        <div className="card">
          <h2
            className="text-2xl text-white mb-2"
            style={{ fontFamily: "Playfair Display, Georgia, serif" }}
          >
            Create your account
          </h2>
          <p className="text-white/40 text-sm mb-8">
            Your phone number will be called if an emergency is detected.
          </p>

          {error && (
            <div className="bg-red-500/10 border border-red-400/30 text-red-300 text-sm px-4 py-3 rounded-sm mb-6">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block text-white/50 text-xs tracking-widest uppercase mb-2">
                Full Name
              </label>
              <input
                className="input-field"
                type="text"
                name="name"
                placeholder="Jane Smith"
                value={form.name}
                onChange={handleChange}
                required
                autoComplete="name"
              />
            </div>

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
                Emergency Contact Phone
              </label>
              <input
                className="input-field"
                type="tel"
                name="phone_number"
                placeholder="+12125551234"
                value={form.phone_number}
                onChange={handleChange}
                required
                autoComplete="tel"
              />
              <p className="text-white/30 text-xs mt-1.5">
                Include country code. This number will be called in an emergency.
              </p>
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
                autoComplete="new-password"
              />
            </div>

            <div>
              <label className="block text-white/50 text-xs tracking-widest uppercase mb-2">
                Confirm Password
              </label>
              <input
                className="input-field"
                type="password"
                name="confirm_password"
                placeholder="••••••••"
                value={form.confirm_password}
                onChange={handleChange}
                required
                autoComplete="new-password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? "Creating account..." : "Create Account"}
            </button>
          </form>
        </div>

        <p className="text-center text-white/40 text-sm mt-6">
          Already have an account?{" "}
          <Link to="/signin" className="text-tan hover:text-tan-dark transition-colors">
            Sign In
          </Link>
        </p>
      </div>
    </div>
  );
}
