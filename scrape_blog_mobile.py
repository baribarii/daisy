import logging
import time
import json
import re
import requests
from bs4 import BeautifulSoup
from blog_utils import extract_blog_id

# 로깅 설정
logger = logging.getLogger(__name__)

def scrape_blog_mobile_mode(blog_url, access_token):
    """
    네이버 모바일 블로그 API를 사용하여 포스트 목록과 내용을 스크래핑합니다.
    
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
        
        # 모바일 API로 포스트 목록 가져오기
        posts = get_posts_via_mobile_api(session, blog_id)
        
        if not posts:
            logger.warning("모바일 API로 포스트를 가져오지 못했습니다. 대체 메서드 시도가 필요합니다.")
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
        logger.error(f"모바일 모드 스크래핑 중 오류: {str(e)}")
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
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1'
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


def get_posts_via_mobile_api(session, blog_id):
    """
    네이버 모바일 블로그 API를 사용하여 포스트 목록을 가져옵니다.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        
    Returns:
        list: 포스트 목록
    """
    try:
        # 모바일 API 엔드포인트들
        endpoints = [
            # 1. 모바일 메인 페이지 (기본)
            f"https://m.blog.naver.com/api/blogs/{blog_id}/post-list?categoryNo=0&tabType=RECENT",
            # 2. 모바일 PostList 페이지
            f"https://m.blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0",
            # 3. 오래된 API 호환성
            f"https://m.blog.naver.com/PluginPost.naver?blogId={blog_id}"
        ]
        
        posts = []
        
        # 각 엔드포인트 시도
        for idx, url in enumerate(endpoints):
            logger.debug(f"모바일 API 시도 #{idx+1}: {url}")
            
            try:
                response = session.get(url, timeout=30)
                
                if response.status_code != 200:
                    logger.warning(f"API #{idx+1} 응답 오류: {response.status_code}")
                    continue
                
                # 1. JSON 응답인지 확인
                if 'application/json' in response.headers.get('Content-Type', ''):
                    data = response.json()
                    
                    # 새로운 모바일 API 형식
                    if 'result' in data and 'postList' in data.get('result', {}):
                        post_list = data['result']['postList']
                        
                        for post_info in post_list:
                            post = {
                                'logNo': str(post_info.get('logNo', '')),
                                'title': post_info.get('title', ''),
                                'date': post_info.get('publishDate', ''),
                                'is_private': post_info.get('openType', '') != 'PUBLIC',
                                'url': f"https://blog.naver.com/{blog_id}/{post_info.get('logNo', '')}"
                            }
                            posts.append(post)
                        
                        if posts:
                            return posts
                
                # 2. HTML 응답 파싱
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # JSON 데이터 찾기 (페이지에 내장된 JSON)
                for script in soup.find_all('script'):
                    script_text = script.string
                    if not script_text:
                        continue
                        
                    # JSON 객체 추출 시도
                    json_pattern = re.compile(r'(?:blogPostListForm|blogInfo|postList)\s*=\s*(\{.*?\});', re.DOTALL)
                    json_matches = json_pattern.findall(script_text)
                    
                    for json_str in json_matches:
                        try:
                            # JSON 문자열 정리 및 파싱
                            json_str = re.sub(r'(\w+):', r'"\1":', json_str)  # 키에 따옴표 추가
                            json_str = re.sub(r',\s*\}', '}', json_str)  # 후행 콤마 제거
                            data = json.loads(json_str)
                            
                            # 다양한 JSON 구조 처리
                            post_list = data.get('postList') or data.get('posts') or []
                            
                            if post_list:
                                for post_info in post_list:
                                    log_no = str(post_info.get('logNo', ''))
                                    title = post_info.get('title', '')
                                    date = post_info.get('addDate', '') or post_info.get('publishDate', '')
                                    
                                    if log_no and title:
                                        post = {
                                            'logNo': log_no,
                                            'title': title,
                                            'date': date,
                                            'is_private': False,  # 모바일 API에서는 확인 어려움
                                            'url': f"https://blog.naver.com/{blog_id}/{log_no}"
                                        }
                                        posts.append(post)
                                
                                if posts:
                                    return posts
                        except:
                            continue
                
                # 3. HTML에서 직접 포스트 목록 추출
                post_items = soup.select('.post_item, .list_item, .box_post, [class*="list_post"]')
                
                for item in post_items:
                    try:
                        # logNo 추출
                        log_no = ''
                        for a_tag in item.find_all('a'):
                            href = a_tag.get('href', '')
                            if 'logNo=' in href:
                                log_no = href.split('logNo=')[1].split('&')[0]
                                break
                        
                        if not log_no:
                            # /blogId/logNo 형식도 체크
                            for a_tag in item.find_all('a'):
                                href = a_tag.get('href', '')
                                if f'/{blog_id}/' in href:
                                    parts = href.split(f'/{blog_id}/')[1].split('?')[0].split('/')
                                    for part in parts:
                                        if part.isdigit():
                                            log_no = part
                                            break
                                    if log_no:
                                        break
                        
                        # 제목 추출
                        title_elem = item.select_one('.title, .tit, [class*="tit_post"], [class*="post_title"]')
                        title = title_elem.get_text(strip=True) if title_elem else ''
                        
                        # 날짜 추출
                        date_elem = item.select_one('.date, [class*="date_post"]')
                        date = date_elem.get_text(strip=True) if date_elem else ''
                        
                        if log_no and title:
                            post = {
                                'logNo': log_no,
                                'title': title,
                                'date': date,
                                'is_private': False,  # HTML에서 판단 어려움
                                'url': f"https://blog.naver.com/{blog_id}/{log_no}"
                            }
                            posts.append(post)
                    except Exception as item_error:
                        logger.error(f"HTML 항목 파싱 오류: {str(item_error)}")
                        continue
                
                if posts:
                    return posts
                    
            except Exception as endpoint_error:
                logger.error(f"API #{idx+1} 호출 오류: {str(endpoint_error)}")
        
        return posts
        
    except Exception as e:
        logger.error(f"모바일 API 호출 오류: {str(e)}")
        return []


def get_post_detail(session, blog_id, log_no):
    """
    특정 포스트의 상세 내용을 모바일 페이지에서 가져옵니다.
    
    Args:
        session (requests.Session): 인증된 세션
        blog_id (str): 블로그 ID
        log_no (str): 포스트 번호
        
    Returns:
        dict: 포스트 상세 정보
    """
    try:
        # 모바일 포스트 조회 URL
        url = f"https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
        response = session.get(url, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"모바일 포스트 상세 조회 오류: {response.status_code}")
            return None
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 1. 제목 추출
        title = ""
        title_selectors = [
            '.se-title-text', '.se-module-text', '.tit_h3', 
            '.se_title', '.pcol1', 'h3.tit_view', '.post_title', 
            '.se-documentTitle-titleText'
        ]
        
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title:
                    break
        
        # 내용 추출 - 모바일에서는 더 간단한 구조
        content = ""
        content_selectors = [
            '.se-main-container', '.post_ct', '#postViewArea', 
            '.se_component_wrap', '.view', '.post-view',
            '.se-module-text-paragraph', '.post_body', '#viewTypeSelector'
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
            '.se_publishDate', '.date', '.se_date', '.se-module-date', 
            '.post_date', '.se-date', '.date_post'
        ]
        
        for selector in date_selectors:
            date_elem = soup.select_one(selector)
            if date_elem:
                date = date_elem.get_text().replace('작성일', '').strip()
                if date:
                    break
        
        # 비공개 여부 확인
        is_private = False
        page_text = soup.get_text()
        if "비공개" in page_text or "권한이 없습니다" in page_text:
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
        logger.error(f"모바일 포스트 상세 내용 가져오기 실패: {str(e)}")
        return None


# 테스트 코드
if __name__ == "__main__":
    # 로깅 설정
    logging.basicConfig(level=logging.DEBUG)
    
    print("이 모듈은 직접 실행하지 마시고, 다른 코드에서 import하여 사용하세요.")