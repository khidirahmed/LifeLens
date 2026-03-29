export default function Logo({ size = 40, showText = true, textClass = "" }) {
  return (
    <div className="flex items-center gap-3">
      <img
        src="/logo.png"
        alt="LifeLens"
        width={size}
        height={size}
        style={{ width: size, height: size, objectFit: "contain" }}
      />
      {showText && (
        <span
          className={`text-tan tracking-wide font-semibold ${textClass}`}
          style={{ fontFamily: "Playfair Display, Georgia, serif" }}
        >
          LifeLens
        </span>
      )}
    </div>
  );
}
