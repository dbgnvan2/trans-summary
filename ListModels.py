import google.generativeai as genai
from dotenv import load_dotenv
import os

# 1. Load variables from the .env file
load_dotenv()

# 2. Get the API key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found. Check your .env file.")

# 3. Configure the library with your key (THIS IS THE CRITICAL STEP)
genai.configure(api_key=api_key)

# 4. Now that you are authenticated, you can list the models
print("Available models:")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(m.name)
