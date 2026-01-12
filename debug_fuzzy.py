import transcript_utils
import config

original = "The colour is gray"
content = "The color is gray."

start, end, ratio = transcript_utils.find_text_in_content(original, content)
print(f"Start: {start}, End: {end}, Ratio: {ratio}")
print(f"Threshold: {config.VALIDATION_FUZZY_AUTO_APPLY}")
