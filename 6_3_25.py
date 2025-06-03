from flask import Flask, request, jsonify
import os
import re
import requests
import time
from datetime import datetime
from dotenv import load_dotenv
import tiktoken  # Library for token counting

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)


class FacebookBot:
    def __init__(self):
        # Retrieve API key from environment variables
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.model = "gpt-4o-mini"  # Using the specified model for response generation

        # Ensure API key is present
        if not self.api_key:
            raise Exception("OPENAI_API_KEY not found in .env file")

        # Headers for API requests
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Initialize the tokenizer for the chosen model
        try:
            self.tokenizer = tiktoken.encoding_for_model(self.model)
        except KeyError:
            print(f"Warning: Model '{self.model}' not found for tiktoken. Using cl100k_base.")
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

        # Store conversation context for each page and post
        self.conversation_context = {}
        # Store recent comments for conversational flow
        self.previous_comments = {}  # Changed to dictionary to store history per page_id_post_id

        # Stores the current comment count for each page_id
        # Example: {"page_id_1": 45, "page_id_2": 20}
        self.comment_counts = {}

        # Slang words and patterns
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

        self.slang_patterns = [
            r'f+u+c+k+i*n*g*',
            r's+h+i+t+',
            r'b+i+t+c+h+',
            r'চো+দা+',
            r'মা+গি+',
            r'খা+নি+',
            r'হা+রা+মি+',
        ]
        # Keep track of processed comment IDs to avoid incrementing count for duplicate requests
        self.processed_comment_ids = set()

    # --- Token Counting Method ---
    def count_tokens(self, text):
        """Counts the number of tokens in a given text using the initialized tokenizer."""
        if not text:
            return 0
        return len(self.tokenizer.encode(text))

    # --- Methods for Comment Limiting ---
    def set_page_limit(self, page_id, limit):
        """
        Sets the maximum comment reply limit for a specific page.
        (This method is now less critical as the limit is expected in the /process-comment payload,
        but can be used for manual overrides or initial setup if needed).
        """
        if not isinstance(limit, int) or limit < 0:
            raise ValueError("Limit must be a non-negative integer.")
        return True

    def get_page_limit(self, page_id):
        """
        Gets the maximum comment reply limit for a specific page.
        (Less relevant for the new flow).
        """
        return -1  # Always return -1 as the limit is expected from the payload now

    def increment_comment_count(self, page_id, comment_id):
        """Increments the comment count for a given page, ensuring each unique comment_id is counted only once."""
        if comment_id not in self.processed_comment_ids:
            self.comment_counts[page_id] = self.comment_counts.get(page_id, 0) + 1
            self.processed_comment_ids.add(comment_id)
        # else:
        #     print(f"Comment ID {comment_id} already processed for page {page_id}. Count not incremented.")

    def get_comment_count(self, page_id):
        """Gets the current comment count for a given page."""
        return self.comment_counts.get(page_id, 0)

    def is_limit_reached(self, page_id, provided_max_limit):
        """
        Checks if the comment limit has been reached for a given page,
        using the limit provided in the incoming data.
        """
        # If no limit is provided or it's -1, limit is never reached
        if provided_max_limit is None or provided_max_limit == -1:
            return False
        current_count = self.get_comment_count(page_id)
        return current_count >= provided_max_limit

    # --- Context and History Management ---
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

    def add_comment_history(self, page_id, post_id, comment_data):
        """
        Add a comment to the history for a specific page and post for contextual understanding
        in subsequent replies. Keeps only the last 10 comments to manage memory usage.
        """
        context_key = f"{page_id}_{post_id}"
        if context_key not in self.previous_comments:
            self.previous_comments[context_key] = []

        self.previous_comments[context_key].append({
            "comment_id": comment_data.get("comment_id", ""),
            "comment_text": comment_data.get("comment_text", ""),
            "commenter_name": comment_data.get("commenter_name", ""),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        # Keep only last 10 comments for context for this specific page_post
        if len(self.previous_comments[context_key]) > 10:
            self.previous_comments[context_key].pop(0)

    # --- Slang and Sentiment Detection ---
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
        text = re.sub(r'[.!?]{2,}', '.', text)  # Normalize multiple punctuation marks
        text = re.sub(r'[-_]{2,}', ' ', text)  # Replace multiple hyphens/underscores with space
        text = re.sub(r'(.)\1{2,}', r'\1\1', text)  # Reduce more than two repetitions of any character
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
                        if fp_word in original_lower:  # Check if the false positive word is present
                            is_false_positive = True
                            break
                    if not is_false_positive:  # If it's not a false positive, then it's slang
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
        spaced_text = re.sub(r'\s+', '', cleaned)  # Remove all spaces
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

    def get_fallback_response(self, comment, sentiment, comment_language):
        """
        Provides a relevant fallback response if the LLM fails or the generated
        reply is invalid. Responses are tailored to sentiment and language.
        """
        import random
        comment_lower = comment.lower()

        # Check for greetings
        if any(word in comment_lower for word in
               ['hello', 'hi', 'hey', 'assalam', 'salam', 'হ্যালো', 'হাই', 'নমস্কার']):
            if comment_language == "bangla":
                return random.choice([
                    "আসসালামু আলাইকুম! কেমন আছেন? 😊",
                    "হ্যালো! আপনাকে স্বাগতম। 👋",
                    "নমস্কার! কী সাহায্য করতে পারি? 🙏"
                ])
            else:  # Defaults to English if not explicitly Bangla
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
            else:  # Defaults to English if not explicitly Bangla
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
            else:  # Defaults to English if not explicitly Bangla
                fallbacks = [
                    "Sorry for any inconvenience. Please message us for details.",
                    "We'll look into this matter and get back to you.",
                    "Sorry! Please contact us for more information."
                ]
        else:  # Neutral sentiment
            if comment_language == "bangla":
                fallbacks = [
                    "আমাদের পেজ সম্পর্কিত কোনো প্রশ্ন থাকলে ইনবক্সে মেসেজ করুন, আমরা সাহায্য করবো।",
                    "আমাদের সেবা বা পণ্য সম্পর্কে জানতে ইনবক্সে যোগাযোগ করুন।",
                    "আপনার প্রশ্নের উত্তর পেতে দয়া করে আমাদের সাথে সরাসরি যোগাযোগ করুন।"
                ]
            else:  # Defaults to English if not explicitly Bangla
                fallbacks = [
                    "For any questions about our page, please message us in inbox. We'll help you.",
                    "To know about our services or products, please contact us via inbox.",
                    "For answers to your questions, please contact us directly."
                ]
        return random.choice(fallbacks)

    def detect_comment_language(self, comment):
        """
        Detects if a comment is primarily in Bangla or English by counting character sets.
        Returns "bangla", "english", or "mixed".
        """
        bangla_chars = re.findall(r'[\u0980-\u09FF]', comment)  # Unicode range for Bengali characters
        english_chars = re.findall(r'[a-zA-Z]', comment)  # English alphabet characters

        bangla_count = len(bangla_chars)
        english_count = len(english_chars)

        if bangla_count > english_count * 0.5:  # More lenient for Bangla if some English present
            return "bangla"
        elif english_count > bangla_count * 0.5:  # More lenient for English if some Bangla present
            return "english"
        else:
            return "mixed"  # If counts are roughly equal or both are low, treat as mixed or unknown

    def extract_contact_info(self, post_content):
        """
        Extracts website link, WhatsApp number, and Facebook group link from post content.
        """
        website_link = re.search(r'https://ghorerbazar\.com/\S+', post_content)
        whatsapp_number = re.search(r'\+880\d{10}', post_content)
        facebook_group_link = re.search(r'https://www\.facebook\.com/groups/\S+', post_content)

        return {
            "website": website_link.group(0) if website_link else None,
            "whatsapp": whatsapp_number.group(0) if whatsapp_number else None,
            "facebook_group": facebook_group_link.group(0) if facebook_group_link else None
        }

    def generate_reply(self, json_data):
        """
        Generates a reply to a comment based on the provided JSON data.
        It first checks for slang, then determines sentiment and language,
        builds a context for the LLM, and finally generates a controlled reply.
        Includes token counting for the LLM response.
        """
        start_time = time.time()
        reply_status_code = 200  # Default status code for OK

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
        comment_id = comment_info.get("comment_id", "")

        # --- Get comment limit directly from incoming page_info ---
        provided_comment_limit = page_info.get("comment limit")  # Accessing "comment limit" key
        if provided_comment_limit is not None:
            try:
                provided_comment_limit = int(provided_comment_limit)
            except ValueError:
                print(f"Warning: 'comment limit' for page {page_id} is not an integer. Treating as no limit (-1).")
                provided_comment_limit = -1  # Treat as no limit if not an integer
        else:
            provided_comment_limit = -1  # Default to no limit if not provided

        # --- Check and apply comment limits using the provided limit ---
        if page_id:  # Only apply limit if page_id is available
            # Check limit BEFORE incrementing count for the current comment
            if self.is_limit_reached(page_id, provided_comment_limit):
                print(f"Comment limit reached for page_id: {page_id}. No reply generated.")
                reply_status_code = 555 # Post off-topic due to limit reached
                limit_reply = "Your comment limit is over. Please try again later."
                return {
                    "reply": limit_reply,
                    "sentiment": "Neutral",
                    "response_time": f"{time.time() - start_time:.2f}s",
                    "controlled": True,
                    "slang_detected": False,
                    "comment_id": comment_id,
                    "commenter_name": comment_info.get("commenter_name", ""),
                    "page_name": page_info.get("page_name", ""),
                    "post_id": post_id,
                    "note": f"Comment limit of {provided_comment_limit} reached for this page. Current count: {self.get_comment_count(page_id)}.",
                    "status_code": reply_status_code, # Add status code
                    "output_tokens": self.count_tokens(limit_reply) # Token count for limit message
                }
            else:
                # Increment count only if limit is NOT reached and this comment_id hasn't been processed before
                self.increment_comment_count(page_id, comment_id)  # Pass comment_id for unique tracking
        # --- END Comment Limiting ---

        if page_id and post_id:
            self.store_conversation_context(page_id, post_id, page_info, post_info)

        # Check for slang FIRST and return a predefined response if detected
        if self.contains_slang(comment_text):
            response_time = time.time() - start_time
            # Get comment language to ensure slang response matches language
            comment_language_for_slang = self.detect_comment_language(comment_text)
            slang_reply = self.get_slang_response()
            reply_status_code = 444 # Slang detected
            return {
                "reply": slang_reply,
                "sentiment": "Inappropriate",
                "response_time": f"{response_time:.2f}s",
                "controlled": True,  # Indicates a controlled, predefined response
                "slang_detected": True,
                "comment_id": comment_id,
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "output_tokens": self.count_tokens(slang_reply),  # Token count for slang response
                "status_code": reply_status_code # Add status code
            }

        # If no slang detected, proceed with normal processing
        comment_language = self.detect_comment_language(comment_text)
        sentiment = self.get_sentiment(comment_text)

        # Extract contact information from the post content
        contact_info = self.extract_contact_info(post_info.get("post_content", ""))
        website_link = contact_info["website"]
        whatsapp_number = contact_info["whatsapp"]
        facebook_group_link = contact_info["facebook_group"]

        # Build context string for the LLM from the JSON data
        context = f"Page Name: {page_info.get('page_name', 'Unknown')} (ID: {page_id})\n"
        context += f"Post Content: {post_info.get('post_content', 'No content available')}\n"
        context += f"Post Type: {post_info.get('post_type', 'Unknown')}\n"
        if website_link:
            context += f"Website Link: {website_link}\n"
        if whatsapp_number:
            context += f"WhatsApp Number: {whatsapp_number}\n"
        if facebook_group_link:
            context += f"Facebook Group: {facebook_group_link}\n"
        context += "\n"

        # Include recent comments in the context for better conversational flow (specific to page_id_post_id)
        context_key = f"{page_id}_{post_id}"
        if context_key in self.previous_comments and self.previous_comments[context_key]:
            context += "Recent Comments for Context:\n"
            for prev in self.previous_comments[context_key][-3:]:  # Include last 3 comments for this specific page_post
                context += f"- {prev['comment_text']} by {prev['commenter_name']} ({prev['timestamp']})\n"
            context += "\n"

        # System prompt for the language model, generalized for database input
        system_prompt = f"""You are a page manager for Ghorer Bazar. Your primary goal is to provide helpful and concise replies.

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
    - If comment is mixed, use the dominant language or a neutral blend if unsure.
8. Use a natural, conversational tone.
9. **CRITICAL:** If the comment asks about how to order, pricing, availability, or any other query that directly relates to purchasing or getting more information about the product, you **MUST** include the relevant contact information (website link, WhatsApp number, or Facebook group link) from the post content. Prioritize the website link for orders, and WhatsApp for queries from abroad.

RESPONSE STYLE:
- Positive comments: Thank briefly.
- Questions: Answer ONLY if info exists in the provided page/post details.
- Complaints: Apologize briefly, offer to help via message.
- General queries: Redirect to "contact us" if no specific information is available."""

        # Language-specific instruction to guide the LLM's response language
        if comment_language == "bangla":
            language_instruction = "IMPORTANT: The comment is in BANGLA. You MUST reply in BANGLA language only. Do NOT use English."
        elif comment_language == "english":
            language_instruction = "IMPORTANT: The comment is in ENGLISH. You MUST reply in ENGLISH language only. Do NOT use Bangla."
        else:  # Mixed or unknown language
            language_instruction = "IMPORTANT: The comment is mixed language. Reply in the dominant language or a neutral blend, prioritizing clarity."

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
            "max_tokens": 150,  # Max tokens for the response
            "temperature": 0.4,  # Controls randomness of the response
            "top_p": 0.9,  # Controls diversity via nucleus sampling
            "frequency_penalty": 0.2,  # Penalizes new tokens based on their existing frequency in the text
            "presence_penalty": 0.1  # Penalizes new tokens based on whether they appear in the text so far
        }

        try:
            # Make API call to the language model
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=30)
            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()

            reply = response.json()['choices'][0]['message']['content'].strip()
            response_time = time.time() - start_time

            # Count tokens for the generated reply
            output_tokens = self.count_tokens(reply)

            # Validate the LLM's response and use fallback if validation fails
            if not self.validate_response(reply, comment_text):
                fallback_reply = self.get_fallback_response(comment_text, sentiment, comment_language)
                fallback_tokens = self.count_tokens(fallback_reply)
                reply = fallback_reply
                output_tokens = fallback_tokens  # Update token count for fallback
                controlled_status = True
                reply_status_code = 555 # Post off-topic (due to invalid LLM reply, leading to fallback)
            else:
                controlled_status = False # LLM response was valid
                reply_status_code = 200 # OK

            # --- Post-processing: Ensure contact info is included if relevant ---
            comment_lower = comment_text.lower()
            keywords_for_contact = ['how to order', 'buy', 'price', 'দাম', 'কিভাবে পাবো', 'কোথায় পাবো', 'যোগাযোগ',
                                    'whatsapp', 'website', 'লিংক', 'number', 'প্রি-অর্ডার', 'pre-order', 'কিনতে',
                                    'order', 'যোগাযোগ']

            should_add_contact = any(keyword in comment_lower for keyword in keywords_for_contact)

            # Add relevant contact info to the reply if needed
            if should_add_contact:
                contact_parts = []
                if website_link:
                    contact_parts.append(f"ওয়েবসাইট: {website_link}" if comment_language == "bangla" else f"Website: {website_link}")
                if whatsapp_number:
                    contact_parts.append(f"WhatsApp: {whatsapp_number}")
                if facebook_group_link:
                    contact_parts.append(f"Facebook Group: {facebook_group_link}")

                if contact_parts:
                    if comment_language == "bangla":
                        reply += "\nবিস্তারিত জানতে বা অর্ডার করতে যোগাযোগ করুন: " + ", ".join(contact_parts) + "।"
                    else:
                        reply += "\nFor more details or to order, please contact us: " + ", ".join(contact_parts) + "."
                    output_tokens = self.count_tokens(reply) # Re-count tokens after adding contact info

            # Add the current comment to history only if a reply was generated (not for slang or limit reached)
            if reply_status_code != 444 and reply_status_code != 555: # Don't add if slang or limit reached
                self.add_comment_history(page_id, post_id, comment_info)

            return {
                "reply": reply,
                "sentiment": sentiment,
                "response_time": f"{response_time:.2f}s",
                "controlled": controlled_status,
                "slang_detected": False, # No slang detected as it was handled earlier
                "comment_id": comment_id,
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "output_tokens": output_tokens,
                "status_code": reply_status_code # Add status code
            }

        except requests.exceptions.RequestException as e:
            print(f"Error calling OpenAI API: {e}")
            response_time = time.time() - start_time
            fallback_reply = self.get_fallback_response(comment_text, sentiment, comment_language)
            fallback_tokens = self.count_tokens(fallback_reply)
            reply_status_code = 555 # Post off-topic (due to API error, leading to fallback)
            return {
                "reply": fallback_reply,
                "sentiment": "Neutral",
                "response_time": f"{response_time:.2f}s",
                "controlled": True,  # Fallback is a controlled response
                "slang_detected": False,
                "comment_id": comment_id,
                "commenter_name": comment_info.get("commenter_name", ""),
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "output_tokens": fallback_tokens,
                "error": str(e),
                "status_code": reply_status_code # Add status code
            }


# Example usage (Flask routes for webhook and processing comments)
bot = FacebookBot()

@app.route('/webhook', methods=['GET'])
def webhook():
    """Webhook for Facebook Messenger platform setup."""
    challenge = request.args.get('hub.challenge')
    return challenge

@app.route('/process-comment', methods=['POST'])
def process_comment():
    """Endpoint to process incoming comment data and generate replies."""
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON data"}), 400

    reply_data = bot.generate_reply(data)
    # Return the generated reply and other info
    return jsonify(reply_data), reply_data.get("status_code", 200) # Use the status code from reply_data


if __name__ == '__main__':
    # For local development, load environment variables from .env
    load_dotenv()
    # Run the Flask app
    app.run(debug=True, port=os.getenv("PORT", 5000))