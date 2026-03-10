import subprocess
import sys

def install_pymorphy3():
    """Устанавливает pymorphy3 и словари, если они не установлены."""
    try:
        import pymorphy3
        print("pymorphy3 уже установлен.")
    except ImportError:
        print("Устанавливаю pymorphy3 и словари...")
        subprocess.check_call([
            sys.executable, "-m", "pip", "install",
            "pymorphy3", "pymorphy3-dicts-ru"
        ])
        print("Установка завершена.")

# Вызываем функцию установки перед остальной логикой
install_pymorphy3()

# Теперь импортируем библиотеку
import pymorphy3
import os
import asyncio
import random
import logging
import re
import pymorphy3
from pathlib import Path
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Инициализация морфологического анализатора
morph = pymorphy3.MorphAnalyzer()

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.getenv("BOT_TOKEN", "8153806401:AAEG8Km4AZWROOeCDP0NcyuPY6q2BXyg37c")

# Папка для загрузок
DOWNLOADS_FOLDER = Path("downloads")
DOWNLOADS_FOLDER.mkdir(exist_ok=True)

# Инициализация бота
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==================== СОСТОЯНИЯ FSM ====================
# Состояния для Сталкера
class StalkerStates(StatesGroup):
    waiting_for_nickname = State()
    waiting_for_duration = State()
    waiting_for_mode = State()

# ==================== ХРАНИЛИЩЕ ДАННЫХ ====================

# Хранилище данных для каждого пользователя
user_data = {}

# Словарь для хранения активных сессий сталкера
# Ключ: session_id, Значение: {user_id, chat_id, nickname, duration, mode, start_time, end_time, last_message_time, timer_task}
active_stalker_sessions = {}

# Словарь для отслеживания активной сессии по пользователю
# Ключ: user_id, Значение: session_id
user_active_sessions = {}

# ==================== СПИСКИ ФРАЗ ====================

# Фразы для режима "Гасим"
INSULT_PHRASES = [
    "Эй, морда!",
    "Что, сусальник отсох?",
    "Ну всё, ебать...",
    "Ау-у!",
    "Ку-ку, ёптэ!",
    "Хули молчишь?",
    "Я жду твоих высеров!",
    "Где ты пропал, чучело?",
    "Ну давай, ляпни что-нибудь!",
    "Эй, ты там уснул?",
    "Приём, база ответьте!",
    "Язык проглотил?",
    "Ну что, словарный запас иссяк?",
    "Давай, выдай чё нить!"
]

# Фразы для режима "Хвалим"
COMPLIMENT_PHRASES = [
    "Солнышко, чего молчишь?",
    "Я что, такой надоедливый?",
    "Ну ответь..",
    "Я скучаю без тебя..😣",
    "Ответь, пожалуйста..",
    "Без тебя тут так скучно!",
    "Твои сообщения как лучик света!",
    "Где же ты, радость моя?",
    "Мне так не хватает твоего голоса!",
    "Возвращайся скорее, котик!",
    "Ты самый лучший собеседник!",
    "Жду не дождусь твоего сообщения!",
    "Ты делаешь этот чат лучше!",
    "Без тебя тут совсем тоскливо...",
    "Ну напиши хоть словечко, зайка!"
]

# ==================== ФУНКЦИИ ТРАНСФОРМАЦИИ ====================

def reduplicate(word: str) -> str:
    """Функция для хуификации слова (редупликация)."""
    vowels = 'аеёиоуыэюя'
    rules = {
        'а': 'я', 'о': 'е', 'у': 'ю', 'э': 'е', 'ы': 'и',
        'е': 'е', 'ё': 'ё', 'и': 'и', 'ю': 'ю', 'я': 'я'
    }

    word_lower = word.lower()
    
    for i, char in enumerate(word_lower):
        if char in vowels:
            if len(word_lower) < 2: 
                return word
                
            # Особые случаи
            if word_lower == "овации": return "хуяции"
            if word_lower == "ответ": return "хует"
            if word_lower == "самолёт": return "хуелёт"
            if word_lower == "телек": return "хуелек"
            
            replaced_vowel = rules.get(char, char)
            prefix = "ху" + replaced_vowel
            postfix = word_lower[i+1:]
            
            result = prefix + postfix
            
            if word[0].isupper(): 
                return result.capitalize()
            return result
            
    return word

def make_diminutive(word: str) -> str:
    """Функция для создания уменьшительно-ласкательного слова."""
    word_lower = word.lower()
    
    if len(word_lower) <= 2:
        return word_lower + "ик"
        
    if word_lower.endswith(('а', 'я')):
        return word_lower[:-1] + "очка"
    elif word_lower.endswith(('о', 'е')):
        return word_lower[:-1] + "ечко"
    elif word_lower[-1] in 'бвгджзклмнпрстфхцчшщ':
        return word_lower + "ик"
    elif word_lower.endswith('ь'):
        return word_lower[:-1] + "ька"
    else:
        return word_lower + "ушка"

def extract_nouns(text: str) -> list:
    """Извлекает существительные из текста."""
    tokens = re.findall(r'\w+', text)
    nouns = []
    
    for token in tokens:
        if token.isalpha():
            parsed = morph.parse(token)[0]
            if 'NOUN' in parsed.tag:
                nouns.append(token)
    
    return nouns

# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_keyboard():
    """Возвращает клавиатуру с основными функциями"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👻 Сталкер-хуялкер", callback_data="start_stalker")]
    ])

@dp.message(Command("stalk"))
async def stalk_command(message: types.Message, state: FSMContext):
    """Команда /stalk для быстрого запуска сталкера"""
    user_id = message.from_user.id
    chat_id = user_data.get(user_id, {}).get('group_chat_id')
    
    # Если команда вызвана в группе
    if message.chat.id != user_id:
        # Сохраняем ID группы
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['group_chat_id'] = message.chat.id
        
        # Удаляем сообщение /stalk из группы
        try:
            await bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
            
        await bot.send_message(user_id, "Так, стопэ! Пока не начался пиздец, расставим точки над "Ё". Это НЕ ДЛЯ САБОТАЖА РАБОЧЕГО ПРОЦЕССА! Поэтому лучше не жестить и не ставить таймер надолго. Чтобы запустить бота жми кнопку STALK ниже. Чтобы остановить его раньше окончания работы таймера, запусти бота ещё раз, там будет кнопка СТОП. Можно запускать только одну сессию за раз, но в чате бот может одновременно вести две сессии от разных человек. Фух, вроде всё, погнали: /stalk")
        return
        
    if not chat_id:
        await message.answer("Сначала нажми /start или /stalk в нужной группе!")
        return
    
    # Проверяем, есть ли у пользователя активная сессия
    if user_id in user_active_sessions:
        session_id = user_active_sessions[user_id]
        if session_id in active_stalker_sessions:
            # У пользователя есть активная сессия, показываем кнопку стоп
            session = active_stalker_sessions[session_id]
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛑 Стоп", callback_data="stalker_stop")]
            ])
            
            remaining_time = max(0, int((session['end_time'] - datetime.now()).total_seconds() / 60))
            await message.answer(
                f"У тебя активна сессия отслеживания @{session['nickname']}\n"
                f"Осталось времени: {remaining_time} минут",
                reply_markup=keyboard
            )
            return
        else:
            # Сессия в словаре но её нет в активных, удаляем
            del user_active_sessions[user_id]
        
    # Проверяем количество активных таймеров для этого чата
    active_in_chat = sum(1 for s in active_stalker_sessions.values() if s['chat_id'] == chat_id)
    
    if active_in_chat >= 2:
        await message.answer("Потише, ковбой, пока все места заняты. Подожди немного.")
        return
        
    await state.set_state(StalkerStates.waiting_for_nickname)
    await state.update_data(target_chat_id=chat_id)
    
    await message.answer("Кого заебать? (укажи никнейм в формате @nickname)")

@dp.callback_query(F.data == "start_stalker")
async def start_stalker_mode(query: types.CallbackQuery, state: FSMContext):
    """Начало настройки сталкера или показ кнопки стоп"""
    user_id = query.from_user.id
    chat_id = user_data.get(user_id, {}).get('group_chat_id')
    
    if not chat_id:
        await query.message.answer("Сначала нажми /start в нужной группе!")
        await query.answer()
        return
    
    # Проверяем, есть ли у пользователя активная сессия
    if user_id in user_active_sessions:
        session_id = user_active_sessions[user_id]
        if session_id in active_stalker_sessions:
            # У пользователя есть активная сессия, показываем кнопку стоп
            session = active_stalker_sessions[session_id]
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🛑 Стоп", callback_data="stalker_stop")]
            ])
            
            remaining_time = max(0, int((session['end_time'] - datetime.now()).total_seconds() / 60))
            await query.message.answer(
                f"У тебя активна сессия отслеживания @{session['nickname']}\n"
                f"Осталось времени: {remaining_time} минут",
                reply_markup=keyboard
            )
            await query.answer()
            return
        else:
            # Сессия в словаре но её нет в активных, удаляем
            del user_active_sessions[user_id]
        
    # Проверяем количество активных таймеров для этого чата
    active_in_chat = sum(1 for s in active_stalker_sessions.values() if s['chat_id'] == chat_id)
    
    if active_in_chat >= 2:
        await query.message.answer("Потише, ковбой, пока все места заняты. Подожди немного.")
        await query.answer()
        return
        
    await state.set_state(StalkerStates.waiting_for_nickname)
    await state.update_data(target_chat_id=chat_id)
    
    await query.message.answer("Кого заебать? (укажи никнейм в формате @nickname)")
    await query.answer()

@dp.message(StalkerStates.waiting_for_nickname)
async def process_nickname(message: types.Message, state: FSMContext):
    """Обработка никнейма жертвы"""
    nickname = message.text.strip()
    
    # Проверка формата
    if not nickname.startswith('@'):
        await message.answer("Нее, не, не. Так не получится, давай ник жертвы в формате @nickname")
        return
        
    # Убираем @ для удобства хранения
    clean_nickname = nickname[1:].lower()
    
    # Проверка на ник бота
    bot_info = await bot.get_me()
    if clean_nickname == bot_info.username.lower():
        await message.answer("Нее, не, не. Так не получится, давай ник жертвы в формате @nickname")
        return
        
    await state.update_data(nickname=clean_nickname)
    await state.set_state(StalkerStates.waiting_for_duration)
    
    await message.answer(
        "Сколько по времени будем заёбывать?\n"
        "Минимум 1 минута, максимум 24 часа (1440 минут)"
    )

@dp.message(StalkerStates.waiting_for_duration)
async def process_duration(message: types.Message, state: FSMContext):
    """Обработка длительности таймера"""
    try:
        duration = int(message.text.strip())
        if not (1 <= duration <= 1440):
            raise ValueError()
    except ValueError:
        await message.answer("Пожалуйста, введи число от 1 до 1440.")
        return
        
    await state.update_data(duration=duration)
    await state.set_state(StalkerStates.waiting_for_mode)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Гасим", callback_data="stalker_mode_insult")],
        [InlineKeyboardButton(text="Хвалим", callback_data="stalker_mode_compliment")],
    ])
    
    await message.answer("Будем гасить, или хвалить?", reply_markup=keyboard)

@dp.callback_query(F.data.in_(["stalker_mode_insult", "stalker_mode_compliment"]))
async def process_stalker_mode(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора режима и запуск таймера"""
    user_id = callback.from_user.id
    data = await state.get_data()
    target_chat_id = data.get('target_chat_id')
    nickname = data.get('nickname')
    duration = data.get('duration')
    mode = 'insult' if callback.data == 'stalker_mode_insult' else 'compliment'
    
    await state.clear()
    
    # Создаем сессию
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration)
    session_id = f"{target_chat_id}_{nickname}_{start_time.timestamp()}"
    
    # Запускаем фоновую задачу для проверки молчания
    timer_task = asyncio.create_task(check_silence(session_id))
    
    active_stalker_sessions[session_id] = {
        'user_id': user_id,
        'chat_id': target_chat_id,
        'nickname': nickname,
        'duration': duration,
        'mode': mode,
        'start_time': start_time,
        'end_time': end_time,
        'last_message_time': start_time,
        'timer_task': timer_task
    }
    
    # Сохраняем связь пользователя с сессией
    user_active_sessions[user_id] = session_id
    
    await callback.message.answer("Принято, погнали!")
    await callback.answer()

@dp.callback_query(F.data == "stalker_stop")
async def stop_stalker(callback: types.CallbackQuery):
    """Остановка сталкера"""
    user_id = callback.from_user.id
    
    if user_id not in user_active_sessions:
        await callback.message.answer("У тебя нет активных сессий.")
        await callback.answer()
        return
    
    session_id = user_active_sessions[user_id]
    
    if session_id not in active_stalker_sessions:
        # Сессия уже завершена
        del user_active_sessions[user_id]
        await callback.message.answer("Сессия уже завершена.")
        await callback.answer()
        return
    
    session = active_stalker_sessions[session_id]
    chat_id = session['chat_id']
    nickname = session['nickname']
    
    # Отменяем таймер
    if 'timer_task' in session:
        session['timer_task'].cancel()
    
    # Удаляем сессию
    del active_stalker_sessions[session_id]
    del user_active_sessions[user_id]
    
    # Отправляем сообщение в группу
    try:
        await bot.send_message(
            chat_id,
            f"Ок, я стопнул отслеживание @{nickname}. Пока!"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения: {e}")
    
    await callback.message.answer("✅ Отслеживание остановлено!")
    await callback.answer()

# ==================== ФОНОВЫЕ ЗАДАЧИ ====================

async def check_silence(session_id: str):
    """Фоновая задача, которая проверяет, не молчит ли жертва"""
    try:
        while session_id in active_stalker_sessions:
            session = active_stalker_sessions[session_id]
            now = datetime.now()
            
            # Проверяем, не истекло ли время
            if now >= session['end_time']:
                await bot.send_message(session['chat_id'], "Ну, хватит на сегодня, я отдыхать..")
                # Удаляем связь пользователя с сессией
                user_id = session.get('user_id')
                if user_id and user_id in user_active_sessions:
                    del user_active_sessions[user_id]
                del active_stalker_sessions[session_id]
                break
                
            # Проверяем время молчания
            time_since_last_msg = (now - session['last_message_time']).total_seconds() / 60
            
            # Случайный интервал от 5 до 15 минут
            target_interval = random.randint(5, 15)
            
            if time_since_last_msg >= target_interval:
                # Жертва молчит, отправляем сообщение
                phrase_list = INSULT_PHRASES if session['mode'] == 'insult' else COMPLIMENT_PHRASES
                phrase = random.choice(phrase_list)
                
                try:
                    await bot.send_message(
                        session['chat_id'], 
                        f"@{session['nickname']} {phrase}"
                    )
                    # Обновляем время, чтобы не спамить каждую секунду после превышения интервала
                    session['last_message_time'] = now
                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение в чат: {e}")
            
            # Спим минуту перед следующей проверкой
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        pass

# ==================== ОСНОВНЫЕ КОМАНДЫ ============

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Команда /start"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Если команда в группе (chat_id != user_id)
    if chat_id != user_id:
        # Сохраняем ID группы для последующих операций
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['group_chat_id'] = chat_id
        
        # Удаляем сообщение /start из группы
        try:
            await bot.delete_message(chat_id, message.message_id)
            logger.info(f"Сообщение /start удалено из группы {chat_id}")
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение /start: {e}")
        
        # Отправляем приветствие в ЛС
        await bot.send_message(
            user_id,
            f"Привет, {message.from_user.first_name}! 👋\n\n"
            f"Выбери функцию:",
            reply_markup=get_main_keyboard()
        )
    else:
        # Если команда в ЛС, просто отправляем меню
        await message.answer(
            f"Привет, {message.from_user.first_name}! 👋\n\n"
            f"Выбери функцию:",
            reply_markup=get_main_keyboard()
        )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    """Команда /help"""
    help_text = (
        "📖 **Доступные функции:**\n\n"
        "👻 **Сталкер-хуялкер** - отслеживай и хуифицируй жертву\n\n"
        "Используй /start для начала"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message()
async def echo_handler(message: types.Message):
    """Обработчик сообщений жертв сталкера"""
    chat_id = message.chat.id
    text = message.text
    
    if not text:
        return
    
    # Проверяем, является ли отправитель жертвой сталкера в этом чате
    sender_username = message.from_user.username
    
    if sender_username:
        sender_clean = sender_username.lower()
        
        for session_id, session in list(active_stalker_sessions.items()):
            if session['chat_id'] == chat_id and session['nickname'] == sender_clean:
                # Обновляем время последнего сообщения жертвы
                session['last_message_time'] = datetime.now()
                
                # Ищем существительные в сообщении
                nouns = extract_nouns(text)
                
                if nouns:
                    # Выбираем случайное существительное
                    target_word = random.choice(nouns)
                    
                    if session['mode'] == 'insult':
                        response = reduplicate(target_word)
                    else:
                        response = make_diminutive(target_word)
                else:
                    # Если существительных нет, отправляем рандомную фразу
                    phrase_list = INSULT_PHRASES if session['mode'] == 'insult' else COMPLIMENT_PHRASES
                    response = random.choice(phrase_list)
                
                try:
                    await message.reply(response)
                except Exception as e:
                    logger.error(f"Ошибка при отправке ответа: {e}")
                
                return  # Прерываем обработку

# ==================== POLLING ============

async def main():
    """Главная функция для запуска бота с polling"""
    logger.info("Бот запущен с использованием polling")
    
    try:
        # Удаляем вебхук если он был установлен
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Вебхук удален")
    except Exception as e:
        logger.warning(f"Ошибка при удалении вебхука: {e}")
    
    # Запускаем polling
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
