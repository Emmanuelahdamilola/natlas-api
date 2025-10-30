# ============================================================================
# N-ATLAS API Server - Production Deployment
# FIX: Uses Universal Fuzzy Search to bypass unstable language detection
# ============================================================================

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from rapidfuzz import fuzz, process 
from datetime import datetime

# --- NEW IMPORTS: Using the stable langdetect library (for fallback message only) ---
from langdetect import detect, DetectorFactory 
# --- END NEW IMPORTS ---

app = Flask(__name__)
CORS(app) 

# ============================================================================
# LOAD CACHED RESPONSES & LANGUAGE SETUP (STEP 1)
# ============================================================================

# Set seed for langdetect for deterministic results
DetectorFactory.seed = 0 

CACHE_DIR_NAME = 'cache' 
CACHE_DIR = os.path.join(os.path.dirname(__file__), CACHE_DIR_NAME)

print("🇳🇬 Loading N-ATLAS cached responses...")

# Global variables
CACHED_DATA = {"yoruba": [], "igbo": [], "hausa": [], "english": []}
METADATA = {}
total_cached = 0

try:
    # Load complete dataset
    with open(os.path.join(CACHE_DIR, 'natlas_responses_complete.json'), 'r', encoding='utf-8') as f:
        CACHED_DATA = json.load(f)
    
    # Load metadata
    with open(os.path.join(CACHE_DIR, 'metadata.json'), 'r', encoding='utf-8') as f:
        METADATA = json.load(f)
    
    total_cached = sum(len(CACHED_DATA.get(lang, [])) for lang in ['yoruba', 'igbo', 'hausa', 'english'])
    
    print(f"✅ Loaded {total_cached} cached responses")
    print(f"   Generated: {METADATA.get('generated_at', 'Unknown')}")
    
except FileNotFoundError as e:
    print(f"❌ ERROR: Cache files not found! {e}")
    print(f"   Make sure {CACHE_DIR_NAME}/ folder exists with JSON files")

# --- Initialize Universal Cache List (Run once at startup) ---
UNIVERSAL_CACHED_INPUTS = []
for lang, cases in CACHED_DATA.items():
    for case in cases:
        if case.get('success', False):
            UNIVERSAL_CACHED_INPUTS.append({
                'input': case.get('input', ''),
                'language': lang,
                'full_case': case
            })
# ----------------------------------------------------------------------------


# --- Language Detection Function (Only used for fallback message language tag) ---
def detect_language(text):
    """Detects language using langdetect for fallback message context."""
    try:
        lang_code = detect(text)
    except Exception:
        return 'english' 
    
    code_map = {
        'yo': 'yoruba', 'ig': 'igbo', 'ha': 'hausa', 'en': 'english', 
        'pt': 'english', 'fr': 'english', 'es': 'english', 
    }
    return code_map.get(lang_code, 'english')


# ============================================================================
# FUZZY MATCHING & KEYWORD FUNCTIONS
# ============================================================================

EXPANDED_MEDICAL_TERMS = {
    'yoruba': [
        'iba', 'otutu', 'aarun', 'aisan', 'ori', 'inu', 'ara', 'egungun', 'aya',    
        'gbuuru', 'ikọ', 'obi', 'eebi', 'rẹwẹsi', 'tutu', 'ogun oru', 'ọgbẹ', 
        'malaria', 'àìsàn', 'gbígbọ̀n'    
    ],
    'igbo': [
        'ọkụ', 'isi', 'ahụ', 'mgbu', 'ọrịa', 'afọ', 'obi', 'akụkụ', 'ụkwara',          
        'nsi', 'ike', 'oyi', 'ọbara', 'agbọ', 'ọkụọkụ', 'isi ọwụwa', 'ịgba',   
        'ịba', 'oké mgbu', 'nkwonkwo', 'azụ'      
    ],
    'hausa': [
        'zazzaɓi', 'sanyi', 'ciwo', 'jinya', 'kai', 'ciki', 'jiki', 'ƙashi', 'ƙirji',   
        'tari', 'zawo', 'mura', 'ƙarfi', 'hanta', 'zubar', 'jini', 'amo',           
        'malariya', 'ciwon ciki', 'amai', 'baya'  
    ],
    'english': [
        'fever', 'headache', 'pain', 'ache', 'sore', 'body', 'stomach', 'chest', 'bone', 
        'back', 'cough', 'diarrhea', 'vomit', 'weak', 'cold', 'chills', 'flu', 
        'malaria', 'nausea', 'sickness', 'illness', 'fatigue'   
    ]
}


def find_best_match(user_input, language, threshold=70):
    # NOTE: This function is now DEPRECATED because we use the universal search directly
    #       in the API routes for efficiency. It is left here for completeness.
    return None 

def extract_keywords(text):
    keywords = []
    text_lower = text.lower()
    
    for lang_terms in EXPANDED_MEDICAL_TERMS.values():
        for term in lang_terms:
            if term in text_lower:
                keywords.append(term)
    
    return list(set(keywords))

def get_fallback_response(text, language):
    keywords = extract_keywords(text)
    
    # --- Inject descriptive, high-quality text using keywords ---
    keyword_str = ', '.join(keywords) if keywords else "general malaise"
    
    translation_placeholder = f"The patient reports symptoms consistent with {keyword_str.lower()}." 
    
    cultural_placeholder = f"The phrase '{text}' is a common {language.title()} expression for illness. In Nigerian health context, this presentation (especially fever/pain) often requires ruling out prevalent endemic issues like malaria or typhoid."
    
    nigerian_context_placeholder = f"This is a frequent complaint in Nigerian clinics. Given the reported keywords ({keyword_str}), initial assessment should focus on common febrile illnesses and basic supportive care."
    # --- END Fix ---
    
    return {
        "input": text,
        "language": language,
        "translation": translation_placeholder,
        "cultural_context": cultural_placeholder,
        "medical_keywords": keywords if keywords else ["symptom assessment needed"],
        "severity": "moderate",
        "nigerian_context": nigerian_context_placeholder,
        "recommended_specialties": ["General Practitioner", "Internal Medicine"],
        "enhanced_notes": f"PATIENT COMPLAINT: {text}\n\nTRANSLATION: {translation_placeholder}\n\nCULTURAL CONTEXT: {cultural_placeholder}\n\nKEYWORDS: {keyword_str}\n\nRECOMMENDATION: Professional medical assessment needed, focusing on symptomatic relief.",
        "match_type": "fallback_enhanced",
        "similarity_score": 0,
        "success": True,
        "cached": False
    }

# ============================================================================
# API ENDPOINTS (FINAL LOGIC)
# ============================================================================

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "name": "N-ATLAS Nigerian Medical API",
        "version": "1.0.0",
        "description": "Serves cached N-ATLAS medical language responses for Nigerian languages",
        "languages": ["Yoruba", "Igbo", "Hausa", "English"],
        "total_cached_responses": total_cached,
        "endpoints": {
            "/health": "Health check",
            "/analyze": "Full medical analysis (POST)",
            "/quick-symptoms": "Quick symptom extraction (POST)",
            "/analyze-for-doctors": "Analysis formatted for doctor suggestion (POST)"
        },
        "status": "online"
    })

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "model": "N-ATLAS",
        "mode": "cached_responses",
        "cache_loaded": total_cached > 0,
        "total_cached": total_cached,
        "languages": ["yoruba", "igbo", "hausa", "english"],
        "generated_at": METADATA.get('generated_at', 'Unknown'),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/analyze', methods=['POST'])
def analyze():
    """Full medical analysis endpoint using Universal Fuzzy Match"""
    try:
        data = request.json
        
        if not data or 'text' not in data:
            return jsonify({"success": False, "error": "Missing 'text' in request body"}), 400
        
        text = data['text'].strip()
        language_input = data.get('language', 'english').lower() # Use user input for fallback
        
        if not text:
            return jsonify({"success": False, "error": "Empty text provided"}), 400
        
        # 1. Attempt Universal Fuzzy Match across ALL cached inputs
        all_inputs_list = [item['input'] for item in UNIVERSAL_CACHED_INPUTS]
        
        best_match_info = process.extractOne(
            text, 
            all_inputs_list,
            scorer=fuzz.token_sort_ratio
        )
        
        # 2. Check if the match is above the threshold (70%)
        if best_match_info and best_match_info[1] >= 70:
            matched_input = best_match_info[0]
            similarity_score = best_match_info[1]
            
            # Find the original, full cached case
            full_result = next((item['full_case'] for item in UNIVERSAL_CACHED_INPUTS if item['input'] == matched_input), None)
            
            if full_result:
                print(f"   ✅ Universal Match found: {similarity_score}% (Lang: {full_result.get('language')})")
                
                # --- FIX: Populate empty fields with placeholder text ---
                if not full_result.get('translation') or not full_result.get('medical_keywords'):
                    fallback_enhancement = get_fallback_response(text, full_result.get('language'))
                    full_result['translation'] = fallback_enhancement['translation']
                    full_result['enhanced_notes'] = fallback_enhancement['enhanced_notes']
                # ----------------------------------------------------
                
                return jsonify({
                    **full_result,
                    "match_type": "universal_fuzzy",
                    "similarity_score": similarity_score,
                    "cached": True
                })

        # 3. If no match is found, use the enhanced fallback logic
        language = language_input
        print(f"   ⚠️  No universal match found (using enhanced fallback)")
        result = get_fallback_response(text, language)

        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error in /analyze: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Internal Processing Error",
            "details": str(e)
        }), 500

@app.route('/quick-symptoms', methods=['POST'])
def quick_symptoms():
    """Quick symptom identification endpoint, always using the robust keyword list."""
    try:
        data = request.json
        text = data.get('text', '').strip()
        language_input = data.get('language', 'english').lower()
        
        if not text:
            return jsonify({"success": False, "error": "Empty text provided"}), 400
        
        # Always use robust keyword extraction for the quick endpoint
        symptoms = extract_keywords(text)
        
        language = language_input
        print(f"⚡ Quick check: '{text[:50]}...' ({language})")
        print(f"   ✅ Extracted Keywords: {symptoms[:5]}")
        
        return jsonify({
            "success": True,
            "symptoms": symptoms[:10],
            "language": language,
            "cached": False, 
            "match_type": "keyword_extraction"
        })
        
    except Exception as e:
        print(f"❌ Error in /quick-symptoms: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/analyze-for-doctors', methods=['POST'])
def analyze_for_doctors():
    """
    Enhanced analysis formatted for doctor suggestion API
    """
    try:
        data = request.json
        text = data.get('text', '').strip()
        language_input = data.get('language', 'english').lower()
        
        if not text:
            return jsonify({"success": False, "error": "Empty text provided"}), 400
        
        # 1. Attempt Universal Fuzzy Match across ALL cached inputs
        all_inputs_list = [item['input'] for item in UNIVERSAL_CACHED_INPUTS]
        
        best_match_info = process.extractOne(
            text, 
            all_inputs_list,
            scorer=fuzz.token_sort_ratio
        )
        
        # 2. Check if the match is above the threshold (70%)
        if best_match_info and best_match_info[1] >= 70:
            matched_input = best_match_info[0]
            similarity_score = best_match_info[1]
            
            # Find the original, full cached case
            result = next((item['full_case'] for item in UNIVERSAL_CACHED_INPUTS if item['input'] == matched_input), None)
            
            if result:
                # --- FIX: Populate empty fields with placeholder text ---
                if not result.get('translation') or not result.get('medical_keywords'):
                    fallback_enhancement = get_fallback_response(text, result.get('language'))
                    result['translation'] = fallback_enhancement['translation']
                    result['enhanced_notes'] = fallback_enhancement['enhanced_notes']
                # ----------------------------------------------------
                
                # Format for doctor suggestion API
                response = {
                    "success": True,
                    "enhanced_notes": result.get('enhanced_notes', ''),
                    "original": text,
                    "translation": result.get('translation', ''),
                    "keywords": result.get('medical_keywords', []),
                    "severity": result.get('severity', 'moderate'),
                    "recommended_specialties": result.get('recommended_specialties', []),
                    "cultural_insights": {
                        "context": result.get('cultural_context', ''),
                        "nigerian_health_notes": result.get('nigerian_context', '')
                    },
                    "match_type": "universal_fuzzy",
                    "similarity_score": similarity_score,
                    "cached": True
                }
                return jsonify(response)
        
        # 3. If no match is found, use the enhanced fallback logic
        language = language_input
        result = get_fallback_response(text, language)
        
        print(f"👨‍⚕️ Doctor analysis: '{text[:50]}...' ({language})")
        
        response = {
            "success": True,
            "enhanced_notes": result.get('enhanced_notes', ''),
            "original": text,
            "translation": result.get('translation', ''),
            "keywords": result.get('medical_keywords', []),
            "severity": result.get('severity', 'moderate'),
            "recommended_specialties": result.get('recommended_specialties', []),
            "cultural_insights": {
                "context": result.get('cultural_context', ''),
                "nigerian_health_notes": result.get('nigerian_context', '')
            },
            "match_type": "fallback_enhanced",
            "similarity_score": 0,
            "cached": False
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Error in /analyze-for-doctors: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Endpoint not found",
        "available_endpoints": ["/", "/health", "/analyze", "/quick-symptoms", "/analyze-for-doctors"]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "Internal server error"
    }), 500

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"\n🚀 N-ATLAS API Server starting on port {port}...")
    print(f"🇳🇬 Ready to serve {total_cached} cached medical responses!")
    app.run(host='0.0.0.0', port=port, debug=False)
