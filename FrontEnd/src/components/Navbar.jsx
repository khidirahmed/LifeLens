import { Link, useNavigate } from "react-router-dom";
import Logo from "./Logo";
import { useAuth } from "../context/AuthContext";

export default function Navbar({ transparent = false }) {
  const { user, signout } = useAuth();
  const navigate = useNavigate();

  const handleSignout = () => {
    signout();
    navigate("/");
  };

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 px-8 py-5 flex items-center justify-between transition-colors duration-300 ${
        transparent ? "bg-transparent" : "bg-slate-deeper/90 backdrop-blur-sm border-b border-white/10"
      }`}
    >
      <Link to="/">
        <Logo size={36} showText textClass="text-xl" />
      </Link>

      <div className="flex items-center gap-8">
        <a
          href="#about"
          className="text-white/70 hover:text-tan text-sm tracking-widest uppercase transition-colors duration-200"
        >
          About
        </a>

        {user ? (
          <div className="flex items-center gap-6">
            <Link
              to="/dashboard"
              className="text-white/70 hover:text-tan text-sm tracking-widest uppercase transition-colors duration-200"
            >
              Dashboard
            </Link>
            <button onClick={handleSignout} className="btn-ghost text-xs px-5 py-2">
              Sign Out
            </button>
          </div>
        ) : (
          <Link to="/signin" className="btn-primary text-xs px-6 py-2.5">
            Sign In / Get Started
          </Link>
        )}
      </div>
    </nav>
  );
}
