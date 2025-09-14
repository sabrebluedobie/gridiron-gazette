import os

def get_openai_key():
    return os.getenv("OPENAI_API_KEY")

# wherever you init your OpenAI client:
api_key = get_openai_key()

# Example: parse arguments using argparse
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--llm-blurbs', action='store_true', help='Request LLM blurbs')
args = parser.parse_args()

if not api_key and args.llm_blurbs:
    raise RuntimeError("OPENAI_API_KEY not set, but --llm-blurbs was requested.")
# e.g. openai = OpenAI(api_key=api_key)
