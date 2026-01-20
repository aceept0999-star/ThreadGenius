"""
ニュース収集モジュール
RSSフィードからニュースを自動取得
"""

import feedparser
from typing import List, Dict, Optional
from datetime import datetime
import requests

class NewsCollector:
    """ニュース自動収集"""
    
    def __init__(self, rss_feeds: List[str]):
        self.rss_feeds = rss_feeds
        
    def collect_news(self, limit: int = 10, keywords: Optional[List[str]] = None) -> List[Dict]:
        """
        RSSフィードからニュースを収集
        
        Args:
            limit: 取得するニュース数
            keywords: フィルタリング用キーワード（指定した場合、キーワードを含むニュースのみ）
            
        Returns:
            ニュースリスト
        """
        all_news = []
        
        for feed_url in self.rss_feeds:
            try:
                news_items = self._fetch_from_feed(feed_url, keywords)
                all_news.extend(news_items)
            except Exception as e:
                print(f"フィード取得エラー [{feed_url}]: {e}")
                continue
        
        # 日付順にソート
        all_news.sort(key=lambda x: x.get("published", ""), reverse=True)
        
        return all_news[:limit]
    
    def _fetch_from_feed(self, feed_url: str, keywords: Optional[List[str]] = None) -> List[Dict]:
        """個別のRSSフィードから取得"""
        
        feed = feedparser.parse(feed_url)
        
        news_items = []
        
        for entry in feed.entries:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "")
            published = entry.get("published", "")
            
            # キーワードフィルタリング
            if keywords:
                if not any(kw in title or kw in summary for kw in keywords):
                    continue
            
            news_items.append({
                "title": title,
                "summary": summary,
                "link": link,
                "published": published,
                "source": feed_url
            })
        
        return news_items
    
    def get_trending_topics(self) -> List[str]:
        """
        トレンドトピックを取得（簡易実装）
        実際にはThreads APIやX APIから取得するのが理想
        """
        # プレースホルダー：実際にはAPIから取得
        trending = [
            "AI", "ビジネス", "健康", "グルメ", "旅行",
            "テクノロジー", "マーケティング", "副業"
        ]
        return trending
    
    def add_custom_feed(self, feed_url: str):
        """カスタムRSSフィードを追加"""
        if feed_url not in self.rss_feeds:
            self.rss_feeds.append(feed_url)
            print(f"フィード追加: {feed_url}")
    
    def format_for_ai(self, news_item: Dict) -> str:
        """AIに渡す形式にフォーマット"""
        return f"""
【ニュース】
タイトル: {news_item['title']}
概要: {news_item['summary'][:200]}
ソース: {news_item['link']}
公開日: {news_item.get('published', '不明')}
"""
