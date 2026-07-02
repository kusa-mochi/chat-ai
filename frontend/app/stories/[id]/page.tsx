/** @jsxImportSource @emotion/react */
"use client";

import { css } from "@emotion/react";
import styled from "@emotion/styled";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  createIllustration,
  getIllustration,
  listBranches,
  getSettings,
  getStory,
  listMessages,
  rewindBranch,
  sendChatStream,
  updateSettings,
} from "../../../lib/api";
import type { BranchSummary, IllustrationJob, Message, Story, StorySettings } from "../../../lib/types";

type SelectionState = {
  text: string;
  messageId: string;
} | null;

const defaultSettings: StorySettings = {
  story_id: "",
  context_size: 4096,
  characters_text: "",
  temperature: 0.8,
  top_p: 0.8,
};

function messageTone(message: Message): string {
  if (message.role === "user") {
    return "#f4f2ff";
  }
  if (message.kind === "dialogue") {
    return "#fff6ea";
  }
  if (message.kind === "narration") {
    return "#e8f4ef";
  }
  return "#f5f5f5";
}

const BASE_SYSTEM_PROMPT_TOKENS = 320;
const HISTORY_WINDOW = 30;
const TURN_MARKER_PATTERN = /<\/?end_of_turn>|<start_of_turn>\s*(?:user|assistant|system|model)?/gi;
const ROLE_LINE_PATTERN = /^\s*(?:user|assistant|system|model)\s*$/gim;

function estimateTokensFromText(text: string): number {
  let score = 0;
  for (const char of text) {
    if (/\s/.test(char)) {
      continue;
    }
    if (/[A-Za-z0-9]/.test(char)) {
      score += 0.25;
      continue;
    }
    if (/[\u3040-\u30ff\u3400-\u9fff]/.test(char)) {
      score += 1;
      continue;
    }
    score += 0.5;
  }
  return Math.max(1, Math.ceil(score));
}

function estimateMessageTokens(message: Message): number {
  const roleOverhead = message.role === "assistant" ? 6 : 4;
  const kindOverhead = message.kind === "narration" ? 6 : 3;
  return roleOverhead + kindOverhead + estimateTokensFromText(message.content);
}

function stripSectionTags(text: string): string {
  const withoutTurnMarkers = text.replace(TURN_MARKER_PATTERN, "");
  const withoutRoleLines = withoutTurnMarkers.replace(ROLE_LINE_PATTERN, "");
  return withoutRoleLines.replace(/\n{3,}/g, "\n\n");
}

const shellStyle = css({
  maxWidth: 1300,
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

const headerStyle = css({
  padding: 16,
  marginBottom: 14,
});

const headerRowStyle = css({
  display: "flex",
  justifyContent: "space-between",
  gap: 12,
  flexWrap: "wrap",
});

const pageTitleStyle = css({
  margin: 0,
});

const noBottomMarginStyle = css({
  marginBottom: 0,
});

const rowActionsStyle = css({
  display: "flex",
  gap: 8,
});

const contentGridStyle = css({
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) minmax(260px, 340px)",
  gap: 14,
  "@media (max-width: 1100px)": {
    gridTemplateColumns: "1fr",
  },
});

const chatSectionStyle = css({
  padding: 12,
  minHeight: 680,
  display: "flex",
  flexDirection: "column",
});

const messageListStyle = css({
  flex: 1,
  overflowY: "auto",
  borderRadius: 12,
  padding: 10,
  border: "1px solid var(--line)",
  background: "#ffffff8a",
});

const centerRowStyle = css({
  display: "flex",
  justifyContent: "center",
  marginBottom: 10,
});

const buttonBaseStyle = css({
  border: "1px solid var(--line)",
  background: "#fff9",
  color: "var(--ink)",
  borderRadius: 12,
  padding: "10px 14px",
  cursor: "pointer",
  fontWeight: 700,
  fontFamily: "inherit",
  "&:disabled": {
    opacity: 0.6,
    cursor: "not-allowed",
  },
});

const primaryButtonStyle = css({
  background: "var(--accent)",
  color: "#fff",
  borderColor: "transparent",
});

const messageCardStyle = css({
  padding: 12,
  borderRadius: 10,
  marginBottom: 10,
  border: "1px solid var(--line)",
});

const messageHeaderStyle = css({
  display: "flex",
  justifyContent: "space-between",
  gap: 10,
});

const timestampStyle = css({
  fontSize: 12,
});

const messageBodyStyle = css({
  whiteSpace: "pre-wrap",
  marginBottom: 8,
});

const wrapRowStyle = css({
  display: "flex",
  gap: 8,
  flexWrap: "wrap",
});

const chatFormStyle = css({
  display: "grid",
  gap: 8,
  marginTop: 10,
});

const fieldStyle = css({
  width: "100%",
  border: "1px solid var(--line)",
  borderRadius: 10,
  padding: "10px 12px",
  background: "#fff",
  color: "var(--ink)",
  fontFamily: "inherit",
});

const chatFooterStyle = css({
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: 8,
});

const errorTextStyle = css({
  color: "#8f1f10",
});

const sidebarStyle = css({
  padding: 14,
  height: "fit-content",
});

const subHeadingStyle = css({
  marginTop: 0,
});

const branchListStyle = css({
  display: "grid",
  gap: 8,
  marginBottom: 14,
});

const branchButtonStyle = css({
  textAlign: "left",
});

const branchStatusStyle = css({
  fontSize: 12,
  opacity: 0.9,
});

const branchIdStyle = css({
  fontWeight: 700,
});

const branchMetaStyle = css({
  fontSize: 12,
});

const dividerStyle = css({
  margin: "16px 0",
  borderColor: "var(--line)",
});

const settingsFormStyle = css({
  display: "grid",
  gap: 8,
});

const usageCardStyle = css({
  border: "1px solid var(--line)",
  borderRadius: 10,
  padding: 10,
  background: "#ffffff85",
  display: "grid",
  gap: 6,
});

const usageHeaderStyle = css({
  display: "flex",
  justifyContent: "space-between",
  gap: 8,
  alignItems: "center",
});

const usageTitleStyle = css({
  fontSize: 13,
});

const usageToneStyle = css({
  fontSize: 12,
});

const usageBarTrackStyle = css({
  width: "100%",
  height: 10,
  borderRadius: 999,
  background: "#00000014",
  overflow: "hidden",
});

const usageStatsStyle = css({
  display: "flex",
  justifyContent: "space-between",
  gap: 8,
  flexWrap: "wrap",
  fontSize: 12,
});

const imageStyle = css({
  width: "100%",
  borderRadius: 8,
});

const TextField = styled.input(fieldStyle);
const TextAreaField = styled.textarea(fieldStyle);

export default function StoryPage({ params }: { params: { id: string } }) {
  const storyId = params.id;

  const [story, setStory] = useState<Story | null>(null);
  const [settings, setSettings] = useState<StorySettings>(defaultSettings);
  const [branchId, setBranchId] = useState("main");
  const [branches, setBranches] = useState<BranchSummary[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [hasMoreHistory, setHasMoreHistory] = useState(false);
  const [loadingMoreHistory, setLoadingMoreHistory] = useState(false);
  const [input, setInput] = useState("港の霧の中から、誰かがこちらを見ている。");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<SelectionState>(null);
  const [job, setJob] = useState<IllustrationJob | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);

  const refreshEverything = useCallback(
    async (forcedBranchId?: string) => {
      setError(null);
      try {
        const storyData = await getStory(storyId);
        const targetBranch = forcedBranchId ?? storyData.active_branch_id ?? "main";

        const [settingsData, messagePage, branchData] = await Promise.all([
          getSettings(storyId),
          listMessages(storyId, targetBranch, { limit: 40 }),
          listBranches(storyId),
        ]);

        setStory(storyData);
        setSettings(settingsData);
        setMessages(messagePage.items);
        setHasMoreHistory(messagePage.has_more);
        setBranchId(targetBranch);
        setBranches(branchData);
      } catch (err) {
        setError(err instanceof Error ? err.message : "読み込みに失敗しました");
      }
    },
    [storyId]
  );

  useEffect(() => {
    void refreshEverything();
  }, [refreshEverything]);

  useEffect(() => {
    if (!job) {
      return;
    }

    if (job.status === "done" || job.status === "error") {
      return;
    }

    const timer = setInterval(() => {
      void getIllustration(storyId, job.id)
        .then((updated) => setJob(updated))
        .catch(() => {
          // Keep polling until job completes or user reloads.
        });
    }, 2500);

    return () => clearInterval(timer);
  }, [storyId, job]);

  async function onSend(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const content = input.trim();
    if (!content) {
      return;
    }

    const previousParentMessageId = messages.length ? messages[messages.length - 1].id : null;
    const tempUserId = `temp-user-${Date.now()}`;
    const tempAssistantId = `temp-assistant-${Date.now()}`;
    const nowIso = new Date().toISOString();

    const optimisticUser: Message = {
      id: tempUserId,
      story_id: storyId,
      branch_id: branchId,
      parent_message_id: previousParentMessageId,
      role: "user",
      kind: "user",
      content,
      created_at: nowIso,
    };
    const optimisticAssistant: Message = {
      id: tempAssistantId,
      story_id: storyId,
      branch_id: branchId,
      parent_message_id: tempUserId,
      role: "assistant",
      kind: "narration",
      speaker_name: null,
      content: "複数の反応を組み立てています...",
      created_at: nowIso,
    };

    setMessages((prev) => [...prev, optimisticUser, optimisticAssistant]);
    setInput("");
    setSelection(null);
    setBusy(true);
    setError(null);
    try {
      const payload = {
        content,
        branch_id: branchId,
        parent_message_id: previousParentMessageId,
      };
      const result = await sendChatStream(storyId, payload);

      setMessages((prev) => {
        const withoutOptimistic = prev.filter(
          (message) => message.id !== tempUserId && message.id !== tempAssistantId
        );
        return [...withoutOptimistic, ...result.messages];
      });

      const branchData = await listBranches(storyId);
      setBranches(branchData);
    } catch (err) {
      setMessages((prev) =>
        prev.filter((message) => message.id !== tempUserId && message.id !== tempAssistantId)
      );
      setError(err instanceof Error ? err.message : "送信に失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function onGenerateIllustration(sourceText: string, messageId: string | null) {
    setError(null);
    try {
      const created = await createIllustration(storyId, sourceText, messageId);
      setJob(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "挿絵生成の開始に失敗しました");
    }
  }

  async function onRewind(messageId: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await rewindBranch(storyId, messageId);
      setSelection(null);
      await refreshEverything(result.new_branch_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "巻き戻しに失敗しました");
    } finally {
      setBusy(false);
    }
  }

  async function onSaveSettings(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingSettings(true);
    setError(null);
    try {
      const updated = await updateSettings(storyId, settings);
      setSettings(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "設定の保存に失敗しました");
    } finally {
      setSavingSettings(false);
    }
  }

  async function onLoadOlderHistory() {
    if (loadingMoreHistory || !hasMoreHistory || messages.length === 0) {
      return;
    }

    setLoadingMoreHistory(true);
    setError(null);
    try {
      const oldest = messages[0];
      const page = await listMessages(storyId, branchId, {
        limit: 40,
        beforeMessageId: oldest.id,
      });
      setMessages((prev) => [...page.items, ...prev]);
      setHasMoreHistory(page.has_more);
    } catch (err) {
      setError(err instanceof Error ? err.message : "過去ログの取得に失敗しました");
    } finally {
      setLoadingMoreHistory(false);
    }
  }

  async function onSwitchBranch(nextBranchId: string) {
    if (nextBranchId === branchId) {
      return;
    }

    setBusy(true);
    setSelection(null);
    try {
      await refreshEverything(nextBranchId);
    } finally {
      setBusy(false);
    }
  }

  const selectedForMessage = useMemo(() => {
    if (!selection) {
      return {} as Record<string, string>;
    }
    return { [selection.messageId]: selection.text };
  }, [selection]);

  const contextUsage = useMemo(() => {
    const recentMessages = messages.slice(-HISTORY_WINDOW);
    const historyTokens = recentMessages.reduce((sum, message) => sum + estimateMessageTokens(message), 0);
    const inputTokens = input.trim() ? estimateTokensFromText(input.trim()) + 4 : 0;
    const systemTokens = BASE_SYSTEM_PROMPT_TOKENS + estimateTokensFromText(settings.characters_text || "");
    const estimatedTokens = historyTokens + inputTokens + systemTokens;
    const contextLimit = Math.max(1, settings.context_size || 1);
    const ratioRaw = estimatedTokens / contextLimit;

    let tone = "#2f7d4a";
    let hint = "余裕あり";
    if (ratioRaw >= 1) {
      tone = "#b33a2f";
      hint = "上限超過";
    } else if (ratioRaw >= 0.85) {
      tone = "#c66a00";
      hint = "ほぼ上限";
    } else if (ratioRaw >= 0.6) {
      tone = "#b8861d";
      hint = "注意";
    }

    return {
      recentMessageCount: recentMessages.length,
      historyTokens,
      inputTokens,
      systemTokens,
      estimatedTokens,
      contextLimit,
      ratioRaw,
      barPercent: Math.max(0, Math.min(100, Math.round(ratioRaw * 100))),
      displayPercent: Math.round(ratioRaw * 100),
      tone,
      hint,
    };
  }, [input, messages, settings.characters_text, settings.context_size]);

  const contextToneDynamicStyle = css({
    color: contextUsage.tone,
  });

  const contextBarFillStyle = css({
    width: `${contextUsage.barPercent}%`,
    height: "100%",
    background: contextUsage.tone,
    transition: "width 180ms ease",
  });

  const messageCardDynamicStyle = (message: Message) =>
    css({
      background: messageTone(message),
    });

  return (
    <main css={shellStyle}>
      <header css={[cardStyle, headerStyle]}>
        <div css={headerRowStyle}>
          <div>
            <h1 css={pageTitleStyle}>{story?.title ?? "物語"}</h1>
            <p css={[mutedStyle, noBottomMarginStyle]}>branch: {branchId}</p>
          </div>
          <div css={rowActionsStyle}>
            <button css={buttonBaseStyle} onClick={() => void refreshEverything(branchId)}>
              再読み込み
            </button>
            <Link href="/" css={buttonBaseStyle}>
              新しい物語
            </Link>
          </div>
        </div>
      </header>

      <div css={contentGridStyle}>
        <section css={[cardStyle, chatSectionStyle]}>
          <div css={messageListStyle}>
            <div css={centerRowStyle}>
              <button
                css={buttonBaseStyle}
                type="button"
                onClick={() => void onLoadOlderHistory()}
                disabled={loadingMoreHistory || !hasMoreHistory}
              >
                {loadingMoreHistory ? "読み込み中..." : hasMoreHistory ? "過去を読み込む" : "これ以上ありません"}
              </button>
            </div>

            {messages.map((message) => (
              <article
                key={message.id}
                css={[messageCardStyle, messageCardDynamicStyle(message)]}
                onMouseUp={() => {
                  const selected = window.getSelection()?.toString().trim() ?? "";
                  if (selected) {
                    setSelection({ text: selected, messageId: message.id });
                  }
                }}
              >
                <div css={messageHeaderStyle}>
                  <strong>
                    {message.role === "user"
                      ? "あなた"
                      : message.kind === "narration"
                        ? "ナレーション"
                        : message.speaker_name || "登場人物"}
                  </strong>
                  <span css={[mutedStyle, timestampStyle]}>{new Date(message.created_at).toLocaleString("ja-JP")}</span>
                </div>

                <p css={messageBodyStyle}>{stripSectionTags(message.content)}</p>

                <div css={wrapRowStyle}>
                  <button
                    css={buttonBaseStyle}
                    onClick={() => void onGenerateIllustration(message.content, message.id)}
                  >
                    この段落で挿絵
                  </button>

                  {selectedForMessage[message.id] ? (
                    <button
                      css={buttonBaseStyle}
                      onClick={() => void onGenerateIllustration(selectedForMessage[message.id], message.id)}
                    >
                      選択テキストで挿絵
                    </button>
                  ) : null}

                  <button css={buttonBaseStyle} onClick={() => void onRewind(message.id)}>
                    ここからやり直す
                  </button>
                </div>
              </article>
            ))}
          </div>

          <form onSubmit={onSend} css={chatFormStyle}>
            <TextAreaField
              rows={4}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="物語を入力..."
            />
            <div css={chatFooterStyle}>
              <span css={mutedStyle}>文字数: {Array.from(input).length}</span>
              <button css={[buttonBaseStyle, primaryButtonStyle]} type="submit" disabled={busy}>
                {busy ? "生成中..." : "送信"}
              </button>
            </div>
          </form>

          {error ? <p css={errorTextStyle}>{error}</p> : null}
        </section>

        <aside css={[cardStyle, sidebarStyle]}>
          <h2 css={subHeadingStyle}>分岐一覧</h2>
          <div css={branchListStyle}>
            {branches.length === 0 ? <p css={mutedStyle}>分岐はまだありません。</p> : null}
            {branches.map((branch) => (
              <button
                key={branch.branch_id}
                css={[
                  buttonBaseStyle,
                  branchButtonStyle,
                  branch.branch_id === branchId ? primaryButtonStyle : null,
                ]}
                type="button"
                onClick={() => void onSwitchBranch(branch.branch_id)}
                disabled={busy}
                title={branch.branch_id}
              >
                <div css={branchStatusStyle}>
                  {branch.branch_id === branchId ? "表示中" : branch.is_active ? "現在の正史" : "履歴分岐"}
                </div>
                <div css={branchIdStyle}>{branch.branch_id.slice(0, 8)}</div>
                <div css={branchMetaStyle}>messages: {branch.message_count}</div>
              </button>
            ))}
          </div>

          <hr css={dividerStyle} />

          <h2 css={subHeadingStyle}>物語設定</h2>
          <form onSubmit={onSaveSettings} css={settingsFormStyle}>
            <label>
              Context Size
              <TextField
                type="number"
                min={512}
                max={32768}
                value={settings.context_size}
                onChange={(event) =>
                  setSettings((prev) => ({ ...prev, context_size: Number(event.target.value) }))
                }
              />
            </label>

            <div css={usageCardStyle}>
              <div css={usageHeaderStyle}>
                <strong css={usageTitleStyle}>現在のコンテキスト消費 (推定)</strong>
                <span css={[usageToneStyle, contextToneDynamicStyle]}>
                  {contextUsage.estimatedTokens.toLocaleString()} / {contextUsage.contextLimit.toLocaleString()} tokens ({contextUsage.displayPercent}%)
                </span>
              </div>

              <div css={usageBarTrackStyle}>
                <div css={contextBarFillStyle} />
              </div>

              <div css={usageStatsStyle}>
                <span css={mutedStyle}>履歴(直近{contextUsage.recentMessageCount}件): 約{contextUsage.historyTokens} tokens</span>
                <span css={mutedStyle}>入力: 約{contextUsage.inputTokens} tokens</span>
                <span css={mutedStyle}>固定プロンプト: 約{contextUsage.systemTokens} tokens</span>
                <span css={[contextToneDynamicStyle, branchIdStyle]}>{contextUsage.hint}</span>
              </div>
            </div>

            <label>
              キャラクター一覧（改行区切り）
              <TextAreaField
                rows={8}
                value={settings.characters_text}
                onChange={(event) => setSettings((prev) => ({ ...prev, characters_text: event.target.value }))}
              />
            </label>

            <label>
              Temperature
              <TextField
                type="number"
                min={0}
                max={2}
                step={0.1}
                value={settings.temperature}
                onChange={(event) =>
                  setSettings((prev) => ({ ...prev, temperature: Number(event.target.value) }))
                }
              />
            </label>

            <label>
              Top P
              <TextField
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={settings.top_p}
                onChange={(event) => setSettings((prev) => ({ ...prev, top_p: Number(event.target.value) }))}
              />
            </label>

            <button css={[buttonBaseStyle, primaryButtonStyle]} type="submit" disabled={savingSettings}>
              {savingSettings ? "保存中..." : "設定を保存"}
            </button>
          </form>

          <hr css={dividerStyle} />

          <h3 css={subHeadingStyle}>挿絵ジョブ</h3>
          {!job ? <p css={mutedStyle}>まだ実行していません。</p> : null}
          {job ? (
            <div>
              <p>
                status: <strong>{job.status}</strong>
              </p>
              {job.status === "error" ? <p css={errorTextStyle}>{job.error_message}</p> : null}
              {job.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={job.image_url} alt="generated" css={imageStyle} />
              ) : null}
            </div>
          ) : null}
        </aside>
      </div>
    </main>
  );
}
