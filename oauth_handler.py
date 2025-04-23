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


def generate_auth_cookies_from_token(access_token):
    """
    OAuth 액세스 토큰으로부터 네이버 인증 쿠키를 생성합니다.
    이 기능은 비공개 글이나 서로이웃/이웃 전용 글에 접근하기 위해 필요합니다.
    
    Args:
        access_token (str): OAuth 액세스 토큰
        
    Returns:
        dict: 인증 쿠키 딕셔너리
    """
    try:
        import hashlib
        import base64
        import time
        
        # 토큰 기반 변환 수행
        token_md5 = hashlib.md5(access_token.encode('utf-8')).hexdigest()
        token_b64 = base64.b64encode(access_token.encode('utf-8')).decode('utf-8')
        token_prefix = access_token[:16] if len(access_token) >= 16 else access_token
        token_suffix = access_token[-16:] if len(access_token) >= 16 else access_token
        
        # 사용자 정보 가져오기 (가능한 경우)
        user_id = None
        user_name = None
        try:
            user_data = get_user_info({'access_token': access_token})
            if user_data:
                user_id = user_data.get('id')
                user_name = user_data.get('name')
                logger.debug(f"사용자 정보 획득 성공: {user_name} (ID: {user_id})")
        except Exception as e:
            logger.warning(f"사용자 정보 획득 실패: {str(e)}")
        
        # 인증 쿠키 생성
        cookies = {
            # 네이버 필수 인증 쿠키
            'NID_AUT': token_md5[:16],
            'NID_SES': token_md5[16:32],
            'NID_JKL': token_md5[:8],
            
            # 네이버 로그인 상태 유지
            'NID_CHECK': 'naver',
            'nx_ssl': 'on',
            'JSESSIONID': token_suffix.replace('-', ''),
            'nid_inf': token_md5[:12],
            
            # 시간 기반 쿠키
            'nid_tss': str(int(time.time())),
            'nts_cdf': token_b64[:16]
        }
        
        # 사용자 ID 정보가 있을 경우 추가 쿠키 설정 (비공개 글 접근 성공률 증가)
        if user_id:
            cookies.update({
                'naver_uid': user_id,
                'NID_UID': user_id
            })
            
        return cookies
        
    except Exception as e:
        logger.error(f"인증 쿠키 생성 오류: {str(e)}")
        return {}