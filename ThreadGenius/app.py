"""
ThreadGenius - メインアプリケーション
Streamlitを使用した対話的UI
"""

import streamlit as st
import json
import os
from datetime import datetime, timedelta
from config import PersonaConfig, DEFAULT_PERSONAS, DEFAULT_RSS_FEEDS, ANTHROPIC_API_KEY, THREADS_APP_ID, THREADS_APP_SECRET
from ai_generator import ThreadsPostGenerator
from news_collector import NewsCollector
from threads_api import ThreadsAPIClient

# ページ設定
st.set_page_config(
    page_title="ThreadGenius - Threads投稿自動生成",
    page_icon="🚀",
    layout="wide"
)

# セッション状態の初期化
if "personas" not in st.session_state:
    st.session_state.personas = DEFAULT_PERSONAS

if "generated_posts" not in st.session_state:
    st.session_state.generated_posts = []

if "rss_feeds" not in st.session_state:
    st.session_state.rss_feeds = DEFAULT_RSS_FEEDS.copy()

if "threads_client" not in st.session_state:
    st.session_state.threads_client = None

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
        # ペルソナ選択
        persona_names = [p.name for p in st.session_state.personas]
        selected_persona_name = st.selectbox(
            "ペルソナを選択",
            persona_names,
            help="投稿するキャラクターを選んでください"
        )
        
        selected_persona = next(p for p in st.session_state.personas if p.name == selected_persona_name)
        
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
    
    news_content = ""
    
    if news_source_type == "RSSフィードから自動取得":
        if st.button("🔄 最新ニュースを取得"):
            with st.spinner("ニュース収集中..."):
                collector = NewsCollector(st.session_state.rss_feeds)
                news_items = collector.collect_news(limit=5)
                
                if news_items:
                    st.success(f"{len(news_items)}件のニュースを取得しました！")
                    
                    # ニュース選択
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
        news_content = st.text_area(
            "ニュース内容を入力",
            height=150,
            placeholder="投稿の元になるニュースやトピックを入力してください..."
        )
    
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
                    posts = generator.generate_posts(
                        persona=selected_persona,
                        news_content=news_content,
                        num_variations=num_posts
                    )
                    
                    st.session_state.generated_posts = posts
                    st.success(f"✅ {len(posts)}件の投稿を生成しました！")
                    
                except Exception as e:
                    st.error(f"❌ エラーが発生しました: {e}")
    
    # 生成された投稿を表示
    if st.session_state.generated_posts:
        st.markdown("---")
        st.subheader("📋 生成された投稿")
        
        for i, post in enumerate(st.session_state.generated_posts, 1):
            score = post.get("score", 0)
            
            # スコアに応じた色
            if score >= 80:
                badge_color = "🟢"
            elif score >= 60:
                badge_color = "🟡"
            else:
                badge_color = "🔴"
            
            with st.expander(f"{badge_color} 投稿案 {i} - スコア: {score:.1f}点"):
                
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown("### 📝 投稿文")
                    st.text_area(
                        "投稿内容",
                        value=post.get("post_text", ""),
                        height=200,
                        key=f"post_text_{i}",
                        label_visibility="collapsed"
                    )
                    
                    st.write(f"**トピックタグ**: {post.get('topic_tag', '')}")
                    st.write(f"**文字数**: {len(post.get('post_text', ''))}文字")
                
                with col2:
                    st.markdown("### 📊 スコア詳細")
                    
                    score_details = post.get("score_details", {})
                    
                    for key, value in score_details.items():
                        st.metric(
                            label=key.replace("_", " ").title(),
                            value=f"{value:.2f}"
                        )
                
                st.markdown("---")
                
                col3, col4, col5 = st.columns([2, 2, 1])
                
                with col3:
                    st.write(f"**到達予測**: {post.get('predicted_stage', 'N/A')}")
                
                with col4:
                    st.write(f"**会話誘発**: {post.get('conversation_trigger', 'N/A')}")
                
                with col5:
                    if st.button("📤 投稿", key=f"publish_{i}"):
                        if st.session_state.threads_client:
                            result = st.session_state.threads_client.create_post(
                                post.get("post_text", "")
                            )
                            if result:
                                st.success("投稿しました！")
                        else:
                            st.warning("Threads連携を設定してください（タブ3）")
                
                with st.expander("🧠 AI の思考プロセス"):
                    st.write(post.get("reasoning", "説明なし"))

# タブ2：ペルソナ管理
with tab2:
    st.header("🎭 ペルソナ管理")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("既存のペルソナ")
        
        for i, persona in enumerate(st.session_state.personas):
            with st.expander(f"👤 {persona.name}"):
                st.write(f"**専門分野**: {persona.specialty}")
                st.write(f"**口調**: {persona.tone}")
                st.write(f"**価値観**: {persona.values}")
                st.write(f"**ターゲット**: {persona.target_audience}")
                st.write(f"**目標**: {persona.goals}")
                
                if st.button(f"🗑️ 削除", key=f"delete_persona_{i}"):
                    st.session_state.personas.pop(i)
                    st.rerun()
    
    with col2:
        st.subheader("新しいペルソナを作成")
        
        with st.form("new_persona_form"):
            name = st.text_input("名前")
            specialty = st.text_input("専門分野")
            tone = st.text_area("口調")
            values = st.text_area("価値観")
            target_audience = st.text_input("ターゲットオーディエンス")
            goals = st.text_area("目標")
            
            submitted = st.form_submit_button("➕ ペルソナを追加")
            
            if submitted and name and specialty:
                new_persona = PersonaConfig(
                    name=name,
                    specialty=specialty,
                    tone=tone,
                    values=values,
                    target_audience=target_audience,
                    goals=goals
                )
                
                st.session_state.personas.append(new_persona)
                st.success(f"✅ {name} を追加しました！")
                st.rerun()

# タブ3：Threads連携
with tab3:
    st.header("🔗 Threads API 連携")
    
    if not threads_app_id or not threads_app_secret:
        st.warning("⚠️ サイドバーでThreads App IDとApp Secretを設定してください")
    else:
        if st.session_state.threads_client is None:
            st.session_state.threads_client = ThreadsAPIClient(
                app_id=threads_app_id,
                app_secret=threads_app_secret
            )
        
        st.subheader("OAuth認証")
        
        if st.button("🔐 認証を開始"):
            st.session_state.threads_client.start_oauth_flow()
            st.info("ブラウザで認証を完了してください")
        
        st.markdown("---")
        
        auth_code = st.text_input(
            "認証コードを入力",
            help="認証後にリダイレクトされたURLの 'code=' パラメータを貼り付けてください"
        )
        
        if st.button("✅ 認証を完了") and auth_code:
            with st.spinner("認証中..."):
                success = st.session_state.threads_client.exchange_code_for_token(auth_code)
                
                if success:
                    st.success("🎉 認証成功！投稿できるようになりました")
                else:
                    st.error("❌ 認証に失敗しました")
        
        st.markdown("---")
        
        # テスト投稿
        st.subheader("テスト投稿")
        
        test_text = st.text_area(
            "テスト投稿内容",
            value="ThreadGeniusからのテスト投稿です！🚀",
            height=100
        )
        
        if st.button("📤 テスト投稿を送信"):
            if st.session_state.threads_client and st.session_state.threads_client.access_token:
                with st.spinner("投稿中..."):
                    result = st.session_state.threads_client.create_post(test_text)
                    
                    if result:
                        st.success("🎉 投稿成功！")
                        st.json(result)
            else:
                st.error("先に認証を完了してください")

# タブ4：分析
with tab4:
    st.header("📊 分析")
    
    st.info("🚧 この機能は開発中です")
    
    st.markdown("""
    ### 今後実装予定の機能
    
    - **投稿パフォーマンス分析**
      - いいね数、リプライ数、再投稿数の追跡
      - エンゲージメント率の計算
      
    - **4段階ステージ到達分析**
      - どのステージで止まったか
      - 改善ポイントの提案
      
    - **ペルソナ別パフォーマンス比較**
      - どのペルソナが最も効果的か
      
    - **投稿時間帯分析**
      - 最適な投稿時間の提案
    """)

# フッター
st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>🚀 ThreadGenius - あなた専用Threads投稿自動生成ツール</p>
    <p>2026年最新アルゴリズム対応 | Claude API Powered</p>
</div>
""", unsafe_allow_html=True)
