# Discord Gemini AI Chatbot

A simple, feature-rich, and context-aware Discord chatbot powered by Google's Gemini API (using the latest `google-genai` SDK) and `discord.py`.

## Features
- **AI-Powered Replies**: Automatically replies to messages when mentioned or in direct messages (DMs).
- **Threaded Conversation Flow**: Keeps track of replies to continue conversation threads naturally.
- **20-Message Context Memory**: Keeps a sliding context window of the last 20 messages in the channel to understand multi-user dialog and context.
- **Message Splitting**: Gracefully handles Discord's 2000-character limit by splitting large generated responses into smaller chunks.
- **Typing Indicator**: Shows the bot is "typing" in Discord while generating the Gemini API response.
- **Robust Error Handling**: Handles API failures, missing variables, and Discord permission issues safely.

---

## Prerequisites
- **Python 3.9+** installed on your machine.
- A **Discord Bot Token** from the [Discord Developer Portal](https://discord.com/developers/applications).
- A **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com/).

---

## Setup & Running

1. **Clone or download this repository** to your local machine.

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**:
   - **Windows**:
     ```powershell
     .\venv\Scripts\activate
     ```
   - **macOS / Linux**:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure environment variables**:
   - Rename `.env.example` to `.env`.
   - Open `.env` and fill in your keys:
     ```env
     DISCORD_TOKEN=your_discord_token_here
     GEMINI_API_KEY=your_gemini_key_here
     ```

6. **Start the chatbot**:
   ```bash
   python bot.py
   ```

---

## Discord Developer Portal Settings
To ensure the bot can read chat messages:
1. Navigate to the **Bot** tab of your application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Under **Privileged Gateway Intents**, turn **ON** the **Message Content Intent**.
3. Save changes.
