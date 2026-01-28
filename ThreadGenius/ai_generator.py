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

from __future__ import annotations

import logging
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
            messages=[{"role": "user", "content": prompt}],
        )

        # Claude応答は複数ブロックになる場合があるため必ず結合
        draft_text = "".join(
            b.text
            for b in getattr(response, "content", []) or []
            if getattr(b, "type", "") == "text" and getattr(b, "text", None)
        )

        # Streamlit Cloud の Logs に確実に出す（printより安定）
        logging.warning("DEBUG draft_text len: %s", len(draft_text))
        logging.warning("DEBUG draft_text head: %s", draft_text[:400])

        posts = self._parse_response(draft_text, expected_count=num_variations)

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

            # ★必ず num_variations 件にする：不足分は Draft を追加して埋める
            if len(posts) < num_variations:
                need = num_variations - len(posts)
                used = set((p.get("post_text") or "").strip() for p in posts)
                fillers: List[Dict] = []

                # ここは response.content[0].text を使わず、結合済み draft_text を再利用する
                draft_posts = self._parse_response(draft_text, expected_count=num_variations) or []

                for d in (self._ensure_lens(x) for x in draft_posts):
                    t = (d.get("post_text") or "").strip()
                    if t and t not in used:
                        d["style_mode"] = d.get("style_mode") or "draft"
                        fillers.append(d)
                        used.add(t)
                    if len(fillers) >= need:
                        break

                posts = (posts + fillers)[:num_variations]

        # 3) ★タグ統一（A）: forced_topic_tag があれば全投稿に強制適用
        posts = self._apply_forced_topic_tag(posts)

        # 4) スコアリング（既存 + 人間味）
        scored_posts = [self._score_post(post, persona) for post in posts]
        scored_posts.sort(key=lambda x: x.get("score", 0), reverse=True)

        # ★最終保険：どうしても欠けたらフォールバックで穴埋め
        if len(scored_posts) < num_variations:
            missing = num_variations - len(scored_posts)
            fillers = self._fallback_parse("", expected_count=missing)
            fillers = [
                self._score_post(self._apply_forced_topic_tag([f])[0], persona)
                for f in fillers
            ]
            scored_posts = scored_posts + fillers

        return scored_posts[:num_variations]

    # =========================
    # PROMPTS（※あなたの既存実装を残す想定）
    # =========================
    def _build_prompt_draft(self, persona: PersonaConfig, news_content: str, num_variations: int) -> str:
    tag = (self.forced_topic_tag or "").strip()
    if tag and not tag.startswith("#"):
        tag = "#" + tag
    if not tag:
        tag = "#ビジネス"

    return f"""
    You are a Japanese social media copywriter specialized in Threads.

    TASK:
    Create {num_variations} Threads posts based on the given persona and news.

    OUTPUT RULES (MUST FOLLOW):
    - Output ONLY valid JSON. No prose. No markdown. No code fences.
    - Output must be a JSON array of exactly {num_variations} objects.
    - Each object MUST contain these keys (exactly these names):
     - post_text (string): Japanese Threads post text (<= 220 chars)
     - topic_tag (string): always "{tag}"
     - predicted_stage (string)
     - conversation_trigger (string)
     - reasoning (string)
     - lens (string)

    CONTENT:
    Persona (summary): {getattr(persona, "name", "N/A")}
    News content:
    {news_content}
    """.strip()

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

            # Claude応答は複数ブロックになる場合があるため必ず結合する
            human_text = "".join(
                b.text for b in response.content
                if getattr(b, "type", "") == "text" and getattr(b, "text", None)
            )
            logging.warning("DEBUG human_text len: %s", len(human_text))
            logging.warning("DEBUG human_text head: %s", human_text[:400])
            
            rewritten = self._parse_single_json_object(human_text)

            # パース失敗 → 元を返す
            if not rewritten:
                post["style_mode"] = style_mode
                return self._ensure_lens(post)

            # style_mode を早めに付与（後段の判定を安定化）
            rewritten["style_mode"] = style_mode

            # topic_tag は強制（A）
            if self.forced_topic_tag:
                rewritten["topic_tag"] = (
                    self.forced_topic_tag
                    if self.forced_topic_tag.startswith("#")
                    else f"#{self.forced_topic_tag}"
                )

            # lens が欠けた場合も補う
            rewritten = self._ensure_lens(rewritten)

            # post_text が空なら戻す
            if not (rewritten.get("post_text") or "").strip():
                post["style_mode"] = style_mode
                return self._ensure_lens(post)

            # 末尾CTA強制（メソッドが存在する場合のみ）
            base_text = (post.get("post_text") or "")
            post_index = int(abs(hash((base_text, style_mode))) % 1000)

            if hasattr(self, "_enforce_short_cta"):
                try:
                    rewritten["post_text"] = self._enforce_short_cta(
                        rewritten.get("post_text") or "",
                        post_index=post_index,
                        max_chars=220
                    )
                except Exception:
                    pass

            return rewritten

        except Exception:
            post["style_mode"] = style_mode
            return self._ensure_lens(post)

    # =========================
    # PARSE（最低限：起動を通す）
    # =========================
    def _parse_single_json_object(self, response_text: str) -> Dict:
        import json
        import re

        text = (response_text or "").strip()

        fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        candidates = []
        if fenced:
            candidates.append(fenced.group(1))

        candidates += re.findall(r"\{.*?\}", text, re.DOTALL)
        for c in candidates:
            try:
                obj = json.loads(c)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                continue
        return {}

    def _parse_response(self, response_text: str, expected_count: int = 5) -> List[Dict]:
        """Claude APIのレスポンスをパース（JSON優先、ダメなら分割復元）"""
        import json
        import re

        text = (response_text or "").strip()

        # 0) まず全文JSONとして読めるか（最優先）
        try:
            posts = json.loads(text)
            if isinstance(posts, list) and posts:
                return posts
        except Exception:
            pass

        # 1) ```json ... ``` を最優先
        fenced = re.search(r"```json\s*(\[.*?\])\s*```", text, re.DOTALL)
        if fenced:
            try:
                posts = json.loads(fenced.group(1))
                if isinstance(posts, list) and posts:
                    return posts
            except Exception:
                pass

        return self._fallback_parse(text, expected_count=expected_count)

    def _fallback_parse(self, text: str, expected_count: int = 5) -> List[Dict]:
        """フォールバック：最低限 expected_count 件を返す"""
        tag = self.forced_topic_tag or "#ビジネス"
        return [
            {
                "post_text": "（DEBUG）Claude返答が空/JSONパース失敗。Logsの draft_text を確認してください。",
                "topic_tag": tag,
                "predicted_stage": "Stage2",
                "conversation_trigger": "質問を含む",
                "reasoning": "フォールバック",
                "lens": "N/A",
                "style_mode": "draft",
            }
            for _ in range(expected_count)
        ]

    # =========================
    # UTIL（最低限：起動を通す）
    # =========================
    def _apply_forced_topic_tag(self, posts: List[Dict]) -> List[Dict]:
        tag = (self.forced_topic_tag or "").strip()
        if not tag:
            return posts
        if not tag.startswith("#"):
            tag = "#" + tag
        for p in posts:
            p["topic_tag"] = tag
        return posts

    def _ensure_lens(self, post: Dict) -> Dict:
        if not post.get("lens"):
            post["lens"] = "N/A"
        return post

    def _score_post(self, post: Dict, persona: PersonaConfig) -> Dict:
        # 既存実装があるなら差し替えてOK
        post["score"] = float(post.get("score", 0))
        return post
