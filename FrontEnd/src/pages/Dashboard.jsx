import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Navbar from "../components/Navbar";

function StatusBadge({ hasAlerts }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`w-2.5 h-2.5 rounded-full ${
          hasAlerts ? "bg-amber-400 animate-pulse" : "bg-emerald-400 animate-pulse"
        }`}
      />
      <span className={`text-sm font-medium ${hasAlerts ? "text-amber-300" : "text-emerald-300"}`}>
        {hasAlerts ? "Alert Detected" : "Monitoring Active"}
      </span>
    </div>
  );
}

function AlertRow({ alert }) {
  const date = new Date(alert.timestamp);
  return (
    <div className="flex items-start justify-between py-4 border-b border-white/10 last:border-0">
      <div className="flex items-start gap-4">
        {/* Icon */}
        <div className="w-9 h-9 rounded-full bg-tan/10 border border-tan/20 flex items-center justify-center flex-shrink-0 mt-0.5">
          <svg className="w-4 h-4 text-tan" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
        </div>
        <div>
          <p className="text-white text-sm font-medium">Emergency Alert Triggered</p>
          <p className="text-white/40 text-xs mt-0.5">
            Call ID: {alert.call_id || "N/A"} · {alert.has_video ? "Video captured" : "No video"}
          </p>
        </div>
      </div>
      <div className="text-right flex-shrink-0 ml-4">
        <p className="text-white/50 text-xs">{date.toLocaleDateString()}</p>
        <p className="text-white/30 text-xs">{date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</p>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { user, alerts, signout, refreshUser } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    refreshUser();
  }, []);

  const handleSignout = () => {
    signout();
    navigate("/");
  };

  if (!user) return null;

  return (
    <div className="min-h-screen bg-slate-blue">
      <Navbar />

      <main className="max-w-4xl mx-auto pt-28 pb-16 px-6">
        {/* Header */}
        <div className="mb-10">
          <p className="text-tan/60 text-xs tracking-[0.3em] uppercase mb-3">Dashboard</p>
          <h1
            className="text-4xl text-white"
            style={{ fontFamily: "Playfair Display, Georgia, serif" }}
          >
            Welcome, {user.name.split(" ")[0]}.
          </h1>
        </div>

        <div className="grid md:grid-cols-2 gap-5 mb-8">
          {/* Status Card */}
          <div className="card">
            <p className="text-white/40 text-xs tracking-widest uppercase mb-4">System Status</p>
            <StatusBadge hasAlerts={alerts.length > 0} />
            <p className="text-white/30 text-xs mt-3 leading-relaxed">
              {alerts.length > 0
                ? `${alerts.length} alert${alerts.length > 1 ? "s" : ""} on record. See the log below.`
                : "All clear. The system is actively monitoring and no emergencies have been detected."}
            </p>
          </div>

          {/* Contact Card */}
          <div className="card">
            <p className="text-white/40 text-xs tracking-widest uppercase mb-4">Emergency Contact</p>
            <p className="text-tan text-2xl font-light tracking-wider mb-2">
              {user.phone_number}
            </p>
            <p className="text-white/30 text-xs leading-relaxed">
              This number will be called immediately when an emergency is detected.
            </p>
          </div>
        </div>

        {/* Account Info */}
        <div className="card mb-8">
          <p className="text-white/40 text-xs tracking-widest uppercase mb-5">Account</p>
          <div className="grid sm:grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-white/30 text-xs mb-1">Name</p>
              <p className="text-white">{user.name}</p>
            </div>
            <div>
              <p className="text-white/30 text-xs mb-1">Email</p>
              <p className="text-white">{user.email}</p>
            </div>
            <div>
              <p className="text-white/30 text-xs mb-1">Member Since</p>
              <p className="text-white">
                {new Date(user.created_at).toLocaleDateString(undefined, {
                  year: "numeric",
                  month: "long",
                  day: "numeric",
                })}
              </p>
            </div>
          </div>
        </div>

        {/* Alert Log */}
        <div className="card">
          <p className="text-white/40 text-xs tracking-widest uppercase mb-5">Alert History</p>

          {alerts.length === 0 ? (
            <div className="py-10 text-center">
              <div className="w-12 h-12 rounded-full bg-emerald-400/10 border border-emerald-400/20 flex items-center justify-center mx-auto mb-4">
                <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-white/40 text-sm">No alerts on record.</p>
              <p className="text-white/25 text-xs mt-1">Alerts will appear here when emergencies are detected.</p>
            </div>
          ) : (
            <div>
              {alerts.map((alert) => (
                <AlertRow key={alert.id} alert={alert} />
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
