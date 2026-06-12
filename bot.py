import os
import sys
import logging
import asyncio
from collections import deque
import discord
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ==========================================
# 1. LOGGING SETUP
# ==========================================
# Configure logging to display clean, timestamped messages in the console.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("DiscordGeminiBot")

# ==========================================
# 2. LOAD & VALIDATE CONFIGURATION
# ==========================================
# Load environment variables from a .env file if it exists in the project root.
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DISCORD_TOKEN:
    logger.critical("CRITICAL ERROR: 'DISCORD_TOKEN' environment variable is not set!")
    logger.critical("Please create a '.env' file based on '.env.example' and add your token.")
    sys.exit(1)

if not GEMINI_API_KEY:
    logger.critical("CRITICAL ERROR: 'GEMINI_API_KEY' environment variable is not set!")
    logger.critical("Please create a '.env' file based on '.env.example' and add your API key.")
    sys.exit(1)

# ==========================================
# 3. INITIALIZE CLIENTS
# ==========================================
# Initialize the Gemini API client.
# The SDK automatically uses the GEMINI_API_KEY environment variable.
try:
    gemini_client = genai.Client()
    logger.info("Gemini API client initialized successfully.")
except Exception as e:
    logger.critical(f"Failed to initialize Gemini API client: {e}")
    sys.exit(1)

# Configure Discord Intents.
# Message Content Intent is required to read the text of messages.
# Make sure to also enable this toggle in the Discord Developer Portal under Bot -> Privileged Gateway Intents.
intents = discord.Intents.default()
intents.message_content = True

discord_client = discord.Client(intents=intents)

# ==========================================
# 4. CHAT HISTORY & CONTEXT MANAGEMENT
# ==========================================
# A dictionary mapping channel IDs to a deque of messages.
# deque(maxlen=20) ensures that we store at most the last 20 messages per channel automatically.
channel_histories = {}

# System instructions define the persona and guidelines for the AI.
SYSTEM_INSTRUCTION = (
    "You are a friendly, helpful, and intelligent AI chatbot in a Discord server. "
    "You are participating in active chats with users. "
    "Use the provided conversation history context to understand what is being discussed. "
    "Keep your answers engaging, natural, and formatted nicely with markdown if helpful. "
    "Do NOT prefix your replies with your name (e.g. do not write 'BotName: Hello'). "
    "Respond directly as the assistant."
)

def add_to_history(message: discord.Message):
    """Appends a message to the channel's sliding history context."""
    channel_id = message.channel.id
    if channel_id not in channel_histories:
        channel_histories[channel_id] = deque(maxlen=20)
    
    # Store essential information about the message.
    # clean_content translates raw user/role mentions to readable strings (e.g., '@User' instead of '<@12345>')
    channel_histories[channel_id].append({
        "author": message.author.display_name,
        "content": message.clean_content,
        "is_self": message.author == discord_client.user
    })

def build_prompt_with_history(message: discord.Message) -> str:
    """Constructs a structured prompt representing the conversation history."""
    channel_id = message.channel.id
    history = channel_histories.get(channel_id, [])
    
    # Compile the message history into a readable dialogue trace
    history_lines = []
    for msg in history:
        role_label = "You (Assistant)" if msg["is_self"] else msg["author"]
        history_lines.append(f"[{role_label}]: {msg['content']}")
    
    history_text = "\n".join(history_lines)
    
    # Build the final prompt with instructions to respond to the last message
    prompt = (
        "Here is the recent conversation history in this channel (up to the last 20 messages):\n\n"
        f"{history_text}\n\n"
        f"Instructions: Provide a response as 'You (Assistant)' replying to the last message from {message.author.display_name}."
    )
    return prompt

# ==========================================
# 5. ASYNC GEMINI API HANDLER
# ==========================================
async def generate_gemini_response(prompt: str) -> str:
    """
    Calls the Gemini API to generate a reply.
    Uses asyncio.to_thread to run this blocking network I/O in a separate thread.
    This prevents the bot's event loop from freezing.
    """
    def make_api_call():
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.7,
            )
        )
        return response.text

    try:
        # Run the blocking SDK call in a separate thread
        text_response = await asyncio.to_thread(make_api_call)
        return text_response
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        raise e

# ==========================================
# 6. DISCORD EVENT LISTENERS
# ==========================================
@discord_client.event
async def on_ready():
    """Triggered when the bot successfully connects to Discord."""
    logger.info(f"Successfully logged in as: {discord_client.user.name} (ID: {discord_client.user.id})")
    logger.info("Bot is ready and listening for mentions and replies!")

@discord_client.event
async def on_message(message: discord.Message):
    """Triggered whenever a message is sent in any channel the bot can access."""
    # 1. Ignore messages from other bots (essential to prevent infinite loops)
    if message.author.bot:
        # If the bot itself sent the message, save it to history so it knows its own context,
        # but do not trigger a response.
        if message.author == discord_client.user:
            add_to_history(message)
        return

    # 2. Add the user's message to the channel's sliding history context
    add_to_history(message)

    # 3. Determine if the bot should reply.
    # Check if the bot is directly mentioned in the message.
    is_mentioned = discord_client.user in message.mentions
    
    # Check if the message is a direct reply to one of our bot's messages.
    is_reply_to_bot = False
    if message.reference and message.reference.resolved:
        resolved_msg = message.reference.resolved
        # Ensure the resolved message is a Message and its author is our bot
        if isinstance(resolved_msg, discord.Message) and resolved_msg.author == discord_client.user:
            is_reply_to_bot = True

    # Also reply if it's a Direct Message (DM)
    is_dm = isinstance(message.channel, discord.DMChannel)

    # If any triggering condition is met, reply with AI-generated text
    if is_mentioned or is_reply_to_bot or is_dm:
        logger.info(f"Responding to message from {message.author} in #{message.channel}")
        
        try:
            # Trigger Discord's 'typing...' indicator while the API generates a response
            async with message.channel.typing():
                # Construct the prompt with channel history context
                prompt = build_prompt_with_history(message)
                
                # Fetch response from Gemini
                reply_text = await generate_gemini_response(prompt)
                
                # If Gemini returned an empty response, handle it
                if not reply_text or reply_text.strip() == "":
                    reply_text = "I received your message, but I'm not sure how to respond."

                # Send the response (handling Discord's 2000-character limit)
                await send_split_reply(message, reply_text)
                
        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)
            # Send a user-friendly error message back to Discord
            try:
                await message.reply(
                    "⚠️ Sorry, I ran into an error while trying to process that request. "
                    "Please check the server logs."
                )
            except Exception as reply_err:
                logger.error(f"Failed to send error reply: {reply_err}")

# ==========================================
# 7. HELPER FUNCTIONS
# ==========================================
async def send_split_reply(original_message: discord.Message, text: str):
    """
    Replies to a message. If the text exceeds Discord's 2000-character limit,
    splits it appropriately and sends subsequent parts as follow-up messages.
    """
    MAX_CHAR = 2000
    
    if len(text) <= MAX_CHAR:
        await original_message.reply(text)
        return

    # Split the message into chunks, attempting to break on newlines or spaces where possible
    chunks = []
    while len(text) > 0:
        if len(text) <= MAX_CHAR:
            chunks.append(text)
            break
        
        # Search backwards from the limit to find a natural split point
        split_idx = text.rfind('\n', 0, MAX_CHAR)
        if split_idx == -1 or split_idx < 1000:
            # If no newline, look for a space character
            split_idx = text.rfind(' ', 0, MAX_CHAR)
        if split_idx == -1 or split_idx < 1000:
            # If no good split point is found, split hard at 2000 characters
            split_idx = MAX_CHAR
            
        chunks.append(text[:split_idx].strip())
        text = text[split_idx:].strip()

    # Reply to the user's message with the first chunk
    first_chunk = chunks[0]
    sent_message = await original_message.reply(first_chunk)
    
    # Send all subsequent chunks as normal messages in the same channel
    for chunk in chunks[1:]:
        if chunk:
            sent_message = await original_message.channel.send(chunk)

# ==========================================
# 8. APPLICATION ENTRYPOINT
# ==========================================
if __name__ == "__main__":
    logger.info("Starting Discord bot...")
    try:
        discord_client.run(DISCORD_TOKEN)
    except discord.errors.LoginFailure:
        logger.critical("Failed to log in: Invalid Discord Bot Token provided!")
    except Exception as e:
        logger.critical(f"An unexpected error occurred while running the bot: {e}")
