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
        # Retrieve API key from environment variables
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "gpt-4o-mini" # Using the specified model

        # Ensure API key is present
        if not self.api_key:
            raise Exception("OPENAI_API_KEY not found in .env file")

        # Headers for API requests
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Store conversation context for each page and post
        self.conversation_context = {}
        # Store recent comments for conversational flow
        self.previous_comments = []

        # --- NEW: Comment Limiting Variables ---
        # Stores the maximum comment limit for each page_id
        # Example: {"page_id_1": 100, "page_id_2": 50}
        self.page_limits = {}
        # Stores the current comment count for each page_id
        # Example: {"page_id_1": 45, "page_id_2": 20}
        self.comment_counts = {}
        # --- END NEW ---

        # Updated list of slang words for detection
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

        # Updated regex patterns for more specific slang detection
        self.slang_patterns = [
            r'f+u+c+k+i*n*g*',
            r's+h+i+t+',
            r'b+i+t+c+h+',
            r'চো+দা+',
            r'মা+গি+',
            r'খা+নি+',
            r'হা+রা+মি+',
        ]

    # --- NEW: Methods for Comment Limiting ---
    def set_page_limit(self, page_id, limit):
        """Sets the maximum comment reply limit for a specific page."""
        if not isinstance(limit, int) or limit < 0:
            raise ValueError("Limit must be a non-negative integer.")
        self.page_limits[page_id] = limit
        # Initialize count if page is new or reset if limit changes significantly
        if page_id not in self.comment_counts:
            self.comment_counts[page_id] = 0
        return True

    def get_page_limit(self, page_id):
        """Gets the maximum comment reply limit for a specific page."""
        return self.page_limits.get(page_id, -1) # -1 indicates no limit set

    def increment_comment_count(self, page_id):
        """Increments the comment count for a given page."""
        self.comment_counts[page_id] = self.comment_counts.get(page_id, 0) + 1

    def get_comment_count(self, page_id):
        """Gets the current comment count for a given page."""
        return self.comment_counts.get(page_id, 0)

    def is_limit_reached(self, page_id):
        """Checks if the comment limit has been reached for a given page."""
        max_limit = self.get_page_limit(page_id)
        current_count = self.get_comment_count(page_id)
        # If no limit is set (max_limit is -1), limit is never reached
        if max_limit == -1:
            return False
        return current_count >= max_limit
    # --- END NEW ---

    def store_conversation_context(self, page_id, post_id, page_info, post_info):
        """
        Store page and post context for generating relevant replies.
        This context helps the bot remember details about the page and the specific post.
        """
        context_key = f"{page_id}_{post_id}"
        self.conversation_context[context_key] = {
            "page_info": page_info,
            "post_info": post_info,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

    def get_conversation_context(self, page_id, post_id):
        """
        Retrieve stored context for a specific page and post.
        """
        context_key = f"{page_id}_{post_id}"
        return self.conversation_context.get(context_key, {})

    def add_comment_history(self, comment_data):
        """
        Add a comment to the history for contextual understanding in subsequent replies.
        Keeps only the last 10 comments to manage memory usage.
        """
        self.previous_comments.append({
            "comment_id": comment_data.get("comment_id", ""),
            "comment_text": comment_data.get("comment_text", ""),
            "commenter_name": comment_data.get("commenter_name", ""),
            "post_id": comment_data.get("post_id", ""),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        # Keep only last 10 comments for context
        if len(self.previous_comments) > 10:
            self.previous_comments.pop(0)

    def clean_text_for_slang(self, text):
        """
        Cleans text by converting to lowercase, replacing symbols with letters,
        and normalizing repeated characters for better slang detection.
        """
        text = text.lower()
        symbol_replacements = {
            '@': 'a', '3': 'e', '1': 'i', '0': 'o', '5': 's',
            '$': 's', '7': 't', '4': 'a', '!': 'i', '*': '',
            '#': '', '%': '', '&': '', '+': '', '=': '',
        }
        for symbol, replacement in symbol_replacements.items():
            text = text.replace(symbol, replacement)
        text = re.sub(r'[.!?]{2,}', '.', text) # Normalize multiple punctuation marks
        text = re.sub(r'[-_]{2,}', ' ', text) # Replace multiple hyphens/underscores with space
        text = re.sub(r'(.)\1{2,}', r'\1\1', text) # Reduce more than two repetitions of any character
        return text

    def contains_slang(self, text):
        """
        Enhanced slang detection using multiple methods:
        1. Strict word boundary matching for known slang words.
        2. Pattern matching for variations (e.g., repeated characters).
        3. Checking for intentionally spaced out slang.
        4. Checking for slang with mixed symbols.
        Includes safeguards against common false positives (e.g., "hello" not being flagged as "hell").
        """
        if not text or len(text.strip()) == 0:
            return False

        cleaned = self.clean_text_for_slang(text)
        original_lower = text.lower().strip()

        # First check for common greetings - these should NEVER be flagged as slang
        greetings = ['hello', 'hi', 'hey', 'hellow', 'helo', 'hii', 'hiii', 'hello there',
                     'hi there', 'hey there', 'assalamu alaikum', 'salam', 'নমস্কার', 'হ্যালো', 'হাই']

        for greeting in greetings:
            # Check for exact greeting or greeting at start/end of sentence
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

            # Skip very short problematic words entirely if they are in false_positives keys
            if slang_lower in ['hell', 'ass', 'bad', 'damn'] and len(slang_lower) <= 4:
                continue

            # Check if this slang word has known false positives
            if slang_lower in false_positives:
                # Use exact word matching only for these cases
                pattern = r'\b' + re.escape(slang_lower) + r'\b'
                matches = re.findall(pattern, original_lower)
                if matches:
                    # Check if it's actually a false positive context
                    is_false_positive = False
                    for fp_word in false_positives[slang_lower]:
                        if fp_word in original_lower: # Check if the false positive word is present
                            is_false_positive = True
                            break
                    if not is_false_positive: # If it's not a false positive, then it's slang
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
                    if len(match) >= 5:  # Increased minimum length for pattern matches
                        return True

        # Method 3: Check for intentionally spaced out slang (only for longer words)
        spaced_text = re.sub(r'\s+', '', cleaned) # Remove all spaces
        for slang in self.slang_words:
            slang_lower = slang.lower()
            if len(slang_lower) >= 5 and slang_lower in spaced_text:  # Increased minimum length for this check
                return True

        # Method 4: Check for slang with mixed symbols (very restrictive)
        no_space_text = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', original_lower)
        for slang in self.slang_words:
            slang_lower = slang.lower()
            clean_slang = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', slang_lower)

            # Only check longer slang words for this method
            if len(clean_slang) >= 5 and clean_slang in no_space_text:
                return True

        return False

    def get_sentiment(self, comment):
        """
        Determines the sentiment of a comment (Positive, Negative, or Neutral)
        based on a predefined list of keywords.
        """
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
        """
        Validates the generated reply to ensure it's within scope and length limits.
        Prevents the bot from giving overly general or lengthy responses.
        """
        out_of_scope_indicators = [
            'generally', 'usually', 'typically', 'in most cases',
            'experts say', 'studies show', 'research indicates',
            'you should try', 'i recommend', 'best practice'
        ]
        reply_lower = reply.lower()
        # Check for out-of-scope phrases
        if any(indicator in reply_lower for indicator in out_of_scope_indicators):
            return False
        # Check for reply length (max 50 words)
        if len(reply.split()) > 50:
            return False
        return True

    def get_slang_response(self):
        """
        Returns a random predefined response when slang is detected.
        """
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
        """
        Provides a relevant fallback response if the LLM fails or the generated
        reply is invalid. Responses are tailored to sentiment and language.
        """
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

        # Check for application/job related keywords
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

        # Fallback based on sentiment
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
        """
        Detects if a comment is primarily in Bangla or English by counting character sets.
        """
        bangla_chars = re.findall(r'[\u0980-\u09FF]', comment) # Unicode range for Bengali characters
        english_chars = re.findall(r'[a-zA-Z]', comment) # English alphabet characters

        bangla_count = len(bangla_chars)
        english_count = len(english_chars)

        if bangla_count > english_count:
            return "bangla"
        elif english_count > bangla_count:
            return "english"
        else:
            return "mixed"

    def generate_reply(self, json_data):
        """
        Generates a reply to a comment based on the provided JSON data.
        It first checks for slang, then determines sentiment and language,
        builds a context for the LLM, and finally generates a controlled reply.
        """
        start_time = time.time()

        # Extract data from the incoming JSON payload
        data = json_data.get("data", {})
        page_info = data.get("page_info", {})
        post_info = data.get("post_info", {})
        comment_info = data.get("comment_info", {})

        comment_text = comment_info.get("comment_text", "").strip()

        # Return error if comment text is empty
        if not comment_text:
            return {"error": "Comment text is required"}

        # Store context for this specific page and post
        page_id = page_info.get("page_id", "")
        post_id = post_info.get("post_id", "")

        # --- NEW: Check and apply comment limits ---
        if page_id: # Only apply limit if page_id is available
            if self.is_limit_reached(page_id):
                # If limit reached, return a specific message indicating no reply
                print(f"Comment limit reached for page_id: {page_id}. No reply generated.")
                return {
                    "reply": "We have received many comments on this page. We will address all queries as soon as possible. Thank you for your understanding.",
                    "sentiment": "Neutral",
                    "response_time": f"{time.time() - start_time:.2f}s",
                    "controlled": True,
                    "slang_detected": False,
                    "comment_id": comment_info.get("comment_id", ""),
                    "commenter_name": comment_info.get("commenter_name", ""),
                    "page_name": page_info.get("page_name", ""),
                    "post_id": post_id,
                    "note": f"Comment limit of {self.get_page_limit(page_id)} reached for this page. Current count: {self.get_comment_count(page_id)}."
                }
            else:
                self.increment_comment_count(page_id) # Increment count only if not reached and processing
        # --- END NEW ---

        if page_id and post_id:
            self.store_conversation_context(page_id, post_id, page_info, post_info)

        # Check for slang FIRST and return a predefined response if detected
        if self.contains_slang(comment_text):
            return {
                "reply": self.get_slang_response(),
                "sentiment": "Inappropriate",
                "response_time": f"{time.time() - start_time:.2f}s",
                "controlled": True, # Indicates a controlled, predefined response
                "slang_detected": True,
                "comment_id": comment_info.get("comment_id", ""),
                "commenter_name": comment_info.get("commenter_name", "")
            }

        # If no slang detected, proceed with normal processing
        comment_language = self.detect_comment_language(comment_text)
        sentiment = self.get_sentiment(comment_text)

        # Build context string for the LLM from the JSON data
        context = f"Page Name: {page_info.get('page_name', 'Unknown')} (ID: {page_info.get('page_id', 'N/A')})\n"
        context += f"Post Content: {post_info.get('post_content', 'No content available')}\n"
        context += f"Post Type: {post_info.get('post_type', 'Unknown')}\n\n"

        # Include recent comments in the context for better conversational flow
        if self.previous_comments:
            context += "Recent Comments for Context:\n"
            for prev in self.previous_comments[-3:]: # Include last 3 comments
                context += f"- {prev['comment_text']} by {prev['commenter_name']} ({prev['timestamp']})\n"
            context += "\n"

        # System prompt for the language model, generalized for database input
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

        # Language-specific instruction to guide the LLM's response language
        if comment_language == "bangla":
            language_instruction = "IMPORTANT: The comment is in BANGLA. You MUST reply in BANGLA language only."
        elif comment_language == "english":
            language_instruction = "IMPORTANT: The comment is in ENGLISH. You MUST reply in ENGLISH language only."
        else:
            language_instruction = "IMPORTANT: The comment is mixed language. Reply in the dominant language used in the comment."

        # User prompt combining context, current comment, and language instruction
        user_prompt = f"""Page and Post Information Available:
{context}

Current Comment: "{comment_text}"
Commenter: {comment_info.get('commenter_name', 'Anonymous')}

{language_instruction}

Reply ONLY based on the page and post information above. If the comment asks about anything not mentioned in the information, give a brief polite fallback response. Keep reply under 50 words. Match the language of the comment."""

        # Payload for the API request to the language model
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 150, # Max tokens for the response
            "temperature": 0.4, # Controls randomness of the response
            "top_p": 0.9, # Controls diversity via nucleus sampling
            "frequency_penalty": 0.2, # Penalizes new tokens based on their existing frequency in the text
            "presence_penalty": 0.1 # Penalizes new tokens based on whether they appear in the text so far
        }

        try:
            # Make API call to the language model
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=30)
            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()

            reply = response.json()['choices'][0]['message']['content'].strip()
            response_time = time.time() - start_time

            # Validate the LLM's response and use fallback if validation fails
            if not self.validate_response(reply, comment_text):
                reply = self.get_fallback_response(comment_text, sentiment)

            # Add the current comment to history after processing
            self.add_comment_history({
                **comment_info, # Unpack all comment_info fields
                "post_id": post_id # Add post_id for context
            })

            # Return the generated reply and associated metadata
            return {
                "reply": reply,
                "sentiment": sentiment,
                "response_time": f"{response_time:.2f}s",
                "controlled": self.validate_response(reply, comment_text), # Was the reply controlled/valid?
                "slang_detected": False,
                "comment_id": comment_info.get("comment_id", ""),
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id
            }
        except requests.exceptions.RequestException as e:
            # Handle API call errors gracefully
            response_time = time.time() - start_time
            print(f"API call failed: {e}") # Log the error
            return {
                "reply": self.get_fallback_response(comment_text, sentiment), # Use fallback on API error
                "sentiment": sentiment,
                "response_time": f"{response_time:.2f}s",
                "controlled": True, # Fallback is a controlled response
                "slang_detected": False,
                "comment_id": comment_info.get("comment_id", ""),
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "note": f"Used fallback due to API error: {e}"
            }
        except Exception as e:
            # Catch any other unexpected errors during reply generation
            response_time = time.time() - start_time
            print(f"An unexpected error occurred: {e}") # Log the error
            return {
                "reply": self.get_fallback_response(comment_text, sentiment),
                "sentiment": sentiment,
                "response_time": f"{response_time:.2f}s",
                "controlled": True,
                "slang_detected": False,
                "comment_id": comment_info.get("comment_id", ""),
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "note": f"Used fallback due to unexpected error: {e}"
            }


# Initialize bot instance globally
bot = FacebookBot()

# --- NEW API ENDPOINT FOR SETTING LIMITS ---
@app.route('/set-page-limit', methods=['POST'])
def set_page_limit():
    """
    Endpoint for web developers to set a maximum comment reply limit for a specific page.
    Expected JSON: {"page_id": "your_page_id", "limit": 100}
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "JSON data is required"}), 400

        page_id = data.get("page_id")
        limit = data.get("limit")

        if not page_id:
            return jsonify({"success": False, "message": "page_id is required"}), 400
        if limit is None: # Allow limit to be 0
            return jsonify({"success": False, "message": "limit is required"}), 400

        try:
            limit = int(limit)
            if limit < 0:
                raise ValueError("Limit must be a non-negative integer.")
        except ValueError:
            return jsonify({"success": False, "message": "Limit must be an integer"}), 400

        bot.set_page_limit(page_id, limit)
        return jsonify({
            "success": True,
            "message": f"Comment reply limit for page_id '{page_id}' set to {limit}.",
            "page_id": page_id,
            "limit": limit,
            "current_count": bot.get_comment_count(page_id) # Show current count after setting limit
        }), 200
    except Exception as e:
        print(f"Error in /set-page-limit: {e}")
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

# --- END NEW API ENDPOINT ---


@app.route('/process-comment', methods=['POST'])
def process_comment():
    """
    API endpoint to process comment data received in JSON format from developers' database.
    It validates the input, generates a reply using the bot, and returns a structured JSON response.
    """
    try:
        json_data = request.get_json()

        # Validate if JSON data is provided
        if not json_data:
            return jsonify({
                "success": False,
                "message": "JSON data is required"
            }), 400

        # Validate top-level 'data' field
        if "data" not in json_data:
            return jsonify({
                "success": False,
                "message": "Invalid JSON structure. 'data' field is required"
            }), 400

        data = json_data["data"]

        # Validate 'comment_info' field within 'data'
        if "comment_info" not in data:
            return jsonify({
                "success": False,
                "message": "comment_info is required in data"
            }), 400

        comment_info = data["comment_info"]
        # Validate 'comment_text' within 'comment_info'
        if not comment_info.get("comment_text", "").strip():
            return jsonify({
                "success": False,
                "message": "comment_text is required and cannot be empty"
            }), 400

        # Generate reply
        result = bot.generate_reply(json_data)

        # Handle errors returned by generate_reply or limit reached messages
        if 'error' in result:
            return jsonify({
                "success": False,
                "message": result['error']
            }), 500
        elif "note" in result and "Comment limit reached" in result["note"]:
             # Specific response for limit reached
             return jsonify({
                "success": True, # Still a successful processing, just no AI reply
                "data": {
                    "original_comment": {
                        "comment_id": result.get("comment_id", ""),
                        "comment_text": comment_info.get("comment_text", ""),
                        "commenter_name": result.get("commenter_name", ""),
                        "commenter_id": comment_info.get("commenter_id", "")
                    },
                    "generated_reply": {
                        "reply_text": result['reply'],
                        "sentiment": result['sentiment'],
                        "response_time": result['response_time'],
                        "controlled": result['controlled'],
                        "slang_detected": result['slang_detected'],
                        "status": "Limit Reached - No AI Reply"
                    },
                    "context_info": {
                        "page_name": result.get("page_name", ""),
                        "page_id": result.get("page_id", ""), # Include page_id for clarity
                        "post_id": result.get("post_id", ""),
                        "current_comment_count": bot.get_comment_count(result.get("page_id", "")),
                        "max_comment_limit": bot.get_page_limit(result.get("page_id", ""))
                    },
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                },
                "message": result["note"] # Pass the note as a message
            })


        # Return success response with generated reply and metadata
        return jsonify({
            "success": True,
            "data": {
                "original_comment": {
                    "comment_id": result.get("comment_id", ""),
                    "comment_text": comment_info.get("comment_text", ""),
                    "commenter_name": result.get("commenter_name", ""),
                    "commenter_id": comment_info.get("commenter_id", "")
                },
                "generated_reply": {
                    "reply_text": result['reply'],
                    "sentiment": result['sentiment'],
                    "response_time": result['response_time'],
                    "controlled": result['controlled'],
                    "slang_detected": result['slang_detected'],
                    "status": "AI Reply Generated"
                },
                "context_info": {
                    "page_name": result.get("page_name", ""),
                    "page_id": result.get("page_id", ""), # Include page_id for clarity
                    "post_id": result.get("post_id", ""),
                    "current_comment_count": bot.get_comment_count(result.get("page_id", "")),
                    "max_comment_limit": bot.get_page_limit(result.get("page_id", ""))
                },
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        })

    except Exception as e:
        # Catch any unexpected server errors
        print(f"Server error in /process-comment: {e}") # Log the error
        return jsonify({
            "success": False,
            "message": f"Server error: {str(e)}"
        }), 500


@app.route('/health', methods=['GET'])
def health_check():
    """
    Health check endpoint to verify the API is running.
    """
    return jsonify({
        "success": True,
        "message": "Page Comment Bot API is running (JSON Database Integration)",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": "2.1 - Comment Limiting" # Updated version
    })


@app.route('/test-slang', methods=['POST'])
def test_slang():
    """
    Test endpoint to check the slang detection functionality with a given text.
    """
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
        print(f"Error in /test-slang: {e}") # Log the error
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500


@app.route('/context-info', methods=['GET'])
def get_context_info():
    """
    Endpoint to retrieve current stored conversation context and recent comments.
    Useful for debugging and monitoring the bot's state, including comment counts and limits.
    """
    try:
        page_counts = {}
        for page_id in bot.comment_counts:
            page_counts[page_id] = {
                "current_count": bot.get_comment_count(page_id),
                "max_limit": bot.get_page_limit(page_id)
            }

        return jsonify({
            "success": True,
            "data": {
                "stored_contexts_count": len(bot.conversation_context),
                "recent_comments_count": len(bot.previous_comments),
                "contexts_keys": list(bot.conversation_context.keys())[:10],  # Show first 10 context keys
                "recent_comments_summary": [
                    {"comment_id": c.get("comment_id"), "commenter_name": c.get("commenter_name"), "timestamp": c.get("timestamp")}
                    for c in bot.previous_comments[-5:] # Show summary of last 5 comments
                ],
                "page_comment_stats": page_counts # NEW: Show current comment counts and limits
            }
        })
    except Exception as e:
        print(f"Error in /context-info: {e}") # Log the error
        return jsonify({
            "success": False,
            "message": f"Error: {str(e)}"
        }), 500


if __name__ == "__main__":
    print("🤖 Page Comment Bot API Server Starting...")
    print("📍 Server will run on: http://localhost:6002")
    print("🔗 Available endpoints:")
    print("    POST /process-comment - Process comment from database JSON")
    print("    POST /set-page-limit - Set maximum comment reply limit for a page (NEW)")
    print("    POST /test-slang - Test slang detection")
    print("    GET  /context-info - Get stored context information (includes limits & counts)")
    print("    GET  /health - Health check")
    print("=" * 50)
    print("📋 Expected JSON format for /process-comment:")
    print("""
    {
      "data": {
        "page_info": {
          "page_id": "12345",
          "page_name": "My Business Page"
        },
        "post_info": {
          "post_id": "67890",
          "post_content": "Check out our new product!",
          "post_type": "photo"
        },
        "comment_info": {
          "comment_id": "111213",
          "comment_text": "This looks great!",
          "commenter_name": "John Doe",
          "commenter_id": "456789",
          "parent_comment_id": null
        }
      }
    }
    """)
    print("📋 Expected JSON format for /set-page-limit:")
    print("""
    {
      "page_id": "PAGE_ID_TO_SET_LIMIT_FOR",
      "limit": 50
    }
    """)
    print("=" * 50)
    # Run the Flask application
    app.run(port=6002, debug=True) # debug=True is useful for development, set to False in production