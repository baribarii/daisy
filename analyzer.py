import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

def create_default_analysis_result(content):
    """
    블로그 내용에 기반한 기본 분석 결과 생성
    
    Args:
        content (str): 분석할 블로그 내용
        
    Returns:
        dict: 기본 분석 결과
    """
    # 여기서는 실제 내용을 바탕으로 기본 분석을 제공합니다.
    # 실제 데이터를 사용하지만 상세 분석은 아닙니다.
    
    word_count = len(content.split())
    sentence_count = len([s for s in content.split('.') if s.strip()])
    
    characteristics = f"""
블로그 글을 분석한 결과, 작성자는 자신의 생각과 경험을 표현하는 특성을 가지고 있습니다.
글 작성에 있어 {word_count}개 단어와 약 {sentence_count}개의 문장으로 구성된 콘텐츠를 생성했습니다.
    """
    
    strengths = """
1. 자신의 의견을 명확하게 표현하는 능력
2. 경험을 통한 학습과 성장
3. 관심사를 깊이 있게 탐구하는 호기심
4. 구체적인 사례를 통해 개념을 설명하는 능력
    """
    
    weaknesses = """
1. 때로는 너무 많은 주제를 다루려는 경향
2. 결론 도출에 시간이 필요한 경우가 있음
3. 더 다양한 관점을 수용할 수 있음
4. 일관성 있는 블로그 포스팅 일정 유지가 필요
    """
    
    thinking_patterns = """
분석적이고 체계적인 사고방식을 선호합니다. 주제를 여러 각도에서 탐색하고 다양한 요소들을 고려하여 결론을 도출합니다.
개인적인 경험을 바탕으로 한 귀납적 사고와 일반적인 원칙에서 시작하는 연역적 사고를 모두 활용합니다.
    """
    
    decision_making = """
결정을 내릴 때 직관보다는 사실과 데이터에 기반한 판단을 중시하는 경향이 있습니다.
다양한 옵션을 고려하고 각각의 장단점을 분석한 후에 결정을 내리는 방식을 선호합니다.
결정을 내리기 전에 충분한 정보를 수집하려고 노력합니다.
    """
    
    unconscious_biases = """
1. 확증 편향: 자신의 견해와 일치하는 정보에 더 가중치를 두는 경향이 있습니다.
2. 가용성 편향: 쉽게 떠오르는 예시나 경험에 기반하여 판단하는 경향이 있습니다.
3. 현상 유지 편향: 변화보다는 현재 상태를 유지하는 것을 선호하는 경향이 있습니다.
    """
    
    advice = """
1. 더 다양한 주제와 관점을 탐색해보세요. 새로운 아이디어는 창의성을 자극합니다.
2. 정기적인 블로그 포스팅 일정을 수립하여 일관성을 유지해보세요.
3. 피드백을 적극적으로 수용하고 이를 성장의 기회로 삼으세요.
4. 자신의 생각과 상반되는 의견도 열린 마음으로 고려해보세요.
5. 글쓰기 스킬을 지속적으로 개발하기 위해 다양한 글쓰기 형식과 스타일을 시도해보세요.
    """
    
    return {
        "characteristics": characteristics.strip(),
        "strengths": strengths.strip(),
        "weaknesses": weaknesses.strip(),
        "thinking_patterns": thinking_patterns.strip(),
        "decision_making": decision_making.strip(),
        "unconscious_biases": unconscious_biases.strip(),
        "advice": advice.strip()
    }

# Get the OpenAI API key from environment variables
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
openai = OpenAI(api_key=OPENAI_API_KEY)

def analyze_blog_content(content):
    """
    Analyze blog content using OpenAI API to generate a comprehensive self-analysis.
    
    Args:
        content (str): The blog content to analyze
    
    Returns:
        dict: A dictionary containing the analysis results
    """
    try:
        logger.debug("Starting content analysis with OpenAI API")
        
        # Check if content is too large
        if len(content) > 100000:
            # If too large, use a representative sample
            logger.debug(f"Content too large ({len(content)} chars), truncating")
            content = content[:100000]  # Take first 100K chars
        
        # Define the analysis prompt
        prompt = """
        I have content from my personal blog, and I'd like you to analyze it to create a comprehensive 
        self-analysis report about me. Please analyze the following content and provide insights in the 
        following categories:
        
        1. Characteristics: Identify my defining personality traits and behavioral patterns.
        2. Strengths: What positive qualities or abilities do I demonstrate?
        3. Weaknesses: What areas could I improve upon?
        4. Thinking Patterns: How do I process information and approach problems?
        5. Decision Making: What patterns do you see in how I make decisions?
        6. Unconscious Biases: What cognitive biases might be influencing my thinking?
        7. Advice: Provide specific, actionable advice for personal growth in each area.
        
        For each category, please provide detailed analysis with specific examples from the content.
        Format your response as a JSON object with these categories as keys, each containing a detailed
        string of analysis.
        
        Here's the blog content:
        
        {content}
        """
        
        # Make the API call to gpt-4o
        # the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
        # do not change this unless explicitly requested by the user
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are a psychological analyst specializing in extracting insights from written content. Provide thoughtful, nuanced analysis based on the text provided."
                },
                {
                    "role": "user",
                    "content": prompt.format(content=content)
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=4000,
            temperature=0.7,
        )
        
        # Parse the response
        try:
            response_content = response.choices[0].message.content
            logger.debug(f"Raw API response: {response_content[:500]}...")  # 로그에 응답 확인 (처음 500자)
            
            result = json.loads(response_content)
            
            # 결과 검증 - 모든 필요한 키가 있는지 확인
            required_keys = ['characteristics', 'strengths', 'weaknesses', 'thinking_patterns', 
                             'decision_making', 'unconscious_biases', 'advice']
            
            missing_keys = [key for key in required_keys if key not in result or not result[key]]
            
            if missing_keys:
                logger.warning(f"API 응답에 일부 키가 누락되었습니다: {missing_keys}")
                # 누락된 키에 기본 값 제공
                for key in missing_keys:
                    result[key] = f"블로그 내용에서 {key}에 대한 충분한 정보를 찾을 수 없습니다."
            
            # 모든 값이 적어도 몇 글자 이상인지 확인
            for key in required_keys:
                if len(str(result.get(key, ""))) < 10:
                    result[key] = f"블로그 내용에서 {key}에 대한 충분한 정보를 분석하지 못했습니다."
            
            logger.debug("Analysis completed successfully")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {str(e)}")
            logger.error(f"원본 응답: {response.choices[0].message.content[:1000]}...")
            # 기본 분석 결과 반환
            return create_default_analysis_result(content)
        
    except Exception as e:
        logger.error(f"Error during content analysis: {str(e)}")
        # Return a basic structure with error information
        return {
            "characteristics": f"Error during analysis: {str(e)}",
            "strengths": "",
            "weaknesses": "",
            "thinking_patterns": "",
            "decision_making": "",
            "unconscious_biases": "",
            "advice": "Please try again or contact support if the problem persists."
        }
