import logging
from oauth_scraper import scrape_blog_with_oauth
from db_utils import save_multiple_posts, list_all_posts, get_total_post_count

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def scrape_and_save_posts(blog_url, access_token):
    """
    네이버 블로그 글을 스크래핑한 후 Replit DB에 저장합니다.
    
    Args:
        blog_url (str): 네이버 블로그 URL
        access_token (str): 네이버 OAuth 액세스 토큰
        
    Returns:
        tuple: (성공한 포스트 수, 이미 DB에 있었던 포스트 수)
    """
    try:
        logger.info(f"블로그 {blog_url} 스크래핑 시작")
        
        # OAuth 토큰을 사용하여 블로그 스크래핑
        posts = scrape_blog_with_oauth(blog_url, access_token)
        
        if not posts:
            logger.warning("스크래핑된 포스트가 없습니다.")
            return (0, 0)
            
        logger.info(f"총 {len(posts)}개의 포스트를 스크래핑했습니다. DB에 저장합니다.")
        
        # 스크래핑한 포스트 저장
        success_count, fail_count = save_multiple_posts(posts)
        
        # 현재 저장된 총 포스트 수
        total_posts = get_total_post_count()
        
        logger.info(f"DB 저장 결과: 성공 {success_count}개, 실패 {fail_count}개")
        logger.info(f"현재 DB에 저장된 총 포스트 수: {total_posts}개")
        
        return (success_count, len(posts) - success_count)
        
    except Exception as e:
        logger.error(f"스크래핑 및 저장 중 오류 발생: {str(e)}")
        return (0, 0)

# 실행 예제 (실제로 실행하려면 아래 주석을 해제하고 값을 입력하세요)
if __name__ == "__main__":
    # 실행하려면 아래 값을 입력하세요
    # BLOG_URL = "https://blog.naver.com/yourblogid"
    # ACCESS_TOKEN = "your_oauth_access_token"
    # scrape_and_save_posts(BLOG_URL, ACCESS_TOKEN)
    
    # 저장된 모든 포스트 ID 출력
    # all_post_ids = list_all_posts()
    # print(f"저장된 포스트 ID 목록 ({len(all_post_ids)}개):")
    # for post_id in all_post_ids:
    #     print(f"- {post_id}")
    pass