import requests
from bs4 import BeautifulSoup
import logging
import time
import re
import json
from urllib.parse import urlparse, quote

logger = logging.getLogger(__name__)

class NaverBlogScraper:
    def __init__(self, blog_id, cookie_str):
        self.blog_id = blog_id
        self.cookie_str = cookie_str
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': f'https://blog.naver.com/{blog_id}',
            'Connection': 'keep-alive',
            'Cookie': cookie_str,
            'Upgrade-Insecure-Requests': '1',
        }
        
    def scrape_blog(self):
        """
        네이버 블로그를 여러 방법을 사용하여 스크랩합니다.
        """
        logger.debug(f"Starting to scrape blog: {self.blog_id}")
        
        # 여러 방법을 시도하고 하나라도 성공하면 반환합니다
        # 1. API JSON 방식 시도
        posts = self._try_api_method()
        if posts:
            logger.debug(f"API method successful, found {len(posts)} posts")
            return posts
            
        # 2. 이전 JSON 방식 시도
        posts = self._try_old_json_method()
        if posts:
            logger.debug(f"Old JSON method successful, found {len(posts)} posts")
            return posts
        
        # 3. 직접 페이지네이션하며 HTML 파싱 시도
        posts = self._try_html_parsing()
        if posts:
            logger.debug(f"HTML parsing successful, found {len(posts)} posts")
            return posts
        
        # 4. 모바일 버전 시도
        posts = self._try_mobile_version()
        if posts:
            logger.debug(f"Mobile version successful, found {len(posts)} posts")
            return posts
        
        logger.error("All scraping methods failed")
        return []
    
    def _make_request(self, url):
        """
        안전하게 요청을 보내는 헬퍼 함수입니다.
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response
            else:
                logger.warning(f"Request failed with status code {response.status_code}: {url}")
                return None
        except Exception as e:
            logger.error(f"Request error for {url}: {str(e)}")
            return None
    
    def _try_api_method(self):
        """
        네이버 블로그 API를 사용하여 포스트 목록을 가져옵니다.
        """
        posts = []
        
        # 1. 모든 카테고리 가져오기
        api_categories = f"https://blog.naver.com/api/blogs/{self.blog_id}/categories"
        response = self._make_request(api_categories)
        
        categories = [0]  # 기본 카테고리
        if response:
            try:
                data = response.json()
                if 'categories' in data:
                    categories = [cat.get('categoryNo', 0) for cat in data['categories']]
                    if not categories:
                        categories = [0]
            except Exception as e:
                logger.error(f"Error parsing categories: {str(e)}")
        
        # 2. 각 카테고리에서 포스트 가져오기
        for category in categories:
            for page in range(1, 5):  # 최대 5페이지까지 시도
                api_url = f"https://blog.naver.com/api/blogs/{self.blog_id}/posts/list?categoryNo={category}&pageNo={page}&pageSize=30"
                response = self._make_request(api_url)
                
                if not response:
                    continue
                
                try:
                    data = response.json()
                    if 'result' in data and 'items' in data['result']:
                        items = data['result']['items']
                        
                        for item in items:
                            logno = item.get('logNo')
                            title = item.get('titleWithInspectMessage', item.get('title', 'Untitled'))
                            
                            # 포스트 내용 가져오기
                            post_content = self._get_post_content(logno)
                            
                            # 날짜 추출
                            date = item.get('addDate', '')
                            if not date:
                                date = item.get('openDate', '')
                            
                            # 비공개 여부 확인
                            is_private = not item.get('openType', True)
                            
                            posts.append({
                                'logNo': logno,
                                'title': title,
                                'content': post_content,
                                'date': date,
                                'is_private': is_private,
                                'url': f"https://blog.naver.com/{self.blog_id}/{logno}"
                            })
                        
                        # 더 이상 포스트가 없으면 중단
                        if len(items) < 30:
                            break
                            
                except Exception as e:
                    logger.error(f"Error parsing API response: {str(e)}")
        
        return posts
    
    def _try_old_json_method(self):
        """
        이전 버전의 JSON 방식으로 포스트 목록을 가져옵니다.
        """
        posts = []
        
        for page in range(1, 5):  # 최대 5페이지까지 시도
            url = f"https://blog.naver.com/PostTitleListAsync.naver?blogId={self.blog_id}&currentPage={page}&categoryNo=0&countPerPage=30"
            response = self._make_request(url)
            
            if not response:
                continue
            
            try:
                html = response.text
                # JSON 직접 추출 (HTML로 포장된 JSON)
                json_text = re.search(r'var postList = (.*?);\s*var', html, re.DOTALL)
                if json_text:
                    json_data = json.loads(json_text.group(1))
                    
                    for post in json_data:
                        logno = post.get('logNo')
                        title = post.get('title', 'Untitled')
                        
                        # 포스트 내용 가져오기
                        post_content = self._get_post_content(logno)
                        
                        # 날짜 추출
                        date = post.get('addDate', '')
                        
                        # 비공개 여부 확인
                        is_private = post.get('openType') == 'F'
                        
                        posts.append({
                            'logNo': logno,
                            'title': title,
                            'content': post_content,
                            'date': date,
                            'is_private': is_private,
                            'url': f"https://blog.naver.com/{self.blog_id}/{logno}"
                        })
                    
                    # 더 이상 포스트가 없으면 중단
                    if len(json_data) < 30:
                        break
            
            except Exception as e:
                logger.error(f"Error parsing old JSON response: {str(e)}")
        
        return posts
    
    def _try_html_parsing(self):
        """
        HTML 페이지를 직접 파싱하여 포스트 목록을 가져옵니다.
        """
        posts = []
        lognos = set()
        
        for page in range(1, 5):  # 최대 5페이지까지 시도
            url = f"https://blog.naver.com/PostList.naver?blogId={self.blog_id}&categoryNo=0&currentPage={page}"
            response = self._make_request(url)
            
            if not response:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 패턴 1: logNo 파라미터가 있는 링크 찾기
            for link in soup.select('a[href*="logNo="]'):
                href = link.get('href', '')
                if 'logNo=' in href:
                    log_no = href.split('logNo=')[1].split('&')[0]
                    lognos.add(log_no)
            
            # 패턴 2: 현대 네이버 블로그 형식 (/blogId/logNo)
            for link in soup.select(f'a[href*="/{self.blog_id}/"]'):
                href = link.get('href', '')
                if f'/{self.blog_id}/' in href:
                    parts = href.split(f'/{self.blog_id}/')[1].split('?')[0].split('/')
                    for part in parts:
                        if part.isdigit():
                            lognos.add(part)
            
            # 다음 페이지가 없으면 중단
            if not soup.select('.page_next') and page > 1:
                break
        
        # 찾은 모든 포스트의 내용 가져오기
        for logno in lognos:
            # 포스트 제목과 내용 가져오기
            title, content, date, is_private = self._get_post_details(logno)
            
            posts.append({
                'logNo': logno,
                'title': title,
                'content': content,
                'date': date,
                'is_private': is_private,
                'url': f"https://blog.naver.com/{self.blog_id}/{logno}"
            })
            
            # 네이버 서버에 부담을 주지 않기 위한 지연
            time.sleep(0.5)
        
        return posts
    
    def _try_mobile_version(self):
        """
        모바일 버전의 블로그를 파싱하여 포스트 목록을 가져옵니다.
        """
        posts = []
        lognos = set()
        
        for page in range(1, 5):  # 최대 5페이지까지 시도
            url = f"https://m.blog.naver.com/{self.blog_id}?categoryNo=0&listStyle=post&page={page}"
            response = self._make_request(url)
            
            if not response:
                continue
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 모바일 포스트 링크 패턴
            for link in soup.select('.item_post a, .post_content a'):
                href = link.get('href', '')
                if 'logNo=' in href:
                    log_no = href.split('logNo=')[1].split('&')[0]
                    lognos.add(log_no)
            
            # 다음 페이지가 없으면 중단
            if not soup.select('.page_next, .btn_next') and page > 1:
                break
        
        # 찾은 모든 포스트의 내용 가져오기
        for logno in lognos:
            # 모바일 버전에서 포스트 제목과 내용 가져오기
            title, content, date, is_private = self._get_mobile_post_details(logno)
            
            posts.append({
                'logNo': logno,
                'title': title,
                'content': content,
                'date': date,
                'is_private': is_private,
                'url': f"https://blog.naver.com/{self.blog_id}/{logno}"
            })
            
            # 네이버 서버에 부담을 주지 않기 위한 지연
            time.sleep(0.5)
        
        return posts
    
    def _get_post_content(self, logno):
        """
        포스트의 내용을 가져옵니다.
        """
        try:
            # 1. API 시도
            api_url = f"https://blog.naver.com/api/blogs/{self.blog_id}/posts/{logno}"
            response = self._make_request(api_url)
            
            if response:
                data = response.json()
                if 'result' in data and 'contentHtml' in data['result']:
                    html_content = data['result']['contentHtml']
                    soup = BeautifulSoup(html_content, 'html.parser')
                    return soup.get_text(separator='\n', strip=True)
            
            # 2. 일반 포스트 페이지 시도
            return self._get_post_details(logno)[1]
            
        except Exception as e:
            logger.error(f"Error getting post content for {logno}: {str(e)}")
            return ""
    
    def _get_post_details(self, logno):
        """
        포스트의 제목, 내용, 날짜, 비공개 여부를 가져옵니다.
        """
        url = f"https://blog.naver.com/PostView.naver?blogId={self.blog_id}&logNo={logno}"
        response = self._make_request(url)
        
        title = ""
        content = ""
        date = ""
        is_private = False
        
        if response:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 제목 추출 (다양한 레이아웃 대응)
            title_selectors = [
                '.se_title', '.tit_h3', '.se_textView .se_textarea', 
                '.pcol1', 'h3.tit_view', '.se-title-text',
                '.post_title', '.se-module-text'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title:
                        break
            
            # 내용 추출 (다양한 레이아웃 대응)
            content_selectors = [
                '.se_component_wrap', '#viewTypeSelector', '.post_ct', 
                '.se-main-container', '.se_doc_viewer', 
                '.view', '#postViewArea', '.post-view', 
                '.post_content', '.post_body'
            ]
            
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text(separator='\n', strip=True)
                    if content:
                        break
            
            # 날짜 추출
            date_selectors = [
                '.se_publishDate', '.date', '.se_date', 
                '.post_date', '.date_post', '.se-module-date'
            ]
            
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date = date_elem.get_text(strip=True)
                    if date:
                        break
            
            # 비공개 여부 확인
            is_private = "비공개" in soup.get_text() or "private" in soup.get_text().lower()
            
        return title, content, date, is_private
    
    def _get_mobile_post_details(self, logno):
        """
        모바일 버전에서 포스트의 제목, 내용, 날짜, 비공개 여부를 가져옵니다.
        """
        url = f"https://m.blog.naver.com/PostView.naver?blogId={self.blog_id}&logNo={logno}"
        response = self._make_request(url)
        
        title = ""
        content = ""
        date = ""
        is_private = False
        
        if response:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 제목 추출 (모바일 레이아웃)
            title_selectors = [
                '.se_title', '.tit_h3', '.tit_view', 'h2.tit'
            ]
            
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title:
                        break
            
            # 내용 추출 (모바일 레이아웃)
            content_selectors = [
                '.se_doc_viewer', '.view', '.post_ct', 
                '.post_view', '.post_content', '.se-main-container'
            ]
            
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text(separator='\n', strip=True)
                    if content:
                        break
            
            # 날짜 추출
            date_selectors = [
                '.se_publishDate', '.date', '.se_date', 
                '.post_date', '.date_post', '.se-module-date'
            ]
            
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date = date_elem.get_text(strip=True)
                    if date:
                        break
            
            # 비공개 여부 확인
            is_private = "비공개" in soup.get_text() or "private" in soup.get_text().lower()
            
        return title, content, date, is_private


def scrape_naver_blog_with_fallback(blog_url, cookie_value):
    """
    네이버 블로그를 스크래핑하는 대체 방법을 제공합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        cookie_value (str): 쿠키 값
        
    Returns:
        list: 포스트 목록
    """
    try:
        # 블로그 ID 추출
        from scraper import extract_blog_id
        blog_id = extract_blog_id(blog_url)
        
        if not blog_id:
            raise ValueError("Failed to extract blog ID from URL")
            
        # NaverBlogScraper 클래스를 사용하여 스크래핑
        scraper = NaverBlogScraper(blog_id, cookie_value)
        posts = scraper.scrape_blog()
        
        if not posts:
            raise ValueError("Failed to extract any posts from the blog")
            
        logger.debug(f"Successfully scraped {len(posts)} posts from blog {blog_id}")
        return posts
        
    except Exception as e:
        logger.error(f"Error in fallback scraper: {str(e)}")
        raise Exception(f"Failed to extract any posts from the blog. Please check the blog URL and cookie value.")