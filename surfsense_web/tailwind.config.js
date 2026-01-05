/** @type {import('tailwindcss').Config} */
module.exports = {
	darkMode: ["class"],
	content: [
		"./pages/**/*.{ts,tsx}",
		"./components/**/*.{ts,tsx}",
		"./app/**/*.{ts,tsx}",
		"./src/**/*.{ts,tsx}",
	],
	theme: {
		container: {
			center: true,
			padding: "2rem",
			screens: {
				"2xl": "1400px",
			},
		},
		extend: {
			colors: {
				border: "var(--border)",
				input: "var(--input)",
				ring: "var(--ring)",
				background: "var(--background)",
				foreground: "var(--foreground)",
				primary: {
					DEFAULT: "var(--primary)",
					foreground: "var(--primary-foreground)",
				},
				secondary: {
					DEFAULT: "var(--secondary)",
					foreground: "var(--secondary-foreground)",
				},
				destructive: {
					DEFAULT: "var(--destructive)",
					foreground: "var(--destructive-foreground)",
				},
				muted: {
					DEFAULT: "var(--muted)",
					foreground: "var(--muted-foreground)",
				},
				accent: {
					DEFAULT: "var(--accent)",
					foreground: "var(--accent-foreground)",
				},
				popover: {
					DEFAULT: "var(--popover)",
					foreground: "var(--popover-foreground)",
				},
				card: {
					DEFAULT: "var(--card)",
					foreground: "var(--card-foreground)",
				},
				// M3 Colors
				"md-primary": "var(--md-sys-color-primary)",
				"md-on-primary": "var(--md-sys-color-on-primary)",
				"md-primary-container": "var(--md-sys-color-primary-container)",
				"md-on-primary-container": "var(--md-sys-color-on-primary-container)",
				"md-secondary": "var(--md-sys-color-secondary)",
				"md-on-secondary": "var(--md-sys-color-on-secondary)",
				"md-secondary-container": "var(--md-sys-color-secondary-container)",
				"md-on-secondary-container": "var(--md-sys-color-on-secondary-container)",
				"md-tertiary": "var(--md-sys-color-tertiary)",
				"md-on-tertiary": "var(--md-sys-color-on-tertiary)",
				"md-tertiary-container": "var(--md-sys-color-tertiary-container)",
				"md-on-tertiary-container": "var(--md-sys-color-on-tertiary-container)",
				"md-error": "var(--md-sys-color-error)",
				"md-on-error": "var(--md-sys-color-on-error)",
				"md-error-container": "var(--md-sys-color-error-container)",
				"md-on-error-container": "var(--md-sys-color-on-error-container)",
				"md-background": "var(--md-sys-color-background)",
				"md-on-background": "var(--md-sys-color-on-background)",
				"md-surface": "var(--md-sys-color-surface)",
				"md-on-surface": "var(--md-sys-color-on-surface)",
				"md-surface-variant": "var(--md-sys-color-surface-variant)",
				"md-on-surface-variant": "var(--md-sys-color-on-surface-variant)",
				"md-outline": "var(--md-sys-color-outline)",
				"md-outline-variant": "var(--md-sys-color-outline-variant)",
			},
			borderRadius: {
				lg: "var(--radius)",
				md: "calc(var(--radius) - 2px)",
				sm: "calc(var(--radius) - 4px)",
				xl: "calc(var(--radius) + 4px)",
				"2xl": "calc(var(--radius) + 8px)",
			},
			boxShadow: {
				"elevation-1": "var(--shadow-elevation-1)",
				"elevation-2": "var(--shadow-elevation-2)",
				"elevation-3": "var(--shadow-elevation-3)",
				"elevation-4": "var(--shadow-elevation-4)",
				"elevation-5": "var(--shadow-elevation-5)",
			},
			keyframes: {
				"accordion-down": {
					from: { height: 0 },
					to: { height: "var(--radix-accordion-content-height)" },
				},
				"accordion-up": {
					from: { height: "var(--radix-accordion-content-height)" },
					to: { height: 0 },
				},
				"progress-indeterminate": {
					"0%": { left: "-33%", width: "33%" },
					"50%": { width: "50%" },
					"100%": { left: "100%", width: "33%" },
				},
			},
			animation: {
				"accordion-down": "accordion-down 0.2s ease-out",
				"accordion-up": "accordion-up 0.2s ease-out",
				"progress-indeterminate": "progress-indeterminate 1.5s ease-in-out infinite",
			},
		},
	},
	plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
};
