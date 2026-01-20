"""
Threads API連携モジュール
OAuth認証と投稿機能
"""

import requests
import json
from typing import Dict, Optional
from datetime import datetime, timedelta
import webbrowser

class ThreadsAPIClient:
    """Threads API クライアント"""
    
    def __init__(self, app_id: str, app_secret: str, redirect_uri: str = "https://localhost:8000/callback"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.redirect_uri = redirect_uri
        self.access_token = None
        self.user_id = None
        
        # Threads API エンドポイント
        self.base_url = "https://graph.threads.net"
        self.auth_url = "https://threads.net/oauth/authorize"
        self.token_url = "https://graph.threads.net/oauth/access_token"
        
    def get_authorization_url(self) -> str:
        """OAuth認証URLを生成"""
        
        scopes = [
            "threads_basic",
            "threads_content_publish",
            "threads_manage_insights",
            "threads_manage_replies"
        ]
        
        params = {
            "client_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "scope": ",".join(scopes),
            "response_type": "code"
        }
        
        url = f"{self.auth_url}?" + "&".join([f"{k}={v}" for k, v in params.items()])
        return url
    
    def start_oauth_flow(self):
        """OAuth認証フローを開始"""
        auth_url = self.get_authorization_url()
        print(f"\n📱 以下のURLにアクセスして認証してください：\n")
        print(auth_url)
        print("\n認証後、リダイレクトされたURLの 'code=' パラメータをコピーしてください。\n")
        
        # ブラウザで開く
        webbrowser.open(auth_url)
        
    def exchange_code_for_token(self, code: str) -> bool:
        """認証コードをアクセストークンに交換"""
        
        params = {
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri,
            "code": code
        }
        
        try:
            response = requests.post(self.token_url, data=params)
            response.raise_for_status()
            
            data = response.json()
            self.access_token = data.get("access_token")
            self.user_id = data.get("user_id")
            
            print(f"✅ アクセストークン取得成功！")
            print(f"ユーザーID: {self.user_id}")
            
            # 長期トークンに交換
            self._exchange_for_long_lived_token()
            
            return True
            
        except Exception as e:
            print(f"❌ トークン取得エラー: {e}")
            return False
    
    def _exchange_for_long_lived_token(self):
        """短期トークンを長期トークンに交換（60日間有効）"""
        
        url = f"{self.base_url}/access_token"
        params = {
            "grant_type": "th_exchange_token",
            "client_secret": self.app_secret,
            "access_token": self.access_token
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            self.access_token = data.get("access_token")
            
            print(f"✅ 長期アクセストークンに交換成功（60日間有効）")
            
        except Exception as e:
            print(f"⚠️ 長期トークン交換失敗（短期トークンのまま使用）: {e}")
    
    def create_post(self, text: str, media_type: str = "TEXT") -> Optional[Dict]:
        """
        Threadsに投稿
        
        Args:
            text: 投稿テキスト（500文字以内）
            media_type: メディアタイプ（TEXT, IMAGE, VIDEO）
            
        Returns:
            投稿結果
        """
        
        if not self.access_token:
            print("❌ 認証が必要です。先にOAuth認証を完了してください。")
            return None
        
        # 文字数チェック
        if len(text) > 500:
            print(f"⚠️ 警告：投稿が500文字を超えています（{len(text)}文字）。切り詰めます。")
            text = text[:500]
        
        # Step 1: メディアコンテナを作成
        container_id = self._create_media_container(text, media_type)
        
        if not container_id:
            print("❌ メディアコンテナ作成失敗")
            return None
        
        # Step 2: 投稿を公開
        result = self._publish_media_container(container_id)
        
        return result
    
    def _create_media_container(self, text: str, media_type: str) -> Optional[str]:
        """メディアコンテナを作成"""
        
        url = f"{self.base_url}/v1.0/{self.user_id}/threads"
        
        data = {
            "media_type": media_type,
            "text": text,
            "access_token": self.access_token
        }
        
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
            
            result = response.json()
            container_id = result.get("id")
            
            print(f"✅ メディアコンテナ作成成功: {container_id}")
            return container_id
            
        except Exception as e:
            print(f"❌ メディアコンテナ作成エラー: {e}")
            if hasattr(e, 'response'):
                print(f"レスポンス: {e.response.text}")
            return None
    
    def _publish_media_container(self, container_id: str) -> Optional[Dict]:
        """メディアコンテナを公開"""
        
        url = f"{self.base_url}/v1.0/{self.user_id}/threads_publish"
        
        data = {
            "creation_id": container_id,
            "access_token": self.access_token
        }
        
        try:
            response = requests.post(url, data=data)
            response.raise_for_status()
            
            result = response.json()
            post_id = result.get("id")
            
            print(f"🎉 投稿成功！投稿ID: {post_id}")
            
            return {
                "success": True,
                "post_id": post_id,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ 投稿エラー: {e}")
            if hasattr(e, 'response'):
                print(f"レスポンス: {e.response.text}")
            return None
    
    def schedule_post(self, text: str, schedule_time: datetime) -> Dict:
        """
        投稿をスケジュール（簡易実装）
        実際には外部スケジューラーと連携が必要
        """
        
        return {
            "scheduled": True,
            "text": text,
            "schedule_time": schedule_time.isoformat(),
            "status": "pending"
        }
    
    def get_insights(self, post_id: str) -> Optional[Dict]:
        """投稿のインサイト（分析データ）を取得"""
        
        if not self.access_token:
            return None
        
        url = f"{self.base_url}/v1.0/{post_id}/insights"
        
        params = {
            "metric": "views,likes,replies,reposts,quotes",
            "access_token": self.access_token
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            print(f"インサイト取得エラー: {e}")
            return None
