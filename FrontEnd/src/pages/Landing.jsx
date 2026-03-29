import { Link } from "react-router-dom";
import Navbar from "../components/Navbar";
import Logo from "../components/Logo";

const features = [
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
    title: "Private by design",
    body: "Footage never leaves the device. Analysis happens locally on the GX10 server, and if everything looks fine, the footage is deleted immediately.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M13 10V3L4 14h7v7l9-11h-7z" />
      </svg>
    ),
    title: "Instant notification",
    body: "The moment something concerning is detected, your phone rings. Not a push notification. A real call, so you can respond right away.",
  },
  {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
      </svg>
    ),
    title: "Built for families",
    body: "Seniors keep their independence. Families get peace of mind. It's not about surveillance. It's about being there when it matters most.",
  },
];

export default function Landing() {
  return (
    <div className="min-h-screen bg-slate-blue text-white">
      <Navbar transparent />

      {/* Hero */}
      <section className="relative min-h-screen flex flex-col items-center justify-center text-center px-6 overflow-hidden">
        {/* Soft glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse 80% 70% at 50% 45%, rgba(196,168,130,0.08) 0%, transparent 65%)",
          }}
        />

        <div className="relative max-w-2xl mx-auto">
          <p className="text-tan/50 text-xs tracking-[0.35em] uppercase mb-10 font-sans">
            Senior Safety, Reimagined
          </p>

          <h1
            className="text-5xl md:text-6xl lg:text-7xl leading-[1.1] mb-7"
            style={{ fontFamily: "Playfair Display, Georgia, serif" }}
          >
            Their freedom.
            <br />
            <em className="not-italic text-tan">Your peace of mind.</em>
          </h1>

          <p className="text-white/55 text-lg leading-relaxed mb-12 max-w-lg mx-auto">
            For the seniors you love.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link to="/signup" className="btn-primary">
              Get Started
            </Link>
            <a href="#about" className="btn-ghost">
              Learn More
            </a>
          </div>
        </div>

        {/* Scroll cue */}
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 opacity-25">
          <div className="w-5 h-8 rounded-full border border-white flex items-start justify-center pt-1.5">
            <div className="w-1 h-2 bg-white rounded-full animate-bounce" />
          </div>
        </div>
      </section>

      {/* About */}
      <section id="about" className="py-32 px-6 bg-slate-deeper">
        <div className="max-w-5xl mx-auto">
          <div className="grid md:grid-cols-2 gap-20 items-center mb-24">
            {/* Logo mark */}
            <div className="flex justify-center">
              <div className="relative">
                <div
                  className="absolute inset-0 rounded-full blur-3xl opacity-20"
                  style={{ background: "#c4a882" }}
                />
                <Logo size={220} showText={false} />
              </div>
            </div>

            {/* Copy */}
            <div>
              <p className="text-tan/50 text-xs tracking-[0.3em] uppercase mb-5">How it works</p>
              <h2
                className="text-3xl md:text-4xl leading-snug mb-6"
                style={{ fontFamily: "Playfair Display, Georgia, serif" }}
              >
                Safety without the trade-off.
              </h2>
              <p className="text-white/55 leading-relaxed mb-5">
                LifeLens uses emerging AI technology to passively watch over seniors throughout
                their day. The glasses stream footage to a local server in the home. No internet.
                No cloud. Nothing leaves.
              </p>
              <p className="text-white/55 leading-relaxed mb-8">
                If everything looks fine, the footage is deleted on the spot. If something
                concerning is detected, your phone rings within seconds. That's it.
              </p>

              <div className="w-10 h-px bg-tan/30 mb-8" />

              <div className="flex flex-wrap gap-2">
                {["On-Device AI", "No Cloud", "Instant Calls", "Always On"].map((tag) => (
                  <span
                    key={tag}
                    className="text-xs text-tan/70 border border-tan/20 rounded-full px-4 py-1.5 tracking-wide"
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Feature cards */}
          <div className="grid md:grid-cols-3 gap-6">
            {features.map((f) => (
              <div key={f.title} className="card group hover:border-tan/30 transition-colors duration-300">
                <div className="w-10 h-10 rounded-full bg-tan/10 flex items-center justify-center text-tan mb-5 group-hover:bg-tan/15 transition-colors duration-300">
                  {f.icon}
                </div>
                <h3
                  className="text-white text-lg mb-3"
                  style={{ fontFamily: "Playfair Display, Georgia, serif" }}
                >
                  {f.title}
                </h3>
                <p className="text-white/45 text-sm leading-relaxed">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Quote / emotional pull */}
      <section className="py-28 px-6 text-center bg-slate-blue">
        <div className="max-w-2xl mx-auto">
          <div className="flex justify-center mb-8">
            <Logo size={52} showText={false} />
          </div>
          <blockquote
            className="text-2xl md:text-3xl text-white/80 leading-relaxed mb-10"
            style={{ fontFamily: "Playfair Display, Georgia, serif" }}
          >
            "No cloud. No storage. No privacy trade-off. Just care, when it counts."
          </blockquote>
          <Link to="/signup" className="btn-primary inline-block">
            Create Your Account
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-slate-deeper border-t border-white/10 py-10 px-8">
        <div className="max-w-5xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <Logo size={30} showText textClass="text-base" />
          <p className="text-white/25 text-xs tracking-wide text-center">
            Private. Local. Always watching over them.
          </p>
          <p className="text-white/25 text-xs">
            {new Date().getFullYear()} LifeLens
          </p>
        </div>
      </footer>
    </div>
  );
}
