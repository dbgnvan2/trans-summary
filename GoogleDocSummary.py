from dotenv import load_dotenv
import os
import google.generativeai as genai
from google.api_core import exceptions
import argparse

load_dotenv()

# --- Configuration ---
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY environment variable not set!")
genai.configure(api_key=api_key)


def main():
    # --- Argument Parsing ---
    parser = argparse.ArgumentParser(
        description="Generate a summary from a transcript using the Gemini API.")
    parser.add_argument("transcript_file", nargs='?', default="transcript.txt",
                        help="Path to the transcript file. Defaults to 'transcript.txt'.")
    parser.add_argument("-p", "--prompt-file", default="Prompt Transcript Summary A and B.md",
                        help="Path to the prompt instructions file. Defaults to 'Prompt Transcript Summary A and B.md'.")
    parser.add_argument("-o", "--output-file", default="summary_output.md",
                        help="Path to save the output summary. Defaults to 'summary_output.md'.")
    parser.add_argument("-m", "--model", default=os.getenv("GEMINI_MODEL", "gemini-1.5-pro-latest"),
                        help="The Gemini model to use for generation.")
    args = parser.parse_args()

    # --- Main Logic ---
    try:
        # 1. Read the content from your files
        print(f"Reading transcript from: {args.transcript_file}")
        with open(args.transcript_file, 'r', encoding='utf-8') as f:
            transcript_content = f.read()

        with open(args.prompt_file, 'r', encoding='utf-8') as f:
            prompt_instructions = f.read()

        # 2. Combine instructions and the transcript into a single prompt
        full_prompt = f"{prompt_instructions}\n\n---\n\nHere is the transcript to process:\n\n{transcript_content}"

        # 3. Call the Gemini API
        print(
            f"Sending request to the Gemini API using model '{args.model}'... this may take a moment.")
        model = genai.GenerativeModel(args.model)
        response = model.generate_content(full_prompt)

        # 4. Save the output
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(response.text)

        print(f"✅ Success! Output saved to {args.output_file}")

    except FileNotFoundError as e:
        print(f"❌ Error: File not found. Make sure '{e.filename}' exists.")
    except exceptions.GoogleAPICallError as e:
        print(f"❌ An error occurred with the API call: {e}")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
