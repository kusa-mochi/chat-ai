import type { Metadata } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'Story Chat AI',
  description: '対話で物語を紡ぐAIチャットシステム'
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>{children}</body>
    </html>
  );
}
