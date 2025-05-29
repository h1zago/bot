import telebot
from telebot import types
import requests
import json
import os

BOT_TOKEN = '7802345049:AAG9smadomRJfEwlNAlGXY7WoJiIuBpUUQg'
TMDB_API_KEY = '2ab9e014e0c882d6ede7e2bcdda2c93f'

bot = telebot.TeleBot(BOT_TOKEN)

# Состояния
user_state = {}  # user_id -> индекс текущего фильма в популярных
movie_details_cache = {}
user_genre_state = {}  # user_id -> {'genre_id': int, 'index': int, 'movies': []}
genre_list = {}

# ✅ Загрузка/сохранение списков
LISTS_FILE = 'user_lists.json'

def load_user_lists():
    if os.path.exists(LISTS_FILE):
        with open(LISTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_user_lists():
    with open(LISTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_lists, f, ensure_ascii=False, indent=2)

user_lists = load_user_lists()

# Жанры
def fetch_genres():
    url = f'https://api.themoviedb.org/3/genre/movie/list?api_key={TMDB_API_KEY}&language=ru-RU'
    res = requests.get(url).json()
    return {g['id']: g['name'] for g in res['genres']}

genre_list = fetch_genres()

# Популярные фильмы
def fetch_movies():
    url = f'https://api.themoviedb.org/3/movie/popular?api_key={TMDB_API_KEY}&language=ru-RU'
    return requests.get(url).json()['results']

movies = fetch_movies()

# По жанру
def fetch_movies_by_genre(genre_id):
    url = f'https://api.themoviedb.org/3/discover/movie?api_key={TMDB_API_KEY}&language=ru-RU&with_genres={genre_id}&sort_by=popularity.desc'
    return requests.get(url).json()['results']

# Трейлер
def get_trailer(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={TMDB_API_KEY}&language=ru-RU"
    data = requests.get(url).json()
    for video in data.get('results', []):
        if video['site'] == 'YouTube' and video['type'] == 'Trailer':
            return f"https://www.youtube.com/watch?v={video['key']}"
    return None

# Кнопки
def get_markup(trailer_url=None, include_back=False, is_list=False, list_type=None, movie_id=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if trailer_url:
        markup.add(types.InlineKeyboardButton("🎞️ Трейлер", url=trailer_url))

    if not is_list:
        markup.add(
            types.InlineKeyboardButton("◀️ Предыдущий", callback_data="prev"),
            types.InlineKeyboardButton("▶️ Следующий", callback_data="next")
        )
        markup.add(
            types.InlineKeyboardButton("✅ Уже смотрел", callback_data="watched"),
            types.InlineKeyboardButton("📌 Хочу посмотреть", callback_data="want")
        )
    else:
        if list_type and movie_id:
            markup.add(types.InlineKeyboardButton("🗑 Удалить из списка", callback_data=f"remove_{list_type}_{movie_id}"))

    if not is_list:
        markup.add(types.InlineKeyboardButton("📂 Мои списки", callback_data="lists"))
        markup.add(types.InlineKeyboardButton("🔍 Поиск по жанрам", callback_data="select_genre"))
        if include_back:
            markup.add(types.InlineKeyboardButton("↩️ Вернуться к популярным", callback_data="back_to_main"))
    else:
        markup.add(types.InlineKeyboardButton("↩️ Назад", callback_data="lists"))

    return markup

# Детали фильма
def get_movie_details(movie_id, basic_data=None):
    if movie_id in movie_details_cache:
        return movie_details_cache[movie_id]
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&language=ru-RU"
    data = requests.get(url).json()
    if basic_data:
        data.update({k: basic_data.get(k) for k in ['title', 'poster_path']})
    movie_details_cache[movie_id] = data
    return data

# Отправить фильм из популярных
def send_movie(chat_id, index):
    movie = movies[index]
    details = get_movie_details(movie['id'], movie)
    send_movie_message(chat_id, details, include_back=False)

# Отправить сообщение с фильмом
def send_movie_message(chat_id, details, is_list=False, list_type=None, include_back=False):
    movie_id = details['id']
    title = details.get('title')
    overview = details.get('overview', 'Описание недоступно.')
    rating = details.get('vote_average', '—')
    genres = ", ".join([g['name'] for g in details.get('genres', [])])
    runtime = details.get('runtime')
    release_date = details.get('release_date')
    poster_path = details.get('poster_path')
    trailer_url = get_trailer(movie_id)

    tmdb_url = f"https://www.themoviedb.org/movie/{movie_id}"
    kinopoisk_url = f"https://www.kinopoisk.ru/index.php?kp_query={title}"

    text = f"🎬 *{title}*\n"
    if release_date: text += f"📅 Дата выхода: {release_date}\n"
    if genres: text += f"🎭 Жанры: {genres}\n"
    if runtime: text += f"🕒 Длительность: {runtime} мин.\n"
    text += f"⭐️ Рейтинг: {rating}\n\n{overview}\n\n"
    text += f"[🌐 TMDB]({tmdb_url}) | [🔗 Кинопоиск]({kinopoisk_url})"

    photo_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
    markup = get_markup(trailer_url, include_back=include_back, is_list=is_list, list_type=list_type, movie_id=movie_id)

    if photo_url:
        bot.send_photo(chat_id, photo=photo_url, caption=text, parse_mode='Markdown', reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode='Markdown', reply_markup=markup)

# Отправить фильм из жанра
def send_genre_movie(chat_id, user_id):
    genre_data = user_genre_state[user_id]
    if 'movies' not in genre_data:
        genre_data['movies'] = fetch_movies_by_genre(genre_data['genre_id'])
    movies_list = genre_data['movies']
    if not movies_list:
        bot.send_message(chat_id, "Нет фильмов в этом жанре.")
        return
    index = genre_data['index']
    movie = movies_list[index]
    details = get_movie_details(movie['id'], movie)
    send_movie_message(chat_id, details, include_back=True)

# /start
@bot.message_handler(commands=['start'])
def start(message):
    user_state[message.chat.id] = 0
    send_movie(message.chat.id, 0)

# Обработка колбэков
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = call.message.chat.id
    data = call.data

    if data in ['next', 'prev']:
        if user_id in user_genre_state:
            genre = user_genre_state[user_id]
            count = len(genre['movies'])
            genre['index'] = (genre['index'] + (1 if data == 'next' else -1)) % count
            send_genre_movie(call.message.chat.id, user_id)
        else:
            index = (user_state.get(user_id, 0) + (1 if data == 'next' else -1)) % len(movies)
            user_state[user_id] = index
            send_movie(call.message.chat.id, index)

    elif data in ['watched', 'want']:
        index = user_state.get(user_id, 0)
        movie = movies[index]
        user_lists.setdefault(str(user_id), {'watched': [], 'want': []})
        if movie not in user_lists[str(user_id)][data]:
            user_lists[str(user_id)][data].append(movie)
            save_user_lists()
        bot.answer_callback_query(call.id, f"Добавлено в «{'Смотрел' if data == 'watched' else 'Хочу посмотреть'}» ✅")

    elif data == 'lists':
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Смотрел", callback_data="show_list_watched"),
            types.InlineKeyboardButton("📌 Хочу посмотреть", callback_data="show_list_want")
        )
        markup.add(types.InlineKeyboardButton("↩️ Назад", callback_data="back_to_main"))
        bot.send_message(call.message.chat.id, "📂 Ваши списки:", reply_markup=markup)

    elif data.startswith("show_list_"):
        list_type = data.split("_")[-1]
        movie_list = user_lists.get(str(user_id), {}).get(list_type, [])
        if not movie_list:
            bot.send_message(call.message.chat.id, "Список пуст.")
        else:
            for movie in movie_list:
                details = get_movie_details(movie['id'], movie)
                send_movie_message(call.message.chat.id, details, is_list=True, list_type=list_type)

    elif data.startswith("remove_"):
        _, list_type, movie_id = data.split("_")
        movie_id = int(movie_id)
        user_id_str = str(user_id)
        user_movies = user_lists.get(user_id_str, {}).get(list_type, [])
        updated_list = [m for m in user_movies if m['id'] != movie_id]
        user_lists[user_id_str][list_type] = updated_list
        save_user_lists()
        bot.answer_callback_query(call.id, "Удалено из списка 🗑")

    elif data == 'select_genre':
        markup = types.InlineKeyboardMarkup()
        for genre_id, name in genre_list.items():
            markup.add(types.InlineKeyboardButton(name, callback_data=f'genre_{genre_id}'))
        bot.send_message(call.message.chat.id, "Выберите жанр:", reply_markup=markup)

    elif data.startswith('genre_'):
        genre_id = int(data.split('_')[1])
        user_genre_state[user_id] = {'genre_id': genre_id, 'index': 0}
        send_genre_movie(call.message.chat.id, user_id)

    elif data == 'back_to_main':
        user_genre_state.pop(user_id, None)
        send_movie(call.message.chat.id, user_state.get(user_id, 0))

bot.polling(none_stop=True)
