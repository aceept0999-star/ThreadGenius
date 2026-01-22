"""
ThreadGenius - メインアプリケーション（Streamlit UI）
- 投稿生成（RSS/手動 + テンプレ + Calm優先 + テーマタグ強制）
- ペルソナ管理（CRUD）
- Threads連携（認可URL表示→code入力→投稿）
- 分析（プレースホルダ）
- マイテンプレ：GitHub（user_templates.json）へ保存/削除
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from typing import Dict, Tuple, Optional, List

import requests
import streamlit as st

from config import (
    PersonaConfig,
    DEFAULT_PERSONAS,
    DEFAULT_RSS_FEEDS,
    ANTHROPIC_API_KEY,
    THREADS_APP_ID,
    THREADS_APP_SECRET,
)
from ai_generator import ThreadsPostGenerator
from news_collector import NewsCollector
from threads_api import ThreadsAPIClient


# -------------------------
# Page
# -------------------------
st.set_page_config(
    page_title="ThreadGenius - Threads投稿自動生成",
    page_icon="🚀",
    layout="wide",
)

st.title("🚀 ThreadGenius")
st.caption("あなた専用 Threads 投稿自動生成ツール（投稿生成 / ペルソナ管理 / Threads連携 / 分析）")


# -------------------------
# GitHub Templates I/O
# -------------------------
def _gh_conf() -> Tuple[str, str, str, str]:
    """
    Streamlit Secrets から GitHub保存設定を読む。
    Secretsが無い場合も落とさない（空文字を返す）。
    """
    token = (st.secrets.get("GITHUB_TOKEN", "") or "").strip()
    owner = (st.secrets.get("GITHUB_OWNER", "") or "").strip()
    repo  = (st.secrets.get("GITHUB_REPO", "") or "").strip()
    path  = (st.secrets.get("GITHUB_TEMPLATES_PATH", "ThreadGenius/user_templates.json") or "").strip()
    return token, owner, repo, path



def github_get_file_json() -> Tuple[Dict[str, str], str]:
    """
    GitHub Contents API から JSON を取得。
    戻り: (data_dict, sha)
    404（未作成）は空dict扱い。
    取得/デコードに失敗してもアプリを落とさない（空dictで継続）。
    """
    token, owner, repo, path = _gh_conf()
    if not (token and owner and repo and path):
        return {}, ""

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)

        if r.status_code == 404:
            return {}, ""

        r.raise_for_status()

        # ここが重要：暗黙の decode を避ける
        payload = json.loads(r.content.decode("utf-8", errors="replace"))

        sha = payload.get("sha", "") or ""
        content_b64 = payload.get("content", "") or ""

        # GitHub の content は改行を含む場合がある
        content_b64 = content_b64.replace("\n", "").replace("\r", "")

        try:
            decoded = base64.b64decode(content_b64).decode("utf-8", errors="replace")
            data = json.loads(decoded)
            if isinstance(data, dict):
                data = {
                    str(k): str(v)
                    for k, v in data.items()
                    if isinstance(v, str)
                }
                return data, sha
        except Exception:
            # content が壊れている/JSONでない場合でも落とさない
            return {}, sha

        return {}, sha

    except Exception as e:
        # 起動を落とさない：UI側で原因を見せたければ st.warning にしてもOK
        # st.warning(f"GitHubテンプレ取得に失敗: {e}")
        return {}, ""
    
def _assert_github_secrets_ascii(token: str, owner: str, repo: str, path: str) -> None:
    """
    requests のヘッダは latin-1 制約があり、非ASCII（全角など）が混ざると落ちる。
    その前に検出して、分かりやすいエラーにする。
    """
    try:
        (token or "").encode("ascii")
        (owner or "").encode("ascii")
        (repo or "").encode("ascii")
        (path or "").encode("ascii")
    except UnicodeEncodeError as e:
        raise RuntimeError(
            "GitHub Secrets に全角/非ASCII文字が混入しています。"
            "Streamlit Secrets の値を『英数字と記号のみ』に修正してください。"
            f"（詳細: {e}）"
        )

def github_put_file_json(data: Dict[str, str], sha: str, commit_message: str) -> None:
    """
    GitHub Contents API へ JSON を保存（新規/更新）。
    """
    token, owner, repo, path = _gh_conf()

    # ★ここ（_gh_conf() の直後）でチェック
    _assert_github_secrets_ascii(token, owner, repo, path)

    if not (token and owner and repo and path):
        raise RuntimeError("GitHub Secrets が未設定です（GITHUB_TOKEN 等）")

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    body_text = json.dumps(data, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(body_text.encode("utf-8")).decode("utf-8")

    payload = {"message": commit_message, "content": content_b64}
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload, timeout=15)

    if r.status_code == 403:
        raise RuntimeError(
            "403 Forbidden（GitHub側で書き込み権限が不足している可能性）\n"
            f"response_text: {r.text}\n"
            f"X-Accepted-GitHub-Permissions: {r.headers.get('X-Accepted-GitHub-Permissions','')}\n"
            f"x-ratelimit-remaining: {r.headers.get('x-ratelimit-remaining','')}\n"
            f"x-ratelimit-reset: {r.headers.get('x-ratelimit-reset','')}"
        )

    r.raise_for_status()

# -------------------------
# Session State Init
# -------------------------
def _init_state():
    if "personas" not in st.session_state:
        st.session_state.personas = DEFAULT_PERSONAS.copy()

    if "rss_feeds" not in st.session_state:
        st.session_state.rss_feeds = DEFAULT_RSS_FEEDS.copy()

    if "generated_posts" not in st.session_state:
        st.session_state.generated_posts = []

    if "selected_persona_name" not in st.session_state:
        st.session_state.selected_persona_name = st.session_state.personas[0].name if st.session_state.personas else ""

    if "news_manual_text" not in st.session_state:
        st.session_state.news_manual_text = ""

    if "preset_key" not in st.session_state:
        st.session_state.preset_key = "（選択なし）"

    if "generation_mode_calm" not in st.session_state:
        st.session_state.generation_mode_calm = False

    if "selected_topic_theme" not in st.session_state:
        st.session_state.selected_topic_theme = "Web集客"

    if "generation_run_id" not in st.session_state:
        st.session_state.generation_run_id = "0"

    if "threads_client" not in st.session_state:
        st.session_state.threads_client = None

    # GitHub templates cache
    if "user_templates" not in st.session_state or "user_templates_sha" not in st.session_state:
        data, sha = github_get_file_json()
        st.session_state.user_templates = data
        st.session_state.user_templates_sha = sha


_init_state()


# -------------------------
# Helpers
# -------------------------
TOPIC_THEME_TO_TAG = {
    "Web集客": "#Web集客",
    "マーケティング": "#マーケティング",
    "店舗集客": "#店舗集客",
}


def safe_get_persona_by_name(personas: List[PersonaConfig], persona_name: str) -> Optional[PersonaConfig]:
    if not personas:
        return None
    for p in personas:
        if p.name == persona_name:
            return p
    return personas[0]


def extract_hook_body_cta(post: Dict) -> Tuple[str, str, str]:
    hook = post.get("hook") or post.get("post_hook") or ""
    body = post.get("body") or post.get("post_body") or ""
    cta = post.get("cta") or post.get("call_to_action") or post.get("post_cta") or ""
    return hook, body, cta


# -------------------------
# Sidebar (Settings)
# -------------------------
with st.sidebar:
    st.header("⚙️ 設定")

    st.subheader("🔑 APIキー")
    anthropic_key = st.text_input(
        "Anthropic API Key",
        value=ANTHROPIC_API_KEY,
        type="password",
        help="Claude APIキー",
    )
    threads_app_id = st.text_input(
        "Threads App ID",
        value=THREADS_APP_ID,
        help="Threads アプリID",
    )
    threads_app_secret = st.text_input(
        "Threads App Secret",
        value=THREADS_APP_SECRET,
        type="password",
        help="Threads アプリシークレット",
    )

    st.divider()

    st.subheader("🧷 GitHub マイテンプレ保存")
    token, owner, repo, path = _gh_conf()
    if token and owner and repo and path:
        st.caption(f"保存先: {owner}/{repo} → {path}")
    else:
        st.warning("Secrets に GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO / GITHUB_TEMPLATES_PATH を設定してください。")

    st.divider()

    st.subheader("📰 RSSフィード")
    new_feed = st.text_input("新しいRSSフィードを追加")
    if st.button("追加", use_container_width=True) and new_feed:
        if new_feed not in st.session_state.rss_feeds:
            st.session_state.rss_feeds.append(new_feed)
            st.success("追加しました")
            st.rerun()

    if st.session_state.rss_feeds:
        st.caption("登録済み:")
        for i, feed in enumerate(st.session_state.rss_feeds):
            c1, c2 = st.columns([4, 1])
            with c1:
                st.write(feed)
            with c2:
                if st.button("🗑", key=f"del_feed_{i}"):
                    st.session_state.rss_feeds.pop(i)
                    st.rerun()

# -------------------------
# Tabs
# -------------------------
tab1, tab2, tab3, tab4 = st.tabs(["📝 投稿生成", "🎭 ペルソナ管理", "🔗 Threads連携", "📊 分析"])
# =========================================================
# Tab1: 投稿生成
# =========================================================
with tab1:
    st.subheader("📝 投稿生成")

    # ---- Persona select
    persona_names = [p.name for p in st.session_state.personas]
    if not persona_names:
        st.error("ペルソナがありません。『ペルソナ管理』タブで作成してください。")
        st.stop()

    # 現在選択のindex
    try:
        persona_index = persona_names.index(st.session_state.selected_persona_name)
    except ValueError:
        persona_index = 0
        st.session_state.selected_persona_name = persona_names[0]

    c1, c2 = st.columns([2, 1])
    with c1:
        selected_persona_name = st.selectbox(
            "ペルソナを選択",
            persona_names,
            index=persona_index,
            key="persona_selectbox",
        )
        st.session_state.selected_persona_name = selected_persona_name

        selected_persona = safe_get_persona_by_name(st.session_state.personas, selected_persona_name)
        if selected_persona is None:
            st.error("ペルソナの取得に失敗しました。")
            st.stop()

        with st.expander("📌 選択中ペルソナ詳細"):
            st.write(f"**専門分野**: {selected_persona.specialty}")
            st.write(f"**口調**: {selected_persona.tone}")
            st.write(f"**価値観**: {selected_persona.values}")
            st.write(f"**ターゲット**: {selected_persona.target_audience}")
            st.write(f"**目標**: {selected_persona.goals}")

    with c2:
        num_posts = st.number_input(
            "生成する投稿数",
            min_value=1,
            max_value=10,
            value=5,
            step=1,
            help="一度に生成する案の数",
            key="num_posts",
        )

    st.divider()

    # ---- 共通トグル/テーマ
    st.session_state.generation_mode_calm = st.toggle(
        "ノウハウ/数値（Calm優先）モード",
        value=st.session_state.generation_mode_calm,
        help="落ち着いた丁寧な“ノウハウ/数値寄り”の生成比率を増やします",
        key="toggle_calm_mode",
    )

    st.markdown("### 🏷️ テーマ（topic_tag を全投稿に強制適用）")
    selected_topic_theme = st.selectbox(
        "今回のテーマ",
        list(TOPIC_THEME_TO_TAG.keys()),
        index=list(TOPIC_THEME_TO_TAG.keys()).index(st.session_state.selected_topic_theme)
        if st.session_state.selected_topic_theme in TOPIC_THEME_TO_TAG else 0,
        key="topic_theme_select",
    )
    st.session_state.selected_topic_theme = selected_topic_theme
    forced_topic_tag = TOPIC_THEME_TO_TAG.get(selected_topic_theme, "#Web集客")
    st.caption(f"この回の投稿は **{forced_topic_tag}** を全案に適用します。")

    st.divider()

    # ---- ニュース入力方法
    st.markdown("### 📰 ニュース/素材の入力")
    news_source_type = st.radio(
        "入力方法",
        ["RSSフィードから自動取得", "手動で入力（テンプレあり）"],
        horizontal=True,
        key="news_source_type",
    )

    news_content = ""

    # =========================================================
    # RSSモード
    # =========================================================
    if news_source_type == "RSSフィードから自動取得":
        col_r1, col_r2 = st.columns([1, 2])
        with col_r1:
            fetch = st.button("🔄 最新ニュース取得", use_container_width=True)
        with col_r2:
            st.caption("RSSからニュースを取得し、AIに渡す形式へ整形します。")

        if fetch:
            with st.spinner("ニュース取得中..."):
                collector = NewsCollector(st.session_state.rss_feeds)
                news_items = collector.collect_news(limit=8)

            if not news_items:
                st.warning("ニュースが取得できませんでした。RSS URL を見直してください。")
            else:
                st.success(f"{len(news_items)}件取得しました。")
                idx = st.selectbox(
                    "使うニュースを選択",
                    list(range(len(news_items))),
                    format_func=lambda i: news_items[i].get("title", f"news_{i}"),
                    key="selected_news_index",
                )
                selected_news = news_items[idx]
                with st.expander("📄 ニュース詳細"):
                    st.write(f"**タイトル**: {selected_news.get('title','')}")
                    st.write(f"**概要**: {selected_news.get('summary','')}")
                    st.write(f"**リンク**: {selected_news.get('link','')}")
                    st.write(f"**公開日**: {selected_news.get('published','')}")
                news_content = collector.format_for_ai(selected_news)

        # 取得済みを編集できるように（任意）
        news_content = st.text_area(
            "AIに渡すニュース内容（編集可）",
            value=news_content,
            height=180,
            key="news_content_rss",
        )

    # =========================================================
    # 手動入力 + テンプレ（既存テンプレ + GitHubマイテンプレ）
    # =========================================================
    else:
        # ---- 既存テンプレ（最低限のサンプル：必要なら後で増やせます）
        PRESET_NEWS_TEMPLATES = {
            "（選択なし）": "",
            "✅ 完成版｜起業家（申込）発信量より順番": "SNSで頑張ってるのに、申込が増えない人へ。\n原因は「発信量」より、申込までの“順番”が詰まってることが多いです。\n\nあなたのボトルネックはどれ？（番号でOK）\n1 導線\n2 LP\n3 オファー\n4 信頼\n5 計測",
            "✅ 完成版｜店舗（新規）見つけてもらえない": "新規が増えない店舗へ。\n原因は「投稿が少ない」より、見つけてもらう入口が弱いことが多いです。\n\nどこが弱い？（番号でOK）\n1 Googleマップ\n2 検索\n3 SNS\n4 写真\n5 初回不安の解消",
        }

        # 既存テンプレからカテゴリ→ペルソナ自動切替（簡易）
        PRESET_TO_CATEGORY = {
            "✅ 完成版｜起業家（申込）発信量より順番": "ビジネス",
            "✅ 完成版｜店舗（新規）見つけてもらえない": "店舗",
        }

        def _find_persona_by_keyword(names: List[str], keyword: str) -> str:
            for n in names:
                if keyword in n:
                    return n
            return names[0] if names else ""

        # ---- 統合テンプレ（既存 + GitHubマイテンプレ）
        user_templates = st.session_state.get("user_templates", {}) or {}
        combined_templates: Dict[str, str] = {}
        combined_templates.update(PRESET_NEWS_TEMPLATES)

        for k, v in user_templates.items():
            combined_templates[f"🧷マイテンプレ｜{k}"] = v

        preset_keys = list(combined_templates.keys())
        preset_index = preset_keys.index(st.session_state.preset_key) if st.session_state.preset_key in preset_keys else 0

        # preset_keys は既に list(combined_templates.keys()) で作ってある前提

        # 初回だけ widget の初期値を入れる（存在しない値なら（選択なし）へ）
        if "preset_key_select" not in st.session_state:
            st.session_state.preset_key_select = st.session_state.get("preset_key", "（選択なし）")
        if st.session_state.preset_key_select not in preset_keys:
            st.session_state.preset_key_select = "（選択なし）"

        preset_key = st.selectbox(
            "テンプレを選択（選択後に「反映」ボタンで本文へ反映）",
            preset_keys,
            key="preset_key_select",
        )

        # 同期（ここでは index を使わない）
        st.session_state.preset_key = preset_key


             # テンプレ本文プレビュー
        def _get_template_text(selected_key: str) -> str:
            if selected_key == "（選択なし）":
                return ""
            # まずプリセットを優先
            if selected_key in PRESET_NEWS_TEMPLATES:
                return PRESET_NEWS_TEMPLATES.get(selected_key, "")
            # 🧷マイテンプレ｜xxx → xxx に戻して user_templates を参照
            prefix = "🧷マイテンプレ｜"
            if selected_key.startswith(prefix):
                raw_name = selected_key[len(prefix):]
                return (user_templates.get(raw_name) or "")
            # 最後の保険
            return combined_templates.get(selected_key, "")

        tpl_preview = _get_template_text(preset_key)

        st.caption(f"DEBUG preset_key: {repr(preset_key)}")
        st.caption(f"DEBUG in_presets: {preset_key in PRESET_NEWS_TEMPLATES}")
        st.caption(f"DEBUG in_combined: {preset_key in combined_templates}")
        st.caption(f"DEBUG user_templates_count: {len(user_templates)}")
        st.caption(f"DEBUG tpl_preview_len: {len(tpl_preview)}")

        st.markdown("**テンプレ本文プレビュー（編集は下の本文欄で）**")
        st.code(tpl_preview if tpl_preview else "（プレビューなし：テンプレを選択してください）")

        if st.button("⬇️ このテンプレを本文に反映", use_container_width=True, key="apply_template_btn"):
    # 本文の“変数”だけでなく、text_area の“キー”も更新する（重要）
    st.session_state.news_manual_text = tpl_preview
    st.session_state.news_manual_text_area = tpl_preview

    # 既存テンプレだけカテゴリで自動切替（マイテンプレは対象外）
    if preset_key in PRESET_TO_CATEGORY:
        cat = PRESET_TO_CATEGORY.get(preset_key, "")
        if cat:
            target_persona = _find_persona_by_keyword(persona_names, cat)
            if target_persona:
                st.session_state.selected_persona_name = target_persona

    st.rerun()
    
    st.text_area(
    "ニュース/素材（手動入力）",
    value=st.session_state.news_manual_text,
    height=220,
    key="news_manual_text_area",
)

# 本文は常に widget 側を正とする（反映ボタンでここも書き換えるため）
st.session_state.news_manual_text = st.session_state.news_manual_text_area
news_content = st.session_state.news_manual_text


        # ---- GitHubマイテンプレ管理
        with st.expander("🧷 マイテンプレ管理（GitHubへ保存/削除）", expanded=False):
            token, owner, repo, path = _gh_conf()
            if not (token and owner and repo and path):
                st.warning("Secrets に GitHub設定が必要です（GITHUB_TOKEN 等）")
            else:
                st.caption(f"保存先: {owner}/{repo} → {path}")

            tpl_name = st.text_input("テンプレ名（重複OK：上書き）", key="tpl_name_input")
            tpl_text = st.text_area("テンプレ本文（保存する内容）", height=160, key="tpl_text_input")

            s1, s2 = st.columns([1, 1])
            with s1:
                if st.button("💾 保存（GitHubへ）", use_container_width=True, key="save_tpl_btn"):
                    name = (tpl_name or "").strip()
                    text = (tpl_text or "").strip()
                    if not name:
                        st.warning("テンプレ名を入力してください。")
                    elif not text:
                        st.warning("テンプレ本文を入力してください。")
                    else:
                        try:
                            data, sha = github_get_file_json()
                            data[name] = text
                            github_put_file_json(data=data, sha=sha, commit_message=f"Save user template: {name}")
                            st.session_state.user_templates = data
                            st.session_state.user_templates_sha = sha
                            st.success(f"保存しました: {name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"保存に失敗しました: {e}")

            with s2:
                saved_names = list((st.session_state.get("user_templates", {}) or {}).keys())
                delete_target = st.selectbox(
                    "削除するテンプレ",
                    options=["（選択なし）"] + saved_names,
                    key="delete_tpl_select",
                )
                if st.button("🗑 削除（GitHubへ）", use_container_width=True, key="delete_tpl_btn"):
                    if delete_target == "（選択なし）":
                        st.warning("削除対象を選択してください。")
                    else:
                        try:
                            data, sha = github_get_file_json()
                            if delete_target in data:
                                data.pop(delete_target, None)
                            github_put_file_json(data=data, sha=sha, commit_message=f"Delete user template: {delete_target}")
                            st.session_state.user_templates = data
                            st.session_state.user_templates_sha = sha
                            st.success(f"削除しました: {delete_target}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"削除に失敗しました: {e}")

            if st.session_state.get("user_templates"):
                st.markdown("**保存済みマイテンプレ**")
                st.write(list(st.session_state.user_templates.keys()))
            else:
                st.caption("まだマイテンプレはありません。")

    st.divider()

    # =========================================================
    # 生成
    # =========================================================
    st.markdown("### 🚀 生成")

    can_generate = bool((anthropic_key or "").strip()) and bool((news_content or "").strip())
    if not anthropic_key:
        st.info("Anthropic API Key を入力してください。")
    if not (news_content or "").strip():
        st.info("ニュース/素材（RSSまたは手動入力）を入れてください。")

    if st.button("✨ 投稿を生成する", type="primary", disabled=not can_generate, use_container_width=True):
        with st.spinner("生成中..."):
            gen = ThreadsPostGenerator(api_key=anthropic_key)
            gen.ui_mode_calm_priority = bool(st.session_state.generation_mode_calm)
            gen.forced_topic_tag = forced_topic_tag

            posts = gen.generate_posts(
                persona=selected_persona,
                news_content=news_content,
                num_variations=int(num_posts),
            )

            # 再生成で表示キーを変える（Streamlitの更新不具合回避）
            st.session_state.generation_run_id = datetime.now().strftime("%Y%m%d%H%M%S")
            st.session_state.generated_posts = posts

        st.success("生成しました！")

    # =========================================================
    # 結果表示
    # =========================================================
    st.markdown("### 📌 生成結果")

    posts = st.session_state.get("generated_posts", []) or []
    if not posts:
        st.caption("まだ生成結果はありません。")
    else:
        for i, post in enumerate(posts):
            score = post.get("score", 0)
            topic_tag = post.get("topic_tag", "")
            style_mode = post.get("style_mode", "")
            lens = post.get("lens", "N/A")

            hook, body, cta = extract_hook_body_cta(post)

            with st.container(border=True):
                h1, h2, h3 = st.columns([2, 1, 1])
                with h1:
                    st.markdown(f"**#{i+1}**  スコア: **{score}**")
                with h2:
                    st.caption(f"tag: {topic_tag}")
                with h3:
                    st.caption(f"mode: {style_mode}")

                # 表示キーをrun_idで変える
                edit_key = f"post_text_{st.session_state.generation_run_id}_{i}"
                post_text = st.text_area(
                    "投稿本文（編集可）",
                    value=post.get("post_text", ""),
                    height=160,
                    key=edit_key,
                )

                with st.expander("🔎 メタ情報（hook/body/cta など）"):
                    st.write(f"**hook**: {hook}")
                    st.write(f"**body**: {body}")
                    st.write(f"**cta**: {cta}")
                    st.write(f"**predicted_stage**: {post.get('predicted_stage','')}")
                    st.write(f"**conversation_trigger**: {post.get('conversation_trigger','')}")
                    st.write(f"**reasoning**: {post.get('reasoning','')}")
                    st.write(f"**lens**: {lens}")

                # 送信ボタン（Threads連携は Tab3 でもできるが、ここからも送れるようにする）
                if st.button("📤 この投稿をThreadsへ送る（Tab3の認証が必要）", key=f"send_post_{i}"):
                    if not st.session_state.get("threads_client"):
                        st.warning("Threads連携が未完了です。先に『Threads連携』タブで認証してください。")
                    else:
                        try:
                            res = st.session_state.threads_client.create_post(post_text)
                            if res and res.get("success"):
                                st.success(f"投稿しました！ post_id={res.get('post_id')}")
                            else:
                                st.error("投稿に失敗しました（レスポンスが空/不正）")
                        except Exception as e:
                            st.error(f"投稿エラー: {e}")
# =========================================================
# Tab2: ペルソナ管理（CRUD）
# =========================================================
with tab2:
    st.subheader("🎭 ペルソナ管理")

    personas: List[PersonaConfig] = st.session_state.personas

    st.markdown("### 登録済みペルソナ")
    if not personas:
        st.info("ペルソナがありません。下のフォームから追加してください。")
    else:
        for idx, p in enumerate(personas):
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{p.name}**")
                    st.caption(f"専門: {p.specialty}")
                    st.caption(f"口調: {p.tone}")
                    st.caption(f"価値観: {p.values}")
                    st.caption(f"ターゲット: {p.target_audience}")
                    st.caption(f"目標: {p.goals}")
                with c2:
                    if st.button("🗑 削除", key=f"delete_persona_{idx}", use_container_width=True):
                        deleting_name = p.name
                        st.session_state.personas.pop(idx)

                        # 選択中ペルソナが消えたら退避
                        if st.session_state.personas:
                            if st.session_state.selected_persona_name == deleting_name:
                                st.session_state.selected_persona_name = st.session_state.personas[0].name
                        else:
                            st.session_state.selected_persona_name = ""

                        st.rerun()

    st.divider()
    st.markdown("### ➕ 新規ペルソナ追加")

    with st.form("add_persona_form"):
        name = st.text_input("名前", value="")
        specialty = st.text_input("専門分野", value="")
        tone = st.text_input("口調", value="丁寧で親しみやすい")
        values = st.text_area("価値観", value="")
        target = st.text_area("ターゲット", value="")
        goals = st.text_area("目標", value="")

        submitted = st.form_submit_button("追加する", use_container_width=True)
        if submitted:
            if not name.strip():
                st.warning("名前は必須です。")
            else:
                new_p = PersonaConfig(
                    name=name.strip(),
                    specialty=(specialty or "").strip(),
                    tone=(tone or "").strip(),
                    values=(values or "").strip(),
                    target_audience=(target or "").strip(),
                    goals=(goals or "").strip(),
                )
                st.session_state.personas.append(new_p)
                st.session_state.selected_persona_name = new_p.name
                st.success("追加しました。")
                st.rerun()


# =========================================================
# Tab3: Threads連携（認可URL → code入力 → token → 投稿）
# =========================================================
with tab3:
    st.subheader("🔗 Threads連携")
    st.caption("Community Cloud では自動でブラウザを開きにくいので、認可URL表示→code貼り付け方式にしています。")

    if not threads_app_id or not threads_app_secret:
        st.warning("サイドバーで Threads App ID / Secret を入力してください。")
    else:
        # まだ client が無ければ作成
        if st.session_state.threads_client is None:
            st.session_state.threads_client = ThreadsAPIClient(
                app_id=threads_app_id,
                app_secret=threads_app_secret,
            )

        client: ThreadsAPIClient = st.session_state.threads_client

        st.markdown("### 1) 認可URLを開いて code を取得")
        auth_url = client.get_authorization_url()
        st.code(auth_url, language="text")
        st.link_button("🔐 認可ページを開く（別タブ）", auth_url)

        st.markdown("### 2) code を貼り付けてトークン取得")
        code = st.text_input("code（URL の code= の値）", value="", key="threads_oauth_code")

        if st.button("✅ code を交換してログイン", use_container_width=True, key="exchange_code_btn"):
            if not code.strip():
                st.warning("code を入力してください。")
            else:
                try:
                    ok = client.exchange_code_for_token(code.strip())
                    if ok:
                        st.success("認証できました。")
                    else:
                        st.error("認証に失敗しました。code が正しいか確認してください。")
                except Exception as e:
                    st.error(f"認証エラー: {e}")

        st.divider()
        st.markdown("### 3) テスト投稿（任意）")
        test_text = st.text_area(
            "投稿テキスト（500文字以内）",
            value="テスト投稿です。うまく送れていますか？（番号で返信してもらえると嬉しいです）\n1 はい 2 いいえ",
            height=160,
            key="threads_test_text",
        )

        if st.button("📤 テスト投稿を送る", use_container_width=True, key="send_test_post_btn"):
            try:
                res = client.create_post(test_text)
                if res and res.get("success"):
                    st.success(f"投稿しました！ post_id={res.get('post_id')}")
                else:
                    st.error("投稿に失敗しました（レスポンスが空/不正）")
            except Exception as e:
                st.error(f"投稿エラー: {e}")

        st.caption("※失敗する場合は、App権限（threads_content_publish等）と有効なアクセストークンを確認してください。")


# =========================================================
# Tab4: 分析（プレースホルダ）
# =========================================================
with tab4:
    st.subheader("📊 分析")
    st.info("分析タブは現在プレースホルダです。今後、投稿の反応（views/likes/replies等）を取得して可視化します。")

    st.markdown("#### 参考: threads_api.py の insights 取得")
    st.caption("threads_api.py には get_insights が実装されています（トークン取得後に post_id を指定）。")
    st.caption("必要なら、このタブに post_id 入力→get_insights 表示を追加できます。")
