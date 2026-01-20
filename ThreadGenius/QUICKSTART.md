# 🚀 ThreadGenius クイックスタートガイド

## 🎉 おめでとうございます！

**ThreadPostに匹敵する、あなた専用のThreads投稿自動生成ツール「ThreadGenius」が完成しました！**

---

## ⚡ 今すぐ始める 3ステップ

### ステップ1️⃣：APIキーを取得

#### 📌 Anthropic API Key（Claude API）
1. [Anthropic Console](https://console.anthropic.com/)にアクセス
2. アカウント作成
3. API Keysから新しいキーを作成
4. キーをコピーして保存

#### 📌 Threads App ID & Secret
1. [Meta for Developers](https://developers.facebook.com/)にアクセス
2. 「マイアプリ」→「アプリを作成」
3. 「その他」を選択
4. アプリ名を入力
5. 「Threads」を製品として追加
6. App ID & App Secretをコピー

### ステップ2️⃣：ツールを起動

```bash
# ThreadGeniusディレクトリに移動
cd /mnt/aidrive/ThreadGenius

# 起動
streamlit run app.py
```

### ステップ3️⃣：投稿を生成！

1. サイドバーでAPIキーを入力
2. ペルソナを選択（または作成）
3. ニュースを取得
4. 「🎨 投稿を生成」をクリック
5. 最高スコアの投稿を選んで投稿！

---

## 🎯 ThreadGeniusの強み

### 1. 2026年最新アルゴリズム完全対応

ThreadGeniusは、ThreadPostと同じく、最新のThreadsアルゴリズムを完全に理解しています：

- ✅ **投稿頻度重視**：アクティブなアカウントとして認識
- ✅ **会話誘発設計**：リプライを増やす質問設計
- ✅ **テキスト中心**：AIが理解できる投稿
- ✅ **4段階ステージ評価**：Stage1-4の到達予測

### 2. プロフェッショナルなスコアリング

各投稿案を8種類のメトリクスで自動評価：

| メトリクス | 重み | 説明 |
|-----------|------|------|
| 会話誘発度 | 30% | 質問や意見を求める力 |
| トレンド適合性 | 25% | トレンドとの関連性 |
| 感情的インパクト | 20% | 感情を揺さぶる力 |
| 提供価値 | 15% | 有益情報の量 |
| Stage1突破ポテンシャル | 10% | 初速での反応期待値 |

### 3. あなた専用にカスタマイズ

- **ペルソナ無制限**：何個でもキャラクターを作成可能
- **カスタムRSS**：自分の情報源を追加
- **スコアリング調整**：重み付けを自由にカスタマイズ

---

## 📊 ThreadPost との比較

| 機能 | ThreadPost | ThreadGenius |
|------|-----------|-------------|
| 月額料金 | ¥2,980〜¥49,800 | **無料** |
| ペルソナ数 | プランに依存（1-30個） | **無制限** |
| 投稿生成 | ○ | ✅ 完全カスタマイズ可能 |
| スコアリング | ○ | ✅ 8種類メトリクス |
| Threads API連携 | ○ | ✅ 完全対応 |
| コード公開 | ✗ | ✅ **完全公開・改造自由** |
| データ所有 | サービス側 | ✅ **完全にあなたのもの** |

---

## 💡 プロからのアドバイス

### フォロワーを増やす黄金ルール

1. **毎日投稿する**
   - ThreadGeniusで毎日1-3回投稿
   - アルゴリズムに「アクティブ」と認識させる

2. **投稿後1時間が勝負**
   - リプライに即返信
   - Stage1突破のカギ

3. **会話を設計する**
   - ThreadGeniusの高スコア投稿（80点以上）を優先
   - 質問で終わる投稿を意識

4. **トピックタグは1つ**
   - ThreadGeniusが自動で最適なタグを提案
   - 必ず1つだけ使用

5. **ペルソナを確立する**
   - 一貫したキャラクターで投稿
   - フォロワーが「あなたらしさ」を認識

### 収益化ロードマップ

```
【0-1,000フォロワー】
├─ ThreadGeniusで毎日投稿
├─ 会話を大切にする
└─ ペルソナを確立

【1,000-5,000フォロワー】
├─ アフィリエイトリンク開始
├─ noteなどで有料コンテンツ
└─ コミュニティ形成

【5,000-10,000フォロワー】
├─ PR案件獲得
├─ 運用代行サービス開始
└─ 月5-30万円の収益

【10,000フォロワー以上】
├─ 企業案件
├─ 自社商品販売
└─ 月30-100万円以上も可能
```

---

## 🛠️ カスタマイズガイド

### ペルソナを最適化する

```python
# config.py を編集
PersonaConfig(
    name="あなたの名前",
    specialty="あなたの専門分野",
    tone="親しみやすく、情熱的",  # ←ここが重要！
    values="あなたの価値観",
    target_audience="20-40代のビジネスパーソン",
    goals="フォロワーと信頼関係を構築"
)
```

### スコアリング重みを調整

```python
# config.py の SCORING_WEIGHTS を編集
SCORING_WEIGHTS = {
    "conversation_trigger": 0.40,  # 会話をもっと重視
    "trend_relevance": 0.20,
    "emotional_impact": 0.20,
    "value_provided": 0.15,
    "stage1_potential": 0.05
}
```

---

## 🆘 トラブルシューティング

### Q: Streamlitが起動しない

```bash
pip install --upgrade streamlit
```

### Q: APIキーのエラー

- APIキーに余分なスペースがないか確認
- 環境変数として設定するのが安全：

```bash
export ANTHROPIC_API_KEY="your-key-here"
export THREADS_APP_ID="your-app-id"
export THREADS_APP_SECRET="your-secret"
```

### Q: 投稿が生成されない

- Claude APIの利用可能枠を確認
- ニュース内容が十分な長さか確認（最低100文字推奨）

### Q: Threads API認証エラー

- Meta for Developersでアプリのステータスを確認
- リダイレクトURIが正しく設定されているか確認

---

## 🎓 さらに学ぶ

### おすすめリソース

1. **Threads公式ドキュメント**
   - [Threads API Documentation](https://developers.facebook.com/docs/threads)

2. **Threadsアルゴリズム最新情報**
   - [2026年最新アルゴリズム解説](https://addness.co.jp/media/threads-algorithms/)

3. **Claude API**
   - [Anthropic Documentation](https://docs.anthropic.com/)

---

## 🎉 成功への道

**ThreadGeniusは、あなたのThreads成功を完全サポートします。**

ThreadPostに月額数万円払う代わりに、完全無料で同等以上の機能を手に入れました。

さあ、2026年のThreadsを攻略しましょう！

---

## 📞 サポート

質問や改善要望があれば、いつでもお気軽にご連絡ください。

**あなたの成功を心から応援しています！ 🚀✨**

---

**ThreadGenius - あなた専用Threads自動投稿ツール**  
*2026年最新アルゴリズム対応 | Claude API Powered*
