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
        # Retrieve API key from environment variables (can use OPENAI_API_KEY for OpenRouter too)
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"  # Back to OpenRouter
        self.model = "openai/gpt-4o-mini"  # Using gpt-4o-mini via OpenRouter (cheaper)

        # Ensure API key is present
        if not self.api_key:
            raise Exception("API key not found. Please set OPENAI_API_KEY or OPENROUTER_API_KEY in .env file")

        print(f"Initialized FacebookBot with model: {self.model} via OpenRouter")

        # Test slang detection with known offensive words
        test_words = ["খানকির পোলা", "মাগির বাচ্চা", "আসসালামু আলাইকুম", "ভালো আছি"]
        print("Testing slang detection:")
        for word in test_words:
            result = self.contains_slang(word)
            print(f"  '{word}' -> {'SLANG' if result else 'CLEAN'}")

        # Headers for API requests - Updated for OpenRouter
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/yourusername/facebook-bot",  # Optional: your app URL
            "X-Title": "Facebook Comment Bot"  # Optional: your app name
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
        self.company_name = "GhorerBazar"  # Set your company name here

        # Slang words and patterns - Only truly offensive content
        self.slang_words = [
            # Core Bengali abusive terms (most common and offensive)
            "মাগি", "খানি", "চোদা", "চোদি", "চুদি", "চুদা", "রান্ড", "বেশ্যা", "বাঞ্চোত", "মাদারচোদ",
            "বাল", "ছাগল", "কুত্তা", "শুয়োর", "গাধা", "বালের", "চুদিরভাই", "খানকি", "খানকির","চোদ","চোদনা","চোদন","বাইঞ্চোদ","মদনা"

            # Stronger negative/derogatory terms
            "হারামি", "হারামজাদা", "কুত্তার বাচ্চা", "শুওরের বাচ্চা", "গাধার বাচ্চা",
            "বদমাইশ", "নোংরা", "নোংরামি", "ফাউল", "ফাউল্টু", "বেয়াদব", "ছাগলের বাচ্চা", "চোদানির পুত",
            "খানকির পোলা", "খানকির বাচ্চা", "মাগির পোলা", "মাগির বাচ্চা", "বালের পোলা", "বালের বাচ্চা",

            # Common offensive combinations
            "পোলা", "বাচ্চা", "ছেলে", "মেয়ে"  # When combined with slang words

            # Removed legitimate feedback words: "বিরক্তিকর", "ফালতু", "আজেবাজে", "বাজে" 
            # These are legitimate criticism, not slang
                                      "হুদা", "বকবক", "তোর কি", "ধুর", "ভ্যাদাইস",

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
            "khankir", "khankir pola", "khankir baccha",

            "harami", "haramjada", "kuttar bacha", "shuorer bacha", "gadhar bacha",
            "badmaish", "nongra", "nongrami", "faul", "faltu", "beyadob", "chagoler bacha", "chodanir put",
            "magir pola", "magir baccha", "baler pola", "baler baccha",

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
            "হারামজাদা পোলা", "যা বাল", "বাল ফালা", "বাল ছিড়া", "মাদারচোদ", "মাগির পোলা",
            "বালের চুদুর", "হাগা", "হাগিস", "লেদা", "গু"
        ]

        self.slang_patterns = [
            # Only truly offensive patterns - removed overly broad ones
            r'f+u+c+k+',  # fuck, fukkk, fukkkk
            r'b+i+t+c+h+',  # bitch, bitcch
            r'a+s+s+h+o+l+e+',  # asshole, asshoole

            # Bengali phonetic variations - only truly offensive
            r'ch+o+d+a+', r'ch+u+d+a+', r'ch+o+d+i+', r'ch+u+d+i+',  # choda, chuda variations
            r'm+a+g+i+',  # magi variations
            r'r+a+n+d+',  # rand variations
            r'b+a+n+c+h+o+t+',  # banchot variations
            r'h+a+r+a+m+i+', r'h+a+r+a+m+j+a+d+a+',  # harami, haramjada
            r'b+e+s+h+y+a+',  # beshya variations

            # Bengali script variations - only truly offensive
            r'চো+দা+', r'চু+দা+', r'চো+দি+', r'চু+দি+',
            r'মা+গি+',
            r'রা+ন্ড+',
            r'বা+ঞ্চো+ত+',
            r'হা+রা+মি+', r'হা+রা+ম+জা+দা+',
            r'বে+শ্যা+',

            # Leetspeak and creative spellings - only for clear offensive words
            r'\b(?:f[\W_]*u[\W_]*c[\W_]*k|f[\W_]*u[\W_]*k)\b',  # f_u_c_k, f.u.c.k, fuk
            r'\b(?:b[\W_]*i[\W_]*t[\W_]*c[\W_]*h)\b',  # b.i.t.c.h

            # Clear offensive combinations - Updated with more comprehensive patterns
            r'খানকির ?\w*', r'মাগির ?\w*', r'বালের ?\w*', r'চোদানির ?\w*', r'হারামির ?\w*',
            r'khankir ?\w*', r'magir ?\w*', r'baler ?\w*', r'chodanir ?\w*', r'haramir ?\w*',
            r'madarchod|motherchod',
            r'chodir ?bhai|codir ?bhai',
            r'khanir ?pola|khanir ?baccha|khanir ?magi',
            r'magir ?pola|magir ?baccha|magir ?chele',
            r'choda ?chudi|chudachudi',

            # Bengali script offensive combinations - More comprehensive
            r'খানকির ?\w*', r'মাগির ?\w*', r'বালের ?\w*', r'চোদানির ?\w*',
            r'মাদার ?চোদ',
            r'চুদির ?ভাই',
            r'খানকির ?পোলা|খানকির ?বাচ্চা|খানকির ?মাগি',
            r'মাগির ?পোলা|মাগির ?বাচ্চা|মাগির ?ছেলে',
            r'চোদা ?চুদি|চুদাচুদি'
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
        Enhanced slang detection - focused on truly offensive content with better detection.
        """
        if not text or len(text.strip()) == 0:
            return False

        cleaned = self.clean_text_for_slang(text)
        original_lower = text.lower().strip()

        print(f"Checking for slang in: '{text}'")  # Debug log
        print(f"Cleaned text: '{cleaned}'")  # Debug log

        # Comprehensive greetings list - these should NEVER be flagged as slang
        greetings = [
            'hello', 'hi', 'hey', 'hellow', 'helo', 'hii', 'hiii', 'hello there',
            'hi there', 'hey there', 'assalamu alaikum', 'assalamualaikum', 'salam',
            'walaikum assalam', 'walaikumsalam', 'স্বাগতম', 'নমস্কার', 'হ্যালো', 'হাই',
            'আসসালামু আলাইকুম', 'আসসালামুয়ালাইকুম', 'ওয়ালাইকুম সালাম',
            'ওয়ালাইকুমুসসালাম', 'সালাম', 'কেমন আছেন', 'কেমন আছো', 'কেমন আছ',
            'kemon asen', 'kemon acho', 'kemon achen', 'ki obostha', 'ki khobor',
            'good morning', 'good afternoon', 'good evening', 'good night',
            'শুভ সকাল', 'শুভ দুপুর', 'শুভ সন্ধ্যা', 'শুভ রাত্রি'
        ]

        # Check for greetings first
        for greeting in greetings:
            if original_lower == greeting or \
                    original_lower.startswith(greeting + ' ') or \
                    original_lower.endswith(' ' + greeting) or \
                    f" {greeting} " in original_lower or \
                    original_lower.startswith(greeting + ',') or \
                    original_lower.startswith(greeting + '!'):
                print(f"Greeting detected: '{greeting}', skipping slang check")
                return False

        # Legitimate feedback words that should NOT be considered slang
        legitimate_feedback = [
            'বাজে', 'খারাপ', 'ভালো না', 'পছন্দ না', 'দাম বেশি', 'expensive', 'costly',
            'বিরক্তিকর', 'ফালতু', 'আজেবাজে', 'bad', 'poor', 'terrible', 'awful',
            'disappointed', 'not good', 'not satisfied', 'সন্তুষ্ট না', 'মন্দ',
            'দেরি', 'late', 'slow', 'ধীর', 'সমস্যা', 'problem', 'issue'
        ]

        # If comment contains only legitimate feedback words, don't flag as slang
        for feedback_word in legitimate_feedback:
            if feedback_word in original_lower and not any(
                    slang in original_lower for slang in ['মাগি', 'চোদা', 'ফাক', 'বিচ']):
                # Check if it's ONLY legitimate criticism without actual slang
                has_real_slang = False
                for truly_offensive in ['মাগি', 'চোদা', 'চুদা', 'বেশ্যা', 'মাদারচোদ', 'fuck', 'bitch', 'shit']:
                    if truly_offensive in original_lower or truly_offensive in cleaned:
                        has_real_slang = True
                        break
                if not has_real_slang:
                    continue  # Don't return False yet, check for actual slang

        # Common false positive words to avoid (expanded and refined)
        false_positives = {
            'hell': ['hello', 'shell', 'hell-o', 'hellow', 'hello there'],
            'ass': ['class', 'pass', 'mass', 'glass', 'grass', 'assistant', 'assalam', 'assalamu', 'assess', 'asset'],
            'damn': ['adam', 'amsterdam', 'condemn'],
            'shit': ['shirts', 'shift', 'fitting', 'shipping'],
            'fuck': ['lucky', 'pluck'],
            'bitch': ['pitch', 'stitch', 'witch', 'rich'],
            'bal': ['football', 'balcony', 'bhalobasa', 'global', 'tribal'],
            'gu': ['gum', 'gulab', 'guitar', 'regular', 'singular'],
            'mal': ['malum', 'malik', 'animal', 'formal', 'normal', 'thermal']
        }

        # Method 1: Check for truly offensive words and combinations
        truly_offensive_words = [
            "মাগি", "খানি", "চোদা", "চোদি", "চুদি", "চুদা", "রান্ড", "বেশ্যা", "বাঞ্চোত", "মাদারচোদ",
            "হারামি", "হারামজাদা", "কুত্তার বাচ্চা", "শুওরের বাচ্চা", "গাধার বাচ্চা",
            "চোদানির পুত", "খানকির পোলা", "খানকির বাচ্চা", "মাগির বাচ্চা", "মাগির পোলা",
            "বালের পোলা", "বালের বাচ্চা", "খানকি", "খানকির",
            # English truly offensive
            "fuck", "fucking", "fucker", "motherfucker", "bitch", "whore", "slut", "cunt",
            # Romanized truly offensive
            "magi", "choda", "chudi", "madarchod", "harami", "rand", "khankir pola", "khankir baccha"
        ]

        # Check for exact matches or word boundary matches
        for offensive_word in truly_offensive_words:
            offensive_lower = offensive_word.lower()

            # For multi-word phrases, check if the full phrase exists
            if ' ' in offensive_word:
                if offensive_lower in original_lower or offensive_lower in cleaned:
                    print(f"Slang detected: '{offensive_word}' found in comment")
                    return True
            else:
                # Check if this word has known false positives
                if offensive_lower in false_positives:
                    pattern = r'\b' + re.escape(offensive_lower) + r'\b'
                    matches = re.findall(pattern, cleaned) or re.findall(pattern, original_lower)
                    if matches:
                        is_false_positive = False
                        for fp_word in false_positives[offensive_lower]:
                            if fp_word in original_lower:
                                is_false_positive = True
                                break
                        if not is_false_positive:
                            print(f"Slang detected: '{offensive_word}' found in comment")
                            return True
                else:
                    # Normal word boundary check for truly offensive words
                    pattern = r'\b' + re.escape(offensive_lower) + r'\b'
                    if re.search(pattern, cleaned) or re.search(pattern, original_lower):
                        print(f"Slang detected: '{offensive_word}' found in comment")
                        return True

        # Method 2: Check for offensive combinations (like "খানকির + পোলা")
        offensive_combinations = [
            ["খানকির", "পোলা"], ["খানকির", "বাচ্চা"], ["মাগির", "পোলা"], ["মাগির", "বাচ্চা"],
            ["বালের", "পোলা"], ["বালের", "বাচ্চা"], ["চোদানির", "পুত"], ["হারামির", "বাচ্চা"],
            ["khankir", "pola"], ["khankir", "baccha"], ["magir", "pola"], ["magir", "baccha"]
        ]

        for combo in offensive_combinations:
            # Check if both parts of the combination exist in the text
            if all(part.lower() in original_lower or part.lower() in cleaned for part in combo):
                print(f"Slang detected: Offensive combination '{' '.join(combo)}' found in comment")
                return True

        # Method 3: Pattern matching for clear offensive patterns
        offensive_patterns = [
            r'f+u+c+k+',  # fuck variations
            r'b+i+t+c+h+',  # bitch variations
            r'ch+o+d+a+', r'ch+u+d+a+',  # choda, chuda variations
            r'm+a+g+i+',  # magi variations
            # Clear offensive combinations - Updated with more comprehensive patterns
            r'খানকির ?\w*', r'মাগির ?\w*', r'বালের ?\w*', r'চোদানির ?\w*', r'হারামির ?\w*',
            r'khankir ?\w*', r'magir ?\w*', r'baler ?\w*', r'chodanir ?\w*', r'haramir ?\w*',
            r'madarchod|motherchod',
            r'chodir ?bhai|codir ?bhai',
            r'khanir ?pola|khanir ?baccha|khanir ?magi',
            r'magir ?pola|magir ?baccha|magir ?chele',
            r'choda ?chudi|chudachudi',
            # Bengali script offensive combinations - More comprehensive
            r'খানকির ?\w*', r'মাগির ?\w*', r'বালের ?\w*', r'চোদানির ?\w*',
            r'মাদার ?চোদ',
            r'চুদির ?ভাই',
            r'খানকির ?পোলা|খানকির ?বাচ্চা|খানকির ?মাগি',
            r'মাগির ?পোলা|মাগির ?বাচ্চা|মাগির ?ছেলে',
            r'চোদা ?চুদি|চুদাচুদি'
        ]

        for pattern_regex in offensive_patterns:
            if re.search(pattern_regex, cleaned, re.IGNORECASE) or \
                    re.search(pattern_regex, original_lower, re.IGNORECASE):
                print(f"Slang detected: Pattern '{pattern_regex}' matched in comment")
                return True

        # Method 4: Additional check for spaced out offensive words
        # Remove all spaces and special characters to catch "খা ন কি র  পো লা" type variations
        no_space_original = re.sub(r'[^a-zA-Z\u0980-\u09FF]', '', original_lower)
        no_space_cleaned = re.sub(r'[^a-zA-Z\u0980-\u09FF]', '', cleaned)

        spaced_offensive = [
            "খানকিরপোলা", "খানকিরবাচ্চা", "মাগিরপোলা", "মাগিরবাচ্চা",
            "বালেরপোলা", "বালেরবাচ্চা", "চোদানিরপুত", "মাদারচোদ",
            "khankirpola", "khankirbaccha", "magirpola", "magirbaccha"
        ]

        for spaced_word in spaced_offensive:
            if spaced_word in no_space_original or spaced_word in no_space_cleaned:
                print(f"Slang detected: Spaced offensive word '{spaced_word}' found in comment")
                return True

        print("No slang detected")
        return False

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
        More relaxed validation rules.
        """
        # Skip validation for very short replies
        if len(reply.split()) <= 5:
            return True

        # Very problematic phrases that should be avoided
        problematic_indicators = [
            'i am an ai', 'i cannot', 'i am not able', 'as an ai',
            'i do not have access', 'i cannot provide medical advice',
            'consult a professional', 'seek professional help'
        ]
        reply_lower = reply.lower()

        # Check for problematic AI-like responses
        if any(indicator in reply_lower for indicator in problematic_indicators):
            print(f"Validation failed: Contains problematic phrase - {reply}")
            return False

        # More generous word limit
        if len(reply.split()) > 50:  # Increased from 25 to 50 words
            print(f"Validation failed: Too long ({len(reply.split())} words) - {reply}")
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
                    "দুঃখিত আপনার অসুবিধার জন্য। ইনবক্স করুন সমাধানের জন্য।",
                    "আপনার সমস্যার কথা বুঝতে পারছি। আমাদের সাথে যোগাযোগ করুন।",
                    "ক্ষমাপ্রার্থী। আপনার সমস্যা সমাধানে আমরা আছি।",
                    "আপনার অভিযোগ গুরুত্বের সাথে দেখছি। ইনবক্স করুন।"
                ]
            else:  # Defaults to English if not explicitly Bangla
                fallbacks = [
                    "Sorry for the inconvenience. Please message us for solution.",
                    "We understand your concern. Please contact us.",
                    "Apologies for the issue. We're here to help.",
                    "We take your feedback seriously. Please inbox us."
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
        Enhanced language detection to better identify Bengali, English, or mixed comments.
        Returns "bangla", "english", or "mixed".
        """
        bangla_chars = re.findall(r'[\u0980-\u09FF]', comment)  # Unicode range for Bengali characters
        english_chars = re.findall(r'[a-zA-Z]', comment)  # English alphabet characters

        # Common Bengali words in Roman script
        bangla_roman_words = [
            'kemon', 'koto', 'kothai', 'kotha', 'koto taka', 'taka', 'dam', 'chele', 'meye',
            'bhai', 'bon', 'apa', 'apu', 'dada', 'didi', 'mama', 'chacha', 'khala', 'nana',
            'nani', 'dadu', 'thakur', 'dadar', 'pore', 'hoyto', 'hoito', 'aar', 'ar',
            'amra', 'tumi', 'tora', 'amader', 'tomader', 'oder', 'ekhane', 'okhane',
            'sekhane', 'etar', 'otar', 'setar', 'eita', 'oita', 'seita', 'keno', 'kemon',
            'kotobela', 'kotokhon', 'amake', 'tomake', 'take', 'kew', 'keu', 'kichu', 'kichui',
            'shob', 'sob', 'shobai', 'sobai', 'dhonnobad', 'shukriya', 'maaf', 'khoma',
            'valo', 'bhalo', 'kharap', 'shundor', 'darun', 'onek', 'onno', 'anno',
            'dhormo', 'islam', 'hindu', 'kristian', 'buddha', 'masjid', 'mondir', 'girja',
            'bihar', 'namaj', 'puja', 'upobash', 'roja', 'eid', 'puja', 'durga', 'kali',
            'laxmi', 'shorasshoti', 'ganesha', 'hanuman', 'ram', 'krishna', 'shib', 'bishnu',
            'allah', 'islamer', 'musolman', 'diner', 'rater', 'shokal', 'dupur', 'bikel',
            'sondha', 'rat', 'din', 'mash', 'bochor', 'tarik', 'shomoyer', 'ghumate',
            'khete', 'khabarer', 'paanir', 'chaa', 'coffee', 'doodh', 'chini', 'nun',
            'tel', 'masala', 'mishti', 'tetuler', 'amer', 'jamrul', 'komolar', 'anarosher',
            'aamer', 'jamer', 'litchur', 'kataler', 'shofeda', 'atafol', 'daler', 'bhater',
            'ruti', 'poratar', 'sobji', 'maachher', 'mangsher', 'murgi', 'dim', 'halka',
            'jhaal', 'nonta', 'mishti', 'tita', 'tikha', 'lebu', 'ada', 'roshun', 'peyaj',
            'holud', 'dhonia', 'jeera', 'elach', 'darchini', 'lobongo', 'badi', 'ghor',
            'basha', 'school', 'college', 'university', 'chapkori', 'kaaj', 'byabsha',
            'dokani', 'haat', 'bazar', 'bank', 'hospital', 'pharmecy', 'daktar', 'noyon',
            'kan', 'naak', 'mukh', 'gola', 'hat', 'pa', 'mathaa', 'chuler', 'deher',
            'shorir', 'mon', 'chokh', 'daat', 'jiv', 'ghar', 'pet', 'buk', 'pith',
            'komorer', 'haatur', 'thenger', 'angul', 'nokhher', 'gaaye', 'chaal',
            'ekhono', 'akhono', 'ekhon', 'akhon', 'pore', 'age', 'agamir', 'ager',
            'shesher', 'prothom', 'duitiyo', 'tritiyo', 'chaturtha', 'shob'
        ]

        # Check for Bengali Roman words
        comment_lower = comment.lower()
        bangla_roman_count = sum(1 for word in bangla_roman_words if word in comment_lower)

        # Common English words that indicate English content
        english_words = [
            'the', 'is', 'at', 'which', 'on', 'are', 'as', 'able', 'about', 'after',
            'all', 'also', 'am', 'an', 'and', 'any', 'are', 'as', 'at', 'be', 'been',
            'by', 'can', 'could', 'do', 'for', 'from', 'get', 'have', 'he', 'her', 'him',
            'his', 'how', 'i', 'if', 'in', 'into', 'is', 'it', 'its', 'just', 'like',
            'make', 'most', 'new', 'no', 'not', 'now', 'of', 'on', 'one', 'only', 'or',
            'other', 'our', 'out', 'over', 'said', 'same', 'see', 'she', 'should', 'so',
            'some', 'take', 'than', 'that', 'the', 'their', 'them', 'there', 'these',
            'they', 'this', 'time', 'to', 'two', 'up', 'us', 'use', 'very', 'want',
            'was', 'water', 'way', 'we', 'well', 'were', 'what', 'when', 'where',
            'which', 'who', 'will', 'with', 'would', 'you', 'your'
        ]

        english_word_count = sum(1 for word in english_words if word in comment_lower.split())

        bangla_count = len(bangla_chars) + bangla_roman_count
        english_count = len(english_chars) + english_word_count

        # More sophisticated detection
        if bangla_count > english_count:
            return "bangla"
        elif english_count > bangla_count * 1.5:  # Give English some advantage
            return "english"
        else:
            return "mixed"

    def extract_contact_info(self, post_content):
        """
        Extracts website link, WhatsApp number, and Facebook group link from post content.
        Updated to extract company name from the website link and make it dynamic.
        """
        website_link = re.search(r'https://(\S+?)\.com/\S*', post_content)  # Broader match for website
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
            "extracted_company_name": extracted_company_name  # Return extracted company name
        }

    def generate_reply(self, json_data):
        """
        Generates a reply to a comment based on the provided JSON data.
        It first checks for slang, then determines sentiment and language,
        builds a context for the LLM, and finally generates a controlled reply.
        Includes token counting for the LLM response.
        Enhanced to reply in the same language as the comment.
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
            reply = ""  # No reply for actual offensive slang
            sentiment = "Negative"  # Assign negative sentiment for slang comments
            note = "Offensive content detected. No reply generated."
            response_time = f"{time.time() - start_time:.2f}s"
            # Return immediate response if offensive slang is detected
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
                "status_code": 200
            }

        # --- Sentiment and Language Detection ---
        sentiment = self.get_sentiment(comment_text)
        comment_language = self.detect_comment_language(comment_text)
        commenter_name = comment_info.get("commenter_name", "User")  # Default to "User" if name is missing

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

        # Enhanced System prompt: Crucial for controlling behavior and language matching
        language_instruction = ""
        if comment_language == "bangla":
            language_instruction = "IMPORTANT: The user is commenting in Bengali/Bangla. You MUST respond ONLY in Bengali/Bangla language. Use Bengali script (বাংলা) or Bengali romanized text when appropriate."
        elif comment_language == "english":
            language_instruction = "IMPORTANT: The user is commenting in English. You MUST respond ONLY in English language."
        else:  # mixed
            language_instruction = "IMPORTANT: The user is commenting in mixed language (Bengali+English). You should respond in the predominant language of their comment, or in Bengali if uncertain."

        system_prompt = f"""
        You are an AI assistant for {company_name_to_use}'s Facebook page.
        Your goal is to provide concise, helpful, and friendly replies to comments.

        {language_instruction}

        Keep replies very short, typically 1-2 sentences, and to the point.
        Address the commenter by their name if available.
        Mention the company name '{company_name_to_use}' naturally if relevant.

        For negative feedback or complaints:
        - Acknowledge their concern professionally
        - Apologize if appropriate 
        - Direct them to inbox/contact for resolution
        - Stay positive and helpful

        For positive feedback:
        - Thank them warmly
        - Show appreciation

        For questions:
        - Answer briefly if you can
        - Direct to contact information if needed

        If contact information (website, WhatsApp, Facebook group) is available from the post, suggest visiting or contacting through those channels where appropriate.
        Do NOT generate long paragraphs or elaborate explanations.
        Use emojis appropriately to make responses friendly.
        The current date and time is {datetime.now().strftime("%Y-%m-%d %H:%M")}.

        Remember: Match the language of the comment - if they write in Bengali, reply in Bengali. If they write in English, reply in English.
        Handle criticism professionally - don't ignore negative feedback, respond with care and direct to proper channels.
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
                messages.append({"role": "user",
                                 "content": f"Previous comment from {prev_comment['commenter_name']}: {prev_comment['comment_text']}"})

        # Add the current comment with language detection info
        current_comment_message = f"The current comment is from {commenter_name} in {comment_language} language: '{comment_text}'."
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
            messages.append({"role": "user", "content": "Relevant contact information for our company: " + " ".join(
                contact_instructions) + " Please suggest visiting our website, WhatsApp, or Facebook group if it makes sense."})
        else:
            messages.append({"role": "user",
                             "content": "No specific contact information provided in the post. Generate a polite and concise general reply in the same language as the comment."})

        # Calculate input tokens before the API call
        input_tokens = self.count_tokens(" ".join([m["content"] for m in messages]))

        # --- Call OpenRouter GPT-4o-mini API ---
        try:
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 100,  # Increased slightly for better language flexibility
                "temperature": 0.7,
                "top_p": 0.9,
                "stop": ["\n\n", "Commenter:", "User:"]  # Common stop sequences
            }
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=15)

            # Handle specific HTTP errors
            if response.status_code == 402:
                print(
                    "Payment Required: Insufficient credits or no payment method. Please add credits to your account.")
                reply = self.get_fallback_response(comment_text, sentiment, comment_language)
                note = "Payment Required: Insufficient API credits. Using fallback."
                controlled_status = True
                output_tokens = 0
            elif response.status_code == 401:
                print("Unauthorized: Invalid API key. Please check your API key.")
                reply = self.get_fallback_response(comment_text, sentiment, comment_language)
                note = "Unauthorized: Invalid API key. Using fallback."
                controlled_status = True
                output_tokens = 0
            elif response.status_code == 429:
                print("Rate Limited: Too many requests. Please wait and try again.")
                reply = self.get_fallback_response(comment_text, sentiment, comment_language)
                note = "Rate Limited: Too many requests. Using fallback."
                controlled_status = True
                output_tokens = 0
            else:
                response.raise_for_status()  # Raise an exception for other HTTP errors
                llm_response_json = response.json()
                llm_reply = llm_response_json["choices"][0]["message"]["content"].strip()
                output_tokens = self.count_tokens(llm_reply)

                # Post-process LLM reply
                # Ensure the reply doesn't start with the commenter's name if already addressed in the prompt
                if commenter_name.lower() in llm_reply.lower() and llm_reply.lower().startswith(commenter_name.lower()):
                    llm_reply = re.sub(r"^\s*" + re.escape(commenter_name) + r"[\s,.:;]*", "", llm_reply,
                                       flags=re.IGNORECASE).strip()
                    if llm_reply.startswith("!"):  # Remove leading exclamation if it resulted from stripping
                        llm_reply = llm_reply[1:].strip()

                # Validate LLM response
                print(f"Original LLM Response: '{llm_reply}'")  # Debug log
                print(f"Response word count: {len(llm_reply.split())}")  # Debug log

                if not self.validate_response(llm_reply, comment_text):
                    # Log why validation failed
                    print(f"Validation failed for response: '{llm_reply}'")
                    reply = self.get_fallback_response(comment_text, sentiment, comment_language)
                    note = f"LLM response rejected by validation: '{llm_reply[:50]}...'. Using fallback."
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
            output_tokens = 0  # No output tokens if API call failed
        except KeyError as e:
            print(
                f"Failed to parse LLM response: {e}. Response: {llm_response_json if 'llm_response_json' in locals() else 'No response'}")
            reply = self.get_fallback_response(comment_text, sentiment, comment_language)
            note = f"Failed to parse LLM response: {e}. Using fallback."
            controlled_status = True
            output_tokens = 0  # No output tokens if parsing failed
        except Exception as e:
            print(f"An unexpected error occurred during LLM reply generation: {e}")
            reply = self.get_fallback_response(comment_text, sentiment, comment_language)
            note = f"Unexpected error: {e}. Using fallback."
            controlled_status = True
            output_tokens = 0  # No output tokens if an unexpected error occurred

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
            "comment_language": comment_language,  # Added language detection result
            "status_code": reply_status_code
        }


@app.route('/', methods=['GET'])
def display():
    return 'welcome'


@app.route('/test-slang', methods=['POST'])
def test_slang():
    """Test endpoint to check slang detection for debugging"""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Text is required"}), 400

    bot = FacebookBot()
    text = data['text']
    slang_detected = bot.contains_slang(text)

    return jsonify({
        "text": text,
        "slang_detected": slang_detected,
        "message": "Slang detected" if slang_detected else "No slang detected"
    })


@app.route('/process-comment', methods=['POST'])
def process_comment():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON data"}), 400

    bot = FacebookBot()
    response = bot.generate_reply(data)
    return jsonify(response), response.get("status_code", 200)


if __name__ == '__main__':
    # For production deployment, remove debug=True
    # Ensure OPENAI_API_KEY or OPENROUTER_API_KEY is set in your .env file or environment variables
    if os.getenv("OPENAI_API_KEY") is None and os.getenv("OPENROUTER_API_KEY") is None:
        print(
            "Error: OPENAI_API_KEY or OPENROUTER_API_KEY environment variable not set. Please set it in a .env file or your system environment.")
    else:
        # For production, use: app.run(host="0.0.0.0", port=5000)
        app.run(debug=False, host="0.0.0.0", port=5000)