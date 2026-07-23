
import datetime
from config import MEMORY_PATH, STRATEGY_PATH, TOPICS_PATH
from database import save_post, search_related_posts
from memory import load_json, save_json
from ai import generate_content, review_content
from prompts import build_generation_prompt, build_review_prompt
from telegram_bot import send_message

def get_next_topic(memory):
    topics = load_json(TOPICS_PATH, [])
    covered = set(memory.get("covered_topics", []))
    for t in topics:
        if t["topic"] not in covered:
            return t
    return None

def main():
    memory = load_json(MEMORY_PATH, {})
    strategy = load_json(STRATEGY_PATH, {})

    topic = get_next_topic(memory)
    if not topic:
        print("تمام موضوعات data/topics.json پوشش داده شده. لطفاً موضوعات جدید اضافه کنید.")
        return

    related = search_related_posts(topic["topic"])

    prompt = build_generation_prompt(memory, strategy, related, topic)
    content = generate_content(prompt)

    review = review_content(build_review_prompt(content))
    attempts = 0
    while not review.get("ok", True) and attempts < 2:
        prompt = build_generation_prompt(memory, strategy, related, topic, extra_note=review.get("feedback", ""))
        content = generate_content(prompt)
        review = review_content(build_review_prompt(content))
        attempts += 1

    send_message(content)

    save_post(
        date=str(datetime.date.today()),
        category=topic["category"],
        level=topic["level"],
        title=topic["topic"],
        content=content,
        keywords=topic["topic"],
        status="published",
    )

    memory.setdefault("covered_topics", []).append(topic["topic"])
    save_json(MEMORY_PATH, memory)
    print(f"پست منتشر شد: {topic['topic']}")

if __name__ == "__main__":
    main()