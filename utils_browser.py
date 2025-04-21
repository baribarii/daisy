from playwright.sync_api import sync_playwright
import time
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def fetch_all_posts_with_playwright(blog_id: str, cookie_str: str):
    """
    Playwright를 사용하여 네이버 블로그 콘텐츠를 수집합니다.
    
    1) 쿠키 문자열을 Playwright context에 설정
    2) 블로그 메인 PostList 페이지로 이동 → 스크롤 → 전체 logNo 추출
    3) 각 포스트 페이지 접속 → 콘텐츠 추출
    
    Args:
        blog_id (str): 네이버 블로그 아이디
        cookie_str (str): 네이버 쿠키 문자열
        
    Returns:
        list: 블로그 포스트 목록 (각각 딕셔너리 형태)
    """
    logger.debug(f"Starting Playwright scraping for blog: {blog_id}")
    posts = []
    
    try:
        with sync_playwright() as p:
            # Chromium 브라우저 실행 (headless=False 모드로 시도)
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            # 쿠키 분해 후 주입
            if cookie_str:
                for pair in cookie_str.split(';'):
                    if '=' not in pair:
                        continue
                    
                    name, value = pair.strip().split('=', 1)
                    logger.debug(f"Adding cookie: {name}")
                    try:
                        context.add_cookies([{
                            'name': name,
                            'value': value,
                            'domain': '.blog.naver.com',
                            'path': '/'
                        }])
                    except Exception as e:
                        logger.error(f"Error adding cookie {name}: {str(e)}")
            
            page = context.new_page()
            
            # 1. 먼저 전체 목록 페이지를 방문하여 모든 포스트 logNo 수집
            lognos = set()
            
            # 여러 페이지에서 logNo 수집
            for page_num in range(1, 6):  # 최대 5 페이지까지 시도
                try:
                    logger.debug(f"Visiting page {page_num}")
                    page.goto(f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&currentPage={page_num}", 
                              wait_until="domcontentloaded", timeout=30000)
                    
                    # 페이지 로딩 완료 대기
                    page.wait_for_load_state("networkidle", timeout=10000)
                    
                    # JavaScript가 실행된 후 더 많은 콘텐츠가 로드되도록 스크롤
                    for _ in range(3):
                        page.evaluate("window.scrollBy(0, document.body.scrollHeight / 2)")
                        time.sleep(1)
                    
                    # 페이지의 HTML 콘텐츠 가져오기
                    content = page.content()
                    
                    # logNo 찾기 (여러 패턴으로 시도)
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # 패턴 1: logNo 파라미터가 있는 링크 찾기
                    for link in soup.select('a[href*="logNo="]'):
                        href = link.get('href', '')
                        if 'logNo=' in href:
                            log_no = href.split('logNo=')[1].split('&')[0]
                            lognos.add(log_no)
                    
                    # 패턴 2: 현대 네이버 블로그 형식 (/blogId/logNo)
                    for link in soup.select(f'a[href*="/{blog_id}/"]'):
                        href = link.get('href', '')
                        # 숫자만 있는 부분을 logNo로 간주
                        if f'/{blog_id}/' in href:
                            parts = href.split(f'/{blog_id}/')[1].split('?')[0].split('/')
                            for part in parts:
                                if part.isdigit():
                                    lognos.add(part)
                    
                    logger.debug(f"Found {len(lognos)} unique logNos so far")
                    
                    # 다음 페이지가 없으면 중단
                    if not soup.select('a.page_next') and page_num > 1:
                        break
                        
                except Exception as e:
                    logger.error(f"Error in page {page_num}: {str(e)}")
            
            logger.debug(f"Found a total of {len(lognos)} unique posts to process")
            
            # 2. 각 포스트 페이지를 방문하여 콘텐츠 수집
            for logno in lognos:
                try:
                    # 직접 포스트 페이지 방문 (모바일 버전이 더 간단한 형식)
                    url = f"https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={logno}"
                    logger.debug(f"Visiting post: {url}")
                    
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=10000)
                    
                    # 제목과 내용을 다양한 선택자로 시도하여 추출
                    title = ""
                    title_selectors = [
                        '.se_title', '.tit_h3', '.se_textView .se_textarea', 
                        '.pcol1', 'h3.tit_view', '.se-title-text',
                        '.post_title', '.se-module-text'
                    ]
                    
                    for selector in title_selectors:
                        title_elem = page.query_selector(selector)
                        if title_elem:
                            title = title_elem.inner_text()
                            if title:
                                break
                    
                    # 콘텐츠 선택자도 다양하게 시도
                    content = ""
                    content_selectors = [
                        '.se_component_wrap', '#viewTypeSelector', '.post_ct', 
                        '.se-main-container', '.se_doc_viewer', 
                        '.view', '#postViewArea', '.post-view', 
                        '.post_content', '.post_body'
                    ]
                    
                    content_html = ""
                    for selector in content_selectors:
                        content_elem = page.query_selector(selector)
                        if content_elem:
                            content_html = content_elem.inner_html()
                            content = content_elem.inner_text()
                            if content:
                                break
                    
                    # 날짜 정보 찾기
                    date = ""
                    date_selectors = [
                        '.se_publishDate', '.date', '.se_date', 
                        '.post_date', '.date_post', '.se-module-date'
                    ]
                    
                    for selector in date_selectors:
                        date_elem = page.query_selector(selector)
                        if date_elem:
                            date = date_elem.inner_text()
                            if date:
                                break
                    
                    # 비공개 여부 확인 (일반적으로 네이버에선 로그인 상태에서만 비공개 글을 볼 수 있음)
                    is_private = False
                    if "비공개" in page.content() or "private" in page.content().lower():
                        is_private = True
                    
                    # 결과 추가
                    if title or content:
                        posts.append({
                            "logNo": logno,
                            "title": title,
                            "content": content,
                            "date": date,
                            "is_private": is_private,
                            "url": f"https://blog.naver.com/{blog_id}/{logno}"
                        })
                        logger.debug(f"Successfully extracted post: {title}")
                    else:
                        logger.warning(f"Failed to extract content for logNo: {logno}")
                    
                    # 서버에 너무 빠른 요청을 보내지 않기 위한 대기
                    time.sleep(0.5)
                    
                except Exception as e:
                    logger.error(f"Error processing post {logno}: {str(e)}")
            
            browser.close()
            
        if not posts:
            logger.warning("No posts were found or extracted")
        
        return posts
        
    except Exception as e:
        logger.error(f"Error in Playwright scraping: {str(e)}")
        raise Exception(f"Failed to scrape blog with Playwright: {str(e)}")