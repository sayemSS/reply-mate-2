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

        # --- IMPORTANT: Define your company name here ---
        self.company_name = "GhorerBazar" # Set your company name here

        # Slang words and patterns (kept as is, assuming current functionality is desired)
        self.slang_words = [
            # Core Bengali abusive terms (most common and offensive)
            "মাগি", "খানি", "চোদা", "চোদি", "চুদি", "চুদা", "রান্ড", "বেশ্যা", "বাঞ্চোত", "মাদারচোদ",
            "বাল", "ছাগল", "কুত্তা", "শুয়োর", "গাধা", "বালের", "চুদিরভাই",

            # Stronger negative/derogatory terms
            "হারামি", "হারামজাদা", "কুত্তার বাচ্চা", "শুওরের বাচ্চা", "গাধার বাচ্চা",
            "বদমাইশ", "নোংরা", "নোংরামি", "ফাউল", "ফাউল্টু", "বেয়াদব", "ছাগলের বাচ্চা", "চোদানির পুত",

            # Common expressions of frustration/annoyance (can be mild to moderate slang)
            "হুদা", "বকবক", "বিরক্তিকর", "ফালতু", "আজেবাজে", "তোর কি", "ধুর", "ভ্যাদাইস", "বাজে",

            # Derogatory terms based on physical/mental state (often used as insults)
            "লেংড়া", "পঙ্গু", "অন্ধ", "বোবা", "কালা", "মোটা", "চিকন", "খোঁড়া", "লুলা", "বোকা", "পাগল", "ছাগল",

            # English explicit words (ensure these are handled with care to avoid false positives)
            "fuck", "fucking", "fucked", "fucker", "fck", "f*ck", "f**k",
            "shit", "bullshit", "sh*t", "s**t", "shyt",
            "bitch", "bitches", "b*tch", "b**ch", "bitch ass",
            "asshole", "a**hole", "arsehole", "ass", "azz",
            "dick", "cock", "penis", "d*ck", "c**k", "dik", "cok",
            "pussy", "vagina", "cunt", "p***y", "c**t", "pusy",
            "slut", "whore", "prostitute", "sl*t", "wh*re", "hore",
            "bastard", "b*stard", "b**tard",
            "dumbass", "stupid", "idiot", "moron", "retard", "dumb", "idiot", "moran",
            "wtf", "stfu", "gtfo", "kys", "lmao", "lmfao", "omfg", "fml",

            # Bengali romanized slang (expanded significantly)
            "magi", "khani", "choda", "chodi", "chudi", "chuda", "rand", "banchot", "madarchod",
            "bal", "chagol", "kutta", "shuyor", "gadha", "baler", "chodirbhai", "codirbhai",

            "harami", "haramjada", "kuttar bacha", "shuorer bacha", "gadhar bacha",
            "badmaish", "nongra", "nongrami", "faul", "faltu", "beyadob", "chagoler bacha", "chodanir put",

            "huda", "bokbok", "biriktikor", "faltu", "ajebaje", "tor ki", "dhur", "vadais", "baje",

            "lengra", "pongu", "ondho", "boba", "kala", "mota", "chikon", "khora", "lula", "boka", "pagol",

            # Mixed language slang (Bengali + English)
            "মাদার চোদ", "ফাক", "শিট", "বিচ", "ড্যাম", "বুলশিট", "ফাকার", "এস হোল", "বালের পোলা",
            "বালের কথা", "কি বাল", "চোদনা", "খানকি মাগি", "চুদানির পুত", "চোদানির বেটা", "ফাকিং",
            "বালছাল", "বাল ফালা", "বাল ছিড়া", "বাল ছিড়ে", "মাগীবাজ", "মাগীবাজি",
            "চোদাচুদি", "চোদান", "চোদান লাগসে", "চুদাচুদি", "চুদিশ", "মাল", "মাল খোর",
            "খানকির পোলা", "খানকির বাচ্চা", "মাগির বাচ্চা", "ফকিরের বাচ্চা", "কুত্তার বাচ্চা",
            "শুয়োরের বাচ্চা", "গাধার বাচ্চা", "হারামির বাচ্চা", "বদমাইশের বাচ্চা", "কুরবানি", "ছাগল",
            "মুড়ি খা", "খাইয়া কাজ নাই", "যা ভাগ", "ভাড়", "গু", "গু-মুত্র", "লেদা", "হাগা",
            "খানকির পোলা", "খানকির বাচ্চা", "মাগির পোলা", "হারামজাদা পোলা",
            "যা বাল", "বাল ফালা", "বাল ছিড়া", "মাদারচোদ", "মাগির পোলা",
            "বালের চুদুর", "কুত্তার বাচ্চা", "হাগা", "হাগিস", "লেদা", "গু"
        ]

        self.slang_patterns = [
            # General repetition patterns for common slang words
            r'f+u+c+k+',  # fuck, fukkk, fukkkk
            r's+h+i+t+',  # shit, shittt
            r'b+i+t+c+h+',  # bitch, bitcch
            r'a+s+s+h+o+l+e+',  # asshole, asshoole

            # Bengali phonetic variations and common misspellings (Romanized)
            r'ch+o+d+a+', r'ch+u+d+a+', r'ch+o+d+i+', r'ch+u+d+i+',  # choda, chudda, chodi, chuddi
            r'm+a+g+i+',  # magi, maagi
            r'k+h+a+n+i+',  # khani, khaani
            r'r+a+n+d+',  # rand, raand
            r'b+a+n+c+h+o+t+',  # banchot, baanchot
            r'h+a+r+a+m+i+', r'h+a+r+a+m+j+a+d+a+',  # harami, haramjada
            r'k+u+t+t+a+',  # kutta, kuttaa
            r's+h+u+o+r+',  # shuor, shuoorr
            r'g+a+d+h+a+',  # gadha, gaadha
            r'b+a+l+',  # bal, baal
            r'b+e+s+h+y+a+',  # beshya, beshyya

            # Bengali phonetic variations (Bengali script)
            r'চো+দা+', r'চু+দা+', r'চো+দি+', r'চু+দি+',
            r'মা+গি+',
            r'খা+নি+',
            r'রা+ন্ড+',
            r'বা+ঞ্চো+ত+',
            r'হা+রা+মি+', r'হা+রা+ম+জা+দা+',
            r'কু+ত্তা+',
            r'শু+য়ো+র+',
            r'গা+ধা+',
            r'বা+ল+',
            r'বে+শ্যা+',

            # Leetspeak and creative spellings (e.g., s_h_i_t, f.u.c.k)
            r'\b(?:f[\W_]*u[\W_]*c[\W_]*k|f[\W_]*u[\W_]*k)\b',  # f_u_c_k, f.u.c.k, fuk
            r'\b(?:s[\W_]*h[\W_]*i[\W_]*t|s[\W_]*h[\W_]*y[\W_]*t)\b',  # s_h_i_t, shyt
            r'\b(?:b[\W_]*i[\W_]*t[\W_]*c[\W_]*h)\b',  # b.i.t.c.h
            r'\b(?:a[\W_]*s[\W_]*s[\W_]*h[\W_]*o[\W_]*l[\W_]*e)\b',  # a.s.s.h.o.l.e

            # Combinations often used in Bengali slang (romanized)
            r'madarchod|motherchod',
            r'baler ?pola|baler ?baccha',
            r'chodir ?bhai|codir ?bhai',
            r'khanir ?pola|khanir ?baccha|khanir ?magi',
            r'magir ?pola|magir ?baccha|magir ?chele',
            r'choda ?chudi|chudachudi',
            r'bal ?falai',
            r'ki ?bal',
            r'guder ?kotha|gu ?kotha',
            r'haga|hagi',
            r'leda',

            # Combinations often used in Bengali slang (Bengali script)
            r'মাদার ?চোদ',
            r'বালের ?পোলা|বালের ?বাচ্চা',
            r'চুদির ?ভাই',
            r'খানকির ?পোলা|খানকির ?বাচ্চা|খানকির ?মাগি',
            r'মাগির ?পোলা|মাগির ?বাচ্চা|মাগির ?ছেলে',
            r'চোদা ?চুদি|চুদাচুদি',
            r'বাল ?ফালাই',
            r'কি ?বাল',
            r'গুদের ?কথা|গু ?কথা',
            r'হাগা|হাগি',
            r'লেদা',

            # Specific common short offensive words that can be problematic
            r'\bgu\b',  # Literally means feces, commonly used as an expletive
            r'\bbal\b',  # Literally means hair, commonly used as an expletive (like "shit" or "damn")
            r'\bmal\b',
            # Can refer to goods, but also used as slang for intoxicants or promiscuous person. Context is key here, but often leans negative.
            r'\bhada\b',  # Slang for something useless or foolish.
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
        # print(f"Comment ID {comment_id} already processed for page {page_id}. Count not incremented.")

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
        This function is crucial for robustness.
        """
        text = text.lower()
        symbol_replacements = {
            '@': 'a', '3': 'e', '1': 'i', '0': 'o', '5': 's',
            '$': 's', '7': 't', '4': 'a', '!': 'i', '*': '',
            '#': '', '%': '', '&': '', '+': '', '=': '',
            '_': ' ', '-': ' ',  # Replace hyphens and underscores with spaces to catch spaced-out slang
            '.': ' ', ',': ' ', ';': ' ', ':': ' ',  # Replace punctuation with spaces
            '(': ' ', ')': ' ', '[': ' ', ']': ' ', '{': ' ', '}': ' ',
            '<': ' ', '>': ' ', '/': ' ', '\\': ' ', '|': ' '
        }
        for symbol, replacement in symbol_replacements.items():
            text = text.replace(symbol, replacement)

        # Normalize multiple spaces into a single space
        text = re.sub(r'\s+', ' ', text).strip()

        # Reduce more than two repetitions of any character (e.g., 'fukkkk' -> 'fukk')
        text = re.sub(r'(.)\1{2,}', r'\1\1', text)

        return text

    def contains_slang(self, text):
        """
        Enhanced slang detection using multiple methods, with refined false positive handling.
        """
        if not text or len(text.strip()) == 0:
            return False

        cleaned = self.clean_text_for_slang(text)
        original_lower = text.lower().strip()

        # First check for common greetings - these should NEVER be flagged as slang
        # Expanded greetings list for more robustness
        greetings = [
            'hello', 'hi', 'hey', 'hellow', 'helo', 'hii', 'hiii', 'hello there',
            'hi there', 'hey there', 'assalamu alaikum', 'salam', 'নমস্কার', 'হ্যালো', 'হাই',
            'আসসালামু আলাইকুম', 'সালাম', 'কেমন আছেন', 'কেমন আছো', 'kemon asen', 'kemon acho'
        ]

        for greeting in greetings:
            # Check for exact greeting or greeting at start/end of sentence, or as a standalone word
            if original_lower == greeting or \
                    original_lower.startswith(greeting + ' ') or \
                    original_lower.endswith(' ' + greeting) or \
                    f" {greeting} " in original_lower:
                return False

        # Common false positive words to avoid (expanded and refined)
        false_positives = {
            'hell': ['hello', 'shell', 'hell-o', 'hellow', 'hello there', 'hell of a', 'what the hell'],
            'ass': ['class', 'pass', 'mass', 'glass', 'grass', 'assistant', 'assalam', 'assalamu', 'assess', 'asset',
                    'compass'],
            'damn': ['adam', 'amsterdam', 'condemn', 'damn it', 'goddamn'],
            'shit': ['shirts', 'shift', 'fitting', 'shipping', 'kshiti', 'bishti'],
            # Added Bengali common word soundalikes
            'fuck': ['lucky', 'pluck'],
            'bitch': ['pitch', 'stitch', 'witch', 'rich'],
            'bal': ['baler', 'balaka', 'football', 'balcony', 'bhalobasa'],  # 'bhalobasa' is common Bengali for love
            'gu': ['gum', 'gulab', 'guitar'],
            'mal': ['malum', 'malik', 'animal', 'formal', 'normal']
        }

        # Method 1: Strict word boundary matching and false positive handling
        for slang in self.slang_words:
            slang_lower = slang.lower()

            # Skip very short problematic words entirely if they are in false_positives keys
            # and their length is too small to differentiate reliably without context
            if slang_lower in ['hell', 'ass', 'bad', 'damn', 'gu', 'bal'] and len(slang_lower) <= 3:
                # For these very short words, we rely more on explicit false_positives checking below.
                # Avoid direct word boundary match if it leads to too many false positives.
                # Continue to other methods.
                continue

            # Check if this slang word has known false positives
            if slang_lower in false_positives:
                pattern = r'\b' + re.escape(slang_lower) + r'\b'
                matches = re.findall(pattern, cleaned) or re.findall(pattern, original_lower)
                if matches:
                    is_false_positive = False
                    for fp_word in false_positives[slang_lower]:
                        # Check if the false positive word is present, or if the slang is part of a larger false positive word
                        if fp_word in original_lower:
                            is_false_positive = True
                            break
                    if not is_false_positive:
                        return True
            else:
                # Normal word boundary check for other slang words that don't have high false positive rates
                pattern = r'\b' + re.escape(slang_lower) + r'\b'
                if re.search(pattern, cleaned) or re.search(pattern, original_lower):
                    return True

        # Method 2: Enhanced Pattern matching for repeated characters, leetspeak, and spaced-out slang
        # This method is now more aggressive after initial false positive filtering.
        for pattern_regex in self.slang_patterns:
            # Check both cleaned and original_lower for robustness
            if re.search(pattern_regex, cleaned, re.IGNORECASE) or \
                    re.search(pattern_regex, original_lower, re.IGNORECASE):
                # Add a sanity check for very short matches to avoid overly aggressive detection if not part of a larger pattern
                # For example, 'hi' matching 'h+i+' might be caught by a pattern, but should be ignored.
                # This requires careful tuning.
                # A better approach here is to ensure the patterns themselves are specific enough.
                return True

        # Method 3: Check for slang with mixed symbols and no spaces (after initial cleaning)
        # The `clean_text_for_slang` already handles symbol replacement.
        # So `cleaned` text should be sufficient for this.
        # This method is less needed if `clean_text_for_slang` is robust, but kept for extra layer.
        no_space_text_cleaned = re.sub(r'\s+', '', cleaned)
        for slang in self.slang_words:
            slang_lower = slang.lower()
            clean_slang_pattern = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', slang_lower)

            # Check if cleaned slang (without symbols) is present in the no-space version of the cleaned text
            if clean_slang_pattern and clean_slang_pattern in no_space_text_cleaned and len(clean_slang_pattern) > 2:
                # Add a length check to avoid single/double character false positives
                # Ensure it's not a common false positive in its non-slang form
                if slang_lower in false_positives:
                    is_false_positive = False
                    for fp_word in false_positives[slang_lower]:
                        if fp_word in original_lower:
                            is_false_positive = True
                            break
                    if not is_false_positive:
                        return True
                else:
                    return True
        return False

    def get_sentiment(self, comment):
        """
        Determines the sentiment of a comment (Positive, Negative, or Neutral)
        based on a predefined list of keywords.
        """
        positive_words = ['ভালো', 'good', 'great', 'excellent', 'love', 'amazing', 'wonderful', 'thanks', 'ধন্যবাদ',
                          'সুন্দর', 'চমৎকার', 'hello', 'hi', 'hey', 'nice', 'awesome', 'খুব ভালো', 'অনেক ভালো', 'দারুন']
        negative_words = ['খারাপ', 'bad', 'terrible', 'awful', 'hate', 'horrible', 'angry', 'disappointed', 'বিরক্ত',
                          'রাগ', 'বাজে', 'জঘন্য', 'সমস্যা', 'বিরক্তিকর']
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
        # The LLM prompt will now focus on generating short replies,
        # so this validation can be less strict or removed if the LLM is well-controlled.
        # Keeping it for an extra layer of safety.
        out_of_scope_indicators = [
            'generally', 'usually', 'typically', 'in most cases',
            'experts say', 'studies show', 'research indicates',
            'you should try', 'i recommend', 'best practice'
        ]
        reply_lower = reply.lower()
        # Check for out-of-scope phrases
        if any(indicator in reply_lower for indicator in out_of_scope_indicators):
            return False
        # The LLM will be instructed to keep replies short, so this check acts as a safeguard.
        if len(reply.split()) > 25: # Reduced to 25 words for even shorter replies
            return False
        return True

    def get_fallback_response(self, comment, sentiment, comment_language):
        """
        Provides a relevant fallback response if the LLM fails or the generated
        reply is invalid. Responses are tailored to sentiment and language.
        These fallback responses are also made shorter.
        """
        import random
        comment_lower = comment.lower()

        # Check for greetings
        if any(word in comment_lower for word in
               ['hello', 'hi', 'hey', 'assalam', 'salam', 'হ্যালো', 'হাই', 'নমস্কার', 'আসসালামু আলাইকুম', 'কেমন আছেন']):
            if comment_language == "bangla":
                return random.choice([
                    "আসসালামু আলাইকুম! কেমন আছেন? 😊",
                    "হ্যালো! স্বাগতম। 👋",
                    "নমস্কার! কী সাহায্য করতে পারি? 🙏"
                ])
            else:  # Defaults to English if not explicitly Bangla
                return random.choice([
                    "Hello! Welcome! 👋",
                    "Hi there! How can we help? 😊",
                    "Hey! Thanks! 🙏"
                ])

        # Check for application/job related keywords
        if any(word in comment_lower for word in ['application', 'apply', 'job', 'আবেদন', 'চাকরি', 'লিখতে', 'নিয়োগ']):
            if comment_language == "bangla":
                return random.choice([
                    "আবেদনের জন্য ইনবক্স করুন।",
                    "আবেদন সংক্রান্ত প্রশ্নে ইনবক্স করুন।",
                    "আবেদন প্রক্রিয়া জানতে যোগাযোগ করুন।"
                ])
            else:
                return random.choice([
                    "Inbox for applications.",
                    "Message us for application queries.",
                    "Contact us for application details."
                ])

        # Fallback based on sentiment
        if sentiment == "Positive":
            if comment_language == "bangla":
                fallbacks = [
                    "ধন্যবাদ! 🙏",
                    "আপনার সাপোর্টের জন্য ধন্যবাদ! ❤️",
                    "অসংখ্য ধন্যবাদ! 😊",
                    "আপনার ভালো লাগলে আমরা আনন্দিত।"
                ]
            else:  # Defaults to English if not explicitly Bangla
                fallbacks = [
                    "Thank you! 😊",
                    "We appreciate your support! ❤️",
                    "Thanks for your feedback! 🙏",
                    "Glad you liked it!"
                ]
        elif sentiment == "Negative":
            if comment_language == "bangla":
                fallbacks = [
                    "দুঃখিত! ইনবক্স করুন।",
                    "আমরা বিষয়টি দেখছি।",
                    "দুঃখিত! যোগাযোগ করুন।",
                    "অসুবিধার জন্য ক্ষমাপ্রার্থী।"
                ]
            else:  # Defaults to English if not explicitly Bangla
                fallbacks = [
                    "Sorry! Please message us.",
                    "We're looking into it.",
                    "Sorry! Contact us.",
                    "Apologies for the trouble."
                ]
        else:  # Neutral sentiment
            if comment_language == "bangla":
                fallbacks = [
                    "ইনবক্স করুন, সাহায্য করবো।",
                    "পণ্য সম্পর্কে জানতে ইনবক্স করুন।",
                    "সরাসরি যোগাযোগ করুন।",
                    "আরো কিছু জানতে চাইলে জিজ্ঞাসা করুন।"
                ]
            else:  # Defaults to English if not explicitly Bangla
                fallbacks = [
                    "Message us for help.",
                    "Inbox to know about products.",
                    "Contact us directly.",
                    "Feel free to ask more."
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
        Updated to extract company name from the website link and make it dynamic.
        """
        website_link = re.search(r'https://(\S+?)\.com/\S*', post_content) # Broader match for website
        whatsapp_number = re.search(r'\+880\d{10}', post_content)
        facebook_group_link = re.search(r'https://www\.facebook\.com/groups/\S*', post_content)

        extracted_company_name = None
        if website_link:
            # Heuristic to get company name from domain, e.g., "ghorerbazar" from "ghorerbazar.com"
            domain = website_link.group(1)
            extracted_company_name = domain.split('.')[-1] if '.' in domain else domain


        return {
            "website": website_link.group(0) if website_link else None,
            "whatsapp": whatsapp_number.group(0) if whatsapp_number else None,
            "facebook_group": facebook_group_link.group(0) if facebook_group_link else None,
            "extracted_company_name": extracted_company_name # Return extracted company name
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
            return {"error": "Comment text is required", "status_code": 400}

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
                reply_status_code = 555  # Custom status for limit reached
                limit_reply = ""  # No reply generated
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
                    "note": f"Comment limit of {provided_comment_limit} reached for this page. Current count: {self.get_comment_count(page_id)}. No reply generated due to limit."
                }

            # Increment count AFTER the limit check, so the current comment is counted for *next* requests
            self.increment_comment_count(page_id, comment_id)

        # --- Slang Detection ---
        slang_detected = self.contains_slang(comment_text)
        if slang_detected:
            reply = ""  # No reply for slang
            sentiment = "Negative" # Assign negative sentiment for slang comments
            note = "Slang detected. No reply generated."
            response_time = f"{time.time() - start_time:.2f}s"
            # Return immediate response if slang is detected
            return {
                "comment_id": comment_id,
                "commenter_name": comment_info.get("commenter_name", ""),
                "controlled": True,
                "input_tokens": 0,  # No LLM call, so 0 input tokens
                "note": note,
                "output_tokens": 0,  # No LLM call, so 0 output tokens
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "reply": reply,
                "response_time": response_time,
                "sentiment": sentiment,
                "slang_detected": True,
                "status_code": 200 # Or a custom status code if preferred for slang, e.g., 204 No Content or 403 Forbidden
            }

        # --- Sentiment and Language Detection ---
        sentiment = self.get_sentiment(comment_text)
        comment_language = self.detect_comment_language(comment_text)
        commenter_name = comment_info.get("commenter_name", "User") # Default to "User" if name is missing

        # Extract contact information
        contact_info = self.extract_contact_info(post_info.get("post_content", ""))
        website_link = contact_info.get("website")
        whatsapp_number = contact_info.get("whatsapp")
        facebook_group_link = contact_info.get("facebook_group")

        # Dynamically get company name. Use the extracted one, or fallback to the pre-defined one.
        # This makes it more robust if the company name appears in the post content.
        # If the domain is just "com" or similar, use the fallback.
        inferred_company_name = contact_info.get("extracted_company_name")
        company_name_to_use = inferred_company_name if inferred_company_name and inferred_company_name != "com" else self.company_name

        # --- Prepare for LLM Request ---
        messages = []

        # System prompt: Crucial for controlling behavior
        system_prompt = f"""
        You are an AI assistant for {company_name_to_use}'s Facebook page.
        Your goal is to provide concise, helpful, and friendly replies to comments.
        Keep replies very short, typically 1-2 sentences, and to the point.
        Address the commenter by their name if available.
        Mention the company name '{company_name_to_use}' naturally if relevant.
        If contact information (website, WhatsApp, Facebook group) is available from the post, suggest visiting or contacting through those channels where appropriate.
        Do NOT generate long paragraphs or elaborate explanations.
        The current date and time is {datetime.now().strftime("%Y-%m-%d %H:%M")}.
        """
        messages.append({"role": "system", "content": system_prompt})

        # Add page and post context
        page_name = page_info.get("page_name", "this page")
        post_content = post_info.get("post_content", "No specific post content available.")

        context_message = f"User is commenting on '{page_name}' about a post with content: '{post_content}'."
        messages.append({"role": "user", "content": context_message})


        # Add previous comments for context (if any)
        context_key = f"{page_id}_{post_id}"
        if context_key in self.previous_comments:
            for prev_comment in self.previous_comments[context_key]:
                messages.append({"role": "user", "content": f"Previous comment from {prev_comment['commenter_name']}: {prev_comment['comment_text']}"})

        # Add the current comment
        current_comment_message = f"The current comment is from {commenter_name}: '{comment_text}'."
        messages.append({"role": "user", "content": current_comment_message})

        # Add specific instructions based on extracted info
        contact_instructions = []
        if website_link:
            contact_instructions.append(f"Our website is: {website_link}")
        if whatsapp_number:
            contact_instructions.append(f"Our WhatsApp contact is: {whatsapp_number}")
        if facebook_group_link:
            contact_instructions.append(f"Our Facebook group is: {facebook_group_link}")

        if contact_instructions:
            messages.append({"role": "user", "content": "Relevant contact information for our company: " + " ".join(contact_instructions) + " Please suggest visiting our website, WhatsApp, or Facebook group if it makes sense."})
        else:
             messages.append({"role": "user", "content": "No specific contact information provided in the post. Generate a polite and concise general reply."})


        # Calculate input tokens before the API call
        input_tokens = self.count_tokens(" ".join([m["content"] for m in messages]))

        # --- Call LLM API ---
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 50,  # Set a low max_tokens to encourage brevity
                "temperature": 0.7,
                "top_p": 0.9,
                "stop": ["\n\n", "Commenter:", "User:"] # Common stop sequences
            }
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            llm_response_json = response.json()
            llm_reply = llm_response_json["choices"][0]["message"]["content"].strip()
            output_tokens = self.count_tokens(llm_reply)

            # Post-process LLM reply
            # Ensure the reply doesn't start with the commenter's name if already addressed in the prompt
            if commenter_name.lower() in llm_reply.lower() and llm_reply.lower().startswith(commenter_name.lower()):
                llm_reply = re.sub(r"^\s*" + re.escape(commenter_name) + r"[\s,.:;]*", "", llm_reply, flags=re.IGNORECASE).strip()
                if llm_reply.startswith("!"): # Remove leading exclamation if it resulted from stripping
                    llm_reply = llm_reply[1:].strip()


            # Validate LLM response
            if not self.validate_response(llm_reply, comment_text):
                # Fallback if LLM generated an invalid response despite instructions
                reply = self.get_fallback_response(comment_text, sentiment, comment_language)
                note = "LLM generated an invalid response, using fallback."
                controlled_status = True
            else:
                reply = llm_reply
                note = ""
                controlled_status = False

        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            reply = self.get_fallback_response(comment_text, sentiment, comment_language)
            note = f"API request failed: {e}. Using fallback."
            controlled_status = True
            output_tokens = 0 # No output tokens if API call failed
        except KeyError as e:
            print(f"Failed to parse LLM response: {e}. Response: {llm_response_json}")
            reply = self.get_fallback_response(comment_text, sentiment, comment_language)
            note = f"Failed to parse LLM response: {e}. Using fallback."
            controlled_status = True
            output_tokens = 0 # No output tokens if parsing failed
        except Exception as e:
            print(f"An unexpected error occurred during LLM reply generation: {e}")
            reply = self.get_fallback_response(comment_text, sentiment, comment_language)
            note = f"Unexpected error: {e}. Using fallback."
            controlled_status = True
            output_tokens = 0 # No output tokens if an unexpected error occurred

        # Add comment to history after successful processing or fallback
        self.add_comment_history(page_id, post_id, comment_info)

        response_time = f"{time.time() - start_time:.2f}s"

        return {
            "comment_id": comment_id,
            "commenter_name": commenter_name,
            "controlled": controlled_status,
            "input_tokens": input_tokens,
            "note": note,
            "output_tokens": output_tokens,
            "page_name": page_info.get("page_name", ""),
            "post_id": post_id,
            "reply": reply,
            "response_time": response_time,
            "sentiment": sentiment,
            "slang_detected": slang_detected,
            "status_code": reply_status_code
        }
@app.route('/',methods=['GET'])
def display():
    return 'welcome'

@app.route('/process-comment', methods=['POST'])
def process_comment():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400

    bot = FacebookBot()
    response = bot.generate_reply(data)
    return jsonify(response), response.get("status_code", 200)

if __name__ == '__main__':
    # For local development, load from .env and run
    # Ensure OPENAI_API_KEY is set in your .env file
    if os.getenv("OPENAI_API_KEY") is None:
        print("Error: OPENAI_API_KEY environment variable not set. Please set it in a .env file or your system environment.")
    else:
        app.run(debug=True,host="0.0.0.0",port=5000)