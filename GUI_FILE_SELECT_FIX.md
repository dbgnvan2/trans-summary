# GUI File Selection Status Fix

**Date:** 2026-01-11
**Issue:** Clicking on `filename_validated.txt` in the GUI didn't show correct file status
**Status:** ✅ FIXED

---

## Problem

When clicking on a validated file (e.g., `example_validated.txt`) in the Select Source section, the GUI was:
- Setting `base_name = "example_validated"` (WRONG)
- Looking for project folder: `projects/example_validated/` (WRONG)
- Checking for files like: `example_validated_validated.txt` (WRONG)

This caused all status checks to fail because:
- The actual project folder is `projects/example/`
- The validated file is `source/example_validated.txt` (not `example_validated_validated.txt`)

---

## Solution

### Fix 1: Strip `_validated` Suffix from Base Name

**File:** `transcript_processor_gui.py` (lines 523-527)

**Before:**
```python
self.base_name = self.selected_file.stem
```

**After:**
```python
# Get base name and strip _validated suffix if present
base_name = self.selected_file.stem
if base_name.endswith("_validated"):
    base_name = base_name[:-10]  # Remove "_validated" suffix
self.base_name = base_name
```

**Impact:** Now both `example.txt` and `example_validated.txt` result in `base_name = "example"`

---

### Fix 2: Always Check Correct Source and Validated Files

**File:** `transcript_processor_gui.py` (lines 544-550)

**Before:**
```python
checks = [
    ("Source", self.selected_file),  # Wrong if clicked on validated file
    ("Initial Val", self.selected_file.parent / f"{base}_validated{self.selected_file.suffix}"),
```

**After:**
```python
# Always check for the base source file (without _validated)
source_file = config.SOURCE_DIR / f"{base}{self.selected_file.suffix}"
validated_file = config.SOURCE_DIR / f"{base}_validated{self.selected_file.suffix}"

checks = [
    ("Source", source_file),       # Always checks base file
    ("Initial Val", validated_file),  # Always checks validated file
```

**Impact:** Status checks now always look for the correct files regardless of which file was clicked

---

## Behavior After Fix

### Scenario 1: Click on `example.txt`
- ✅ `base_name = "example"`
- ✅ Checks for: `source/example.txt` (Source)
- ✅ Checks for: `source/example_validated.txt` (Initial Val)
- ✅ Looks in: `projects/example/` (project folder)
- ✅ Shows correct status for all processed files

### Scenario 2: Click on `example_validated.txt`
- ✅ `base_name = "example"` (stripped suffix)
- ✅ Checks for: `source/example.txt` (Source)
- ✅ Checks for: `source/example_validated.txt` (Initial Val)
- ✅ Looks in: `projects/example/` (project folder)
- ✅ Shows correct status for all processed files

**Result:** Both scenarios now work identically and correctly!

---

## Testing

### Test Case 1: Original File Exists
Files:
- `source/example.txt` ✅
- `source/example_validated.txt` ✅

**Click on `example.txt`:**
- Source: ✅ (found)
- Initial Val: ✅ (found)
- Other files: Check in `projects/example/`

**Click on `example_validated.txt`:**
- Source: ✅ (found)
- Initial Val: ✅ (found)
- Other files: Check in `projects/example/`

---

### Test Case 2: Only Validated File Exists
Files:
- `source/example.txt` ❌ (doesn't exist)
- `source/example_validated.txt` ✅

**Click on `example_validated.txt`:**
- Source: ❌ (not found - correct!)
- Initial Val: ✅ (found)
- Other files: Check in `projects/example/`

This correctly shows that the original source file is missing.

---

### Test Case 3: Multiple Files
Files:
- `source/webinar1.txt` ✅
- `source/webinar1_validated.txt` ✅
- `source/webinar2_validated.txt` ✅ (no original)

**Click on `webinar1.txt`:**
- base_name: `webinar1` ✅
- Project folder: `projects/webinar1/` ✅

**Click on `webinar1_validated.txt`:**
- base_name: `webinar1` ✅ (stripped)
- Project folder: `projects/webinar1/` ✅

**Click on `webinar2_validated.txt`:**
- base_name: `webinar2` ✅ (stripped)
- Project folder: `projects/webinar2/` ✅
- Source: ❌ (correctly shows missing)

---

## Edge Cases Handled

### 1. File with Multiple Underscores
- File: `my_webinar_recording_validated.txt`
- Result: `base_name = "my_webinar_recording"` ✅
- Only the trailing `_validated` is removed

### 2. File Named "validated.txt"
- File: `validated.txt`
- Result: `base_name = "validated"` ✅
- No suffix removed (doesn't end with `_validated`)

### 3. File Named "something_validated_validated.txt"
- File: `something_validated_validated.txt`
- Result: `base_name = "something_validated"` ✅
- Only one `_validated` suffix removed

---

## Related Code

### Button State Updates
The `update_button_states()` method (called after file selection) uses `self.base_name` to enable/disable buttons. This now works correctly regardless of which file was clicked.

### Formatted File Path
Line 531-532 sets `self.formatted_file` using `self.base_name`. This now correctly points to:
```
projects/example/example-formatted.md
```
Not the incorrect:
```
projects/example_validated/example_validated-formatted.md
```

---

## Files Modified

1. `transcript_processor_gui.py`
   - Lines 523-527: Strip `_validated` suffix from base_name
   - Lines 544-550: Always check correct source and validated files

---

## Impact

**Before:** Users had to click on the exact original filename to see correct status
**After:** Users can click on either the original or validated file to see the same correct status

This makes the GUI more user-friendly and intuitive, especially when the original file has been deleted or moved after validation.

---

## Future Considerations

### If Validation Creates Files in Projects Folder
If in the future the validation process creates files in the `projects/base/` folder instead of `source/`, the validated file check would need to be updated to:

```python
validated_file = project_dir / f"{base}_validated{self.selected_file.suffix}"
```

Currently it assumes validated files are in the source directory alongside the original files.

---

**Status:** ✅ FIXED and tested
**Date:** 2026-01-11
