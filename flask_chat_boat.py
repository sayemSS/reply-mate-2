from flask import Flask, request, jsonify
import os
import re
import requests
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)


class FacebookBot:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "gpt-4o-mini"

        if not self.api_key:
            raise Exception("OPENAI_API_KEY not found in .env file")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        self.page_info = ""
        self.previous_comments = []

        # Updated slang words list - removed problematic short words that cause false positives
        self.slang_words = [
            # Bengali explicit words
            "মাগি", "খানি", "চোদা", "চোদি", "চুদি", "চুদা", "রান্ড", "বেশ্যা",
            "হারামি", "হারামজাদা", "কুত্তা", "কুত্তার বাচ্চা", "শুওরের বাচ্চা",
            "গাধা", "গাধার বাচ্চা", "বদমাইশ", "নোংরা", "নোংরামি",
            "হুদা", "বকবক", "বিরক্তিকর",
            "লেংড়া", "পঙ্গু", "অন্ধ", "বোবা", "কালা", "মোটা", "চিকন",

            # English explicit words - kept only clear offensive words, REMOVED problematic short words
            "fuck", "fucking", "fucked", "fucker", "fck", "f*ck", "f**k",
            "shit", "bullshit", "sh*t", "s**t",
            "bitch", "bitches", "b*tch", "b**ch",
            "asshole", "a**hole",
            "dick", "cock", "penis", "d*ck", "c**k",
            "pussy", "vagina", "cunt", "p***y", "c**t",
            "slut", "whore", "prostitute", "sl*t", "wh*re",
            "bastard", "b*stard", "b**tard",
            "dumbass", "stupid", "idiot", "moron", "retard",
            "wtf", "stfu",

            # Common internet slang/abbreviations
            "lmao", "lmfao", "omfg", "fml", "gtfo", "kys",

            # Leetspeak and variations
            "f0ck", "sh1t", "b1tch", "d1ck", "fuk", "sht",

            # Bengali romanized slang
            "magi", "khani", "choda", "chodi", "chudi", "chuda", "rand",
            "harami", "haramjada", "kutta", "kuttar bacha", "shuorer bacha",
            "gadha", "gadhar bacha", "badmaish", "nongra",
            "huda", "bokbok", "biriktikor",

            # Mixed language slang
            "মাদার চোদ", "ফাক", "শিট", "বিচ", "ড্যাম"
        ]

        # Updated patterns - more specific
        self.slang_patterns = [
            r'f+u+c+k+i*n*g*',
            r's+h+i+t+',
            r'b+i+t+c+h+',
            r'চো+দা+',
            r'মা+গি+',
            r'খা+নি+',
            r'হা+রা+মি+',
        ]

    def set_page_info(self, info):
        self.page_info = info

    def add_comment_history(self, comment):
        self.previous_comments.append({
            "comment": comment,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        if len(self.previous_comments) > 10:
            self.previous_comments.pop(0)

    def clean_text_for_slang(self, text):
        text = text.lower()
        symbol_replacements = {
            '@': 'a', '3': 'e', '1': 'i', '0': 'o', '5': 's',
            '$': 's', '7': 't', '4': 'a', '!': 'i', '*': '',
            '#': '', '%': '', '&': '', '+': '', '=': '',
        }
        for symbol, replacement in symbol_replacements.items():
            text = text.replace(symbol, replacement)
        text = re.sub(r'[.!?]{2,}', '.', text)
        text = re.sub(r'[-_]{2,}', ' ', text)
        text = re.sub(r'(.)\1{2,}', r'\1\1', text)
        return text

    def contains_slang(self, text):
        """Enhanced slang detection with proper word boundary checking"""
        if not text or len(text.strip()) == 0:
            return False

        cleaned = self.clean_text_for_slang(text)
        original_lower = text.lower().strip()

        # First check for common greetings - these should NEVER be flagged as slang
        greetings = ['hello', 'hi', 'hey', 'hellow', 'helo', 'hii', 'hiii', 'hello there',
                     'hi there', 'hey there', 'assalamu alaikum', 'salam', 'নমস্কার', 'হ্যালো', 'হাই']

        for greeting in greetings:
            if original_lower == greeting or original_lower.startswith(greeting + ' ') or original_lower.endswith(
                    ' ' + greeting):
                return False

        # Common false positive words to avoid
        false_positives = {
            'hell': ['hello', 'shell', 'hell-o', 'hellow', 'hello there', 'hi hello'],
            'ass': ['class', 'pass', 'mass', 'glass', 'grass', 'assistant', 'assalam', 'assalamu'],
            'damn': ['adam', 'amsterdam'],
            'bad': ['abad', 'badminton', 'baghdad']
        }

        # Method 1: Strict word boundary matching
        for slang in self.slang_words:
            slang_lower = slang.lower()

            # Skip very short problematic words entirely
            if slang_lower in ['hell', 'ass', 'bad', 'damn'] and len(slang_lower) <= 4:
                continue

            # Check if this slang word has known false positives
            if slang_lower in false_positives:
                # Use exact word matching only
                pattern = r'\b' + re.escape(slang_lower) + r'\b'
                matches = re.findall(pattern, original_lower)
                if matches:
                    # Check if it's actually a false positive
                    is_false_positive = False
                    for fp_word in false_positives[slang_lower]:
                        if fp_word in original_lower:
                            is_false_positive = True
                            break
                    if not is_false_positive:
                        return True
            else:
                # Normal word boundary check for other slang words
                pattern = r'\b' + re.escape(slang_lower) + r'\b'
                if re.search(pattern, cleaned) or re.search(pattern, original_lower):
                    return True

        # Method 2: Pattern matching for repeated characters (more strict)
        for pattern in self.slang_patterns:
            matches = re.findall(pattern, cleaned, re.IGNORECASE)
            if matches:
                for match in matches:
                    if len(match) >= 5:  # Increased minimum length
                        return True

        # Method 3: Check for intentionally spaced out slang (only for longer words)
        spaced_text = re.sub(r'\s+', '', cleaned)
        for slang in self.slang_words:
            slang_lower = slang.lower()
            if len(slang_lower) >= 5 and slang_lower in spaced_text:  # Increased minimum length
                return True

        # Method 4: Check for slang with mixed symbols (very restrictive)
        no_space_text = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', original_lower)
        for slang in self.slang_words:
            slang_lower = slang.lower()
            clean_slang = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', slang_lower)

            # Only check longer slang words
            if len(clean_slang) >= 5 and clean_slang in no_space_text:
                return True

        return False

    def get_sentiment(self, comment):
        positive_words = ['ভালো', 'good', 'great', 'excellent', 'love', 'amazing', 'wonderful', 'thanks', 'ধন্যবাদ',
                          'সুন্দর', 'চমৎকার', 'hello', 'hi', 'hey', 'nice', 'awesome']
        negative_words = ['খারাপ', 'bad', 'terrible', 'awful', 'hate', 'horrible', 'angry', 'disappointed', 'বিরক্ত',
                          'রাগ']
        comment_lower = comment.lower()
        positive_count = sum(1 for word in positive_words if word in comment_lower)
        negative_count = sum(1 for word in negative_words if word in comment_lower)
        if positive_count > negative_count:
            return "Positive"
        elif negative_count > positive_count:
            return "Negative"
        else:
            return "Neutral"

    def validate_response(self, reply, comment):
        out_of_scope_indicators = [
            'generally', 'usually', 'typically', 'in most cases',
            'experts say', 'studies show', 'research indicates',
            'you should try', 'i recommend', 'best practice'
        ]
        reply_lower = reply.lower()
        if any(indicator in reply_lower for indicator in out_of_scope_indicators):
            return False
        if len(reply.split()) > 50:
            return False
        return True

    def get_slang_response(self):
        import random
        responses = [
            "দয়া করে ভদ্র ভাষায় মন্তব্য করুন। আমরা আপনাকে সাহায্য করতে চাই। 🙏",
            "অনুগ্রহ করে শালীন ভাষা ব্যবহার করুন। আমরা সবার সাথে সম্মানের সাথে কথা বলি। ✋",
            "Please use respectful language. We're here to help you in a positive way. 😊",
            "আমাদের পেজে সবাই ভদ্র আচরণ করেন। দয়া করে শালীন ভাষায় মন্তব্য করুন। 🚫",
            "এই ধরনের ভাষা ব্যবহার করবেন না। আমরা সকলের সাথে সম্মানের সাথে কথা বলি। ❌",
            "Please maintain a respectful tone. We believe in positive communication. 🤝"
        ]
        return random.choice(responses)

    def get_fallback_response(self, comment, sentiment):
        import random
        comment_lower = comment.lower()
        comment_language = self.detect_comment_language(comment)

        # Check for greetings
        if any(word in comment_lower for word in
               ['hello', 'hi', 'hey', 'assalam', 'salam', 'হ্যালো', 'হাই', 'নমস্কার']):
            if comment_language == "bangla":
                return random.choice([
                    "আসসালামু আলাইকুম! কেমন আছেন? 😊",
                    "হ্যালো! আপনাকে স্বাগতম। 👋",
                    "নমস্কার! কী সাহায্য করতে পারি? 🙏"
                ])
            else:
                return random.choice([
                    "Hello! Welcome to our page! 👋",
                    "Hi there! How can we help you? 😊",
                    "Hey! Thanks for reaching out! 🙏"
                ])

        if any(word in comment_lower for word in ['application', 'apply', 'job', 'আবেদন', 'চাকরি', 'লিখতে']):
            if comment_language == "bangla":
                return random.choice([
                    "অ্যাপ্লিকেশন লেখার জন্য আমাদের অফিসিয়াল ফর্ম ডাউনলোড করুন অথবা সরাসরি ইনবক্সে যোগাযোগ করুন।",
                    "আপনার আবেদন সংক্রান্ত প্রশ্নের জন্য আমাদের ইনবক্সে মেসেজ করুন, আমরা সাহায্য করবো।",
                    "আবেদন প্রক্রিয়া সম্পর্কে বিস্তারিত জানতে দয়া করে আমাদের সাথে যোগাযোগ করুন।"
                ])
            else:
                return random.choice([
                    "Please download our official application form or contact us directly via inbox.",
                    "For application related queries, please message us in inbox. We'll help you.",
                    "For detailed information about application process, please contact us."
                ])

        if sentiment == "Positive":
            if comment_language == "bangla":
                fallbacks = [
                    "ধন্যবাদ! আপনার মতামতের জন্য কৃতজ্ঞ। 🙏",
                    "আপনার সাপোর্টের জন্য ধন্যবাদ! ❤️",
                    "অসংখ্য ধন্যবাদ আপনাকে! 😊"
                ]
            else:
                fallbacks = [
                    "Thank you for your kind words! 😊",
                    "We appreciate your support! ❤️",
                    "Thanks for your positive feedback! 🙏"
                ]
        elif sentiment == "Negative":
            if comment_language == "bangla":
                fallbacks = [
                    "দুঃখিত! আরো তথ্যের জন্য আমাদের ইনবক্স করুন।",
                    "আমরা এই বিষয়ে খোঁজ নিয়ে জানাবো।",
                    "দুঃখিত! বিস্তারিত জানতে আমাদের সাথে যোগাযোগ করুন।"
                ]
            else:
                fallbacks = [
                    "Sorry for any inconvenience. Please message us for details.",
                    "We'll look into this matter and get back to you.",
                    "Sorry! Please contact us for more information."
                ]
        else:
            if comment_language == "bangla":
                fallbacks = [
                    "আমাদের পেজ সম্পর্কিত কোনো প্রশ্ন থাকলে ইনবক্সে মেসেজ করুন, আমরা সাহায্য করবো।",
                    "আমাদের সেবা বা পণ্য সম্পর্কে জানতে ইনবক্সে যোগাযোগ করুন।",
                    "আপনার প্রশ্নের উত্তর পেতে দয়া করে আমাদের সাথে সরাসরি যোগাযোগ করুন।"
                ]
            else:
                fallbacks = [
                    "For any questions about our page, please message us in inbox. We'll help you.",
                    "To know about our services or products, please contact us via inbox.",
                    "For answers to your questions, please contact us directly."
                ]
        return random.choice(fallbacks)

    def detect_comment_language(self, comment):
        """Detect if comment is primarily in Bangla or English"""
        bangla_chars = re.findall(r'[\u0980-\u09FF]', comment)
        english_chars = re.findall(r'[a-zA-Z]', comment)

        bangla_count = len(bangla_chars)
        english_count = len(english_chars)

        if bangla_count > english_count:
            return "bangla"
        elif english_count > bangla_count:
            return "english"
        else:
            return "mixed"

    def generate_reply(self, comment):
        start_time = time.time()

        # Check for slang FIRST
        if self.contains_slang(comment):
            return {
                "reply": self.get_slang_response(),
                "sentiment": "Inappropriate",
                "response_time": f"{time.time() - start_time:.2f}s",
                "controlled": True,
                "slang_detected": True
            }

        # If no slang detected, proceed with normal processing
        comment_language = self.detect_comment_language(comment)
        sentiment = self.get_sentiment(comment)

        context = f"Facebook Page Information: {self.page_info}\n\n"
        if self.previous_comments:
            context += "Recent Comments for Context:\n"
            for prev in self.previous_comments[-3:]:
                context += f"- {prev['comment']} ({prev['timestamp']})\n"
            context += "\n"

        system_prompt = """You are a Facebook page manager. Reply to comments STRICTLY based on provided page information only.

STRICT RULES:
1. NEVER answer questions beyond the provided page information
2. If asked about something not in page info, respond with polite fallback responses
3. Keep replies under 50 words maximum
4. Don't give general advice, tips, or external information
5. Only mention services/products/info that are specifically provided
6. If comment is about something you don't have info about, acknowledge but don't elaborate
7. LANGUAGE MATCHING: Reply in the SAME language as the comment
   - If comment is in Bangla, reply in Bangla
   - If comment is in English, reply in English
   - If comment is mixed, use the dominant language
8. Use natural, conversational tone

RESPONSE STYLE:
- Positive comments: Thank briefly
- Questions: Answer ONLY if info exists in page details
- Complaints: Apologize briefly, offer to help via message
- General queries: Redirect to "contact us" if no specific info available"""

        # Language-specific instruction
        if comment_language == "bangla":
            language_instruction = "IMPORTANT: The comment is in BANGLA. You MUST reply in BANGLA language only."
        elif comment_language == "english":
            language_instruction = "IMPORTANT: The comment is in ENGLISH. You MUST reply in ENGLISH language only."
        else:
            language_instruction = "IMPORTANT: The comment is mixed language. Reply in the dominant language used in the comment."

        user_prompt = f"""Page Information Available:
{context}

Current Comment: "{comment}"

{language_instruction}

Reply ONLY based on the page information above. If the comment asks about anything not mentioned in page information, give a brief polite fallback response. Keep reply under 50 words. Match the language of the comment."""

        # Updated parameters optimized for Bangla language
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 150,
            "temperature": 0.4,
            "top_p": 0.9,
            "frequency_penalty": 0.2,
            "presence_penalty": 0.1
        }

        try:
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=30)
            if response.status_code != 200:
                return {"error": f"API call failed ({response.status_code})"}

            reply = response.json()['choices'][0]['message']['content'].strip()
            response_time = time.time() - start_time

            if not self.validate_response(reply, comment):
                reply = self.get_fallback_response(comment, sentiment)

            self.add_comment_history(comment)

            return {
                "reply": reply,
                "sentiment": sentiment,
                "response_time": f"{response_time:.2f}s",
                "controlled": self.validate_response(reply, comment),
                "slang_detected": False
            }
        except Exception as e:
            # If API fails, use fallback response
            response_time = time.time() - start_time
            return {
                "reply": self.get_fallback_response(comment, sentiment),
                "sentiment": sentiment,
                "response_time": f"{response_time:.2f}s",
                "controlled": True,
                "slang_detected": False,
                "note": "Used fallback due to API error"
            }


# Initialize bot instance
bot = FacebookBot()


@app.route('/set-page-info', methods=['POST'])
def set_page_info():
    """Set or update Facebook page information"""
    try:
        data = request.get_json()
        if not data or 'page_info' not in data:
            return jsonify({
                "success": False,
                "message": "page_info is required"
            }), 400

        bot.set_page_info(data['page_info'])
        return jsonify({
            "success": True,
            "message": "Page information updated successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500


@app.route('/generate-reply', methods=['POST'])
def generate_reply():
    """Generate reply for a comment/question"""
    try:
        data = request.get_json()

        # Validate input
        if not data:
            return jsonify({
                "success": False,
                "message": "JSON data is required"
            }), 400

        if 'comment' not in data or not data['comment'].strip():
            return jsonify({
                "success": False,
                "message": "comment field is required and cannot be empty"
            }), 400

        # Optional: Set page info if provided
        if 'page_info' in data and data['page_info']:
            bot.set_page_info(data['page_info'])

        # Generate reply
        comment = data['comment'].strip()
        result = bot.generate_reply(comment)

        if 'error' in result:
            return jsonify({
                "success": False,
                "message": result['error']
            }), 500

        return jsonify({
            "success": True,
            "data": {
                "original_comment": comment,
                "reply": result['reply'],
                "sentiment": result['sentiment'],
                "response_time": result['response_time'],
                "controlled": result['controlled'],
                "slang_detected": result['slang_detected'],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}"
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "success": True,
        "message": "Facebook Bot API is running",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route('/test-slang', methods=['POST'])
def test_slang():
    """Test endpoint to check slang detection"""
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({
                "success": False,
                "message": "text field is required"
            }), 400

        text = data['text'].strip()
        is_slang = bot.contains_slang(text)
        sentiment = bot.get_sentiment(text)

        return jsonify({
            "success": True,
            "data": {
                "text": text,
                "is_slang": is_slang,
                "sentiment": sentiment,
                "language": bot.detect_comment_language(text)
            }
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500


if __name__ == "__main__":
    print("🤖 Facebook Bot API Server Starting...")
    print("📍 Server will run on: http://localhost:6002")
    print("🔗 Available endpoints:")
    print("   POST /set-page-info - Set page information")
    print("   POST /generate-reply - Generate reply for comments")
    print("   POST /test-slang - Test slang detection")
    print("   GET  /health - Health check")
    print("=" * 50)

    app.run(debug=True, host='0.0.0.0', port=6002)