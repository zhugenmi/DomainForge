import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DomainForge — 领域智能体控制台",
  description: "面向垂直领域的企业级 Agent 平台",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="h-full overflow-hidden atmosphere">
        {children}
      </body>
    </html>
  );
}
