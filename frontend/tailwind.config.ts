import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        dispatch: {
          bg: "#0f1419",
          surface: "#1a2332",
          border: "#2d3a4d",
          muted: "#64748b",
          accent: "#3b82f6",
          delayed: "#f59e0b",
          conflict: "#ef4444",
        },
      },
    },
  },
  plugins: [],
};

export default config;
