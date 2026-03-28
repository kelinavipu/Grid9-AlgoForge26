"""
Telegram Bot - Complete Maternal Care System

Features:
- Mother self-registration (new users)
- Main menu with buttons (existing users)
- AI nutrition advisor with time-aware recommendations
- Health summary, alerts, messages, document upload
- Direct communication with healthcare team
"""

import os
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from pymongo import MongoClient
from bson import ObjectId
from groq import Groq

# Load environment
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017')
DB_NAME = os.getenv('DB_NAME', 'matruraksha')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

# MongoDB Connection
mongo_client = None
db = None
mothers_collection = None
messages_collection = None
assessments_collection = None

try:
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client[DB_NAME]
    mothers_collection = db['mothers']
    messages_collection = db['messages']
    assessments_collection = db['assessments']
    # Test connection
    mongo_client.server_info()
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    mongo_client = None
    db = None

# Groq AI Client
groq_client = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("✅ Groq AI client initialized")
    except Exception as e:
        logger.error(f"❌ Groq client initialization failed: {e}")

# Conversation states for registration
(NAME, AGE, PHONE, LOCATION, GESTATIONAL_WEEK, 
 WEIGHT, HEIGHT, EMAIL, CONFIRM) = range(9)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - Check if mother exists or start registration."""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # Check if mother already registered
    if db is not None:
        existing_mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})
        
        if existing_mother:
            # Already registered - SHOW MAIN MENU
            mother_name = existing_mother.get('name', 'there')
            assigned_asha = existing_mother.get('assigned_asha_id')
            assigned_doctor = existing_mother.get('assigned_doctor_id')
            
            if assigned_asha and assigned_doctor:
                welcome_text = (
                    f"👋 Welcome back, *{mother_name}*!\n\n"
                    "✅ Your healthcare team is assigned.\n\n"
                    "What would you like to do today?\n\n"
                    "💬 *Tip:* You can also just type a message to send it to your doctor and ASHA worker!"
                )
            else:
                welcome_text = (
                    f"👋 Welcome back, *{mother_name}*!\n\n"
                    "⏳ Waiting for healthcare team assignment by admin.\n\n"
                    "What would you like to do today?"
                )
            
            # Main menu with buttons
            keyboard = [
                [InlineKeyboardButton("🩺 Health Summary", callback_data='health_summary')],
                [InlineKeyboardButton("📄 Upload Documents", callback_data='upload_docs')],
                [InlineKeyboardButton("🚨 Alerts", callback_data='alerts')],
                [InlineKeyboardButton("👩‍⚕️ Doctor Messages", callback_data='messages')],
                [InlineKeyboardButton("💬 Send Message", callback_data='send_message')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                welcome_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            return ConversationHandler.END
    
    # New mother - Start registration
    welcome_message = (
        "🌸 *Welcome to MatruRaksha!* 🌸\n\n"
        "I'm here to help you during your pregnancy journey.\n\n"
        "Let's get you registered so our healthcare team can assist you.\n\n"
        "📝 *Please enter your full name:*"
    )
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store name and ask for age."""
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("Please enter a valid name (at least 2 characters):")
        return NAME
    
    context.user_data['name'] = name
    
    await update.message.reply_text(
        f"Nice to meet you, *{name}*! 😊\n\n"
        f"📅 *What is your age?*\n"
        f"(Enter a number between 18-45)",
        parse_mode='Markdown'
    )
    return AGE


async def get_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store age and ask for phone."""
    try:
        age = int(update.message.text.strip())
        if age < 15 or age > 50:
            await update.message.reply_text("Please enter a valid age (15-50):")
            return AGE
    except ValueError:
        await update.message.reply_text("Please enter a valid number:")
        return AGE
    
    context.user_data['age'] = age
    
    await update.message.reply_text(
        "📱 *Please enter your phone number:*\n"
        "(Include country code, e.g., +91XXXXXXXXXX)",
        parse_mode='Markdown'
    )
    return PHONE


async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store phone and ask for location."""
    phone = update.message.text.strip()
    
    if len(phone) < 10:
        await update.message.reply_text("Please enter a valid phone number:")
        return PHONE
    
    context.user_data['phone'] = phone
    
    await update.message.reply_text(
        "📍 *What is your location?*\n"
        "(e.g., Village name, District, State)",
        parse_mode='Markdown'
    )
    return LOCATION


async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store location and ask for gestational week."""
    location = update.message.text.strip()
    context.user_data['location'] = location
    
    await update.message.reply_text(
        "🤰 *What is your current gestational week?*\n"
        "(Enter a number between 1-42)\n\n"
        "If you don't know, enter your best estimate.",
        parse_mode='Markdown'
    )
    return GESTATIONAL_WEEK


async def get_gestational_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store gestational week and ask for weight."""
    try:
        week = int(update.message.text.strip())
        if week < 1 or week > 42:
            await update.message.reply_text("Please enter a valid week (1-42):")
            return GESTATIONAL_WEEK
    except ValueError:
        await update.message.reply_text("Please enter a valid number:")
        return GESTATIONAL_WEEK
    
    context.user_data['gestational_week'] = week
    
    # Calculate approximate EDD
    from datetime import timedelta
    weeks_remaining = 40 - week
    edd = datetime.now() + timedelta(weeks=weeks_remaining)
    context.user_data['edd'] = edd.strftime('%Y-%m-%d')
    
    # Optional fields with skip button
    keyboard = [['Skip']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "⚖️ *What is your current weight?* (in kg)\n\n"
        "This is optional. You can type a number or press Skip.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return WEIGHT


async def get_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store weight (optional) and ask for height."""
    weight_text = update.message.text.strip()
    
    if weight_text.lower() != 'skip':
        try:
            weight = float(weight_text)
            if weight < 30 or weight > 150:
                await update.message.reply_text("Please enter a valid weight (30-150 kg) or press Skip:")
                return WEIGHT
            context.user_data['weight'] = weight
        except ValueError:
            await update.message.reply_text("Please enter a valid number or press Skip:")
            return WEIGHT
    
    keyboard = [['Skip']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "📏 *What is your height?* (in cm)\n\n"
        "This is optional. You can type a number or press Skip.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return HEIGHT


async def get_height(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store height (optional) and ask for email."""
    height_text = update.message.text.strip()
    
    if height_text.lower() != 'skip':
        try:
            height = float(height_text)
            if height < 100 or height > 220:
                await update.message.reply_text("Please enter a valid height (100-220 cm) or press Skip:")
                return HEIGHT
            context.user_data['height'] = height
        except ValueError:
            await update.message.reply_text("Please enter a valid number or press Skip:")
            return HEIGHT
    
    keyboard = [['Skip']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "📧 *What is your email address?*\n\n"
        "This is optional. You can type your email or press Skip.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return EMAIL


async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store email (optional) and show confirmation."""
    email_text = update.message.text.strip()
    
    if email_text.lower() != 'skip':
        if '@' not in email_text:
            await update.message.reply_text("Please enter a valid email or press Skip:")
            return EMAIL
        context.user_data['email'] = email_text
    
    # Show confirmation
    data = context.user_data
    
    confirmation_text = (
        "✅ *Please confirm your details:*\n\n"
        f"👤 Name: {data.get('name')}\n"
        f"📅 Age: {data.get('age')}\n"
        f"📱 Phone: {data.get('phone')}\n"
        f"📍 Location: {data.get('location')}\n"
        f"🤰 Gestational Week: {data.get('gestational_week')}\n"
    )
    
    if 'weight' in data:
        confirmation_text += f"⚖️ Weight: {data.get('weight')} kg\n"
    if 'height' in data:
        confirmation_text += f"📏 Height: {data.get('height')} cm\n"
    if 'email' in data:
        confirmation_text += f"📧 Email: {data.get('email')}\n"
    
    confirmation_text += "\nIs this correct?"
    
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Register Me", callback_data='confirm_yes')],
        [InlineKeyboardButton("❌ No, Start Over", callback_data='confirm_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        confirmation_text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )
    return CONFIRM


async def confirm_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle confirmation and save to database."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'confirm_no':
        await query.edit_message_text("Registration cancelled. Use /start to begin again.")
        context.user_data.clear()
        return ConversationHandler.END
    
    # Save to MongoDB
    if db is None:
        await query.edit_message_text(
            "❌ Database connection error. Please try again later.",
            parse_mode='Markdown'
        )
        return ConversationHandler.END
    
    try:
        data = context.user_data
        chat_id = update.effective_chat.id
        
        mother_data = {
            'name': data.get('name'),
            'age': data.get('age'),
            'phone': data.get('phone'),
            'location': data.get('location'),
            'gestational_age': data.get('gestational_week'),
            'edd': data.get('edd'),
            'telegram_chat_id': str(chat_id),
            'telegram_username': update.effective_user.username,
            'registered_via': 'telegram',
            'active': True,
            'risk_level': 'pending',  # Will be updated after first assessment
            'assigned_asha_id': None,
            'assigned_doctor_id': None,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        # Add optional fields
        if 'weight' in data:
            mother_data['weight'] = data.get('weight')
        if 'height' in data:
            mother_data['height'] = data.get('height')
        if 'email' in data:
            mother_data['email'] = data.get('email')
        
        # Insert to database
        result = mothers_collection.insert_one(mother_data)
        mother_id = str(result.inserted_id)
        
        success_message = (
            "🎉 *Registration Successful!* 🎉\n\n"
            f"Welcome to MatruRaksha, {data.get('name')}!\n\n"
            "✅ Your profile has been created.\n"
            "⏳ An admin will assign a healthcare team to you soon.\n\n"
            "Once assigned, you will be able to:\n"
            "• Receive health assessments\n"
            "• Ask questions to your ASHA worker\n"
            "• Get advice from your doctor\n"
            "• Track your pregnancy progress\n\n"
            "Use /help to see available commands.\n"
            "Use /status to check your assignment status.\n\n"
            "Take care! 💚"
        )
        
        await query.edit_message_text(
            success_message,
            parse_mode='Markdown'
        )
        
        logger.info(f"✅ New mother registered: {mother_id} - {data.get('name')}")
        
        # Clear user data
        context.user_data.clear()
        
    except Exception as e:
        logger.error(f"❌ Registration error: {e}")
        await query.edit_message_text(
            "❌ Registration failed. Please try again with /start",
            parse_mode='Markdown'
        )
    
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel registration."""
    await update.message.reply_text(
        "❌ Registration cancelled.\n"
        "Use /start whenever you're ready to register.",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data.clear()
    return ConversationHandler.END


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check registration and assignment status."""
    chat_id = update.effective_chat.id
    
    if db is None:
        await update.message.reply_text("❌ Database connection error.")
        return
    
    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})
    
    if not mother:
        await update.message.reply_text(
            "❌ You are not registered yet.\n"
            "Use /start to register."
        )
        return
    
    # Get assignment status
    asha_assigned = mother.get('assigned_asha_id') is not None
    doctor_assigned = mother.get('assigned_doctor_id') is not None
    
    status_message = f"👤 *Your Status*\n\n"
    status_message += f"Name: {mother.get('name')}\n"
    status_message += f"Age: {mother.get('age')}\n"
    status_message += f"Gestational Week: {mother.get('gestational_age')}\n"
    status_message += f"Risk Level: {mother.get('risk_level', 'pending').upper()}\n\n"
    
    status_message += "*Healthcare Team Assignment:*\n"
    
    if asha_assigned and doctor_assigned:
        status_message += "✅ ASHA Worker: Assigned\n"
        status_message += "✅ Doctor: Assigned\n\n"
        status_message += "Your healthcare team is ready to assist you! 💚"
    elif asha_assigned:
        status_message += "✅ ASHA Worker: Assigned\n"
        status_message += "⏳ Doctor: Pending\n"
    elif doctor_assigned:
        status_message += "⏳ ASHA Worker: Pending\n"
        status_message += "✅ Doctor: Assigned\n"
    else:
        status_message += "⏳ ASHA Worker: Pending\n"
        status_message += "⏳ Doctor: Pending\n\n"
        status_message += "Admin will assign your healthcare team soon."
    
    await update.message.reply_text(status_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message."""
    help_text = (
        "🌸 *MatruRaksha Bot Commands* 🌸\n\n"
        "/start - Main menu with options\n"
        "/status - Check your assignment status\n"
        "/help - Show this help message\n\n"
        "*Main Menu Options:*\n"
        "🩺 Health Summary - View latest assessment\n"
        "📄 Upload Documents - Send lab reports\n"
        "🚨 Alerts - View important notifications\n"
        "👩‍⚕️ Doctor Messages - See messages from your team\n"
        "💬 Send Message - Contact your healthcare team\n\n"
        "*Ask me anything!*\n"
        "Just type questions like:\n"
        "• What should I eat for dinner?\n"
        "• Can I exercise?\n"
        "• Is my BP normal?\n\n"
        "I'll provide personalized advice based on your health data! 🤰💚"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


# ==================== MENU CALLBACK HANDLERS ====================

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses from main menu."""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat.id
    callback_data = query.data
    
    if callback_data == 'health_summary':
        await show_health_summary(chat_id, query)
    elif callback_data == 'upload_docs':
        await show_upload_instructions(chat_id, query)
    elif callback_data == 'alerts':
        await show_alerts(chat_id, query)
    elif callback_data == 'messages':
        await show_messages(chat_id, query)
    elif callback_data == 'send_message':
        await show_send_message_prompt(chat_id, query)


async def show_health_summary(chat_id, query):
    """Show latest health assessment and AI summary."""
    if db is None:
        await query.edit_message_text("❌ Database connection error.")
        return
    
    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})
    if not mother:
        await query.edit_message_text("Please use /start first.")
        return
    
    # Get latest assessment
    assessments = list(assessments_collection.find(
        {'mother_id': mother['_id']}
    ).sort('timestamp', -1).limit(1))
    
    if not assessments:
        message = (
            "📋 *Health Summary*\n\n"
            "No health assessments yet.\n\n"
            "Your ASHA worker will conduct regular health checks.\n\n"
            "Use /start to return to the main menu."
        )
        await query.edit_message_text(message, parse_mode='Markdown')
        return
    
    assessment = assessments[0]
    vitals = assessment.get('vitals', {})
    ai_eval = assessment.get('ai_evaluation', {})
    
    # Extract vitals
    bp_sys = vitals.get('bp_systolic', 'N/A')
    bp_dia = vitals.get('bp_diastolic', 'N/A')
    hb = vitals.get('hemoglobin', 'N/A')
    weight = vitals.get('weight', 'N/A')
    pulse = vitals.get('pulse', 'N/A')
    
    # Risk level
    risk_level = ai_eval.get('risk_level', 'UNKNOWN').upper()
    risk_emoji = {'LOW': '🟢', 'MODERATE': '🟡', 'HIGH': '🟠', 'CRITICAL': '🔴'}.get(risk_level, '⚪')
    
    message = (
        f"📋 *Your Health Summary*\n\n"
        f"{risk_emoji} *Risk Level:* {risk_level}\n\n"
        f"*Latest Vitals:*\n"
        f"• Blood Pressure: {bp_sys}/{bp_dia} mmHg\n"
        f"• Hemoglobin: {hb} g/dL\n"
        f"• Weight: {weight} kg\n"
        f"• Pulse: {pulse} bpm\n\n"
        f"*Assessment Date:* {assessment.get('timestamp', 'N/A')}\n\n"
        f"Use /start to return to the main menu."
    )
    
    await query.edit_message_text(message, parse_mode='Markdown')


async def show_upload_instructions(chat_id, query):
    """Show instructions for uploading documents."""
    message = (
        "📄 *Upload Medical Documents*\n\n"
        "You can upload:\n"
        "• Lab reports (PDF, JPG)\n"
        "• Ultrasound scans (JPG, PNG)\n"
        "• Prescription images\n\n"
        "*How to upload:*\n"
        "1. Click the attachment icon 📎\n"
        "2. Select your document/photo\n"
        "3. Send it to me\n\n"
        "I'll save it to your medical records and notify your doctor.\n\n"
        "Use /start to return to the main menu."
    )
    
    await query.edit_message_text(message, parse_mode='Markdown')


async def show_alerts(chat_id, query):
    """Show critical alerts and notifications."""
    message = (
        "🚨 *Alerts & Notifications*\n\n"
        "No critical alerts at this time. ✅\n\n"
        "You will be notified here if:\n"
        "• Your vitals show concerning trends\n"
        "• Doctor schedules an appointment\n"
        "• ASHA needs to visit you\n"
        "• Important reminders\n\n"
        "Use /start to return to the main menu."
    )
    
    await query.edit_message_text(message, parse_mode='Markdown')


async def show_messages(chat_id, query):
    """Show recent messages from doctor/ASHA."""
    if db is None:
        await query.edit_message_text("❌ Database connection error.")
        return
    
    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})
    if not mother:
        await query.edit_message_text("Please use /start first.")
        return
    
    # Get recent messages from healthcare team
    recent_messages = list(messages_collection.find(
        {'mother_id': mother['_id'], 'message_type': {'$ne': 'from_mother'}}
    ).sort('timestamp', -1).limit(5))
    
    if not recent_messages:
        message = (
            "👩‍⚕️ *Doctor Messages*\n\n"
            "No messages from your healthcare team yet.\n\n"
            "They will send you updates, advice, and follow-up instructions here.\n\n"
            "Use /start to return to the main menu."
        )
    else:
        message = "👩‍⚕️ *Recent Messages*\n\n"
        for msg in recent_messages:
            sender = msg.get('sender_name', 'Healthcare Team')
            content = msg.get('content', '')
            timestamp = msg.get('timestamp', datetime.utcnow())
            message += f"*{sender}* ({timestamp.strftime('%b %d, %H:%M')})\n{content}\n\n"
        message += "Use /start to return to the main menu."
    
    await query.edit_message_text(message, parse_mode='Markdown')


async def show_send_message_prompt(chat_id, query):
    """Prompt mother to send a message."""
    message = (
        "💬 *Send a Message*\n\n"
        "Just type your message below and send it!\n\n"
        "Your message will be delivered to:\n"
        "• Your assigned doctor 👨‍⚕️\n"
        "• Your ASHA worker 👩‍⚕️\n\n"
        "They will respond as soon as possible.\n\n"
        "You can ask about:\n"
        "• Health concerns\n"
        "• Medication questions\n"
        "• Appointment scheduling\n"
        "• Any pregnancy-related questions\n\n"
        "Type your message now... ✍️"
    )
    
    await query.edit_message_text(message, parse_mode='Markdown')


# ==================== AI NUTRITION ADVISOR ====================

def get_time_context():
    """Determine meal context based on current time."""
    now = datetime.now()
    hour = now.hour
    
    if 5 <= hour < 10:
        return {
            "meal_type": "breakfast",
            "greeting": "Good morning",
            "time_specific": "Start your day with a nutritious breakfast"
        }
    elif 10 <= hour < 12:
        return {
            "meal_type": "mid_morning_snack",
            "greeting": "Good morning",
            "time_specific": "A healthy mid-morning snack will keep you energized"
        }
    elif 12 <= hour < 15:
        return {
            "meal_type": "lunch",
            "greeting": "Good afternoon",
            "time_specific": "Let's plan a balanced lunch for you"
        }
    elif 15 <= hour < 17:
        return {
            "meal_type": "afternoon_snack",
            "greeting": "Good afternoon",
            "time_specific": "A nutritious snack will help you stay active"
        }
    elif 17 <= hour < 21:
        return {
            "meal_type": "dinner",
            "greeting": "Good evening",
            "time_specific": "Let's prepare a healthy dinner"
        }
    else:
        return {
            "meal_type": "night_snack",
            "greeting": "Good evening",
            "time_specific": "If you're hungry, here's what you can have"
        }


def is_nutrition_query(message_text):
    """Check if message is about food/nutrition."""
    message_lower = message_text.lower()
    nutrition_keywords = [
        'eat', 'food', 'dinner', 'lunch', 'breakfast', 'snack',
        'hungry', 'meal', 'diet', 'nutrition', 'recipe', 'cook',
        'drink', 'vegetable', 'fruit', 'protein', 'vitamin',
        'should i have', 'can i eat', 'what to eat'
    ]
    return any(keyword in message_lower for keyword in nutrition_keywords)


async def generate_ai_nutrition_response(mother, message_text):
    """Generate AI nutrition recommendation based on health data and time."""
    if not groq_client:
        return None
    
    try:
        # Get time context
        time_ctx = get_time_context()
        
        # Get latest assessment
        assessments = list(assessments_collection.find(
            {'mother_id': mother['_id']}
        ).sort('timestamp', -1).limit(1))
        
        # Build context
        context = f"""
{time_ctx['greeting']}! {time_ctx['time_specific']}.

MOTHER'S PROFILE:
- Name: {mother.get('name')}
- Age: {mother.get('age', 'Unknown')}
- Gestational Week: {mother.get('gestational_age', 'Unknown')}
"""
        
        if assessments:
            assessment = assessments[0]
            vitals = assessment.get('vitals', {})
            ai_eval = assessment.get('ai_evaluation', {})
            
            context += f"""
LATEST HEALTH DATA:
- BP: {vitals.get('bp_systolic', 'N/A')}/{vitals.get('bp_diastolic', 'N/A')} mmHg
- Hemoglobin: {vitals.get('hemoglobin', 'N/A')} g/dL
- Weight: {vitals.get('weight', 'N/A')} kg
- Risk Level: {ai_eval.get('risk_level', 'UNKNOWN')}
"""
        
        # AI Prompt
        prompt = f"""You are a maternal nutrition AI assistant for a pregnant woman in India.

CONTEXT:
{context}

MOTHER'S QUESTION:
"{message_text}"

INSTRUCTIONS:
1. Consider the current time of day ({time_ctx['meal_type']})
2. Consider her health data (BP, hemoglobin, risk level)
3. Provide specific Indian meal suggestions
4. Keep it conversational, warm, and caring
5. Include portion sizes and preparation tips
6. Mention nutrients and benefits
7. Keep response under 300 words

Provide a personalized nutrition recommendation:
"""
        
        # Generate response
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a caring maternal nutrition advisor in India."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"AI nutrition error: {e}")
        return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle regular messages from registered mothers with AI nutrition advisor."""
    chat_id = update.effective_chat.id
    message_text = update.message.text
    
    if db is None:
        return
    
    mother = mothers_collection.find_one({'telegram_chat_id': str(chat_id)})
    
    if not mother:
        await update.message.reply_text(
            "Please register first using /start"
        )
        return
    
    # Check if it's a nutrition query
    if is_nutrition_query(message_text):
        # Show typing indicator
        await update.message.chat.send_action(action="typing")
        
        # Generate AI response
        ai_response = await generate_ai_nutrition_response(mother, message_text)
        
        if ai_response:
            response_text = f"🥗 *Nutrition Advice*\n\n{ai_response}\n\n💚 Stay healthy!"
            await update.message.reply_text(response_text, parse_mode='Markdown')
        else:
            # Fallback if AI fails
            await update.message.reply_text(
                "I'm having trouble generating a response right now. "
                "Please consult your doctor or ASHA worker for nutrition advice."
            )
    else:
        # Regular message - save for healthcare team
        message_data = {
            'mother_id': mother['_id'],
            'mother_name': mother.get('name'),
            'telegram_chat_id': str(chat_id),
            'message_type': 'from_mother',
            'content': message_text,
            'timestamp': datetime.utcnow(),
            'read': False
        }
        
        messages_collection.insert_one(message_data)
        
        await update.message.reply_text(
            "📨 Message received! Your healthcare team will respond soon.\n\n"
            "For emergency situations, please call your local health center."
        )


def main():
    """Start the bot in polling mode."""
    if not BOT_TOKEN:
        print("❌ ERROR: TELEGRAM_BOT_TOKEN not found in .env file")
        return
    
    if db is None:
        print("❌ ERROR: MongoDB connection failed")
        return
    
    print(f"✅ Bot token found: {BOT_TOKEN[:10]}...")
    print("✅ MongoDB connected")
    print("🚀 Starting Telegram bot with mother registration...")
    print("\nBot is running! Press Ctrl+C to stop.\n")
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Registration conversation handler
    registration_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            GESTATIONAL_WEEK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gestational_week)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            CONFIRM: [CallbackQueryHandler(confirm_registration)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    # Register handlers
    app.add_handler(registration_handler)
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback_query))  # Handle menu button clicks
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
