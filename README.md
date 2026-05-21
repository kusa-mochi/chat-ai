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

## 4. モデルの準備

### 4.1 チャットモデル (GGUF) を Ollama に登録

`backend/llm_models/` にある GGUF を Ollama コンテナへコピーし、モデルとして登録します。

```powershell
docker compose up -d ollama

$ModelName = "qwen2.5-7b-instruct-uncensored-q4km"
$Gguf = "backend/llm_models/Qwen2.5-7B-Instruct-Uncensored.Q4_K_M.gguf"
$ModelfileLocal = "backend/llm_models/Modelfile.$ModelName"

@"
FROM /models/Qwen2.5-7B-Instruct-Uncensored.Q4_K_M.gguf
PARAMETER num_ctx 4096
"@ | Set-Content -Path $ModelfileLocal -Encoding ascii

docker compose exec ollama mkdir -p /models
docker cp $Gguf "chat-ai-ollama:/models/Qwen2.5-7B-Instruct-Uncensored.Q4_K_M.gguf"
docker cp $ModelfileLocal "chat-ai-ollama:/models/Modelfile.$ModelName"
docker compose exec ollama ollama create $ModelName -f /models/Modelfile.$ModelName
docker compose exec ollama ollama list
```

### 4.2 埋め込みモデルを pull

```powershell
docker compose exec ollama ollama pull nomic-embed-text
```

最後に backend を再作成して環境変数の反映を確認します。

```powershell
docker compose up -d --force-recreate backend
docker compose exec backend printenv OLLAMA_CHAT_MODEL OLLAMA_EMBEDDING_MODEL
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
  - 上記 4.1/4.2 を実行してから再試行
- 画像生成が timeout になる
  - ComfyUI 側にチェックポイントが未配置の可能性
  - `COMFYUI_CHECKPOINT` を実在ファイル名に合わせる
- GPUメモリ不足
  - `OLLAMA_NUM_PARALLEL=1` を維持
  - Q4 量子化モデルを使う
