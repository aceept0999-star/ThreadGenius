"""
AI投稿生成モジュール
Claude APIを使用して、2026年最新Threadsアルゴリズムに最適化された投稿を生成

高品質運用:
- 2パス生成: Draft → Humanize（丁寧＋会話、人間味）
- UIトグルで Calm優先（ノウハウ/数値）を切替（ui_mode_calm_priority）
- テーマ選択で topic_tag を全投稿に強制（forced_topic_tag）
- 人間味スコアを追加して上位表示を安定化
- lens を付与して UI 側で検証しやすくする（app.py expander で表示）
"""

import anthropic
from typing import List, Dict
from config import PersonaConfig, ThreadsAlgorithmRules, PostTemplate, SCORING_WEIGHTS


class ThreadsPostGenerator:
    """Threads投稿生成エンジン"""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.rules = ThreadsAlgorithmRules()

        # ===== 高品質用 =====
        self.enable_two_pass_humanize = True
        self.draft_temperature = 0.7
        self.humanize_temperature = 0.4

        # app.py から渡される UIトグル
        self.ui_mode_calm_priority = False

        # app.py から渡される テーマタグ（A＝全投稿で統一）
        self.forced_topic_tag = None  # 例: "#Web集客"

        # AIっぽさを感じやすい定型句（必要なら拡張）
        self.ai_like_phrases = [
            "結論から言うと", "本質的には", "重要なのは", "要するに", "つまり",
            "〜かもしれません", "徹底的に", "最適化", "網羅的", "体系的に",
            "ご紹介します", "解説します", "メリット・デメリット",
        ]

    # =========================
    # PUBLIC
    # =========================
    def generate_posts(
        self,
        persona: PersonaConfig,
        news_content: str,
        num_variations: int = 5
    ) -> List[Dict]:
        """ペルソナとニュースから複数の投稿案を生成"""

        # 1) Draft生成（JSON配列）
        prompt = self._build_prompt_draft(persona, news_content, num_variations)

        response = self.client.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=4000,
            temperature=self.draft_temperature,
            messages=[{"role": "user", "content": prompt}]
        )

        posts = self._parse_response(response.content[0].text, expected_count=num_variations)

        # Draft段階でも念のため lens を補完（UIで N/A を減らす）
        posts = [self._ensure_lens(p) for p in posts]

        # 2) Humanize（2パス）：Warm/Calm混在（Calm優先トグル対応）
        if self.enable_two_pass_humanize:
            if self.ui_mode_calm_priority:
                calm_n, warm_n = 4, 1
            else:
                warm_n, calm_n = 3, 2

            humanized_pool: List[Dict] = []
            for p in posts[:num_variations]:
                calm_post = self._humanize_post(p, persona, style_mode="polite_calm")
                if calm_post:
                    humanized_pool.append(calm_post)

                warm_post = self._humanize_post(p, persona, style_mode="polite_warm")
                if warm_post:
                    humanized_pool.append(warm_post)

            calm_posts = [x for x in humanized_pool if x.get("style_mode") == "polite_calm"]
            warm_posts = [x for x in humanized_pool if x.get("style_mode") == "polite_warm"]

            posts = (calm_posts[:calm_n] + warm_posts[:warm_n])

        # 3) ★タグ統一（A）: forced_topic_tag があれば全投稿に強制適用
        posts = self._apply_forced_topic_tag(posts)

        # 4) スコアリング（既存 + 人間味）
        scored_posts = [self._score_post(post, persona) for post in posts]
        scored_posts.sort(key=lambda x: x.get("score", 0), reverse=True)

        return scored_posts[:num_variations]

    def _apply_forced_topic_tag(self, posts: List[Dict]) -> List[Dict]:
        """A運用：テーマ選択タグを全投稿に強制"""
        tag = (self.forced_topic_tag or "").strip()
        if not tag:
            return posts

        # 念のため "#" で始まっていなければ付ける
        if not tag.startswith("#"):
            tag = "#" + tag

        for p in posts:
            p["topic_tag"] = tag
        return posts

    def _ensure_lens(self, post: Dict) -> Dict:
        """lens が無い場合の安全なデフォルト付与（UI表示のN/A回避）"""
        if not post.get("lens"):
            post["lens"] = "N/A"
        return post

    # =========================
    # PROMPTS
    # =========================
    def _build_prompt_draft(self, persona: PersonaConfig, news_content: str, num_variations: int) -> str:
        """1パス目：構造・論点を作る（ここでは整いすぎてもOK）"""
        prompt = f"""
<role>
あなたは「2026年最新のThreadsアルゴリズム」を理解したプロのSNS投稿クリエイターです。
</role>

<persona>
名前：{persona.name}
専門分野：{persona.specialty}
口調：{persona.tone}
価値観：{persona.values}
ターゲット：{persona.target_audience}
目標：{persona.goals}
</persona>

<rules>
【2026年Threadsアルゴリズムの鉄則】
1. 「いいね」より「リプライ（会話）」が重要
2. テキスト中心（AIが内容を理解できる）
3. トピックタグは1つだけ
4. 500文字以内で「ツッコミ代」を残す（完璧すぎない）
5. 末尾は必ず質問で終える（番号回答が理想）
</rules>

<structure>
【投稿構成テンプレート】
1. 冒頭（1-2行）：スクロールを止めるフック
2. 本文（3-8行）：共感 or 有益情報
3. 末尾（1-2行）：会話を誘発する質問（番号回答）
</structure>

<context>
【ニュース内容】
{news_content}
</context>

<task>
上記を基に、{persona.name}として{num_variations}つの投稿案を作成してください。
</task>

<constraints>
✓ 各投稿は500文字以内
✓ {persona.tone}の口調を守る
✓ 末尾に必ず質問（番号回答推奨）を入れる
✓ トピックタグは1つだけ
✓ ステージ(Stage1-4)を予測して入れる
✓ 文字数は140〜220字（厳守）
✓ 3〜6行で改行（読みやすさ優先）
✓ 文章は「短文・断定寄り」。丁寧すぎる前置き・長文説明は禁止
✓ 本文に必ず次のうち1語以上を含める：導線 / LP / オファー / 信頼 / 計測
✓ CTAは必ず番号回答で終える（番号は固定）：
  1導線 2LP 3オファー 4信頼 5計測
✓ ただし、CTAの「問いかけ文」は毎回変える（同じ文を連発しない）

</constraints>

<output_rules>
【最重要：出力ルール】
- 出力は「JSONのみ」
- 説明文、見出し、注釈、コードフェンス（```）、箇条書き、前置きは一切禁止
- 先頭文字は必ず '['、末尾文字は必ず ']'
</output_rules>

<output_format>
[
  {{
    "post_text": "投稿本文（500文字以内）",
    "topic_tag": "#トピック名",
    "hook": "冒頭のフック部分",
    "body": "本文の核心部分",
    "cta": "末尾の質問/呼びかけ",
    "predicted_stage": "Stage1-4",
    "conversation_trigger": "会話を誘発するポイント",
    "reasoning": "なぜこの構成にしたか（100文字以内）",
    "lens": "N/A"
  }}
]
</output_format>
"""
        return prompt.strip()

    def _build_prompt_humanize(self, persona: PersonaConfig, draft_post: Dict, style_mode: str) -> str:
        """2パス目：人間味（丁寧＋会話）に寄せるリライト専用プロンプト"""
        draft_text = (draft_post.get("post_text") or "").strip()

        # 強制タグがあればそれを優先（Humanizeの段階でもブレ防止）
        topic_tag = (self.forced_topic_tag or draft_post.get("topic_tag") or "#ビジネス").strip()
        if not topic_tag.startswith("#"):
            topic_tag = "#" + topic_tag

        predicted_stage = draft_post.get("predicted_stage", "Stage2")
        lens = draft_post.get("lens", "N/A")

        if style_mode == "polite_calm":
            mode_label = "polite_calm（丁寧で落ち着いた会話：ノウハウ/数値向き）"
            vocab_hint = "語彙は落ち着き（ご相談でよく/現場では/ここが鍵です）。砕けすぎ禁止。"
            warmth_hint = "硬くしすぎないために、会話のクッションを1つだけ入れる。"
        else:
            mode_label = "polite_warm（丁寧＋少しくだける会話：距離が近い）"
            vocab_hint = "少しだけ近い言い回し（これ、よくあります/ここ意外と抜けます）。ただし軽すぎ禁止。"
            warmth_hint = "丁寧語は維持しつつ、温度を少し上げる。"

        prompt = f"""
<role>
あなたはThreadsの投稿を「プロっぽいが会話的（丁寧＋質問で巻き込む）」に整える編集者です。
</role>

<persona>
名前：{persona.name}
専門分野：{persona.specialty}
口調：{persona.tone}
価値観：{persona.values}
ターゲット：{persona.target_audience}
目標：{persona.goals}
</persona>

<style_mode>
{mode_label}
</style_mode>

<input>
以下は下書きです。内容（言いたいこと・主張・例・論点）は維持して、文の“人間味”だけを上げてください。
下書き本文:
{draft_text}
</input>

<human_style_spec>
【文章品質（人間味）ルール：最重要】
- 丁寧語（です・ます）を基本に、会話の温度感を出す（硬すぎない）
- {vocab_hint}
- {warmth_hint}
- 1投稿につき「現場の一言」or「自分の小さい体験」を1つだけ入れる
- “整いすぎ”禁止：説明し切らず、相手が返したくなる余白を残す
- 断定しすぎず、逃げすぎない：「〜かもしれません」は最大1回まで
- 見出し風の「Hook:」「Body:」「CTA:」などは本文に出さない
- AIっぽい定型句は避ける（例：結論から言うと／本質的には／重要なのは／要するに）
- 最後は必ず質問。Yes/Noで終わらせず、選択式 or 体験想起（例：どこで詰まった？どっち派？）
- 文字数は140〜220字（厳守）
- 3〜6行で改行（読みやすさ優先）
- 文章は「短文・断定寄り」。丁寧すぎる前置き・長文説明は禁止
- 本文に必ず次のうち1語以上を含める：導線 / LP / オファー / 信頼 / 計測
- 最後は必ず番号回答のCTAで終える（番号は固定）：
  1導線 2LP 3オファー 4信頼 5計測
- ただしCTAの「問いかけ文」は毎回変える（同じ文を連発しない）
- CTA問いかけ文は次の候補から毎回どれか1つ：
  「あなたはどれ？番号でOK」
  「今いちばん詰まってるのは？1〜5で」
  「最初に直すならどれ？数字で返信して」
  「1個だけ選ぶなら？1〜5」
  「今週やるならどれ？1〜5」
  「まず潰すなら？1〜5」
- topic_tagは必ずこの1つ：{topic_tag}

</human_style_spec>

<output_rules>
【出力ルール】
- 出力はJSONのみ（説明文禁止）
- 先頭は '{{'、末尾は '}}'
</output_rules>

<output_format>
{{
  "post_text": "改善後の投稿本文（500文字以内）",
  "topic_tag": "{topic_tag}",
  "hook": "本文に含まれるフックの要旨（短く）",
  "body": "本文に含まれる核（短く）",
  "cta": "末尾の質問文（短く）",
  "predicted_stage": "{predicted_stage}",
  "conversation_trigger": "返したくなる理由（短く）",
  "reasoning": "改善の意図（100文字以内）",
  "style_mode": "{style_mode}",
  "lens": "{lens}"
}}
</output_format>
"""
        return prompt.strip()

    # =========================
    # HUMANIZE
    # =========================
    def _humanize_post(self, post: Dict, persona: PersonaConfig, style_mode: str) -> Dict:
        """2パス目で“人間味”に寄せる。失敗時は原文を返す（style_mode付与）。"""
        prompt = self._build_prompt_humanize(persona, post, style_mode=style_mode)

        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1200,
                temperature=self.humanize_temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            rewritten = self._parse_single_json_object(response.content[0].text)
            if not rewritten:
                post["style_mode"] = style_mode
                post = self._ensure_lens(post)
                return post

            # topic_tag は強制（A）
            if self.forced_topic_tag:
                rewritten["topic_tag"] = self.forced_topic_tag if self.forced_topic_tag.startswith("#") else f"#{self.forced_topic_tag}"

            # lens が欠けた場合も補う
            rewritten = self._ensure_lens(rewritten)

            # post_text が空なら戻す
            if not (rewritten.get("post_text") or "").strip():
                post["style_mode"] = style_mode
                post = self._ensure_lens(post)
                return post
                
            # ★B案：末尾CTA強制（ローテ＋重複除去＋220字上限）
            # post_index は draft_post の predicted_stage 等からは取れないので、
            # ひとまず style_mode ごとの生成順を使う：fallbackとして hash を使う
            post_index = int(abs(hash((draft_text, style_mode))) % 1000)
            rewritten["post_text"] = self._enforce_short_cta(
             rewritten.get("post_text") or "",
             post_index=post_index,
             max_chars=220
             )
             
            # 500字カット（保険）
            rewritten["post_text"] = (rewritten.get("post_text") or "")[:500]

            # 質問が無い場合は補う（保険）
            if "？" not in rewritten["post_text"] and "?" not in rewritten["post_text"]:
                rewritten["post_text"] = (rewritten["post_text"][:460] + "\n\nあなたはどこで詰まりましたか？")[:500]

            rewritten["style_mode"] = style_mode
            return rewritten

        except Exception:
            post["style_mode"] = style_mode
            post = self._ensure_lens(post)
            return post

    def _parse_single_json_object(self, response_text: str) -> Dict:
        """Humanizeの戻り（JSONオブジェクト）を抽出してdictにする"""
        import json
        import re

        text = (response_text or "").strip()
        m = re.search(r'\{\s*".*"\s*\}', text, re.DOTALL)
        if not m:
            return {}

        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return {}

        return {}

    # =========================
    # PARSE（現行互換）
    # =========================
    def _parse_response(self, response_text: str, expected_count: int = 5) -> List[Dict]:
        """Claude APIのレスポンスをパース（JSON優先、ダメなら分割復元）"""
        import json
        import re

        text = (response_text or "").strip()

        first_array = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
        if first_array:
            try:
                posts = json.loads(first_array.group(0))
                if isinstance(posts, list) and posts:
                    return posts
            except json.JSONDecodeError:
                pass

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

        return self._fallback_parse(text, expected_count=expected_count)

    def _fallback_parse(self, text: str, expected_count: int = 5) -> List[Dict]:
        """フォールバック：テキストから投稿を抽出して expected_count 件へ復元"""
        import re

        raw = (text or "").strip()
        if not raw:
            return [{
                "post_text": "",
                "topic_tag": self.forced_topic_tag or "#ビジネス",
                "predicted_stage": "Stage2",
                "conversation_trigger": "質問を含む",
                "reasoning": "空レスポンスのためフォールバック",
                "lens": "N/A"
            }]

        parts = re.split(r'【\s*投稿\s*\d+\s*】', raw)
        parts = [p.strip() for p in parts if p.strip()]

        if len(parts) < 2:
            parts2 = re.split(r'投稿\s*\d+\s*[:：]?', raw)
            parts2 = [p.strip() for p in parts2 if p.strip()]
            if len(parts2) >= 2:
                parts = parts2

        chunks: List[str] = []

        if len(parts) >= 1:
            if len(parts) >= expected_count:
                chunks = parts[:expected_count]
            else:
                blocks = [b.strip() for b in re.split(r'\n\s*\n', raw) if b.strip()]
                if len(blocks) >= expected_count:
                    chunks = blocks[:expected_count]
                else:
                    step = max(180, min(500, max(1, len(raw) // expected_count)))
                    tmp = [raw[i:i+step].strip() for i in range(0, len(raw), step)]
                    tmp = [t for t in tmp if t]
                    chunks = (tmp + [""] * expected_count)[:expected_count]

        posts: List[Dict] = []
        for c in chunks[:expected_count]:
            c2 = c.strip()
            if c2 and ("？" not in c2 and "?" not in c2):
                c2 = (c2[:460] + "\n\n今いちばん詰まっているのはどこですか？")[:500]
            posts.append({
                "post_text": c2[:500],
                "topic_tag": self.forced_topic_tag or "#ビジネス",
                "predicted_stage": "Stage2",
                "conversation_trigger": "質問を含む",
                "reasoning": "JSON取得に失敗したためテキストを分割して復元",
                "lens": "N/A"
            })

        return posts

    # =========================
    # SCORING（現行 + 人間味）
    # =========================
    def _score_post(self, post: Dict, persona: PersonaConfig) -> Dict:
        """投稿をスコアリング（0-100点） + 人間味スコア"""

        score = 0
        details = {}

        conversation_score = self._evaluate_conversation_trigger(post)
        score += conversation_score * SCORING_WEIGHTS["conversation_trigger"] * 100
        details["conversation_trigger"] = conversation_score

        trend_score = self._evaluate_trend_relevance(post)
        score += trend_score * SCORING_WEIGHTS["trend_relevance"] * 100
        details["trend_relevance"] = trend_score

        emotional_score = self._evaluate_emotional_impact(post)
        score += emotional_score * SCORING_WEIGHTS["emotional_impact"] * 100
        details["emotional_impact"] = emotional_score

        value_score = self._evaluate_value_provided(post)
        score += value_score * SCORING_WEIGHTS["value_provided"] * 100
        details["value_provided"] = value_score

        stage1_score = self._evaluate_stage1_potential(post)
        score += stage1_score * SCORING_WEIGHTS["stage1_potential"] * 100
        details["stage1_potential"] = stage1_score

        human_score = self._evaluate_human_likeness(post)
        score += human_score * 12
        details["human_likeness"] = human_score

        post["score"] = round(score, 2)
        post["score_details"] = details
        return post

    def _evaluate_human_likeness(self, post: Dict) -> float:
        """人間味評価（0.0-1.0）"""
        text = (post.get("post_text") or "")
        cta = (post.get("cta") or "")

        s = 0.0

        polite = sum(1 for w in ["です", "ます", "でした", "ません"] if w in text)
        s += min(polite * 0.12, 0.25)

        if any(w in text for w in ["あなた", "みなさん", "皆さん", "でしょうか"]):
            s += 0.18

        if "？" in text or "?" in text:
            s += 0.22
            if any(w in text for w in ["どっち", "どちら", "何番", "どれ", "どの", "どこ"]):
                s += 0.10

        if any(w in text for w in ["正直", "ぶっちゃけ", "これ、", "これって", "よくあります", "相談で"]):
            s += 0.18

        penalty = 0.0
        for p in self.ai_like_phrases:
            if p in text:
                penalty += 0.08
        s -= min(penalty, 0.35)

        if len(cta.strip()) < 6:
            s -= 0.05

        return max(0.0, min(s, 1.0))

    # ---- 既存評価（現行踏襲） ----
    def _evaluate_conversation_trigger(self, post: Dict) -> float:
        text = post.get("post_text", "").lower()
        cta = post.get("cta", "").lower()

        score = 0.0
        if "?" in text or "？" in text:
            score += 0.4

        opinion_keywords = ["どう思", "考え", "意見", "教えて", "どうです", "どっち", "どれ"]
        if any(kw in text for kw in opinion_keywords):
            score += 0.3

        if len(cta) > 10:
            score += 0.3

        return min(score, 1.0)

    def _evaluate_trend_relevance(self, post: Dict) -> float:
        if post.get("topic_tag"):
            return 0.8
        return 0.4

    def _evaluate_emotional_impact(self, post: Dict) -> float:
        text = post.get("post_text", "")
        emotional_words = ["驚", "感動", "最高", "やばい", "すごい", "衝撃", "共感", "涙"]
        count = sum(1 for word in emotional_words if word in text)
        return min(count * 0.25, 1.0)

    def _evaluate_value_provided(self, post: Dict) -> float:
        text = post.get("post_text", "")
        value_keywords = ["方法", "コツ", "ポイント", "秘訣", "戦略", "結果", "データ", "実践", "手順"]
        count = sum(1 for word in value_keywords if word in text)
        return min(count * 0.3, 1.0)

    def _evaluate_stage1_potential(self, post: Dict) -> float:
        predicted_stage = post.get("predicted_stage", "Stage1")
        if "Stage3" in predicted_stage or "Stage4" in predicted_stage:
            return 0.9
        elif "Stage2" in predicted_stage:
            return 0.7
        else:
            return 0.5
