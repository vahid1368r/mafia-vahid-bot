import os
import random
from datetime import datetime, timedelta
from typing import Dict, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    JobQueue,
)
from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

# --- تنظیمات اولیه ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
Base = declarative_base()

# --- مدلهای دیتابیس ---
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String)
    total_games = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    mafia_wins = Column(Integer, default=0)

class Game(Base):
    __tablename__ = 'games'
    id = Column(Integer, primary_key=True)
    chat_id = Column(Integer)
    start_time = Column(String)
    winner = Column(String)
    players = relationship("Player", back_populates="game")

class Player(Base):
    __tablename__ = 'players'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    game_id = Column(Integer, ForeignKey('games.id'))
    role = Column(String)
    alive = Column(Boolean, default=True)
    game = relationship("Game", back_populates="players")

engine = create_engine('sqlite:///mafia.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# --- کلاس مدیریت بازی ---
class MafiaGame:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.players: Dict[int, Dict] = {}  # {user_id: {'name': str, 'role': str, 'alive': bool}}
        self.phase = "LOBBY"
        self.night_actions = {}
        self.votes = {}
        self.start_time = None
        self.job_queue = None

    def assign_roles(self):
        players = list(self.players.values())
        num_players = len(players)
        
        # توزیع نقشها بر اساس تعداد بازیکنان
        roles = []
        if num_players >= 6:
            roles = ['mafia', 'mafia', 'doctor', 'detective'] + ['citizen']*(num_players-4)
        else:
            roles = ['mafia', 'doctor', 'detective'] + ['citizen']*(num_players-3)
        
        random.shuffle(roles)
        for i, (user_id, data) in enumerate(self.players.items()):
            data['role'] = roles[i]

    def check_win_condition(self):
        mafia_alive = sum(1 for p in self.players.values() if p['role'] in ['mafia'] and p['alive'])
        citizens_alive = sum(1 for p in self.players.values() if p['role'] in ['citizen', 'doctor', 'detective'] and p['alive'])
        
        if mafia_alive == 0:
            return "citizens"
        elif mafia_alive >= citizens_alive:
            return "mafia"
        return None

# --- دستورات اصلی ربات ---
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🎭 **به ربات پیشرفته مافیا خوش آمدید!**\n"
        "دستورات قابل استفاده:\n"
        "/newgame - ساخت بازی جدید\n"
        "/join - پیوستن به بازی\n"
        "/startgame - شروع بازی\n"
        "/players - نمایش بازیکنان حاضر"
    )

def new_game(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    context.chat_data['game'] = MafiaGame(chat_id)
    update.message.reply_text(
        "🎮 یک بازی جدید ساخته شد!\n"
        "برای پیوستن به بازی از دستور /join استفاده کنید."
    )

def join_game(update: Update, context: CallbackContext):
    game: MafiaGame = context.chat_data.get('game')
    user = update.effective_user
    
    if not game or game.phase != "LOBBY":
        update.message.reply_text("⚠️ هیچ بازی در حال انتظاری وجود ندارد!")
        return
    
    if user.id not in game.players:
        game.players[user.id] = {'name': user.first_name, 'role': None, 'alive': True}
        update.message.reply_text(f"✅ {user.first_name} به بازی پیوست!")
    else:
        update.message.reply_text("⚠️ شما قبلاً در بازی هستید!")

def start_game(update: Update, context: CallbackContext):
    game: MafiaGame = context.chat_data.get('game')
    
    if len(game.players) < 5:
        update.message.reply_text("❌ حداقل 5 بازیکن نیاز است!")
        return
    
    game.assign_roles()
    game.phase = "NIGHT"
    game.start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # ارسال نقشها به صورت خصوصی
    for user_id, data in game.players.items():
        role_text = "🔫 مافیا" if data['role'] == 'mafia' else "🩺 دکتر" if data['role'] == 'doctor' else "🕵️ کارآگاه" if data['role'] == 'detective' else "👨🌾 شهروند"
        context.bot.send_message(
            chat_id=user_id,
            text=f"🎭 نقش شما: {role_text}\n\n"
            "در طول شب منتظر دستورالعملها باشید!"
        )
    
    context.bot.send_message(
        chat_id=game.chat_id,
        text="🌙 **شب اول آغاز شد!**\n"
        "مافیاها در حال تصمیم گیری هستند... (زمان باقی مانده: 2 دقیقه)"
    )
    
    # زمانبندی برای پایان فاز شب
    context.job_queue.run_once(end_night_phase, 120, context=game.chat_id)

# --- سیستم رأیگیری و اقدامات ---
def end_night_phase(context: CallbackContext):
    game: MafiaGame = context.chat_data.get('game')
    game.phase = "DAY"
    
    # پردازش اقدامات شب
    # (این بخش نیاز به توسعه دارد)
    
    context.bot.send_message(
        chat_id=game.chat_id,
        text="☀️ **روز شد!**\n"
        "همه بازیکنان 3 دقیقه برای بحث و رأیگیری فرصت دارند."
    )
    
    # زمانبندی برای پایان فاز روز
    context.job_queue.run_once(end_day_phase, 180, context=game.chat_id)

def end_day_phase(context: CallbackContext):
    game: MafiaGame = context.chat_data.get('game')
    
    # پردازش رأیها و حذف بازیکن
    # (این بخش نیاز به توسعه دارد)
    
    # بررسی شرایط پیروزی
    winner = game.check_win_condition()
    if winner:
        end_game(context, winner)
    else:
        game.phase = "NIGHT"
        context.bot.send_message(
            chat_id=game.chat_id,
            text="🌙 **شب شد!**\nمافیاها در حال تصمیم گیری هستند..."
        )
        context.job_queue.run_once(end_night_phase, 120, context=game.chat_id)

def end_game(context: CallbackContext, winner: str):
    game: MafiaGame = context.chat_data.get('game')
    
    winner_text = "شهروندان" if winner == "citizens" else "مافیاها"
    context.bot.send_message(
        chat_id=game.chat_id,
        text=f"🏆 **بازی به پایان رسید!**\nبرنده: {winner_text}"
    )
    
    # ذخیره اطلاعات در دیتابیس
    session = Session()
    try:
        new_game = Game(
            chat_id=game.chat_id,
            start_time=game.start_time,
            winner=winner
        )
        session.add(new_game)
        session.commit()
        
        for user_id in game.players:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                user = User(id=user_id)
                session.add(user)
            
            user.total_games += 1
            if (winner == "mafia" and game.players[user_id]['role'] == 'mafia') or \
               (winner == "citizens" and game.players[user_id]['role'] != 'mafia'):
                user.wins += 1
            if game.players[user_id]['role'] == 'mafia':
                user.mafia_wins += 1
        
        session.commit()
    finally:
        session.close()
    
    del context.chat_data['game']

# --- اجرای ربات ---
def main():
    updater = Updater(TOKEN)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('newgame', new_game))
    dp.add_handler(CommandHandler('join', join_game))
    dp.add_handler(CommandHandler('startgame', start_game))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()