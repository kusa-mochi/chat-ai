/** @jsxImportSource @emotion/react */
"use client";

import { css } from "@emotion/react";
import styled from "@emotion/styled";
import Link from "next/link";
import { useEffect, useState } from "react";

import { createStory, listStories } from "../lib/api";
import type { Story } from "../lib/types";

const shellStyle = css({
  maxWidth: 1080,
  margin: "0 auto",
  minHeight: "100vh",
  padding: 28,
  "@media (max-width: 900px)": {
    padding: 14,
  },
});

const cardStyle = css({
  border: "1px solid var(--line)",
  background: "var(--panel)",
  borderRadius: 18,
  backdropFilter: "blur(6px)",
});

const mutedStyle = css({
  color: "var(--ink-soft)",
});

const sectionHeadStyle = css({
  padding: 24,
  marginBottom: 16,
});

const headingStyle = css({
  marginTop: 0,
});

const introStyle = css({
  marginTop: 6,
});

const createFormStyle = css({
  display: "flex",
  gap: 10,
  marginTop: 18,
});

const fieldStyle = css({
  width: "100%",
  border: "1px solid var(--line)",
  borderRadius: 10,
  padding: "10px 12px",
  background: "#fff",
  color: "var(--ink)",
});

const buttonBaseStyle = css({
  border: "1px solid var(--line)",
  background: "#fff9",
  color: "var(--ink)",
  borderRadius: 12,
  padding: "10px 14px",
  cursor: "pointer",
  fontWeight: 700,
});

const primaryButtonStyle = css({
  background: "var(--accent)",
  color: "#fff",
  borderColor: "transparent",
});

const errorStyle = css({
  color: "#8f1f10",
});

const sectionBodyStyle = css({
  padding: 18,
});

const listGridStyle = css({
  display: "grid",
  gap: 10,
});

const storyLinkStyle = css({
  padding: 14,
  display: "block",
});

const storyMetaStyle = css({
  marginBottom: 0,
});

const PrimaryButton = styled.button(buttonBaseStyle, primaryButtonStyle);

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
    <main css={shellStyle}>
      <section css={[cardStyle, sectionHeadStyle]}>
        <h1 css={headingStyle}>Story Chat AI</h1>
        <p css={[mutedStyle, introStyle]}>
          日本語で物語を紡ぐローカルLLM環境。新しい物語を作成して、チャット形式で物語を進められます。
        </p>

        <form onSubmit={onCreateStory} css={createFormStyle}>
          <input
            css={fieldStyle}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="物語タイトル"
          />
          <PrimaryButton type="submit">新しい物語</PrimaryButton>
        </form>

        {error ? <p css={errorStyle}>{error}</p> : null}
      </section>

      <section css={[cardStyle, sectionBodyStyle]}>
        <h2 css={headingStyle}>保存済みの物語</h2>
        {loading ? <p css={mutedStyle}>読み込み中...</p> : null}
        {!loading && stories.length === 0 ? <p css={mutedStyle}>まだ物語がありません。</p> : null}

        <div css={listGridStyle}>
          {stories.map((story) => (
            <Link key={story.id} href={`/stories/${story.id}`} css={[cardStyle, storyLinkStyle]}>
              <strong>{story.title}</strong>
              <p css={[mutedStyle, storyMetaStyle]}>モデル: {story.llm_model}</p>
            </Link>
          ))}
        </div>
      </section>
    </main>
  );
}
