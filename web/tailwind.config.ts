import type { Config } from "tailwindcss";

const config: Config = {
    content: [
        "./pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./components/**/*.{js,ts,jsx,tsx,mdx}",
        "./app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                "neon-cyan": "#00f3ff",
                "neon-purple": "#bd00ff",
                "hot-pink": "#ff0099",
                "terminal-green": "#0aff00",
                "midnight-purple": "#261447",
                "void": "#050014",
                "background": "#0d0221",
                "foreground": "#e0e0e0",
            },
            fontFamily: {
                orbitron: ["var(--font-orbitron)", "ui-sans-serif", "system-ui", "sans-serif"],
                "fira-code": ["var(--font-fira-code)", "ui-monospace", "monospace"],
                mono: ["var(--font-fira-code)", "ui-monospace", "monospace"],
            },
        },
    },
    plugins: [
        require('@tailwindcss/typography'),
    ],
} satisfies Config;

export default config;
