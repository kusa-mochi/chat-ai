"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { createStory, listStories } from "../lib/api";
import type { Story } from "../lib/types";


export default function HomePage() {
  const [stories, setStories] = useState<Story[]>([]);
  const [title, setTitle] = useState("真夜中の港町");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const items = await listStories();
      setStories(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "取得に失敗しました");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function onCreateStory(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      const created = await createStory(title.trim() || "新しい物語");
      window.location.href = `/stories/${created.id}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "作成に失敗しました");
    }
  }

  return (
    <main className="shell" style={{ maxWidth: 1080, margin: "0 auto" }}>
      <section className="card" style={{ padding: 24, marginBottom: 16 }}>
        <h1 style={{ marginTop: 0 }}>Story Chat AI</h1>
        <p className="muted" style={{ marginTop: 6 }}>
          日本語で物語を紡ぐローカルLLM環境。新しい物語を作成して、チャット形式で物語を進められます。
        </p>

        <form onSubmit={onCreateStory} style={{ display: "flex", gap: 10, marginTop: 18 }}>
          <input
            className="field"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="物語タイトル"
          />
          <button className="btn primary" type="submit">
            新しい物語
          </button>
        </form>

        {error ? <p style={{ color: "#8f1f10" }}>{error}</p> : null}
      </section>

      <section className="card" style={{ padding: 18 }}>
        <h2 style={{ marginTop: 0 }}>保存済みの物語</h2>
        {loading ? <p className="muted">読み込み中...</p> : null}
        {!loading && stories.length === 0 ? <p className="muted">まだ物語がありません。</p> : null}

        <div style={{ display: "grid", gap: 10 }}>
          {stories.map((story) => (
            <Link key={story.id} href={`/stories/${story.id}`} className="card" style={{ padding: 14 }}>
              <strong>{story.title}</strong>
              <p className="muted" style={{ marginBottom: 0 }}>
                モデル: {story.llm_model}
              </p>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
