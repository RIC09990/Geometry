import type { Metadata } from "next";
import "./globals.css";
import {LanguageProvider} from '@/lib/i18n';
import {AiCredentialsProvider} from '@/lib/ai-credentials';
import {AiChatSessionProvider} from '@/lib/ai-chat-state';

export const metadata: Metadata = {
  title: "Geometry · 几何证明探究",
  description: "改变一个条件，重新理解一条证明。创建图形、追踪推理、核验反例。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="antialiased"><LanguageProvider><AiCredentialsProvider><AiChatSessionProvider>{children}</AiChatSessionProvider></AiCredentialsProvider></LanguageProvider></body>
    </html>
  );
}
