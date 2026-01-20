"""
ThreadGenius デモ実行スクリプト
APIキーなしでも動作確認できるデモモード
"""

from config import PersonaConfig, DEFAULT_PERSONAS, DEFAULT_RSS_FEEDS
from news_collector import NewsCollector

def demo_persona():
    """ペルソナのデモ"""
    print("=" * 60)
    print("🎭 ThreadGenius - ペルソナシステムデモ")
    print("=" * 60)
    print()
    
    for i, persona in enumerate(DEFAULT_PERSONAS, 1):
        print(f"【ペルソナ {i}】")
        print(f"名前: {persona.name}")
        print(f"専門分野: {persona.specialty}")
        print(f"口調: {persona.tone}")
        print(f"価値観: {persona.values}")
        print(f"ターゲット: {persona.target_audience}")
        print(f"目標: {persona.goals}")
        print()

def demo_news_collection():
    """ニュース収集のデモ"""
    print("=" * 60)
    print("📰 ThreadGenius - ニュース収集デモ")
    print("=" * 60)
    print()
    
    print("RSSフィードから最新ニュースを取得中...")
    print()
    
    collector = NewsCollector(DEFAULT_RSS_FEEDS)
    
    try:
        news_items = collector.collect_news(limit=3)
        
        if news_items:
            print(f"✅ {len(news_items)}件のニュースを取得しました！\n")
            
            for i, news in enumerate(news_items, 1):
                print(f"【ニュース {i}】")
                print(f"タイトル: {news['title']}")
                print(f"概要: {news['summary'][:100]}...")
                print(f"リンク: {news['link']}")
                print()
        else:
            print("⚠️ ニュースが取得できませんでした")
            print("（ネットワーク接続を確認してください）")
    
    except Exception as e:
        print(f"❌ エラー: {e}")

def demo_post_template():
    """投稿テンプレートのデモ"""
    print("=" * 60)
    print("📝 ThreadGenius - 投稿テンプレートデモ")
    print("=" * 60)
    print()
    
    print("【2026年最新 Threadsアルゴリズム対応投稿構成】\n")
    
    example_post = """
🔥 最近AIツールがヤバすぎる件

ChatGPTやClaudeを使えば、
SNS投稿も自動生成できる時代。

でも正直、ツールに頼りすぎると
「自分らしさ」が消えませんか？

僕は8割は自動化して、
残り2割で「人間味」を出すようにしてる。

あなたはAIとの付き合い方、
どう考えてます？🤔

#AI活用術
"""
    
    print("【生成例】")
    print(example_post.strip())
    print()
    
    print("【構成分析】")
    print("✓ 冒頭：「ヤバすぎる」でスクロールを止める")
    print("✓ 本文：共感（自分らしさが消える）+ 有益情報（8:2の法則）")
    print("✓ 末尾：質問で会話を誘発")
    print("✓ トピックタグ：1つのみ (#AI活用術)")
    print("✓ 文字数：500文字以内")
    print("✓ 「ツッコミ代」：8:2の比率、賛否両論あり")
    print()

def demo_scoring():
    """スコアリングデモ"""
    print("=" * 60)
    print("📊 ThreadGenius - スコアリングシステムデモ")
    print("=" * 60)
    print()
    
    print("【8種類メトリクス評価】\n")
    
    scores = {
        "会話誘発度": 0.85,
        "トレンド適合性": 0.75,
        "感情的インパクト": 0.90,
        "提供価値": 0.70,
        "Stage1突破ポテンシャル": 0.80
    }
    
    weights = {
        "会話誘発度": 30,
        "トレンド適合性": 25,
        "感情的インパクト": 20,
        "提供価値": 15,
        "Stage1突破ポテンシャル": 10
    }
    
    total_score = 0
    
    for metric, score in scores.items():
        weight = weights[metric]
        weighted_score = score * weight
        total_score += weighted_score
        
        bar = "█" * int(score * 20)
        print(f"{metric:20s} [{bar:20s}] {score:.2f} × {weight}% = {weighted_score:.1f}点")
    
    print()
    print(f"【総合スコア】 {total_score:.1f} / 100点")
    print()
    
    if total_score >= 80:
        print("🟢 評価：優秀 - Stage3以上到達の可能性が高い")
    elif total_score >= 60:
        print("🟡 評価：良好 - Stage2安定到達")
    else:
        print("🔴 評価：改善推奨 - Stage1突破が課題")

def demo_algorithm_rules():
    """アルゴリズムルールのデモ"""
    print("=" * 60)
    print("🎯 ThreadGenius - 2026年最新アルゴリズム")
    print("=" * 60)
    print()
    
    print("【3つの鍵】\n")
    print("1️⃣  投稿頻度：「いること」をアルゴリズムに知らせる")
    print("   → 最低1日1回、理想は1日2-5回")
    print()
    print("2️⃣  会話の質：「いいね」より「リプライ」が圧倒的に重要")
    print("   → 質問や意見を求める投稿を設計")
    print()
    print("3️⃣  テキスト中心：AIが理解できる投稿")
    print("   → 画像だけでなく、必ずテキストを添える")
    print()
    
    print("【4段階ステージ評価】\n")
    print("Stage1: 初期配信（フォロワーの一部）")
    print("  └─ 評価ポイント：初速の反応")
    print("  └─ 対策：投稿後1時間はリプライに即返信\n")
    
    print("Stage2: 拡大配信（フォロワー全体）")
    print("  └─ 評価ポイント：反応の持続性")
    print("  └─ 対策：テキストで文脈を補足\n")
    
    print("Stage3: 発見・おすすめ（フォロワー外）")
    print("  └─ 評価ポイント：トレンドとの関連性")
    print("  └─ 対策：トピックタグを活用\n")
    
    print("Stage4: 広範囲拡散（Instagram等外部）")
    print("  └─ 評価ポイント：シェア価値")
    print("  └─ 対策：Stage3を安定して超えることを目指す\n")

def main():
    """メインのデモ実行"""
    print()
    print("🚀" * 30)
    print()
    print("     ThreadGenius - あなた専用Threads投稿自動生成ツール")
    print("     ThreadPostに匹敵する最強ツール")
    print()
    print("🚀" * 30)
    print()
    
    demos = [
        ("1", "ペルソナシステム", demo_persona),
        ("2", "ニュース収集", demo_news_collection),
        ("3", "投稿テンプレート", demo_post_template),
        ("4", "スコアリングシステム", demo_scoring),
        ("5", "2026年最新アルゴリズム", demo_algorithm_rules),
        ("6", "全てのデモを実行", None)
    ]
    
    print("【デモメニュー】\n")
    for num, name, _ in demos:
        print(f"{num}. {name}")
    print()
    
    choice = input("選択してください (1-6): ").strip()
    print()
    
    if choice == "6":
        # 全て実行
        demo_persona()
        input("\nEnterキーで次へ...")
        print()
        
        demo_news_collection()
        input("\nEnterキーで次へ...")
        print()
        
        demo_post_template()
        input("\nEnterキーで次へ...")
        print()
        
        demo_scoring()
        input("\nEnterキーで次へ...")
        print()
        
        demo_algorithm_rules()
    else:
        # 個別実行
        for num, name, func in demos:
            if choice == num and func:
                func()
                break
    
    print()
    print("=" * 60)
    print("🎉 デモ完了！")
    print("=" * 60)
    print()
    print("【次のステップ】")
    print()
    print("1. APIキーを設定")
    print("   - Anthropic API Key (Claude)")
    print("   - Threads App ID & Secret")
    print()
    print("2. アプリを起動")
    print("   $ streamlit run app.py")
    print()
    print("3. ブラウザでThreadGeniusを使う！")
    print()

if __name__ == "__main__":
    main()
