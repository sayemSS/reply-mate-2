import os
import re
import requests
import time
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


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

        self.slang_patterns = [
            r'f+u+c+k+',
            r's+h+i+t+',
            r'b+i+t+c+h+',
            r'a+s+s+',
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
        """Enhanced slang detection with multiple methods"""
        if not text or len(text.strip()) == 0:
            return False

        cleaned = self.clean_text_for_slang(text)
        original_lower = text.lower()

        # Method 1: Direct word matching
        for slang in self.slang_words:
            pattern = r'\b' + re.escape(slang.lower()) + r'\b'
            if re.search(pattern, cleaned) or re.search(pattern, original_lower):
                return True

        # Method 2: Pattern matching for repeated characters
        for pattern in self.slang_patterns:
            if re.search(pattern, cleaned, re.IGNORECASE):
                return True

        # Method 3: Check for spaced out slang (f u c k -> fuck)
        spaced_text = re.sub(r'\s+', '', cleaned)
        for slang in self.slang_words:
            if slang.lower() in spaced_text:
                return True

        # Method 4: Check for slang with mixed case/symbols
        no_space_text = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', original_lower)
        for slang in self.slang_words:
            clean_slang = re.sub(r'[\s\-_.,!@#$%^&*()+={}[\]|\\:";\'<>?/~`]', '', slang.lower())
            if clean_slang in no_space_text:
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
        if any(word in comment_lower for word in ['application', 'apply', 'job', 'আবেদন', 'চাকরি', 'লিখতে']):
            return random.choice([
                "অ্যাপ্লিকেশন লেখার জন্য আমাদের অফিসিয়াল ফর্ম ডাউনলোড করুন অথবা সরাসরি ইনবক্সে যোগাযোগ করুন।",
                "আপনার আবেদন সংক্রান্ত প্রশ্নের জন্য আমাদের ইনবক্সে মেসেজ করুন, আমরা সাহায্য করবো।",
                "আবেদন প্রক্রিয়া সম্পর্কে বিস্তারিত জানতে দয়া করে আমাদের সাথে যোগাযোগ করুন।"
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
                "Sorry for any inconvenience. Please message us for details.",
                "আমরা এই বিষয়ে খোঁজ নিয়ে জানাবো।"
            ]
        else:
            fallbacks = [
                "আমাদের পেজ সম্পর্কিত কোনো প্রশ্ন থাকলে ইনবক্সে মেসেজ করুন, আমরা সাহায্য করবো।",
                "আমাদের সেবা বা পণ্য সম্পর্কে জানতে ইনবক্সে যোগাযোগ করুন।",
                "আপনার প্রশ্নের উত্তর পেতে দয়া করে আমাদের সাথে সরাসরি যোগাযোগ করুন।"
            ]
        return random.choice(fallbacks)

    def generate_reply(self, comment):
        start_time = time.time()
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
            context += "\n"
        system_prompt = """You are a Facebook page manager. Reply to comments STRICTLY based on provided page information only.

STRICT RULES:
1. NEVER answer questions beyond the provided page information
2. If asked about something not in page info, respond with polite fallback responses
3. Keep replies under 50 words maximum
4. Don't give general advice, tips, or external information
5. Only mention services/products/info that are specifically provided
6. If comment is about something you don't have info about, acknowledge but don't elaborate

RESPONSE STYLE:
- Positive comments: Thank briefly
- Questions: Answer ONLY if info exists in page details
- Complaints: Apologize briefly, offer to help via message
- General queries: Redirect to "contact us" if no specific info available"""

        user_prompt = f"""Page Information Available:
{context}

Current Comment: "{comment}"

IMPORTANT: Reply ONLY based on the page information above. If the comment asks about anything not mentioned in page information, give a brief polite fallback response. Keep reply under 50 words."""

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
            return {"error": str(e)}


# POST-like functionality functions
def process_comment_request(data):
    """
    POST /generate-reply এর মতো functionality
    Input: {"comment": "...", "page_info": "..."}
    Output: {"success": True/False, "data": {...}}
    """
    try:
        # Input validation
        if not isinstance(data, dict):
            return {
                "success": False,
                "message": "Invalid data format. Expected JSON object."
            }

        if "comment" not in data or not data["comment"].strip():
            return {
                "success": False,
                "message": "Comment field is required and cannot be empty."
            }

        # Initialize bot
        bot = FacebookBot()

        # Set page info if provided
        if "page_info" in data and data["page_info"]:
            bot.set_page_info(data["page_info"])

        # Generate reply
        comment = data["comment"].strip()
        result = bot.generate_reply(comment)

        if "error" in result:
            return {
                "success": False,
                "message": result["error"]
            }

        return {
            "success": True,
            "data": {
                "original_comment": comment,
                "reply": result["reply"],
                "sentiment": result["sentiment"],
                "response_time": result["response_time"],
                "controlled": result["controlled"],
                "slang_detected": result["slang_detected"],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Server error: {str(e)}"
        }


def set_page_info_request(data):
    """
    POST /set-page-info এর মতো functionality
    Input: {"page_info": "..."}
    Output: {"success": True/False, "message": "..."}
    """
    try:
        if not isinstance(data, dict) or "page_info" not in data:
            return {
                "success": False,
                "message": "page_info field is required"
            }

        page_info = data["page_info"].strip()
        if not page_info:
            return {
                "success": False,
                "message": "Page information cannot be empty"
            }

        return {
            "success": True,
            "message": "Page information saved successfully",
            "data": {
                "page_info": page_info,
                "word_count": len(page_info.split()),
                "character_count": len(page_info),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "status": "Active"
            }
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


def get_user_input_for_page_info():
    """Get page info from user input"""
    print("\n📋 Set Page Information:")
    print("Enter your Facebook page information (press Enter twice to finish):")

    lines = []
    while True:
        line = input()
        if line == "" and len(lines) > 0:
            break
        elif line == "" and len(lines) == 0:
            continue
        lines.append(line)

    page_info = "\n".join(lines)
    return {"page_info": page_info}


def get_user_input_for_comment():
    """Get comment and page info from user input"""
    print("\n💬 Generate Reply for Comment:")

    # Get comment
    comment = input("Enter the comment: ").strip()
    if not comment:
        return None

    # Ask if user wants to provide page info
    provide_page_info = input("\nDo you want to provide page information? (y/n): ").strip().lower()

    data = {"comment": comment}

    if provide_page_info == 'y':
        print("\nEnter page information (press Enter twice to finish):")
        lines = []
        while True:
            line = input()
            if line == "" and len(lines) > 0:
                break
            elif line == "" and len(lines) == 0:
                continue
            lines.append(line)

        if lines:
            data["page_info"] = "\n".join(lines)

    return data


# Main function for testing
def main():
    print("🤖 Facebook Bot - Interactive Mode")
    print("=" * 50)

    while True:
        print("\n📋 Choose an option:")
        print("1. Set Page Information")
        print("2. Generate Reply for Comment")
        print("3. Show Demo Examples")
        print("4. Exit")

        choice = input("\nEnter your choice (1-4): ").strip()

        if choice == "1":
            # Set page info
            try:
                print("\n" + "=" * 60)
                print("📋 SETTING PAGE INFORMATION")
                print("=" * 60)

                data = get_user_input_for_page_info()

                print("\n📥 INPUT DATA:")
                print(f"Page Info: {data['page_info']}")

                result = set_page_info_request(data)

                print("\n📤 PROCESSING RESULT:")
                print(json.dumps(result, indent=2, ensure_ascii=False))

                if result['success']:
                    print(f"\n✅ SUCCESS: Page information has been saved!")
                    print(f"📊 Statistics:")
                    print(f"   - Words: {result['data']['word_count']}")
                    print(f"   - Characters: {result['data']['character_count']}")
                    print(f"   - Status: {result['data']['status']}")
                else:
                    print(f"\n❌ FAILED: {result['message']}")

            except Exception as e:
                print(f"❌ Error: {str(e)}")

        elif choice == "2":
            # Generate reply
            try:
                print("\n" + "=" * 60)
                print("💬 GENERATING REPLY FOR COMMENT")
                print("=" * 60)

                data = get_user_input_for_comment()
                if data is None:
                    print("❌ Comment cannot be empty!")
                    continue

                print("\n📥 INPUT DATA:")
                print(f"Comment: {data['comment']}")
                if 'page_info' in data:
                    print(f"Page Info: {data['page_info']}")
                else:
                    print("Page Info: Not provided")

                result = process_comment_request(data)

                print("\n📤 PROCESSING RESULT:")
                print(json.dumps(result, indent=2, ensure_ascii=False))

                if result['success']:
                    print(f"\n✅ REPLY GENERATED:")
                    print(f"🔤 Original Comment: {result['data']['original_comment']}")
                    print(f"💬 Bot Reply: {result['data']['reply']}")
                    print(f"😊 Sentiment: {result['data']['sentiment']}")
                    print(f"⏱️ Response Time: {result['data']['response_time']}")
                    print(f"🚫 Slang Detected: {'Yes' if result['data']['slang_detected'] else 'No'}")
                    print(f"✅ Controlled Response: {'Yes' if result['data']['controlled'] else 'No'}")
                else:
                    print(f"\n❌ FAILED: {result['message']}")

            except Exception as e:
                print(f"❌ Error: {str(e)}")

        elif choice == "3":
            # Show demo examples
            print("\n" + "=" * 60)
            print("🎯 DEMO EXAMPLES")
            print("=" * 60)

            examples = [
                {
                    "title": "Normal Comment Example",
                    "data": {
                        "comment": "আপনাদের web development এর দাম কত?",
                        "page_info": "আমাদের কোম্পানি Skill Bangladesh web development এবং mobile app development সার্ভিস প্রদান করে। Web development এর দাম ৫০,০০০ টাকা থেকে শুরু।"
                    }
                },
                {
                    "title": "Slang Detection Example",
                    "data": {
                        "comment": "তোমাদের সার্ভিস shit!",
                        "page_info": "আমাদের কোম্পানি IT সার্ভিস দেয়।"
                    }
                },
                {
                    "title": "Positive Comment Example",
                    "data": {
                        "comment": "আপনাদের কোর্স অনেক ভালো! ধন্যবাদ!",
                        "page_info": "Skill Bangladesh এ আমরা Python, Web Development, এবং Digital Marketing কোর্স করি।"
                    }
                }
            ]

            for i, example in enumerate(examples, 1):
                print(f"\n📋 Example {i}: {example['title']}")
                print("-" * 40)
                print(f"📥 Input:")
                print(f"   Comment: {example['data']['comment']}")
                print(f"   Page Info: {example['data']['page_info']}")

                result = process_comment_request(example['data'])

                print(f"📤 Output:")
                if result['success']:
                    print(f"   Reply: {result['data']['reply']}")
                    print(f"   Sentiment: {result['data']['sentiment']}")
                    print(f"   Slang Detected: {'Yes' if result['data']['slang_detected'] else 'No'}")
                else:
                    print(f"   Error: {result['message']}")
                print()

        elif choice == "4":
            print("👋 Goodbye!")
            break

        else:
            print("❌ Invalid choice! Please enter 1-4.")

        # Ask if user wants to continue
        continue_choice = input("\nDo you want to perform another operation? (y/n): ").strip().lower()
        if continue_choice != 'y':
            print("👋 Goodbye!")
            break


if __name__ == "__main__":
    main()