import time
import logging
import requests
from bs4 import BeautifulSoup
import re
import trafilatura  # Web scraping library for text extraction
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://blog.naver.com/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Cookie': cookie_value
        }
        
        # First, get the list of all posts
        post_list = []
        
        # Try different URL formats to find posts
        url_patterns = [
            # Classic URL pattern
            f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&from=postList",
            # Private URL pattern
            f"https://blog.naver.com/PostList.naver?blogId={blog_id}&categoryNo=0&directAccess=true&logCode=0",
            # Alternative URL patterns that might work
            f"https://blog.naver.com/{blog_id}",
            f"https://m.blog.naver.com/{blog_id}",
            f"https://blog.naver.com/PostTitleListAsync.naver?blogId={blog_id}&viewdate=&currentPage=1&categoryNo=0&parentCategoryNo=&countPerPage=30"
        ]
        
        for url in url_patterns:
            if "directAccess=true" in url:
                is_private = True
            else:
                is_private = False
                
            logger.debug(f"Trying URL pattern: {url} (private: {is_private})")
            
            try:
                posts = get_posts_from_url(url, headers, is_private)
                if posts:
                    logger.debug(f"Found {len(posts)} posts from URL: {url}")
                    post_list.extend(posts)
            except Exception as e:
                logger.error(f"Error with URL pattern {url}: {str(e)}")
        
        # Remove duplicate posts by URL
        seen_urls = set()
        unique_posts = []
        for post in post_list:
            if post['url'] not in seen_urls:
                seen_urls.add(post['url'])
                unique_posts.append(post)
        
        post_list = unique_posts
        logger.debug(f"Found a total of {len(post_list)} unique posts")
        
        # If no posts found by normal means, try a more direct approach
        if not post_list:
            logger.debug("No posts found with standard methods, trying direct exploration")
            try:
                # Try to get the main blog page and find post links directly
                main_blog_url = f"https://blog.naver.com/{blog_id}"
                response = requests.get(main_blog_url, headers=headers)
                soup = BeautifulSoup(response.text, 'lxml')
                
                # Look for any links that might point to posts
                post_links = soup.select('a[href*="PostView.naver"]')
                
                for link in post_links:
                    url = link.get('href', '')
                    if url and not url.startswith('http'):
                        url = f"https://blog.naver.com{url}"
                    
                    if url not in seen_urls:
                        seen_urls.add(url)
                        title = link.get_text(strip=True) or 'Untitled Post'
                        logger.debug(f"Found post via direct exploration: {title} at {url}")
                        post_list.append({
                            'title': title,
                            'url': url,
                            'date': 'Unknown date',
                            'is_private': False,  # Assume public since we found it
                            'content': ''
                        })
            except Exception as e:
                logger.error(f"Error with direct exploration: {str(e)}")
        
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
                
                if not content or len(content) < 50:  # Consider it failed if content too short
                    logger.debug("Trafilatura extraction failed or content too short, trying BeautifulSoup")
                    # Fallback to BeautifulSoup if trafilatura fails
                    soup = BeautifulSoup(response.text, 'lxml')
                    
                    # Try multiple content selectors
                    content_selectors = [
                        'div.se-main-container',          # Modern editor
                        'div#postViewArea',               # Classic editor
                        'div.post-view',                  # Alternative 
                        'div.se_component_wrap',          # Another editor style
                        'div.post_content',               # Common container
                        'div.entry-content',              # Another common container
                        'div.post_body',                  # Yet another container
                        'div#ct',                         # Mobile version sometimes
                        'div.se_paragraph',               # Individual paragraphs in SE editor
                        'div.blog_article'                # Another container
                    ]
                    
                    # Try each selector
                    extracted_text = ""
                    for selector in content_selectors:
                        content_elements = soup.select(selector)
                        if content_elements:
                            logger.debug(f"Found content using selector: {selector}")
                            for element in content_elements:
                                extracted_text += element.get_text(separator=' ', strip=True) + " "
                            break
                    
                    if extracted_text:
                        content = extracted_text.strip()
                    else:
                        # Worst case: just get the entire main content area text
                        main_content = soup.select_one('div#main_content') or soup.select_one('div#content')
                        if main_content:
                            content = main_content.get_text(separator=' ', strip=True)
                        else:
                            # Last resort: get text from body but remove headers/footers
                            body = soup.select_one('body')
                            if body:
                                # Remove navigation, headers, footers
                                for element in body.select('header, footer, nav, script, style'):
                                    element.decompose()
                                content = body.get_text(separator=' ', strip=True)
                            else:
                                content = "Content could not be extracted - no suitable container found"
                
                # Clean up the content a bit
                content = ' '.join(content.split())  # Remove extra whitespace
                post['content'] = content
                result_posts.append(post)
                
                # Be nice to the server
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error fetching post content: {str(e)}")
                # Add the post with error indication
                post['content'] = f"Error fetching content: {str(e)}"
                result_posts.append(post)
        
        if not result_posts:
            logger.error("No posts could be retrieved despite multiple attempts")
            raise ValueError("Failed to extract any posts from the blog. Please check the blog URL and cookie value.")
            
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
        
        # Log the URL we're fetching
        logger.debug(f"Fetching posts from URL: {list_url}")
        
        # Save the HTML content for debugging if needed
        html_content = response.text
        
        # Log the first 200 characters to check if we're getting valid HTML
        logger.debug(f"HTML response preview: {html_content[:200]}...")
        
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Try multiple selectors to find post elements - Naver has different layouts
        post_elements = []
        
        # New layout selectors
        selectors = [
            'div.post_item',                # Standard post items
            'tr.tbody_item',                # Table layout
            'li.item',                      # List layout
            'div.list_post_container li',   # Another common layout
            'div.post',                     # Sometimes used
            'div.blog-post',                # Sometimes used
            'div.se-post-thumbnail',        # SE editor posts
            'li.item_list',                 # Mobile or new layout
            'div.postlist_list_wrapper > div',  # Another layout
            'div.blog2_post_list > div'     # Another layout
        ]
        
        for selector in selectors:
            elements = soup.select(selector)
            if elements:
                logger.debug(f"Found {len(elements)} posts with selector: {selector}")
                post_elements.extend(elements)
        
        # Alternative approach: Look for links with post-specific patterns
        if not post_elements:
            logger.debug("Using fallback method to find posts by link patterns")
            post_links = soup.select('a[href*="/PostView.naver"]') or soup.select('a[href*="blogId="]')
            
            # Process found links
            processed_urls = set()
            for link in post_links:
                url = link.get('href', '')
                if url and '/PostView.naver' in url and url not in processed_urls:
                    processed_urls.add(url)
                    title = link.get_text(strip=True) or 'Untitled Post'
                    date = "Unknown date"
                    
                    # Try to find date near the link
                    date_element = link.find_next('span', class_='date') or link.find_next('td', class_='date')
                    if date_element:
                        date = date_element.get_text(strip=True)
                    
                    if not url.startswith('http'):
                        url = f"https://blog.naver.com{url}"
                    
                    posts.append({
                        'title': title,
                        'url': url,
                        'date': date,
                        'is_private': is_private,
                        'content': ''
                    })
            
            if posts:
                logger.debug(f"Found {len(posts)} posts using link pattern approach")
                return posts
        
        # Process post elements using multiple selectors for title and date
        for post_elem in post_elements:
            try:
                # Multiple selectors for finding title
                title_selectors = [
                    'a.title', 'a.pcol1', 'a.se-title', 'strong.title', 'strong.se-title', 
                    'a[href*="PostView.naver"]', 'div.title', 'span.title', 'h2.title', 'h3.title'
                ]
                
                title_elem = None
                for selector in title_selectors:
                    title_elem = post_elem.select_one(selector)
                    if title_elem:
                        break
                
                if not title_elem:
                    # If no specific title element found, check for any link in the post element
                    links = post_elem.select('a')
                    for link in links:
                        href = link.get('href', '')
                        if href and '/PostView.naver' in href:
                            title_elem = link
                            break
                
                if not title_elem:
                    logger.debug(f"Could not find title element in post: {post_elem}")
                    continue
                
                title = title_elem.get_text(strip=True)
                post_url = title_elem.get('href', '')
                
                if not post_url:
                    # Try to find the URL from onclick attribute or other sources
                    onclick = title_elem.get('onclick', '')
                    if 'location.href' in onclick:
                        post_url = onclick.split("location.href='")[1].split("'")[0]
                    else:
                        # Look for nearby links that might be the post URL
                        nearby_link = post_elem.select_one('a[href*="PostView.naver"]')
                        if nearby_link:
                            post_url = nearby_link.get('href', '')
                
                if not post_url:
                    logger.debug(f"Could not extract URL for post with title: {title}")
                    continue
                
                if not post_url.startswith('http'):
                    post_url = f"https://blog.naver.com{post_url}"
                
                # Multiple selectors for finding date
                date_selectors = [
                    'span.date', 'td.date', 'div.date', 'p.date', 
                    'span.se-date', 'div.se-date', 'time', 'span.time'
                ]
                
                date = "Unknown date"
                for selector in date_selectors:
                    date_elem = post_elem.select_one(selector)
                    if date_elem:
                        date = date_elem.get_text(strip=True)
                        break
                
                posts.append({
                    'title': title,
                    'url': post_url,
                    'date': date,
                    'is_private': is_private,
                    'content': ''  # Will be filled later
                })
                
                logger.debug(f"Found post: '{title}' at URL: {post_url}")
                
            except Exception as e:
                logger.error(f"Error processing post element: {str(e)}")
        
        # Try to find pagination links for next page
        next_page = None
        next_selectors = [
            'a.paginate_next', 'a.next', 'a.nextprev', 'a[rel="next"]',
            'a.pg_next', 'a.pagination-next', 'a.next_page'
        ]
        
        for selector in next_selectors:
            next_page = soup.select_one(selector)
            if next_page and 'href' in next_page.attrs:
                break
        
        if next_page and 'href' in next_page.attrs:
            next_url = next_page['href']
            if not next_url.startswith('http'):
                next_url = f"https://blog.naver.com{next_url}"
            
            logger.debug(f"Found next page: {next_url}")
            
            # Be nice to the server
            time.sleep(1)
            
            # Recursively get posts from next page
            next_posts = get_posts_from_url(next_url, headers, is_private)
            posts.extend(next_posts)
        
        logger.debug(f"Returning {len(posts)} posts from URL: {list_url}")
        return posts
        
    except Exception as e:
        logger.error(f"Error getting posts from URL {list_url}: {str(e)}")
        return []
