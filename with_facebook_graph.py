import os
import re
import requests
import time
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import threading

load_dotenv()


class FacebookAPI:
    def __init__(self):
        self.app_id = 1452004559585377
        self.app_secret = '74d82f171814dba30aa6c49e65b40dbf'
        self.page_access_token = 'EAAUolyf8gGEBOxOrsw8yweSS7NS7mDjWO1ZAd3hhZAbXjcEpmroSSaqD3bXaMg3QA6KZBSz89CKRQwBgJmZAimWtKgRdvsj1iCrynOjkEg4CPHUSk2VP44qBBhAZAdw2VPZA8H7pZB6ZAFYkS166OlR3p88erq5JWzifVmZAC3RTK6HYakJp8T5aEuec1kAallSE9nzYG'
        self.page_id = 649928478205782
        self.base_url = "https://graph.facebook.com/v18.0/"

        if not all([self.app_id, self.app_secret, self.page_access_token, self.page_id]):
            raise Exception("Missing Facebook API credentials in .env file")

    def safe_api_call(self, method, url, **kwargs):
        """Safe API call with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, **kwargs)
                else:
                    response = requests.post(url, **kwargs)

                if response.status_code == 429:  # Rate limited
                    retry_after = int(response.headers.get('Retry-After', 60))
                    print(f"⏳ Rate limited. Waiting {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                return response.json()

            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"❌ API call failed after {max_retries} attempts: {e}")
                    return None
                time.sleep(2 ** attempt)  # Exponential backoff

        return None

    def get_page_info(self):
        """Get page information"""
        url = f"{self.base_url}/{self.page_id}"
        params = {
            'access_token': self.page_access_token,
            'fields': 'id,name,about,category,description,phone,website,location,hours,price_range,fan_count,emails'
        }

        result = self.safe_api_call('GET', url, params=params)
        if result:
            print("✅ Page information fetched successfully")
        return result

    def get_recent_posts(self, limit=10):
        """Get recent posts with comments"""
        url = f"{self.base_url}/{self.page_id}/posts"
        params = {
            'access_token': self.page_access_token,
            'fields': 'id,message,created_time,comments.limit(50){id,message,from,created_time,parent}',
            'limit': limit
        }

        result = self.safe_api_call('GET', url, params=params)
        if result:
            print(f"✅ Fetched {len(result.get('data', []))} recent posts")
        return result

    def get_post_comments(self, post_id, limit=100):
        """Get comments for a specific post"""
        url = f"{self.base_url}/{post_id}/comments"
        params = {
            'access_token': self.page_access_token,
            'fields': 'id,message,from,created_time,parent',
            'limit': limit,
            'order': 'chronological'
        }

        return self.safe_api_call('GET', url, params=params)

    def reply_to_comment(self, comment_id, message):
        """Reply to a specific comment"""
        url = f"{self.base_url}/{comment_id}/comments"
        data = {
            'message': message,
            'access_token': self.page_access_token
        }

        result = self.safe_api_call('POST', url, data=data)
        if result:
            print(f"✅ Reply posted successfully to comment {comment_id}")
        return result

    def comment_on_post(self, post_id, message):
        """Comment directly on a post"""
        url = f"{self.base_url}/{post_id}/comments"
        data = {
            'message': message,
            'access_token': self.page_access_token
        }

        result = self.safe_api_call('POST', url, data=data)
        if result:
            print(f"✅ Comment posted successfully on post {post_id}")
        return result


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
        self.processed_comments = set()  # Track processed comments

        # Comprehensive slang/bad words list - Bengali and English
        self.slang_words = [
            # Bengali explicit words
            "মাগি", "খানি", "চোদা", "চোদি", "চুদি", "চুদা", "রান্ড", "বেশ্যা",
            "হারামি", "হারামজাদা", "কুত্তা", "কুত্তার বাচ্চা", "শুওরের বাচ্চা",
            "গাধা", "গাধার বাচ্চা", "পাগল", "বদমাইশ", "নোংরা", "নোংরামি",
            "হুদা", "হুজুর", "বকবক", "বাজে", "খারাপ", "বিরক্তিকর",
            "লেংড়া", "পঙ্গু", "অন্ধ", "বোবা", "কালা", "মোটা", "চিকন",

            # English explicit words
            "fuck", "fucking", "fucked", "fucker", "fck", "f*ck", "f**k",
            "shit", "shit", "bullshit", "bs", "sh*t", "s**t",
            "bitch", "bitches", "b*tch", "b**ch",
            "asshole", "ass", "a**hole", "a*s",
            "dick", "cock", "penis", "d*ck", "c**k",
            "pussy", "vagina", "cunt", "p***y", "c**t",
            "slut", "whore", "prostitute", "sl*t", "wh*re",
            "bastard", "b*stard", "b**tard",
            "dumbass", "stupid", "idiot", "moron", "retard",
            "damn", "hell", "bloody", "wtf", "stfu",

            # Common internet slang/abbreviations
            "lmao", "lmfao", "omfg", "fml", "gtfo", "kys",

            # Leetspeak and variations
            "f0ck", "sh1t", "b1tch", "a55", "d1ck", "fuk", "sht",

            # Bengali romanized slang
            "magi", "khani", "choda", "chodi", "chudi", "chuda", "rand",
            "harami", "haramjada", "kutta", "kuttar bacha", "shuorer bacha",
            "gadha", "gadhar bacha", "pagol", "badmaish", "nongra",
            "huda", "hujur", "bokbok", "baje", "kharap", "biriktikor",

            # Mixed language slang
            "মাদার চোদ", "ফাক", "শিট", "বিচ", "হেল", "ড্যাম"
        ]

        # Patterns for detecting slang with numbers/symbols
        self.slang_patterns = [
            r'f+u+c+k+',  # fuuuuck
            r's+h+i+t+',  # shiiiit
            r'b+i+t+c+h+',  # biiiitch
            r'a+s+s+',  # assss
            r'চো+দা+',  # চোওওদা
            r'মা+গি+',  # মাাাগি
            r'খা+নি+',  # খাাাানি
            r'হা+রা+মি+',  # হাাাররামি
        ]

    def set_page_info(self, info):
        self.page_info = info
        print(f"✅ Page information updated")

    def add_comment_history(self, comment):
        self.previous_comments.append({
            "comment": comment,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
        })
        if len(self.previous_comments) > 10:
            self.previous_comments.pop(0)

    def clean_text_for_slang(self, text):
        """Enhanced text cleaning for better slang detection"""
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
        """Enhanced slang detection with multiple methods"""
        if not text or len(text.strip()) == 0:
            return False

        cleaned = self.clean_text_for_slang(text)
        original_lower = text.lower()

        # Method 1: Direct word matching
        for slang in self.slang_words:
            pattern = r'\b' + re.escape(slang.lower()) + r'\b'
            if re.search(pattern, cleaned) or re.search(pattern, original_lower):
                print(f"🚫 Slang detected: '{slang}' in '{text[:50]}...'")
                return True

        # Method 2: Pattern matching for repeated characters
        for pattern in self.slang_patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                print(f"🚫 Slang pattern detected in '{text[:50]}...'")
                return True

        # Method 3: Check for spaced out slang
        spaced_text = re.sub(r'\s+', '', cleaned)
        for slang in self.slang_words:
            if slang.lower() in spaced_text:
                print(f"🚫 Spaced slang detected: '{slang}' in '{text[:50]}...'")
                return True

        # Method 4: Check for slang with mixed case/symbols
        no_space_text = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', original_lower)
        for slang in self.slang_words:
            clean_slang = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', slang.lower())
            if clean_slang in no_space_text:
                print(f"🚫 Hidden slang detected: '{slang}' in '{text[:50]}...'")
                return True

        return False

    def get_sentiment(self, comment):
        positive_words = ['ভালো', 'good', 'great', 'excellent', 'love', 'amazing', 'wonderful', 'thanks', 'ধন্যবাদ',
                          'সুন্দর', 'চমৎকার']
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

    def get_slang_response(self):
        """Different responses for slang comments"""
        import random
        responses = [
            "দয়া করে ভদ্র ভাষায় মন্তব্য করুন। আমরা আপনাকে সাহায্য করতে চাই। 🙏",
            "অনুগ্রহ করে শালীন ভাষা ব্যবহার করুন। আমরা সবার সাথে সম্মানের সাথে কথা বলি। ✋",
            "Please use respectful language. We're here to help you in a positive way. 😊",
            "আমাদের পেজে সবাই ভদ্র আচরণ করেন। দয়া করে শালীন ভাষায় মন্তব্য করুন। 🚫"
        ]
        return random.choice(responses)

    def get_fallback_response(self, comment, sentiment):
        import random
        comment_lower = comment.lower()

        if any(word in comment_lower for word in ['application', 'apply', 'job', 'আবেদন', 'চাকরি', 'লিখতে']):
            return random.choice([
                "অ্যাপ্লিকেশন লেখার জন্য আমাদের অফিসিয়াল ফর্ম ডাউনলোড করুন অথবা সরাসরি ইনবক্সে যোগাযোগ করুন।",
                "আপনার আবেদন সংক্রান্ত প্রশ্নের জন্য আমাদের ইনবক্সে মেসেজ করুন, আমরা সাহায্য করবো।"
            ])

        if sentiment == "Positive":
            fallbacks = [
                "ধন্যবাদ! আপনার মতামতের জন্য কৃতজ্ঞ। 🙏",
                "Thank you for your kind words! 😊",
                "আপনার সাপোর্টের জন্য ধন্যবাদ! ❤️"
            ]
        elif sentiment == "Negative":
            fallbacks = [
                "দুঃখিত! আরো তথ্যের জন্য আমাদের ইনবক্স করুন।",
                "Sorry for any inconvenience. Please message us for details."
            ]
        else:
            fallbacks = [
                "আমাদের পেজ সম্পর্কিত কোনো প্রশ্ন থাকলে ইনবক্সে মেসেজ করুন।",
                "আমাদের সেবা সম্পর্কে জানতে ইনবক্সে যোগাযোগ করুন।"
            ]

        return random.choice(fallbacks)

    def generate_reply(self, comment):
        start_time = time.time()

        # Enhanced slang detection
        if self.contains_slang(comment):
            return {
                "reply": self.get_slang_response(),
                "sentiment": "Inappropriate",
                "response_time": f"{time.time() - start_time:.2f}s",
                "controlled": True,
                "slang_detected": True
            }

        context = f"Facebook Page Information: {self.page_info}\n\n"

        if self.previous_comments:
            context += "Recent Comments for Context:\n"
            for prev in self.previous_comments[-3:]:
                context += f"- {prev['comment']} ({prev['timestamp']})\n"

        system_prompt = """You are a Facebook page manager. Reply to comments STRICTLY based on provided page information only.

STRICT RULES:
1. NEVER answer questions beyond the provided page information
2. Keep replies under 50 words maximum
3. Don't give general advice or external information
4. Only mention services/products/info that are specifically provided
5. If no relevant info available, give brief polite fallback response"""

        user_prompt = f"""Page Information Available:
{context}

Current Comment: "{comment}"

Reply ONLY based on page information. Keep under 50 words."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "max_tokens": 80,
            "temperature": 0.3
        }

        try:
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=30)
            if response.status_code != 200:
                return {"error": f"API call failed ({response.status_code})"}

            reply = response.json()['choices'][0]['message']['content'].strip()
            response_time = time.time() - start_time
            sentiment = self.get_sentiment(comment)

            # Validate response
            if len(reply.split()) > 50:
                reply = self.get_fallback_response(comment, sentiment)

            self.add_comment_history(comment)

            return {
                "reply": reply,
                "sentiment": sentiment,
                "response_time": f"{response_time:.2f}s",
                "controlled": True,
                "slang_detected": False
            }
        except Exception as e:
            return {"error": str(e)}


class FacebookPageBot:
    def __init__(self):
        self.fb_api = FacebookAPI()
        self.bot = FacebookBot()
        self.is_running = False
        self.monitoring_thread = None
        self.check_interval = 60  # Check every 60 seconds
        self.last_check_time = datetime.now()

    def initialize(self):
        """Initialize the bot with page information"""
        try:
            print("🚀 Initializing Facebook Page Bot...")

            # Get page information
            page_info = self.fb_api.get_page_info()
            if not page_info:
                raise Exception("Failed to fetch page information")

            # Set page info for the bot
            info_text = f"""
            Page Name: {page_info.get('name', 'N/A')}
            Category: {page_info.get('category', 'N/A')}
            About: {page_info.get('about', 'N/A')}
            Description: {page_info.get('description', 'N/A')}
            Phone: {page_info.get('phone', 'N/A')}
            Website: {page_info.get('website', 'N/A')}
            Followers: {page_info.get('fan_count', 'N/A')}
            """

            self.bot.set_page_info(info_text)
            print("✅ Bot initialization completed successfully")
            return True

        except Exception as e:
            print(f"❌ Initialization failed: {e}")
            return False

    def process_new_comments(self):
        """Process new comments on recent posts"""
        try:
            # Get recent posts
            posts_data = self.fb_api.get_recent_posts(limit=5)
            if not posts_data or 'data' not in posts_data:
                return

            processed_count = 0

            for post in posts_data['data']:
                post_id = post['id']

                # Get comments for this post
                if 'comments' in post and 'data' in post['comments']:
                    comments = post['comments']['data']

                    for comment in comments:
                        comment_id = comment['id']
                        comment_text = comment.get('message', '')
                        comment_time = comment.get('created_time', '')

                        # Skip if already processed
                        if comment_id in self.bot.processed_comments:
                            continue

                        # Skip if comment is too old (older than last check)
                        try:
                            comment_datetime = datetime.fromisoformat(comment_time.replace('Z', '+00:00'))
                            if comment_datetime < self.last_check_time:
                                continue
                        except:
                            pass

                        # Skip if it's our own comment
                        if comment.get('from', {}).get('id') == self.fb_api.page_id:
                            continue

                        # Generate reply
                        print(f"💬 Processing comment: {comment_text[:50]}...")
                        reply_data = self.bot.generate_reply(comment_text)

                        if 'error' in reply_data:
                            print(f"❌ Error generating reply: {reply_data['error']}")
                            continue

                        # Post reply
                        reply_result = self.fb_api.reply_to_comment(comment_id, reply_data['reply'])

                        if reply_result:
                            print(f"✅ Replied to comment: {reply_data['reply'][:30]}...")
                            processed_count += 1

                            # Mark as processed
                            self.bot.processed_comments.add(comment_id)

                            # Rate limiting - wait between replies
                            time.sleep(2)
                        else:
                            print(f"❌ Failed to post reply to comment {comment_id}")

            if processed_count > 0:
                print(f"🎉 Processed {processed_count} new comments")

            # Update last check time
            self.last_check_time = datetime.now()

        except Exception as e:
            print(f"❌ Error processing comments: {e}")

    def monitor_comments(self):
        """Continuous monitoring of comments"""
        print(f"👀 Starting comment monitoring (checking every {self.check_interval} seconds)")

        while self.is_running:
            try:
                self.process_new_comments()
                time.sleep(self.check_interval)
            except KeyboardInterrupt:
                print("\n⏹️ Monitoring stopped by user")
                break
            except Exception as e:
                print(f"❌ Monitoring error: {e}")
                time.sleep(30)  # Wait 30 seconds before retrying

    def start_monitoring(self):
        """Start the bot monitoring in a separate thread"""
        if self.is_running:
            print("⚠️ Bot is already running")
            return False

        if not self.initialize():
            print("❌ Cannot start monitoring - initialization failed")
            return False

        self.is_running = True
        self.monitoring_thread = threading.Thread(target=self.monitor_comments, daemon=True)
        self.monitoring_thread.start()

        print("🚀 Facebook Page Bot started successfully!")
        return True

    def stop_monitoring(self):
        """Stop the bot monitoring"""
        if not self.is_running:
            print("⚠️ Bot is not running")
            return False

        self.is_running = False
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=5)

        print("⏹️ Facebook Page Bot stopped")
        return True

    def get_status(self):
        """Get current bot status"""
        return {
            "running": self.is_running,
            "processed_comments": len(self.bot.processed_comments),
            "last_check": self.last_check_time.strftime("%Y-%m-%d %H:%M:%S"),
            "check_interval": self.check_interval
        }

    def test_reply(self, test_comment):
        """Test the bot's reply generation"""
        if not self.bot.page_info:
            if not self.initialize():
                return {"error": "Failed to initialize bot"}

        print(f"🧪 Testing reply for: {test_comment}")
        reply_data = self.bot.generate_reply(test_comment)
        print(f"🤖 Generated reply: {reply_data}")
        return reply_data


def main():
    """Main function to run the Facebook Page Bot"""
    try:
        # Create bot instance
        page_bot = FacebookPageBot()

        print("=" * 60)
        print("🤖 FACEBOOK PAGE BOT")
        print("=" * 60)

        while True:
            print("\n📋 Available Commands:")
            print("1. Start monitoring")
            print("2. Stop monitoring")
            print("3. Check status")
            print("4. Test reply")
            print("5. Exit")

            choice = input("\n👉 Enter your choice (1-5): ").strip()

            if choice == '1':
                page_bot.start_monitoring()

            elif choice == '2':
                page_bot.stop_monitoring()

            elif choice == '3':
                status = page_bot.get_status()
                print(f"\n📊 Bot Status:")
                print(f"Running: {'✅ Yes' if status['running'] else '❌ No'}")
                print(f"Processed Comments: {status['processed_comments']}")
                print(f"Last Check: {status['last_check']}")
                print(f"Check Interval: {status['check_interval']} seconds")

            elif choice == '4':
                test_comment = input("Enter test comment: ").strip()
                if test_comment:
                    result = page_bot.test_reply(test_comment)
                    print(f"\n🧪 Test Result: {json.dumps(result, indent=2)}")

            elif choice == '5':
                if page_bot.is_running:
                    page_bot.stop_monitoring()
                print("👋 Goodbye!")
                break

            else:
                print("❌ Invalid choice. Please try again.")

    except KeyboardInterrupt:
        print("\n\n⏹️ Program interrupted by user")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
    finally:
        print("🔚 Program ended")


if __name__ == "__main__":
    main()