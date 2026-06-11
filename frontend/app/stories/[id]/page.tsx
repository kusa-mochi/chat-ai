"use client";

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
  character_name: "シャルロット",
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
const SECTION_TAG_PATTERN = /\[\/?(?:dialogue|narration)\]/gi;
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
  const withoutSections = text.replace(SECTION_TAG_PATTERN, "");
  const withoutTurnMarkers = withoutSections.replace(TURN_MARKER_PATTERN, "");
  const withoutRoleLines = withoutTurnMarkers.replace(ROLE_LINE_PATTERN, "");
  return withoutRoleLines.replace(/\n{3,}/g, "\n\n");
}


function extractStreamingDialogue(rawText: string): string {
  const dialogueMatch = rawText.match(/\[dialogue\]/i);
  const narrationMatch = rawText.match(/\[narration\]/i);

  if (!dialogueMatch && !narrationMatch) {
    return stripSectionTags(rawText);
  }

  if (dialogueMatch) {
    const dialogueStart = dialogueMatch.index ?? 0;
    const afterDialogueTag = rawText.slice(dialogueStart + dialogueMatch[0].length);
    const narrationInDialogue = afterDialogueTag.match(/\[narration\]/i);
    const dialoguePart = narrationInDialogue
      ? afterDialogueTag.slice(0, narrationInDialogue.index ?? 0)
      : afterDialogueTag;
    return stripSectionTags(dialoguePart).trimStart();
  }

  const beforeNarration = rawText.slice(0, narrationMatch?.index ?? 0);
  return stripSectionTags(beforeNarration).trimStart();
}


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
      kind: "dialogue",
      content: "",
      created_at: nowIso,
    };

    setMessages((prev) => [...prev, optimisticUser, optimisticAssistant]);
    setInput("");
    setSelection(null);
    setBusy(true);
    setError(null);
    try {
      let streamedRaw = "";
      const payload = {
        content,
        branch_id: branchId,
        parent_message_id: previousParentMessageId,
      };
      const result = await sendChatStream(storyId, payload, {
        onDelta: (chunk) => {
          streamedRaw += chunk;
          const dialoguePreview = extractStreamingDialogue(streamedRaw);
          setMessages((prev) =>
            prev.map((message) =>
              message.id === tempAssistantId
                ? { ...message, content: dialoguePreview }
                : message
            )
          );
        },
      });

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
    const systemTokens = BASE_SYSTEM_PROMPT_TOKENS + estimateTokensFromText(settings.character_name || "");
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
  }, [input, messages, settings.character_name, settings.context_size]);

  return (
    <main className="shell" style={{ maxWidth: 1300, margin: "0 auto" }}>
      <header className="card" style={{ padding: 16, marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
          <div>
            <h1 style={{ margin: 0 }}>{story?.title ?? "物語"}</h1>
            <p className="muted" style={{ marginBottom: 0 }}>
              branch: {branchId}
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={() => void refreshEverything(branchId)}>
              再読み込み
            </button>
            <Link href="/" className="btn">
              新しい物語
            </Link>
          </div>
        </div>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(260px, 340px)", gap: 14 }}>
        <section className="card" style={{ padding: 12, minHeight: 680, display: "flex", flexDirection: "column" }}>
          <div
            style={{
              flex: 1,
              overflowY: "auto",
              borderRadius: 12,
              padding: 10,
              border: "1px solid var(--line)",
              background: "#ffffff8a",
            }}
          >
            <div style={{ display: "flex", justifyContent: "center", marginBottom: 10 }}>
              <button
                className="btn"
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
                style={{
                  background: messageTone(message),
                  padding: 12,
                  borderRadius: 10,
                  marginBottom: 10,
                  border: "1px solid var(--line)",
                }}
                onMouseUp={() => {
                  const selected = window.getSelection()?.toString().trim() ?? "";
                  if (selected) {
                    setSelection({ text: selected, messageId: message.id });
                  }
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                  <strong>
                    {message.role === "user"
                      ? "あなた"
                      : message.kind === "narration"
                        ? "ナレーション"
                        : settings.character_name || "Character"}
                  </strong>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {new Date(message.created_at).toLocaleString("ja-JP")}
                  </span>
                </div>

                <p style={{ whiteSpace: "pre-wrap", marginBottom: 8 }}>{stripSectionTags(message.content)}</p>

                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button
                    className="btn"
                    onClick={() => void onGenerateIllustration(message.content, message.id)}
                  >
                    この段落で挿絵
                  </button>

                  {selectedForMessage[message.id] ? (
                    <button
                      className="btn"
                      onClick={() => void onGenerateIllustration(selectedForMessage[message.id], message.id)}
                    >
                      選択テキストで挿絵
                    </button>
                  ) : null}

                  <button className="btn" onClick={() => void onRewind(message.id)}>
                    ここからやり直す
                  </button>
                </div>
              </article>
            ))}
          </div>

          <form onSubmit={onSend} style={{ display: "grid", gap: 8, marginTop: 10 }}>
            <textarea
              className="field"
              rows={4}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="物語を入力..."
            />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span className="muted">文字数: {Array.from(input).length}</span>
              <button className="btn primary" type="submit" disabled={busy}>
                {busy ? "生成中..." : "送信"}
              </button>
            </div>
          </form>

          {error ? <p style={{ color: "#8f1f10" }}>{error}</p> : null}
        </section>

        <aside className="card" style={{ padding: 14, height: "fit-content" }}>
          <h2 style={{ marginTop: 0 }}>分岐一覧</h2>
          <div style={{ display: "grid", gap: 8, marginBottom: 14 }}>
            {branches.length === 0 ? <p className="muted">分岐はまだありません。</p> : null}
            {branches.map((branch) => (
              <button
                key={branch.branch_id}
                className={`btn ${branch.branch_id === branchId ? "primary" : ""}`}
                type="button"
                onClick={() => void onSwitchBranch(branch.branch_id)}
                disabled={busy}
                style={{ textAlign: "left" }}
                title={branch.branch_id}
              >
                <div style={{ fontSize: 12, opacity: 0.9 }}>
                  {branch.branch_id === branchId ? "表示中" : branch.is_active ? "現在の正史" : "履歴分岐"}
                </div>
                <div style={{ fontWeight: 700 }}>{branch.branch_id.slice(0, 8)}</div>
                <div style={{ fontSize: 12 }}>messages: {branch.message_count}</div>
              </button>
            ))}
          </div>

          <hr style={{ margin: "16px 0", borderColor: "var(--line)" }} />

          <h2 style={{ marginTop: 0 }}>物語設定</h2>
          <form onSubmit={onSaveSettings} style={{ display: "grid", gap: 8 }}>
            <label>
              Context Size
              <input
                className="field"
                type="number"
                min={512}
                max={32768}
                value={settings.context_size}
                onChange={(event) =>
                  setSettings((prev) => ({ ...prev, context_size: Number(event.target.value) }))
                }
              />
            </label>

            <div
              style={{
                border: "1px solid var(--line)",
                borderRadius: 10,
                padding: 10,
                background: "#ffffff85",
                display: "grid",
                gap: 6,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                <strong style={{ fontSize: 13 }}>現在のコンテキスト消費 (推定)</strong>
                <span style={{ fontSize: 12, color: contextUsage.tone }}>
                  {contextUsage.estimatedTokens.toLocaleString()} / {contextUsage.contextLimit.toLocaleString()} tokens ({contextUsage.displayPercent}%)
                </span>
              </div>

              <div
                style={{
                  width: "100%",
                  height: 10,
                  borderRadius: 999,
                  background: "#00000014",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${contextUsage.barPercent}%`,
                    height: "100%",
                    background: contextUsage.tone,
                    transition: "width 180ms ease",
                  }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", gap: 8, flexWrap: "wrap", fontSize: 12 }}>
                <span className="muted">履歴(直近{contextUsage.recentMessageCount}件): 約{contextUsage.historyTokens} tokens</span>
                <span className="muted">入力: 約{contextUsage.inputTokens} tokens</span>
                <span className="muted">固定プロンプト: 約{contextUsage.systemTokens} tokens</span>
                <span style={{ color: contextUsage.tone, fontWeight: 700 }}>{contextUsage.hint}</span>
              </div>
            </div>

            <label>
              登場人物名
              <input
                className="field"
                value={settings.character_name}
                onChange={(event) => setSettings((prev) => ({ ...prev, character_name: event.target.value }))}
              />
            </label>

            <label>
              Temperature
              <input
                className="field"
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
              <input
                className="field"
                type="number"
                min={0}
                max={1}
                step={0.05}
                value={settings.top_p}
                onChange={(event) => setSettings((prev) => ({ ...prev, top_p: Number(event.target.value) }))}
              />
            </label>

            <button className="btn primary" type="submit" disabled={savingSettings}>
              {savingSettings ? "保存中..." : "設定を保存"}
            </button>
          </form>

          <hr style={{ margin: "16px 0", borderColor: "var(--line)" }} />

          <h3 style={{ marginTop: 0 }}>挿絵ジョブ</h3>
          {!job ? <p className="muted">まだ実行していません。</p> : null}
          {job ? (
            <div>
              <p>
                status: <strong>{job.status}</strong>
              </p>
              {job.status === "error" ? <p style={{ color: "#8f1f10" }}>{job.error_message}</p> : null}
              {job.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={job.image_url} alt="generated" style={{ width: "100%", borderRadius: 8 }} />
              ) : null}
            </div>
          ) : null}
        </aside>
      </div>
    </main>
  );
}
