import logging
import re
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def extract_blog_id(blog_url):
    """Extract blog ID from Naver blog URL."""
    parsed_url = urlparse(blog_url)
    path_parts = parsed_url.path.strip('/').split('/')
    
    # Try different ways to extract the blog ID
    if parsed_url.netloc == 'blog.naver.com' or parsed_url.netloc == 'm.blog.naver.com':
        # Format: blog.naver.com/username
        if len(path_parts) > 0:
            return path_parts[0]
    
    # If no blog ID found, use a fallback approach with regex
    match = re.search(r'blog\.naver\.com/([^/]+)', blog_url)
    if match:
        return match.group(1)
    
    # If still no match, raise an error
    raise ValueError("Could not extract blog ID from the provided URL")

# 쿠키 기반 스크래퍼는 제거되었습니다.
# OAuth 기반 스크래퍼만 사용합니다. (oauth_scraper.py 참조)
