import datetime

from config import FEEDBACK_PATH
from memory import load_json, save_json


def add_feedback(post_title, notes):
    feedback_list = load_json(FEEDBACK_PATH, [])
    feedback_list.append({
        "post_title": post_title,
        "notes": notes,
        "date": str(datetime.date.today()),
    })
    save_json(FEEDBACK_PATH, feedback_list)
    print("بازخورد ذخیره شد.")


if __name__ == "__main__":
    title = input("عنوان پست: ")
    notes = input("بازخورد/نظر شما: ")
    add_feedback(title, notes)
