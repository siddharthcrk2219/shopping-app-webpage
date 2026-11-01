"""Milestone I tokenizer; fixed vocabulary enforces the saved training filters."""
import re
TOKEN_REGEX = re.compile(r"[a-zA-Z]+(?:['\-][a-zA-Z]+)?")
def tokenize_review(text):
    return [t for t in TOKEN_REGEX.findall(text.lower()) if len(t)>1]
