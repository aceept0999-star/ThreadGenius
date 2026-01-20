# ThreadGenius - あなた専用Threads投稿自動生成ツール
# Configuration File

import os
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class PersonaConfig:
    """ペルソナ設定"""
    name: str
    specialty: str  # 専門分野（グルメ、ビジネス、フィットネスなど）
    tone: str  # 口調（フレンドリー、プロフェッショナル、親しみやすいなど）
    values: str  # 価値観
    target_audience: str  # ターゲットオーディエンス
    goals: str  # 目標
    
@dataclass
class ThreadsAlgorithmRules:
    """2026年最新Threadsアルゴリズムルール"""
    max_chars: int = 500
    min_posting_frequency: str = "1日1回"
    topic_tags: int = 1  # トピックタグは1つ
    engagement_priority: str = "リプライ > いいね"
    
    # 4段階ステージ
    stages = {
        "Stage1": "初期配信（フォロワーの一部）- 初速の反応",
        "Stage2": "拡大配信（フォロワー全体）- 反応の持続性",
        "Stage3": "発見・おすすめ（フォロワー外）- トレンドとの関連性",
        "Stage4": "広範囲拡散（Instagram等外部）- シェア価値"
    }
    
@dataclass
class PostTemplate:
    """投稿テンプレート構造"""
    hook: str  # 冒頭：興味を引く
    body: str  # 本文：共感・有益情報
    call_to_action: str  # 末尾：質問投げかけ（会話誘発）
    topic_tag: Optional[str] = None  # トピックタグ（1つのみ）

# デフォルトペルソナ例
DEFAULT_PERSONAS = [
    PersonaConfig(
        name="グルメ太郎",
        specialty="グルメ・食文化",
        tone="親しみやすく、食への情熱があふれる",
        values="美味しい食事で人生を豊かに",
        target_audience="食にこだわりのある20-40代",
        goals="フォロワーと食の喜びを共有し、コミュニティを形成"
    ),
    PersonaConfig(
        name="ビジネス先生",
        specialty="ビジネス・マーケティング",
        tone="プロフェッショナルだが親しみやすい",
        values="正しい知識で人を成功に導く",
        target_audience="副業・起業を目指す20-50代",
        goals="実践的な知識を共有し、信頼を構築"
    ),
    PersonaConfig(
        name="フィットネスコーチ",
        specialty="健康・フィットネス",
        tone="明るく、励ましながら指導",
        values="継続可能な健康習慣で人生を変える",
        target_audience="健康意識の高い25-45代",
        goals="フォロワーの健康改善をサポート"
    )
]

# API設定
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
THREADS_APP_ID = os.getenv("THREADS_APP_ID", "")
THREADS_APP_SECRET = os.getenv("THREADS_APP_SECRET", "")

# RSS フィード設定（カスタマイズ可能）
DEFAULT_RSS_FEEDS = [
    "https://news.yahoo.co.jp/rss/topics/top-picks.xml",
    "https://www.itmedia.co.jp/rss/2.0/news_bursts.xml",
    # ユーザーが追加可能
]

# スコアリング重み設定
SCORING_WEIGHTS = {
    "conversation_trigger": 0.30,  # 会話誘発度
    "trend_relevance": 0.25,       # トレンド適合性
    "emotional_impact": 0.20,       # 感情的インパクト
    "value_provided": 0.15,         # 提供価値
    "stage1_potential": 0.10        # Stage1突破ポテンシャル
}
