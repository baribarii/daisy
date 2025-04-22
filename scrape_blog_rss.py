import logging
import time
import requests
from bs4 import BeautifulSoup
from blog_utils import extract_blog_id

# 로깅 설정
logger = logging.getLogger(__name__)

def scrape_blog_rss_mode(blog_url, access_token=None):
    """
    네이버 블로그 RSS 피드를 사용하여 공개된 포스트 목록을 스크래핑합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        access_token (str, optional): 사용하지 않지만 인터페이스 일관성을 위해 남김
        
    Returns:
        list: 포스트 목록 (각 항목은 딕셔너리 형태)
    """
    try:
        # 블로그 ID 추출
        blog_id = extract_blog_id(blog_url)
        logger.debug(f"블로그 ID 추출: {blog_id}")
        
        # RSS 피드 URL
        rss_url = f"https://rss.blog.naver.com/{blog_id}.xml"
        
        # RSS 피드 가져오기
        response = requests.get(rss_url, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"RSS 피드 응답 오류: {response.status_code}")
            return []
        
        # XML 파싱
        soup = BeautifulSoup(response.text, 'xml')
        if not soup.find('rss'):
            # XML 파서가 없는 경우 lxml HTML 파서 사용
            soup = BeautifulSoup(response.text, 'html.parser')
        
        # 피드 아이템 추출
        items = soup.find_all('item')
        logger.debug(f"RSS 피드에서 {len(items)}개 항목 발견")
        
        if not items:
            logger.warning("RSS 피드에서 항목을 찾을 수 없습니다")
            return []
        
        # 각 아이템에서 정보 추출
        posts = []
        
        for item in items:
            try:
                # 필수 정보 추출
                title_tag = item.find('title')
                link_tag = item.find('link')
                desc_tag = item.find('description')
                date_tag = item.find('pubDate')
                guid_tag = item.find('guid')
                
                if not (title_tag and link_tag):
                    continue
                
                title = title_tag.text
                link = link_tag.text
                content = desc_tag.text if desc_tag else ""
                date = date_tag.text if date_tag else ""
                
                # 링크에서 logNo 추출
                log_no = ""
                if "logNo=" in link:
                    log_no = link.split("logNo=")[1].split("&")[0]
                elif guid_tag:
                    # GUID에서 logNo 추출 시도
                    guid = guid_tag.text
                    if "logNo=" in guid:
                        log_no = guid.split("logNo=")[1].split("&")[0]
                
                # logNo가 없으면 링크에서 패턴 검색
                if not log_no and f"/{blog_id}/" in link:
                    parts = link.split(f"/{blog_id}/")[1].split("?")[0].split("/")
                    for part in parts:
                        if part.isdigit():
                            log_no = part
                            break
                
                if log_no and title:
                    post = {
                        'logNo': log_no,
                        'title': title,
                        'content': clean_html_content(content),
                        'date': date,
                        'is_private': False,  # RSS는 공개 글만 포함
                        'url': link
                    }
                    posts.append(post)
            except Exception as item_error:
                logger.error(f"RSS 항목 파싱 오류: {str(item_error)}")
                continue
        
        # 최대 30개로 제한
        if len(posts) > 30:
            logger.debug(f"포스트 수 제한: {len(posts)}개 -> 30개")
            posts = posts[:30]
            
        # 각 포스트 상세 내용 강화 시도
        if access_token:
            logger.debug("OAuth 토큰 있음: 상세 내용 강화 시도")
            session = create_authenticated_session(access_token)
            
            for i, post in enumerate(posts):
                log_no = post.get('logNo')
                if not log_no or post.get('content'):
                    continue
                
                # 포스트 상세 내용 가져오기
                try:
                    post_detail = get_post_detail(session, blog_id, log_no)
                    if post_detail and post_detail.get('content'):
                        post['content'] = post_detail.get('content')
                        if post_detail.get('date'):
                            post['date'] = post_detail.get('date')
                except Exception as detail_error:
                    logger.error(f"상세 내용 강화 오류: {str(detail_error)}")
                
                # 서버 부하 방지
                time.sleep(0.5)
        
        return posts
        
    except Exception as e:
        logger.error(f"RSS 모드 스크래핑 중 오류: {str(e)}")
        return []


def create_authenticated_session(access_token):
    """
    OAuth 액세스 토큰으로 인증된 세션을 생성합니다.
    
    Args:
        access_token (str): OAuth 액세스 토큰
        
    Returns:
        requests.Session: 인증된 세션 객체
    """
    session = requests.Session()
    
    # 토큰을 쿠키와 헤더에 모두 설정 (네이버의 다양한 인증 방식 지원)
    session.headers.update({
        'Authorization': f'Bearer {access_token}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    # OAuth 토큰을 쿠키로 변환 (네이버 블로그 인증에 필요)
    if access_token:
        token_prefix = access_token[:16] if len(access_token) >= 16 else access_token
        token_suffix = access_token[-16:] if len(access_token) >= 16 else access_token
        
        # 네이버 인증 쿠키 설정
        cookies = {
            'NID_AUT': token_prefix,
            'NID_SES': token_suffix
        }
        
        session.cookies.update(cookies)
    
    return session


def get_post_detail(session, blog_id, log_no):
    """
    특정 포스트의 상세 내용을 가져옵니다.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        log_no (str): 포스트 번호
        
    Returns:
        dict: 포스트 상세 정보
    """
    try:
        url = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
        response = session.get(url, timeout=30)
        
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # iframe 확인
        iframe = soup.select_one('iframe#mainFrame')
        if iframe:
            iframe_src = iframe.get('src')
            if iframe_src:
                # iframe URL 처리
                if iframe_src.startswith('/'):
                    iframe_src = f"https://blog.naver.com{iframe_src}"
                elif not iframe_src.startswith('http'):
                    iframe_src = f"https://blog.naver.com/{iframe_src}"
                
                try:
                    iframe_response = session.get(iframe_src, timeout=30)
                    if iframe_response.status_code == 200:
                        soup = BeautifulSoup(iframe_response.text, 'html.parser')
                except:
                    pass
        
        # 내용 추출
        content = ""
        content_selectors = [
            '.se-main-container', '.post_ct', '#postViewArea', 
            '.se_component_wrap', '.view', '.post-view'
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # 불필요한 요소 제거
                for remove_sel in ['script', 'style', '.comment_area', '.btn_area']:
                    for el in content_elem.select(remove_sel):
                        el.decompose()
                
                content = content_elem.get_text(separator='\n', strip=True)
                if content:
                    break
        
        # 날짜 추출
        date = ""
        date_selectors = [
            '.se_publishDate', '.date', '.se_date', '.pub_date', '.se-module-date'
        ]
        
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                date = date_elem.get_text().replace('작성일', '').strip()
                if date:
                    break
        
        return {
            'content': content,
            'date': date
        }
        
    except Exception as e:
        logger.error(f"RSS 상세 내용 가져오기 실패: {str(e)}")
        return None


def clean_html_content(html_content):
    """
    HTML 콘텐츠에서 텍스트만 추출합니다.
    
    Args:
        html_content (str): HTML 형식의 콘텐츠
        
    Returns:
        str: 정리된 텍스트
    """
    if not html_content:
        return ""
    
    # BeautifulSoup으로 파싱
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 불필요한 태그 제거
    for tag in soup(['script', 'style']):
        tag.decompose()
    
    # 텍스트만 추출
    text = soup.get_text(separator='\n', strip=True)
    
    # 연속된 공백 제거
    import re
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


# 테스트 코드
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.DEBUG)
    
    print("이 모듈은 직접 실행하지 마시고, 다른 코드에서 import하여 사용하세요.")