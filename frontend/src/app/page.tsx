'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { createStory, listStories } from '../lib/api';
import { StorySummary } from '../lib/types';

export default function HomePage() {
  const router = useRouter();
  const [stories, setStories] = useState<StorySummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await listStories();
        setStories(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : '物語一覧の取得に失敗しました');
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, []);

  const sortedStories = useMemo(
    () => [...stories].sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()),
    [stories]
  );

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const created = await createStory();
      router.push(`/stories/${created.story.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : '新しい物語の作成に失敗しました');
    } finally {
      setCreating(false);
    }
  };

  return (
    <main className="landing-shell">
      <section className="landing-header">
        <p className="overline">Dialogue-Driven Fiction Forge</p>
        <h1>Story Chat AI</h1>
        <p>
          日本語の自然文を送るだけで、AIがもう一人の登場人物とナレーションを担当し、物語を継続します。
          設定調整、巻き戻し、挿絵生成にも対応しています。
        </p>
        <button className="primary-btn" onClick={handleCreate} disabled={creating}>
          {creating ? '作成中...' : '新しい物語'}
        </button>
      </section>

      <section className="stories-panel">
        <h2>保存済みの物語</h2>
        {loading && <p>読み込み中...</p>}
        {error && <p className="error-text">{error}</p>}
        {!loading && sortedStories.length === 0 && <p>まだ物語はありません。上のボタンから始めてください。</p>}
        <ul className="stories-grid">
          {sortedStories.map((story) => (
            <li key={story.id}>
              <Link href={`/stories/${story.id}`} className="story-card">
                <strong>{story.title}</strong>
                <span>更新: {new Date(story.updated_at).toLocaleString('ja-JP')}</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
