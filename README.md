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
# backend/llm_models の GGUF を ollama create したモデル名
OLLAMA_CHAT_MODEL=qwen2.5-7b-instruct-uncensored-q4km:latest
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_CHAT_TIMEOUT_SECONDS=300
OLLAMA_EMBEDDING_TIMEOUT_SECONDS=120

COMFYUI_BASE_URL=http://comfyui:8188
COMFYUI_CHECKPOINT=v1-5-pruned-emaonly.safetensors

BACKEND_CORS_ORIGINS=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

## 3. 起動

```powershell
docker compose up -d --build
```

`docker compose down -v` 後の復旧は、次の1コマンドで完了します。

```powershell
pwsh ./scripts/reset-and-up.ps1
```

ボリューム削除まで含めて1コマンドでやる場合:

```powershell
pwsh ./scripts/reset-and-up.ps1 -ResetVolumes
```

## 4. モデルの準備

通常は `pwsh ./scripts/reset-and-up.ps1` が自動で実施します。

- Ollama の起動待機
- チャットモデル作成 (`OLLAMA_CHAT_MODEL`)
- 埋め込みモデル pull (`OLLAMA_EMBEDDING_MODEL`)
- backend の再作成

手動で実行したい場合のみ、下記を使ってください。

```powershell
docker compose up -d ollama
docker compose exec ollama ollama create qwen2.5-7b-instruct-uncensored-q4km:latest -f /models/Modelfile.qwen2.5-7b-instruct-uncensored-q4km
docker compose exec ollama ollama pull nomic-embed-text
docker compose up -d --force-recreate backend
```

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
  - `pwsh ./scripts/reset-and-up.ps1` を実行して再試行
- 画像生成が timeout になる
  - ComfyUI 側にチェックポイントが未配置の可能性
  - `COMFYUI_CHECKPOINT` を実在ファイル名に合わせる
- GPUメモリ不足
  - `OLLAMA_NUM_PARALLEL=1` を維持
  - Q4 量子化モデルを使う
