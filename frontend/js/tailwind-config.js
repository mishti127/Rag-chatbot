/* Tailwind CDN config — preflight off to preserve existing forms/buttons */
tailwind.config = {
  corePlugins: { preflight: false },
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "Plus Jakarta Sans", "system-ui", "sans-serif"],
        display: ["Plus Jakarta Sans", "Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        glow: "0 0 60px rgba(139, 92, 246, 0.12), 0 0 120px rgba(99, 102, 241, 0.08)",
        "glow-sm": "0 0 24px rgba(167, 139, 250, 0.2)",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      animation: {
        "fade-in": "ragFadeIn 0.35s ease-out forwards",
        "float": "ragFloat 6s ease-in-out infinite",
      },
      keyframes: {
        ragFadeIn: {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        ragFloat: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-6px)" },
        },
      },
    },
  },
};
