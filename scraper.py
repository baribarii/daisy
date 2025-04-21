import time
import logging
import requests
from bs4 import BeautifulSoup
import re
import trafilatura
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

def extract_blog_id(blog_url):
    """Extract blog ID from Naver blog URL."""
    parsed_url = urlparse(blog_url)
    path_parts = parsed_url.path.strip('/').split('/')
    
    # Try different ways to extract the blog ID
    if parsed_url.netloc == 'blog.naver.com':
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
    Scrape posts from a Naver blog.
    
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cookie': cookie_value
        }
        
        # First, get the list of all posts
        post_list = []
        
        # Define the URLs for public and private posts
        public_list_url = f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&from=postList"
        private_list_url = f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&directAccess=true&logCode=0"
        
        # Get public posts
        logger.debug("Fetching public posts...")
        posts = get_posts_from_url(public_list_url, headers, False)
        post_list.extend(posts)
        
        # Get private posts
        logger.debug("Fetching private posts...")
        posts = get_posts_from_url(private_list_url, headers, True)
        post_list.extend(posts)
        
        logger.debug(f"Found a total of {len(post_list)} posts")
        
        # Process each post to get the full content
        result_posts = []
        for post in post_list:
            post_url = post['url']
            logger.debug(f"Fetching content for post: {post_url}")
            
            try:
                # Get the post content
                response = requests.get(post_url, headers=headers)
                response.raise_for_status()
                
                # Extract the post content using trafilatura for better text extraction
                content = trafilatura.extract(response.text)
                
                if not content:
                    # Fallback to BeautifulSoup if trafilatura fails
                    soup = BeautifulSoup(response.text, 'html.parser')
                    content_div = soup.select_one('div.se-main-container')
                    if content_div:
                        content = content_div.get_text(strip=True)
                    else:
                        # Try alternative content container
                        content_div = soup.select_one('div#postViewArea') or soup.select_one('div.post-view')
                        if content_div:
                            content = content_div.get_text(strip=True)
                        else:
                            content = "Content could not be extracted"
                
                post['content'] = content
                result_posts.append(post)
                
                # Be nice to the server
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error fetching post content: {str(e)}")
                # Add the post with error indication
                post['content'] = f"Error fetching content: {str(e)}"
                result_posts.append(post)
        
        return result_posts
        
    except Exception as e:
        logger.error(f"Error scraping blog: {str(e)}")
        raise

def get_posts_from_url(list_url, headers, is_private):
    """Extract post links and basic info from the post list page."""
    try:
        posts = []
        
        # Get the list page
        response = requests.get(list_url, headers=headers)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find post elements
        post_elements = soup.select('div.post_item') or soup.select('tr.tbody_item')
        
        for post_elem in post_elements:
            try:
                # Extract post title and URL
                title_elem = post_elem.select_one('a.title') or post_elem.select_one('a.pcol1')
                
                if not title_elem:
                    continue
                
                title = title_elem.get_text(strip=True)
                post_url = title_elem['href']
                
                if not post_url.startswith('http'):
                    post_url = f"https://blog.naver.com{post_url}"
                
                # Extract date if available
                date_elem = post_elem.select_one('span.date') or post_elem.select_one('td.date')
                date = date_elem.get_text(strip=True) if date_elem else "Unknown date"
                
                posts.append({
                    'title': title,
                    'url': post_url,
                    'date': date,
                    'is_private': is_private,
                    'content': ''  # Will be filled later
                })
                
            except Exception as e:
                logger.error(f"Error processing post element: {str(e)}")
        
        # Try to find "Next" button for pagination
        next_page = soup.select_one('a.paginate_next')
        if next_page and 'href' in next_page.attrs:
            next_url = f"https://blog.naver.com{next_page['href']}"
            # Be nice to the server
            time.sleep(1)
            # Recursively get posts from next page
            next_posts = get_posts_from_url(next_url, headers, is_private)
            posts.extend(next_posts)
        
        return posts
        
    except Exception as e:
        logger.error(f"Error getting posts from URL {list_url}: {str(e)}")
        return []
