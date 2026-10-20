export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: { colors: { bg: "var(--bg)", surface: "var(--surface)", raised: "var(--surface-raised)",
    text: "var(--text)", muted: "var(--muted)", accent: "var(--accent)", danger: "var(--danger)" },
    borderRadius: { card: "14px" } } },
};
