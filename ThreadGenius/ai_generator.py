"""
AI投稿生成モジュール
Claude APIを使用して、2026年最新Threadsアルゴリズムに最適化された投稿を生成
"""

import anthropic
from typing import List, Dict, Optional
from config import PersonaConfig, ThreadsAlgorithmRules, PostTemplate, SCORING_WEIGHTS

class ThreadsPostGenerator:
    """Threads投稿生成エンジン"""
    
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.rules = ThreadsAlgorithmRules()
        
    def generate_posts(
        self, 
        persona: PersonaConfig, 
        news_content: str,
        num_variations: int = 5
    ) -> List[Dict]:
        """
        ペルソナとニュースから複数の投稿案を生成
        
        Args:
            persona: ペルソナ設定
            news_content: ニュース内容
            num_variations: 生成するバリエーション数
            
        Returns:
            投稿案のリスト（スコア付き）
        """
        
        prompt = self._build_prompt(persona, news_content, num_variations)
        
        response = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4000,
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        # レスポンスをパース
        posts = self._parse_response(response.content[0].text)
        
        # スコアリング
        scored_posts = [self._score_post(post, persona) for post in posts]
        
        # スコア順にソート
        scored_posts.sort(key=lambda x: x['score'], reverse=True)
        
        return scored_posts
    
    def _build_prompt(self, persona: PersonaConfig, news_content: str, num_variations: int) -> str:
        """Claude APIに送信するプロンプトを構築"""
        
        prompt = f"""あなたは、2026年最新のThreadsアルゴリズムを完全に理解した、プロのSNS投稿クリエイターです。

【あなたのペルソナ】
名前：{persona.name}
専門分野：{persona.specialty}
口調：{persona.tone}
価値観：{persona.values}
ターゲット：{persona.target_audience}
目標：{persona.goals}

【2026年Threadsアルゴリズムの鉄則】
1. 投稿頻度が高いほど、1投稿あたりのインプレッションも増加
2. 「いいね」より「リプライ（会話）」が圧倒的に重要
3. テキスト中心（AIが内容を理解できる）
4. トピックタグは1つだけ
5. 500文字以内で「ツッコミ代」を残す（完璧すぎない）

【4段階ステージ評価】
Stage1：初期配信（フォロワーの一部）→ 初速の反応が命
Stage2：拡大配信（フォロワー全体）→ 反応の持続性
Stage3：発見・おすすめ（フォロワー外）→ トレンドとの関連性
Stage4：広範囲拡散（Instagram等外部）→ シェア価値

【投稿構成テンプレート】
1. 冒頭（1-2行）：スクロールを止める「フック」
2. 本文（3-8行）：共感または有益な情報
3. 末尾（1-2行）：会話を誘発する「質問」

【ニュース内容】
{news_content}

【タスク】
上記のニュースを基に、{persona.name}として{num_variations}つの投稿案を作成してください。

【必須条件】
✓ 各投稿は500文字以内
✓ {persona.tone}の口調を守る
✓ 末尾に必ず「質問」または「意見を求める」文を入れる
✓ 完璧すぎず、「それってどうなの？」とツッコミたくなる余白を残す
✓ トピックタグを1つ提案（例：#ビジネス、#グルメ、#健康）
✓ Stage1（初速の反応）を突破できる設計

【出力形式】
各投稿を以下のJSON形式で出力してください：

```json
[
  {{
    "post_text": "投稿本文（500文字以内）",
    "topic_tag": "#トピック名",
    "hook": "冒頭のフック部分",
    "body": "本文の核心部分",
    "cta": "末尾の質問/呼びかけ",
    "predicted_stage": "この投稿が到達しそうなステージ（Stage1-4）",
    "conversation_trigger": "会話を誘発するポイント",
    "reasoning": "なぜこの構成にしたか（100文字以内）"
  }}
]
```

それでは、{persona.name}として、魂を込めた投稿を作成してください！"""

        return prompt
    
    def _parse_response(self, response_text: str) -> List[Dict]:
        """Claude APIのレスポンスをパース"""
        import json
        import re
        
        # JSONブロックを抽出
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        
        if json_match:
            json_str = json_match.group(1)
            try:
                posts = json.loads(json_str)
                return posts if isinstance(posts, list) else [posts]
            except json.JSONDecodeError:
                print("JSON解析エラー。テキストから手動パース中...")
        
        # フォールバック：テキストから手動抽出
        return self._fallback_parse(response_text)
    
    def _fallback_parse(self, text: str) -> List[Dict]:
        """フォールバック：テキストから投稿を抽出"""
        # 簡易実装（後で改善可能）
        return [{
            "post_text": text[:500],
            "topic_tag": "#トレンド",
            "predicted_stage": "Stage2",
            "conversation_trigger": "質問を含む",
            "reasoning": "自動生成"
        }]
    
    def _score_post(self, post: Dict, persona: PersonaConfig) -> Dict:
        """投稿をスコアリング（0-100点）"""
        
        score = 0
        details = {}
        
        # 1. 会話誘発度（30点）
        conversation_score = self._evaluate_conversation_trigger(post)
        score += conversation_score * SCORING_WEIGHTS["conversation_trigger"] * 100
        details["conversation_trigger"] = conversation_score
        
        # 2. トレンド適合性（25点）
        trend_score = self._evaluate_trend_relevance(post)
        score += trend_score * SCORING_WEIGHTS["trend_relevance"] * 100
        details["trend_relevance"] = trend_score
        
        # 3. 感情的インパクト（20点）
        emotional_score = self._evaluate_emotional_impact(post)
        score += emotional_score * SCORING_WEIGHTS["emotional_impact"] * 100
        details["emotional_impact"] = emotional_score
        
        # 4. 提供価値（15点）
        value_score = self._evaluate_value_provided(post)
        score += value_score * SCORING_WEIGHTS["value_provided"] * 100
        details["value_provided"] = value_score
        
        # 5. Stage1突破ポテンシャル（10点）
        stage1_score = self._evaluate_stage1_potential(post)
        score += stage1_score * SCORING_WEIGHTS["stage1_potential"] * 100
        details["stage1_potential"] = stage1_score
        
        post["score"] = round(score, 2)
        post["score_details"] = details
        
        return post
    
    def _evaluate_conversation_trigger(self, post: Dict) -> float:
        """会話誘発度を評価（0.0-1.0）"""
        text = post.get("post_text", "").lower()
        cta = post.get("cta", "").lower()
        
        score = 0.0
        
        # 質問があるか
        if "?" in text or "？" in text:
            score += 0.4
        
        # 意見を求める表現
        opinion_keywords = ["どう思", "考え", "意見", "教えて", "どうです", "どっち"]
        if any(kw in text for kw in opinion_keywords):
            score += 0.3
        
        # CTAが具体的か
        if len(cta) > 10:
            score += 0.3
        
        return min(score, 1.0)
    
    def _evaluate_trend_relevance(self, post: Dict) -> float:
        """トレンド適合性を評価（0.0-1.0）"""
        # 簡易実装：トピックタグの有無
        if post.get("topic_tag"):
            return 0.8
        return 0.4
    
    def _evaluate_emotional_impact(self, post: Dict) -> float:
        """感情的インパクトを評価（0.0-1.0）"""
        text = post.get("post_text", "")
        
        # 感情的な言葉の存在
        emotional_words = ["驚", "感動", "最高", "やばい", "すごい", "衝撃", "共感", "涙"]
        
        count = sum(1 for word in emotional_words if word in text)
        
        return min(count * 0.25, 1.0)
    
    def _evaluate_value_provided(self, post: Dict) -> float:
        """提供価値を評価（0.0-1.0）"""
        text = post.get("post_text", "")
        
        # 有益情報を示すキーワード
        value_keywords = ["方法", "コツ", "ポイント", "秘訣", "戦略", "結果", "データ", "実践"]
        
        count = sum(1 for word in value_keywords if word in text)
        
        return min(count * 0.3, 1.0)
    
    def _evaluate_stage1_potential(self, post: Dict) -> float:
        """Stage1突破ポテンシャルを評価（0.0-1.0）"""
        predicted_stage = post.get("predicted_stage", "Stage1")
        
        if "Stage3" in predicted_stage or "Stage4" in predicted_stage:
            return 0.9
        elif "Stage2" in predicted_stage:
            return 0.7
        else:
            return 0.5
