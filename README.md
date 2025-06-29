# WebSinu Grades Agent

## 📊 Automated WebSinu Grade Checker with Ntfy Notifications

This Python script is designed to automate the process of checking for new or changed grades on the WebSinu platform (UTCN) and sending real-time notifications via Ntfy. It supports monitoring grades for multiple users from a single instance.

## ✨ Features

- **Automated Login:** Securely logs into WebSinu using credentials from environment variables.
- **Grade Extraction:** Parses HTML content to retrieve current academic grades.
- **Change Detection:** Compares newly fetched grades with previously saved ones to identify:
  - **New Grades:** Grades that appear for the first time.
  - **Changed Grades:** Existing grades whose values have been updated (e.g., from "Necules" to a numerical grade).
- **Ntfy Notifications:** Sends instant, customizable notifications to a single Ntfy topic for all detected changes, clearly indicating which user's grades were updated.
- **Multi-User Support:** Configurable to monitor grades for multiple students concurrently.
- **Logging:** Detailed logging of script activity and errors to a file.
- **Scheduled Execution:** Designed to be run periodically (e.g., via `cron` on Linux/macOS or Task Scheduler on Windows).

## 🚀 Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:

- **Python 3.x**
- **pip** (Python package installer)
- Access to your **WebSinu account(s)** credentials.
- An **Ntfy topic URL**. If you don't have one, visit [Ntfy.sh](https://ntfy.sh/) to set one up. It's free and easy\!

### Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/your-repo-name.git
    cd your-repo-name
    ```

    (Replace `your-username/your-repo-name` with your actual GitHub repository details.)

2.  **Create a Python Virtual Environment (Recommended):**

    ```bash
    python3 -m venv venv
    source venv/bin/activate # On Windows: .\venv\Scripts\activate
    ```

3.  **Install Required Libraries:**

    ```bash
    pip install -r requirements.txt
    ```

    (If `requirements.txt` doesn't exist, generate it first using `pip freeze > requirements.txt` after manually installing `requests`, `beautifulsoup4`, `python-dotenv`.)

### Configuration

Sensitive information like WebSinu credentials and Ntfy topic URLs are stored securely using environment variables, loaded from a `.env` file.

1.  **Create your `.env` file:**
    Copy the provided example environment file:

    ```bash
    cp example.env .env
    ```

2.  **Edit the `.env` file:**
    Open the newly created `.env` file in a text editor and fill in your details.

    **Important:** Do **NOT** commit your `.env` file to Git\! It's already in `.gitignore`.

3.  **Configure `main.py` for Users:**
    Open `main.py` and modify the `USER_IDENTIFIERS` list to match the prefixes you used in your `.env` file.

    ```python
    # In main.py, find this section:
    # ...
    # Define a list of GENERIC user identifiers/nicknames.
    # These will be used as prefixes in your .env file and in log/notification messages.
    USER_IDENTIFIERS = ["STUDENT_A", "STUDENT_B"] # <--- Adjust this list for your users
    # ...
    ```

## 🏃 Running the Agent

### Manual Run (for testing)

You can run the script manually to test the setup:

```bash
source venv/bin/activate # On Windows: .\venv\Scripts\activate
python main.py
```

Check the console output and the `websinu_agent.log` file for activity.

### Scheduled Run (Cron for Linux/macOS)

For continuous monitoring, schedule the script using `cron`.

1.  **Open your crontab:**

    ```bash
    crontab -e
    ```

2.  **Add the cron job entry:**
    Add the following line to the end of the file. Ensure you use the absolute path to your `python3` executable and your `main.py` script.

    ```cron
    0,30 8-23 * * * /usr/bin/python3 /path/to/your/project/main.py >> /path/to/your/project/agent_cron.log 2>&1
    ```

    - **Replace `/path/to/your/project/`** with the actual absolute path to your project directory (e.g., `/home/user/Desktop/agent_note/`).
    - `/usr/bin/python3` is a common path; verify it by running `which python3` in your terminal.
    - `agent_cron.log` will contain general output from cron, while `websinu_agent.log` will contain detailed script logs.

3.  **Save and exit:**

    - `nano`: `Ctrl+X`, then `Y`, then `Enter`.
    - `vim`: `Esc`, then `:wq`, then `Enter`.

### Scheduled Run (Task Scheduler for Windows)

1.  **Open Task Scheduler.**
2.  **Create Basic Task** and follow the wizard.
    - **Name:** `WebSinu Grade Checker`
    - **Trigger:** `Daily`, starting `8:00:00 AM`, recurring `1` day.
    - **Action:** `Start a program`.
    - **Program/script:** `C:\Path\To\Your\Python\python.exe` (e.g., `C:\Python39\python.exe`)
    - **Add arguments (optional):** `main.py` (ensure `main.py` is in the `Start in` directory)
    - **Start in (optional):** `C:\Path\To\Your\Project\Folder` (e.g., `C:\Users\YourUser\Desktop\agent_note`)
3.  **Finish** the wizard.
4.  **Edit task properties:** Find your task in `Task Scheduler Library`. Right-click \> `Properties`.
    - Go to the **Triggers** tab. Double-click your daily trigger.
    - Check `Repeat task every:` and set to `30 minutes`.
    - Set `for a duration of:` to `15 hours and 30 minutes` (to cover 8:00 AM to 11:30 PM).
    - In the **Settings** tab, configure `Stop the task if it runs longer than:` (e.g., `30 minutes`) and `If the task is already running, then the following rule applies:` to `Do not start a new instance`.

## 📄 Logging

The script generates two log files in its directory:

- `websinu_agent.log`: Detailed logs from the Python script itself, including login attempts, grade parsing details, and Ntfy notification outcomes.
- `agent_cron.log`: (Linux/macOS only) Output from the `cron` daemon indicating when the script was launched and any system-level errors.

## ⚠️ Important Considerations

- **WebSinu HTML Changes:** This script relies on the HTML structure of the WebSinu pages. If WebSinu updates its design or internal structure, the parsing logic (`get_grades` function) may need to be adjusted.
- **Rate Limiting:** Running the script too frequently for too many users might trigger rate limiting or temporary bans from the WebSinu server. The `DELAY_BETWEEN_USERS_SECONDS` is a safeguard. Use responsibly.
- **Security:** Your `.env` file contains sensitive credentials. **Never share it and ensure it's properly ignored by Git.**
