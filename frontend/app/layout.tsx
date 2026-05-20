import type { Metadata } from "next";
import { Noto_Sans_JP } from "next/font/google";

import "./globals.css";


const jp = Noto_Sans_JP({
  subsets: ["latin"],
  weight: ["400", "700"],
});


export const metadata: Metadata = {
  title: "Story Chat AI",
  description: "ローカルLLMで遊ぶ物語チャット",
};


export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className={jp.className}>{children}</body>
    </html>
  );
}
