"""
AI投稿生成モジュール
Claude APIを使用して、2026年最新Threadsアルゴリズムに最適化された投稿を生成
"""

import anthropic
from typing import List, Dict
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

        # レスポンスをパース（期待件数も渡す）
        posts = self._parse_response(response.content[0].text, expected_count=num_variations)

        # スコアリング
        scored_posts = [self._score_post(post, persona) for post in posts]

        # スコア順にソート
        scored_posts.sort(key=lambda x: x.get('score', 0), reverse=True)

        # 念のため、返却数を num_variations に丸める（多すぎる場合）
        return scored_posts[:num_variations]

    def _build_prompt(self, persona: PersonaConfig, news_content: str, num_variations: int) -> str:
        """Claude APIに送信するプロンプトを構築"""

        prompt = f"""あなたは「2026年最新のThreadsアルゴリズム」を理解したプロのSNS投稿クリエイターです。

【あなたのペルソナ】
名前：{persona.name}
専門分野：{persona.specialty}
口調：{persona.tone}
価値観：{persona.values}
ターゲット：{persona.target_audience}
目標：{persona.goals}

【2026年Threadsアルゴリズムの鉄則】
1. 「いいね」より「リプライ（会話）」が重要
2. テキスト中心（AIが内容を理解できる）
3. トピックタグは1つだけ
4. 500文字以内で「ツッコミ代」を残す（完璧すぎない）
5. 末尾は必ず質問で終える（番号回答が理想）

【投稿構成テンプレート】
1. 冒頭（1-2行）：スクロールを止めるフック
2. 本文（3-8行）：共感 or 有益情報
3. 末尾（1-2行）：会話を誘発する質問（番号回答）

【ニュース内容】
{news_content}

【タスク】
上記を基に、{persona.name}として{num_variations}つの投稿案を作成してください。

【必須条件】
✓ 各投稿は500文字以内
✓ {persona.tone}の口調を守る
✓ 末尾に必ず質問（番号回答推奨）を入れる
✓ トピックタグは1つだけ
✓ ステージ(Stage1-4)を予測して入れる

【最重要：出力ルール】
- 出力は「JSONのみ」
- 説明文、見出し、注釈、コードフェンス（```）、箇条書き、前置きは一切禁止
- 先頭文字は必ず '['、末尾文字は必ず ']'

【出力形式（JSON配列）】
[
  {{
    "post_text": "投稿本文（500文字以内）",
    "topic_tag": "#トピック名",
    "hook": "冒頭のフック部分",
    "body": "本文の核心部分",
    "cta": "末尾の質問/呼びかけ",
    "predicted_stage": "Stage1-4",
    "conversation_trigger": "会話を誘発するポイント",
    "reasoning": "なぜこの構成にしたか（100文字以内）"
  }}
]
"""
        return prompt

    def _parse_response(self, response_text: str, expected_count: int = 5) -> List[Dict]:
        """Claude APIのレスポンスをパース（JSON優先、ダメなら分割復元）"""
        import json
        import re

        text = (response_text or "").strip()

        # 1) まず「フェンス無しのJSON配列」を最優先で取りに行く
        #    先頭に説明文が混じっても、最初に現れる [ ... ] を抽出する
        first_array = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
        if first_array:
            try:
                posts = json.loads(first_array.group(0))
                if isinstance(posts, list) and posts:
                    return posts
            except json.JSONDecodeError:
                pass

        # 2) 次に ```json ... ``` 形式（元コード互換）
        fenced = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if fenced:
            try:
                posts = json.loads(fenced.group(1))
                if isinstance(posts, list) and posts:
                    return posts
                if isinstance(posts, dict):
                    return [posts]
            except json.JSONDecodeError:
                pass

        # 3) それでもダメならフォールバック（expected_count件へ復元）
        return self._fallback_parse(text, expected_count=expected_count)

    def _fallback_parse(self, text: str, expected_count: int = 5) -> List[Dict]:
        """
        フォールバック：テキストから投稿を抽出して expected_count 件へ復元
        - 「【投稿1】」「【投稿 1】」などがあれば、それで分割
        - なければ「投稿1」「投稿 1」でも分割
        - それも無ければ、文字数で分割して件数を作る
        """
        import re

        raw = (text or "").strip()
        if not raw:
            return [{
                "post_text": "",
                "topic_tag": "#ビジネス",
                "predicted_stage": "Stage2",
                "conversation_trigger": "質問を含む",
                "reasoning": "空レスポンスのためフォールバック"
            }]

        # 1) 「【投稿1】」分割
        parts = re.split(r'【\s*投稿\s*\d+\s*】', raw)
        parts = [p.strip() for p in parts if p.strip()]

        # 2) 「投稿1」分割（角括弧が無いケース）
        if len(parts) < 2:
            parts2 = re.split(r'投稿\s*\d+\s*[:：]?', raw)
            parts2 = [p.strip() for p in parts2 if p.strip()]
            if len(parts2) >= 2:
                parts = parts2

        chunks: List[str] = []

        if len(parts) >= 1:
            # partsが長文1つだけの場合もあるので、長さでさらに分割する
            if len(parts) >= expected_count:
                chunks = parts[:expected_count]
            else:
                # 1個しかない/少ないなら、改行ブロックで切って足りなければ文字数分割
                # 「投稿として成立しそうな塊」を優先
                blocks = [b.strip() for b in re.split(r'\n\s*\n', raw) if b.strip()]
                if len(blocks) >= expected_count:
                    chunks = blocks[:expected_count]
                else:
                    # 文字数分割（最低でも expected_count を満たす）
                    step = max(180, min(500, max(1, len(raw) // expected_count)))
                    tmp = [raw[i:i+step].strip() for i in range(0, len(raw), step)]
                    tmp = [t for t in tmp if t]
                    chunks = (tmp + [""] * expected_count)[:expected_count]

        # 投稿辞書を組み立て
        posts: List[Dict] = []
        for c in chunks[:expected_count]:
            # 末尾が質問で終わってない場合、軽く補う（会話誘発の最低保証）
            c2 = c.strip()
            if c2 and ("？" not in c2 and "?" not in c2):
                c2 = (c2[:460] + "\n\n今いちばん詰まっているのはどこですか？")[:500]
            posts.append({
                "post_text": c2[:500],
                "topic_tag": "#ビジネス",
                "predicted_stage": "Stage2",
                "conversation_trigger": "質問を含む",
                "reasoning": "JSON取得に失敗したためテキストを分割して復元"
            })

        return posts

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
        opinion_keywords = ["どう思", "考え", "意見", "教えて", "どうです", "どっち", "どれ"]
        if any(kw in text for kw in opinion_keywords):
            score += 0.3

        # CTAが具体的か
        if len(cta) > 10:
            score += 0.3

        return min(score, 1.0)

    def _evaluate_trend_relevance(self, post: Dict) -> float:
        """トレンド適合性を評価（0.0-1.0）"""
        if post.get("topic_tag"):
            return 0.8
        return 0.4

    def _evaluate_emotional_impact(self, post: Dict) -> float:
        """感情的インパクトを評価（0.0-1.0）"""
        text = post.get("post_text", "")

        emotional_words = ["驚", "感動", "最高", "やばい", "すごい", "衝撃", "共感", "涙"]
        count = sum(1 for word in emotional_words if word in text)

        return min(count * 0.25, 1.0)

    def _evaluate_value_provided(self, post: Dict) -> float:
        """提供価値を評価（0.0-1.0）"""
        text = post.get("post_text", "")

        value_keywords = ["方法", "コツ", "ポイント", "秘訣", "戦略", "結果", "データ", "実践", "手順"]
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
