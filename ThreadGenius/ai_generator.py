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
    
    def __init__(
        self,
        api_key: str,
        enable_two_pass_humanize: bool = True,
        draft_temperature: float = 0.7,
        humanize_temperature: float = 0.4,
    ):
        api_key = (api_key or "").strip()
        if not api_key:
           raise ValueError("Anthropic api_key is empty. Check Streamlit secrets / env var.")

        # 認証はここで一本化（明示）
        self.client = anthropic.Anthropic(api_key=api_key)

        self.enable_two_pass_humanize = enable_two_pass_humanize
        self.draft_temperature = draft_temperature
        self.humanize_temperature = humanize_temperature

        self.ui_mode_calm_priority = False
        self.forced_topic_tag = None

    def _pick_style_modes(self, n: int) -> List[str]:
        """UI toggle rule: Calm優先なら 4 Calm + 1 Warm, それ以外は 3 Warm + 2 Calm."""
        n = int(n or 5)
        if getattr(self, "ui_mode_calm_priority", False):
            base = ["calm"] * max(0, n - 1) + ["warm"]
        else:
            warm = min(3, n)
            calm = max(0, n - warm)
            base = ["warm"] * warm + ["calm"] * calm
        return (base + ["calm"] * n)[:n]

    # =========================
    # PROMPTS
    # =========================
    def _build_prompt_draft(
        self,
        persona: PersonaConfig,
        news_content: str,
        num_variations: int,
    ) -> str:
        tag = (self.forced_topic_tag or "").strip()
        if tag and not tag.startswith("#"):
            tag = "#" + tag
        if not tag:
            tag = "#ビジネス"

        persona_name = getattr(persona, "name", "") or "N/A"

        return f"""
You are a Japanese social media copywriter. Create {num_variations} Threads posts optimized for engagement.

OUTPUT RULES (MUST FOLLOW):
- Output ONLY valid JSON (no prose, no markdown fences).
- Output must be a JSON array of exactly {num_variations} objects.
- Each object MUST contain these keys exactly:
  - post_text (string): Japanese Threads post text (<= 220 chars)
  - topic_tag (string): always "{tag}"
  - predicted_stage (string)
  - conversation_trigger (string)
  - reasoning (string)
  - lens (string)

CONTEXT:
Persona: {persona_name}
News content:
{news_content}
""".strip()

    def _build_prompt_humanize(
        self,
        persona: PersonaConfig,
        draft_post: Dict,
        style_mode: str,
    ) -> str:
        tag = (self.forced_topic_tag or "").strip()
        if tag and not tag.startswith("#"):
            tag = "#" + tag
        if not tag:
            tag = "#ビジネス"

        base_text = (draft_post.get("post_text") or "").strip()

        return f"""
Rewrite the following Japanese Threads post to match style_mode="{style_mode}".

OUTPUT RULES (MUST FOLLOW):
- Output ONLY valid JSON (no prose, no markdown fences).
- Output must be ONE JSON object.
- Return ALL keys exactly:
  - post_text (string): non-empty, <= 220 chars
  - topic_tag (string): always "{tag}"
  - predicted_stage (string)
  - conversation_trigger (string)
  - reasoning (string)
  - lens (string)

INPUT (draft_post.post_text):
{base_text}
""".strip()

    # =========================
    # PUBLIC
    # =========================
    def generate_posts(
        self,
        persona: PersonaConfig,
        news_content: str,
        num_variations: int = 5,
    ) -> List[Dict]:
        """Generate Threads posts. Always returns exactly num_variations items."""
        num_variations = int(num_variations or 5)
        if num_variations <= 0:
            num_variations = 5

        prompt = self._build_prompt_draft(persona, news_content, num_variations)

        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4000,
                temperature=self.draft_temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            logging.exception("ERROR draft messages.create failed")
            posts = self._fallback_parse("", expected_count=num_variations)
            posts = self._apply_forced_topic_tag(posts)
            posts = [self._ensure_lens(p) for p in posts]
            return [self._score_post(p, persona) for p in posts][:num_variations]

        draft_text = "".join(
            b.text
            for b in (getattr(response, "content", []) or [])
            if getattr(b, "type", "") == "text" and getattr(b, "text", None)
        )

        logging.warning("DEBUG draft_text len: %s", len(draft_text))
        logging.warning("DEBUG draft_text head: %s", draft_text[:400])

        posts = self._parse_response(draft_text, expected_count=num_variations)
        if not isinstance(posts, list):
            posts = []

        posts = [p for p in posts if isinstance(p, dict)]
        posts = [self._ensure_lens(p) for p in posts]
        posts = self._apply_forced_topic_tag(posts)

        if getattr(self, "enable_two_pass_humanize", True):
            style_modes = self._pick_style_modes(num_variations)
            humanized: List[Dict] = []
            for i in range(min(len(posts), num_variations)):
                try:
                    humanized.append(self._humanize_post(posts[i], persona, style_modes[i]))
                except Exception:
                    logging.exception("ERROR humanize failed at index=%s", i)
                    p = dict(posts[i])
                    p["style_mode"] = style_modes[i]
                    humanized.append(self._ensure_lens(p))
            posts = humanized

        scored_posts = [self._score_post(p, persona) for p in posts]
        scored_posts.sort(key=lambda x: float(x.get("score", 0.0) or 0.0), reverse=True)

        missing = num_variations - len(scored_posts)
        if missing > 0:
            fillers = self._fallback_parse("", expected_count=missing)
            fillers = self._apply_forced_topic_tag(fillers)
            fillers = [self._ensure_lens(f) for f in fillers]
            fillers = [self._score_post(f, persona) for f in fillers]
            scored_posts.extend(fillers)

        fixed: List[Dict] = []
        for p in scored_posts[:num_variations]:
            if not isinstance(p, dict):
                p = {}
            if not (p.get("post_text") or "").strip():
                fb = self._fallback_parse("", expected_count=1)[0]
                fb["topic_tag"] = (p.get("topic_tag") or fb.get("topic_tag"))
                fb["lens"] = (p.get("lens") or fb.get("lens") or "N/A")
                fb["style_mode"] = (p.get("style_mode") or fb.get("style_mode") or "draft")
                p = fb
            fixed.append(self._ensure_lens(p))

        logging.warning("DEBUG posts_final_count: %s", len(fixed))
        return fixed

    # =========================
    # HUMANIZE
    # =========================
    def _humanize_post(self, post: Dict, persona: PersonaConfig, style_mode: str) -> Dict:
        prompt = self._build_prompt_humanize(persona, post, style_mode=style_mode)

        try:
            response = self.client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=1200,
                temperature=self.humanize_temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            human_text = "".join(
                b.text
                for b in getattr(response, "content", []) or []
                if getattr(b, "type", "") == "text" and getattr(b, "text", None)
            )
            logging.warning("DEBUG human_text len: %s", len(human_text))
            logging.warning("DEBUG human_text head: %s", human_text[:400])

            rewritten = self._parse_single_json_object(human_text)
            if not rewritten:
                post["style_mode"] = style_mode
                return self._ensure_lens(post)

            rewritten["style_mode"] = style_mode

            if self.forced_topic_tag:
                rewritten["topic_tag"] = (
                    self.forced_topic_tag
                    if self.forced_topic_tag.startswith("#")
                    else f"#{self.forced_topic_tag}"
                )

            rewritten = self._ensure_lens(rewritten)

            if not (rewritten.get("post_text") or "").strip():
                post["style_mode"] = style_mode
                return self._ensure_lens(post)

            base_text = (post.get("post_text") or "")
            post_index = int(abs(hash((base_text, style_mode))) % 1000)

            if hasattr(self, "_enforce_short_cta"):
                try:
                    rewritten["post_text"] = self._enforce_short_cta(
                        rewritten.get("post_text") or "",
                        post_index=post_index,
                        max_chars=220,
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
        import json
        import re

        text = (response_text or "").strip()

        try:
            posts = json.loads(text)
            if isinstance(posts, list) and posts:
                return posts
        except Exception:
            pass

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
        post["score"] = float(post.get("score", 0))
        return post
