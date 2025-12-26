
import re

# Sample with extra newlines, missing bold, different italics, etc.
sample_topics = """
### Topic One
This is the description for topic one. It has some text.

*_(~25% of transcript; Sections 1-5)_*

###   Topic Two with Spaces  

This is topic two description.
It spans multiple lines.

_ (~15% of transcript; Section 10) _

### Topic Three (No Percentage Match - Should Skip)
Description.
*_(~2% of transcript)_*

### Topic Four - Weird Formatting
Description here.
[~30% of transcript; Sections 20-25]
"""

# Sample themes with missing bold, different numbering
sample_themes = """
1. **Theme One**: Description of theme one.
*Source Sections: 1, 2*

2. Theme Two: Description of theme two without bold.
- Source Sections: 3, 4

3. **Theme Three**:
Description on new line.
*Source Sections: 5*
"""

def test_topics():
    print("Testing Topics Regex...")
    # The regex from abstract_pipeline.py
    pattern = r'###\s+(.+?)\s*\n\s*(.+?)\s*\n\s*[\*_\-]+(?:\(|\)|\[)?~?(\d+)%[^;]+;\s*Sections?\s+([\d\-,\s]+)(?:\)|\])?[\*_\-]+'
    
    matches = re.findall(pattern, sample_topics, re.DOTALL)
    for m in matches:
        print(f"Match: {m}")
        
    # Expecting Topic One, Topic Two, Topic Four. (Topic Three is < 5% but regex captures it, logic filters it)

def test_themes():
    print("\nTesting Themes Regex...")
    # The regex from abstract_pipeline.py
    pattern = r'\d+\.\s+(?:\*\*)?(.+?)(?:\*\*)?:\s*(.+?)\s*\n\s*[\*_\-]*Source Sections:'
    
    matches = re.findall(pattern, sample_themes, re.DOTALL)
    for m in matches:
        print(f"Match: {m}")

if __name__ == "__main__":
    test_topics()
    test_themes()
