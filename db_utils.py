from replit import db
import json
import logging

# 로깅 설정
logger = logging.getLogger(__name__)

def save_blog_post(post_id, title, content, date, is_private=False, extra_data=None):
    """
    네이버 블로그 포스트를 Replit DB에 저장합니다.
    
    Args:
        post_id (str): 네이버 블로그 포스트 ID (logNo)
        title (str): 포스트 제목
        content (str): 포스트 본문 텍스트
        date (str): 포스트 작성일
        is_private (bool, optional): 비공개 포스트 여부
        extra_data (dict, optional): 추가 메타데이터
        
    Returns:
        bool: 저장 성공 여부
    """
    try:
        # 키 이름 생성 - 'post_' 접두사 추가
        key = f"post_{post_id}"
        
        # 이미 저장된 포스트인지 확인
        if key in db.keys():
            logger.info(f"포스트 ID {post_id}는 이미 저장되어 있습니다. 업데이트합니다.")
        
        # 저장할 데이터 구성
        post_data = {
            "id": post_id,
            "title": title,
            "content": content,
            "date": date,
            "is_private": is_private
        }
        
        # 추가 데이터가 있으면 병합
        if extra_data and isinstance(extra_data, dict):
            post_data.update(extra_data)
        
        # DB에 저장
        db[key] = json.dumps(post_data)
        logger.debug(f"포스트 ID {post_id} 저장 완료")
        
        return True
        
    except Exception as e:
        logger.error(f"포스트 ID {post_id} 저장 중 오류 발생: {str(e)}")
        return False

def get_blog_post(post_id):
    """
    저장된 블로그 포스트를 ID로 조회합니다.
    
    Args:
        post_id (str): 네이버 블로그 포스트 ID
        
    Returns:
        dict or None: 저장된 포스트 데이터 또는 None (없는 경우)
    """
    try:
        key = f"post_{post_id}"
        
        if key not in db.keys():
            logger.warning(f"포스트 ID {post_id}가 DB에 존재하지 않습니다.")
            return None
            
        post_data = json.loads(db[key])
        return post_data
        
    except Exception as e:
        logger.error(f"포스트 ID {post_id} 조회 중 오류 발생: {str(e)}")
        return None

def list_all_posts():
    """
    저장된 모든 블로그 포스트 ID 목록을 반환합니다.
    
    Returns:
        list: 저장된 포스트 ID 목록
    """
    try:
        # 'post_' 접두사가 있는 키만 필터링
        post_keys = [key for key in db.keys() if key.startswith("post_")]
        
        # 접두사 제거하여 실제 포스트 ID만 반환
        post_ids = [key.replace("post_", "") for key in post_keys]
        
        return post_ids
        
    except Exception as e:
        logger.error(f"포스트 목록 조회 중 오류 발생: {str(e)}")
        return []

def delete_blog_post(post_id):
    """
    저장된 블로그 포스트를 삭제합니다.
    
    Args:
        post_id (str): 삭제할 네이버 블로그 포스트 ID
        
    Returns:
        bool: 삭제 성공 여부
    """
    try:
        key = f"post_{post_id}"
        
        if key not in db.keys():
            logger.warning(f"포스트 ID {post_id}가 DB에 존재하지 않아 삭제할 수 없습니다.")
            return False
            
        del db[key]
        logger.debug(f"포스트 ID {post_id} 삭제 완료")
        return True
        
    except Exception as e:
        logger.error(f"포스트 ID {post_id} 삭제 중 오류 발생: {str(e)}")
        return False

def save_multiple_posts(posts):
    """
    여러 블로그 포스트를 한 번에 저장합니다.
    
    Args:
        posts (list): 포스트 데이터 목록. 각 항목은 딕셔너리 형태로:
                      {'id': str, 'title': str, 'content': str, 'date': str, 
                       'is_private': bool, ...기타 필드}
    
    Returns:
        tuple: (성공 개수, 실패 개수)
    """
    success_count = 0
    fail_count = 0
    
    for post in posts:
        post_id = post.get('id') or post.get('logNo')
        
        if not post_id:
            logger.error("유효하지 않은 포스트 데이터: 'id' 또는 'logNo' 필드가 없습니다.")
            fail_count += 1
            continue
            
        # 기본 필드 추출
        title = post.get('title', '')
        content = post.get('content', '')
        date = post.get('date', '')
        is_private = post.get('is_private', False)
        
        # 기본 필드를 제외한 추가 데이터
        extra_data = {k: v for k, v in post.items() 
                     if k not in ['id', 'logNo', 'title', 'content', 'date', 'is_private']}
        
        if save_blog_post(post_id, title, content, date, is_private, extra_data):
            success_count += 1
        else:
            fail_count += 1
    
    logger.info(f"총 {success_count}개 포스트 저장 성공, {fail_count}개 실패")
    return (success_count, fail_count)

def get_total_post_count():
    """
    저장된 총 포스트 수를 반환합니다.
    
    Returns:
        int: 저장된 포스트의 총 개수
    """
    try:
        post_keys = [key for key in db.keys() if key.startswith("post_")]
        return len(post_keys)
    except Exception as e:
        logger.error(f"포스트 개수 조회 중 오류 발생: {str(e)}")
        return 0

def clear_all_posts():
    """
    저장된 모든 블로그 포스트 데이터를 삭제합니다.
    위험한 작업이므로 주의해서 사용해야 합니다.
    
    Returns:
        int: 삭제된 포스트 개수
    """
    try:
        post_keys = [key for key in db.keys() if key.startswith("post_")]
        count = 0
        
        for key in post_keys:
            del db[key]
            count += 1
            
        logger.warning(f"총 {count}개의 포스트가 삭제되었습니다.")
        return count
        
    except Exception as e:
        logger.error(f"포스트 일괄 삭제 중 오류 발생: {str(e)}")
        return 0