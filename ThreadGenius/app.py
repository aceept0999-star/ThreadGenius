"""
ThreadGenius - メインアプリケーション
Streamlitを使用した対話的UI
"""

import streamlit as st
import json
import os
import base64
import requests
from datetime import datetime, timedelta

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

# ページ設定
st.set_page_config(
    page_title="ThreadGenius - Threads投稿自動生成",
    page_icon="🚀",
    layout="wide"
)

# =========================
# ✅ GitHubにマイテンプレを保存（Streamlit Cloud向け）
# =========================
def _gh_conf():
    # Secrets が無い場合は空になる（ローカル実行でも落とさない）
    token = st.secrets.get("GITHUB_TOKEN", "")
    owner = st.secrets.get("GITHUB_OWNER", "")
    repo = st.secrets.get("GITHUB_REPO", "")
    path = st.secrets.get("GITHUB_TEMPLATES_PATH", "ThreadGenius/user_templates.json")
    return token, owner, repo, path


def github_get_file_json() -> tuple[dict, str]:
    """
    GitHub上のJSONを読み込む。
    戻り: (data_dict, sha)
    """
    token, owner, repo, path = _gh_conf()
    if not (token and owner and repo and path):
        return {}, ""

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    r = requests.get(url, headers=headers, timeout=15)

    # ファイルがまだ無い（初回）なら空で返す
    if r.status_code == 404:
        return {}, ""

    r.raise_for_status()
    payload = r.json()
    sha = payload.get("sha", "")
    content_b64 = payload.get("content", "") or ""
    content_bytes = base64.b64decode(content_b64)
    text = content_bytes.decode("utf-8")

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            data = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
            return data, sha
    except Exception:
        pass

    return {}, sha


def github_put_file_json(data: dict, sha: str, commit_message: str) -> None:
    """
    GitHub上のJSONを更新（新規作成/上書き）。
    """
    token, owner, repo, path = _gh_conf()
    if not (token and owner and repo and path):
        raise RuntimeError("GitHub Secrets が未設定です（GITHUB_TOKEN等）")

    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    body_text = json.dumps(data, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(body_text.encode("utf-8")).decode("utf-8")

    payload = {
        "message": commit_message,
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers=headers, json=payload, timeout=15)
    r.raise_for_status()


# セッション状態の初期化（既存キーは絶対に壊さない）
if "personas" not in st.session_state:
    st.session_state.personas = DEFAULT_PERSONAS

if "generated_posts" not in st.session_state:
    st.session_state.generated_posts = []

if "rss_feeds" not in st.session_state:
    st.session_state.rss_feeds = DEFAULT_RSS_FEEDS.copy()

if "threads_client" not in st.session_state:
    st.session_state.threads_client = None

if "selected_persona_name" not in st.session_state:
    st.session_state.selected_persona_name = st.session_state.personas[0].name if st.session_state.personas else ""

if "preset_key" not in st.session_state:
    st.session_state.preset_key = "（選択なし）"

if "news_manual_text" not in st.session_state:
    st.session_state.news_manual_text = ""

# ✅ 追加①：生成モード（RSS/手動 共通）Calm優先トグル
if "generation_mode_calm" not in st.session_state:
    st.session_state.generation_mode_calm = False

# ✅ 追加①補助：再生成時に post_text 表示が更新されない問題対策（run_id）
if "generation_run_id" not in st.session_state:
    st.session_state.generation_run_id = "0"

# ✅ 追加②：テーマ選択（Web集客/マーケティング/店舗集客）→ forced_topic_tag 強制適用
if "selected_topic_theme" not in st.session_state:
    st.session_state.selected_topic_theme = "Web集客"

TOPIC_THEME_TO_TAG = {
    "Web集客": "#Web集客",
    "マーケティング": "#マーケティング",
    "店舗集客": "#店舗集客",
}

# ✅ 追加：GitHubからマイテンプレを読み込み（Secrets未設定でも落ちない）
if "user_templates" not in st.session_state:
    data, sha = github_get_file_json()
    st.session_state.user_templates = data
    st.session_state.user_templates_sha = sha

if "user_templates_sha" not in st.session_state:
    st.session_state.user_templates_sha = ""


# 安全化ユーティリティ（StopIteration / 空リスト対策）
def safe_get_persona_by_name(personas, persona_name: str):
    """
    persona_name が見つからない場合でも落ちないようにする。
    """
    if not personas:
        return None
    hit = next((p for p in personas if p.name == persona_name), None)
    return hit if hit is not None else personas[0]


def extract_hook_body_cta(post: dict):
    """
    generator側の返却形式が将来変わっても壊れないように、
    可能性のあるキーを広めに拾う。
    """
    hook = post.get("hook") or post.get("post_hook") or ""
    body = post.get("body") or post.get("post_body") or ""
    cta = post.get("cta") or post.get("call_to_action") or post.get("post_cta") or ""
    return hook, body, cta


# タイトル
st.title("🚀 ThreadGenius")
st.subheader("あなた専用 Threads投稿自動生成ツール")
st.markdown("---")

# サイドバー：設定
with st.sidebar:
    st.header("⚙️ 設定")

    # API キー設定
    st.subheader("🔑 API キー")

    anthropic_key = st.text_input(
        "Anthropic API Key",
        value=ANTHROPIC_API_KEY,
        type="password",
        help="Claude APIキーを入力してください"
    )

    threads_app_id = st.text_input(
        "Threads App ID",
        value=THREADS_APP_ID,
        help="Threads アプリIDを入力"
    )

    threads_app_secret = st.text_input(
        "Threads App Secret",
        value=THREADS_APP_SECRET,
        type="password",
        help="Threads アプリシークレットを入力"
    )

    st.markdown("---")

    # RSSフィード管理
    st.subheader("📰 RSSフィード")

    new_feed = st.text_input("新しいRSSフィードを追加")
    if st.button("追加") and new_feed:
        if new_feed not in st.session_state.rss_feeds:
            st.session_state.rss_feeds.append(new_feed)
            st.success(f"追加しました: {new_feed}")

    st.write("登録済みフィード:")
    for i, feed in enumerate(st.session_state.rss_feeds):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.text(feed[:40] + "..." if len(feed) > 40 else feed)
        with col2:
            if st.button("🗑️", key=f"delete_{i}"):
                st.session_state.rss_feeds.pop(i)
                st.rerun()

# メインコンテンツ
tab1, tab2, tab3, tab4 = st.tabs(["📝 投稿生成", "🎭 ペルソナ管理", "🔗 Threads連携", "📊 分析"])


# タブ1：投稿生成
with tab1:
    st.header("投稿を自動生成")

    col1, col2 = st.columns([2, 1])

    with col1:
        # ペルソナ選択（テンプレ連動のためsession_stateで管理）
        persona_names = [p.name for p in st.session_state.personas]

        if not persona_names:
            st.error("ペルソナが1件もありません。タブ「ペルソナ管理」で作成してください。")
            st.stop()

        # 現在選択のindexを取得（なければ0）
        try:
            persona_index = persona_names.index(st.session_state.selected_persona_name)
        except ValueError:
            persona_index = 0
            st.session_state.selected_persona_name = persona_names[0]

        selected_persona_name = st.selectbox(
            "ペルソナを選択",
            persona_names,
            index=persona_index,
            help="投稿するキャラクターを選んでください",
            key="persona_selectbox"
        )
        st.session_state.selected_persona_name = selected_persona_name

        selected_persona = safe_get_persona_by_name(st.session_state.personas, selected_persona_name)
        if selected_persona is None:
            st.error("ペルソナが取得できませんでした。")
            st.stop()

        st.session_state.selected_persona_name = selected_persona.name

        # ペルソナ情報表示
        with st.expander("📋 選択中のペルソナ詳細"):
            st.write(f"**専門分野**: {selected_persona.specialty}")
            st.write(f"**口調**: {selected_persona.tone}")
            st.write(f"**価値観**: {selected_persona.values}")
            st.write(f"**ターゲット**: {selected_persona.target_audience}")
            st.write(f"**目標**: {selected_persona.goals}")

    with col2:
        num_posts = st.number_input(
            "生成する投稿数",
            min_value=1,
            max_value=10,
            value=5,
            help="一度に生成する投稿案の数"
        )

    st.markdown("---")

    # ニュース選択
    st.subheader("📰 ニュースソース")

    news_source_type = st.radio(
        "ニュースの取得方法",
        ["RSSフィードから自動取得", "手動で入力"],
        horizontal=True
    )

    # ✅ 追加①：生成モード（RSS/手動 共通トグル）
    st.session_state.generation_mode_calm = st.toggle(
        "ノウハウ/数値（Calm優先）モード",
        value=st.session_state.generation_mode_calm,
        key="generation_mode_toggle",
        help="ノウハウ・手順・実績・数値系は『丁寧で落ち着いた会話（Calm）』を優先して生成します。"
    )

    # ✅ 追加②：テーマ選択（RSS/手動 共通）→ forced_topic_tag
    st.markdown("### 🏷️ テーマ（トピックタグ）")
    selected_topic_theme = st.selectbox(
        "今回の投稿テーマを選択",
        options=list(TOPIC_THEME_TO_TAG.keys()),
        index=list(TOPIC_THEME_TO_TAG.keys()).index(st.session_state.selected_topic_theme)
        if st.session_state.selected_topic_theme in TOPIC_THEME_TO_TAG else 0,
        key="topic_theme_selectbox",
        help="選択したテーマに応じて、生成された全投稿の topic_tag を同一タグに強制適用します。"
    )
    st.session_state.selected_topic_theme = selected_topic_theme
    forced_topic_tag = TOPIC_THEME_TO_TAG.get(selected_topic_theme, "#Web集客")
    st.caption(f"この回の投稿は **{selected_topic_theme} → {forced_topic_tag}** を全案へ適用します。")

    news_content = ""

    if news_source_type == "RSSフィードから自動取得":
        if st.button("🔄 最新ニュースを取得"):
            with st.spinner("ニュース収集中..."):
                collector = NewsCollector(st.session_state.rss_feeds)
                news_items = collector.collect_news(limit=5)

                if news_items:
                    st.success(f"{len(news_items)}件のニュースを取得しました！")

                    selected_news_index = st.selectbox(
                        "投稿に使用するニュースを選択",
                        range(len(news_items)),
                        format_func=lambda i: news_items[i]["title"]
                    )

                    selected_news = news_items[selected_news_index]

                    with st.expander("📄 ニュース詳細"):
                        st.write(f"**タイトル**: {selected_news['title']}")
                        st.write(f"**概要**: {selected_news['summary']}")
                        st.write(f"**リンク**: {selected_news['link']}")

                    news_content = collector.format_for_ai(selected_news)
                else:
                    st.warning("ニュースが取得できませんでした")

    else:
        # テンプレ選択（既存ロジックを維持）
        PRESET_NEWS_TEMPLATES = {
            "（選択なし）": "",

            # =========================================================
            # 🧩 1テーマ5役割テンプレ（合計6テーマ：起業家3 + 店舗3）
            # =========================================================

            "🧩1テーマ5役割｜起業家：申込が増えない（被り防止）": """【テーマ】SNS頑張ってるのに申込が増えない（原因は“発信量”より“順番”）
【前提】同じテーマで“1日5投稿”作るが、文章の被りは禁止。5本は必ず別の型で。

【あなたへの指示】以下の5役割で、Threads投稿を5本作成すること（各500字以内）。
①共感（あるある）：悩みの状況を言語化→「Yes/No」で終える
②診断（番号回答）：ボトルネック5択→「1〜5どれ？」で終える
③今日の1手（超具体）：10分でできる改善を1つ→「どれからやる？」で終える
④事例/たとえ：改善前→改善後が想像できる話→「あなたはどのパターン？」で終える
⑤誤解を壊す：よくある勘違いを否定→「賛成/反対？」で終える

【診断軸（5択で使用）】
1 導線（どこから申込？）
2 LP（申込ページ）
3 オファー（内容/価格）
4 信頼（実績/口コミ）
5 計測（数字が見れてない）

【厳守ルール（重複回避）】
- 5本は「書き出し」を必ず変える（同じ冒頭禁止）
- 語尾を揃えない（です/ますの連続や同語尾連発禁止）
- 同じ比喩・同じ結論文の使い回し禁止
- 質問形式は5本すべて別（Yes/No・番号・順位・賛否・穴埋め等）
- 1つのトピックタグのみ（例：#Web集客）

【目的】返信（会話）を増やし、コメント欄で状況を聞き出せる投稿にする。""",

            "🧩1テーマ5役割｜起業家：成約しない（被り防止）": """【テーマ】アクセスはあるのに成約しない（原因は“文章力”より“比較不安の未解消”）
【前提】同じテーマで“1日5投稿”作るが、文章の被りは禁止。5本は必ず別の型で。

【あなたへの指示】以下の5役割で、Threads投稿を5本作成すること（各500字以内）。
①共感（あるある）：検討止まりの気持ちを代弁→「当てはまる？Yes/No」で終える
②診断（番号回答）：比較不安の残り方5択→「1〜5どれ？」で終える
③今日の1手（超具体）：LP/提案で今日直せる1箇所→「どれからやる？」で終える
④事例/たとえ：不安が消えた瞬間の例→「あなたはどのパターン？」で終える
⑤誤解を壊す：よくある勘違いを否定→「賛成/反対？」で終える

【診断軸（5択で使用）】
1 誰向けの明確さ（対象が広すぎる）
2 証拠（実績/事例/声が薄い）
3 提案の具体性（何がどう変わる？が曖昧）
4 価格の根拠（なぜその値段？が不明）
5 申込の簡単さ（導線が迷う/面倒）

【厳守ルール（重複回避）】
- 5本は書き出しを必ず変える
- 質問形式は5本すべて別（Yes/No・番号・順位・賛否・穴埋め等）
- 同じ結論の言い回し禁止／同じ比喩禁止
- 1つのトピックタグのみ（例：#マーケティング）

【目的】返信（会話）を増やし、コメント欄で「どの不安が残ってるか」を引き出す投稿にする。""",

            "🧩1テーマ5役割｜起業家：単価が上がらない（被り防止）": """【テーマ】単価が上がらない（原因は“価値がない”ではなく“価値の伝え方/見せ方”）
【前提】同じテーマで“1日5投稿”作るが、文章の被りは禁止。5本は必ず別の型で。

【あなたへの指示】以下の5役割で、Threads投稿を5本作成すること（各500字以内）。
①共感（あるある）：安売りループの心理→「Yes/No」で終える
②診断（番号回答）：単価が上がらない原因5択→「1〜5どれ？」で終える
③今日の1手（超具体）：今日できる“見せ方改善”を1つ→「どれからやる？」で終える
④事例/たとえ：高単価が選ばれる理由の例→「あなたはどのパターン？」で終える
⑤誤解を壊す：「値上げ＝離脱」等の誤解を否定→「賛成/反対？」で終える

【診断軸（5択で使用）】
1 差別化（誰に何が一番強い？が曖昧）
2 実績の見せ方（数字/ビフォアフ/変化が弱い）
3 提案内容（中身の濃さが伝わるか）
4 限定性（誰には合わないかが言えない）
5 導線（高単価商品への流れが無い）

【厳守ルール（重複回避）】
- 5本は書き出しを必ず変える
- 質問形式は5本すべて別（Yes/No・番号・順位・賛否・穴埋め等）
- 同じ結論の言い回し禁止／同じ比喩禁止
- 1つのトピックタグのみ（例：#ビジネス）

【目的】返信（会話）を増やし、コメント欄で「どこが弱いか」を特定する投稿にする。""",

            "🧩1テーマ5役割｜店舗：新規が増えない（被り防止）": """【テーマ】新規が増えない（原因は“投稿回数”より“見つけてもらう入口”）
【前提】同じテーマで“1日5投稿”作るが、文章の被りは禁止。5本は必ず別の型で。

【あなたへの指示】以下の5役割で、Threads投稿を5本作成すること（各500字以内）。
①共感（あるある）：頑張ってるのに見つからない→「当てはまる？Yes/No」で終える
②診断（番号回答）：入口の弱点5択→「1〜5どれ？」で終える
③今日の1手（超具体）：今日10分でできる入口改善→「どれからやる？」で終える
④事例/たとえ：入口が強い店の共通点→「あなたはどのパターン？」で終える
⑤誤解を壊す：「インスタだけ」等の誤解を否定→「賛成/反対？」で終える

【診断軸（5択で使用）】
1 Googleマップ（MEO）
2 検索（地域×サービス名）
3 SNS（発見される投稿/プロフィール）
4 写真（雰囲気/メニュー/実績）
5 初回不安の解消（料金/流れ/時間/注意点）

【厳守ルール（重複回避）】
- 5本は書き出しを必ず変える
- 質問形式は5本すべて別（Yes/No・番号・順位・賛否・穴埋め等）
- 同じ結論の言い回し禁止／同じ比喩禁止
- 1つのトピックタグのみ（例：#店舗集客）

【目的】返信（会話）を増やし、コメント欄で「入口の弱点」を特定する投稿にする。""",

            "🧩1テーマ5役割｜店舗：リピートしない（被り防止）": """【テーマ】新規は来るのにリピートしない（原因は“満足度”より“次回設計”）
【前提】同じテーマで“1日5投稿”作るが、文章の被りは禁止。5本は必ず別の型で。

【あなたへの指示】以下の5役割で、Threads投稿を5本作成すること（各500字以内）。
①共感（あるある）：2回目が途切れる→「当てはまる？Yes/No」で終える
②診断（番号回答）：リピートが止まる理由5択→「1〜5どれ？」で終える
③今日の1手（超具体）：今日からできる次回導線→「どれからやる？」で終える
④事例/たとえ：リピートが続く店の流れ→「あなたはどのパターン？」で終える
⑤誤解を壊す：「技術が足りないから」等の誤解を否定→「賛成/反対？」で終える

【診断軸（5択で使用）】
1 次回提案（通う理由の提示）
2 フォロー（LINE/DM/声かけ）
3 メニュー導線（次に何を選ぶ？）
4 口コミ導線（紹介が増えない）
5 回数券/定期（続けやすい設計）

【厳守ルール（重複回避）】
- 5本は書き出しを必ず変える
- 質問形式は5本すべて別（Yes/No・番号・順位・賛否・穴埋め等）
- 同じ結論の言い回し禁止／同じ比喩禁止
- 1つのトピックタグのみ（例：#リピート）

【目的】返信（会話）を増やし、コメント欄で「どこが弱いか」を特定する投稿にする。""",

            "🧩1テーマ5役割｜店舗：口コミが増えない（被り防止）": """【テーマ】口コミが増えない（原因は“お願い不足”より“お願いのタイミングと導線”）
【前提】同じテーマで“1日5投稿”作るが、文章の被りは禁止。5本は必ず別の型で。

【あなたへの指示】以下の5役割で、Threads投稿を5本作成すること（各500字以内）。
①共感（あるある）：忙しくてお願いできない→「当てはまる？Yes/No」で終える
②診断（番号回答）：口コミが増えない原因5択→「1〜5どれ？」で終える
③今日の1手（超具体）：今日からできる依頼導線→「どれからやる？」で終える
④事例/たとえ：口コミが増える店の一言→「あなたはどのパターン？」で終える
⑤誤解を壊す：「お願いすると嫌われる」等の誤解を否定→「賛成/反対？」で終える

【診断軸（5択で使用）】
1 そもそも依頼してない
2 依頼のタイミングがズレてる
3 一言テンプレがない（何て言う？）
4 QR/リンク導線がない（どこから書く？）
5 口コミ返信ができてない（信頼が積もらない）

【厳守ルール（重複回避）】
- 5本は書き出しを必ず変える
- 質問形式は5本すべて別（Yes/No・番号・順位・賛否・穴埋め等）
- 同じ結論の言い回し禁止／同じ比喩禁止
- 1つのトピックタグのみ（例：#口コミ）

【目的】返信（会話）を増やし、コメント欄で「どこが詰まっているか」を特定する投稿にする。""",

            # =========================================================
            # 既存：完成版6種
            # =========================================================
            "✅完成版｜起業家（申込）発信量より順番": """SNSで頑張ってるのに、申込が増えない人へ。
原因は「発信量」より、申込までの順番が詰まってることが多いです。

あなたのボトルネックはどれ？（番号でOK）
1 導線（どこから申込？）
2 LP（申込ページ）
3 オファー（内容/価格）
4 信頼（実績/口コミ）
5 計測（数字が見れてない）""",

            "✅完成版｜起業家（成約）アクセスあるのに決まらない": """アクセスはあるのに成約しない人へ。
原因は「文章が下手」より、相手の“比較不安”が残ってることが多いです。

どこが一番弱い？（番号でOK）
1 誰向けの明確さ
2 証拠（実績/事例/声）
3 提案の具体性（何がどう変わる？）
4 価格の根拠（なぜその値段？が不明）
5 申込の簡単さ（導線が迷わない導線）""",

            "✅完成版｜起業家（単価）安売りから抜けたい": """単価が上がらない人へ。
価値がないんじゃなくて、“価値の伝え方”が弱いだけのことが多いです。

どこを強化したい？（番号でOK）
1 差別化（誰に何が一番強い？）
2 実績の見せ方（ビフォアフ/数字）
3 提案内容（中身の濃さ）
4 限定性（誰には合わないも言える）
5 導線（単価の高い商品へ誘導）""",

            "✅完成版｜店舗（新規）見つけてもらえない": """新規が増えない店舗へ。
原因は「投稿が少ない」より、見つけてもらう入口が弱いことが多いです。

どこが弱い？（番号でOK）
1 Googleマップ（MEO）
2 検索（地域×サービス名）
3 SNS（発見される投稿）
4 写真（雰囲気/メニュー/実績）
5 初回不安の解消（料金/流れ/時間）""",

            "✅完成版｜店舗（リピート）2回目につながらない": """新規は来るのにリピートしない店舗へ。
原因は“満足度”より、次回につながる設計が無いことが多いです。

どこが一番弱い？（番号でOK）
1 次回提案（通う理由の提示）
2 フォロー（LINE/DM/声かけ）
3 メニュー導線（次に何を選ぶ？）
4 口コミ導線（紹介が増えない）
5 回数券/定期（続けやすい設計）""",

            "✅完成版｜店舗（口コミ）増えない・集まらない": """口コミが増えない店舗へ。
原因は「お願い不足」より、お願いの“タイミングと導線”が弱いことが多いです。

あなたの課題はどれ？（番号でOK）
1 そもそも依頼してない
2 依頼のタイミングがズレてる
3 一言テンプレがない（何て言う？）
4 QR/リンク導線がない（どこから書く？）
5 口コミ返信ができてない（信頼が積もらない）""",
        }

        PRESET_TO_CATEGORY = {
            # ===== 🧩 1テーマ5役割テンプレ（6テーマ） =====
            "🧩1テーマ5役割｜起業家：申込が増えない（被り防止）": "起業家",
            "🧩1テーマ5役割｜起業家：成約しない（被り防止）": "起業家",
            "🧩1テーマ5役割｜起業家：単価が上がらない（被り防止）": "起業家",
            "🧩1テーマ5役割｜店舗：新規が増えない（被り防止）": "店舗",
            "🧩1テーマ5役割｜店舗：リピートしない（被り防止）": "店舗",
            "🧩1テーマ5役割｜店舗：口コミが増えない（被り防止）": "店舗",

            # ===== 既存：完成版6種 =====
            "✅完成版｜起業家（申込）発信量より順番": "起業家",
            "✅完成版｜起業家（成約）アクセスあるのに決まらない": "起業家",
            "✅完成版｜起業家（単価）安売りから抜けたい": "起業家",
            "✅完成版｜店舗（新規）見つけてもらえない": "店舗",
            "✅完成版｜店舗（リピート）2回目につながらない": "店舗",
            "✅完成版｜店舗（口コミ）増えない・集まらない": "店舗",
        }

        def _find_persona_by_keyword(names, keyword: str):
            for n in names:
                if keyword in n:
                    return n
            return names[0] if names else ""

        # =========================
        # ✅ 既存テンプレ + GitHubマイテンプレ を統合して表示
        # =========================
        user_templates = st.session_state.get("user_templates", {}) or {}
        combined_templates = {}
        combined_templates.update(PRESET_NEWS_TEMPLATES)

        # マイテンプレは表示名を変えて衝突回避
        for k, v in user_templates.items():
            combined_templates[f"🧷マイテンプレ｜{k}"] = v

        preset_keys = list(combined_templates.keys())
        preset_index = preset_keys.index(st.session_state.preset_key) if st.session_state.preset_key in preset_keys else 0

        preset_key = st.selectbox(
            "✅テンプレを選択（ニュース内容に自動挿入）",
            preset_keys,
            index=preset_index,
            help="既存テンプレに加えて、GitHubに保存したマイテンプレも選べます。",
            key="preset_selectbox"
        )
        st.session_state.preset_key = preset_key

        # テンプレ選択→ニュース欄へ反映 & （既存テンプレだけ）ペルソナ自動切替
        if preset_key != "（選択なし）":
            st.session_state.news_manual_text = combined_templates.get(preset_key, "")

            category = PRESET_TO_CATEGORY.get(preset_key)
            if category:
                target_persona = _find_persona_by_keyword(persona_names, category)
                if target_persona and st.session_state.selected_persona_name != target_persona:
                    st.session_state.selected_persona_name = target_persona
                    st.rerun()

        # =========================
        # ✅ マイテンプレ管理（GitHubに保存/削除）
        # =========================
        with st.expander("🧷 マイテンプレ管理（GitHubに保存）", expanded=False):
            token, owner, repo, path = _gh_conf()
            if not (token and owner and repo and path):
                st.warning("GitHub保存を使うには Streamlit Secrets に GITHUB_TOKEN / GITHUB_OWNER / GITHUB_REPO / GITHUB_TEMPLATES_PATH を設定してください。")
            else:
                st.caption(f"保存先: {owner}/{repo} → {path}")

            new_tpl_name = st.text_input("テンプレ名（重複OK：上書き）", key="user_tpl_name")
            new_tpl_text = st.text_area("テンプレ本文（この内容を保存）", height=180, key="user_tpl_text")

            c1, c2 = st.columns([1, 1])

            with c1:
                if st.button("💾 保存（GitHubへ）", key="save_user_template"):
                    name = (new_tpl_name or "").strip()
                    text = (new_tpl_text or "").strip()
                    if not name:
                        st.warning("テンプレ名を入力してください。")
                    elif not text:
                        st.warning("テンプレ本文を入力してください。")
                    else:
                        try:
                            data, sha = github_get_file_json()
                            data[name] = text
                            github_put_file_json(
                                data=data,
                                sha=sha,
                                commit_message=f"Save user template: {name}"
                            )
                            st.session_state.user_templates = data
                            st.session_state.user_templates_sha = sha
                            st.success(f"保存しました: {name}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ 保存に失敗しました: {e}")

            with c2:
                saved_names = list((st.session_state.get("user_templates", {}) or {}).keys())
                delete_target = st.selectbox(
                    "削除するテンプレ",
                    options=["（選択なし）"] + saved_names,
                    key="delete_user_template_select"
                )
                if st.button("🗑 削除（GitHubへ）", key="delete_user_template_btn"):
                    if delete_target == "（選択なし）":
                        st.warning("削除対象を選んでください。")
                    else:
                        try:
                            data, sha = github_get_file_json()
                            data.pop(delete_target, None)
                            github_put_file_json(
                                data=data,
                                sha=sha,
                                commit_message=f"Delete user template: {delete_target}"
                            )
                            st.session_state.user_templates = data
                            st.session_state.user_templates_sha = sha
                            st.success(f"削除しました: {delete_target}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ 削除に失敗しました: {e}")

        news_content = st.text_area(
            "ニュース内容を入力",
            height=180,
            value=st.session_state.news_manual_text,
            placeholder="投稿の元になるニュースやトピックを入力してください..."
        )
        st.session_state.news_manual_text = news_content

    st.markdown("---")

    # 投稿生成ボタン
    if st.button("🎨 投稿を生成", type="primary", use_container_width=True):

        if not anthropic_key:
            st.error("❌ Anthropic API Keyを設定してください")
        elif not news_content:
            st.error("❌ ニュース内容を取得または入力してください")
        else:
            with st.spinner(f"{selected_persona.name} として投稿を生成中..."):
                try:
                    generator = ThreadsPostGenerator(anthropic_key)

                    # ✅ 追加①：UIトグルを生成エンジンへ反映（ノウハウ/数値＝Calm優先）
                    generator.ui_mode_calm_priority = st.session_state.generation_mode_calm

                    # ✅ 追加②：テーマ選択→ forced_topic_tag を生成エンジンへ渡す（全投稿に強制）
                    generator.forced_topic_tag = forced_topic_tag

                    posts = generator.generate_posts(
                        persona=selected_persona,
                        news_content=news_content,
                        num_variations=num_posts
                    )

                    st.session_state.generated_posts = posts

                    # ✅ 重要：再生成時の表示更新対策（run_id を更新）
                    st.session_state.generation_run_id = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")

                    st.success(f"✅ {len(posts)}件の投稿を生成しました！")

                    # 表示を確実に更新したい場合は有効化（必要なら）
                    # st.rerun()

                except Exception as e:
                    st.error(f"❌ エラーが発生しました: {e}")

    # =========================================================
    # ✅ 生成された投稿を表示（post_textをメイン表示）
    # =========================================================
    if st.session_state.generated_posts:
        st.markdown("---")
        st.subheader("📋 生成された投稿（post_textをメイン表示）")
        st.caption("投稿本文（post_text）だけがまず見えるようにし、詳細情報は折りたたみに移動しました。")

        run_id = st.session_state.get("generation_run_id", "0")

        for i, post in enumerate(st.session_state.generated_posts, 1):
            score = float(post.get("score", 0) or 0)

            if score >= 80:
                badge_color = "🟢"
            elif score >= 60:
                badge_color = "🟡"
            else:
                badge_color = "🔴"

            st.markdown(f"### {badge_color} 投稿案 {i}（スコア: {score:.1f}点）")

            st.text_area(
                "投稿内容",
                value=post.get("post_text", ""),
                height=180,
                key=f"post_text_{run_id}_{i}",
                label_visibility="collapsed",
            )

            meta_cols = st.columns([2, 2, 2, 1])
            with meta_cols[0]:
                topic = post.get("topic_tag", "")
                st.write(f"**タグ**: {topic}" if topic else "**タグ**: （なし）")
            with meta_cols[1]:
                st.write(f"**文字数**: {len(post.get('post_text', '') or '')}文字")
            with meta_cols[2]:
                st.write(f"**到達予測**: {post.get('predicted_stage', 'N/A')}")
            with meta_cols[3]:
                if st.button("📤 投稿", key=f"publish_{run_id}_{i}"):
                    if st.session_state.threads_client:
                        result = st.session_state.threads_client.create_post(post.get("post_text", ""))
                        if result:
                            st.success("投稿しました！")
                    else:
                        st.warning("Threads連携を設定してください（タブ3）")

            # ✅ 追加③：生成結果のExpanderに style_mode / lens / topic_tag を表示
            with st.expander("🔍 詳細（hook/body/cta・スコア内訳・思考プロセス）", expanded=False):
                hook, body, cta = extract_hook_body_cta(post)
                has_structured = any([hook, body, cta])

                st.markdown("#### 🏷️ メタ情報（検証用）")
                st.write(f"**topic_tag**: {post.get('topic_tag', 'N/A')}")
                st.write(f"**style_mode**: {post.get('style_mode', 'N/A')}")
                st.write(f"**lens**: {post.get('lens', 'N/A')}")

                st.markdown("---")

                if has_structured:
                    st.markdown("#### 🧩 構成（hook / body / cta）")
                    if hook:
                        st.markdown("**Hook**")
                        st.write(hook)
                    if body:
                        st.markdown("**Body**")
                        st.write(body)
                    if cta:
                        st.markdown("**CTA**")
                        st.write(cta)
                    st.markdown("---")
                else:
                    st.info("この投稿案には hook/body/cta が個別フィールドとして返っていません（post_textのみ表示しています）。")

                score_details = post.get("score_details", {})
                if score_details:
                    st.markdown("#### 📊 スコア内訳")
                    st.json(score_details)

                reasoning = post.get("reasoning", "")
                if reasoning:
                    st.markdown("#### 🧠 reasoning")
                    st.write(reasoning)

            st.markdown("---")


# タブ2：ペルソナ管理
with tab2:
    st.header("ペルソナ管理")

    if st.session_state.personas:
        st.subheader("登録済みペルソナ")
        for i, persona in enumerate(st.session_state.personas):
            with st.expander(f"👤 {persona.name}"):
                st.write(f"**専門分野**: {persona.specialty}")
                st.write(f"**口調**: {persona.tone}")
                st.write(f"**価値観**: {persona.values}")
                st.write(f"**ターゲット**: {persona.target_audience}")
                st.write(f"**目標**: {persona.goals}")

                if st.button("削除", key=f"delete_persona_{i}"):
                    if len(st.session_state.personas) > 1:
                        st.session_state.personas.pop(i)

                        # 選択中だった場合のケア
                        if st.session_state.selected_persona_name == persona.name:
                            st.session_state.selected_persona_name = st.session_state.personas[0].name

                        st.success(f"{persona.name} を削除しました")
                        st.rerun()
                    else:
                        st.warning("最低1つのペルソナが必要です")

    st.markdown("---")
    st.subheader("新しいペルソナを追加")

    with st.form("new_persona_form"):
        name = st.text_input("名前")
        specialty = st.text_input("専門分野")
        tone = st.text_input("口調", value="丁寧で親しみやすい")
        values = st.text_area("価値観", height=100)
        target_audience = st.text_area("ターゲット", height=100)
        goals = st.text_area("目標", height=100)

        submitted = st.form_submit_button("追加")
        if submitted:
            if name and specialty:
                new_persona = PersonaConfig(
                    name=name,
                    specialty=specialty,
                    tone=tone,
                    values=values,
                    target_audience=target_audience,
                    goals=goals
                )
                st.session_state.personas.append(new_persona)
                st.success(f"{name} を追加しました")
                st.rerun()
            else:
                st.error("名前と専門分野は必須です")


# タブ3：Threads連携
with tab3:
    st.header("Threads連携")

    if not threads_app_id or not threads_app_secret:
        st.warning("Threads App ID / Secret をサイドバーで設定してください。")
    else:
        st.write("Threads API連携を設定します。")

        if st.button("🔗 Threadsクライアント初期化"):
            try:
                st.session_state.threads_client = ThreadsAPIClient(
                    app_id=threads_app_id,
                    app_secret=threads_app_secret
                )
                st.success("Threadsクライアントを初期化しました。")
            except Exception as e:
                st.error(f"初期化エラー: {e}")

        st.markdown("---")
        st.subheader("テスト投稿")

        test_text = st.text_area("テスト投稿内容", height=120, value="テスト投稿です。返信で反応ください？")

        if st.button("📤 テスト投稿を送信"):
            if st.session_state.threads_client:
                try:
                    result = st.session_state.threads_client.create_post(test_text)
                    if result:
                        st.success("テスト投稿しました！")
                except Exception as e:
                    st.error(f"投稿エラー: {e}")
            else:
                st.warning("Threadsクライアントが未初期化です。上のボタンで初期化してください。")


# タブ4：分析
with tab4:
    st.header("分析")
    st.info("分析タブは開発中です。今後、投稿パフォーマンスの可視化などを追加できます。")
