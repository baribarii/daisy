/**
 * 포스트 카드 최신순 정렬 기능
 * URL에서 logNo를 추출하여 최신순으로 정렬합니다.
 * 네이버 블로그는 logNo 번호가 클수록 최신 글입니다.
 */
document.addEventListener('DOMContentLoaded', function() {
  console.log('포스트 정렬 스크립트 실행 시작');
  
  // 포스트 컨테이너 찾기
  const postsContainer = document.querySelector('.posts-container');
  if (!postsContainer) {
    console.warn('포스트 컨테이너를 찾을 수 없습니다.');
    return;
  }

  // 모든 포스트 카드 요소 가져오기
  const postCards = Array.from(postsContainer.querySelectorAll('.post-card'));
  console.log(`정렬할 포스트 카드: ${postCards.length}개`);
  
  if (postCards.length <= 1) {
    console.log('정렬할 포스트가 1개 이하입니다. 정렬 불필요.');
    return; // 정렬할 필요 없음
  }

  // URL에서 logNo 추출 함수
  function extractLogNo(url) {
    if (!url) return 0;
    
    // logNo 파라미터 추출 시도
    const logNoParam = url.match(/logNo=(\d+)/);
    if (logNoParam && logNoParam[1]) {
      return parseInt(logNoParam[1]);
    }
    
    // 직접 URL 구조에서 추출 (예: https://blog.naver.com/userId/223840700407)
    const directLogNo = url.match(/\/(\d{9,})\/?$/);
    if (directLogNo && directLogNo[1]) {
      return parseInt(directLogNo[1]);
    }
    
    return 0; // logNo를 찾을 수 없는 경우
  }

  // 포스트 정렬용 메타데이터 수집 및 로그
  const cardData = postCards.map(card => {
    // 먼저 data-logno 속성에서 logNo 가져오기 시도
    let logNo = parseInt(card.getAttribute('data-logno') || '0');
    
    // data-logno 속성이 없거나 유효하지 않으면 링크에서 추출 시도
    if (!logNo) {
      const link = card.querySelector('a.post-link');
      const url = link ? link.getAttribute('href') : '';
      logNo = extractLogNo(url);
    }
    
    const title = card.querySelector('.card-title')?.textContent || '제목 없음';
    
    return { card, logNo, title };
  });
  
  // 디버깅을 위한 메타데이터 로그 출력
  console.log('수집된 포스트 메타데이터:');
  cardData.forEach(item => {
    console.log(`제목: ${item.title.substring(0, 20)}... - logNo: ${item.logNo}`);
  });

  // logNo 기준으로 정렬 (내림차순: 높은 번호 = 최신글)
  cardData.sort((a, b) => b.logNo - a.logNo);
  
  // 정렬 결과 로그
  console.log('정렬 결과 (상위 5개):');
  cardData.slice(0, 5).forEach((item, idx) => {
    console.log(`${idx+1}. ${item.title.substring(0, 20)}... - logNo: ${item.logNo}`);
  });

  // 정렬된 순서로 다시 DOM에 삽입
  const fragment = document.createDocumentFragment();
  cardData.forEach(item => {
    fragment.appendChild(item.card);
  });
  
  // 기존 내용을 지우고 새로 정렬된 카드 추가
  while (postsContainer.firstChild) {
    postsContainer.removeChild(postsContainer.firstChild);
  }
  postsContainer.appendChild(fragment);
  
  console.log('포스트 정렬 완료');
});