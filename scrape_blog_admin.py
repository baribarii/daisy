import logging
import time
import json
import re
import requests
from bs4 import BeautifulSoup
from blog_utils import extract_blog_id

# 로깅 설정
logger = logging.getLogger(__name__)

def scrape_blog_admin_mode(blog_url, access_token):
    """
    네이버 블로그 관리자 AJAX API를 사용하여 포스트 목록과 내용을 스크래핑합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        access_token (str): OAuth 액세스 토큰
        
    Returns:
        list: 포스트 목록 (각 항목은 딕셔너리 형태)
    """
    try:
        # 블로그 ID 추출
        blog_id = extract_blog_id(blog_url)
        logger.debug(f"블로그 ID 추출: {blog_id}")
        
        # OAuth 토큰으로 인증된 세션 생성
        session = create_authenticated_session(access_token)
        
        # 관리자 AJAX로 포스트 목록 가져오기
        posts = get_posts_via_admin_api(session, blog_id)
        
        if not posts:
            logger.warning("관리자 API로 포스트를 가져오지 못했습니다. 대체 메서드 시도가 필요합니다.")
            return []
            
        # 최대 30개로 제한
        if len(posts) > 30:
            logger.debug(f"포스트 수 제한: {len(posts)}개 -> 30개")
            posts = posts[:30]
        
        # 각 포스트 내용 가져오기
        detailed_posts = []
        
        for post in posts:
            log_no = post.get('logNo')
            if not log_no:
                continue
                
            # 포스트 상세 내용 가져오기
            post_detail = get_post_detail(session, blog_id, log_no)
            
            if post_detail:
                detailed_posts.append(post_detail)
                # 서버 부하 방지
                time.sleep(0.5)
        
        logger.debug(f"총 {len(detailed_posts)}개의 상세 포스트를 가져왔습니다.")
        return detailed_posts
        
    except Exception as e:
        logger.error(f"관리자 모드 스크래핑 중 오류: {str(e)}")
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


def get_posts_via_admin_api(session, blog_id):
    """
    네이버 블로그 관리자 AJAX API를 사용하여 포스트 목록을 가져옵니다.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        
    Returns:
        list: 포스트 목록
    """
    try:
        # 관리자 페이지 접속 (인증 초기화)
        init_url = f"https://blog.naver.com/{blog_id}"
        session.get(init_url, timeout=30)
        
        # ManageListAjax 엔드포인트로 게시물 목록 요청
        ajax_url = f"https://blog.naver.com/PostManageListAjax.naver?blogId={blog_id}"
        headers = {
            'Referer': init_url,
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        response = session.get(
            ajax_url,
            headers=headers,
            params={
                'blogId': blog_id,
                'listStatus': 'COMPLETE',  # 발행 완료된 글만
                'viewDate': 'ALL',  # 전체 기간
                'categoryNo': 0,    # 전체 카테고리
                'parentCategoryNo': 0,
                'sortType': 'DATE', # 날짜순
                'keyword': '',
                'property': 'ALL',
                'page': 1,
                'countPerPage': 30  # 30개씩
            },
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"관리자 API 응답 오류: {response.status_code}")
            return []
        
        # JSON 응답 파싱
        try:
            data = response.json()
            post_list = data.get('postList', [])
            
            # 필요한 정보 추출
            posts = []
            for post_info in post_list:
                post = {
                    'logNo': str(post_info.get('logNo', '')),
                    'title': post_info.get('title', ''),
                    'date': post_info.get('addDate', ''),
                    'is_private': post_info.get('openType') != 'PUBLIC',
                    'url': f"https://blog.naver.com/{blog_id}/{post_info.get('logNo', '')}"
                }
                posts.append(post)
                
            return posts
            
        except ValueError:
            # JSON 파싱 실패 시 HTML로 간주하고 파싱 시도
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # HTML에서 스크립트를 찾아 JSON 데이터 추출 시도
            for script in soup.find_all('script'):
                script_text = script.string
                if script_text and 'postList' in script_text:
                    # JSON 데이터 추출
                    match = re.search(r'postList\s*:\s*(\[.*?\])', script_text, re.DOTALL)
                    if match:
                        try:
                            post_list_json = match.group(1)
                            post_list = json.loads(post_list_json)
                            
                            posts = []
                            for post_info in post_list:
                                post = {
                                    'logNo': str(post_info.get('logNo', '')),
                                    'title': post_info.get('title', ''),
                                    'date': post_info.get('addDate', ''),
                                    'is_private': post_info.get('openType') != 'PUBLIC',
                                    'url': f"https://blog.naver.com/{blog_id}/{post_info.get('logNo', '')}"
                                }
                                posts.append(post)
                                
                            return posts
                        except:
                            continue
            
            # HTML에서 직접 포스트 목록 추출 시도
            posts = []
            for row in soup.select('.post_item'):
                try:
                    log_no = ''
                    title = ''
                    date = ''
                    is_private = False
                    
                    # logNo 추출
                    log_no_elem = row.select_one('a[href*="logNo="]')
                    if log_no_elem:
                        href = log_no_elem.get('href', '')
                        if 'logNo=' in href:
                            log_no = href.split('logNo=')[1].split('&')[0]
                    
                    # 제목 추출
                    title_elem = row.select_one('.title, .post_title')
                    if title_elem:
                        title = title_elem.get_text().strip()
                    
                    # 날짜 추출
                    date_elem = row.select_one('.date, .post_date')
                    if date_elem:
                        date = date_elem.get_text().strip()
                    
                    # 비공개 여부
                    private_elem = row.select_one('.private, .secret')
                    if private_elem:
                        is_private = True
                    
                    if log_no and title:
                        posts.append({
                            'logNo': log_no,
                            'title': title,
                            'date': date,
                            'is_private': is_private,
                            'url': f"https://blog.naver.com/{blog_id}/{log_no}"
                        })
                except Exception as e:
                    logger.error(f"HTML 항목 파싱 오류: {str(e)}")
                    continue
            
            return posts
            
    except Exception as e:
        logger.error(f"관리자 API 호출 오류: {str(e)}")
        return []


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
            logger.error(f"포스트 상세 조회 오류: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # iframe 확인 (네이버 블로그는 종종 iframe에 컨텐츠를 로드)
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
                except Exception as iframe_error:
                    logger.error(f"iframe 로드 실패: {str(iframe_error)}")
        
        # 1. 제목 추출
        title = ""
        title_selectors = [
            '.se-title-text', '.se-module-text', '.tit_h3', 
            '.pcol1', 'h3.tit_view', '.post_title'
        ]
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    break
        
        # 2. 내용 추출
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
        
        # 3. 날짜 추출
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
        
        # 4. 비공개 여부 확인
        is_private = False
        if "비공개" in soup.get_text() or "권한이 없습니다" in soup.get_text():
            is_private = True
        
        if title or content:
            return {
                'logNo': log_no,
                'title': title or '제목 없음',
                'content': content,
                'date': date,
                'is_private': is_private,
                'url': f"https://blog.naver.com/{blog_id}/{log_no}"
            }
        
        return None
        
    except Exception as e:
        logger.error(f"포스트 상세 내용 가져오기 실패: {str(e)}")
        return None


# 테스트 코드
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.DEBUG)
    
    print("이 모듈은 직접 실행하지 마시고, 다른 코드에서 import하여 사용하세요.")