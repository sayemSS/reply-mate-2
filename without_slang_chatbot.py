import os
import re
import requests
import time
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

        # Expanded slang/bad words list (Add more as needed)
        self.slang_words = [
            "মাগি", "খানি", "চোদা", "বিরক্তিকর", "হুদা", "বকবক",
            "fuck", "shit", "bitch", "asshole", "dick", "pussy",
            "slut", "whore", "bastard", "dumbass"
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

    def clean_text(self, text):
        # Remove punctuation and special chars, keep Bengali, English letters, digits, and spaces
        return re.sub(r'[^a-zA-Z0-9অ-হ০-৯ ]', '', text).lower()

    def contains_slang(self, text):
        cleaned = self.clean_text(text)
        for slang in self.slang_words:
            pattern = r'\b' + re.escape(slang) + r'\b'
            if re.search(pattern, cleaned):
                return True
        return False

    def get_sentiment(self, comment):
        positive_words = ['ভালো', 'good', 'great', 'excellent', 'love', 'amazing', 'wonderful', 'thanks', 'ধন্যবাদ']
        negative_words = ['খারাপ', 'bad', 'terrible', 'awful', 'hate', 'horrible', 'angry', 'disappointed']

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

    def get_fallback_response(self, comment, sentiment):
        import random
        comment_lower = comment.lower()

        if any(word in comment_lower for word in ['application', 'apply', 'job', 'আবেদন', 'চাকরি', 'লিখতে']):
            return random.choice([
                "অ্যাপ্লিকেশন লেখার জন্য আমাদের অফিসিয়াল ফর্ম ডাউনলোড করুন অথবা সরাসরি ইনবক্সে যোগাযোগ করুন।",
                "আপনার আবেদন সংক্রান্ত প্রশ্নের জন্য আমাদের ইনবক্সে মেসেজ করুন, আমরা সাহায্য করবো।",
                "আবেদন প্রক্রিয়া সম্পর্কে বিস্তারিত জানতে দয়া করে আমাদের সাথে যোগাযোগ করুন।"
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
                "আপনার প্রশ্নের উত্তর পেতে দয়া করে আমাদের সাথে সরাসরি যোগাযোগ করুন।"
            ]

        return random.choice(fallbacks)

    def generate_reply(self, comment):
        # Check slang first
        if self.contains_slang(comment):
            return {
                "reply": "দয়া করে ভদ্র ভাষায় মন্তব্য করুন। আমরা আপনাকে সাহায্য করতে চাই।",
                "sentiment": "Negative",
                "response_time": "0s",
                "controlled": True
            }

        start_time = time.time()

        context = f"Facebook Page Information: {self.page_info}\n\n"

        if self.previous_comments:
            context += "Recent Comments for Context:\n"
            for prev in self.previous_comments[-3:]:
                context += f"- {prev['comment']} ({prev['timestamp']})\n"
            context += "\n"

        system_prompt = """You are a Facebook page manager. Reply to comments STRICTLY based on provided page information only.

STRICT RULES:
1. NEVER answer questions beyond the provided page information
2. If asked about something not in page info, respond with polite fallback responses (see below)
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
                return f"Error: API call failed ({response.status_code})"

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
                "controlled": self.validate_response(reply, comment)
            }
        except Exception as e:
            return f"Error: {str(e)}"


def main():
    bot = FacebookBot()

    print("🤖 Facebook Page Comment Bot")
    print("=" * 40)

    print("\n📋 First, provide your Facebook page information:")
    page_info = input("Enter page details (business type, services, etc.): ").strip()

    if page_info:
        bot.set_page_info(page_info)
    else:
        print("⚠️ No page info provided. Bot will work with limited context.")

    print("\n📝 Commands:")
    print("- Type comment to get AI reply")
    print("- Type 'info' to update page information")
    print("- Type 'exit' to quit")
    print("=" * 40)

    while True:
        user_input = input("\n💬 Comment: ").strip()

        if user_input.lower() == "exit":
            print("👋 Goodbye!")
            break
        elif user_input.lower() == "info":
            new_info = input("📋 Enter updated page information: ").strip()
            if new_info:
                bot.set_page_info(new_info)
            continue
        elif not user_input:
            print("⚠️ Please enter a comment")
            continue

        print("\n🔄 Generating reply...")
        result = bot.generate_reply(user_input)

        if isinstance(result, dict):
            print(f"\n📊 Sentiment: {result['sentiment']}")
            print(f"⏱️ Time: {result['response_time']}")

            if result.get('controlled', True):
                print("✅ Response: Within page scope")
            else:
                print("⚠️ Response: Used fallback (AI went out of scope)")

            print(f"\n🤖 Reply:\n{result['reply']}")
        else:
            print(f"\n❌ {result}")


if __name__ == "__main__":
    main()