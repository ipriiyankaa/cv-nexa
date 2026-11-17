import os
import re
from pypdf import PdfReader
import docx
from fpdf import FPDF
from google import genai

# Safe SpaCy Import (Prevents DLL crash on Python 3.14+ Windows)
SPACY_AVAILABLE = False
nlp = None
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
    SPACY_AVAILABLE = True
except Exception as e:
    print(f"Using Built-in Pure-Python NLP Lemmatizer (SpaCy skipped: {e})")

STOPWORDS = {
    'and', 'the', 'for', 'with', 'you', 'that', 'this', 'from', 'have', 'are',
    'will', 'your', 'about', 'must', 'requirements', 'required', 'looking',
    'proficient', 'skilled', 'experienced', 'experience', 'using', 'into',
    'work', 'working', 'role', 'team', 'years', 'year', 'knowledge', 'good',
    'strong', 'ability', 'skills', 'skill', 'such', 'well', 'also', 'other'
}


def simple_lemmatize(word):
    """Pure-Python morphological root lemmatizer fallback."""
    if len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ing") and len(word) > 5:
        base = word[:-3]
        if len(base) > 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    if word.endswith("ed") and len(word) > 4:
        base = word[:-2]
        if len(base) > 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    if word.endswith("ers") and len(word) > 5:
        return word[:-3]
    if word.endswith("er") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def extract_text_from_pdf(file_path):
    text = ""
    try:
        reader = PdfReader(file_path)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + " "
    except Exception as e:
        print(f"PDF Read Error: {e}")
    return text


def extract_text_from_docx(file_path):
    try:
        doc = docx.Document(file_path)
        full_text = [para.text for para in doc.paragraphs if para.text]
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    if cell.text.strip():
                        full_text.append(cell.text.strip())
        return " ".join(full_text)
    except Exception as e:
        print(f"DOCX Read Error: {e}")
        return ""


def parse_resume(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.pdf':
        return extract_text_from_pdf(file_path)
    elif ext in ['.docx', '.doc']:
        return extract_text_from_docx(file_path)
    else:
        raise ValueError("Unsupported file format. Please upload PDF or DOCX.")


def extract_nlp_features(text):
    """
    Extracts lemmatized single keywords AND 2-word technical phrases (bigrams).
    Uses SpaCy if available, otherwise uses Pure-Python NLP engine.
    """
    lemmas = set()
    clean_tokens = []

    if SPACY_AVAILABLE and nlp is not None:
        doc = nlp(text.lower())
        for token in doc:
            if token.is_alpha and not token.is_stop and len(token.text) > 2:
                lemmas.add(token.lemma_)
                clean_tokens.append(token.lemma_)
    else:
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
        for w in words:
            if w not in STOPWORDS:
                root = simple_lemmatize(w)
                lemmas.add(root)
                clean_tokens.append(root)

    bigrams = set()
    for i in range(len(clean_tokens) - 1):
        phrase = f"{clean_tokens[i]} {clean_tokens[i + 1]}"
        bigrams.add(phrase)

    return lemmas, bigrams


def analyze_keywords_detailed(resume_text, job_desc):
    if not job_desc.strip():
        return 0, [], [], {"keyword_score": 0, "formatting_score": 0, "action_verbs_score": 0, "metrics_score": 0}

    res_lemmas, res_bigrams = extract_nlp_features(resume_text)
    jd_lemmas, jd_bigrams = extract_nlp_features(job_desc)

    if not jd_lemmas:
        return 0, [], [], {"keyword_score": 0, "formatting_score": 0, "action_verbs_score": 0, "metrics_score": 0}

    # 1. Single Lemma + Phrase Matching
    matched_lemmas = res_lemmas.intersection(jd_lemmas)
    missing_lemmas = jd_lemmas.difference(res_lemmas)
    matched_phrases = res_bigrams.intersection(jd_bigrams)

    base_kw_ratio = len(matched_lemmas) / len(jd_lemmas)
    phrase_bonus = (len(matched_phrases) / len(jd_bigrams)) * 0.25 if jd_bigrams else 0
    keyword_score = min(round((base_kw_ratio + phrase_bonus) * 100), 100)

    matched_display = list(matched_phrases)[:5] + sorted(list(matched_lemmas))
    missing_display = sorted(list(missing_lemmas))

    # 2. Formatting & Section Completeness Check
    formatting_score = 30
    sections = ['education', 'experience', 'project', 'skill', 'summary', 'certification', 'achievement']
    res_lower = resume_text.lower()
    for sec in sections:
        if sec in res_lower:
            formatting_score += 10
    formatting_score = min(round(formatting_score), 100)

    # 3. Strong Action Verbs Check
    action_verbs = [
        'developed', 'managed', 'created', 'built', 'led', 'designed', 'optimized',
        'implemented', 'achieved', 'launched', 'engineered', 'automated', 'reduced',
        'increased', 'integrated', 'deployed', 'architected', 'analyzed'
    ]
    found_verbs = [v for v in action_verbs if re.search(r'\b' + v + r'\b', res_lower)]
    action_verbs_score = min(len(found_verbs) * 12, 100)

    # 4. Quantifiable Metrics Check
    numbers_found = re.findall(
        r'\b\d+(\.\d+)?%\b|\$\d+|\b\d+\+\b|\b\d+\s*(users|clients|customers|projects|k|m|x)\b',
        res_lower
    )
    metrics_score = min(len(numbers_found) * 20, 100)

    # Final Weighted ATS Score
    overall_score = round(
        (keyword_score * 0.50) +
        (formatting_score * 0.20) +
        (action_verbs_score * 0.15) +
        (metrics_score * 0.15)
    )

    score_breakdown = {
        "keyword_score": keyword_score,
        "formatting_score": formatting_score,
        "action_verbs_score": action_verbs_score,
        "metrics_score": metrics_score
    }

    return overall_score, matched_display[:16], missing_display[:16], score_breakdown


def generate_insights_and_questions(resume_text, job_desc, missing_keywords):
    api_key = os.environ.get("GEMINI_API_KEY")

    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"""
            You are an expert ATS Resume Coach & Senior Technical Recruiter.
            
            Resume Snippet: {resume_text[:1500]}
            Job Description Snippet: {job_desc[:1500]}
            Missing Keywords: {', '.join(missing_keywords[:8])}
            
            Provide a concise, high-impact response with these exact two sections:
            ### Recommended Resume Bullet Points
            (Write 3 STAR-method bullet points naturally integrating the missing keywords with measurable impact)
            
            ### Expected Interview Questions
            (Write 3 targeted technical/behavioral interview questions based on the candidate's skill gaps, along with a 1-line hint on how to answer each)
            """
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            return response.text
        except Exception as e:
            print(f"Gemini API Fallback Triggered: {e}")

    output = "### Recommended Resume Bullet Points\n"
    if missing_keywords:
        top_kws = ", ".join([kw.capitalize() for kw in missing_keywords[:4]])
        output += f"1. Engineered scalable modules utilizing {top_kws}, reducing processing latency by 25%.\n"
        output += f"2. Integrated {missing_keywords[0].capitalize()} workflows into production pipelines, improving system reliability by 30%.\n\n"
    else:
        output += "1. Spearheaded end-to-end feature delivery, improving user engagement by 20%.\n\n"

    output += "### Expected Interview Questions\n"
    if missing_keywords:
        for idx, kw in enumerate(missing_keywords[:3], 1):
            output += f"{idx}. How have you implemented or worked with '{kw.capitalize()}' in a real-world project?\n"
    else:
        output += "1. Walk me through the most complex architecture decision you made in your recent project.\n"
        output += "2. How do you ensure code quality, testing, and performance under tight deadlines?\n"

    return output


def rewrite_bullet_with_ai(original_bullet):
    api_key = os.environ.get("GEMINI_API_KEY")
    if api_key:
        try:
            client = genai.Client(api_key=api_key)
            prompt = f"Rewrite this resume bullet point using the STAR method (Strong Action Verb + Technical Context + Quantifiable Result): '{original_bullet}'. Give 3 distinct, ATS-optimized options."
            response = client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            return response.text
        except Exception as e:
            print(f"Rewriter Fallback: {e}")

    return (
        f"1. Spearheaded '{original_bullet}', boosting workflow efficiency by 25% and minimizing manual errors.\n"
        f"2. Architected and executed '{original_bullet}' using industry best practices, achieving a 20% faster turnaround time.\n"
        f"3. Optimized end-to-end delivery for '{original_bullet}', directly enhancing overall team productivity by 15%."
    )


def generate_pdf_report(score, matched, missing, insights, breakdown, output_path="static/resume_analysis_report.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=16, style="B")
    pdf.cell(0, 10, text="CV Nexa - Resume Evaluation Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    pdf.set_font("Helvetica", size=13, style="B")
    pdf.cell(0, 10, text=f"Overall ATS Compatibility Score: {score}%", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", size=10)
    pdf.cell(
        0, 6,
        text=f"Keywords: {breakdown['keyword_score']}%  |  Formatting: {breakdown['formatting_score']}%  |  Action Verbs: {breakdown['action_verbs_score']}%  |  Impact Metrics: {breakdown['metrics_score']}%",
        new_x="LMARGIN", new_y="NEXT"
    )
    pdf.ln(5)

    pdf.set_font("Helvetica", size=11, style="B")
    pdf.cell(0, 8, text="Matched Skills & Phrases:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 6, text=", ".join(matched) if matched else "None detected")
    pdf.ln(4)

    pdf.set_font("Helvetica", size=11, style="B")
    pdf.cell(0, 8, text="Missing Target Keywords:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 6, text=", ".join(missing) if missing else "None - Great Match!")
    pdf.ln(5)

    pdf.set_font("Helvetica", size=11, style="B")
    pdf.cell(0, 8, text="AI Bullet Recommendations & Interview Prep:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    clean_text = insights.replace("###", "").replace("**", "")
    clean_text = clean_text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 5, text=clean_text)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    pdf.output(output_path)
    return output_path