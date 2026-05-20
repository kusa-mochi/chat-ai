# Story Chat AI

日本語の自然言語をチャットで入力し、AIが「登場人物のセリフ」と「ナレーション」を返しながら物語を紡ぐローカルシステムです。

- Frontend: Next.js + TypeScript (strict)
- Backend: FastAPI
- DB: PostgreSQL
- Vector Search: Qdrant
- Local LLM: Ollama
- Image Generation: ComfyUI + Stable Diffusion
- Orchestration: Docker Compose

## 1. 前提

- Windows + Docker Desktop + WSL2
- NVIDIA GPU (VRAM 8GB想定)
- NVIDIA Container Toolkit が有効

## 2. 環境変数

プロジェクトルートで `.env` を作成します。

```env
POSTGRES_DB=chat_ai
POSTGRES_USER=chat_ai
POSTGRES_PASSWORD=chat_ai
DATABASE_URL=postgresql+psycopg://chat_ai:chat_ai@postgres:5432/chat_ai

QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=story_context

OLLAMA_BASE_URL=http://ollama:11434
# ここは運用する uncensored 系 Qwen モデルタグに変更可能
OLLAMA_CHAT_MODEL=qwen2.5:7b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text

COMFYUI_BASE_URL=http://comfyui:8188
COMFYUI_CHECKPOINT=v1-5-pruned-emaonly.safetensors

BACKEND_CORS_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 3. 起動

```powershell
docker compose up -d --build
```

## 4. モデルの準備

Ollama コンテナに入り、チャットモデルと埋め込みモデルを pull します。

```powershell
docker exec -it chat-ai-ollama ollama pull qwen2.5:7b
docker exec -it chat-ai-ollama ollama pull nomic-embed-text
```

必要に応じて、8GB VRAMで動作する uncensored 系 Qwen タグへ差し替えてください。

## 5. 利用URL

- Frontend: http://localhost:3000
- Backend OpenAPI: http://localhost:8000/docs
- Qdrant: http://localhost:6333/dashboard
- ComfyUI: http://localhost:8188

## 6. 主な機能

- チャットUIで物語を継続生成
- AIはセリフ(dialogue)とナレーション(narration)を分けて返答
- 入出力テキストをQdrantへ蓄積して文脈再利用
- 物語ごとにコンテキストサイズ、プレプロンプト、人格設定を調整
- 任意テキスト(段落/セリフ/ナレーション)から挿絵生成
- 任意メッセージ位置から分岐して「途中からやり直し」
- 物語は複数保存でき、縦スクロールで過去を遡読可能

## 7. 停止

```powershell
docker compose down
```

## 8. トラブルシュート

- Ollamaモデル未取得で 500 が出る
  - `ollama pull` を実行してから再試行
- 画像生成が timeout になる
  - ComfyUI 側にチェックポイントが未配置の可能性
  - `COMFYUI_CHECKPOINT` を実在ファイル名に合わせる
- GPUメモリ不足
  - `OLLAMA_NUM_PARALLEL=1` を維持
  - Q4 量子化モデルを使う
