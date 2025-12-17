# Secretary Partner AI - Backend

ADHD向け自律型秘書AI「Brain Dump Partner」のバックエンド実装。

## Quick Start

```bash
# 依存関係のインストール
pip install -e ".[dev]"

# 環境変数の設定
cp .env.example .env
# .envファイルを編集してGOOGLE_API_KEY等を設定

# 開発サーバー起動
uvicorn main:app --reload

# テスト実行
pytest
```

詳細は `CLAUDE.md` を参照してください。

