from datetime import datetime
import re

def clean_text(text):
    """Clean unwanted characters like non-breaking spaces and excessive spaces."""
    return text.replace("\xa0", " ").strip()


def parse_date(date_str):
    """Parse dates of the form MM/DD/YYYY. Returns a datetime.date or None."""
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
    except:
        return None
    

def compute_months_diff(d1, d2):
    """
    Returns the number of full months between two date objects.
    """
    return (d2.year - d1.year) * 12 + (d2.month - d1.month)


def extract_credit_limit(lines):
    """
    Extracts the Credit Limit from a list of lines.
    This function looks for the first dollar amount in the lines after finding "Credit Limit".
    """
    # Check if "Credit" and "Limit" appear in the same line
    credit_limit_index = -1

    # If not found, check for consecutive lines
    if credit_limit_index == -1:
        for i in range(len(lines) - 1):
            if "Credit" in lines[i] and "Limit" in lines[i + 1]:
                credit_limit_index = i + 1
                break

    # If we found "Credit Limit", search for the first dollar amount after that
    if credit_limit_index != -1:
        for i in range(credit_limit_index + 1, len(lines)):
            # Clean the line for non-breaking spaces
            cleaned_line = lines[i].replace("\xa0", " ").strip()

            # Match any dollar amount like "$300", "$500.75", etc.
            match = re.search(r"\$([\d,]+(?:\.\d{2})?|\d+)", cleaned_line)
            if match:
                # Return the first matched amount as the Credit Limit
                return int(
                    match.group(1).replace(",", "")
                )  # Remove commas and convert to integer

    # If no Credit Limit found, return None
    return None