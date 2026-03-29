import os
import asyncio
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from config import Config
from ai.voice_processor import VoiceProcessor
from ai.assistant import AIAssistant
from ai.registration_engine import RegistrationEngine
from db.mother_repository import MotherRepository
from models.database import init_db
from scheduler import book_appointment, get_next_available_dates, get_available_slots, get_appointments_for_patient

# Initialize Database for Bot Process
class MockApp:
    config = {'MONGO_URI': Config.MONGO_URI, 'DB_NAME': Config.DB_NAME}

init_db(MockApp)

voice_processor = VoiceProcessor()
ai_assistant = AIAssistant()
reg_engine = RegistrationEngine(ai_assistant)
repo = MotherRepository()

async def send_voice_response(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, session: dict):
    """Helper to generate and send a TTS voice message."""
    user_lang = session.get('preferred_language', 'Hindi')
    voice_path = await voice_processor.text_to_audio(text, lang=user_lang)
    if voice_path and os.path.exists(voice_path):
        with open(voice_path, 'rb') as vf:
            await context.bot.send_voice(chat_id=update.message.chat_id, voice=vf)
        os.remove(voice_path)

def get_keyboard(ui_details):
    """Generates a Telegram keyboard based on UI type."""
    if ui_details['type'] in ['binary', 'choice'] and ui_details['options']:
        keyboard = [[KeyboardButton(opt)] for opt in ui_details['options']]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    elif ui_details['type'] == 'contact':
        keyboard = [[KeyboardButton("📱 Share Phone Number / अपना फोन नंबर साझा करें", request_contact=True)]]
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    return ReplyKeyboardRemove()

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user = update.message.from_user
    
    session = repo.get_session(chat_id)
    if not session:
        # Silently capture the Telegram user's name
        session = {"telegram_id": chat_id, "full_name": user.first_name}
        repo.update_session_data(chat_id, session)

    # Request next step from AI
    _, next_q_text, is_comp, ui_details = reg_engine.provide_next_question(session)

    await update.message.reply_text(
        next_q_text,
        reply_markup=get_keyboard(ui_details)
    )
    await send_voice_response(update, context, next_q_text, session)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show help message."""
    chat_id = update.message.chat_id
    mother = repo.get_mother(chat_id)
    lang = mother.get('preferred_language', 'Hindi') if mother else 'Hindi'
    is_eng = 'English' in lang
    
    if is_eng:
        help_text = (
            "🌸 *MatruRaksha Bot Commands* 🌸\n\n"
            "/start - Main menu / Begin registration\n"
            "/status - Check your health team assignment\n"
            "/tip - Get a personalized daily advice\n"
            "/help - Show this help message\n\n"
            "*Ask me anything!*\n"
            "Just type questions like:\n"
            "• What should I eat for dinner?\n"
            "• Can I exercise?\n"
            "• Is my BP normal?\n\n"
            "I'll provide personalized advice! 🤰💚"
        )
    else:
        help_text = (
            "🌸 *MatruRaksha सहायक कमांड* 🌸\n\n"
            "/start - मुख्य मेनू / पंजीकरण शुरू करें\n"
            "/status - अपनी स्वास्थ्य टीम की स्थिति जांचें\n"
            "/tip - व्यक्तिगत दैनिक सलाह प्राप्त करें\n"
            "/help - यह सहायता संदेश दिखाएं\n\n"
            "*मुझसे कुछ भी पूछें!*\n"
            "ऐसे प्रश्न टाइप करें:\n"
            "• मुझे रात के खाने में क्या खाना चाहिए?\n"
            "• क्या मैं व्यायाम कर सकती हूँ?\n"
            "• क्या मेरा बीपी सामान्य है?\n\n"
            "मैं आपको व्यक्तिगत सलाह दूंगी! 🤰💚"
        )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check registration and assignment status."""
    chat_id = update.effective_chat.id
    mother = repo.get_mother(chat_id)
    
    if not mother:
        await update.message.reply_text(
            "❌ You are not fully registered yet.\nUse /start to register."
        )
        return
    
    lang = mother.get('preferred_language', 'Hindi')
    is_eng = 'English' in lang
    
    # Get assignment status
    asha_assigned = mother.get('assigned_asha_id') is not None
    doctor_assigned = mother.get('assigned_doctor_id') is not None
    
    if is_eng:
        status_message = f"👤 *Your Status*\n\n"
        status_message += f"Name: {mother.get('full_name')}\n"
        status_message += f"Gestational Week: {mother.get('gestational_week', 'N/A')}\n"
        status_message += f"Risk Level: {mother.get('risk_level', 'pending').upper()}\n\n"
        status_message += "*Healthcare Team:*\n"
        status_message += f"✅ ASHA: {'Assigned' if asha_assigned else 'Pending'}\n"
        status_message += f"✅ Doctor: {'Assigned' if doctor_assigned else 'Pending'}\n"
    else:
        status_message = f"👤 *आपकी स्थिति*\n\n"
        status_message += f"नाम: {mother.get('full_name')}\n"
        status_message += f"गर्भावस्था सप्ताह: {mother.get('gestational_week', 'N/A')}\n"
        status_message += f"जोखिम स्तर: {mother.get('risk_level', 'pending').upper()}\n\n"
        status_message += "*स्वास्थ्य टीम:*\n"
        status_message += f"✅ आशा कार्यकर्ता: {'नियुक्त' if asha_assigned else 'लंबित'}\n"
        status_message += f"✅ डॉक्टर: {'नियुक्त' if doctor_assigned else 'लंबित'}\n"
    
    await update.message.reply_text(status_message, parse_mode='Markdown')

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, mother: dict):
    """Shows the main interactive menu for registered mothers."""
    lang = mother.get('preferred_language', 'Hindi')
    is_eng = 'English' in lang
    name = mother.get('full_name', 'there')
    
    if is_eng:
        welcome_text = f"👋 Welcome back, *{name}*!\nHow can I help you today?"
        keyboard = [
            [InlineKeyboardButton("🩺 Health Summary", callback_data='health_summary')],
            [InlineKeyboardButton("📅 Schedule Appointment", callback_data='schedule_appointment')],
            [InlineKeyboardButton("📄 Upload Reports", callback_data='upload_docs')],
            [InlineKeyboardButton("🚨 Alerts", callback_data='alerts')],
            [InlineKeyboardButton("💬 Ask/Message Team", callback_data='send_message')]
        ]
    else:
        welcome_text = f"👋 सुस्वागतम, *{name}*!\nआज मैं आपकी क्या सहायता कर सकती हूँ?"
        keyboard = [
            [InlineKeyboardButton("🩺 स्वास्थ्य सारांश", callback_data='health_summary')],
            [InlineKeyboardButton("📅 अपॉइंटमेंट शेड्यूल करें", callback_data='schedule_appointment')],
            [InlineKeyboardButton("📄 रिपोर्ट अपलोड करें", callback_data='upload_docs')],
            [InlineKeyboardButton("🚨 अलर्ट", callback_data='alerts')],
            [InlineKeyboardButton("💬 टीम से पूछें", callback_data='send_message')]
        ]
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    session = repo.get_session(chat_id)
    
    # 1. Routing: Check if this user is ALREADY REGISTERED as a mother
    mother = repo.get_mother(chat_id)
    
    # 2. Process Input (Voice, Contact, or Text)
    if update.message.contact:
        text_content = update.message.contact.phone_number
    elif update.message.voice:
        voice_file = await context.bot.get_file(update.message.voice.file_id)
        os.makedirs('tmp', exist_ok=True)
        ogg_path = f"tmp/{update.message.voice.file_id}.ogg"
        await voice_file.download_to_drive(ogg_path)
        text_content = voice_processor.audio_to_text(ogg_path)
        os.remove(ogg_path)
    else:
        text_content = update.message.text

    # 3. Handle Registered Mother (Assistant Mode)
    if mother:
        # 1. Main Menu check
        if text_content and text_content.lower() in ['menu', 'main menu', 'नमस्ते', 'hello', 'hi']:
            await show_main_menu(update, context, mother)
            return

        # 2. Nutrition Check
        if text_content and ai_assistant.is_nutrition_query(text_content):
            reply_text = ai_assistant.get_nutrition_advice(text_content, mother)
        else:
            # 3. Default Chat Advisor
            reply_text = ai_assistant.chat_as_pregnancy_friend(text_content, mother)
            
        await update.message.reply_text(reply_text, reply_markup=ReplyKeyboardRemove())
        await send_voice_response(update, context, reply_text, mother)
        return

    # 4. Handle Registration (New User Mode)
    if not session:
        await update.message.reply_text("नमस्ते, शुरू करने के लिए कृपया /start टाइप करें।")
        return
        
    # Registration Engine logic
    extracted, next_q_text, is_comp, ui_details = reg_engine.provide_next_question(session, text_content)
    
    # Update Session Data
    repo.update_session_data(chat_id, extracted)
    new_session = repo.get_session(chat_id)
    
    # Respond with Text + Keyboard + Voice
    if is_comp:
        repo.finalize_registration(chat_id)
        user_lang = new_session.get('preferred_language', 'Hindi')
        if 'English' in user_lang:
            final_msg = "✅ Registration Complete! Your health profile is now active. I am now your pregnancy friend. You can ask me any health questions or just talk to me!"
        else:
            final_msg = "✅ पंजीकरण पूरा हुआ! आपका स्वास्थ्य प्रोफाइल अब सक्रिय है। मैं अब आपकी गर्भावस्था की दोस्त (Pregnancy Friend) हूँ। आप मुझसे कोई भी स्वास्थ्य प्रश्न पूछ सकती हैं या मुझसे बात कर सकती हैं!"
        await update.message.reply_text(final_msg, reply_markup=ReplyKeyboardRemove())
        await send_voice_response(update, context, final_msg, new_session)
    else:
        await update.message.reply_text(next_q_text, reply_markup=get_keyboard(ui_details))
        await send_voice_response(update, context, next_q_text, new_session)

async def check_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Background task to send pending Hindi reminders from MongoDB."""
    due = repo.pop_due_reminders()
    for r in due:
        try:
            await context.bot.send_message(
                chat_id=r['telegram_id'],
                text=r['message']
            )
            
            # Send Voice Note for reminder
            try:
                from ai.voice_processor import VoiceProcessor
                vp = VoiceProcessor()
                
                # Fetch mother to determine correct voice model
                mother_doc = repo.get_mother(r['telegram_id'])
                lang = mother_doc.get('preferred_language', 'Hindi') if mother_doc else 'Hindi'
                
                voice_path = await vp.text_to_audio(r['message'], lang=lang)
                if voice_path and __import__('os').path.exists(voice_path):
                    with open(voice_path, 'rb') as vf:
                        await context.bot.send_voice(chat_id=r['telegram_id'], voice=vf)
                    __import__('os').remove(voice_path)
            except Exception as e:
                print(f"Failed to send audio reminder to {r['telegram_id']}: {e}")

            print(f" Sent reminder to {r['telegram_id']}")
        except Exception as e:
            print(f"Failed to send reminder to {r['telegram_id']}: {e}")

from ai.notification_engine import NotificationEngine

# ...

notifier = NotificationEngine()

async def send_daily_tips(context: ContextTypes.DEFAULT_TYPE):
    """Background task to send personalized daily health tips to all mothers."""
    mothers = repo.get_all_mothers()
    for m in mothers:
        try:
            week = m.get('gestational_week', 'Unknown')
            conditions = f"{m.get('medical_conditions', 'None')}, {m.get('previous_complications', 'None')}"
            lang = m.get('preferred_language', 'Hindi')
            is_eng = 'English' in lang
            
            tip = notifier.generate_daily_tip(week, conditions, lang=lang)
            prefix = "💡 Today's advice:\n" if is_eng else "💡 आज की सलाह:\n"
            
            await context.bot.send_message(
                chat_id=m['telegram_id'],
                text=f"{prefix}{tip}"
            )
            
            # Send Voice Note
            try:
                from ai.voice_processor import VoiceProcessor
                vp = VoiceProcessor()
                voice_path = await vp.text_to_audio(tip, lang=lang)
                if voice_path and __import__('os').path.exists(voice_path):
                    with open(voice_path, 'rb') as vf:
                        await context.bot.send_voice(chat_id=m['telegram_id'], voice=vf)
                    __import__('os').remove(voice_path)
            except Exception as e:
                print(f"Failed to send audio tip to {m.get('telegram_id')}: {e}")
                
            print(f" Sent daily tip to {m['telegram_id']}")
        except Exception as e:
            print(f"Failed to send tip to {m.get('telegram_id')}: {e}")

async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows a mother to request a tip immediately."""
    chat_id = update.message.chat_id
    m = repo.get_mother(chat_id)
    session = repo.get_session(chat_id)
    lang = m.get('preferred_language', 'Hindi') if m else 'Hindi'
    is_eng = 'English' in lang
    
    if not m:
        msg = "Please complete registration first." if is_eng else "कृपया पहले अपनी जानकारी देकर पंजीकरण पूरा करें।"
        await update.message.reply_text(msg)
        return
        
    week = m.get('gestational_week', 'Unknown')
    conditions = f"{m.get('medical_conditions', 'None')}, {m.get('previous_complications', 'None')}"
    
    wait_msg = "I am thinking of a special tip for you, please wait..." if is_eng else "मैं आपके लिए आज खास सलाह सोच रही हूँ, कृपया प्रतीक्षा करें..."
    await update.message.reply_text(wait_msg)
    
    tip = notifier.generate_daily_tip(week, conditions, lang=lang)
    prefix = "💡 Today's advice:\n" if is_eng else "💡 आज की सलाह:\n"
    await update.message.reply_text(f"{prefix}{tip}")
    if session:
        await send_voice_response(update, context, tip, session)

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button presses from main menu."""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat.id
    callback_data = query.data
    mother = repo.get_mother(chat_id)
    lang = mother.get('preferred_language', 'Hindi') if mother else 'Hindi'
    is_eng = 'English' in lang
    
    if callback_data == 'health_summary':
        # Fetch latest assessment
        assessments = repo.get_all_assessments()
        # Filter for this mother
        mother_assessments = [a for a in assessments if a.get('mother_id') == mother.get('_id') or str(a.get('mother_id')) == str(mother.get('_id'))]
        
        if not mother_assessments:
            msg = "No health assessments yet. Your ASHA worker will visit you soon!" if is_eng else "अभी तक कोई स्वास्थ्य मूल्यांकन नहीं हुआ है। आपकी आशा कार्यकर्ता जल्द ही आपसे मिलेंगी!"
            await query.edit_message_text(msg)
            return
            
        latest = mother_assessments[0]
        vitals = latest.get('vitals', {})
        risk = latest.get('ai_evaluation', {}).get('risk_level', 'Unknown').upper()
        
        if is_eng:
            summary = (
                f"📋 *Your Health Summary*\n\n"
                f"🚩 Risk Level: {risk}\n"
                f"• BP: {vitals.get('bp_systolic')}/{vitals.get('bp_diastolic')} mmHg\n"
                f"• Hb: {vitals.get('hemoglobin')} g/dL\n"
                f"• Weight: {vitals.get('weight')} kg\n\n"
                "Type 'menu' to go back."
            )
        else:
            summary = (
                f"📋 *आपका स्वास्थ्य सारांश*\n\n"
                f"🚩 जोखिम स्तर: {risk}\n"
                f"• बीपी: {vitals.get('bp_systolic')}/{vitals.get('bp_diastolic')} mmHg\n"
                f"• हीमोग्लोबिन: {vitals.get('hemoglobin')} g/dL\n"
                f"• वजन: {vitals.get('weight')} kg\n\n"
                "वापस जाने के लिए 'menu' टाइप करें।"
            )
        await query.edit_message_text(summary, parse_mode='Markdown')

    elif callback_data == 'upload_docs':
        msg = ("📄 *Upload Medical Documents*\n\n"
               "Please send a photo or PDF of your reports here. I will save them for your doctor." if is_eng else 
               "📄 *चिकित्सा दस्तावेज अपलोड करें*\n\n"
               "कृपया अपनी रिपोर्ट का फोटो या पीडीएफ यहां भेजें। मैं उन्हें आपके डॉक्टर के लिए सुरक्षित रखूंगी।")
        await query.edit_message_text(msg, parse_mode='Markdown')

    elif callback_data == 'alerts':
        msg = ("🚨 *Alerts*\n\nNo critical alerts. You are doing great!" if is_eng else 
               "🚨 *अलर्ट*\n\nकोई गंभीर अलर्ट नहीं है। आप बहुत अच्छा कर रही हैं!")
        await query.edit_message_text(msg, parse_mode='Markdown')

    elif callback_data == 'send_message':
        msg = ("💬 *Message Team*\n\nJust type your message and I will forward it to your ASHA worker and Doctor." if is_eng else 
               "💬 *टीम को संदेश भेजें*\n\nबस अपना संदेश टाइप करें और मैं इसे आपकी आशा कार्यकर्ता और डॉक्टर को भेज दूंगी।")
        await query.edit_message_text(msg, parse_mode='Markdown')

    elif callback_data == 'schedule_appointment':
        # Show available dates (next 7 days)
        dates = get_next_available_dates(7)
        if not dates:
            no_msg = "No available appointment slots in the next 7 days. Please try later." if is_eng else "अगले 7 दिनों में कोई उपलब्ध स्लॉट नहीं है। कृपया बाद में प्रयास करें।"
            await query.edit_message_text(no_msg)
            return
        
        header = "📅 *Schedule an Appointment*\n\nSelect a date:" if is_eng else "📅 *अपॉइंटमेंट शेड्यूल करें*\n\nतारीख चुनें:"
        keyboard = []
        for d in dates:
            label = f"{d['display']} ({d['free_count']} slots)"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"pick_date_{d['date']}")])
        keyboard.append([InlineKeyboardButton("← Back" if is_eng else "← वापस", callback_data='back_to_menu')])
        await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif callback_data.startswith('pick_date_'):
        chosen_date = callback_data.replace('pick_date_', '')
        context.user_data['sched_date'] = chosen_date
        slots = get_available_slots(chosen_date)
        
        if not slots:
            no_msg = "No slots available on this date. Please pick another." if is_eng else "इस तारीख पर कोई स्लॉट उपलब्ध नहीं है।"
            await query.edit_message_text(no_msg)
            return
        
        from datetime import datetime as dt
        d = dt.strptime(chosen_date, '%Y-%m-%d')
        date_display = d.strftime('%A, %b %d')
        header = f"📅 *{date_display}*\n\nPick a time slot:" if is_eng else f"📅 *{date_display}*\n\nसमय चुनें:"
        
        keyboard = []
        row = []
        for s in slots:
            h = int(s.split(':')[0])
            m = s.split(':')[1]
            ampm = 'PM' if h >= 12 else 'AM'
            h12 = h - 12 if h > 12 else (12 if h == 0 else h)
            label = f"{h12}:{m} {ampm}"
            row.append(InlineKeyboardButton(label, callback_data=f"pick_time_{s}"))
            if len(row) == 3:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        keyboard.append([InlineKeyboardButton("← Back" if is_eng else "← वापस", callback_data='schedule_appointment')])
        await query.edit_message_text(header, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif callback_data.startswith('pick_time_'):
        chosen_time = callback_data.replace('pick_time_', '')
        chosen_date = context.user_data.get('sched_date')
        
        if not chosen_date:
            await query.edit_message_text("Session expired. Please type 'menu' to start again.")
            return
        
        mother_data = repo.get_mother(chat_id)
        name = mother_data.get('full_name', 'Mother') if mother_data else 'Mother'
        
        result = book_appointment(chat_id, name, chosen_date, chosen_time, 'General Checkup')
        
        if result:
            from datetime import datetime as dt
            d = dt.strptime(chosen_date, '%Y-%m-%d')
            date_display = d.strftime('%A, %b %d, %Y')
            h = int(chosen_time.split(':')[0])
            m = chosen_time.split(':')[1]
            ampm = 'PM' if h >= 12 else 'AM'
            h12 = h - 12 if h > 12 else (12 if h == 0 else h)
            time_display = f"{h12}:{m} {ampm}"
            
            if is_eng:
                conf = (f"✅ *Appointment Confirmed!*\n\n"
                       f"📅 Date: {date_display}\n"
                       f"🕐 Time: {time_display}\n"
                       f"📝 Reason: General Checkup\n"
                       f"🆔 ID: {result['id']}\n\n"
                       f"Your doctor will be notified. See you there! 💚")
            else:
                conf = (f"✅ *अपॉइंटमेंट कन्फर्म!*\n\n"
                       f"📅 तारीख: {date_display}\n"
                       f"🕐 समय: {time_display}\n"
                       f"📝 कारण: सामान्य जांच\n"
                       f"🆔 ID: {result['id']}\n\n"
                       f"आपके डॉक्टर को सूचित किया जाएगा। ध्यान रखें! 💚")
            await query.edit_message_text(conf, parse_mode='Markdown')
        else:
            fail = "❌ This slot was just taken. Please try another time." if is_eng else "❌ यह स्लॉट अभी-अभी बुक हो गया। कृपया अन्य समय चुनें।"
            await query.edit_message_text(fail)

    elif callback_data == 'back_to_menu':
        # Re-show main menu
        mother_data = repo.get_mother(chat_id)
        if mother_data:
            name = mother_data.get('full_name', 'there')
            if is_eng:
                welcome_text = f"👋 Welcome back, *{name}*!\nHow can I help you today?"
                keyboard = [
                    [InlineKeyboardButton("🩺 Health Summary", callback_data='health_summary')],
                    [InlineKeyboardButton("📅 Schedule Appointment", callback_data='schedule_appointment')],
                    [InlineKeyboardButton("📄 Upload Reports", callback_data='upload_docs')],
                    [InlineKeyboardButton("🚨 Alerts", callback_data='alerts')],
                    [InlineKeyboardButton("💬 Ask/Message Team", callback_data='send_message')]
                ]
            else:
                welcome_text = f"👋 सुस्वागतम, *{name}*!\nआज मैं आपकी क्या सहायता कर सकती हूँ?"
                keyboard = [
                    [InlineKeyboardButton("🩺 स्वास्थ्य सारांश", callback_data='health_summary')],
                    [InlineKeyboardButton("📅 अपॉइंटमेंट शेड्यूल करें", callback_data='schedule_appointment')],
                    [InlineKeyboardButton("📄 रिपोर्ट अपलोड करें", callback_data='upload_docs')],
                    [InlineKeyboardButton("🚨 अलर्ट", callback_data='alerts')],
                    [InlineKeyboardButton("💬 टीम से पूछें", callback_data='send_message')]
                ]
            await query.edit_message_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

def main():
    if not Config.TELEGRAM_BOT_TOKEN:
        print("Error: Missing TELEGRAM_BOT_TOKEN")
        return
        
    application = Application.builder().token(Config.TELEGRAM_BOT_TOKEN).build()

    # Job Queue for Scheduled Reminders
    if application.job_queue:
        application.job_queue.run_repeating(check_reminders, interval=3600, first=10)
        import datetime
        t = datetime.time(hour=23, minute=30, tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
        application.job_queue.run_daily(send_daily_tips, time=t)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("tip", tip_command))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    application.add_handler(MessageHandler(filters.TEXT | filters.VOICE | filters.CONTACT, handle_message))

    print("🤖 Arogya_bot is running...")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        if "Conflict" in str(e):
            print("\n⚠️ CONFLICT ERROR: Multiple bot instances are running.")
            print("Please CLOSE all other terminal windows running 'run_telegram_bot.py'.")
        else:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()

