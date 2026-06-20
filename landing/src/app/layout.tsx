import type { Metadata } from "next";

import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "个人知识 Agent",
  description: "面向个人资料沉淀、知识工作区管理与结构化产物交互的知识工作流系统。",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "64x64" },
      { url: "/icon.png", type: "image/png", sizes: "64x64" },
    ],
    shortcut: "/favicon.ico",
    apple: "/apple-icon.png",
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" className="dark" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
