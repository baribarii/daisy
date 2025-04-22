from replit import db
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clear_all_replit_db_data():
    """
    Replit DB에 저장된 모든 데이터를 삭제합니다.
    """
    try:
        # 모든 키 조회
        all_keys = list(db.keys())
        total_keys = len(all_keys)
        
        if total_keys == 0:
            logger.info("Replit DB에 삭제할 데이터가 없습니다.")
            return 0
        
        logger.info(f"총 {total_keys}개의 키를 삭제합니다.")
        
        # 모든 키 삭제
        for key in all_keys:
            del db[key]
            
        logger.info(f"총 {total_keys}개의 키가 성공적으로 삭제되었습니다.")
        return total_keys
        
    except Exception as e:
        logger.error(f"Replit DB 데이터 삭제 중 오류 발생: {str(e)}")
        return -1

if __name__ == "__main__":
    deleted_count = clear_all_replit_db_data()
    if deleted_count >= 0:
        print(f"총 {deleted_count}개의 데이터가 삭제되었습니다.")
    else:
        print("데이터 삭제 중 오류가 발생했습니다.")