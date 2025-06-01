from flask import Flask, request, jsonify
import os
import re
import requests
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
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

        self.conversation_context = {}
        self.previous_comments = []
        self.comment_counts = {}

        self.slang_words = [
            "মাগি", "খানি", "চোদা", "চোদি", "চুদি", "চুদা", "রান্ড", "বেশ্যা",
            "হারামি", "হারামজাদা", "কুত্তা", "কুত্তার বাচ্চা", "শুওরের বাচ্চা",
            "গাধা", "গাধার বাচ্চা", "বদমাইশ", "নোংরা", "নোংরামি",
            "হুদা", "বকবক", "বিরক্তিকর",
            "লেংড়া", "পঙ্গু", "অন্ধ", "বোবা", "কালা", "মোটা", "চিকন",
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
            "lmao", "lmfao", "omfg", "fml", "gtfo", "kys",
            "f0ck", "sh1t", "b1tch", "d1ck", "fuk", "sht",
            "magi", "khani", "choda", "chodi", "chudi", "chuda", "rand",
            "harami", "haramjada", "kutta", "kuttar bacha", "shuorer bacha",
            "gadha", "gadhar bacha", "badmaish", "nongra",
            "huda", "bokbok", "biriktikor",
            "মাদার চোদ", "ফাক", "শিট", "বিচ", "ড্যাম"
        ]

        self.slang_patterns = [
            r'f+u+c+k+i*n*g*',
            r's+h+i+t+',
            r'b+i+t+c+h+',
            r'চো+দা+',
            r'মা+গি+',
            r'খা+নি+',
            r'হা+রা+মি+',
        ]

    def increment_comment_count(self, page_id):
        self.comment_counts[page_id] = self.comment_counts.get(page_id, 0) + 1

    def get_comment_count(self, page_id):
        return self.comment_counts.get(page_id, 0)

    def is_limit_reached(self, page_id, comment_limit):
        current_count = self.get_comment_count(page_id)
        if not comment_limit or comment_limit <= 0:
            return False
        return current_count >= comment_limit

    def reset_comment_count(self, page_id):
        self.comment_counts[page_id] = 0

    def store_conversation_context(self, page_id, post_id, page_info, post_info):
        context_key = f"{page_id}_{post_id}"
        self.conversation_context[context_key] = {
            "page_info": page_info,
            "post_info": post_info,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_conversation_context(self, page_id, post_id):
        context_key = f"{page_id}_{post_id}"
        return self.conversation_context.get(context_key, {})

    def add_comment_history(self, comment_data):
        self.previous_comments.append({
            "comment_id": comment_data.get("comment_id", ""),
            "comment_text": comment_data.get("comment_text", ""),
            "commenter_name": comment_data.get("commenter_name", ""),
            "post_id": comment_data.get("post_id", ""),
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
        if not text or len(text.strip()) == 0:
            return False

        cleaned = self.clean_text_for_slang(text)
        original_lower = text.lower().strip()

        greetings = ['hello', 'hi', 'hey', 'hellow', 'helo', 'hii', 'hiii', 'hello there',
                     'hi there', 'hey there', 'assalamu alaikum', 'salam', 'নমস্কার', 'হ্যালো', 'হাই']

        for greeting in greetings:
            if original_lower == greeting or original_lower.startswith(greeting + ' ') or original_lower.endswith(
                    ' ' + greeting):
                return False

        false_positives = {
            'hell': ['hello', 'shell', 'hell-o', 'hellow', 'hello there', 'hi hello'],
            'ass': ['class', 'pass', 'mass', 'glass', 'grass', 'assistant', 'assalam', 'assalamu'],
            'damn': ['adam', 'amsterdam'],
            'bad': ['abad', 'badminton', 'baghdad']
        }

        for slang in self.slang_words:
            slang_lower = slang.lower()

            if slang_lower in ['hell', 'ass', 'bad', 'damn'] and len(slang_lower) <= 4:
                continue

            if slang_lower in false_positives:
                pattern = r'\b' + re.escape(slang_lower) + r'\b'
                matches = re.findall(pattern, original_lower)
                if matches:
                    is_false_positive = False
                    for fp_word in false_positives[slang_lower]:
                        if fp_word in original_lower:
                            is_false_positive = True
                            break
                    if not is_false_positive:
                        return True
            else:
                pattern = r'\b' + re.escape(slang_lower) + r'\b'
                if re.search(pattern, cleaned) or re.search(pattern, original_lower):
                    return True

        for pattern in self.slang_patterns:
            matches = re.findall(pattern, cleaned, re.IGNORECASE)
            if matches:
                for match in matches:
                    if len(match) >= 5:
                        return True

        spaced_text = re.sub(r'\s+', '', cleaned)
        for slang in self.slang_words:
            slang_lower = slang.lower()
            if len(slang_lower) >= 5 and slang_lower in spaced_text:
                return True

        no_space_text = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', original_lower)
        for slang in self.slang_words:
            slang_lower = slang.lower()
            clean_slang = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', slang_lower)

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
        else: # Neutral sentiment
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

    def generate_reply(self, json_data):
        start_time = time.time()

        data = json_data.get("data", {})
        page_info = data.get("page_info", {})
        post_info = data.get("post_info", {})
        comment_info = data.get("comment_info", {})

        comment_text = comment_info.get("comment_text", "").strip()

        if not comment_text:
            return {"error": "Comment text is required"}

        page_id = page_info.get("page_id", "")
        post_id = post_info.get("post_id", "")

        comment_limit_from_db = page_info.get("comment limit") # Get limit from page_info
        # Ensure comment_limit_from_db is an integer, default to None if not found or invalid
        comment_limit = None
        if isinstance(comment_limit_from_db, int) and comment_limit_from_db >= 0:
            comment_limit = comment_limit_from_db
        elif isinstance(comment_limit_from_db, str) and comment_limit_from_db.isdigit():
            comment_limit = int(comment_limit_from_db)

        if page_id and comment_limit is not None:
            if self.is_limit_reached(page_id, comment_limit):
                print(f"Comment limit reached for page_id: {page_id}. Current count: {self.get_comment_count(page_id)}, Limit: {comment_limit}")
                return {
                    "reply": "Your comment limit exceeded.", # Updated message
                    "sentiment": "Neutral",
                    "response_time": f"{time.time() - start_time:.2f}s",
                    "controlled": True,
                    "slang_detected": False,
                    "comment_id": comment_info.get("comment_id", ""),
                    "commenter_name": comment_info.get("commenter_name", ""),
                    "page_name": page_info.get("page_name", ""),
                    "post_id": post_id,
                    "page_id": page_id,
                    "current_count": self.get_comment_count(page_id),
                    "comment_limit": comment_limit,
                    "limit_reached": True,
                    "note": f"Comment limit of {comment_limit} reached for page '{page_info.get('page_name', 'Unknown')}'. Current count: {self.get_comment_count(page_id)}."
                }
            else:
                self.increment_comment_count(page_id)

        if page_id and post_id:
            self.store_conversation_context(page_id, post_id, page_info, post_info)

        if self.contains_slang(comment_text):
            return {
                "reply": self.get_slang_response(),
                "sentiment": "Inappropriate",
                "response_time": f"{time.time() - start_time:.2f}s",
                "controlled": True,
                "slang_detected": True,
                "comment_id": comment_info.get("comment_id", ""),
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "page_id": page_id,
                "current_count": self.get_comment_count(page_id),
                "comment_limit": comment_limit,
                "limit_reached": False
            }

        comment_language = self.detect_comment_language(comment_text)
        sentiment = self.get_sentiment(comment_text)

        context = f"Page Name: {page_info.get('page_name', 'Unknown')} (ID: {page_info.get('page_id', 'N/A')})\n"
        context += f"Post Content: {post_info.get('post_content', 'No content available')}\n"
        context += f"Post Type: {post_info.get('post_type', 'Unknown')}\n\n"

        if self.previous_comments:
            context += "Recent Comments for Context:\n"
            for prev in self.previous_comments[-3:]:
                context += f"- {prev['comment_text']} by {prev['commenter_name']} ({prev['timestamp']})\n"
            context += "\n"

        system_prompt = """You are a page manager. Reply to comments STRICTLY based on provided page and post information only.

STRICT RULES:
1. NEVER answer questions beyond the provided page/post information.
2. If asked about something not in page info, respond with polite fallback responses.
3. Keep replies under 50 words maximum.
4. Don't give general advice, tips, or external information.
5. Only mention services/products/info that are specifically provided in the page/post data.
6. If a comment is about something you don't have information about, acknowledge but don't elaborate.
7. LANGUAGE MATCHING: Reply in the SAME language as the comment.
    - If comment is in Bangla, reply in Bangla.
    - If comment is in English, reply in English.
    - If comment is mixed, use the dominant language.
8. Use a natural, conversational tone.

RESPONSE STYLE:
- Positive comments: Thank briefly.
- Questions: Answer ONLY if info exists in the provided page/post details.
- Complaints: Apologize briefly, offer to help via message.
- General queries: Redirect to "contact us" if no specific information is available."""

        if comment_language == "bangla":
            language_instruction = "IMPORTANT: The comment is in BANGLA. You MUST reply in BANGLA language only."
        elif comment_language == "english":
            language_instruction = "IMPORTANT: The comment is in ENGLISH. You MUST reply in ENGLISH language only."
        else:
            language_instruction = "IMPORTANT: The comment is mixed language. Reply in the dominant language used in the comment."

        user_prompt = f"""Page and Post Information Available:
{context}

Current Comment: "{comment_text}"
Commenter: {comment_info.get('commenter_name', 'Anonymous')}

{language_instruction}

Reply ONLY based on the page and post information above. If the comment asks about anything not mentioned in the information, give a brief polite fallback response. Keep reply under 50 words. Match the language of the comment."""

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
            response.raise_for_status()

            reply = response.json()['choices'][0]['message']['content'].strip()
            response_time = time.time() - start_time

            if not self.validate_response(reply, comment_text):
                reply = self.get_fallback_response(comment_text, sentiment)

            self.add_comment_history({
                **comment_info,
                "post_id": post_id
            })

            return {
                "reply": reply,
                "sentiment": sentiment,
                "response_time": f"{response_time:.2f}s",
                "controlled": self.validate_response(reply, comment_text),
                "slang_detected": False,
                "comment_id": comment_info.get("comment_id", ""),
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "page_id": page_id,
                "current_count": self.get_comment_count(page_id),
                "comment_limit": comment_limit,
                "limit_reached": False
            }

        except requests.exceptions.RequestException as e:
            print(f"API call error: {e}")
            fallback_reply = self.get_fallback_response(comment_text, sentiment)
            return {
                "reply": fallback_reply,
                "sentiment": sentiment,
                "response_time": f"{time.time() - start_time:.2f}s",
                "controlled": True,
                "slang_detected": False,
                "comment_id": comment_info.get("comment_id", ""),
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "page_id": page_id,
                "current_count": self.get_comment_count(page_id),
                "comment_limit": comment_limit,
                "limit_reached": False,
                "error": str(e)
            }
        except Exception as e:
            print(f"Error generating reply: {e}")
            fallback_reply = self.get_fallback_response(comment_text, sentiment)
            return {
                "reply": fallback_reply,
                "sentiment": sentiment,
                "response_time": f"{time.time() - start_time:.2f}s",
                "controlled": True,
                "slang_detected": False,
                "comment_id": comment_info.get("comment_id", ""),
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "page_id": page_id,
                "current_count": self.get_comment_count(page_id),
                "comment_limit": comment_limit,
                "limit_reached": False,
                "error": str(e)
            }

# Initialize the bot
fb_bot = FacebookBot()

@app.route('/process-comment', methods=['POST'])
def process_comment():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    reply_data = fb_bot.generate_reply(data)
    return jsonify(reply_data)

if __name__ == '__main__':
    # Define the specific port you want to use
    SPECIFIC_PORT = 8000 # You can change this to any available port, e.g., 5000, 8080, etc.
    app.run(debug=True, port=SPECIFIC_PORT)