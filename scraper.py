import time
import logging
import requests
import json
from bs4 import BeautifulSoup
import re
import trafilatura  # Web scraping library for text extraction
from urllib.parse import urlparse, parse_qs, quote

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

def scrape_naver_blog(blog_url, cookie_value):
    """
    Scrape posts from a Naver blog using the API endpoints.
    
    Args:
        blog_url: URL of the Naver blog
        cookie_value: Cookie value for authentication
        
    Returns:
        List of dictionaries containing post information
    """
    try:
        blog_id = extract_blog_id(blog_url)
        logger.debug(f"Extracted blog ID: {blog_id}")
        
        # Set up headers with the cookie
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': f'https://blog.naver.com/{blog_id}',
            'Origin': 'https://blog.naver.com',
            'Connection': 'keep-alive',
            'X-Requested-With': 'XMLHttpRequest',
            'Cookie': cookie_value
        }
        
        # Use the modern API endpoints that Naver uses internally
        api_list_posts = f"https://blog.naver.com/api/blogs/{blog_id}/posts/list?categoryNo=0&itemCount=30"
        api_all_categories = f"https://blog.naver.com/api/blogs/{blog_id}/categories"
        
        # First, try to get all categories to extract all posts
        categories = []
        try:
            response = requests.get(api_all_categories, headers=headers)
            if response.status_code == 200:
                categories_data = response.json()
                if 'categories' in categories_data:
                    for category in categories_data['categories']:
                        if 'categoryNo' in category:
                            categories.append(category['categoryNo'])
            logger.debug(f"Found {len(categories)} categories")
        except Exception as e:
            logger.error(f"Error getting categories: {str(e)}")
            # Continue with just the default category
            categories = [0]
        
        # If no categories found, use default
        if not categories:
            categories = [0]
        
        # Get posts from each category
        post_list = []
        
        for category_no in categories:
            try:
                # Try using the modern API
                api_url = f"https://blog.naver.com/api/blogs/{blog_id}/posts/list?categoryNo={category_no}&itemCount=30"
                logger.debug(f"Fetching posts from API: {api_url}")
                
                response = requests.get(api_url, headers=headers)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if 'result' in data and 'items' in data['result']:
                            items = data['result']['items']
                            logger.debug(f"Found {len(items)} posts in category {category_no}")
                            
                            for item in items:
                                title = item.get('titleWithInspectMessage', item.get('title', 'Untitled'))
                                log_no = item.get('logNo', '')
                                if not log_no:
                                    continue
                                
                                # Create post URL
                                post_url = f"https://blog.naver.com/{blog_id}/{log_no}"
                                
                                # Get date info
                                date = item.get('addDate', '')
                                if not date:
                                    date = item.get('createdAt', 'Unknown date')
                                
                                # Check if post is private
                                is_private = item.get('openType', '') != 'PUBLIC'
                                
                                post_list.append({
                                    'title': title,
                                    'url': post_url,
                                    'date': date,
                                    'is_private': is_private,
                                    'content': '',  # Will be filled later
                                    'log_no': log_no  # Save this for fetching content
                                })
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON response from API")
                        
                # If API approach doesn't work, try the traditional approach
                if not post_list and category_no == 0:
                    # Try the PostTitleListAsync endpoint
                    async_url = f"https://blog.naver.com/PostTitleListAsync.naver?blogId={blog_id}&categoryNo=0&currentPage=1&countPerPage=30"
                    logger.debug(f"Trying backup endpoint: {async_url}")
                    
                    response = requests.get(async_url, headers=headers)
                    try:
                        data = response.json()
                        if 'postList' in data:
                            items = data['postList']
                            logger.debug(f"Found {len(items)} posts from backup endpoint")
                            
                            for item in items:
                                title = item.get('title', 'Untitled')
                                log_no = item.get('logNo', '')
                                if not log_no:
                                    continue
                                
                                # Decode title if it's URL encoded
                                try:
                                    title = title.encode('latin1').decode('utf-8')
                                except:
                                    pass
                                
                                post_url = f"https://blog.naver.com/{blog_id}/{log_no}"
                                date = item.get('addDate', 'Unknown date')
                                is_private = 'private' in item.get('openType', '').lower()
                                
                                post_list.append({
                                    'title': title,
                                    'url': post_url,
                                    'date': date,
                                    'is_private': is_private,
                                    'content': '',
                                    'log_no': log_no
                                })
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON from backup endpoint")
                
            except Exception as e:
                logger.error(f"Error fetching posts from category {category_no}: {str(e)}")
        
        # Check if we found any posts
        if not post_list:
            # Try the direct API for fetching content page by page
            logger.debug("No posts found with API methods, trying direct pagination")
            
            # Try different pages
            for page in range(1, 5):  # Try up to 5 pages
                try:
                    page_url = f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&currentPage={page}"
                    logger.debug(f"Trying page: {page_url}")
                    
                    response = requests.get(page_url, headers=headers)
                    soup = BeautifulSoup(response.text, 'lxml')
                    
                    # Look for post links
                    post_links = soup.select('a[href*="PostView.naver"]') or soup.select('a[href*="/'+blog_id+'/"]')
                    
                    for link in post_links:
                        href = link.get('href', '')
                        if not href or href.startswith('#'):
                            continue
                        
                        # Extract log_no from href if possible
                        log_no = None
                        if '/PostView.naver?' in href:
                            params = parse_qs(urlparse(href).query)
                            if 'logNo' in params:
                                log_no = params['logNo'][0]
                        else:
                            match = re.search(r'/([0-9]+)(?:\?|$)', href)
                            if match:
                                log_no = match.group(1)
                        
                        if not log_no:
                            continue
                        
                        # Skip duplicates
                        post_url = f"https://blog.naver.com/{blog_id}/{log_no}"
                        if any(p.get('url') == post_url for p in post_list):
                            continue
                        
                        title = link.get_text(strip=True) or 'Untitled'
                        
                        # Try to find date near the link
                        date_elem = None
                        parent = link.parent
                        for _ in range(3):  # Look up to 3 levels up
                            if parent:
                                date_elem = parent.select_one('.date, .post_date, time, .se_date')
                                if date_elem:
                                    break
                                parent = parent.parent
                        
                        date = date_elem.get_text(strip=True) if date_elem else 'Unknown date'
                        
                        post_list.append({
                            'title': title,
                            'url': post_url,
                            'date': date,
                            'is_private': False,  # Can't determine from here
                            'content': '',
                            'log_no': log_no
                        })
                    
                    # If we found posts, break the loop
                    if post_list:
                        break
                    
                except Exception as e:
                    logger.error(f"Error in pagination attempt for page {page}: {str(e)}")
        
        logger.debug(f"Found a total of {len(post_list)} posts")
        
        # If still no posts, fail gracefully
        if not post_list:
            logger.error("Could not find any posts with multiple methods")
            raise ValueError("Failed to extract any posts from the blog. Please check the blog URL and cookie value.")
        
        # Process each post to get the full content
        result_posts = []
        for post in post_list:
            post_url = post['url']
            log_no = post.get('log_no', '')
            logger.debug(f"Fetching content for post: {post_url}")
            
            try:
                # Try to get the content via the mobile API which is more reliable
                api_content_url = f"https://m.blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}&mobileBlogCommentInputBox=false"
                
                # Get the post content
                response = requests.get(api_content_url, headers=headers)
                response.raise_for_status()
                
                # Extract the post content using trafilatura for better text extraction
                content = trafilatura.extract(response.text)
                
                if not content or len(content) < 50:  # Consider it failed if content too short
                    logger.debug("Trafilatura extraction failed or content too short, trying API")
                    
                    # Try the direct API
                    api_post_url = f"https://blog.naver.com/api/blogs/{blog_id}/posts/{log_no}"
                    api_response = requests.get(api_post_url, headers=headers)
                    
                    if api_response.status_code == 200:
                        try:
                            data = api_response.json()
                            if 'result' in data and 'contentHtml' in data['result']:
                                html_content = data['result']['contentHtml']
                                soup = BeautifulSoup(html_content, 'lxml')
                                content = soup.get_text(separator=' ', strip=True)
                            else:
                                # Try other fields
                                content_fields = ['contentHtml', 'postContent', 'content']
                                for field in content_fields:
                                    if field in data.get('result', {}):
                                        html_content = data['result'][field]
                                        soup = BeautifulSoup(html_content, 'lxml')
                                        content = soup.get_text(separator=' ', strip=True)
                                        if content:
                                            break
                        except (json.JSONDecodeError, KeyError):
                            logger.error("Failed to parse API response for content")
                    
                    # If API approach failed, fall back to basic scraping
                    if not content or len(content) < 50:
                        logger.debug("API approach failed, falling back to scraping")
                        soup = BeautifulSoup(response.text, 'lxml')
                        
                        # Try multiple content selectors (mobile version)
                        content_selectors = [
                            'div.post_ct',                   # Mobile post content
                            'div.se-main-container',         # New editor
                            'div#postViewArea',              # Old editor
                            'div.post_content',              # Generic content
                            'div.se_component_wrap',         # Component wrapper
                            'div.post_body',                 # Post body
                            'div.post-content',              # Generic post content
                            'article'                        # Generic article tag
                        ]
                        
                        for selector in content_selectors:
                            content_elem = soup.select_one(selector)
                            if content_elem:
                                content = content_elem.get_text(separator=' ', strip=True)
                                logger.debug(f"Found content with selector: {selector}")
                                break
                
                # Clean up the content a bit
                if content:
                    content = ' '.join(content.split())  # Remove extra whitespace
                else:
                    content = "Content could not be extracted"
                
                post['content'] = content
                # Remove log_no as it's no longer needed
                if 'log_no' in post:
                    del post['log_no']
                
                result_posts.append(post)
                
                # Be nice to the server
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error fetching post content: {str(e)}")
                post['content'] = f"Error fetching content: {str(e)}"
                if 'log_no' in post:
                    del post['log_no']
                result_posts.append(post)
        
        return result_posts
        
    except Exception as e:
        logger.error(f"Error scraping blog: {str(e)}")
        raise

# 기존 get_posts_from_url 함수는 제거되었습니다. 
# 모든 로직이 새로운 scrape_naver_blog 함수로 통합되었습니다.
