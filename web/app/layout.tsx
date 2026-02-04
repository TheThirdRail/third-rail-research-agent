import type { Metadata } from "next";
import { Orbitron, Fira_Code } from "next/font/google";
import "./globals.css";

const orbitron = Orbitron({
  variable: "--font-orbitron",
  subsets: ["latin"],
  display: "swap",
});

const firaCode = Fira_Code({
  variable: "--font-fira-code",
  subsets: ["latin"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Research Agent | Multi-Agent Orchestration",
  description: "AI-powered news research and political bias analysis",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body
        className={`${orbitron.variable} ${firaCode.variable} antialiased bg-background text-foreground font-mono`}
      >
        {children}
      </body>
    </html>
  );
}
