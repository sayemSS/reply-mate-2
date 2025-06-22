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

    # --- Language Detection (Simplified) ---
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
            'valo', 'bhalo', 'kharap', 'shundor', 'darun', 'onek', 'onno', 'anno'
        ]

        # Check for Bengali Roman words
        comment_lower = comment.lower()
        bangla_roman_count = sum(1 for word in bangla_roman_words if word in comment_lower)

        # Common English words
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

    def get_fallback_response(self, comment, comment_language):
        """
        Provides a relevant fallback response if the LLM fails.
        Responses are tailored to language.
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

        # General fallback responses
        if comment_language == "bangla":
            fallbacks = [
                "ধন্যবাদ! ইনবক্স করুন আরো সাহায্যের জন্য। 🙏",
                "আপনার মতামতের জন্য ধন্যবাদ! 😊",
                "সরাসরি যোগাযোগ করুন সাহায্যের জন্য।",
                "আরো জানতে ইনবক্স করুন।"
            ]
        else:  # Defaults to English if not explicitly Bangla
            fallbacks = [
                "Thank you! Please inbox for more help. 🙏",
                "Thanks for your feedback! 😊",
                "Contact us directly for assistance.",
                "Inbox us to know more."
            ]
        return random.choice(fallbacks)

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

    def analyze_comment_with_gpt(self, comment_text):
        """
        Uses ChatGPT to analyze comment for sentiment and offensive content detection.
        Returns: {
            'sentiment': 'positive'/'negative'/'neutral',
            'is_offensive': True/False,
            'analysis_reason': 'explanation of the analysis'
        }
        """
        try:
            analysis_prompt = f"""
            You are an expert content moderator and sentiment analyst. Analyze the following comment and provide:

            1. Sentiment: positive, negative, or neutral
            2. Is it offensive/inappropriate: true or false
            3. Brief reason for your analysis

            Comment to analyze: "{comment_text}"

            Response format (JSON only):
            {{
                "sentiment": "positive/negative/neutral",
                "is_offensive": true/false,
                "analysis_reason": "brief explanation"
            }}

            Consider:
            - Bengali/English mixed language
            - Cultural context
            - Slang and informal language
            - Sarcasm and irony
            - Profanity and offensive language
            - Context-dependent meanings
            """

            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": analysis_prompt}],
                "max_tokens": 150,
                "temperature": 0.3,  # Lower temperature for more consistent analysis
                "response_format": {"type": "json_object"}
            }

            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=15)

            if response.status_code == 200:
                analysis_result = response.json()
                content = analysis_result["choices"][0]["message"]["content"]

                try:
                    import json
                    parsed_result = json.loads(content)
                    return {
                        'sentiment': parsed_result.get('sentiment', 'neutral').lower(),
                        'is_offensive': parsed_result.get('is_offensive', False),
                        'analysis_reason': parsed_result.get('analysis_reason', 'Analysis completed')
                    }
                except json.JSONDecodeError:
                    print(f"Failed to parse GPT analysis result: {content}")
                    return {'sentiment': 'neutral', 'is_offensive': False, 'analysis_reason': 'Parse error'}
            else:
                print(f"GPT analysis API failed with status: {response.status_code}")
                return {'sentiment': 'neutral', 'is_offensive': False, 'analysis_reason': 'API error'}

        except Exception as e:
            print(f"Error in GPT analysis: {e}")
            return {'sentiment': 'neutral', 'is_offensive': False, 'analysis_reason': f'Error: {e}'}

    def generate_reply(self, json_data):
        """
        Generates a reply to a comment based on the provided JSON data.
        Now uses ChatGPT for both content analysis and reply generation.
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

        # --- Use ChatGPT for Content Analysis ---
        print(f"Analyzing comment with ChatGPT: {comment_text}")
        gpt_analysis = self.analyze_comment_with_gpt(comment_text)

        sentiment = gpt_analysis['sentiment']
        is_offensive = gpt_analysis['is_offensive']
        analysis_reason = gpt_analysis['analysis_reason']

        # If offensive content detected, don't reply
        if is_offensive:
            reply = ""  # No reply for offensive content
            note = f"Offensive content detected by GPT: {analysis_reason}"
            response_time = f"{time.time() - start_time:.2f}s"
            return {
                "comment_id": comment_id,
                "commenter_name": comment_info.get("commenter_name", ""),
                "controlled": True,
                "input_tokens": 0,
                "note": note,
                "output_tokens": 0,
                "page_name": page_info.get("page_name", ""),
                "post_id": post_id,
                "reply": reply,
                "response_time": response_time,
                "sentiment": sentiment,
                "slang_detected": True,  # Keep this for backward compatibility
                "analysis_reason": analysis_reason,
                "status_code": 200
            }

        # --- Language Detection ---
        comment_language = self.detect_comment_language(comment_text)
        commenter_name = comment_info.get("commenter_name", "User")  # Default to "User" if name is missing

        # Extract contact information
        contact_info = self.extract_contact_info(post_info.get("post_content", ""))
        website_link = contact_info.get("website")
        whatsapp_number = contact_info.get("whatsapp")
        facebook_group_link = contact_info.get("facebook_group")

        # Dynamically get company name
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

        IMPORTANT: The comment sentiment has been analyzed as "{sentiment}". Use this information to craft an appropriate response.
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

        # Add the current comment with analysis info
        current_comment_message = f"The current comment is from {commenter_name} in {comment_language} language with {sentiment} sentiment: '{comment_text}'."
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

        # --- Call OpenRouter GPT-4o-mini API for Reply Generation ---
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
                print("Payment Required: Insufficient credits or no payment method.")
                reply = self.get_fallback_response(comment_text, comment_language)
                note = "Payment Required: Insufficient API credits. Using fallback."
                controlled_status = True
                output_tokens = 0
            elif response.status_code == 401:
                print("Unauthorized: Invalid API key.")
                reply = self.get_fallback_response(comment_text, comment_language)
                note = "Unauthorized: Invalid API key. Using fallback."
                controlled_status = True
                output_tokens = 0
            elif response.status_code == 429:
                print("Rate Limited: Too many requests.")
                reply = self.get_fallback_response(comment_text, comment_language)
                note = "Rate Limited: Too many requests. Using fallback."
                controlled_status = True
                output_tokens = 0
            else:
                response.raise_for_status()
                llm_response_json = response.json()
                llm_reply = llm_response_json["choices"][0]["message"]["content"].strip()
                output_tokens = self.count_tokens(llm_reply)

                # Post-process LLM reply
                if commenter_name.lower() in llm_reply.lower() and llm_reply.lower().startswith(commenter_name.lower()):
                    llm_reply = re.sub(r"^\s*" + re.escape(commenter_name) + r"[\s,.:;]*", "", llm_reply,
                                       flags=re.IGNORECASE).strip()
                    if llm_reply.startswith("!"):
                        llm_reply = llm_reply[1:].strip()

                reply = llm_reply
                note = f"GPT Analysis: {analysis_reason}"
                controlled_status = False

        except requests.exceptions.RequestException as e:
            print(f"API request failed: {e}")
            reply = self.get_fallback_response(comment_text, comment_language)
            note = f"API request failed: {e}. Using fallback."
            controlled_status = True
            output_tokens = 0
        except KeyError as e:
            print(f"Failed to parse LLM response: {e}")
            reply = self.get_fallback_response(comment_text, comment_language)
            note = f"Failed to parse LLM response: {e}. Using fallback."
            controlled_status = True
            output_tokens = 0
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            reply = self.get_fallback_response(comment_text, comment_language)
            note = f"Unexpected error: {e}. Using fallback."
            controlled_status = True
            output_tokens = 0

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
            "slang_detected": is_offensive,  # Keep for backward compatibility
            "comment_language": comment_language,
            "analysis_reason": analysis_reason,
            "status_code": reply_status_code
        }


@app.route('/', methods=['GET'])
def display():
    return 'welcome'


@app.route('/test-analysis', methods=['POST'])
def test_analysis():
    """Test endpoint to check GPT-based content analysis for debugging"""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "Text is required"}), 400

    bot = FacebookBot()
    text = data['text']
    analysis_result = bot.analyze_comment_with_gpt(text)

    return jsonify({
        "text": text,
        "analysis": analysis_result,
        "message": "Analysis completed using ChatGPT"
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