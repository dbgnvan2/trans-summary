import re

file_path = "pipeline.py"
with open(file_path, "r") as f:
    content = f.read()

# Pattern to match the function up to its final return False in the exception block
# We use dotall to match across lines
pattern = r"(def validate_summary_coverage(base_name: str, logger=None) -> bool:.*?Error validating summary coverage.*?return False)"

match = re.search(pattern, content, re.DOTALL)

if match:
    # The match includes the function body up to the end of the exception block
    # We want to keep everything up to the end of this match
    end_pos = match.end()

    print(f"Found match ending at {end_pos}. Total length: {len(content)}")

    if len(content) > end_pos + 50:  # If there's significant content after
        print("Truncating file...")
        new_content = content[:end_pos] + "\n"
        with open(file_path, "w") as f:
            f.write(new_content)
        print("Done.")
    else:
        print("File appears to be already clean.")
else:
    print("Could not find the specific pattern. Checking file content...")
    # Debug: print last 200 chars to see what's there
    print(content[-200:])
