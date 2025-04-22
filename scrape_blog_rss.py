import logging
import time
import json
import re
import requests
from bs4 import BeautifulSoup
from blog_utils import extract_blog_id

# 로깅 설정
logger = logging.getLogger(__name__)

def fetch_rss_lognos(blog_id):
    """
    RSS 피드에서 포스트 ID(logNo) 목록만 가져옵니다.
    
    Args:
        blog_id (str): 블로그 ID
        
    Returns:
        list: logNo 목록 (최대 100개)
    """
    try:
        # RSS URL 구성
        rss_url = f"https://rss.blog.naver.com/{blog_id}.xml"
        logger.debug(f"RSS URL: {rss_url}")
        
        # 재시도 로직
        max_retries = 2
        retry_count = 0
        response = None
        
        # 일반 세션으로 충분함
        session = requests.Session()
        
        while retry_count <= max_retries:
            try:
                logger.debug(f"RSS 요청 시도 {retry_count+1}/{max_retries+1}")
                response = session.get(rss_url, timeout=5)
                if response.status_code == 200:
                    break
            except Exception as retry_error:
                logger.warning(f"RSS 요청 재시도 {retry_count+1}/{max_retries+1}: {str(retry_error)}")
            
            retry_count += 1
            time.sleep(1)  # backoff
        
        if not response or response.status_code != 200:
            logger.error(f"RSS 응답 오류: {response.status_code if response else 'No response'}")
            return []
        
        # logNo 목록 추출
        log_nos = []
        
        # XML 파싱 시도
        try:
            soup = BeautifulSoup(response.content, 'xml')
            
            # RSS 구조 확인
            if soup and soup.find('rss'):
                # <item> 태그 찾기
                items = soup.find_all('item')
                
                for item in items:
                    # <guid> 태그에서 logNo 추출
                    guid = item.find('guid')
                    log_no = None
                    
                    if guid and guid.text:
                        guid_url = guid.text.strip()
                        # 형식: https://blog.naver.com/[blogId]/[logNo]
                        if f'/{blog_id}/' in guid_url:
                            log_no = guid_url.split(f'/{blog_id}/')[1].split('?')[0].strip()
                    
                    if not log_no:
                        # <link> 태그에서 추출 시도
                        link = item.find('link')
                        if link and link.text:
                            link_url = link.text.strip()
                            if 'logNo=' in link_url:
                                log_no = link_url.split('logNo=')[1].split('&')[0].strip()
                    
                    if log_no and log_no.isdigit() and log_no not in log_nos:
                        log_nos.append(log_no)
                        
                        # 최대 100개 제한
                        if len(log_nos) >= 100:
                            break
        except Exception as xml_error:
            logger.error(f"XML 파싱 오류: {str(xml_error)}")
        
        # 결과가 없으면 HTML 파싱 시도
        if not log_nos:
            try:
                soup = BeautifulSoup(response.text, 'html.parser')
                links = soup.find_all('a', href=True)
                
                for link in links:
                    href = link['href']
                    
                    # /blogId/logNo 패턴 찾기
                    if f'/{blog_id}/' in href:
                        try:
                            log_no = href.split(f'/{blog_id}/')[1].split('?')[0]
                            if log_no.isdigit() and log_no not in log_nos:
                                log_nos.append(log_no)
                                
                                # 최대 100개 제한
                                if len(log_nos) >= 100:
                                    break
                        except:
                            continue
                    
                    # logNo= 파라미터 찾기
                    elif 'logNo=' in href:
                        try:
                            log_no = href.split('logNo=')[1].split('&')[0]
                            if log_no.isdigit() and log_no not in log_nos:
                                log_nos.append(log_no)
                                
                                # 최대 100개 제한
                                if len(log_nos) >= 100:
                                    break
                        except:
                            continue
            except Exception as html_error:
                logger.error(f"HTML 파싱 오류: {str(html_error)}")
        
        logger.debug(f"RSS에서 {len(log_nos)}개의 logNo 발견")
        return log_nos
        
    except Exception as e:
        logger.error(f"RSS logNo 추출 오류: {str(e)}")
        return []

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
        
        # RSS 피드에서 logNo 목록 가져오기
        log_nos = fetch_rss_lognos(blog_id)
        
        if not log_nos:
            logger.warning("RSS에서 포스트 ID를 찾을 수 없습니다")
            return []
        
        # 세션 생성 - RSS는 OAuth 없이도 가능하지만 접근성을 높이기 위해 토큰 사용
        session = create_authenticated_session(access_token)
        
        # 포스트 상세 내용 수집
        posts = []
        
        # 최대 30개로 제한
        if len(log_nos) > 30:
            logger.debug(f"포스트 수 제한: {len(log_nos)}개 -> 30개")
            log_nos = log_nos[:30]
        
        for log_no in log_nos:
            try:
                post_detail = get_post_detail(session, blog_id, log_no)
                if post_detail:
                    posts.append(post_detail)
                    # 서버 부하 방지
                    time.sleep(0.5)
            except Exception as post_error:
                logger.error(f"포스트 {log_no} 처리 중 오류: {str(post_error)}")
                continue
        
        logger.debug(f"RSS 모드로 {len(posts)}개의 포스트를 찾았습니다.")
        return posts
    
    except Exception as e:
        logger.error(f"RSS 스크래핑 중 오류 발생: {str(e)}")
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