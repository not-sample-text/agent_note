import requests
import os
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import time

# --- Configuration ---
LOG_FILE = "websinu_agent.log"
# GRADES_FILE will be dynamically determined per user (e.g., previous_grades_USER1.json)
DELAY_BETWEEN_USERS_SECONDS = 5 # Small delay to avoid overwhelming the server
# --- End Configuration ---

def log_message(message, level="INFO"):
    """Appends a timestamped message to the log file and prints to console."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] [{level}] {message}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
    print(f"[{level}] {message}")


def send_ntfy_notification(global_ntfy_topic_url, message, title="WebSinu Grades Update", tags=None):
    """
    Sends a notification to an Ntfy topic.
    """
    if not global_ntfy_topic_url:
        log_message("Ntfy topic URL is not configured. Cannot send notification.", level="WARNING")
        return

    try:
        headers = {
            "Title": title,
        }
        if tags:
            headers["Tags"] = ",".join(tags)

        response = requests.post(global_ntfy_topic_url, data=message.encode('utf-8'), headers=headers)
        response.raise_for_status()
        log_message(f"Ntfy notification sent successfully: '{message}'", level="INFO")
    except requests.exceptions.RequestException as e:
        log_message(f"Failed to send Ntfy notification: {e}", level="ERROR")
    except Exception as e:
        log_message(f"An unexpected error occurred while sending Ntfy notification: {e}", level="ERROR")


def login_websinu(username, password):
    """
    Logs into the WebSinu account and returns a requests Session object,
    the 'sid' value, and the HTML content of the grades selection page if successful.

    Returns:
        tuple: (requests.Session, str, str) if login is successful,
               otherwise (None, None, None).
    """
    login_url = "https://websinu.utcluj.ro/note/default.asp"
    roluri_url = "https://websinu.utcluj.ro/note/roluri.asp"

    payload = {
        'hidSelfSubmit': 'default.asp',
        'username': username,
        'password': password,
        'submit': ' Intra '
    }

    session = requests.Session()
    session_sid = None
    initial_grades_page_html = None

    try:
        log_message("Attempting initial login POST request...")
        response = session.post(login_url, data=payload)
        response.raise_for_status()

        if "document.frmData.submit()" in response.text and "roluri.asp" in response.text:
            log_message("Detected JavaScript redirect page. Following...")
            soup_intermediate = BeautifulSoup(response.text, 'html.parser')
            form = soup_intermediate.find('form', {'name': 'frmData', 'action': 'roluri.asp'})

            if form:
                sid_input = form.find('input', {'name': 'sid'})
                intermediate_sid = sid_input['value'] if sid_input else ''
                hid_self_submit_input = form.find('input', {'name': 'hidSelfSubmit'})
                intermediate_hid_self_submit = hid_self_submit_input['value'] if hid_self_submit_input else 'roluri.asp'

                if intermediate_sid:
                    log_message(f"Extracted intermediate SID: {intermediate_sid}")
                    second_post_payload = {
                        'hidSelfSubmit': intermediate_hid_self_submit,
                        'sid': intermediate_sid,
                        'hidOperation': '',
                        'hidNume_Facultate': '',
                        'hidNume_Specializare': ''
                    }
                    log_message("Sending second POST request to roluri.asp to complete login...")
                    final_response = session.post(roluri_url, data=second_post_payload)
                    final_response.raise_for_status()

                    initial_grades_page_html = final_response.text

                    final_soup = BeautifulSoup(initial_grades_page_html, 'html.parser')
                    if final_soup.title and final_soup.title.string == "Note din sesiunea curenta":
                        log_message("Successfully completed login sequence and landed on grades selection page!")
                        session_sid = intermediate_sid
                        return session, session_sid, initial_grades_page_html
                    else:
                        log_message("Login sequence completed, but title 'Note din sesiunea curenta' not found on final page.")
                        log_message(f"Final Response content (first 500 chars for debugging):\n{initial_grades_page_html[:500]}")
                        return None, None, None
                else:
                    log_message("Could not extract SID from intermediate redirect page.")
                    return None, None, None
            else:
                log_message("Could not find the intermediate form for JavaScript redirect.")
                return None, None, None
        elif BeautifulSoup(response.text, 'html.parser').title and BeautifulSoup(response.text, 'html.parser').title.string == "Note din sesiunea curenta":
            log_message("Successfully logged into WebSinu directly (no JS redirect detected).")
            initial_grades_page_html = response.text
            soup_direct = BeautifulSoup(initial_grades_page_html, 'html.parser')
            form_on_page = soup_direct.find('form', {'name': 'frmData', 'action': 'roluri.asp'})
            if form_on_page:
                sid_input_direct = form_on_page.find('input', {'name': 'sid'})
                session_sid = sid_input_direct['value'] if sid_input_direct else None
                if session_sid:
                    log_message(f"Extracted SID from directly landed page: {session_sid}")
                    return session, session_sid, initial_grades_page_html
                else:
                    log_message("Error: SID not found on directly landed roluri.asp page form.")
                    return None, None, None
            else:
                log_message("Error: Form 'frmData' not found on directly landed roluri.asp page.")
                return None, None, None
        else:
            log_message(f"Failed to log into WebSinu. Status Code: {response.status_code}")
            log_message(f"Response content (first 500 chars for debugging):\n{response.text[:500]}")
            return None, None, None
    except requests.exceptions.RequestException as e:
        log_message(f"A network or HTTP error occurred during login: {e}", level="ERROR")
        return None, None, None
    except Exception as e:
        log_message(f"An unexpected error occurred during login sequence: {e}", level="ERROR")
        return None, None, None

def get_grades(session, initial_sid, initial_grades_page_html):
    """
    Parses the initial grades selection page HTML to extract necessary data,
    triggers the grade display with a POST request using the initial_sid,
    parses the HTML for grades, and returns them.

    Returns:
        list of dict: A list of dictionaries, each representing a grade entry,
                      or an empty list if no grades are found or an error occurs.
    """
    grades_post_url = "https://websinu.utcluj.ro/note/roluri.asp"

    try:
        log_message("Parsing HTML from successful login to find faculty/specialization link.")
        soup = BeautifulSoup(initial_grades_page_html, 'html.parser')

        sid_to_use = initial_sid
        if not sid_to_use:
            log_message("Error: Initial SID not provided to get_grades. Cannot proceed.", level="ERROR")
            return []
        log_message(f"Using SID obtained from login for grade view: {sid_to_use}")

        view_notes_link = soup.find('a', href=lambda href: href and href.startswith("javascript: NoteSesiuneaCurenta"))

        faculty_name = ""
        specialization_name = ""

        if view_notes_link:
            js_call = view_notes_link['href']
            # This regex extracts the two string arguments from the JS function call
            match = re.search(r"NoteSesiuneaCurenta\('(.*?)',\s*'(.*?)'\)", js_call)
            if match:
                faculty_name = match.group(1).strip()
                specialization_name = match.group(2).strip()
                log_message(f"Found faculty: '{faculty_name}', specialization: '{specialization_name}'")
            else:
                log_message("Could not parse 'NoteSesiuneaCurenta' arguments from link. Regex mismatch?", level="ERROR")
                log_message(f"JavaScript call found: {js_call}", level="ERROR")
                return []
        else:
            log_message("Could not find 'Vizualizare note' link (<a> tag with NoteSesiuneaCurenta call) on the provided HTML.", level="ERROR")
            return []

        post_payload = {
            'hidSelfSubmit': 'roluri.asp',
            'sid': sid_to_use,
            'hidOperation': 'N',
            'hidNume_Facultate': faculty_name,      # Using the dynamically extracted name
            'hidNume_Specializare': specialization_name # Using the dynamically extracted name
        }

        log_message("Sending POST request to display grades...")
        grades_response = session.post(grades_post_url, data=post_payload)
        grades_response.raise_for_status()

        log_message("\n--- Full HTML content AFTER grades POST request (for grade extraction) ---", level="DEBUG")
        log_message(grades_response.text, level="DEBUG")
        log_message("--- End Full HTML content AFTER grades POST --- \n", level="DEBUG")

        soup_grades = BeautifulSoup(grades_response.text, 'html.parser')

        grades_list = []

        for tr in soup_grades.find_all('tr'):
            tds = tr.find_all('td', recursive=False)
            if len(tds) == 6:
                parent_table = tr.find_parent('table')
                if parent_table and 'class' in parent_table.attrs and 'table' in parent_table['class']:
                    try:
                        year = tds[0].get_text(strip=True)
                        semester = tds[1].get_text(strip=True)
                        subject = tds[2].get_text(strip=True).replace('\xa0', ' ').replace('\u00a0', ' ').strip()
                        grade_type = tds[3].get_text(strip=True)
                        date = tds[4].get_text(strip=True)
                        grade_value = tds[5].get_text(strip=True)

                        grades_list.append({
                            'year': year,
                            'semester': semester,
                            'subject': subject,
                            'type': grade_type,
                            'date': date,
                            'grade': grade_value
                        })
                    except IndexError:
                        log_message(f"Skipping malformed row (fewer than 6 TDs): {tr.get_text()}", level="WARNING")

        if not grades_list:
            log_message("No grades found after parsing. The HTML structure might have changed or parsing logic needs adjustment.", level="WARNING")
        return grades_list

    except requests.exceptions.RequestException as e:
        log_message(f"A network or HTTP error occurred while fetching or posting grades: {e}", level="ERROR")
        return []
    except Exception as e:
        log_message(f"An unexpected error occurred during grade parsing: {e}", level="ERROR")
        return []

def load_previous_grades(user_identifier):
    """Loads previously saved grades for a specific user from a JSON file."""
    user_grades_file = f"previous_grades_{user_identifier}.json"
    if os.path.exists(user_grades_file):
        try:
            with open(user_grades_file, 'r', encoding='utf-8') as f:
                grades = json.load(f)
                log_message(f"Loaded {len(grades)} previous grades for user '{user_identifier}' from {user_grades_file}", level="INFO")
                return grades
        except json.JSONDecodeError as e:
            log_message(f"Error decoding JSON from {user_grades_file}: {e}. Starting with empty grades for '{user_identifier}'.", level="ERROR")
            return []
        except Exception as e:
            log_message(f"An error occurred loading previous grades for '{user_identifier}': {e}. Starting with empty grades.", level="ERROR")
            return []
    log_message(f"No previous grades file found for user '{user_identifier}' at {user_grades_file}. Starting with empty grades.", level="INFO")
    return []

def save_current_grades(user_identifier, grades):
    """Saves the current grades for a specific user to a JSON file."""
    user_grades_file = f"previous_grades_{user_identifier}.json"
    try:
        with open(user_grades_file, 'w', encoding='utf-8') as f:
            json.dump(grades, f, indent=4, ensure_ascii=False)
        log_message(f"Saved {len(grades)} current grades for user '{user_identifier}' to {user_grades_file}", level="INFO")
    except Exception as e:
        log_message(f"Error saving current grades for user '{user_identifier}' to {user_grades_file}: {e}", level="ERROR")

def compare_grades(old_grades, new_grades):
    """
    Compares old and new grade lists to find new or changed grades.
    Assumes each grade can be uniquely identified by subject, year, and semester.
    """
    new_grade_entries = []
    changed_grade_entries = []

    old_grades_map = {}
    for grade in old_grades:
        key = (grade['subject'], grade['year'], grade['semester'])
        old_grades_map[key] = grade['grade']

    for new_grade in new_grades:
        key = (new_grade['subject'], new_grade['year'], new_grade['semester'])
        
        if key not in old_grades_map:
            new_grade_entries.append(new_grade)
        elif old_grades_map[key] != new_grade['grade']:
            changed_grade_entries.append({
                'old_grade': old_grades_map[key],
                'new_grade': new_grade['grade'],
                'subject': new_grade['subject'],
                'year': new_grade['year'],
                'semester': new_grade['semester'],
                'date': new_grade['date']
            })
    
    return new_grade_entries, changed_grade_entries


if __name__ == "__main__":
    # Load environment variables from the single .env file
    load_dotenv() 

    current_dir = os.getcwd()
    log_message(f"Current working directory: {current_dir}", level="DEBUG")

    # Define a list of GENERIC user identifiers/nicknames.
    # These will be used as prefixes in your .env file and in log/notification messages.
    # IMPORTANT: When sharing, use generic placeholders here (e.g., "STUDENT_A", "USER_B").
    # NOT in the script you commit to GitHub.
    USER_IDENTIFIERS = ["STUDENT_A", "STUDENT_B"] # Example: replace with generic names if sharing

    # Get the GLOBAL Ntfy topic URL once (from the .env file)
    global_ntfy_topic_url = os.getenv("NTFY_TOPIC_URL")
    
    if not global_ntfy_topic_url:
        log_message("CRITICAL ERROR: NTFY_TOPIC_URL not found in .env. Agent cannot send notifications. Please add NTFY_TOPIC_URL='your_ntfy_topic_url' to your .env file.", level="CRITICAL")
        exit(1) # Exit with an error code

    log_message(f"NTFY_TOPIC_URL loaded: {'Yes' if global_ntfy_topic_url else 'No'}", level="DEBUG")
    send_ntfy_notification(global_ntfy_topic_url, "WebSinu Grades agent started!", title="Agent Status", tags=["robot"])


    # Iterate through each user
    for user_identifier in USER_IDENTIFIERS:
        log_message(f"\n--- Processing grades for user: '{user_identifier}' ---", level="INFO")

        # Dynamically get username and password based on the user_identifier prefix
        websinu_username = os.getenv(f"{user_identifier}_WEBSINU_USERNAME")
        websinu_password = os.getenv(f"{user_identifier}_WEBSINU_PASSWORD")

        log_message(f"'{user_identifier}_WEBSINU_USERNAME' loaded: {'Yes' if websinu_username else 'No'}", level="DEBUG")
        log_message(f"'{user_identifier}_WEBSINU_PASSWORD' loaded: {'Yes' if websinu_password else 'No'}", level="DEBUG")


        if not websinu_username or not websinu_password:
            log_message(f"Error: WebSinu username or password not found in .env for user '{user_identifier}'. Skipping this user.", level="ERROR")
            send_ntfy_notification(
                global_ntfy_topic_url,
                f"WebSinu credentials missing for user '{user_identifier}'. Skipping.",
                title="WebSinu Agent Error",
                tags=["error", "x"]
            )
            continue
        else:
            send_ntfy_notification(global_ntfy_topic_url, f"Agent started checking for user '{user_identifier}'.", title="Agent Status", tags=["robot", "sync"])

            # Load previous grades specific to this user identifier
            previous_grades = load_previous_grades(user_identifier)

            websinu_session, login_sid, initial_grades_html_content = login_websinu(websinu_username, websinu_password)

            if websinu_session and login_sid and initial_grades_html_content:
                log_message(f"\nAttempting to retrieve grades for user '{user_identifier}'...", level="INFO")
                current_grades = get_grades(websinu_session, login_sid, initial_grades_html_content)

                if current_grades:
                    log_message(f"Found {len(current_grades)} current grades for user '{user_identifier}'.", level="INFO")
                    
                    if previous_grades:
                        new_entries, changed_entries = compare_grades(previous_grades, current_grades)

                        if new_entries:
                            for entry in new_entries:
                                # Custom notification message style: <user_identifier>'s new grade for <class> is: <grade>
                                msg = f"New grade for {user_identifier}: {entry['subject']} is {entry['grade']} (on {entry['date']})"
                                send_ntfy_notification(global_ntfy_topic_url, msg, title=f"New WebSinu Grade for {user_identifier}!", tags=["new", "sparkles"])
                                log_message(f"Notified: {msg}", level="INFO")
                        
                        if changed_entries:
                            for entry in changed_entries:
                                # Custom notification message style: <user_identifier>'s grade for <class> changed from <old_grade> to <new_grade>
                                msg = f"Grade for {user_identifier}: {entry['subject']} changed from {entry['old_grade']} to {entry['new_grade']} (on {entry['date']})"
                                send_ntfy_notification(global_ntfy_topic_url, msg, title=f"WebSinu Grade Changed for {user_identifier}!", tags=["changed", "warning"])
                                log_message(f"Notified: {msg}", level="INFO")

                        if not new_entries and not changed_entries:
                            log_message(f"No new or changed grades found for user '{user_identifier}'.", level="INFO")
                            send_ntfy_notification(global_ntfy_topic_url, f"No new grades found for {user_identifier}. All good.", tags=["check"])

                    else:
                        log_message(f"First run or no previous grades found for user '{user_identifier}'. Not comparing, just saving current grades.", level="INFO")
                        send_ntfy_notification(global_ntfy_topic_url, f"First grade check completed for {user_identifier}. Found {len(current_grades)} grades. Will notify on changes.", tags=["info"])

                    save_current_grades(user_identifier, current_grades)

                else:
                    log_message(f"Could not retrieve current grades for user '{user_identifier}'.", level="ERROR")
                    send_ntfy_notification(global_ntfy_topic_url, f"Failed to retrieve grades for {user_identifier}. Check logs.", tags=["warning", "exclamation"])
            else:
                log_message(f"Login failed for user '{user_identifier}'. Cannot proceed to get grades.", level="ERROR")
                send_ntfy_notification(global_ntfy_topic_url, f"WebSinu login failed for {user_identifier}. Check credentials or site changes.", tags=["error", "x"])
        
        # Add a small delay before processing the next user
        if user_identifier != USER_IDENTIFIERS[-1]:
            log_message(f"Pausing for {DELAY_BETWEEN_USERS_SECONDS} seconds before next user...", level="INFO")
            time.sleep(DELAY_BETWEEN_USERS_SECONDS)

    log_message("\n--- All user grade checks completed ---", level="INFO")
    send_ntfy_notification(global_ntfy_topic_url, "All WebSinu grade checks completed!", title="Agent Batch Complete", tags=["checkmark", "bell"])
