import os
import logging
import requests
from requests_oauthlib import OAuth2Session
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# 네이버 OAuth 설정
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET')
# Replit에서는 동적으로 설정됨
NAVER_REDIRECT_URI = None

# OAuth 관련 URL
NAVER_AUTH_URL = 'https://nid.naver.com/oauth2.0/authorize'
NAVER_TOKEN_URL = 'https://nid.naver.com/oauth2.0/token'
NAVER_PROFILE_URL = 'https://openapi.naver.com/v1/nid/me'


def get_oauth_session():
    """
    OAuth2Session 객체 생성
    """
    return OAuth2Session(
        client_id=NAVER_CLIENT_ID,
        redirect_uri=NAVER_REDIRECT_URI,
        scope=['blog', 'read_profile']
    )


def get_authorization_url(callback_url=None):
    """
    OAuth 인증 URL 생성
    """
    global NAVER_REDIRECT_URI
    if callback_url:
        NAVER_REDIRECT_URI = callback_url

    oauth = get_oauth_session()
    authorization_url, state = oauth.authorization_url(NAVER_AUTH_URL)
    
    logger.debug(f"Authorization URL: {authorization_url}")
    return authorization_url, state


def get_token_from_code(code, state=None):
    """
    인증 코드로부터 토큰 발급
    """
    try:
        oauth = get_oauth_session()
        token = oauth.fetch_token(
            token_url=NAVER_TOKEN_URL,
            client_secret=NAVER_CLIENT_SECRET,
            code=code
        )
        logger.debug("Successfully retrieved token")
        return token
    except Exception as e:
        logger.error(f"Error fetching token: {str(e)}")
        raise


def get_user_info(token):
    """
    액세스 토큰으로 사용자 정보 조회
    """
    try:
        headers = {
            'Authorization': f'Bearer {token["access_token"]}',
            'Content-Type': 'application/json'
        }
        response = requests.get(NAVER_PROFILE_URL, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if data.get('resultcode') == '00':
                return data.get('response', {})
        
        logger.error(f"Failed to get user info: {response.text}")
        return None
    except Exception as e:
        logger.error(f"Error getting user info: {str(e)}")
        return None


def refresh_token(refresh_token):
    """
    리프레시 토큰으로 새 액세스 토큰 발급
    """
    try:
        params = {
            'grant_type': 'refresh_token',
            'client_id': NAVER_CLIENT_ID,
            'client_secret': NAVER_CLIENT_SECRET,
            'refresh_token': refresh_token
        }
        response = requests.get(NAVER_TOKEN_URL, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Failed to refresh token: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Error refreshing token: {str(e)}")
        return None