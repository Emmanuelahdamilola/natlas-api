# ============================================================================
# N-ATLAS API Server - Production Deployment
# Serves 250 cached Nigerian medical language responses
# Supports: Yoruba, Igbo, Hausa, English
# ============================================================================

from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import os
from rapidfuzz import fuzz, process
from datetime import datetime

# --- NEW IMPORTS FOR LANGUAGE DETECTION ---
import fasttext 
# --- END NEW IMPORTS ---

app = Flask(__name__)
CORS(app) 

# ============================================================================
# LOAD CACHED RESPONSES & LANGUAGE MODEL (STEP 1)
# ============================================================================

CACHE_DIR_NAME = 'cache' 
CACHE_DIR = os.path.join(os.path.dirname(__file__), CACHE_DIR_NAME)

print("🇳🇬 Loading N-ATLAS cached responses...")

# Global variables for cache data and metadata
CACHED_DATA = {"yoruba": [], "igbo": [], "hausa": [], "english": []}
METADATA = {}
total_cached = 0
LANG_MODEL = None # Initialize global fasttext model variable

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

try:
    # Load Language Detection Model (lid.176.ftz)
    model_path = os.path.join(os.path.dirname(__file__), 'lid.176.ftz')
    if os.path.exists(model_path):
        LANG_MODEL = fasttext.load_model(model_path)
        print("✅ Language Detection Model loaded!")
    else:
        print("⚠️ Warning: fastText model (lid.176.bin) not found. Auto-detection disabled.")
except Exception as e:
    print(f"❌ ERROR loading fastText model: {e}")


# ============================================================================
# FUZZY MATCHING & KEYWORD FUNCTIONS (STEP 2 & 3)
# ============================================================================

# 🌟 EXPANDED MEDICAL TERMS LIST (STEP 2)
EXPANDED_MEDICAL_TERMS = {
    'yoruba': [
        'iba', 'otutu', 'aarun', 'aisan',         # Fever, Cold/Chill, Illness, Sickness
        'ori', 'inu', 'ara', 'egungun', 'aya',    # Head, Stomach/Inside, Body, Bone, Chest
        'gbuuru', 'ikọ', 'obi', 'eebi',           # Diarrhea, Cough, Chest/Heart, Vomit
        'rẹwẹsi', 'tutu', 'ogun oru',             # Weakness, Cold, Night sweat
        'ọgbẹ', 'malaria', 'àìsàn', 'gbígbọ̀n'    # Wound/Sore, Malaria, Sickness, Shivering/Chills
    ],
    'igbo': [
        'ọkụ', 'isi', 'ahụ', 'mgbu', 'ọrịa',      # Fever/Heat, Head, Body, Pain, Sickness
        'afọ', 'obi', 'akụkụ', 'ụkwara',          # Stomach, Chest/Heart, Side/Rib, Cough
        'nsi', 'ike', 'oyi', 'ọbara',             # Feces/Diarrhea, Strength/Weakness, Cold, Blood
        'agbọ', 'ọkụọkụ', 'isi ọwụwa', 'ịgba',   # Vomit, Fever, Headache, Cramp/Seizure
        'ịba', 'oké mgbu', 'nkwonkwo', 'azụ'      # Malaria, Severe pain, Joint, Back
    ],
    'hausa': [
        'zazzaɓi', 'sanyi', 'ciwo', 'jinya',       # Fever, Cold, Pain, Sickness
        'kai', 'ciki', 'jiki', 'ƙashi', 'ƙirji',   # Head, Stomach, Body, Bone, Chest
        'tari', 'zawo', 'mura', 'ƙarfi',          # Cough, Diarrhea, Cold, Strength/Weakness
        'hanta', 'zubar', 'jini', 'amo',           # Liver, Bleed/Discharge, Blood, Ringing (ear)
        'malariya', 'ciwon ciki', 'amai', 'baya'  # Malaria, Stomach pain, Vomit, Back
    ],
    'english': [
        'fever', 'headache', 'pain', 'ache', 'sore', # Fever, Headache, Pain, Ache, Sore
        'body', 'stomach', 'chest', 'bone', 'back',  # Body, Stomach, Chest, Bone, Back
        'cough', 'diarrhea', 'vomit', 'weak',        # Cough, Diarrhea, Vomit, Weak
        'cold', 'chills', 'flu', 'malaria',          # Cold, Chills, Flu, Malaria
        'nausea', 'sickness', 'illness', 'fatigue'   # Nausea, Sickness, Illness, Fatigue
    ]
}


# --- Language Detection Function (STEP 3) ---
def detect_language(text):
    """Detects language using fastText and maps it to N-ATLAS languages."""
    global LANG_MODEL
    
    if not LANG_MODEL:
        return 'english' # Default to English if model not loaded

    predictions = LANG_MODEL.predict(text, k=1)
    lang_code = predictions[0][0].replace('__label__', '') 
    
    # Map fastText codes to your API's language names
    code_map = {
        'yo': 'yoruba',
        'ig': 'igbo',
        'ha': 'hausa',
        'en': 'english'
    }
    
    # Return the mapped language, or 'english' as a default fallback
    return code_map.get(lang_code, 'english')


def find_best_match(user_input, language, threshold=70):
    """
    Find best matching cached response using fuzzy matching
    """
    
    if language not in CACHED_DATA or language not in ['yoruba', 'igbo', 'hausa', 'english']:
        return None
    
    cached_cases = CACHED_DATA.get(language, [])
    
    if not cached_cases:
        return None
    
    # Extract all cached inputs (only successful cases)
    cached_inputs = [case.get('input', '') for case in cached_cases if case.get('success', False)]
    
    if not cached_inputs:
        return None
    
    # Find best match using fuzzy matching
    best_match = process.extractOne(
        user_input, 
        cached_inputs,
        scorer=fuzz.token_sort_ratio
    )
    
    if best_match and best_match[1] >= threshold:
        matched_input = best_match[0]
        similarity_score = best_match[1]
        
        # Find the full cached response
        for case in cached_cases:
            if case.get('input') == matched_input and case.get('success', False):
                return {
                    **case,
                    "match_type": "fuzzy" if similarity_score < 100 else "exact",
                    "similarity_score": similarity_score,
                    "matched_input": matched_input,
                    "cached": True
                }
    
    return None

def extract_keywords(text):
    """Extract potential medical keywords from text using the EXPANDED list"""
    keywords = []
    text_lower = text.lower()
    
    # Check against all expanded terms regardless of detected language for maximum coverage
    for lang_terms in EXPANDED_MEDICAL_TERMS.values():
        for term in lang_terms:
            if term in text_lower:
                keywords.append(term)
    
    return list(set(keywords))

def get_fallback_response(text, language):
    """Generate fallback response when no good match is found"""
    keywords = extract_keywords(text)
    
    return {
        "input": text,
        "language": language,
        "translation": f"Medical complaint detected in {language.title()}",
        "cultural_context": f"Patient is communicating in {language.title()}, a major Nigerian language.",
        "medical_keywords": keywords if keywords else ["symptom assessment needed"],
        "severity": "moderate",
        "nigerian_context": "Common medical presentation in Nigerian healthcare. Requires professional assessment.",
        "recommended_specialties": ["General Practitioner"],
        "enhanced_notes": f"Patient complaint: {text}\n\nLanguage: {language.title()}\nDetected keywords: {', '.join(keywords) if keywords else 'None specific'}\n\nRecommendation: Professional medical assessment needed.",
        "match_type": "fallback",
        "similarity_score": 0,
        "success": True,
        "cached": False
    }

# ============================================================================
# API ENDPOINTS (STEP 4: Updated to use auto-detection)
# ============================================================================

@app.route('/', methods=['GET'])
def home():
    """Root endpoint - API info"""
    return jsonify({
        "name": "N-ATLAS Nigerian Medical API",
        "version": "1.0.0",
        "description": "Serves cached N-ATLAS medical language responses for Nigerian languages",
        "languages": ["Yoruba", "Igbo", "Hausa", "English"],
        "total_cached_responses": total_cached,
        "endpoints": {
            "/health": "Health check",
            "/analyze": "Full medical analysis (POST)",
        },
        "status": "online"
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
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
    """Full medical analysis endpoint"""
    try:
        data = request.json
        
        if not data or 'text' not in data:
            return jsonify({
                "success": False,
                "error": "Missing 'text' in request body"
            }), 400
        
        text = data['text'].strip()
        language_input = data.get('language', '').lower()
        
        if not text:
            return jsonify({
                "success": False,
                "error": "Empty text provided"
            }), 400
        
        # --- Language Logic: Use input language or auto-detect ---
        if language_input in ['yoruba', 'igbo', 'hausa', 'english']:
            language = language_input
        elif language_input and language_input not in ['yoruba', 'igbo', 'hausa', 'english']:
             return jsonify({
                "success": False,
                "error": f"Unsupported language: {language_input}. Supported: yoruba, igbo, hausa, english"
            }), 400
        else:
            language = detect_language(text)
            print(f"   (Auto-detected language: {language})")
        
        
        print(f"📝 Analyzing: '{text[:50]}...' ({language})")
        
        # Try to find best match
        result = find_best_match(text, language, threshold=70)
        
        if not result:
            print(f"   ⚠️  No good match found (using fallback)")
            result = get_fallback_response(text, language)
        else:
            print(f"   ✅ Match: {result['match_type']} ({result['similarity_score']}%)")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error in /analyze: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/quick-symptoms', methods=['POST'])
def quick_symptoms():
    """Quick symptom identification endpoint"""
    try:
        data = request.json
        text = data.get('text', '').strip()
        language_input = data.get('language', '').lower()
        
        if not text:
            return jsonify({
                "success": False,
                "error": "Empty text provided"
            }), 400
        
        # --- Language Logic: Use input language or auto-detect ---
        if language_input in ['yoruba', 'igbo', 'hausa', 'english']:
            language = language_input
        else:
            language = detect_language(text)
        
        print(f"⚡ Quick check: '{text[:50]}...' ({language})")
        
        # Find best match
        result = find_best_match(text, language, threshold=65)
        
        if result:
            symptoms = result.get('medical_keywords', [])
            print(f"   ✅ Symptoms: {symptoms[:5]}")
        else:
            symptoms = extract_keywords(text)
            print(f"   ⚠️  Fallback keywords: {symptoms}")
        
        return jsonify({
            "success": True,
            "symptoms": symptoms[:10],
            "language": language,
            "cached": result is not None
        })
        
    except Exception as e:
        print(f"❌ Error in /quick-symptoms: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/analyze-for-doctors', methods=['POST'])
def analyze_for_doctors():
    """
    Enhanced analysis formatted for doctor suggestion API
    """
    try:
        data = request.json
        text = data.get('text', '').strip()
        language_input = data.get('language', '').lower()
        
        if not text:
            return jsonify({
                "success": False,
                "error": "Empty text provided"
            }), 400
        
        # --- Language Logic: Use input language or auto-detect ---
        if language_input in ['yoruba', 'igbo', 'hausa', 'english']:
            language = language_input
        else:
            language = detect_language(text)
        
        print(f"👨‍⚕️ Doctor analysis: '{text[:50]}...' ({language})")
        
        # Find best match
        result = find_best_match(text, language, threshold=70)
        
        if not result:
            result = get_fallback_response(text, language)
        
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
            "match_type": result.get('match_type', 'unknown'),
            "similarity_score": result.get('similarity_score', 0),
            "cached": result.get('cached', False)
        }
        
        print(f"   ✅ Analysis complete ({response['match_type']})")
        
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ Error in /analyze-for-doctors: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

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
