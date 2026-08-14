import re

def evaluate_multiple_choice(selected_option, correct_option):
    return {
        'is_correct': str(selected_option).strip() == str(correct_option).strip(),
        'selected': selected_option
    }

def evaluate_rubric(user_text, keywords, threshold=0.75):
    if not user_text:
        return {'is_passed': False, 'score_percent': 0, 'user_text': ''}
        
    user_text_lower = user_text.lower()
    matched_count = sum(1 for kw in keywords if re.search(r'\b' + re.escape(kw.lower()) + r'\b', user_text_lower))
    total_keywords = len(keywords)
    
    score_percent = (matched_count / total_keywords) if total_keywords > 0 else 0
    
    return {
        'is_passed': score_percent >= threshold,
        'score_percent': round(score_percent * 100),
        'user_text': user_text
    }