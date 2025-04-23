/**
 * 포스트 카드 최신순 정렬 기능
 * 날짜 형식을 인식하고 최신순으로 정렬합니다.
 */
document.addEventListener('DOMContentLoaded', function() {
  // 포스트 컨테이너 찾기
  const postsContainer = document.querySelector('.posts-container');
  if (!postsContainer) return;

  // 모든 포스트 카드 요소 가져오기
  const postCards = Array.from(postsContainer.querySelectorAll('.post-card'));
  if (postCards.length <= 1) return; // 정렬할 필요 없음

  // 날짜 변환 함수
  function parseKoreanDate(dateStr) {
    if (!dateStr) return new Date(0); // 날짜 없으면 가장 오래된 날짜로

    // YYYY-MM-DD 형식 처리
    const ymdMatch = dateStr.match(/(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})/);
    if (ymdMatch) {
      return new Date(
        parseInt(ymdMatch[1]), 
        parseInt(ymdMatch[2]) - 1, 
        parseInt(ymdMatch[3])
      );
    }
    
    // YYYY년 MM월 DD일 형식 처리
    const koreanMatch = dateStr.match(/(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일/);
    if (koreanMatch) {
      return new Date(
        parseInt(koreanMatch[1]), 
        parseInt(koreanMatch[2]) - 1, 
        parseInt(koreanMatch[3])
      );
    }

    // 인식할 수 없는 날짜는 가장 오래된 날짜로
    return new Date(0);
  }

  // 날짜로 정렬
  postCards.sort((a, b) => {
    const dateA = a.querySelector('.post-date')?.textContent || '';
    const dateB = b.querySelector('.post-date')?.textContent || '';
    
    return parseKoreanDate(dateB) - parseKoreanDate(dateA); // 최신순
  });

  // 정렬된 순서로 다시 DOM에 삽입
  postCards.forEach(card => {
    postsContainer.appendChild(card);
  });
});